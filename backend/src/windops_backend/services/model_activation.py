from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.benchmarks.care.anomaly import (
    ActivationGateEvidence,
    ActivationGatePolicy,
    AnomalyActivationAuthorization,
    CareAnomalyError,
    evaluate_activation_gate,
    require_activation_authorization,
)
from windops_backend.benchmarks.care.anomaly import (
    BenchmarkMetricSnapshot as ActivationMetricSnapshot,
)
from windops_backend.benchmarks.care.online_contract import (
    CareOnlineReplayError,
    verify_online_runtime_configuration,
)
from windops_backend.benchmarks.care.trust import (
    verify_embedded_care_approval,
)
from windops_backend.config import Settings
from windops_backend.errors import (
    AnomalyActivationArtifactDriftError,
    AnomalyActivationBindingError,
    AnomalyActivationConcurrencyError,
    AnomalyActivationEvaluationError,
    InvalidTransitionError,
    NotFoundError,
)
from windops_backend.models import (
    BenchmarkEvaluationRun,
    BenchmarkMetricSnapshot,
    DomainEvent,
    ModelDeployment,
    RegisteredModel,
)
from windops_backend.services.events import append_domain_event
from windops_backend.services.model_runtime_contracts import (
    CARE_ACTIVATION_ARTIFACT_CONTENT_TYPES,
    CARE_ACTIVATION_GATE_POLICY_VERSION,
    MAX_CARE_ACTIVATION_ARTIFACT_BYTES,
    _canonical_json,
)
from windops_backend.storage import ArtifactVerifier


def _metric_passed(metric: BenchmarkMetricSnapshot) -> bool:
    threshold = metric.threshold_value
    direction = metric.threshold_direction
    if threshold is None or direction is None:
        return False
    if direction == "gte":
        calculated = metric.value >= threshold
    elif direction == "lte":
        calculated = metric.value <= threshold
    elif direction == "eq":
        calculated = metric.value == threshold
    else:
        return False
    return metric.passed is True and calculated


def _required_metric(
    metrics: Mapping[str, BenchmarkMetricSnapshot], name: str
) -> BenchmarkMetricSnapshot:
    metric = metrics.get(name)
    if metric is None:
        raise AnomalyActivationEvaluationError(f"authoritative evaluation metric {name} is missing")
    return metric


def _integer_metric(metrics: Mapping[str, BenchmarkMetricSnapshot], name: str) -> int:
    value = _required_metric(metrics, name).value
    if not float(value).is_integer() or value < 0:
        raise AnomalyActivationEvaluationError(
            f"authoritative evaluation metric {name} must be a non-negative integer"
        )
    return int(value)


