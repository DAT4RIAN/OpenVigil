"""Auditable hypotheses with frozen source cards and independent human review."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.model_base import JSON_VALUE, Base, utcnow
from windops_backend.model_structural import StructuralAssetScope


class EngineeringClaim(StructuralAssetScope, Base):
    __tablename__ = "engineering_claims"
    __table_args__ = (
        ForeignKeyConstraint(
            ["component_id", "turbine_id"], ["tower_components.id", "tower_components.turbine_id"]
        ),
        CheckConstraint("revision >= 1", name="ck_engineering_claim_revision"),
        CheckConstraint(
            "claim_kind IN ('screening_finding','retest_recommendation','procedure_guidance')",
            name="ck_engineering_claim_kind",
        ),
        CheckConstraint(
            "review_status IN ('pending','approved','rejected','withdrawn')",
            name="ck_engineering_claim_review",
        ),
        CheckConstraint("valid_until > created_at", name="ck_engineering_claim_expiry"),
        Index("ix_engineering_claim_mission", "mission_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    component_id: Mapped[str] = mapped_column(String(36), nullable=False)
    claim_kind: Mapped[str] = mapped_column(String(48), nullable=False)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    applicability: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    evidence_cards: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, nullable=False)
    missing_evidence: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(160))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(Text)


class EngineeringClaimReview(Base):
    __tablename__ = "engineering_claim_reviews"
    __table_args__ = (
        Index("ix_engineering_claim_review_history", "claim_id", "created_at"),
        UniqueConstraint("claim_id", "claim_revision", name="uq_engineering_claim_review_revision"),
        CheckConstraint("claim_revision >= 2", name="ck_engineering_review_revision"),
        CheckConstraint(
            "action IN ('approve','reject','withdraw')", name="ck_engineering_review_action"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    claim_id: Mapped[str] = mapped_column(ForeignKey("engineering_claims.id"), nullable=False)
    claim_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
