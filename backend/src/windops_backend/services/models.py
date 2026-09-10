from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

import httpx
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import ValidationError  # type: ignore[import-untyped]
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.benchmarks.care.anomaly import (
    AnomalyActivationAuthorization,
    AnomalyFeatureWindow,
    AnomalyRuntimeContext,
    ArtifactReference,
    CareAnomalyError,
    build_governed_anomaly_output,
    require_activation_authorization,
    verify_governed_anomaly_output,
)
from windops_backend.benchmarks.care.contract import DATASET_ID
from windops_backend.benchmarks.care.scoring import ThresholdPolicy
from windops_backend.config import ModelInferenceTarget, Settings
from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.models import (
    Alarm,
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkReplayRun,
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
    ScadaSample,
    Turbine,
)
from windops_backend.schemas import ModelRegisterRequest
from windops_backend.services.events import append_domain_event

ALLOWED_MODEL_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "application/octet-stream",
        "application/onnx",
        "application/zip",
    }
)
MAX_MODEL_ARTIFACT_BYTES = 50 * 1024 * 1024
_prediction_locks: dict[str, asyncio.Lock] = {}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ModelInferenceClient(Protocol):
    async def predict(
        self,
        target: ModelInferenceTarget,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int]: ...


class HttpModelInferenceClient:
    """Strict HTTPS JSON client; package bytes are never executed by WindOps."""

    async def predict(
        self,
        target: ModelInferenceTarget,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int]:
        started = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=target.timeout_seconds,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                target.endpoint_url,
                headers={
                    "Authorization": f"Bearer {target.api_token.get_secret_value()}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                json=payload,
            )
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        if response.is_redirect:
            raise RuntimeError("model inference redirects are rejected")
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("model inference response must be a JSON object")
        return body, latency_ms


def _validate_instance(schema: Mapping[str, Any], value: dict[str, Any], label: str) -> None:
    try:
        Draft202012Validator(schema).validate(value)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "$"
        raise InvalidTransitionError(
            f"{label} contract violation at {location}: {exc.message}"
        ) from exc


async def register_model(
    session: AsyncSession,
    request: ModelRegisterRequest,
    *,
    content_size_bytes: int,
    subject: str,
) -> tuple[RegisteredModel, bool]:
    existing = await session.get(RegisteredModel, request.model_id)
    if existing is not None:
        immutable_identity = (
            existing.name,
            existing.version,
            existing.kind,
            existing.artifact_uri,
            existing.artifact_sha256,
            existing.content_type,
            existing.content_size_bytes,
            existing.input_schema,
            existing.output_schema,
            existing.metrics,
            existing.description,
            existing.created_by,
        )
        requested_identity = (
            request.name,
            request.version,
            request.kind,
            request.artifact_uri,
            request.artifact_sha256.lower(),
            request.content_type,
            content_size_bytes,
            request.input_schema,
            request.output_schema,
            request.metrics,
            request.description,
            subject,
        )
        if immutable_identity == requested_identity:
            return existing, True
        raise ConflictError(f"model {request.model_id} already exists with different content")
    same_version = await session.scalar(
        select(RegisteredModel).where(
            RegisteredModel.name == request.name,
            RegisteredModel.version == request.version,
        )
    )
    if same_version is not None:
        raise ConflictError("the model name and version are already registered")
    model = RegisteredModel(
        id=request.model_id,
        name=request.name,
        version=request.version,
        kind=request.kind,
        status="registered",
        artifact_uri=request.artifact_uri,
        artifact_sha256=request.artifact_sha256.lower(),
        content_type=request.content_type,
        content_size_bytes=content_size_bytes,
        input_schema=request.input_schema,
        output_schema=request.output_schema,
        metrics=request.metrics,
        description=request.description,
        created_by=subject,
    )
    session.add(model)
    append_domain_event(
        session,
        event_type="model.registered",
        aggregate_type="model",
        aggregate_id=model.id,
        payload={
            "model_id": model.id,
            "name": model.name,
            "version": model.version,
            "kind": model.kind,
            "artifact_sha256": model.artifact_sha256,
            "created_by": subject,
        },
    )
    await session.flush()
    return model, False


