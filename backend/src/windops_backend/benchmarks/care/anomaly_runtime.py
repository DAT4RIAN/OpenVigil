from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from windops_backend.benchmarks.care.artifact_utils import (
    canonical_json_sha256 as _sha256_json,
)
from windops_backend.benchmarks.care.contract import DATASET_VERSION
from windops_backend.benchmarks.care.replay import (
    SYNTHETIC_TIME_CLAIM,
    ReplayWindowIdentity,
    validate_replay_window,
)
from windops_backend.benchmarks.care.scoring import (
    ThresholdPolicy,
    verify_evaluation_artifact,
)

ANOMALY_RUNTIME_CONTRACT_VERSION = "care-v6-anomaly-runtime-v1"
ANOMALY_PREDICTION_SCHEMA_VERSION = "care-v6-online-anomaly-prediction-v1"
ALERT_POLICY_SCHEMA_VERSION = "care-v6-alert-policy-v1"
ALERT_STATE_SCHEMA_VERSION = "care-v6-alert-state-v1"
ACTIVATION_GATE_SCHEMA_VERSION = "care-v6-activation-gate-v1"
DEPLOYMENT_VERSION_RULE = "immutable-model-deployment-id-v1"
_EVALUATION_SUITE_SCHEMA_VERSION = "care-v6-evaluation-suite-v1"

ANOMALY_INPUT_REQUIRED = frozenset(
    {
        "turbine_id",
        "dataset_version",
        "farm",
        "event_id",
        "benchmark_replay_run_id",
        "feature_window_start",
        "feature_window_end",
        "feature_start_sequence",
        "feature_end_sequence",
        "signals",
        "feature_set_version",
        "quality_rule_version",
    }
)
ANOMALY_OUTPUT_REQUIRED = frozenset(
    {
        "anomaly_score",
        "binary_prediction",
        "component",
        "model_id",
        "model_version",
        "deployment_id",
        "deployment_version",
        "threshold_policy_version",
        "threshold_policy_sha256",
        "threshold_policy",
        "threshold_value",
        "threshold_comparison",
        "feature_window_start",
        "feature_window_end",
        "feature_start_sequence",
        "feature_end_sequence",
        "feature_set_version",
        "evidence_artifact_ref",
        "benchmark_replay_run_id",
    }
)
FORBIDDEN_ANOMALY_FIELDS = frozenset(
    {
        "failure_probability_30d",
        "remaining_useful_life_days",
        "rul",
        "ground_truth",
        "event_label",
        "failure_type",
    }
)


class CareAnomalyError(ValueError):
    """Raised when the CARE anomaly runtime would violate its governed contract."""


def _verify_governed_evaluation_artifact(artifact: Mapping[str, Any]) -> None:
    if artifact.get("schema_version") == _EVALUATION_SUITE_SCHEMA_VERSION:
        from windops_backend.benchmarks.care.evaluation_artifact import (
            verify_evaluation_suite_artifact,
        )

        verify_evaluation_suite_artifact(artifact)
        return
    verify_evaluation_artifact(artifact)


