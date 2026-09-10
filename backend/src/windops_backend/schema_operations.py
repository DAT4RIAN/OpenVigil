from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from windops_backend.enums import ApprovalAction


# Owned declarations follow; their order is part of the compatibility contract.
class ScadaSampleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_event_id: str = Field(min_length=3, max_length=128)
    source_sequence: int | None = Field(default=None, ge=0)
    turbine_id: str = Field(min_length=3, max_length=32)
    observed_at: datetime
    variable: str = Field(min_length=2, max_length=96)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=24)
    quality: Literal["good", "uncertain", "bad"] = "good"
    quality_code: str | None = Field(default=None, min_length=1, max_length=64)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include an explicit timezone")
        return value


class ScadaIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(default="scada-default", min_length=3, max_length=96)
    samples: list[ScadaSampleIn] = Field(min_length=1, max_length=1000)


class IngestResult(BaseModel):
    source_event_id: str
    disposition: Literal["accepted", "duplicate", "quarantined"]
    late: bool = False
    reason_code: str | None = None
    alarm_id: str | None = None
    mission_id: str | None = None


class ScadaIngestResponse(BaseModel):
    accepted: int
    duplicates: int
    quarantined: int
    results: list[IngestResult]


class EamWorkOrderStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str = Field(min_length=1, max_length=160)
    status: str = Field(pattern=r"^[a-z][a-z0-9._-]{1,47}$")
    external_updated_at: datetime

    @field_validator("external_updated_at")
    @classmethod
    def require_external_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("external_updated_at must include an explicit timezone")
        return value


class AlarmCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["acknowledge", "assign", "unassign"]
    expected_revision: int = Field(ge=1)
    reason: str | None = Field(default=None, min_length=3, max_length=500)


class WorkOrderTaskTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=240)
    schema_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    measurement_schema: dict[str, Any]

    @field_validator("measurement_schema")
    @classmethod
    def validate_measurement_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as exc:
            raise ValueError(f"invalid JSON Schema: {exc.message}") from exc
        if value.get("type") != "object":
            raise ValueError("task measurement schema must describe an object")
        if value.get("additionalProperties") is not False:
            raise ValueError("task measurement schema must reject additional properties")
        if not isinstance(value.get("properties"), dict) or not value["properties"]:
            raise ValueError("task measurement schema must declare properties")
        return value


class WorkOrderPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=240)
    priority: Literal["low", "medium", "high", "critical"] = "high"
    required_resource_types: list[str] = Field(min_length=1, max_length=10)
    safety_plan: dict[str, Any]
    tasks: list[WorkOrderTaskTemplate] = Field(min_length=1, max_length=20)
    closure_health_score_field: str = Field(
        default="turbine_health_score", pattern=r"^[a-z][a-z0-9_]{2,63}$"
    )
    healthy_threshold: float = Field(default=80, ge=0, le=100)

    @model_validator(mode="after")
    def validate_closure_contract(self) -> WorkOrderPlan:
        if len(set(self.required_resource_types)) != len(self.required_resource_types):
            raise ValueError("required resource types must be unique")
        closure_properties = self.tasks[-1].measurement_schema.get("properties", {})
        health_contract = closure_properties.get(self.closure_health_score_field)
        if not isinstance(health_contract, dict) or health_contract.get("type") != "number":
            raise ValueError("the final task must define the numeric closure health-score field")
        minimum = health_contract.get("minimum")
        if not isinstance(minimum, int | float) or float(minimum) < self.healthy_threshold:
            raise ValueError(
                "the closure health-score field minimum must meet the healthy threshold"
            )
        return self


class MissionAnalysisProfile(BaseModel):
    """Public, auditable inputs that parameterize a mission analysis."""

    model_config = ConfigDict(extra="forbid")

    component: str = Field(min_length=2, max_length=80)
    primary_variable: str = Field(min_length=2, max_length=96)
    related_variables: list[str] = Field(default_factory=list, max_length=20)
    failure_mode_hint: str = Field(default="", max_length=240)
    knowledge_query: str = Field(min_length=3, max_length=400)
    work_order_plan: WorkOrderPlan | None = None


class MissionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alarm_id: str = Field(min_length=3, max_length=36)
    title: str = Field(min_length=3, max_length=240)
    analysis_profile: MissionAnalysisProfile


class PublicEvidence(BaseModel):
    evidence_id: str
    evidence_type: str
    summary: str
    source_refs: list[str]
    metrics: dict[str, float | str] = Field(default_factory=dict)


class PublicDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_mode: str
    component: str
    confidence: float = Field(ge=0, le=1)
    conclusion: str
    evidence_refs: list[str] = Field(min_length=1, max_length=50)


class MaintenanceAlternative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alternative_id: str
    title: str
    action: str
    safety_risk: Literal["low", "medium", "high", "critical"]
    estimated_downtime_hours: float = Field(ge=0)
    estimated_cost_cny: float = Field(ge=0)
    estimated_energy_loss_mwh: float = Field(ge=0)
    deterioration_risk_percent: float = Field(ge=0, le=100)
    weather_window_id: str | None = None
    required_resources: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=3, max_length=1000)
    recommended: bool = False


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_type: str
    reviewer_agent: str
    outcome: Literal["pass", "conditional_pass", "fail"]
    public_summary: str
    conditions: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    action: ApprovalAction
    expected_revision: int = Field(ge=1)
    selected_alternative_id: str | None = Field(default=None, max_length=64)
    # Accepted for wire compatibility only. The API replaces this value with the
    # authenticated principal before it reaches the audit service.
    approver: str = Field(default="", max_length=160)
    reason: str = Field(min_length=3, max_length=240)
    comment: str = Field(default="", max_length=4000)


class TaskCompletionRequest(BaseModel):
    # Accepted for wire compatibility only; never trusted as an audit actor.
    completed_by: str = Field(default="", max_length=160)
    result: str = Field(min_length=3, max_length=4000)
    artifact_uri: str = Field(min_length=8, max_length=1024)
    artifact_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    measurement: dict[str, Any] = Field(min_length=1)


class ArtifactUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(min_length=1, max_length=240)
    content_type: Literal[
        "application/json",
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain",
        "video/mp4",
    ]
    artifact_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


KnowledgeContentType = Literal[
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]


class KnowledgeDocumentUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
    file_name: str = Field(min_length=1, max_length=240)
    content_type: KnowledgeContentType
    artifact_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class KnowledgeDocumentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
    title: str = Field(min_length=3, max_length=240)
    document_type: str = Field(min_length=2, max_length=64)
    document_version: str = Field(default="1", min_length=1, max_length=32)
    artifact_uri: str = Field(min_length=16, max_length=1024)
    artifact_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    content_type: KnowledgeContentType
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    wind_farm_id: str | None = Field(default=None, min_length=1, max_length=36)
    turbine_id: str | None = Field(default=None, min_length=1, max_length=32)
    data_scope: Literal["knowledge"] = "knowledge"
    metadata: dict[str, Any] = Field(default_factory=dict)


ModelArtifactContentType = Literal[
    "application/json",
    "application/octet-stream",
    "application/onnx",
    "application/zip",
]
