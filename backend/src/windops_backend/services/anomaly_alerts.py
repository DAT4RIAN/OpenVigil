from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.benchmarks.care.anomaly import (
    AlertPolicyInput,
    AnomalyAlertPolicy,
    AnomalyAlertState,
    ArtifactReference,
    apply_alert_policy,
    verify_governed_anomaly_output,
)
from windops_backend.benchmarks.care.online_contract import verify_online_runtime_configuration
from windops_backend.benchmarks.care.replay import CARE_REPLAY_SOURCE_ID
from windops_backend.benchmarks.care.scoring import ThresholdPolicy
from windops_backend.config import Settings
from windops_backend.enums import AlarmSeverity, AlarmStatus
from windops_backend.errors import InvalidTransitionError, NotFoundError
from windops_backend.models import (
    Alarm,
    AnomalyAlertPolicyState,
    BenchmarkReplayRun,
    Mission,
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
    ScadaSample,
)
from windops_backend.schemas import (
    AnomalyAlertPolicyStateRequest,
    MissionAnalysisProfile,
    MissionCreateRequest,
)
from windops_backend.services.benchmark_metadata import persist_anomaly_alert_policy_state
from windops_backend.services.events import append_domain_event
from windops_backend.services.missions import create_mission
from windops_backend.services.models import ModelInferenceClient, run_anomaly_inference


@dataclass(frozen=True, slots=True)
class AnomalyRuntimeConfiguration:
    threshold_policy: ThresholdPolicy
    evidence_artifact: ArtifactReference
    alert_policy: AnomalyAlertPolicy
    mission_profile: MissionAnalysisProfile
    evaluation_run_id: str
    feature_set_version: str
    quality_rule_version: str
    document_sha256: str


