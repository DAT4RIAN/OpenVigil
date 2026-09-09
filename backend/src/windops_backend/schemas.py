from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from windops_backend.enums import ApprovalAction


class ScadaSampleIn(BaseModel):
    source_event_id: str = Field(min_length=3, max_length=128)
    turbine_id: str = Field(min_length=3, max_length=32)
    observed_at: datetime
    variable: str = Field(min_length=2, max_length=96)
    value: float
    unit: str = Field(min_length=1, max_length=24)
    quality: Literal["good", "uncertain", "bad"] = "good"
    attributes: dict[str, Any] = Field(default_factory=dict)


class ScadaIngestRequest(BaseModel):
    samples: list[ScadaSampleIn] = Field(min_length=1, max_length=1000)


class IngestResult(BaseModel):
    source_event_id: str
    disposition: Literal["accepted", "duplicate"]
    alarm_id: str | None = None
    mission_id: str | None = None


class ScadaIngestResponse(BaseModel):
    accepted: int
    duplicates: int
    results: list[IngestResult]


class PublicEvidence(BaseModel):
    evidence_id: str
    evidence_type: str
    summary: str
    source_refs: list[str]
    metrics: dict[str, float | str] = Field(default_factory=dict)


class PublicDiagnosis(BaseModel):
    failure_mode: str
    component: str
    confidence: float = Field(ge=0, le=1)
    conclusion: str
    evidence_refs: list[str]


class MaintenanceAlternative(BaseModel):
    alternative_id: str
    title: str
    action: str
    safety_risk: Literal["low", "medium", "high", "critical"]
    estimated_downtime_hours: float = Field(ge=0)
    estimated_cost_cny: float = Field(ge=0)
    recommended: bool = False


class ReviewResult(BaseModel):
    review_type: str
    reviewer_agent: str
    outcome: Literal["pass", "conditional_pass", "fail"]
    public_summary: str
    conditions: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    action: ApprovalAction
    expected_revision: int = Field(ge=1)
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


class StrictTaskMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LubricationTaskMeasurement(StrictTaskMeasurement):
    lubrication_condition: Literal["acceptable", "clean"]
    water_content_ppm: float = Field(ge=0, le=500)


class VibrationTaskMeasurement(StrictTaskMeasurement):
    vibration_rms_mm_s: float = Field(ge=0, le=4.5)
    bpfo_band_energy_pct: float = Field(ge=0, le=10)


class TemperatureTaskMeasurement(StrictTaskMeasurement):
    bearing_temperature_c: float = Field(ge=-40, le=75)


class BorescopeTaskMeasurement(StrictTaskMeasurement):
    defect_severity: Literal["none", "minor"]
    spall_area_mm2: float = Field(ge=0, le=5)


class ClosureTaskMeasurement(StrictTaskMeasurement):
    photo_count: int = Field(ge=3, le=100)
    main_bearing_health_score: float = Field(ge=78, le=100)
    turbine_health_score: float = Field(ge=82, le=100)


TASK_MEASUREMENT_SCHEMAS: dict[int, type[StrictTaskMeasurement]] = {
    1: LubricationTaskMeasurement,
    2: VibrationTaskMeasurement,
    3: TemperatureTaskMeasurement,
    4: BorescopeTaskMeasurement,
    5: ClosureTaskMeasurement,
}


class ErrorBody(BaseModel):
    code: str
    message: str


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AgentExecutionOut(OrmModel):
    id: str
    mission_id: str
    node: str
    agent_role: str
    status: str
    input_refs: dict[str, Any]
    public_output: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    latency_ms: int
    provider: str
    model: str | None
    token_usage: dict[str, Any]
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None
