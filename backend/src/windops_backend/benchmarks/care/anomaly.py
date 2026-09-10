from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

import windops_backend.benchmarks.care.anomaly_runtime as _anomaly_runtime
from windops_backend.benchmarks.care.artifact_utils import (
    canonical_json_sha256 as _sha256_json,
)
from windops_backend.benchmarks.care.replay import (
    REPLAY_CONTRACT_VERSION,
)
from windops_backend.benchmarks.care.scoring import (
    SCORE_PROTOCOL_VERSION,
)

ANOMALY_RUNTIME_CONTRACT_VERSION = _anomaly_runtime.ANOMALY_RUNTIME_CONTRACT_VERSION
ANOMALY_PREDICTION_SCHEMA_VERSION = _anomaly_runtime.ANOMALY_PREDICTION_SCHEMA_VERSION
ALERT_POLICY_SCHEMA_VERSION = _anomaly_runtime.ALERT_POLICY_SCHEMA_VERSION
ALERT_STATE_SCHEMA_VERSION = _anomaly_runtime.ALERT_STATE_SCHEMA_VERSION
ACTIVATION_GATE_SCHEMA_VERSION = _anomaly_runtime.ACTIVATION_GATE_SCHEMA_VERSION
DEPLOYMENT_VERSION_RULE = _anomaly_runtime.DEPLOYMENT_VERSION_RULE
ANOMALY_INPUT_REQUIRED = _anomaly_runtime.ANOMALY_INPUT_REQUIRED
ANOMALY_OUTPUT_REQUIRED = _anomaly_runtime.ANOMALY_OUTPUT_REQUIRED
FORBIDDEN_ANOMALY_FIELDS = _anomaly_runtime.FORBIDDEN_ANOMALY_FIELDS
CareAnomalyError = _anomaly_runtime.CareAnomalyError
_verify_governed_evaluation_artifact = _anomaly_runtime._verify_governed_evaluation_artifact
_nonempty = _anomaly_runtime._nonempty
_utc = _anomaly_runtime._utc
_finite = _anomaly_runtime._finite
_require_schema_fields = _anomaly_runtime._require_schema_fields
validate_anomaly_model_schemas = _anomaly_runtime.validate_anomaly_model_schemas
canonical_anomaly_input_schema = _anomaly_runtime.canonical_anomaly_input_schema
canonical_anomaly_output_schema = _anomaly_runtime.canonical_anomaly_output_schema
ArtifactReference = _anomaly_runtime.ArtifactReference
AnomalyFeatureWindow = _anomaly_runtime.AnomalyFeatureWindow
AnomalyRuntimeContext = _anomaly_runtime.AnomalyRuntimeContext
build_governed_anomaly_output = _anomaly_runtime.build_governed_anomaly_output
verify_governed_anomaly_output = _anomaly_runtime.verify_governed_anomaly_output


@dataclass(frozen=True, slots=True)
class AlarmSourceReference:
    source_event_id: str | None = None
    model_prediction_id: str | None = None

    def __post_init__(self) -> None:
        if self.source_event_id is None and self.model_prediction_id is None:
            raise CareAnomalyError("alarm must reference an ingest event or a model prediction")
        if self.source_event_id is not None:
            _nonempty(self.source_event_id, field_name="alarm source_event_id")
        if self.model_prediction_id is not None:
            _nonempty(self.model_prediction_id, field_name="alarm model_prediction_id")

    @property
    def requires_synthetic_ingest_receipt(self) -> bool:
        return False


MissingWindowBehavior = Literal["reset", "hold"]
UncertainQualityBehavior = Literal["reset", "hold"]


