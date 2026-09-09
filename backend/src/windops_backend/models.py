from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from windops_backend.enums import (
    AlarmSeverity,
    AlarmStatus,
    DecisionStatus,
    ExecutionStatus,
    MissionStatus,
    ResourceStatus,
    TaskStatus,
    TurbineStatus,
    WorkOrderStatus,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class WindFarm(Base):
    __tablename__ = "wind_farms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    capacity_mw: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Turbine(Base):
    __tablename__ = "turbines"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    wind_farm_id: Mapped[str] = mapped_column(ForeignKey("wind_farms.id"), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=TurbineStatus.RUNNING.value)
    health_score: Mapped[float] = mapped_column(Float, default=96.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestReceipt(Base):
    __tablename__ = "ingest_receipts"

    source_event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScadaSample(Base):
    __tablename__ = "scada_samples"
    __table_args__ = (
        Index("ix_scada_turbine_variable_observed", "turbine_id", "variable", "observed_at"),
    )

    # TimescaleDB requires every unique index to include the partition key.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(
        ForeignKey("ingest_receipts.source_event_id"), nullable=False, index=True
    )
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False)
    variable: Mapped[str] = mapped_column(String(96), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    quality: Mapped[str] = mapped_column(String(24), default="good")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)


class Alarm(Base):
    __tablename__ = "alarms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    source_event_id: Mapped[str] = mapped_column(
        ForeignKey("ingest_receipts.source_event_id"), nullable=False, unique=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    subsystem: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default=AlarmSeverity.MAJOR.value)
    status: Mapped[str] = mapped_column(String(24), default=AlarmStatus.OPEN.value)
    ai_status: Mapped[str] = mapped_column(String(32), default="queued")
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    alarm_id: Mapped[str] = mapped_column(ForeignKey("alarms.id"), nullable=False, unique=True)
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=MissionStatus.DETECTED.value)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    public_state: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CatalogVersion(Base):
    __tablename__ = "catalog_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentDefinition(Base):
    __tablename__ = "agent_definitions"
    __table_args__ = (
        UniqueConstraint("agent_key", "version", name="uq_agent_definition_key_version"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    agent_key: Mapped[str] = mapped_column(String(96), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(96), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    catalog_version_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_versions.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SkillDefinition(Base):
    __tablename__ = "skill_definitions"
    __table_args__ = (
        UniqueConstraint("skill_key", "version", name="uq_skill_definition_key_version"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    skill_key: Mapped[str] = mapped_column(String(96), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    catalog_version_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_versions.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)


class ToolDefinition(Base):
    __tablename__ = "tool_definitions"
    __table_args__ = (
        UniqueConstraint("tool_key", "version", name="uq_tool_definition_key_version"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tool_key: Mapped[str] = mapped_column(String(96), nullable=False)
    mode: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    catalog_version_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_versions.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)


class AgentSkillLink(Base):
    __tablename__ = "agent_skill_links"

    agent_definition_id: Mapped[str] = mapped_column(
        ForeignKey("agent_definitions.id"), primary_key=True
    )
    skill_definition_id: Mapped[str] = mapped_column(
        ForeignKey("skill_definitions.id"), primary_key=True
    )
    catalog_version_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_versions.id"), nullable=False
    )


class AgentToolLink(Base):
    __tablename__ = "agent_tool_links"

    agent_definition_id: Mapped[str] = mapped_column(
        ForeignKey("agent_definitions.id"), primary_key=True
    )
    tool_definition_id: Mapped[str] = mapped_column(
        ForeignKey("tool_definitions.id"), primary_key=True
    )
    catalog_version_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_versions.id"), nullable=False
    )


class AgentExecution(Base):
    __tablename__ = "agent_executions"
    __table_args__ = (Index("ix_agent_execution_mission_started", "mission_id", "started_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    catalog_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_versions.id"), index=True
    )
    agent_definition_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_definitions.id"), index=True
    )
    node: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=ExecutionStatus.RUNNING.value)
    input_refs: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    public_output: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(96), default="sqlalchemy")
    model: Mapped[str | None] = mapped_column(String(160))
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(96))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReadAccessAudit(Base):
    __tablename__ = "read_access_audits"
    __table_args__ = (Index("ix_read_access_subject_accessed", "subject", "accessed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(96), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(320), nullable=False)
    query: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("mission_id", "mission_revision", name="uq_approval_mission_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, index=True)
    mission_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
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

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("missions.id"), nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default=DecisionStatus.PENDING_APPROVAL.value)
    alternatives: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, nullable=False)
    recommended_alternative_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recommendation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, default=list)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, unique=True)
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approvals.id"), nullable=False, unique=True
    )
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=WorkOrderStatus.SCHEDULED.value)
    priority: Mapped[str] = mapped_column(String(24), default="high")
    assigned_team: Mapped[str] = mapped_column(String(160), default="East China Offshore Team A")
    created_by: Mapped[str] = mapped_column(String(96), default="work_order_agent")
    safety_plan: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index(
            "ix_knowledge_documents_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    citation_uri: Mapped[str] = mapped_column(String(320), nullable=False)
    embedding: Mapped[list[float] | bytes | None] = mapped_column(
        Vector(1536).with_variant(LargeBinary(), "sqlite"), nullable=True
    )
    vectorized: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeCase(Base):
    __tablename__ = "knowledge_cases"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, unique=True)
    work_order_id: Mapped[str] = mapped_column(
        ForeignKey("work_orders.id"), nullable=False, unique=True
    )
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    diagnosis: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    resolution: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default=ResourceStatus.AVAILABLE.value)


class ResourceReservation(Base):
    __tablename__ = "resource_reservations"
    __table_args__ = (
        UniqueConstraint("mission_id", "resource_id", name="uq_reservation_mission_resource"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WeatherWindow(Base):
    __tablename__ = "weather_windows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    wind_farm_id: Mapped[str] = mapped_column(ForeignKey("wind_farms.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    wind_speed_ms: Mapped[float] = mapped_column(Float, nullable=False)
    wave_height_m: Mapped[float] = mapped_column(Float, nullable=False)
    suitable: Mapped[bool] = mapped_column(Boolean, nullable=False)
