"""Controlled structural review contracts; no operating or tensioning authority."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from windops_backend.schema_engineering_claim import EngineeringEvidenceReference
from windops_backend.schema_operations import TaskCompletionRequest


class ForceAcceptanceCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_kn: float = Field(gt=0, allow_inf_nan=False)
    maximum_kn: float = Field(gt=0, allow_inf_nan=False)
    procedure: EngineeringEvidenceReference

    @model_validator(mode="after")
    def controlled_bounds(self) -> "ForceAcceptanceCriteria":
        if self.maximum_kn <= self.minimum_kn:
            raise ValueError("maximum force must exceed minimum force")
        if self.procedure.kind != "knowledge_passage" or self.procedure.relation != "supports":
            raise ValueError("acceptance bounds require a supporting controlled passage quote")
        return self


class StructuralMissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turbine_id: str = Field(min_length=3, max_length=32)
    component_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=3, max_length=240)
    scenario: Literal["modal_frequency_review", "prestress_retest"]
    source_id: str = Field(min_length=1, max_length=36)
    baseline_id: str | None = Field(default=None, min_length=1, max_length=36)
    previous_prestress_id: str | None = Field(default=None, min_length=1, max_length=36)
    force_acceptance: ForceAcceptanceCriteria | None = None
    planning_duration_hours: float = Field(gt=0, le=24, allow_inf_nan=False)

    @model_validator(mode="after")
    def scenario_inputs(self) -> "StructuralMissionCreate":
        if self.scenario == "modal_frequency_review":
            if self.previous_prestress_id or self.force_acceptance:
                raise ValueError("modal review cannot use direct-force acceptance inputs")
        elif self.baseline_id:
            raise ValueError("direct-force retest cannot use a modal baseline")
        return self


class StructuralScreeningOutput(BaseModel):
    """A scoped interpretation of measured evidence, never a damage probability."""

    model_config = ConfigDict(extra="forbid")

    component: str
    failure_mode: Literal["structural_screening", "insufficient_structural_evidence"]
    confidence: None = None
    damage_probability: None = None
    conclusion: str = Field(min_length=3, max_length=4000)
    evidence_refs: list[str] = Field(min_length=1, max_length=50)
    missing_evidence: list[str] = Field(default_factory=list, max_length=20)
    field_qualification: Literal["unverified"] = "unverified"
    permitted_use: Literal["human_review_and_retest_proposal"] = "human_review_and_retest_proposal"


class StructuralHealthReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_mission_revision: int = Field(ge=1)
    action: Literal["resolve_review", "requires_followup"]
    reason: str = Field(min_length=3, max_length=4000)
    hypothesis_outcome: Literal["supported", "not_supported", "inconclusive"]


class StructuralCaseReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    action: Literal["approve", "reject"]
    reason: str = Field(min_length=3, max_length=4000)


class StructuralRetestSubmission(TaskCompletionRequest):
    model_config = ConfigDict(extra="forbid")
    expected_mission_revision: int = Field(ge=1)


class StructuralWorkflowContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_id: str
    turbine_id: str
    component_id: str
    scenario: Literal["modal_frequency_review", "prestress_retest"]
    contract_version: str
    source_refs: list[EngineeringEvidenceReference]
    evidence_cards: list[dict[str, Any]]
    comparison: dict[str, Any]
    missing_evidence: list[str]
    context_sha256: str
    created_at: datetime