async def create_deployment(
    session: AsyncSession,
    settings: Settings,
    *,
    model_id: str,
    target_id: str,
    stage: str,
    evaluation_gate: dict[str, Any],
    subject: str,
) -> ModelDeployment:
    model = await session.get(RegisteredModel, model_id)
    if model is None:
        raise NotFoundError(f"model {model_id} was not found")
    if model.kind not in {"predictive", "anomaly"}:
        raise InvalidTransitionError("only predictive or anomaly models can use model runtime")
    if target_id not in settings.model_inference_targets:
        raise InvalidTransitionError("the requested inference target is not configured")
    deployment = ModelDeployment(
        id=str(uuid4()),
        model_id=model.id,
        target_id=target_id,
        stage=stage,
        status="staged",
        traffic_percent=0,
        evaluation_gate=evaluation_gate,
        deployed_by=subject,
    )
    session.add(deployment)
    model.status = "staged"
    model.updated_at = datetime.now(UTC)
    append_domain_event(
        session,
        event_type="model.deployment.staged",
        aggregate_type="model_deployment",
        aggregate_id=deployment.id,
        payload={
            "deployment_id": deployment.id,
            "model_id": model.id,
            "target_id": target_id,
            "stage": stage,
            "deployed_by": subject,
        },
    )
    await session.flush()
    return deployment


async def activate_deployment(
    session: AsyncSession,
    *,
    deployment_id: str,
    traffic_percent: int,
    reason: str,
    subject: str,
    rollback_from_id: str | None = None,
    anomaly_authorization: AnomalyActivationAuthorization | None = None,
) -> ModelDeployment:
    selected = await session.scalar(
        select(ModelDeployment).where(ModelDeployment.id == deployment_id).with_for_update()
    )
    if selected is None:
        raise NotFoundError(f"model deployment {deployment_id} was not found")
    model = await session.get(RegisteredModel, selected.model_id)
    if model is None:  # pragma: no cover - protected by foreign key
        raise NotFoundError(f"model {selected.model_id} was not found")
    if model.kind == "anomaly":
        if anomaly_authorization is None:
            raise InvalidTransitionError(
                "anomaly activation requires server-issued benchmark authorization"
            )
        try:
            require_activation_authorization(
                anomaly_authorization,
                model_id=model.id,
                model_version=model.version,
                model_artifact_sha256=model.artifact_sha256,
                deployment_id=selected.id,
            )
        except CareAnomalyError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        package_sha256 = model.metrics.get("model_package_sha256")
        if "care_online_runtime" in selected.evaluation_gate and (
            not isinstance(package_sha256, str) or len(package_sha256) != 64
        ):
            raise InvalidTransitionError(
                "CARE online activation requires a verified model-package document hash"
            )
        selected.evaluation_gate = {
            **selected.evaluation_gate,
            "server_authorization": {
                "evaluation_run_id": anomaly_authorization.evaluation_run_id,
                "metric_snapshot_sha256": anomaly_authorization.metric_snapshot_sha256,
                "gate_policy_version": anomaly_authorization.gate_policy_version,
                "authorized_at": anomaly_authorization.authorized_at.isoformat(),
            },
            **(
                {"authorized_model_package_sha256": package_sha256}
                if isinstance(package_sha256, str)
                else {}
            ),
        }
    peers = list(
        (
            await session.scalars(
                select(ModelDeployment)
                .join(RegisteredModel, RegisteredModel.id == ModelDeployment.model_id)
                .where(
                    ModelDeployment.stage == selected.stage,
                    ModelDeployment.status == "active",
                    ModelDeployment.id != selected.id,
                    RegisteredModel.kind == model.kind,
                )
                .order_by(desc(ModelDeployment.activated_at))
                .with_for_update()
            )
        ).all()
    )
    now = datetime.now(UTC)
    remaining = 100 - traffic_percent
    for index, peer in enumerate(peers):
        if index == 0 and remaining:
            peer.traffic_percent = remaining
        else:
            peer.status = "inactive"
            peer.traffic_percent = 0
            peer.retired_at = now
    if remaining and not peers:
        raise InvalidTransitionError(
            "a partial rollout requires an existing active deployment for fallback traffic"
        )
    selected.status = "active"
    selected.traffic_percent = traffic_percent
    selected.activated_at = now
    selected.retired_at = None
    selected.rollback_from_id = rollback_from_id
    model.status = "active"
    model.updated_at = now
    append_domain_event(
        session,
        event_type=(
            "model.deployment.rolled-back" if rollback_from_id else "model.deployment.activated"
        ),
        aggregate_type="model_deployment",
        aggregate_id=selected.id,
        payload={
            "deployment_id": selected.id,
            "model_id": selected.model_id,
            "traffic_percent": traffic_percent,
            "reason": reason,
            "subject": subject,
            "rollback_from_id": rollback_from_id,
        },
    )
    await session.flush()
    return selected