@dataclass(frozen=True, slots=True)
class AnomalyAlertPolicy:
    policy_id: str
    policy_version: str
    model_id: str
    model_version: str
    deployment_id: str
    deployment_version: str
    component: str
    asset_scope: str
    trigger_threshold: float
    consecutive_trigger_windows: int
    recovery_threshold: float
    consecutive_recovery_windows: int
    cooldown_seconds: int
    missing_window_behavior: MissingWindowBehavior = "reset"
    uncertain_quality_behavior: UncertainQualityBehavior = "hold"
    enabled: bool = True

    def __post_init__(self) -> None:
        for name, value in (
            ("policy_id", self.policy_id),
            ("policy_version", self.policy_version),
            ("model_id", self.model_id),
            ("model_version", self.model_version),
            ("deployment_id", self.deployment_id),
            ("deployment_version", self.deployment_version),
            ("component", self.component),
            ("asset_scope", self.asset_scope),
        ):
            _nonempty(value, field_name=name)
        _finite(self.trigger_threshold, field_name="trigger_threshold")
        _finite(self.recovery_threshold, field_name="recovery_threshold")
        if not 0 <= self.recovery_threshold < self.trigger_threshold <= 1:
            raise CareAnomalyError("alert thresholds must satisfy 0 <= recovery < trigger <= 1")
        if self.consecutive_trigger_windows < 1 or self.consecutive_recovery_windows < 1:
            raise CareAnomalyError("alert consecutive-window counts must be positive")
        if self.cooldown_seconds < 0:
            raise CareAnomalyError("alert cooldown cannot be negative")
        if self.missing_window_behavior not in {"reset", "hold"}:
            raise CareAnomalyError("unsupported missing-window behavior")
        if self.uncertain_quality_behavior not in {"reset", "hold"}:
            raise CareAnomalyError("unsupported uncertain-quality behavior")

    @property
    def dedup_key(self) -> str:
        identity = {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "deployment_id": self.deployment_id,
            "deployment_version": self.deployment_version,
            "component": self.component,
            "asset_scope": self.asset_scope,
        }
        return f"care-alert:{_sha256_json(identity)}"

    def to_document(self) -> dict[str, Any]:
        document = {
            "schema_version": ALERT_POLICY_SCHEMA_VERSION,
            **{field_name: getattr(self, field_name) for field_name in self.__dataclass_fields__},
            "dedup_key": self.dedup_key,
            "out_of_order_behavior": "reject",
        }
        return {**document, "policy_sha256": _sha256_json(document)}

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> AnomalyAlertPolicy:
        actual = value.get("policy_sha256")
        if not isinstance(actual, str):
            raise CareAnomalyError("alert policy document is missing policy_sha256")
        unsigned = {key: item for key, item in value.items() if key != "policy_sha256"}
        if _sha256_json(unsigned) != actual:
            raise CareAnomalyError("alert policy document hash mismatch")
        if (
            value.get("schema_version") != ALERT_POLICY_SCHEMA_VERSION
            or value.get("out_of_order_behavior") != "reject"
        ):
            raise CareAnomalyError("alert policy document has unsupported semantics")
        try:
            missing_behavior = value["missing_window_behavior"]
            uncertain_behavior = value["uncertain_quality_behavior"]
            enabled = value["enabled"]
            if missing_behavior not in {"reset", "hold"} or uncertain_behavior not in {
                "reset",
                "hold",
            }:
                raise CareAnomalyError("alert policy document has invalid behavior rules")
            if type(enabled) is not bool:
                raise CareAnomalyError("alert policy enabled must be boolean")
            return cls(
                policy_id=str(value["policy_id"]),
                policy_version=str(value["policy_version"]),
                model_id=str(value["model_id"]),
                model_version=str(value["model_version"]),
                deployment_id=str(value["deployment_id"]),
                deployment_version=str(value["deployment_version"]),
                component=str(value["component"]),
                asset_scope=str(value["asset_scope"]),
                trigger_threshold=float(value["trigger_threshold"]),
                consecutive_trigger_windows=int(value["consecutive_trigger_windows"]),
                recovery_threshold=float(value["recovery_threshold"]),
                consecutive_recovery_windows=int(value["consecutive_recovery_windows"]),
                cooldown_seconds=int(value["cooldown_seconds"]),
                missing_window_behavior=cast(MissingWindowBehavior, missing_behavior),
                uncertain_quality_behavior=cast(UncertainQualityBehavior, uncertain_behavior),
                enabled=enabled,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CareAnomalyError("alert policy document is malformed") from exc


AlertStatus = Literal["normal", "alarming", "cooldown"]


@dataclass(frozen=True, slots=True)
class AnomalyAlertState:
    policy_id: str
    policy_version: str
    asset_scope: str
    status: AlertStatus = "normal"
    consecutive_trigger_count: int = 0
    consecutive_recovery_count: int = 0
    last_end_sequence: int | None = None
    last_prediction_id: str | None = None
    last_alarm_at: datetime | None = None
    active_alarm_id: str | None = None
    revision: int = 0

    def __post_init__(self) -> None:
        _nonempty(self.policy_id, field_name="state policy_id")
        _nonempty(self.policy_version, field_name="state policy_version")
        _nonempty(self.asset_scope, field_name="state asset_scope")
        if self.status not in {"normal", "alarming", "cooldown"}:
            raise CareAnomalyError("unknown alert state status")
        if min(self.consecutive_trigger_count, self.consecutive_recovery_count, self.revision) < 0:
            raise CareAnomalyError("alert state counters cannot be negative")
        if self.last_alarm_at is not None:
            _utc(self.last_alarm_at, field_name="last_alarm_at")
        if self.status == "alarming" and not self.active_alarm_id:
            raise CareAnomalyError("alarming state must reference its active alarm")
        if self.status != "alarming" and self.active_alarm_id is not None:
            raise CareAnomalyError("only alarming state may retain an active alarm")

    @classmethod
    def initial(cls, policy: AnomalyAlertPolicy) -> AnomalyAlertState:
        return cls(policy.policy_id, policy.policy_version, policy.asset_scope)

    def to_document(self) -> dict[str, Any]:
        document = {
            "schema_version": ALERT_STATE_SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "asset_scope": self.asset_scope,
            "status": self.status,
            "consecutive_trigger_count": self.consecutive_trigger_count,
            "consecutive_recovery_count": self.consecutive_recovery_count,
            "last_end_sequence": self.last_end_sequence,
            "last_prediction_id": self.last_prediction_id,
            "last_alarm_at": self.last_alarm_at.isoformat() if self.last_alarm_at else None,
            "active_alarm_id": self.active_alarm_id,
            "revision": self.revision,
        }
        return {**document, "state_sha256": _sha256_json(document)}

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> AnomalyAlertState:
        actual = value.get("state_sha256")
        if not isinstance(actual, str):
            raise CareAnomalyError("alert state document is missing state_sha256")
        unsigned = {key: item for key, item in value.items() if key != "state_sha256"}
        if _sha256_json(unsigned) != actual:
            raise CareAnomalyError("alert state document hash mismatch")
        if value.get("schema_version") != ALERT_STATE_SCHEMA_VERSION:
            raise CareAnomalyError("alert state document has an unsupported schema")
        raw_alarm_at = value.get("last_alarm_at")
        try:
            raw_status = value["status"]
            if raw_status not in {"normal", "alarming", "cooldown"}:
                raise CareAnomalyError("alert state document has an invalid status")
            last_alarm_at = (
                datetime.fromisoformat(str(raw_alarm_at)) if raw_alarm_at is not None else None
            )
            return cls(
                policy_id=str(value["policy_id"]),
                policy_version=str(value["policy_version"]),
                asset_scope=str(value["asset_scope"]),
                status=cast(AlertStatus, raw_status),
                consecutive_trigger_count=int(value["consecutive_trigger_count"]),
                consecutive_recovery_count=int(value["consecutive_recovery_count"]),
                last_end_sequence=(
                    int(value["last_end_sequence"])
                    if value.get("last_end_sequence") is not None
                    else None
                ),
                last_prediction_id=(
                    str(value["last_prediction_id"])
                    if value.get("last_prediction_id") is not None
                    else None
                ),
                last_alarm_at=last_alarm_at,
                active_alarm_id=(
                    str(value["active_alarm_id"])
                    if value.get("active_alarm_id") is not None
                    else None
                ),
                revision=int(value["revision"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CareAnomalyError("alert state document is malformed") from exc


@dataclass(frozen=True, slots=True)
class AlertPolicyDecision:
    state: AnomalyAlertState
    action: Literal["none", "trigger", "recover", "duplicate", "disabled"]
    dedup_key: str
    reason: str


@dataclass(frozen=True, slots=True)
class AlertPolicyInput:
    prediction_id: str
    model_id: str
    model_version: str
    deployment_id: str
    deployment_version: str
    component: str
    asset_scope: str
    start_sequence: int
    end_sequence: int
    observed_at: datetime
    anomaly_score: float
    binary_prediction: bool
    quality: Literal["good", "uncertain", "bad"]

    def __post_init__(self) -> None:
        for name in (
            "prediction_id",
            "model_id",
            "model_version",
            "deployment_id",
            "deployment_version",
            "component",
            "asset_scope",
        ):
            _nonempty(str(getattr(self, name)), field_name=name)
        _utc(self.observed_at, field_name="prediction observed_at")
        _finite(self.anomaly_score, field_name="anomaly_score")
        if not 0 <= self.anomaly_score <= 1 or type(self.binary_prediction) is not bool:
            raise CareAnomalyError("alert prediction score/binary is invalid")
        if self.start_sequence < 0 or self.end_sequence < self.start_sequence:
            raise CareAnomalyError("alert feature sequence window is invalid")
        if self.quality not in {"good", "uncertain", "bad"}:
            raise CareAnomalyError("alert prediction quality is invalid")

    @classmethod
    def from_governed_output(
        cls,
        prediction_id: str,
        output: Mapping[str, Any],
        *,
        quality: Literal["good", "uncertain", "bad"],
    ) -> AlertPolicyInput:
        verify_governed_anomaly_output(output)
        try:
            return cls(
                prediction_id=prediction_id,
                model_id=str(output["model_id"]),
                model_version=str(output["model_version"]),
                deployment_id=str(output["deployment_id"]),
                deployment_version=str(output["deployment_version"]),
                component=str(output["component"]),
                asset_scope=str(output["online_turbine_id"]),
                start_sequence=int(output["feature_start_sequence"]),
                end_sequence=int(output["feature_end_sequence"]),
                observed_at=datetime.fromisoformat(str(output["feature_window_end"])),
                anomaly_score=float(output["anomaly_score"]),
                binary_prediction=bool(output["binary_prediction"]),
                quality=quality,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CareAnomalyError("governed anomaly output cannot drive alert policy") from exc


def _reset_or_hold_counts(
    state: AnomalyAlertState,
    behavior: Literal["reset", "hold"],
) -> tuple[int, int]:
    if behavior == "hold":
        return state.consecutive_trigger_count, state.consecutive_recovery_count
    return 0, 0


def apply_alert_policy(
    policy: AnomalyAlertPolicy,
    state: AnomalyAlertState,
    *,
    prediction: AlertPolicyInput,
    alarm_id_factory: str | None = None,
) -> AlertPolicyDecision:
    if (
        state.policy_id != policy.policy_id
        or state.policy_version != policy.policy_version
        or state.asset_scope != policy.asset_scope
    ):
        raise CareAnomalyError("alert state does not belong to this policy identity")
    expected_identity = (
        policy.model_id,
        policy.model_version,
        policy.deployment_id,
        policy.deployment_version,
        policy.component,
        policy.asset_scope,
    )
    actual_identity = (
        prediction.model_id,
        prediction.model_version,
        prediction.deployment_id,
        prediction.deployment_version,
        prediction.component,
        prediction.asset_scope,
    )
    if actual_identity != expected_identity:
        raise CareAnomalyError("alert prediction identity does not match its policy scope")
    score = prediction.anomaly_score
    binary_prediction = prediction.binary_prediction
    if binary_prediction != (score > policy.trigger_threshold):
        raise CareAnomalyError("alert binary prediction disagrees with policy threshold")
    if state.last_prediction_id == prediction.prediction_id:
        return AlertPolicyDecision(state, "duplicate", policy.dedup_key, "idempotent-retry")
    if state.last_end_sequence is not None and prediction.end_sequence <= state.last_end_sequence:
        raise CareAnomalyError("out-of-order or replayed prediction window rejected")

    trigger_count = state.consecutive_trigger_count
    recovery_count = state.consecutive_recovery_count
    reason = "evaluated"
    if (
        state.last_end_sequence is not None
        and prediction.start_sequence > state.last_end_sequence + 1
    ):
        trigger_count, recovery_count = _reset_or_hold_counts(state, policy.missing_window_behavior)
        reason = f"missing-window-{policy.missing_window_behavior}"
    if prediction.quality != "good":
        trigger_count, recovery_count = _reset_or_hold_counts(
            replace(
                state,
                consecutive_trigger_count=trigger_count,
                consecutive_recovery_count=recovery_count,
            ),
            policy.uncertain_quality_behavior,
        )
        updated = replace(
            state,
            consecutive_trigger_count=trigger_count,
            consecutive_recovery_count=recovery_count,
            last_end_sequence=prediction.end_sequence,
            last_prediction_id=prediction.prediction_id,
            revision=state.revision + 1,
        )
        return AlertPolicyDecision(
            updated,
            "none" if policy.enabled else "disabled",
            policy.dedup_key,
            f"quality-{prediction.quality}-{policy.uncertain_quality_behavior}",
        )
    if not policy.enabled:
        updated = replace(
            state,
            last_end_sequence=prediction.end_sequence,
            last_prediction_id=prediction.prediction_id,
            revision=state.revision + 1,
        )
        return AlertPolicyDecision(updated, "disabled", policy.dedup_key, "policy-disabled")

    status: AlertStatus = state.status
    active_alarm_id = state.active_alarm_id
    last_alarm_at = state.last_alarm_at
    action: Literal["none", "trigger", "recover", "duplicate", "disabled"] = "none"
    if status == "alarming":
        trigger_count = 0
        recovery_count = recovery_count + 1 if score <= policy.recovery_threshold else 0
        if recovery_count >= policy.consecutive_recovery_windows:
            status = "normal"
            recovery_count = 0
            active_alarm_id = None
            action = "recover"
            reason = "recovery-threshold-satisfied"
    elif binary_prediction:
        recovery_count = 0
        trigger_count += 1
        cooldown_active = bool(
            last_alarm_at is not None
            and prediction.observed_at < last_alarm_at + timedelta(seconds=policy.cooldown_seconds)
        )
        if cooldown_active:
            status = "cooldown"
            reason = "cooldown-active"
        elif trigger_count >= policy.consecutive_trigger_windows:
            alarm_id = _nonempty(alarm_id_factory or "", field_name="new alarm_id")
            status = "alarming"
            trigger_count = 0
            active_alarm_id = alarm_id
            last_alarm_at = prediction.observed_at
            action = "trigger"
            reason = "consecutive-trigger-threshold-satisfied"
    else:
        status = "normal" if status == "cooldown" else status
        trigger_count = 0
        recovery_count = 0

    updated = replace(
        state,
        status=status,
        consecutive_trigger_count=trigger_count,
        consecutive_recovery_count=recovery_count,
        last_end_sequence=prediction.end_sequence,
        last_prediction_id=prediction.prediction_id,
        last_alarm_at=last_alarm_at,
        active_alarm_id=active_alarm_id,
        revision=state.revision + 1,
    )
    return AlertPolicyDecision(updated, action, policy.dedup_key, reason)


@dataclass(frozen=True, slots=True)
class BenchmarkMetricSnapshot:
    care_score: float
    event_detection_rate: float
    normal_event_false_positive_rate: float
    requested_event_count: int
    scored_event_count: int
    unscorable_event_count: int
    data_failure_event_count: int
    model_failure_event_count: int
    score_protocol_version: str = SCORE_PROTOCOL_VERSION
    snapshot_sha256: str = ""

    def __post_init__(self) -> None:
        for name in ("care_score", "event_detection_rate", "normal_event_false_positive_rate"):
            value = _finite(float(getattr(self, name)), field_name=name)
            if not 0 <= value <= 1:
                raise CareAnomalyError(f"{name} must be within 0..1")
        counts = (
            self.requested_event_count,
            self.scored_event_count,
            self.unscorable_event_count,
            self.data_failure_event_count,
            self.model_failure_event_count,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts
        ):
            raise CareAnomalyError("metric snapshot counts must be non-negative integers")
        if self.score_protocol_version != SCORE_PROTOCOL_VERSION:
            raise CareAnomalyError("metric snapshot uses an unsupported scoring protocol")
        expected = _sha256_json(self.unsigned_document())
        if self.snapshot_sha256 and self.snapshot_sha256 != expected:
            raise CareAnomalyError("metric snapshot content hash mismatch")
        object.__setattr__(self, "snapshot_sha256", expected)

    def unsigned_document(self) -> dict[str, Any]:
        return {
            "care_score": self.care_score,
            "event_detection_rate": self.event_detection_rate,
            "normal_event_false_positive_rate": self.normal_event_false_positive_rate,
            "requested_event_count": self.requested_event_count,
            "scored_event_count": self.scored_event_count,
            "unscorable_event_count": self.unscorable_event_count,
            "data_failure_event_count": self.data_failure_event_count,
            "model_failure_event_count": self.model_failure_event_count,
            "score_protocol_version": self.score_protocol_version,
        }

    @classmethod
    def from_evaluation_artifact(cls, artifact: Mapping[str, Any]) -> BenchmarkMetricSnapshot:
        _verify_governed_evaluation_artifact(artifact)
        summary = artifact.get("summary")
        if not isinstance(summary, Mapping) or summary.get("status") != "scored":
            raise CareAnomalyError("activation requires a scored evaluation summary")
        event_metrics = summary.get("event_metrics")
        if not isinstance(event_metrics, Mapping):
            raise CareAnomalyError("evaluation artifact has no structured event metrics")
        return cls(
            care_score=float(summary["care_score"]),
            event_detection_rate=float(event_metrics["event_detection_rate"]),
            normal_event_false_positive_rate=float(
                event_metrics["normal_event_false_positive_rate"]
            ),
            requested_event_count=int(summary["requested_event_count"]),
            scored_event_count=int(summary["scored_event_count"]),
            unscorable_event_count=int(summary["unscorable_event_count"]),
            data_failure_event_count=int(summary["data_failure_event_count"]),
            model_failure_event_count=int(summary["model_failure_event_count"]),
        )


@dataclass(frozen=True, slots=True)
class ActivationGatePolicy:
    policy_version: str
    minimum_care_score: float
    minimum_event_detection_rate: float
    maximum_normal_event_false_positive_rate: float
    required_farms: tuple[str, ...]
    required_generalization_protocols: tuple[str, ...]
    required_feature_set_version: str
    required_feature_set_sha256: str
    required_quality_rule_version: str
    required_quality_contract_sha256: str
    required_threshold_policy_version: str
    required_threshold_policy_sha256: str
    require_zero_failures: bool = True
    require_zero_unscorable: bool = True

    def __post_init__(self) -> None:
        _nonempty(self.policy_version, field_name="activation policy version")
        for name in (
            "minimum_care_score",
            "minimum_event_detection_rate",
            "maximum_normal_event_false_positive_rate",
        ):
            value = _finite(float(getattr(self, name)), field_name=name)
            if not 0 <= value <= 1:
                raise CareAnomalyError(f"{name} must be within 0..1")
        if not self.required_farms or not self.required_generalization_protocols:
            raise CareAnomalyError("activation gate must require farms and evaluation protocols")
        for name in (
            "required_feature_set_version",
            "required_feature_set_sha256",
            "required_quality_rule_version",
            "required_quality_contract_sha256",
            "required_threshold_policy_version",
            "required_threshold_policy_sha256",
        ):
            _nonempty(str(getattr(self, name)), field_name=name)


@dataclass(frozen=True, slots=True)
class ActivationGateEvidence:
    evaluation_run_id: str
    evaluation_status: str
    invalidated: bool
    evaluation_artifact: Mapping[str, Any]
    metric_snapshot: BenchmarkMetricSnapshot
    model_id: str
    model_version: str
    model_artifact_sha256: str
    deployment_id: str
    deployment_version: str
    approval_ids: tuple[str, ...]
    audit_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "evaluation_run_id",
            "model_id",
            "model_version",
            "model_artifact_sha256",
            "deployment_id",
            "deployment_version",
        ):
            _nonempty(str(getattr(self, name)), field_name=name)
        if not self.approval_ids or not self.audit_event_ids:
            raise CareAnomalyError("activation evidence requires approvals and audit events")
        digest = self.model_artifact_sha256.lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise CareAnomalyError("activation evidence has an invalid model artifact hash")


_ACTIVATION_AUTHORITY = object()


@dataclass(frozen=True, slots=True)
class AnomalyActivationAuthorization:
    model_id: str
    model_version: str
    model_artifact_sha256: str
    deployment_id: str
    deployment_version: str
    evaluation_run_id: str
    metric_snapshot_sha256: str
    gate_policy_version: str
    authorized_at: datetime
    _authority: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._authority is not _ACTIVATION_AUTHORITY:
            raise CareAnomalyError("activation authorization was not issued by the server gate")
        _utc(self.authorized_at, field_name="authorized_at")


def evaluate_activation_gate(
    policy: ActivationGatePolicy,
    evidence: ActivationGateEvidence,
    *,
    authorized_at: datetime,
) -> AnomalyActivationAuthorization:
    if evidence.evaluation_status != "completed" or evidence.invalidated:
        raise CareAnomalyError("evaluation run must be completed and not invalidated")
    _verify_governed_evaluation_artifact(evidence.evaluation_artifact)
    rebuilt_snapshot = BenchmarkMetricSnapshot.from_evaluation_artifact(
        evidence.evaluation_artifact
    )
    if rebuilt_snapshot != evidence.metric_snapshot:
        raise CareAnomalyError("metric snapshot does not match the immutable evaluation artifact")
    snapshot = evidence.metric_snapshot
    if snapshot.care_score < policy.minimum_care_score:
        raise CareAnomalyError("CARE score does not meet the activation threshold")
    if snapshot.event_detection_rate < policy.minimum_event_detection_rate:
        raise CareAnomalyError("event detection rate does not meet the activation threshold")
    if snapshot.normal_event_false_positive_rate > policy.maximum_normal_event_false_positive_rate:
        raise CareAnomalyError("normal-event false-positive rate exceeds the activation threshold")
    if policy.require_zero_failures and (
        snapshot.data_failure_event_count or snapshot.model_failure_event_count
    ):
        raise CareAnomalyError("evaluation failures cannot be excluded from activation")
    if policy.require_zero_unscorable and snapshot.unscorable_event_count:
        raise CareAnomalyError("unscorable events prevent activation")
    if snapshot.scored_event_count != snapshot.requested_event_count:
        raise CareAnomalyError("activation requires every requested event to be scored")

    artifact = evidence.evaluation_artifact
    run = artifact.get("run")
    predictions = artifact.get("predictions")
    event_results = artifact.get("event_results")
    if (
        not isinstance(run, Mapping)
        or not isinstance(predictions, list)
        or not isinstance(event_results, list)
    ):
        raise CareAnomalyError("evaluation artifact lacks governed activation identities")
    if (
        run.get("model_id") != evidence.model_id
        or run.get("model_version") != evidence.model_version
    ):
        raise CareAnomalyError("evaluation model identity does not match activation target")
    if run.get("generalization_protocol") not in policy.required_generalization_protocols:
        raise CareAnomalyError("evaluation protocol is not approved for activation")
    covered_farms = {
        str(result.get("farm"))
        for result in event_results
        if isinstance(result, Mapping) and result.get("farm") is not None
    }
    if not set(policy.required_farms).issubset(covered_farms):
        raise CareAnomalyError("evaluation does not cover every required farm")
    for prediction in predictions:
        if not isinstance(prediction, Mapping):
            raise CareAnomalyError("evaluation contains a malformed prediction")
        threshold = prediction.get("threshold_policy")
        if not isinstance(threshold, Mapping):
            raise CareAnomalyError("evaluation prediction has no threshold policy")
        expected_pairs = (
            (prediction.get("feature_set_version"), policy.required_feature_set_version),
            (prediction.get("feature_set_sha256"), policy.required_feature_set_sha256),
            (prediction.get("quality_rule_version"), policy.required_quality_rule_version),
            (
                prediction.get("quality_contract_sha256"),
                policy.required_quality_contract_sha256,
            ),
            (threshold.get("version"), policy.required_threshold_policy_version),
            (
                threshold.get("threshold_policy_sha256"),
                policy.required_threshold_policy_sha256,
            ),
        )
        if any(actual != expected for actual, expected in expected_pairs):
            raise CareAnomalyError("evaluation version matrix does not match activation policy")
    return AnomalyActivationAuthorization(
        model_id=evidence.model_id,
        model_version=evidence.model_version,
        model_artifact_sha256=evidence.model_artifact_sha256.lower(),
        deployment_id=evidence.deployment_id,
        deployment_version=evidence.deployment_version,
        evaluation_run_id=evidence.evaluation_run_id,
        metric_snapshot_sha256=snapshot.snapshot_sha256,
        gate_policy_version=policy.policy_version,
        authorized_at=_utc(authorized_at, field_name="authorized_at"),
        _authority=_ACTIVATION_AUTHORITY,
    )


def require_activation_authorization(
    authorization: AnomalyActivationAuthorization | None,
    *,
    model_id: str,
    model_version: str,
    model_artifact_sha256: str,
    deployment_id: str,
) -> None:
    if authorization is None or authorization._authority is not _ACTIVATION_AUTHORITY:
        raise CareAnomalyError("anomaly activation requires server-issued benchmark authorization")
    expected = (
        model_id,
        model_version,
        model_artifact_sha256.lower(),
        deployment_id,
        deployment_id,
    )
    actual = (
        authorization.model_id,
        authorization.model_version,
        authorization.model_artifact_sha256,
        authorization.deployment_id,
        authorization.deployment_version,
    )
    if actual != expected:
        raise CareAnomalyError("activation authorization does not match the model/deployment")


def build_anomaly_runtime_contract() -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schema_version": ANOMALY_RUNTIME_CONTRACT_VERSION,
        "dependencies": {
            "score_protocol": SCORE_PROTOCOL_VERSION,
            "replay_contract": REPLAY_CONTRACT_VERSION,
        },
        "registered_model": {
            "reuse_existing_entity": True,
            "kind": "anomaly",
            "input_required": sorted(ANOMALY_INPUT_REQUIRED),
            "output_required": sorted(ANOMALY_OUTPUT_REQUIRED),
            "forbidden_output": sorted(FORBIDDEN_ANOMALY_FIELDS),
            "predictive_contract_unchanged": True,
        },
        "prediction": {
            "schema_version": ANOMALY_PREDICTION_SCHEMA_VERSION,
            "truth_present": False,
            "window_identity": [
                "dataset_version",
                "farm",
                "event_id",
                "benchmark_replay_run_id",
                "online_turbine_id",
            ],
            "strict_threshold_comparison": "anomaly_score > threshold",
            "deployment_version_rule": DEPLOYMENT_VERSION_RULE,
        },
        "alarm_source": {
            "at_least_one_of": ["source_event_id", "model_prediction_id"],
            "model_prediction_may_be_primary": True,
            "fake_ingest_receipt": False,
            "database_constraint_owner": "CARE-H002",
        },
        "alert_policy": {
            "schema_version": ALERT_POLICY_SCHEMA_VERSION,
            "state_schema_version": ALERT_STATE_SCHEMA_VERSION,
            "persistent_identity": [
                "policy_id",
                "policy_version",
                "model_id",
                "model_version",
                "deployment_id",
                "deployment_version",
                "component",
                "asset_scope",
            ],
            "out_of_order": "reject",
            "missing_window": ["reset", "hold"],
            "uncertain_quality": ["reset", "hold"],
        },
        "activation_gate": {
            "schema_version": ACTIVATION_GATE_SCHEMA_VERSION,
            "authority": "server-only-capability",
            "recompute_evaluation_artifact": True,
            "structured_metric_snapshot": True,
            "arbitrary_metrics_json_accepted": False,
            "frontend_state_accepted": False,
            "requires": [
                "completed-non-invalidated-evaluation",
                "model-package-and-deployment-identity",
                "care-score-v6",
                "normal-and-anomaly-metrics",
                "farm-and-generalization-coverage",
                "feature-quality-threshold-version-matrix",
                "zero-excluded-failures",
                "approval-and-audit-evidence",
            ],
        },
        "phase_boundaries": {
            "database_entities_constraints_and_migration": "CARE-H002",
            "actual_prediction_alarm_mission_replay": "CARE-H005",
        },
    }
    contract["contract_sha256"] = _sha256_json(contract)
    return contract


def verify_anomaly_runtime_contract(contract: Mapping[str, Any]) -> None:
    actual = contract.get("contract_sha256")
    if not isinstance(actual, str):
        raise CareAnomalyError("anomaly runtime contract is missing contract_sha256")
    unsigned = {key: value for key, value in contract.items() if key != "contract_sha256"}
    if _sha256_json(unsigned) != actual:
        raise CareAnomalyError("anomaly runtime contract content hash mismatch")
    if dict(contract) != build_anomaly_runtime_contract():
        raise CareAnomalyError("anomaly runtime contract differs from frozen semantics")


def write_anomaly_runtime_contract(path: Path) -> None:
    document = build_anomaly_runtime_contract()
    verify_anomaly_runtime_contract(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write the CARE v6 anomaly runtime contract")
    parser.add_argument("output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    write_anomaly_runtime_contract(args.output)
    return 0
