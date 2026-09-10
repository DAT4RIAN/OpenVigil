from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, Self

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from windops_backend.benchmarks.care.anomaly import (
    CareAnomalyError,
    validate_anomaly_model_schemas,
)
from windops_backend.schema_operations import ModelArtifactContentType

# Owned declarations follow; their order is part of the compatibility contract.
BENCHMARK_SHA256_PATTERN = r"^[0-9a-f]{64}$"
BENCHMARK_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$"
MAX_BENCHMARK_EXTENSION_BYTES = 65_536
MAX_BENCHMARK_EXTENSION_NODES = 2_048
MAX_BENCHMARK_EXTENSION_DEPTH = 8


def _validate_benchmark_extension(value: dict[str, Any], *, label: str) -> dict[str, Any]:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite JSON data") from exc
    if len(encoded) > MAX_BENCHMARK_EXTENSION_BYTES:
        raise ValueError(f"{label} exceeds {MAX_BENCHMARK_EXTENSION_BYTES} bytes")
    stack: list[tuple[object, int]] = [(value, 0)]
    node_count = 0
    while stack:
        node, depth = stack.pop()
        node_count += 1
        if node_count > MAX_BENCHMARK_EXTENSION_NODES:
            raise ValueError(f"{label} exceeds {MAX_BENCHMARK_EXTENSION_NODES} JSON nodes")
        if depth > MAX_BENCHMARK_EXTENSION_DEPTH:
            raise ValueError(f"{label} exceeds JSON depth {MAX_BENCHMARK_EXTENSION_DEPTH}")
        if isinstance(node, dict):
            if not all(isinstance(key, str) and key for key in node):
                raise ValueError(f"{label} object keys must be non-empty strings")
            stack.extend((item, depth + 1) for item in node.values())
        elif isinstance(node, list):
            stack.extend((item, depth + 1) for item in node)
    return value