async def select_active_deployment(
    session: AsyncSession, turbine_id: str, *, model_kind: str = "predictive"
) -> tuple[ModelDeployment, RegisteredModel]:
    deployments = list(
        (
            await session.scalars(
                select(ModelDeployment)
                .join(RegisteredModel, RegisteredModel.id == ModelDeployment.model_id)
                .where(ModelDeployment.stage == "production", ModelDeployment.status == "active")
                .where(RegisteredModel.kind == model_kind)
                .order_by(ModelDeployment.id)
            )
        ).all()
    )
    if not deployments or sum(item.traffic_percent for item in deployments) != 100:
        raise InvalidTransitionError(
            f"production {model_kind} model routing does not have exactly 100% coverage"
        )
    slot = int(hashlib.sha256(turbine_id.encode()).hexdigest()[:8], 16) % 100
    boundary = 0
    selected = deployments[-1]
    for deployment in deployments:
        boundary += deployment.traffic_percent
        if slot < boundary:
            selected = deployment
            break
    model = await session.get(RegisteredModel, selected.model_id)
    if model is None:  # pragma: no cover - protected by foreign key
        raise NotFoundError(f"model {selected.model_id} was not found")
    return selected, model


async def _feature_snapshot(
    session: AsyncSession, turbine_id: str, input_schema: Mapping[str, Any]
) -> tuple[dict[str, Any], datetime]:
    turbine = await session.get(Turbine, turbine_id)
    if turbine is None:
        raise NotFoundError(f"turbine {turbine_id} was not found")
    # Select one row per signal in SQL. Loading a fixed 10,000-row window and
    # deduplicating in Python both wastes memory and can omit a variable whose
    # newest sample falls just outside that arbitrary window.
    latest_samples = (
        select(
            ScadaSample.id.label("sample_id"),
            func.row_number()
            .over(
                partition_by=ScadaSample.variable,
                order_by=(desc(ScadaSample.observed_at), desc(ScadaSample.id)),
            )
            .label("row_number"),
        )
        .where(ScadaSample.turbine_id == turbine_id, ScadaSample.quality == "good")
        .subquery()
    )
    latest_rows = (
        await session.scalars(
            select(ScadaSample)
            .join(latest_samples, latest_samples.c.sample_id == ScadaSample.id)
            .where(latest_samples.c.row_number == 1)
        )
    ).all()
    latest = {row.variable: row for row in latest_rows}
    if not latest:
        raise InvalidTransitionError(f"turbine {turbine_id} has no good-quality SCADA features")
    observed_at = max(row.observed_at for row in latest.values())
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    alarm_count = int(
        await session.scalar(
            select(func.count(Alarm.id)).where(
                Alarm.turbine_id == turbine_id,
                Alarm.status != "resolved",
            )
        )
        or 0
    )
    candidates: dict[str, Any] = {
        "turbine_id": turbine.id,
        "turbine_model": turbine.model,
        "health_score": turbine.health_score,
        "active_alarm_count": alarm_count,
        "observed_at": observed_at.isoformat(),
        "signals": {key: row.value for key, row in sorted(latest.items())},
    }
    allowed = set(dict(input_schema.get("properties", {})))
    snapshot = {key: value for key, value in candidates.items() if key in allowed}
    _validate_instance(input_schema, snapshot, "model input")
    return snapshot, observed_at


