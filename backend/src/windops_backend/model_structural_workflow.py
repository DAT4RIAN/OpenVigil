"""Sidecars preserve the existing mission, work-order and knowledge-case contracts."""

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


class StructuralMissionContext(StructuralAssetScope, Base):
    __tablename__ = "structural_mission_contexts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["component_id", "turbine_id"], ["tower_components.id", "tower_components.turbine_id"]
        ),
        UniqueConstraint("turbine_id", "origin_fingerprint", name="uq_structural_mission_origin"),
        CheckConstraint(
            "scenario IN ('modal_frequency_review','prestress_retest')",
            name="ck_structural_mission_scenario",
        ),
    )
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), primary_key=True)
    component_id: Mapped[str] = mapped_column(String(36), nullable=False)
    scenario: Mapped[str] = mapped_column(String(40), nullable=False)
    origin_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    context_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    frozen_context: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    claim_id: Mapped[str | None] = mapped_column(ForeignKey("engineering_claims.id"))
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StructuralHealthReview(StructuralAssetScope, Base):
    __tablename__ = "structural_health_reviews"
    __table_args__ = (
        UniqueConstraint("work_order_id", "mission_revision", name="uq_structural_health_revision"),
        CheckConstraint(
            "action IN ('resolve_review','requires_followup')", name="ck_structural_health_action"
        ),
        Index("ix_structural_health_history", "work_order_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("structural_mission_contexts.mission_id"), nullable=False
    )
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), nullable=False)
    mission_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    hypothesis_outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    assessment: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StructuralCaseReview(StructuralAssetScope, Base):
    __tablename__ = "structural_case_reviews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected')", name="ck_structural_case_status"
        ),
        CheckConstraint("revision >= 1", name="ck_structural_case_revision"),
    )
    case_id: Mapped[str] = mapped_column(ForeignKey("knowledge_cases.id"), primary_key=True)
    health_review_id: Mapped[str] = mapped_column(
        ForeignKey("structural_health_reviews.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reviewed_by: Mapped[str | None] = mapped_column(String(160))
    review_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StructuralRetestHandoff(StructuralAssetScope, Base):
    __tablename__ = "structural_retest_handoffs"
    __table_args__ = (
        UniqueConstraint(
            "work_order_id", "source_fingerprint", name="uq_structural_retest_handoff"
        ),
        CheckConstraint(
            "(modal_id IS NOT NULL AND prestress_id IS NULL) OR "
            "(modal_id IS NULL AND prestress_id IS NOT NULL)",
            name="ck_structural_retest_one_source",
        ),
        ForeignKeyConstraint(
            ["modal_id", "turbine_id"], ["modal_observations.id", "modal_observations.turbine_id"]
        ),
        Index("ix_structural_retest_order_time", "work_order_id", "verified_at"),
        ForeignKeyConstraint(
            ["prestress_id", "turbine_id"],
            ["prestress_observations.id", "prestress_observations.turbine_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("structural_mission_contexts.mission_id"), nullable=False
    )
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), nullable=False)
    health_review_id: Mapped[str] = mapped_column(
        ForeignKey("structural_health_reviews.id"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("work_order_tasks.id"), nullable=False)
    modal_id: Mapped[str | None] = mapped_column(String(36))
    prestress_id: Mapped[str | None] = mapped_column(String(36))
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    verified_by: Mapped[str] = mapped_column(String(160), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
