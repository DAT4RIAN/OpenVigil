"""Governed output contracts shared by provider orchestration and structural policy."""

from typing import Any

from pydantic import BaseModel, Field, model_validator

from windops_backend.schema_operations import (
    MaintenanceAlternative,
    MaintenanceReviewTarget,
    ReviewResult,
)

REVIEW_COMMITTEE_AGENT = "review_committee"


class AlternativeBundle(BaseModel):
    alternatives: list[MaintenanceAlternative] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def validate_governed_choice(self) -> "AlternativeBundle":
        identifiers = [item.alternative_id for item in self.alternatives]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("maintenance alternative IDs must be unique")
        recommended = [item for item in self.alternatives if item.recommended]
        if len(recommended) != 1:
            raise ValueError("exactly one maintenance alternative must be recommended")
        if recommended[0].safety_risk == "critical":
            raise ValueError("a critical-safety-risk alternative cannot be recommended")
        return self


class ReviewBundle(BaseModel):
    reviews: list[ReviewResult] = Field(min_length=5, max_length=5)
    # Legacy review artifacts remain readable without inventing their subject.
    # New generation requires this shared target via schema and post-validation.
    target: MaintenanceReviewTarget | None = None

    @model_validator(mode="after")
    def validate_review_coverage(self) -> "ReviewBundle":
        required = {"engineering", "safety", "economic", "resource", "compliance"}
        observed = [item.review_type for item in self.reviews]
        if set(observed) != required or len(set(observed)) != len(observed):
            raise ValueError("reviews must cover each governed review type exactly once")
        return self


class ReasoningEvaluationError(ValueError):
    pass


def _review_target(public_context: dict[str, Any]) -> MaintenanceReviewTarget:
    try:
        return MaintenanceReviewTarget.model_validate(public_context.get("review_target"))
    except ValueError as exc:
        raise ReasoningEvaluationError("a governed maintenance review target is required") from exc