def _evaluation_document(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    if raw.get("schema_version") == "care-v6-within-farm-fold-v1":
        supplied = raw.get("document_sha256")
        unsigned = {key: value for key, value in raw.items() if key != "document_sha256"}
        expected = hashlib.sha256(_canonical_json(unsigned).encode()).hexdigest()
        nested = raw.get("evaluation")
        if supplied != expected or not isinstance(nested, Mapping):
            raise AnomalyActivationEvaluationError(
                "authoritative CARE fold artifact identity is invalid"
            )
        return nested
    return raw


def _artifact_approval_lineage(
    raw: Mapping[str, Any], evaluation_artifact: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    for candidate in (
        raw.get("care_approval"),
        evaluation_artifact.get("care_approval"),
        (
            evaluation_artifact.get("provenance", {}).get("care_approval")
            if isinstance(evaluation_artifact.get("provenance"), Mapping)
            else None
        ),
    ):
        if isinstance(candidate, Mapping):
            return candidate
    return None


async def _load_authoritative_activation_evidence(
    session: AsyncSession,
    settings: Settings,
    artifact_verifier: ArtifactVerifier,
    *,
    selected: ModelDeployment,
    model: RegisteredModel,
    operation: str,
    reason: str,
    subject: str,
) -> tuple[AnomalyActivationAuthorization, DomainEvent, DomainEvent, str]:
    runtime = selected.evaluation_gate.get("care_online_runtime")
    if not isinstance(runtime, Mapping):
        raise AnomalyActivationBindingError(
            "anomaly deployment has no immutable CARE online runtime binding"
        )
    try:
        verify_online_runtime_configuration(
            runtime,
            model_id=model.id,
            model_version=model.version,
        )
    except CareOnlineReplayError as exc:
        raise AnomalyActivationBindingError(str(exc)) from exc

    evaluation_run_id = runtime.get("evaluation_run_id")
    if not isinstance(evaluation_run_id, str) or not evaluation_run_id:
        raise AnomalyActivationBindingError(
            "CARE runtime has no authoritative evaluation run binding"
        )
    evaluation = await session.scalar(
        select(BenchmarkEvaluationRun)
        .where(BenchmarkEvaluationRun.id == evaluation_run_id)
        .with_for_update()
    )
    if evaluation is None:
        raise AnomalyActivationBindingError("the CARE runtime evaluation run does not exist")
    if evaluation.model_id != model.id or evaluation.model_version != model.version:
        raise AnomalyActivationBindingError(
            "evaluation model identity does not match the deployment model"
        )
    if evaluation.status != "completed" or evaluation.invalidated_at is not None:
        raise AnomalyActivationEvaluationError(
            "evaluation run must be completed and not invalidated"
        )
    if evaluation.artifact_uri is None or evaluation.artifact_sha256 is None:
        raise AnomalyActivationEvaluationError(
            "completed evaluation has no immutable artifact identity"
        )
    if (
        runtime.get("feature_set_version") != evaluation.feature_set_version
        or runtime.get("quality_rule_version") != evaluation.quality_rule_version
        or runtime.get("offline_threshold_policy_sha256") != evaluation.threshold_policy_sha256
    ):
        raise AnomalyActivationBindingError(
            "CARE runtime versions do not match the authoritative evaluation"
        )

    package_document_sha256 = model.metrics.get("model_package_sha256")
    runtime_evidence = runtime.get("evidence_artifact")
    package_reference = evaluation.extension_data.get("model_package")
    if (
        not isinstance(package_document_sha256, str)
        or len(package_document_sha256) != 64
        or runtime.get("model_package_sha256") != package_document_sha256
        or not isinstance(runtime_evidence, Mapping)
        or runtime_evidence.get("uri") != model.artifact_uri
        or runtime_evidence.get("sha256") != package_document_sha256
        or not isinstance(package_reference, Mapping)
        or package_reference.get("artifact_uri") != model.artifact_uri
        or package_reference.get("file_sha256") != model.artifact_sha256
        or package_reference.get("document_sha256") != package_document_sha256
    ):
        raise AnomalyActivationBindingError(
            "model package, runtime, and evaluation bindings do not match"
        )

    try:
        body, _ = await artifact_verifier.read_verified_object(
            evaluation.artifact_uri,
            evaluation.artifact_sha256,
            bucket=settings.minio_care_bucket,
            prefix=settings.minio_care_reports_prefix,
            allowed_content_types=CARE_ACTIVATION_ARTIFACT_CONTENT_TYPES,
            max_bytes=MAX_CARE_ACTIVATION_ARTIFACT_BYTES,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise AnomalyActivationArtifactDriftError(
            "authoritative CARE evaluation artifact is absent or its SHA-256 drifted"
        ) from exc
    try:
        raw_artifact = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnomalyActivationEvaluationError(
            "authoritative CARE evaluation artifact is not valid JSON"
        ) from exc
    if not isinstance(raw_artifact, Mapping):
        raise AnomalyActivationEvaluationError(
            "authoritative CARE evaluation artifact must be a JSON object"
        )
    evaluation_artifact = _evaluation_document(raw_artifact)

    database_lineage = evaluation.extension_data.get("care_approval")
    model_lineage = model.metrics.get("care_approval")
    artifact_lineage = _artifact_approval_lineage(raw_artifact, evaluation_artifact)
    if (
        not isinstance(database_lineage, Mapping)
        or not isinstance(model_lineage, Mapping)
        or not isinstance(artifact_lineage, Mapping)
        or dict(database_lineage) != dict(model_lineage)
        or dict(database_lineage) != dict(artifact_lineage)
    ):
        raise AnomalyActivationBindingError(
            "CARE approved-root lineage is not identical across model and evaluation evidence"
        )
    try:
        verify_embedded_care_approval(database_lineage)
    except ValueError as exc:
        raise AnomalyActivationBindingError(str(exc)) from exc

    metric_rows = list(
        (
            await session.scalars(
                select(BenchmarkMetricSnapshot)
                .where(BenchmarkMetricSnapshot.evaluation_run_id == evaluation.id)
                .order_by(BenchmarkMetricSnapshot.metric_name, BenchmarkMetricSnapshot.id)
                .with_for_update()
            )
        ).all()
    )
    metrics: dict[str, BenchmarkMetricSnapshot] = {}
    for metric in metric_rows:
        if metric.metric_name in metrics:
            raise AnomalyActivationEvaluationError(
                f"authoritative evaluation metric {metric.metric_name} is ambiguous"
            )
        metrics[metric.metric_name] = metric
        bound_hash = metric.details.get("evaluation_artifact_sha256") or metric.details.get(
            "fold_artifact_sha256"
        )
        if bound_hash != evaluation.artifact_sha256:
            raise AnomalyActivationBindingError(
                f"metric {metric.metric_name} is not bound to the evaluation artifact"
            )
        if metric.is_release_metric and not _metric_passed(metric):
            raise AnomalyActivationEvaluationError(
                f"release metric {metric.metric_name} did not pass its authoritative threshold"
            )

    care_score = _required_metric(metrics, "care_score")
    event_detection = _required_metric(metrics, "event_detection_rate")
    normal_false_positive = _required_metric(metrics, "normal_event_false_positive_rate")
    data_failures = _integer_metric(metrics, "data_failure_event_count")
    model_failures = _integer_metric(metrics, "model_failure_event_count")
    unscorable = _integer_metric(metrics, "unscorable_event_count")
    if evaluation.failed_event_count != data_failures + model_failures:
        raise AnomalyActivationEvaluationError(
            "evaluation failure totals do not match authoritative metric snapshots"
        )
    try:
        database_snapshot = ActivationMetricSnapshot(
            care_score=float(care_score.value),
            event_detection_rate=float(event_detection.value),
            normal_event_false_positive_rate=float(normal_false_positive.value),
            requested_event_count=evaluation.requested_event_count,
            scored_event_count=evaluation.scored_event_count,
            unscorable_event_count=unscorable,
            data_failure_event_count=data_failures,
            model_failure_event_count=model_failures,
        )
    except CareAnomalyError as exc:
        raise AnomalyActivationEvaluationError(str(exc)) from exc
    if evaluation.farm is None:
        raise AnomalyActivationEvaluationError(
            "activation evaluation must identify its governed farm"
        )
    care_score_threshold = care_score.threshold_value
    event_detection_threshold = event_detection.threshold_value
    normal_false_positive_threshold = normal_false_positive.threshold_value
    if (
        care_score_threshold is None
        or event_detection_threshold is None
        or normal_false_positive_threshold is None
    ):
        raise AnomalyActivationEvaluationError(
            "activation metrics must define authoritative release thresholds"
        )
    expected_metric_directions = (
        (care_score, "gte"),
        (event_detection, "gte"),
        (normal_false_positive, "lte"),
    )
    if any(
        not metric.is_release_metric or metric.threshold_direction != expected_direction
        for metric, expected_direction in expected_metric_directions
    ):
        raise AnomalyActivationEvaluationError(
            "activation metrics do not use the governed release directions"
        )
    predictions = evaluation_artifact.get("predictions")
    first_prediction = predictions[0] if isinstance(predictions, list) and predictions else None
    if not isinstance(first_prediction, Mapping):
        raise AnomalyActivationEvaluationError(
            "activation evaluation has no governed prediction evidence"
        )
    try:
        policy = ActivationGatePolicy(
            policy_version=CARE_ACTIVATION_GATE_POLICY_VERSION,
            minimum_care_score=float(care_score_threshold),
            minimum_event_detection_rate=float(event_detection_threshold),
            maximum_normal_event_false_positive_rate=float(normal_false_positive_threshold),
            required_farms=(evaluation.farm,),
            required_generalization_protocols=(evaluation.protocol_version,),
            required_feature_set_version=evaluation.feature_set_version,
            required_feature_set_sha256=str(first_prediction.get("feature_set_sha256", "")),
            required_quality_rule_version=evaluation.quality_rule_version,
            required_quality_contract_sha256=str(
                first_prediction.get("quality_contract_sha256", "")
            ),
            required_threshold_policy_version=evaluation.threshold_policy_version,
            required_threshold_policy_sha256=evaluation.threshold_policy_sha256,
        )
    except CareAnomalyError as exc:
        raise AnomalyActivationEvaluationError(str(exc)) from exc
    approval_event = append_domain_event(
        session,
        event_type="model.activation.approved",
        aggregate_type="model_deployment",
        aggregate_id=selected.id,
        payload={
            "operation": operation,
            "deployment_id": selected.id,
            "model_id": model.id,
            "model_version": model.version,
            "model_artifact_sha256": model.artifact_sha256,
            "evaluation_run_id": evaluation.id,
            "evaluation_artifact_sha256": evaluation.artifact_sha256,
            "care_approved_root_sha256": database_lineage["approved_root_sha256"],
            "approved_by": subject,
            "reason": reason,
        },
    )
    audit_event = append_domain_event(
        session,
        event_type="model.activation.evidence-audited",
        aggregate_type="benchmark_evaluation_run",
        aggregate_id=evaluation.id,
        payload={
            "operation": operation,
            "deployment_id": selected.id,
            "model_artifact_sha256": model.artifact_sha256,
            "evaluation_artifact_sha256": evaluation.artifact_sha256,
            "metric_snapshot_sha256": database_snapshot.snapshot_sha256,
            "care_approved_root_sha256": database_lineage["approved_root_sha256"],
            "audited_by": subject,
        },
    )
    await session.flush()
    try:
        authorization = evaluate_activation_gate(
            policy,
            ActivationGateEvidence(
                evaluation_run_id=evaluation.id,
                evaluation_status=evaluation.status,
                invalidated=evaluation.invalidated_at is not None,
                evaluation_artifact=evaluation_artifact,
                metric_snapshot=database_snapshot,
                model_id=model.id,
                model_version=model.version,
                model_artifact_sha256=model.artifact_sha256,
                deployment_id=selected.id,
                deployment_version=selected.id,
                approval_ids=(approval_event.id,),
                audit_event_ids=(audit_event.id,),
            ),
            authorized_at=datetime.now(UTC),
        )
    except (CareAnomalyError, KeyError, TypeError, ValueError) as exc:
        raise AnomalyActivationEvaluationError(str(exc)) from exc
    return authorization, approval_event, audit_event, str(database_lineage["approved_root_sha256"])


async def govern_and_activate_deployment(
    session: AsyncSession,
    settings: Settings,
    artifact_verifier: ArtifactVerifier,
    *,
    deployment_id: str,
    traffic_percent: int,
    reason: str,
    subject: str,
    rollback: bool = False,
) -> ModelDeployment:
    selected = await session.scalar(
        select(ModelDeployment).where(ModelDeployment.id == deployment_id).with_for_update()
    )
    if selected is None:
        raise NotFoundError(f"model deployment {deployment_id} was not found")
    model = await session.scalar(
        select(RegisteredModel).where(RegisteredModel.id == selected.model_id).with_for_update()
    )
    if model is None:  # pragma: no cover - protected by foreign key
        raise NotFoundError(f"model {selected.model_id} was not found")

    rollback_from_id: str | None = None
    if rollback:
        current = await session.scalar(
            select(ModelDeployment)
            .join(RegisteredModel, RegisteredModel.id == ModelDeployment.model_id)
            .where(
                ModelDeployment.stage == selected.stage,
                ModelDeployment.status == "active",
                ModelDeployment.id != selected.id,
                RegisteredModel.kind == model.kind,
            )
            .order_by(desc(ModelDeployment.activated_at), ModelDeployment.id)
            .with_for_update()
        )
        if current is None:
            raise InvalidTransitionError(
                "rollback requires a different active deployment in the same stage"
            )
        rollback_from_id = current.id

    if model.kind != "anomaly":
        return await activate_deployment(
            session,
            deployment_id=selected.id,
            traffic_percent=traffic_percent,
            reason=reason,
            subject=subject,
            rollback_from_id=rollback_from_id,
        )
    if selected.status not in ({"inactive"} if rollback else {"staged", "inactive"}):
        raise AnomalyActivationConcurrencyError(
            "anomaly deployment routing changed before this activation could commit"
        )

    (
        authorization,
        approval_event,
        audit_event,
        approved_root_sha256,
    ) = await _load_authoritative_activation_evidence(
        session,
        settings,
        artifact_verifier,
        selected=selected,
        model=model,
        operation="rollback" if rollback else "activate",
        reason=reason,
        subject=subject,
    )
    active = await activate_deployment(
        session,
        deployment_id=selected.id,
        traffic_percent=traffic_percent,
        reason=reason,
        subject=subject,
        rollback_from_id=rollback_from_id,
        anomaly_authorization=authorization,
    )
    active.evaluation_gate = {
        **active.evaluation_gate,
        "server_authorization": {
            **active.evaluation_gate["server_authorization"],
            "approval_event_id": approval_event.id,
            "evidence_audit_event_id": audit_event.id,
            "care_approved_root_sha256": approved_root_sha256,
            "consumed_in_transaction": True,
        },
    }
    append_domain_event(
        session,
        event_type="model.activation.authorization-consumed",
        aggregate_type="model_deployment",
        aggregate_id=active.id,
        payload={
            "operation": "rollback" if rollback else "activate",
            "approval_event_id": approval_event.id,
            "evidence_audit_event_id": audit_event.id,
            "evaluation_run_id": authorization.evaluation_run_id,
            "metric_snapshot_sha256": authorization.metric_snapshot_sha256,
            "care_approved_root_sha256": approved_root_sha256,
            "subject": subject,
        },
    )
    await session.flush()
    return active


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