def _nonempty(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise CareAnomalyError(f"{field_name} cannot be empty")
    return normalized


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CareAnomalyError(f"{field_name} must include an explicit timezone")
    if value.utcoffset() != timedelta(0):
        raise CareAnomalyError(f"{field_name} must be normalized to UTC")
    return value.astimezone(UTC)


def _finite(value: float, *, field_name: str) -> float:
    if isinstance(value, bool) or not math.isfinite(value):
        raise CareAnomalyError(f"{field_name} must be a finite number")
    return value


def _require_schema_fields(
    schema: Mapping[str, Any],
    required_fields: frozenset[str],
    *,
    label: str,
) -> None:
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise CareAnomalyError(f"{label} schema must have a string required list")
    if not isinstance(properties, Mapping):
        raise CareAnomalyError(f"{label} schema must declare properties")
    missing_required = sorted(required_fields.difference(required))
    missing_properties = sorted(required_fields.difference(properties))
    if missing_required or missing_properties:
        raise CareAnomalyError(
            f"{label} schema is missing canonical fields: "
            f"required={missing_required}, properties={missing_properties}"
        )


def validate_anomaly_model_schemas(
    input_schema: Mapping[str, Any],
    output_schema: Mapping[str, Any],
) -> None:
    """Validate the conditional registration contract for a CARE anomaly model."""

    _require_schema_fields(input_schema, ANOMALY_INPUT_REQUIRED, label="anomaly input")
    _require_schema_fields(output_schema, ANOMALY_OUTPUT_REQUIRED, label="anomaly output")
    output_properties = output_schema.get("properties", {})
    output_required = output_schema.get("required", [])
    forbidden = FORBIDDEN_ANOMALY_FIELDS.intersection(
        set(output_properties).union(str(item) for item in output_required)
    )
    if forbidden:
        raise CareAnomalyError(
            f"anomaly output must not fabricate predictive/RUL or truth fields: {sorted(forbidden)}"
        )


def canonical_anomaly_input_schema() -> dict[str, Any]:
    signal_properties: dict[str, Any] = {
        "source_event_id": {"type": "string"},
        "source_sequence": {"type": "integer", "minimum": 0},
        "observed_at": {"type": "string", "format": "date-time"},
        "variable": {"type": "string"},
        "value": {"type": "number"},
        "unit": {"type": "string"},
        "quality": {"enum": ["good", "uncertain", "bad"]},
        "quality_code": {"type": ["string", "null"]},
        "quality_mask_refs": {"type": "array", "items": {"type": "string"}},
    }
    properties: dict[str, Any] = {
        "turbine_id": {"type": "string"},
        "dataset_version": {"const": DATASET_VERSION},
        "farm": {"enum": ["A", "B", "C"]},
        "event_id": {"type": "integer", "minimum": 0, "maximum": 94},
        "benchmark_replay_run_id": {"type": "string"},
        "feature_window_start": {"type": "string", "format": "date-time"},
        "feature_window_end": {"type": "string", "format": "date-time"},
        "feature_start_sequence": {"type": "integer", "minimum": 0},
        "feature_end_sequence": {"type": "integer", "minimum": 0},
        "signals": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(signal_properties),
                "properties": signal_properties,
            },
        },
        "feature_set_version": {"type": "string"},
        "quality_rule_version": {"type": "string"},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def canonical_anomaly_output_schema() -> dict[str, Any]:
    properties: dict[str, Any] = {
        "schema_version": {"const": ANOMALY_PREDICTION_SCHEMA_VERSION},
        "prediction_kind": {"const": "anomaly"},
        "anomaly_score": {"type": "number", "minimum": 0, "maximum": 1},
        "binary_prediction": {"type": "boolean"},
        "component": {"type": "string", "minLength": 1},
        "model_id": {"type": "string"},
        "model_version": {"type": "string"},
        "deployment_id": {"type": "string"},
        "deployment_version": {"type": "string"},
        "deployment_version_rule": {"const": DEPLOYMENT_VERSION_RULE},
        "threshold_policy_version": {"type": "string"},
        "threshold_policy_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "threshold_policy": {"type": "object"},
        "threshold_value": {"type": "number"},
        "threshold_comparison": {"const": "strict-greater-than"},
        "feature_window_start": {"type": "string", "format": "date-time"},
        "feature_window_end": {"type": "string", "format": "date-time"},
        "feature_start_sequence": {"type": "integer", "minimum": 0},
        "feature_end_sequence": {"type": "integer", "minimum": 0},
        "feature_set_version": {"type": "string"},
        "quality_rule_version": {"type": "string"},
        "evidence_artifact_ref": {
            "type": "object",
            "additionalProperties": False,
            "required": ["uri", "sha256"],
            "properties": {
                "uri": {"type": "string"},
                "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
        },
        "benchmark_replay_run_id": {"type": "string"},
        "dataset_version": {"const": DATASET_VERSION},
        "farm": {"enum": ["A", "B", "C"]},
        "event_id": {"type": "integer", "minimum": 0, "maximum": 94},
        "online_turbine_id": {"type": "string"},
        "observed_at_time_claim": {"const": SYNTHETIC_TIME_CLAIM},
        "prediction_truth_present": {"const": False},
        "anomaly_prediction_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    uri: str
    sha256: str

    def __post_init__(self) -> None:
        uri = _nonempty(self.uri, field_name="artifact URI")
        if not (uri.startswith("minio://") or uri.startswith("https://")):
            raise CareAnomalyError("artifact URI must use minio:// or https://")
        digest = self.sha256.lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise CareAnomalyError("artifact sha256 must be 64 hexadecimal characters")
        object.__setattr__(self, "uri", uri)
        object.__setattr__(self, "sha256", digest)

    def to_document(self) -> dict[str, str]:
        return {"uri": self.uri, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class AnomalyFeatureWindow:
    identity: ReplayWindowIdentity
    feature_window_start: datetime
    feature_window_end: datetime
    feature_start_sequence: int
    feature_end_sequence: int
    feature_set_version: str
    quality_rule_version: str
    signals: tuple[dict[str, Any], ...]

    @classmethod
    def from_replay_samples(
        cls,
        samples: Sequence[Mapping[str, Any]],
        *,
        feature_set_version: str,
        quality_rule_version: str,
    ) -> AnomalyFeatureWindow:
        identity = validate_replay_window(samples)
        _nonempty(feature_set_version, field_name="feature_set_version")
        _nonempty(quality_rule_version, field_name="quality_rule_version")
        if not samples:
            raise CareAnomalyError("anomaly feature window cannot be empty")
        records: list[dict[str, Any]] = []
        sequences: list[int] = []
        observed_times: list[datetime] = []
        event_ids: set[str] = set()
        for sample in samples:
            source_event_id = sample.get("source_event_id")
            sequence = sample.get("source_sequence")
            observed_at = sample.get("observed_at")
            variable = sample.get("variable")
            value = sample.get("value")
            quality = sample.get("quality")
            unit = sample.get("unit")
            quality_code = sample.get("quality_code")
            attributes = sample.get("attributes")
            if (
                not isinstance(source_event_id, str)
                or isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or not isinstance(observed_at, str)
                or not isinstance(variable, str)
                or isinstance(value, bool)
                or not isinstance(value, int | float)
                or quality not in {"good", "uncertain", "bad"}
                or not isinstance(unit, str)
                or (quality_code is not None and not isinstance(quality_code, str))
                or not isinstance(attributes, Mapping)
            ):
                raise CareAnomalyError("replay sample cannot form a governed anomaly feature")
            quality_mask_refs = attributes.get("quality_mask_refs", [])
            if not isinstance(quality_mask_refs, list) or not all(
                isinstance(item, str) for item in quality_mask_refs
            ):
                raise CareAnomalyError("feature quality mask references must be strings")
            try:
                parsed_time = datetime.fromisoformat(observed_at)
            except ValueError as exc:
                raise CareAnomalyError("feature observed_at is not ISO-8601") from exc
            parsed_time = _utc(parsed_time, field_name="feature observed_at")
            _finite(float(value), field_name="feature value")
            if source_event_id in event_ids:
                raise CareAnomalyError("anomaly feature window contains a duplicate source event")
            event_ids.add(source_event_id)
            sequences.append(sequence)
            observed_times.append(parsed_time)
            records.append(
                {
                    "source_event_id": source_event_id,
                    "source_sequence": sequence,
                    "observed_at": parsed_time.isoformat(),
                    "variable": variable,
                    "value": float(value),
                    "unit": unit,
                    "quality": quality,
                    "quality_code": quality_code,
                    "quality_mask_refs": list(quality_mask_refs),
                }
            )
        if sequences != sorted(sequences):
            raise CareAnomalyError("anomaly feature samples must be ordered by source sequence")
        if observed_times != sorted(observed_times):
            raise CareAnomalyError("anomaly feature samples must be ordered by synthetic time")
        return cls(
            identity=identity,
            feature_window_start=min(observed_times),
            feature_window_end=max(observed_times),
            feature_start_sequence=min(sequences),
            feature_end_sequence=max(sequences),
            feature_set_version=feature_set_version,
            quality_rule_version=quality_rule_version,
            signals=tuple(records),
        )

    def to_model_input(self) -> dict[str, Any]:
        return {
            "turbine_id": self.identity.online_turbine_id,
            "dataset_version": self.identity.dataset_version,
            "farm": self.identity.farm,
            "event_id": self.identity.event_id,
            "benchmark_replay_run_id": self.identity.benchmark_replay_run_id,
            "feature_window_start": self.feature_window_start.isoformat(),
            "feature_window_end": self.feature_window_end.isoformat(),
            "feature_start_sequence": self.feature_start_sequence,
            "feature_end_sequence": self.feature_end_sequence,
            "signals": [dict(item) for item in self.signals],
            "feature_set_version": self.feature_set_version,
            "quality_rule_version": self.quality_rule_version,
        }


@dataclass(frozen=True, slots=True)
class AnomalyRuntimeContext:
    model_id: str
    model_version: str
    deployment_id: str
    deployment_version: str
    threshold_policy: ThresholdPolicy
    evidence_artifact: ArtifactReference

    def __post_init__(self) -> None:
        for name, value in (
            ("model_id", self.model_id),
            ("model_version", self.model_version),
            ("deployment_id", self.deployment_id),
            ("deployment_version", self.deployment_version),
        ):
            _nonempty(value, field_name=name)


def build_governed_anomaly_output(
    raw_output: Mapping[str, Any],
    window: AnomalyFeatureWindow,
    context: AnomalyRuntimeContext,
) -> dict[str, Any]:
    reserved = ANOMALY_OUTPUT_REQUIRED.difference(
        {"anomaly_score", "binary_prediction", "component"}
    )
    collisions = reserved.intersection(raw_output)
    forbidden = FORBIDDEN_ANOMALY_FIELDS.intersection(raw_output)
    if collisions:
        raise CareAnomalyError(
            f"inference response attempted to forge provenance: {sorted(collisions)}"
        )
    if forbidden:
        raise CareAnomalyError(f"anomaly response contains forbidden fields: {sorted(forbidden)}")
    score = raw_output.get("anomaly_score")
    binary = raw_output.get("binary_prediction")
    component = raw_output.get("component")
    if isinstance(score, bool) or not isinstance(score, int | float):
        raise CareAnomalyError("anomaly_score must be numeric")
    score = _finite(float(score), field_name="anomaly_score")
    if not 0 <= score <= 1:
        raise CareAnomalyError("anomaly_score must be within 0..1")
    if type(binary) is not bool:
        raise CareAnomalyError("binary_prediction must be a boolean")
    if binary != (score > context.threshold_policy.value):
        raise CareAnomalyError("binary_prediction disagrees with the strict threshold policy")
    if not isinstance(component, str):
        raise CareAnomalyError("component must be a string or the controlled 'unknown' value")
    component = _nonempty(component, field_name="component")
    threshold_document = context.threshold_policy.to_dict()
    payload: dict[str, Any] = {
        **dict(raw_output),
        "anomaly_score": score,
        "binary_prediction": binary,
        "component": component,
        "model_id": context.model_id,
        "model_version": context.model_version,
        "deployment_id": context.deployment_id,
        "deployment_version": context.deployment_version,
        "deployment_version_rule": DEPLOYMENT_VERSION_RULE,
        "threshold_policy_version": context.threshold_policy.version,
        "threshold_policy_sha256": threshold_document["threshold_policy_sha256"],
        "threshold_policy": threshold_document,
        "threshold_value": context.threshold_policy.value,
        "threshold_comparison": "strict-greater-than",
        "feature_window_start": window.feature_window_start.isoformat(),
        "feature_window_end": window.feature_window_end.isoformat(),
        "feature_start_sequence": window.feature_start_sequence,
        "feature_end_sequence": window.feature_end_sequence,
        "feature_set_version": window.feature_set_version,
        "quality_rule_version": window.quality_rule_version,
        "evidence_artifact_ref": context.evidence_artifact.to_document(),
        "benchmark_replay_run_id": window.identity.benchmark_replay_run_id,
        "dataset_version": window.identity.dataset_version,
        "farm": window.identity.farm,
        "event_id": window.identity.event_id,
        "online_turbine_id": window.identity.online_turbine_id,
        "observed_at_time_claim": SYNTHETIC_TIME_CLAIM,
        "prediction_truth_present": False,
    }
    envelope = {
        "schema_version": ANOMALY_PREDICTION_SCHEMA_VERSION,
        "prediction_kind": "anomaly",
        **payload,
    }
    return {**envelope, "anomaly_prediction_sha256": _sha256_json(envelope)}


def verify_governed_anomaly_output(output: Mapping[str, Any]) -> None:
    actual = output.get("anomaly_prediction_sha256")
    if not isinstance(actual, str):
        raise CareAnomalyError("anomaly prediction is missing its content hash")
    unsigned = {key: value for key, value in output.items() if key != "anomaly_prediction_sha256"}
    if _sha256_json(unsigned) != actual:
        raise CareAnomalyError("anomaly prediction content hash mismatch")
    if (
        output.get("schema_version") != ANOMALY_PREDICTION_SCHEMA_VERSION
        or output.get("prediction_kind") != "anomaly"
        or output.get("dataset_version") != DATASET_VERSION
        or output.get("prediction_truth_present") is not False
    ):
        raise CareAnomalyError("anomaly prediction envelope has invalid semantics")
    forbidden = FORBIDDEN_ANOMALY_FIELDS.intersection(output)
    if forbidden:
        raise CareAnomalyError(f"anomaly prediction contains forbidden fields: {sorted(forbidden)}")
    score = output.get("anomaly_score")
    binary = output.get("binary_prediction")
    if isinstance(score, bool) or not isinstance(score, int | float) or type(binary) is not bool:
        raise CareAnomalyError("anomaly prediction has invalid score/binary types")
    threshold = output.get("threshold_value")
    threshold_policy = output.get("threshold_policy")
    if not isinstance(threshold_policy, Mapping):
        raise CareAnomalyError("anomaly prediction has no self-contained threshold policy")
    threshold_policy_hash = threshold_policy.get("threshold_policy_sha256")
    unsigned_policy = {
        key: value for key, value in threshold_policy.items() if key != "threshold_policy_sha256"
    }
    if (
        not isinstance(threshold_policy_hash, str)
        or _sha256_json(unsigned_policy) != threshold_policy_hash
        or output.get("threshold_policy_sha256") != threshold_policy_hash
        or output.get("threshold_policy_version") != threshold_policy.get("version")
        or threshold_policy.get("comparison") != "strict-greater-than"
        or threshold_policy.get("prediction_truth_used") is not False
        or threshold_policy.get("value") != threshold
    ):
        raise CareAnomalyError("anomaly prediction threshold policy is inconsistent")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, int | float)
        or output.get("threshold_comparison") != "strict-greater-than"
        or binary != (float(score) > float(threshold))
    ):
        raise CareAnomalyError("anomaly prediction violates its strict threshold semantics")
    component = output.get("component")
    if not isinstance(component, str) or not component.strip():
        raise CareAnomalyError("anomaly prediction has an invalid component")
    evidence = output.get("evidence_artifact_ref")
    if not isinstance(evidence, Mapping):
        raise CareAnomalyError("anomaly prediction has no governed evidence reference")
    ArtifactReference(str(evidence.get("uri", "")), str(evidence.get("sha256", "")))
    for field_name in ANOMALY_OUTPUT_REQUIRED:
        if field_name not in output:
            raise CareAnomalyError(f"anomaly prediction is missing {field_name}")
