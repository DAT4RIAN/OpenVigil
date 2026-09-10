from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.enums import (
    DecisionStatus,
    TaskStatus,
    WorkOrderStatus,
)
from windops_backend.model_base import JSON_VALUE, Base, utcnow


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("mission_id", "mission_revision", name="uq_approval_mission_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, index=True)
    mission_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_alternative_id: Mapped[str | None] = mapped_column(String(64))
    approver: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("mission_id", "source_key", name="uq_evidence_mission_source_key"),
        Index("ix_evidence_mission_created", "mission_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    source_key: Mapped[str] = mapped_column(String(96), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    citation_uri: Mapped[str | None] = mapped_column(String(640))
    retrieval_method: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        UniqueConstraint("mission_id", name="decisions_mission_id_key"),
        Index("ix_decisions_mission_id", "mission_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=DecisionStatus.PENDING_APPROVAL.value)
    alternatives: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, nullable=False)
    recommended_alternative_id: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_alternative_id: Mapped[str | None] = mapped_column(String(64))
    recommendation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, default=list)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        Index("ix_work_orders_planned_id", "planned_start", "id"),
        Index("ix_work_orders_status_planned_id", "status", "planned_start", "id"),
        Index("ix_work_orders_team_planned_id", "assigned_team", "planned_start", "id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, unique=True)
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approvals.id"), nullable=False, unique=True
    )
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    selected_alternative_id: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=WorkOrderStatus.SCHEDULED.value)
    priority: Mapped[str] = mapped_column(String(24), default="high")
    assigned_team: Mapped[str] = mapped_column(String(160), default="East China Offshore Team A")
    created_by: Mapped[str] = mapped_column(String(96), default="work_order_agent")
    safety_plan: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    closure_policy: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_duration_hours: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalWorkOrderLink(Base):
    """Idempotent mapping between an authoritative OpenVigil work order and EAM."""

    __tablename__ = "external_work_order_links"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_external_work_order_provider_id"),
        Index("ix_external_work_order_status_updated", "sync_status", "updated_at"),
    )

    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    sync_status: Mapped[str] = mapped_column(String(48), nullable=False)
    last_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    external_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkOrderTask(Base):
    __tablename__ = "work_order_tasks"
    __table_args__ = (
        UniqueConstraint("work_order_id", "sequence", name="uq_work_order_task_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    work_order_id: Mapped[str] = mapped_column(
        ForeignKey("work_orders.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement_schema: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=TaskStatus.PENDING.value)
    result: Mapped[str | None] = mapped_column(Text)
    completed_by: Mapped[str | None] = mapped_column(String(160))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssetHealthEvent(Base):
    __tablename__ = "asset_health_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"))
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index(
            "ix_asset_health_turbine_recorded_id",
            turbine_id,
            recorded_at.desc(),
            id.desc(),
        ),
    )