def _validate_predictive_output(output: dict[str, Any]) -> None:
    probability = output.get("failure_probability_30d")
    rul = output.get("remaining_useful_life_days")
    anomaly = output.get("anomaly_score")
    if not isinstance(probability, int | float) or not 0 <= probability <= 100:
        raise InvalidTransitionError("model probability must be between 0 and 100")
    if not isinstance(rul, int | float) or rul < 0:
        raise InvalidTransitionError("model remaining useful life must be non-negative")
    if not isinstance(anomaly, int | float) or not 0 <= anomaly <= 1:
        raise InvalidTransitionError("model anomaly score must be between 0 and 1")


def _prediction_lock_id(deployment_id: str, turbine_id: str, observed_at: datetime) -> int:
    digest = hashlib.sha256(
        f"{deployment_id}:{turbine_id}:{observed_at.isoformat()}".encode()
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


@asynccontextmanager
async def _claim_prediction_key(
    session: AsyncSession,
    deployment_id: str,
    turbine_id: str,
    observed_at: datetime,
) -> AsyncIterator[None]:
    lock_id = _prediction_lock_id(deployment_id, turbine_id, observed_at)
    dialect = session.bind.dialect.name if session.bind is not None else "unknown"
    if dialect == "postgresql":
        # Transaction-scoped advisory locks cover the external inference call
        # and work across API replicas without holding a row that does not yet
        # exist. The caller commits only after the result has been persisted.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
        yield
        return

    # SQLite is the deterministic test double. Keep the same single-flight
    # contract for concurrent tests without pretending it is a multi-process
    # production lock.
    key = f"{deployment_id}:{turbine_id}:{observed_at.isoformat()}"
    lock = _prediction_locks.setdefault(key, asyncio.Lock())
    async with lock:
        yield


async def run_predictive_inference(
    session: AsyncSession,
    settings: Settings,
    inference_client: ModelInferenceClient,
    *,
    turbine_id: str,
    subject: str,
) -> ModelPrediction:
    deployment, model = await select_active_deployment(session, turbine_id)
    snapshot, observed_at = await _feature_snapshot(session, turbine_id, model.input_schema)
    canonical = _canonical_json(snapshot)
    input_digest = hashlib.sha256(canonical.encode()).hexdigest()
    async with _claim_prediction_key(session, deployment.id, turbine_id, observed_at):
        existing = await session.scalar(
            select(ModelPrediction).where(
                ModelPrediction.deployment_id == deployment.id,
                ModelPrediction.turbine_id == turbine_id,
                ModelPrediction.feature_observed_at == observed_at,
            )
        )
        if existing is not None and existing.status == "succeeded":
            return existing
        prediction = existing or ModelPrediction(
            id=str(uuid4()),
            model_id=model.id,
            deployment_id=deployment.id,
            turbine_id=turbine_id,
            feature_observed_at=observed_at,
            prediction_kind="predictive",
            input_digest=input_digest,
            input_snapshot=snapshot,
            output={},
            status="running",
            requested_by=subject,
        )
        if existing is None:
            session.add(prediction)
        else:
            prediction.model_id = model.id
            prediction.prediction_kind = "predictive"
            prediction.input_digest = input_digest
            prediction.input_snapshot = snapshot
            prediction.output = {}
            prediction.status = "running"
            prediction.error_code = None
            prediction.requested_by = subject
        await session.flush()
        target = settings.model_inference_targets.get(deployment.target_id)
        if target is None:
            raise InvalidTransitionError("the active model inference target is not configured")
        try:
            output, latency_ms = await inference_client.predict(
                target,
                {"model": {"id": model.id, "version": model.version}, "inputs": snapshot},
                idempotency_key=f"windops:{deployment.id}:{turbine_id}:{input_digest}",
            )
            _validate_instance(model.output_schema, output, "model output")
            _validate_predictive_output(output)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            prediction.status = "failed"
            prediction.error_code = type(exc).__name__[:96]
            prediction.output = {}
            prediction.latency_ms = 0
            append_domain_event(
                session,
                event_type="model.prediction.failed",
                aggregate_type="model_prediction",
                aggregate_id=prediction.id,
                payload={
                    "prediction_id": prediction.id,
                    "model_id": model.id,
                    "deployment_id": deployment.id,
                    "turbine_id": turbine_id,
                    "error_code": prediction.error_code,
                },
            )
            await session.flush()
            return prediction
        prediction.status = "succeeded"
        prediction.error_code = None
        prediction.output = output
        prediction.latency_ms = latency_ms
        append_domain_event(
            session,
            event_type="model.prediction.succeeded",
            aggregate_type="model_prediction",
            aggregate_id=prediction.id,
            payload={
                "prediction_id": prediction.id,
                "model_id": model.id,
                "deployment_id": deployment.id,
                "turbine_id": turbine_id,
                "feature_observed_at": observed_at.isoformat(),
                "latency_ms": latency_ms,
            },
        )
        await session.flush()
        return prediction


async def run_anomaly_inference(
    session: AsyncSession,
    settings: Settings,
    inference_client: ModelInferenceClient,
    *,
    deployment_id: str,
    feature_samples: Sequence[Mapping[str, Any]],
    feature_set_version: str,
    quality_rule_version: str,
    threshold_policy: ThresholdPolicy,
    evidence_artifact: ArtifactReference,
    subject: str,
    benchmark_evaluation_run_id: str | None = None,
) -> ModelPrediction:
    """Run one governed anomaly window without fabricating predictive/RUL values."""

    deployment = await session.get(ModelDeployment, deployment_id)
    if deployment is None:
        raise NotFoundError(f"model deployment {deployment_id} was not found")
    if deployment.status != "active":
        raise InvalidTransitionError("anomaly inference requires an active deployment")
    model = await session.get(RegisteredModel, deployment.model_id)
    if model is None:  # pragma: no cover - protected by foreign key
        raise NotFoundError(f"model {deployment.model_id} was not found")
    if model.kind != "anomaly":
        raise InvalidTransitionError("anomaly inference requires a registered anomaly model")
    try:
        window = AnomalyFeatureWindow.from_replay_samples(
            feature_samples,
            feature_set_version=feature_set_version,
            quality_rule_version=quality_rule_version,
        )
    except CareAnomalyError as exc:
        raise InvalidTransitionError(str(exc)) from exc
    snapshot = window.to_model_input()
    _validate_instance(model.input_schema, snapshot, "anomaly model input")
    input_digest = hashlib.sha256(_canonical_json(snapshot).encode()).hexdigest()
    turbine_id = window.identity.online_turbine_id
    observed_at = window.feature_window_end
    threshold_policy_sha256 = str(threshold_policy.to_dict()["threshold_policy_sha256"])
    persisted_replay = await session.get(
        BenchmarkReplayRun, window.identity.benchmark_replay_run_id
    )
    persisted_dataset: BenchmarkDatasetVersion | None = None
    if persisted_replay is not None:
        persisted_dataset = await session.get(
            BenchmarkDatasetVersion, persisted_replay.dataset_version_id
        )
        if persisted_dataset is None:  # pragma: no cover - protected by the foreign key
            raise NotFoundError("benchmark replay dataset version was not found")
        if (
            persisted_dataset.dataset_id != DATASET_ID
            or persisted_dataset.version != window.identity.dataset_version
            or persisted_replay.farm != window.identity.farm
            or persisted_replay.source_event_number != window.identity.event_id
            or persisted_replay.online_turbine_id != turbine_id
        ):
            raise InvalidTransitionError("persisted benchmark replay does not match feature window")
    evaluation_run: BenchmarkEvaluationRun | None = None
    if benchmark_evaluation_run_id is not None:
        evaluation_run = await session.get(BenchmarkEvaluationRun, benchmark_evaluation_run_id)
        if evaluation_run is None:
            raise NotFoundError(
                f"benchmark evaluation run {benchmark_evaluation_run_id} was not found"
            )
        evaluation_dataset = await session.get(
            BenchmarkDatasetVersion, evaluation_run.dataset_version_id
        )
        if evaluation_dataset is None:  # pragma: no cover - protected by the foreign key
            raise NotFoundError("benchmark evaluation dataset version was not found")
        if (
            evaluation_run.model_id != model.id
            or evaluation_run.model_version != model.version
            or evaluation_dataset.dataset_id != DATASET_ID
            or evaluation_dataset.version != window.identity.dataset_version
            or (
                persisted_replay is not None
                and evaluation_run.dataset_version_id != persisted_replay.dataset_version_id
            )
        ):
            raise InvalidTransitionError(
                "benchmark evaluation provenance does not match anomaly model/window"
            )
    async with _claim_prediction_key(session, deployment.id, turbine_id, observed_at):
        existing = await session.scalar(
            select(ModelPrediction).where(
                ModelPrediction.deployment_id == deployment.id,
                ModelPrediction.turbine_id == turbine_id,
                ModelPrediction.feature_observed_at == observed_at,
            )
        )
        if existing is not None and existing.input_digest != input_digest:
            raise ConflictError(
                "anomaly prediction key already exists for a different governed feature window"
            )
        if existing is not None and existing.status == "succeeded":
            if (
                benchmark_evaluation_run_id is not None
                and existing.benchmark_evaluation_run_id != benchmark_evaluation_run_id
            ):
                raise ConflictError(
                    "anomaly prediction already exists with different evaluation provenance"
                )
            return existing
        prediction = existing or ModelPrediction(
            id=str(uuid4()),
            model_id=model.id,
            deployment_id=deployment.id,
            turbine_id=turbine_id,
            feature_observed_at=observed_at,
            prediction_kind="anomaly",
            benchmark_replay_run_id=(persisted_replay.id if persisted_replay else None),
            benchmark_evaluation_run_id=(evaluation_run.id if evaluation_run else None),
            feature_window_start=window.feature_window_start,
            feature_window_end=window.feature_window_end,
            feature_start_sequence=window.feature_start_sequence,
            feature_end_sequence=window.feature_end_sequence,
            threshold_policy_version=threshold_policy.version,
            threshold_policy_sha256=threshold_policy_sha256,
            feature_set_version=feature_set_version,
            quality_rule_version=quality_rule_version,
            evidence_artifact_uri=evidence_artifact.uri,
            evidence_artifact_sha256=evidence_artifact.sha256,
            input_digest=input_digest,
            input_snapshot=snapshot,
            output={},
            status="running",
            requested_by=subject,
        )
        if existing is None:
            session.add(prediction)
        else:
            prediction.prediction_kind = "anomaly"
            prediction.benchmark_replay_run_id = persisted_replay.id if persisted_replay else None
            prediction.benchmark_evaluation_run_id = evaluation_run.id if evaluation_run else None
            prediction.feature_window_start = window.feature_window_start
            prediction.feature_window_end = window.feature_window_end
            prediction.feature_start_sequence = window.feature_start_sequence
            prediction.feature_end_sequence = window.feature_end_sequence
            prediction.threshold_policy_version = threshold_policy.version
            prediction.threshold_policy_sha256 = threshold_policy_sha256
            prediction.feature_set_version = feature_set_version
            prediction.quality_rule_version = quality_rule_version
            prediction.evidence_artifact_uri = evidence_artifact.uri
            prediction.evidence_artifact_sha256 = evidence_artifact.sha256
            prediction.anomaly_score = None
            prediction.binary_prediction = None
            prediction.component = None
            prediction.output = {}
            prediction.status = "running"
            prediction.error_code = None
            prediction.requested_by = subject
        await session.flush()
        target = settings.model_inference_targets.get(deployment.target_id)
        if target is None:
            raise InvalidTransitionError("the anomaly inference target is not configured")
        try:
            raw_output, latency_ms = await inference_client.predict(
                target,
                {"model": {"id": model.id, "version": model.version}, "inputs": snapshot},
                idempotency_key=(f"windops:anomaly:{deployment.id}:{turbine_id}:{input_digest}"),
            )
            output = build_governed_anomaly_output(
                raw_output,
                window,
                AnomalyRuntimeContext(
                    model_id=model.id,
                    model_version=model.version,
                    deployment_id=deployment.id,
                    deployment_version=deployment.id,
                    threshold_policy=threshold_policy,
                    evidence_artifact=evidence_artifact,
                ),
            )
            _validate_instance(model.output_schema, output, "anomaly model output")
            verify_governed_anomaly_output(output)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            prediction.status = "failed"
            prediction.error_code = type(exc).__name__[:96]
            prediction.output = {}
            prediction.latency_ms = 0
            append_domain_event(
                session,
                event_type="model.anomaly-prediction.failed",
                aggregate_type="model_prediction",
                aggregate_id=prediction.id,
                payload={
                    "prediction_id": prediction.id,
                    "model_id": model.id,
                    "deployment_id": deployment.id,
                    "turbine_id": turbine_id,
                    "benchmark_replay_run_id": window.identity.benchmark_replay_run_id,
                    "error_code": prediction.error_code,
                },
            )
            await session.flush()
            return prediction
        prediction.status = "succeeded"
        prediction.error_code = None
        prediction.output = output
        prediction.anomaly_score = float(output["anomaly_score"])
        prediction.binary_prediction = bool(output["binary_prediction"])
        prediction.component = str(output["component"])
        prediction.latency_ms = latency_ms
        append_domain_event(
            session,
            event_type="model.anomaly-prediction.succeeded",
            aggregate_type="model_prediction",
            aggregate_id=prediction.id,
            payload={
                "prediction_id": prediction.id,
                "model_id": model.id,
                "deployment_id": deployment.id,
                "turbine_id": turbine_id,
                "benchmark_replay_run_id": window.identity.benchmark_replay_run_id,
                "feature_start_sequence": window.feature_start_sequence,
                "feature_end_sequence": window.feature_end_sequence,
                "latency_ms": latency_ms,
            },
        )
        await session.flush()
        return prediction


def serialize_model(model: RegisteredModel, deployments: list[ModelDeployment]) -> dict[str, Any]:
    return {
        "model_id": model.id,
        "name": model.name,
        "version": model.version,
        "kind": model.kind,
        "status": model.status,
        "description": model.description,
        "artifact_uri": model.artifact_uri,
        "artifact_sha256": model.artifact_sha256,
        "content_type": model.content_type,
        "content_size_bytes": model.content_size_bytes,
        "input_schema": model.input_schema,
        "output_schema": model.output_schema,
        "metrics": model.metrics,
        "created_by": model.created_by,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
        "deployments": [serialize_deployment(item) for item in deployments],
    }


def serialize_deployment(deployment: ModelDeployment) -> dict[str, Any]:
    return {
        "deployment_id": deployment.id,
        "model_id": deployment.model_id,
        "target_id": deployment.target_id,
        "stage": deployment.stage,
        "status": deployment.status,
        "traffic_percent": deployment.traffic_percent,
        "evaluation_gate": deployment.evaluation_gate,
        "rollback_from_id": deployment.rollback_from_id,
        "deployed_by": deployment.deployed_by,
        "deployed_at": deployment.deployed_at,
        "activated_at": deployment.activated_at,
        "retired_at": deployment.retired_at,
    }


def serialize_prediction(prediction: ModelPrediction) -> dict[str, Any]:
    return {
        "prediction_id": prediction.id,
        "model_id": prediction.model_id,
        "deployment_id": prediction.deployment_id,
        "turbine_id": prediction.turbine_id,
        "feature_observed_at": prediction.feature_observed_at,
        "input_digest": prediction.input_digest,
        "output": prediction.output,
        "status": prediction.status,
        "error_code": prediction.error_code,
        "latency_ms": prediction.latency_ms,
        "requested_by": prediction.requested_by,
        "created_at": prediction.created_at,
    }
