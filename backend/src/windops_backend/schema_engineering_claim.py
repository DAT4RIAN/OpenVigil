from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from windops_backend.schema_structural import Finite, Identity, StructuralRequest

EvidenceKind = Literal["analysis", "modal", "prestress", "baseline", "knowledge_passage"]
EvidenceRelation = Literal["supports", "contradicts", "context"]


class EngineeringEvidenceReference(StructuralRequest):
    kind: EvidenceKind
    source_id: Annotated[str, Field(min_length=1, max_length=64)]
    relation: EvidenceRelation
    quote: Annotated[str, Field(min_length=3, max_length=2000)] | None = None

    @model_validator(mode="after")
    def require_exact_quote(self) -> Self:
        if (self.kind == "knowledge_passage") != (self.quote is not None):
            raise ValueError("only knowledge evidence requires an exact source quote")
        return self


class EngineeringClaimCreate(StructuralRequest):
    turbine_id: Identity
    mission_id: Annotated[str, Field(min_length=1, max_length=40)]
    component_id: Identity
    claim_kind: Literal["screening_finding", "retest_recommendation", "procedure_guidance"]
    conclusion: Annotated[str, Field(min_length=3, max_length=4000)]
    applicability: dict[str, Annotated[str, Field(min_length=1, max_length=320)]] = Field(
        min_length=1, max_length=20
    )
    evidence: list[EngineeringEvidenceReference] = Field(min_length=1, max_length=20)
    missing_evidence: list[Annotated[str, Field(min_length=3, max_length=320)]] = Field(
        default_factory=list, max_length=20
    )
    valid_until: AwareDatetime

    @model_validator(mode="after")
    def unique_evidence(self) -> Self:
        identities = [(item.kind, item.source_id) for item in self.evidence]
        if len(set(identities)) != len(identities):
            raise ValueError("each source can have only one declared relation per claim")
        if not any(item.relation == "supports" for item in self.evidence):
            raise ValueError("a claim requires at least one supporting source")
        return self


class EngineeringClaimReviewRequest(StructuralRequest):
    expected_revision: Annotated[int, Field(ge=1)]
    action: Literal["approve", "reject", "withdraw"]
    reason: Annotated[str, Field(min_length=3, max_length=4000)]


class EvidenceMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: Finite | None
    unit: str


class EngineeringEvidenceCard(BaseModel):
    """Server-built source facts. A relation records a hypothesis, not semantic proof."""

    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    reference: EngineeringEvidenceReference
    tenant_id: str
    wind_farm_id: str
    turbine_id: str
    component_id: str
    time_window: dict[str, datetime | None]
    source: dict[str, Any]
    method: dict[str, Any]
    measurements: list[EvidenceMeasurement]
    quality: dict[str, Any]
    uncertainty: dict[str, Any]
    applicability: dict[str, Any]
    valid_until: datetime | None
    source_fingerprint: str
    engineering_qualification: Literal["unverified"] = "unverified"