@dataclass(frozen=True, slots=True)
class AnomalyAlertOutcome:
    prediction_id: str
    action: Literal["none", "trigger", "recover", "duplicate", "disabled"]
    reason: str
    policy_state_id: str
    state_revision: int
    alarm_id: str | None
    mission_id: str | None
    replayed: bool

    def to_document(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "action": self.action,
            "reason": self.reason,
            "policy_state_id": self.policy_state_id,
            "state_revision": self.state_revision,
            "alarm_id": self.alarm_id,
            "mission_id": self.mission_id,
            "replayed": self.replayed,
        }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _runtime_configuration(
    deployment: ModelDeployment,
    model: RegisteredModel,
    *,
    turbine_id: str,
) -> AnomalyRuntimeConfiguration:
    raw = deployment.evaluation_gate.get("care_online_runtime")
    if not isinstance(raw, Mapping):
        raise InvalidTransitionError("anomaly deployment has no CARE online runtime configuration")
    try:
        verify_online_runtime_configuration(
            raw,
            model_id=model.id,
            model_version=model.version,
        )
        if raw.get("model_package_sha256") != deployment.evaluation_gate.get(
            "authorized_model_package_sha256"
        ):
            raise InvalidTransitionError(
                "CARE runtime package does not match the server-authorized deployment"
            )
        threshold_raw = raw["online_threshold_policy"]
        if not isinstance(threshold_raw, Mapping):
            raise InvalidTransitionError("CARE online threshold policy is malformed")
        threshold = ThresholdPolicy(
            value=float(threshold_raw["value"]),
            version=str(threshold_raw["version"]),
            calibration_split=str(threshold_raw["calibration_split"]),
            calibration_run_id=str(threshold_raw["calibration_run_id"]),
            strategy=str(threshold_raw["strategy"]),
        )
        if threshold.to_dict() != dict(threshold_raw):
            raise InvalidTransitionError("CARE online threshold policy cannot be reproduced")
        evidence_raw = raw["evidence_artifact"]
        if not isinstance(evidence_raw, Mapping):
            raise InvalidTransitionError("CARE runtime evidence artifact is malformed")
        evidence = ArtifactReference(str(evidence_raw["uri"]), str(evidence_raw["sha256"]))
        template = raw["alert_policy_template"]
        if not isinstance(template, Mapping):
            raise InvalidTransitionError("CARE alert policy template is malformed")
        policy = AnomalyAlertPolicy(
            policy_id=str(template["policy_id"]),
            policy_version=str(template["policy_version"]),
            model_id=model.id,
            model_version=model.version,
            deployment_id=deployment.id,
            deployment_version=deployment.id,
            component=str(template["component"]),
            asset_scope=turbine_id,
            trigger_threshold=float(template["trigger_threshold"]),
            consecutive_trigger_windows=int(template["consecutive_trigger_windows"]),
            recovery_threshold=float(template["recovery_threshold"]),
            consecutive_recovery_windows=int(template["consecutive_recovery_windows"]),
            cooldown_seconds=int(template["cooldown_seconds"]),
            missing_window_behavior=cast(Any, template["missing_window_behavior"]),
            uncertain_quality_behavior=cast(Any, template["uncertain_quality_behavior"]),
            enabled=bool(template["enabled"]),
        )
        if policy.trigger_threshold != threshold.value:
            raise InvalidTransitionError("CARE alert and prediction thresholds disagree")
        profile_raw = raw["mission_analysis_profile"]
        if not isinstance(profile_raw, Mapping):
            raise InvalidTransitionError("CARE mission analysis profile is malformed")
        profile = MissionAnalysisProfile.model_validate(dict(profile_raw))
        return AnomalyRuntimeConfiguration(
            threshold_policy=threshold,
            evidence_artifact=evidence,
            alert_policy=policy,
            mission_profile=profile,
            evaluation_run_id=str(raw["evaluation_run_id"]),
            feature_set_version=str(raw["feature_set_version"]),
            quality_rule_version=str(raw["quality_rule_version"]),
            document_sha256=str(raw["runtime_configuration_sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTransitionError("CARE online runtime configuration is malformed") from exc


async def run_replay_anomaly_inference(
    session: AsyncSession,
    settings: Settings,
    inference_client: ModelInferenceClient,
    *,
    deployment_id: str,
    benchmark_replay_run_id: str,
    source_row_id: int,
    subject: str,
) -> ModelPrediction:
    """Run one persisted CARE replay row through the deployment's governed model path."""

    deployment = await session.get(ModelDeployment, deployment_id)
    if deployment is None:
        raise NotFoundError(f"model deployment {deployment_id} was not found")
    model = await session.get(RegisteredModel, deployment.model_id)
    if model is None:  # pragma: no cover - protected by the foreign key
        raise NotFoundError(f"model {deployment.model_id} was not found")
    replay = await session.get(BenchmarkReplayRun, benchmark_replay_run_id)
    if replay is None:
        raise NotFoundError(f"benchmark replay run {benchmark_replay_run_id} was not found")
    if (
        replay.deployment_id != deployment.id
        or replay.model_id != model.id
        or replay.model_version != model.version
        or replay.status != "running"
        or not replay.window_start_row_id <= source_row_id <= replay.window_end_row_id
    ):
        raise InvalidTransitionError("benchmark replay is not running in this deployment scope")
    runtime = _runtime_configuration(deployment, model, turbine_id=replay.online_turbine_id)
    selected_names = [str(value["canonical_variable"]) for value in replay.selected_variables]
    rows = list(
        (
            await session.scalars(
                select(ScadaSample)
                .where(
                    ScadaSample.source_id == CARE_REPLAY_SOURCE_ID,
                    ScadaSample.turbine_id == replay.online_turbine_id,
                    ScadaSample.source_sequence == source_row_id,
                    ScadaSample.variable.in_(selected_names),
                )
                .order_by(ScadaSample.variable, ScadaSample.id)
            )
        ).all()
    )
    if len(rows) != len(selected_names) or {row.variable for row in rows} != set(selected_names):
        raise InvalidTransitionError("CARE replay row does not contain the exact selected features")
    samples = [
        {
            "source_event_id": row.source_event_id,
            "source_sequence": row.source_sequence,
            "turbine_id": row.turbine_id,
            "observed_at": _as_utc(row.observed_at).isoformat(),
            "variable": row.variable,
            "value": row.value,
            "unit": row.unit,
            "quality": row.quality,
            "quality_code": row.attributes.get("quality_code"),
            "attributes": row.attributes,
        }
        for row in rows
    ]
    return await run_anomaly_inference(
        session,
        settings,
        inference_client,
        deployment_id=deployment.id,
        feature_samples=samples,
        feature_set_version=runtime.feature_set_version,
        quality_rule_version=runtime.quality_rule_version,
        threshold_policy=runtime.threshold_policy,
        evidence_artifact=runtime.evidence_artifact,
        subject=subject,
        benchmark_evaluation_run_id=runtime.evaluation_run_id,
    )


def _state_id(policy: AnomalyAlertPolicy) -> str:
    digest = hashlib.sha256(policy.dedup_key.encode("utf-8")).hexdigest()[:40]
    return f"care-alert-state-{digest}"


def _phase(state: AnomalyAlertState) -> str:
    if state.status == "alarming":
        return "active"
    if state.status == "cooldown":
        return "cooldown"
    if state.consecutive_recovery_count:
        return "recovering"
    if state.consecutive_trigger_count:
        return "triggering"
    return "normal"


def _state_request(
    policy: AnomalyAlertPolicy,
    state: AnomalyAlertState,
    *,
    last_prediction_created_at: datetime | None,
) -> AnomalyAlertPolicyStateRequest:
    policy_document = policy.to_document()
    cooldown_until = (
        state.last_alarm_at + timedelta(seconds=policy.cooldown_seconds)
        if state.last_alarm_at is not None
        else None
    )
    return AnomalyAlertPolicyStateRequest(
        policy_state_id=_state_id(policy),
        deployment_id=policy.deployment_id,
        turbine_id=policy.asset_scope,
        component=policy.component,
        policy_version=policy.policy_version,
        policy_sha256=str(policy_document["policy_sha256"]),
        phase=cast(Any, _phase(state)),
        consecutive_trigger_count=state.consecutive_trigger_count,
        consecutive_recovery_count=state.consecutive_recovery_count,
        cooldown_until=cooldown_until,
        last_prediction_id=state.last_prediction_id,
        last_prediction_created_at=last_prediction_created_at,
        dedup_key=policy.dedup_key,
        policy_document=policy_document,
        state_document=state.to_document(),
        revision=state.revision,
    )


def _prediction_quality(prediction: ModelPrediction) -> Literal["good", "uncertain", "bad"]:
    signals = prediction.input_snapshot.get("signals")
    if not isinstance(signals, list) or not signals:
        raise InvalidTransitionError("anomaly prediction has no persisted feature signals")
    qualities = {str(signal.get("quality")) for signal in signals if isinstance(signal, Mapping)}
    if "bad" in qualities:
        return "bad"
    if qualities != {"good"}:
        return "uncertain"
    return "good"


async def evaluate_anomaly_alert(
    session: AsyncSession,
    *,
    prediction_id: str,
    subject: str,
) -> AnomalyAlertOutcome:
    """Persist policy state and create a prediction-sourced alarm/Mission when it triggers."""

    prediction = await session.get(ModelPrediction, prediction_id)
    if prediction is None:
        raise NotFoundError(f"model prediction {prediction_id} was not found")
    if prediction.status != "succeeded" or prediction.prediction_kind != "anomaly":
        raise InvalidTransitionError("alert evaluation requires a successful anomaly prediction")
    verify_governed_anomaly_output(prediction.output)
    deployment = await session.get(ModelDeployment, prediction.deployment_id)
    model = await session.get(RegisteredModel, prediction.model_id)
    if deployment is None or model is None:  # pragma: no cover - protected by foreign keys
        raise NotFoundError("anomaly prediction deployment or model was not found")
    runtime = _runtime_configuration(deployment, model, turbine_id=prediction.turbine_id)
    policy = runtime.alert_policy
    existing = await session.scalar(
        select(AnomalyAlertPolicyState)
        .where(
            AnomalyAlertPolicyState.deployment_id == policy.deployment_id,
            AnomalyAlertPolicyState.turbine_id == policy.asset_scope,
            AnomalyAlertPolicyState.component == policy.component,
            AnomalyAlertPolicyState.policy_version == policy.policy_version,
        )
        .with_for_update()
    )
    if existing is None:
        state = AnomalyAlertState.initial(policy)
        await persist_anomaly_alert_policy_state(
            session,
            _state_request(policy, state, last_prediction_created_at=None),
        )
        previous_prediction_created_at = None
    else:
        if existing.policy_document != policy.to_document():
            raise InvalidTransitionError("persisted anomaly alert policy has drifted")
        state = AnomalyAlertState.from_document(existing.state_document)
        previous_prediction_created_at = existing.last_prediction_created_at

    alarm_id = f"ALARM-{hashlib.sha256(prediction.id.encode()).hexdigest()[:30]}"
    decision = apply_alert_policy(
        policy,
        state,
        prediction=AlertPolicyInput.from_governed_output(
            prediction.id,
            prediction.output,
            quality=_prediction_quality(prediction),
        ),
        alarm_id_factory=alarm_id,
    )
    last_prediction_created_at = (
        previous_prediction_created_at
        if decision.action == "duplicate"
        else _as_utc(prediction.created_at)
    )
    _persisted_state, state_replayed = await persist_anomaly_alert_policy_state(
        session,
        _state_request(
            policy,
            decision.state,
            last_prediction_created_at=last_prediction_created_at,
        ),
    )

    alarm: Alarm | None = await session.scalar(
        select(Alarm).where(Alarm.model_prediction_id == prediction.id)
    )
    mission: Mission | None = None
    if alarm is not None:
        mission = await session.scalar(select(Mission).where(Mission.alarm_id == alarm.id))
    if decision.action == "trigger":
        if alarm is not None:  # pragma: no cover - uniqueness and duplicate path prevent this
            raise InvalidTransitionError("anomaly prediction already owns an alarm")
        signals = prediction.input_snapshot["signals"]
        primary = next(
            (
                value
                for value in signals
                if isinstance(value, Mapping)
                and value.get("variable") == runtime.mission_profile.primary_variable
            ),
            signals[0],
        )
        source_event_ids = [
            str(value["source_event_id"])
            for value in signals
            if isinstance(value, Mapping) and isinstance(value.get("source_event_id"), str)
        ]
        alarm = Alarm(
            id=alarm_id,
            turbine_id=prediction.turbine_id,
            source_event_id=None,
            model_prediction_id=prediction.id,
            code="CARE-MULTIVARIATE-ANOMALY",
            subsystem=policy.component,
            title=f"{prediction.turbine_id} governed CARE anomaly",
            severity=AlarmSeverity.MAJOR.value,
            status=AlarmStatus.OPEN.value,
            triggered_at=_as_utc(prediction.feature_observed_at),
            evidence={
                "variable": str(primary["variable"]),
                "value": float(primary["value"]),
                "unit": str(primary["unit"]),
                "quality": str(primary["quality"]),
                "source_id": CARE_REPLAY_SOURCE_ID,
                "source_event_ids": source_event_ids,
                "model_prediction_id": prediction.id,
                "benchmark_replay_run_id": prediction.benchmark_replay_run_id,
                "benchmark_evaluation_run_id": prediction.benchmark_evaluation_run_id,
                "policy_state_id": _state_id(policy),
                "runtime_configuration_sha256": runtime.document_sha256,
                "attributes": {
                    "anomaly_score": prediction.anomaly_score,
                    "binary_prediction": prediction.binary_prediction,
                    "threshold_policy_sha256": prediction.threshold_policy_sha256,
                    "prediction_truth_used": False,
                },
            },
        )
        session.add(alarm)
        await session.flush()
        mission_result, _mission_replayed = await create_mission(
            session,
            MissionCreateRequest(
                alarm_id=alarm.id,
                title=f"Investigate {prediction.turbine_id} CARE anomaly",
                analysis_profile=runtime.mission_profile,
            ),
            idempotency_key=hashlib.sha256(
                f"care-alert-mission:{prediction.id}".encode()
            ).hexdigest(),
            subject=subject,
        )
        mission = await session.get(Mission, str(mission_result["mission_id"]))
        append_domain_event(
            session,
            event_type="alarm.opened.from-model-prediction",
            aggregate_type="alarm",
            aggregate_id=alarm.id,
            payload={
                "alarm_id": alarm.id,
                "mission_id": mission.id if mission is not None else None,
                "model_prediction_id": prediction.id,
                "benchmark_replay_run_id": prediction.benchmark_replay_run_id,
                "policy_state_id": _state_id(policy),
                "prediction_truth_used": False,
            },
        )
    elif decision.action == "recover":
        previous_alarm_id = state.active_alarm_id
        if previous_alarm_id is not None:
            recovered = await session.get(Alarm, previous_alarm_id)
            if recovered is not None and recovered.status != AlarmStatus.RESOLVED.value:
                recovered.status = AlarmStatus.RESOLVED.value
                recovered.resolved_at = _as_utc(prediction.feature_observed_at)
                recovered.revision += 1
                recovered.updated_at = datetime.now(UTC)
                append_domain_event(
                    session,
                    event_type="alarm.resolved.by-model-policy",
                    aggregate_type="alarm",
                    aggregate_id=recovered.id,
                    payload={
                        "alarm_id": recovered.id,
                        "model_prediction_id": prediction.id,
                        "policy_state_id": _state_id(policy),
                    },
                )
    if decision.action != "duplicate":
        append_domain_event(
            session,
            event_type="model.anomaly-alert.evaluated",
            aggregate_type="model_prediction",
            aggregate_id=prediction.id,
            payload={
                "prediction_id": prediction.id,
                "action": decision.action,
                "reason": decision.reason,
                "policy_state_id": _state_id(policy),
                "state_revision": decision.state.revision,
                "alarm_id": alarm.id if alarm is not None else None,
                "mission_id": mission.id if mission is not None else None,
                "prediction_truth_used": False,
            },
        )
    await session.flush()
    return AnomalyAlertOutcome(
        prediction_id=prediction.id,
        action=decision.action,
        reason=decision.reason,
        policy_state_id=_state_id(policy),
        state_revision=decision.state.revision,
        alarm_id=alarm.id if alarm is not None else None,
        mission_id=mission.id if mission is not None else None,
        replayed=decision.action == "duplicate" or state_replayed,
    )


__all__ = [
    "AnomalyAlertOutcome",
    "AnomalyRuntimeConfiguration",
    "evaluate_anomaly_alert",
    "run_replay_anomaly_inference",
]