def _require_explicit_timezone(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include an explicit timezone")
    return value


class ModelArtifactUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
    file_name: str = Field(min_length=1, max_length=240)
    content_type: ModelArtifactContentType
    artifact_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class ModelRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
    name: str = Field(min_length=3, max_length=240)
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
    kind: Literal["anomaly", "predictive", "health", "retrieval", "report"]
    description: str = Field(default="", max_length=4000)
    artifact_uri: str = Field(min_length=16, max_length=1024)
    artifact_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    content_type: ModelArtifactContentType
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    metrics: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input_schema", "output_schema")
    @classmethod
    def validate_json_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as exc:
            raise ValueError(f"invalid JSON Schema: {exc.message}") from exc
        if value.get("type") != "object":
            raise ValueError("model contracts must describe JSON objects")
        if value.get("additionalProperties") is not False:
            raise ValueError("model contracts must reject additional properties")
        return value

    @model_validator(mode="after")
    def validate_kind_contract(self) -> ModelRegisterRequest:
        if self.kind == "predictive":
            required_input = {"turbine_id", "observed_at", "signals"}
            required_output = {
                "component",
                "failure_probability_30d",
                "remaining_useful_life_days",
                "anomaly_score",
                "primary_finding",
            }
            if not required_input.issubset(set(self.input_schema.get("required", []))):
                raise ValueError("predictive input schema is missing canonical required fields")
            if not required_output.issubset(set(self.output_schema.get("required", []))):
                raise ValueError("predictive output schema is missing canonical required fields")
        elif self.kind == "anomaly":
            try:
                validate_anomaly_model_schemas(self.input_schema, self.output_schema)
            except CareAnomalyError as exc:
                raise ValueError(str(exc)) from exc
        return self


class BenchmarkDatasetVersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    tenant_id: str = Field(min_length=3, max_length=64)
    dataset_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$")
    status: Literal["registered", "importing", "ready", "failed"] = "registered"
    source_uri: str = Field(min_length=8, max_length=1024)
    manifest_uri: str = Field(min_length=8, max_length=1024)
    manifest_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    content_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    source_archive_md5: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    source_archive_sha256: str | None = Field(default=None, pattern=BENCHMARK_SHA256_PATTERN)
    size_bytes: int = Field(ge=0)
    file_count: int = Field(ge=0, le=100_000)
    license_name: str = Field(min_length=3, max_length=160)
    license_url: str = Field(min_length=8, max_length=1024)
    doi: str = Field(min_length=3, max_length=256)
    citation: str = Field(min_length=3, max_length=4000)
    attribution: dict[str, Any] = Field(default_factory=dict)

    @field_validator("attribution")
    @classmethod
    def validate_attribution(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_benchmark_extension(value, label="benchmark attribution")


class BenchmarkFileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    dataset_version_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    file_kind: Literal["event", "event_info", "feature_description", "archive", "manifest"]
    relative_path: str = Field(min_length=1, max_length=512)
    farm: Literal["A", "B", "C"] | None = None
    event_id: int | None = Field(default=None, ge=0, le=94)
    size_bytes: int = Field(ge=0)
    row_count: int = Field(ge=0)
    schema_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    content_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_benchmark_extension(value, label="benchmark file metadata")

    @model_validator(mode="after")
    def validate_event_identity(self) -> Self:
        if self.file_kind == "event" and (self.farm is None or self.event_id is None):
            raise ValueError("event files require farm and event_id")
        return self


class BenchmarkEventCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark_event_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    dataset_version_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    source_file_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    event_id: int = Field(ge=0, le=94)
    farm: Literal["A", "B", "C"]
    source_asset_id: str = Field(min_length=1, max_length=64)
    logical_asset_id: str = Field(min_length=3, max_length=64)
    event_label: Literal["anomaly", "normal"]
    first_source_row_id: int = Field(ge=0)
    last_source_row_id: int = Field(ge=0)
    train_row_count: int = Field(ge=0)
    prediction_row_count: int = Field(ge=0)
    event_interval_start: int = Field(ge=0)
    event_interval_end: int = Field(ge=0)
    truth_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("truth_metadata")
    @classmethod
    def validate_truth_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_benchmark_extension(value, label="benchmark truth metadata")

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.last_source_row_id < self.first_source_row_id:
            raise ValueError("last_source_row_id must not precede first_source_row_id")
        if self.event_interval_end < self.event_interval_start:
            raise ValueError("event_interval_end must not precede event_interval_start")
        return self


class BenchmarkFeatureMapCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_map_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    dataset_version_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    mapping_version: str = Field(min_length=3, max_length=64)
    farm: Literal["A", "B", "C"]
    source_column: str = Field(min_length=1, max_length=160)
    canonical_feature: str = Field(min_length=1, max_length=160)
    statistic: str = Field(min_length=1, max_length=32)
    unit: str = Field(min_length=1, max_length=32)
    enabled: bool = False
    semantics: dict[str, Any] = Field(default_factory=dict)

    @field_validator("semantics")
    @classmethod
    def validate_semantics(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_benchmark_extension(value, label="benchmark feature semantics")


class BenchmarkQualityReportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quality_report_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    event_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    quality_rule_version: str = Field(min_length=3, max_length=64)
    feature_set_version: str = Field(min_length=3, max_length=64)
    canonical_content_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    artifact_stage: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    artifact_uri: str = Field(min_length=8, max_length=1024)
    artifact_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    mask_uri: str = Field(min_length=8, max_length=1024)
    mask_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    summary: dict[str, Any] = Field(default_factory=dict)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_benchmark_extension(value, label="benchmark quality summary")


class BenchmarkEvaluationRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_run_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    dataset_version_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    model_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    model_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
    run_kind: Literal["development", "tuning", "final-holdout"]
    protocol_version: str = Field(min_length=3, max_length=96)
    farm: Literal["A", "B", "C"] | None = None
    feature_set_version: str = Field(min_length=3, max_length=64)
    quality_rule_version: str = Field(min_length=3, max_length=64)
    threshold_policy_version: str = Field(min_length=3, max_length=64)
    threshold_policy_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    random_seed: int = Field(ge=0, le=2_147_483_647)
    input_identity_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    requested_event_count: int = Field(ge=1, le=95)
    extension_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("extension_data")
    @classmethod
    def validate_extension_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_benchmark_extension(value, label="benchmark evaluation extension_data")


class BenchmarkEventResultCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_result_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    evaluation_run_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    event_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    status: Literal["scored", "failed", "unscorable"]
    scorable: bool
    anomaly_detected: bool | None = None
    care_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    coverage_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    accuracy_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    reliability_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    earliness_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    prediction_artifact_uri: str | None = Field(default=None, min_length=8, max_length=1024)
    prediction_artifact_sha256: str | None = Field(default=None, pattern=BENCHMARK_SHA256_PATTERN)
    failure_code: str | None = Field(default=None, min_length=1, max_length=96)
    result_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def validate_details(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_benchmark_extension(value, label="benchmark event-result details")

    @model_validator(mode="after")
    def validate_result_state(self) -> Self:
        if self.status == "scored":
            if not self.scorable:
                raise ValueError("scored event results require scorable=true")
        elif self.scorable or self.care_score is not None:
            raise ValueError("failed/unscorable event results cannot carry care_score")
        artifact_fields = (self.prediction_artifact_uri, self.prediction_artifact_sha256)
        if (artifact_fields[0] is None) != (artifact_fields[1] is None):
            raise ValueError("prediction artifact URI and SHA-256 must be provided together")
        return self


class BenchmarkMetricSnapshotCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_snapshot_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    evaluation_run_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    metric_name: str = Field(pattern=r"^[a-z][a-z0-9._-]{1,95}$")
    protocol_version: str = Field(min_length=3, max_length=96)
    metric_version: str = Field(min_length=1, max_length=64)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=32)
    numerator: float | None = Field(default=None, allow_inf_nan=False)
    denominator: float | None = Field(default=None, allow_inf_nan=False)
    is_release_metric: bool = False
    threshold_value: float | None = Field(default=None, allow_inf_nan=False)
    threshold_direction: Literal["gte", "lte", "eq"] | None = None
    passed: bool | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def validate_details(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_benchmark_extension(value, label="benchmark metric details")

    @model_validator(mode="after")
    def validate_release_metric(self) -> Self:
        if self.is_release_metric and (
            self.threshold_value is None or self.threshold_direction is None or self.passed is None
        ):
            raise ValueError("release metrics require threshold value/direction and passed")
        return self


class BenchmarkReplayRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark_replay_run_id: str = Field(pattern=r"^[a-z0-9]{8}$")
    dataset_version_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    event_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    source_asset_id: str = Field(min_length=1, max_length=64)
    logical_asset_id: str = Field(min_length=3, max_length=64)
    online_turbine_id: str = Field(min_length=3, max_length=32)
    farm: Literal["A", "B", "C"]
    source_event_number: int = Field(ge=0, le=94)
    replay_mode: Literal["live-relative", "historical-fixed"]
    speed: float = Field(gt=0, allow_inf_nan=False)
    status: Literal["pending", "running", "cancelling", "cancelled", "completed", "failed"]
    replay_anchor_at: datetime
    time_rule_version: str = Field(min_length=3, max_length=64)
    sequence_rule_version: str = Field(min_length=3, max_length=64)
    source_event_id_rule_version: str = Field(min_length=3, max_length=64)
    selected_variables: list[dict[str, Any]] = Field(min_length=1, max_length=1024)
    window_start_row_id: int = Field(ge=0)
    window_end_row_id: int = Field(ge=0)
    checkpoint: dict[str, Any]
    checkpoint_revision: int = Field(ge=0)
    checkpoint_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    model_id: str | None = Field(default=None, pattern=BENCHMARK_ID_PATTERN)
    model_version: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
    deployment_id: str | None = Field(default=None, min_length=36, max_length=36)
    threshold_policy_version: str | None = Field(default=None, min_length=3, max_length=64)
    threshold_policy_sha256: str | None = Field(default=None, pattern=BENCHMARK_SHA256_PATTERN)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancelled_by: str | None = Field(default=None, min_length=1, max_length=160)
    error: str | None = Field(default=None, min_length=1, max_length=4000)

    @field_validator("replay_anchor_at", "started_at", "finished_at")
    @classmethod
    def validate_timezone(cls, value: datetime | None, info: Any) -> datetime | None:
        if value is None:
            return None
        return _require_explicit_timezone(value, label=info.field_name)

    @field_validator("checkpoint")
    @classmethod
    def validate_checkpoint(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_benchmark_extension(value, label="benchmark replay checkpoint")

    @field_validator("selected_variables")
    @classmethod
    def validate_selected_variables(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _validate_benchmark_extension({"selected_variables": value}, label="selected variables")
        return value

    @model_validator(mode="after")
    def validate_replay_state(self) -> Self:
        if self.window_end_row_id < self.window_start_row_id:
            raise ValueError("window_end_row_id must not precede window_start_row_id")
        if (self.model_id is None) != (self.model_version is None):
            raise ValueError("model_id and model_version must be provided together")
        if self.deployment_id is not None and self.model_id is None:
            raise ValueError("deployment_id requires model_id and model_version")
        if self.status in {"cancelled", "completed", "failed"} and self.finished_at is None:
            raise ValueError("terminal replay runs require finished_at")
        if self.status == "cancelled" and self.cancelled_by is None:
            raise ValueError("cancelled replay runs require cancelled_by")
        if self.status == "failed" and self.error is None:
            raise ValueError("failed replay runs require error")
        return self


class AnomalyAlertPolicyStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_state_id: str = Field(pattern=BENCHMARK_ID_PATTERN)
    deployment_id: str = Field(min_length=36, max_length=36)
    turbine_id: str = Field(min_length=3, max_length=32)
    component: str = Field(min_length=1, max_length=80)
    policy_version: str = Field(min_length=3, max_length=64)
    policy_sha256: str = Field(pattern=BENCHMARK_SHA256_PATTERN)
    phase: Literal["normal", "triggering", "active", "recovering", "cooldown"]
    consecutive_trigger_count: int = Field(ge=0)
    consecutive_recovery_count: int = Field(ge=0)
    cooldown_until: datetime | None = None
    last_prediction_id: str | None = Field(default=None, min_length=36, max_length=36)
    last_prediction_created_at: datetime | None = None
    dedup_key: str | None = Field(default=None, min_length=1, max_length=128)
    policy_document: dict[str, Any]
    state_document: dict[str, Any]
    revision: int = Field(ge=0)

    @field_validator("cooldown_until", "last_prediction_created_at")
    @classmethod
    def validate_timezone(cls, value: datetime | None, info: Any) -> datetime | None:
        if value is None:
            return None
        return _require_explicit_timezone(value, label=info.field_name)

    @field_validator("policy_document", "state_document")
    @classmethod
    def validate_documents(cls, value: dict[str, Any], info: Any) -> dict[str, Any]:
        return _validate_benchmark_extension(value, label=info.field_name)


class BenchmarkTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version_id: str
    event_id: str
    model_id: str
    model_version: str
    evaluation_run_id: str
    replay_run_id: str
    prediction_id: str
    alarm_id: str
    source_event_id: str | None
    metric_snapshot_ids: list[str] = Field(max_length=256)


class BenchmarkArtifactExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    export_format: Literal["json", "csv"] = Field(alias="format")
    distribution: Literal["internal", "external"]
    include_truth: bool = Field(default=False, alias="includeTruth")
    changes_made: str = Field(alias="changesMade", min_length=8, max_length=1000)
    expected_source_artifact_sha256: str = Field(
        alias="expectedSourceArtifactSha256", pattern=r"^[0-9a-f]{64}$"
    )
    attribution_confirmed: bool = Field(default=False, alias="attributionConfirmed")
    license_link_confirmed: bool = Field(default=False, alias="licenseLinkConfirmed")
    share_alike_confirmed: bool = Field(default=False, alias="shareAlikeConfirmed")
    legal_review_reference: str | None = Field(
        default=None, alias="legalReviewReference", min_length=3, max_length=160
    )


class AnomalyReplayInferenceRequest(BaseModel):
    """Server-resolved inference request; policy and evidence are never client supplied."""

    model_config = ConfigDict(extra="forbid")

    benchmark_replay_run_id: str = Field(pattern=r"^[a-z0-9]{8}$")
    source_row_id: int = Field(ge=0)


class ModelDeploymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{2,95}$")
    stage: Literal["production"] = "production"
    evaluation_gate: dict[str, Any] = Field(default_factory=dict)


class ModelActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    traffic_percent: int = Field(default=100, ge=1, le=100)
    reason: str = Field(min_length=3, max_length=500)


class ModelRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_deployment_id: str = Field(min_length=36, max_length=36)
    reason: str = Field(min_length=3, max_length=500)


class PredictiveRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turbine_ids: list[str] = Field(min_length=1, max_length=64)

    @field_validator("turbine_ids")
    @classmethod
    def unique_turbines(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("turbine_ids must be unique")
        return value
