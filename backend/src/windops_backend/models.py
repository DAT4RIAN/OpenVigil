from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
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
DEFAULT_TENANT_ID = "tenant-east-china"


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    """Operational tenant boundary used by asset and graph authorization."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WindFarm(Base):
    __tablename__ = "wind_farms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=DEFAULT_TENANT_ID,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    capacity_mw: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Turbine(Base):
    __tablename__ = "turbines"
    __table_args__ = (Index("ix_turbines_health_id", "health_score", "id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    wind_farm_id: Mapped[str] = mapped_column(ForeignKey("wind_farms.id"), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=TurbineStatus.RUNNING.value)
    health_score: Mapped[float] = mapped_column(Float, default=96.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestReceipt(Base):
    __tablename__ = "ingest_receipts"

    source_event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(96), nullable=False, default="scada-default")
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(24), nullable=False, default="accepted")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestSource(Base):
    """Configured external source and its most recent operational state."""

    __tablename__ = "ingest_sources"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="never_seen")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    credential_secret_reference: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestSourceSecurityAudit(Base):
    """Secret-free evidence for quarantined ingest source credentials."""

    __tablename__ = "ingest_source_security_audits"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "original_fingerprint",
            name="uq_ingest_source_security_audit_fingerprint",
        ),
        Index(
            "ix_ingest_source_security_audit_rotation",
            "rotation_required",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("ingest_sources.id"), nullable=False)
    finding_categories: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    original_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    rotation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    replacement_secret_reference: Mapped[str | None] = mapped_column(String(512))
    rotation_evidence: Mapped[str | None] = mapped_column(String(500))
    rotation_confirmed_by: Mapped[str | None] = mapped_column(String(160))
    rotation_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestStreamState(Base):
    """Durable watermark and source sequence for one normalized telemetry stream."""

    __tablename__ = "ingest_stream_states"
    __table_args__ = (Index("ix_ingest_stream_source_updated", "source_id", "updated_at"),)

    source_id: Mapped[str] = mapped_column(ForeignKey("ingest_sources.id"), primary_key=True)
    stream_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    highest_sequence: Mapped[int | None] = mapped_column(BigInteger)
    watermark_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    late_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    quarantined_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommandReceipt(Base):
    """Durable response ledger for externally retried business commands."""

    __tablename__ = "command_receipts"
    __table_args__ = (
        UniqueConstraint(
            "subject",
            "command_type",
            "target",
            "idempotency_key",
            name="uq_command_receipt_subject_scope_target_key",
        ),
        Index("ix_command_receipts_subject_created", "subject", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    command_type: Mapped[str] = mapped_column(String(96), nullable=False)
    target: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    replay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DelegatedRequestNonce(Base):
    """Short-lived, atomically consumed nonce for a delegated write request."""

    __tablename__ = "delegated_request_nonces"
    __table_args__ = (Index("ix_delegated_request_nonces_expires", "expires_at"),)

    jti_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    target: Mapped[str] = mapped_column(String(1024), nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DelegatedRequestAudit(Base):
    """Durable evidence for accepted and rejected delegated write nonces."""

    __tablename__ = "delegated_request_audits"
    __table_args__ = (
        Index("ix_delegated_request_audits_subject_occurred", "subject", "occurred_at"),
        Index("ix_delegated_request_audits_jti_occurred", "jti_sha256", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    jti_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    target: Mapped[str] = mapped_column(String(1024), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScadaSample(Base):
    __tablename__ = "scada_samples"

    # TimescaleDB requires every unique index to include the partition key.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(
        ForeignKey("ingest_receipts.source_event_id"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("ingest_sources.id"), nullable=False, default="scada-default", index=True
    )
    source_sequence: Mapped[int | None] = mapped_column(BigInteger)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False)
    variable: Mapped[str] = mapped_column(String(96), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    quality: Mapped[str] = mapped_column(String(24), default="good")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    __table_args__ = (
        Index(
            "ix_scada_turbine_variable_observed",
            turbine_id,
            variable,
            observed_at.desc(),
        ),
    )


class QuarantinedScadaSample(Base):
    """Immutable rejected input retained for investigation and controlled replay."""

    __tablename__ = "quarantined_scada_samples"
    __table_args__ = (Index("ix_quarantined_source_received", "source_id", "received_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_event_id: Mapped[str] = mapped_column(
        ForeignKey("ingest_receipts.source_event_id"), nullable=False, unique=True
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("ingest_sources.id"), nullable=False)
    stream_key: Mapped[str] = mapped_column(String(160), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)


class DomainEvent(Base):
    """Public, replayable event log; sequence is the durable client cursor."""

    __tablename__ = "domain_events"
    __table_args__ = (
        Index("ix_domain_events_type_sequence", "event_type", "sequence"),
        Index("ix_domain_events_aggregate_sequence", "aggregate_type", "aggregate_id", "sequence"),
    )

    sequence: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True
    )
    id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(96), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Alarm(Base):
    __tablename__ = "alarms"
    __table_args__ = (
        Index("ix_alarms_turbine_status_severity_id", "turbine_id", "status", "severity", "id"),
        Index("ix_alarms_severity_id", "severity", "id"),
        CheckConstraint(
            "source_event_id IS NOT NULL OR model_prediction_id IS NOT NULL",
            name="ck_alarms_has_source",
        ),
        UniqueConstraint("model_prediction_id", name="uq_alarms_model_prediction_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    source_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingest_receipts.source_event_id"), nullable=True, unique=True
    )
    model_prediction_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_predictions.id"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    subsystem: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default=AlarmSeverity.MAJOR.value)
    status: Mapped[str] = mapped_column(String(24), default=AlarmStatus.OPEN.value)
    ai_status: Mapped[str] = mapped_column(String(32), default="queued")
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(String(160))
    assigned_to: Mapped[str | None] = mapped_column(String(160))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)


class Mission(Base):
    __tablename__ = "missions"
    __table_args__ = (
        Index("ix_missions_updated_id", "updated_at", "id"),
        Index("ix_missions_status_updated_id", "status", "updated_at", "id"),
        Index("ix_missions_turbine_updated_id", "turbine_id", "updated_at", "id"),
    )

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
    evaluation_result: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    degradation_policy: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(96))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentToolInvocation(Base):
    """Durable, idempotent audit ledger for user-initiated production tools."""

    __tablename__ = "agent_tool_invocations"
    __table_args__ = (
        UniqueConstraint("subject", "idempotency_key", name="uq_agent_tool_subject_key"),
        Index("ix_agent_tool_invocations_completed", "completed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_key: Mapped[str] = mapped_column(String(96), nullable=False)
    tool_key: Mapped[str] = mapped_column(String(96), nullable=False)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(96))
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MissionComment(Base):
    """Append-only collaboration note attributed to a delegated production identity."""

    __tablename__ = "mission_comments"
    __table_args__ = (Index("ix_mission_comments_mission_created", "mission_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_subject: Mapped[str] = mapped_column(String(160), nullable=False)
    author_email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlatformConfigurationRevision(Base):
    """Immutable platform policy revision; secret values are never stored here."""

    __tablename__ = "platform_configuration_revisions"
    __table_args__ = (
        UniqueConstraint("configuration_key", "revision", name="uq_platform_config_key_revision"),
        Index("ix_platform_config_key_active", "configuration_key", "active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    configuration_key: Mapped[str] = mapped_column(String(96), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    secret_reference: Mapped[str | None] = mapped_column(String(512))
    security_status: Mapped[str] = mapped_column(String(48), nullable=False, default="clean")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlatformConfigurationSecurityAudit(Base):
    """Secret-free evidence for historical platform configuration remediation."""

    __tablename__ = "platform_configuration_security_audits"
    __table_args__ = (
        UniqueConstraint("configuration_id", name="uq_platform_config_security_audit_revision"),
        Index(
            "ix_platform_config_security_audit_rotation",
            "rotation_required",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    configuration_id: Mapped[str] = mapped_column(
        ForeignKey("platform_configuration_revisions.id"), nullable=False
    )
    configuration_key: Mapped[str] = mapped_column(String(96), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    finding_categories: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    original_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    rotation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    replacement_secret_reference: Mapped[str | None] = mapped_column(String(512))
    rotation_evidence: Mapped[str | None] = mapped_column(String(500))
    rotation_confirmed_by: Mapped[str | None] = mapped_column(String(160))
    rotation_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DataContractDefinition(Base):
    """Versioned source/variable contract used to govern normalization and quality."""

    __tablename__ = "data_contract_definitions"
    __table_args__ = (
        UniqueConstraint("source_id", "variable", "revision", name="uq_data_contract_revision"),
        Index("ix_data_contract_source_active", "source_id", "active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("ingest_sources.id"), nullable=False)
    variable: Mapped[str] = mapped_column(String(96), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    contract: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssetTwinProfile(Base):
    """Governed GIS and geometry references for one operational digital twin."""

    __tablename__ = "asset_twin_profiles"

    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), primary_key=True)
    manufacturer: Mapped[str] = mapped_column(String(160), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    coordinate_reference_system: Mapped[str] = mapped_column(String(96), nullable=False)
    geometry_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    geometry_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    """Idempotent mapping between an authoritative WindOps work order and EAM."""

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


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index(
            "ix_knowledge_documents_tenant_scope",
            "tenant_id",
            "wind_farm_id",
            "turbine_id",
            "data_scope",
        ),
        Index(
            "ix_knowledge_documents_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # These columns are the server-trusted visibility boundary.  Metadata is
    # descriptive only and must never be used to authorize a document read.
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    wind_farm_id: Mapped[str | None] = mapped_column(ForeignKey("wind_farms.id"), nullable=True)
    turbine_id: Mapped[str | None] = mapped_column(ForeignKey("turbines.id"), nullable=True)
    data_scope: Mapped[str] = mapped_column(String(48), nullable=False, default="knowledge")
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    citation_uri: Mapped[str] = mapped_column(String(320), nullable=False)
    artifact_uri: Mapped[str | None] = mapped_column(String(1024))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(128))
    content_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    document_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_VALUE, default=dict)
    ingestion_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    embedding: Mapped[list[float] | bytes | None] = mapped_column(
        Vector(1536).with_variant(LargeBinary(), "sqlite"), nullable=True
    )
    vectorized: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding_provider: Mapped[str | None] = mapped_column(String(96))
    embedding_model: Mapped[str | None] = mapped_column(String(160))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RegisteredModel(Base):
    """Immutable, content-addressed model package and its governed contracts."""

    __tablename__ = "registered_models"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_registered_model_name_version"),
        UniqueConstraint("id", "version", name="uq_registered_model_id_version"),
        Index("ix_registered_models_kind_status", "kind", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="registered")
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    content_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelDeployment(Base):
    """Auditable routing state; endpoints and credentials remain external configuration."""

    __tablename__ = "model_deployments"
    __table_args__ = (
        Index("ix_model_deployments_model_status", "model_id", "status"),
        Index("ix_model_deployments_stage_status", "stage", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(
        ForeignKey("registered_models.id"), nullable=False, index=True
    )
    target_id: Mapped[str] = mapped_column(String(96), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="production")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="staged")
    traffic_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluation_gate: Mapped[dict[str, Any]] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    rollback_from_id: Mapped[str | None] = mapped_column(String(36))
    deployed_by: Mapped[str] = mapped_column(String(160), nullable=False)
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelPrediction(Base):
    """Immutable inference ledger used by predictive views and model monitoring."""

    __tablename__ = "model_predictions"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "turbine_id",
            "feature_observed_at",
            name="uq_prediction_deployment_turbine_features",
        ),
        Index("ix_model_predictions_turbine_created", "turbine_id", "created_at"),
        Index("ix_model_predictions_deployment_created", "deployment_id", "created_at"),
        Index(
            "ix_model_predictions_benchmark_replay_created",
            "benchmark_replay_run_id",
            "created_at",
        ),
        Index(
            "ix_model_predictions_benchmark_evaluation_created",
            "benchmark_evaluation_run_id",
            "created_at",
        ),
        CheckConstraint(
            "prediction_kind IN ('predictive', 'anomaly')",
            name="ck_model_predictions_kind",
        ),
        CheckConstraint(
            "feature_window_start IS NULL OR feature_window_end IS NULL "
            "OR feature_window_start <= feature_window_end",
            name="ck_model_predictions_feature_window",
        ),
        CheckConstraint(
            "feature_start_sequence IS NULL OR feature_end_sequence IS NULL "
            "OR feature_start_sequence <= feature_end_sequence",
            name="ck_model_predictions_feature_sequence",
        ),
        CheckConstraint(
            "anomaly_score IS NULL OR (anomaly_score >= 0 AND anomaly_score <= 1)",
            name="ck_model_predictions_anomaly_score",
        ),
        CheckConstraint(
            "prediction_kind <> 'anomaly' OR status <> 'succeeded' OR ("
            "anomaly_score IS NOT NULL AND binary_prediction IS NOT NULL "
            "AND component IS NOT NULL AND threshold_policy_version IS NOT NULL "
            "AND length(threshold_policy_sha256) = 64 "
            "AND feature_window_start IS NOT NULL AND feature_window_end IS NOT NULL "
            "AND feature_start_sequence IS NOT NULL AND feature_end_sequence IS NOT NULL "
            "AND feature_set_version IS NOT NULL AND quality_rule_version IS NOT NULL "
            "AND evidence_artifact_uri IS NOT NULL "
            "AND length(evidence_artifact_sha256) = 64)",
            name="ck_model_predictions_anomaly_structure",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(
        ForeignKey("registered_models.id"), nullable=False, index=True
    )
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("model_deployments.id"), nullable=False, index=True
    )
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    feature_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prediction_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="predictive")
    benchmark_replay_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("benchmark_replay_runs.id"), nullable=True
    )
    benchmark_evaluation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("benchmark_evaluation_runs.id"), nullable=True
    )
    feature_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feature_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feature_start_sequence: Mapped[int | None] = mapped_column(BigInteger)
    feature_end_sequence: Mapped[int | None] = mapped_column(BigInteger)
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    binary_prediction: Mapped[bool | None] = mapped_column(Boolean)
    component: Mapped[str | None] = mapped_column(String(80))
    threshold_policy_version: Mapped[str | None] = mapped_column(String(64))
    threshold_policy_sha256: Mapped[str | None] = mapped_column(String(64))
    feature_set_version: Mapped[str | None] = mapped_column(String(64))
    quality_rule_version: Mapped[str | None] = mapped_column(String(64))
    evidence_artifact_uri: Mapped[str | None] = mapped_column(String(1024))
    evidence_artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(96))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkDatasetVersion(Base):
    """Immutable identity and licensing boundary for one benchmark dataset release."""

    __tablename__ = "benchmark_dataset_versions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version", name="uq_benchmark_dataset_version"),
        UniqueConstraint("content_sha256", name="uq_benchmark_dataset_content_sha256"),
        Index("ix_benchmark_datasets_tenant_status", "tenant_id", "status"),
        CheckConstraint("size_bytes >= 0", name="ck_benchmark_dataset_size"),
        CheckConstraint("file_count >= 0", name="ck_benchmark_dataset_file_count"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="registered")
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    manifest_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_archive_md5: Mapped[str | None] = mapped_column(String(32))
    source_archive_sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    license_name: Mapped[str] = mapped_column(String(160), nullable=False)
    license_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    doi: Mapped[str] = mapped_column(String(256), nullable=False)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    attribution: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkFile(Base):
    __tablename__ = "benchmark_files"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id", "relative_path", name="uq_benchmark_file_dataset_path"
        ),
        Index("ix_benchmark_files_dataset_farm_event", "dataset_version_id", "farm", "event_id"),
        CheckConstraint("farm IS NULL OR farm IN ('A', 'B', 'C')", name="ck_benchmark_files_farm"),
        CheckConstraint(
            "event_id IS NULL OR (event_id >= 0 AND event_id <= 94)",
            name="ck_benchmark_files_event_id",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_benchmark_files_size"),
        CheckConstraint("row_count >= 0", name="ck_benchmark_files_row_count"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_dataset_versions.id"), nullable=False, index=True
    )
    file_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    farm: Mapped[str | None] = mapped_column(String(1))
    event_id: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    schema_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkEvent(Base):
    __tablename__ = "benchmark_events"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "event_id", name="uq_benchmark_event_dataset_event"),
        Index(
            "ix_benchmark_events_dataset_farm_asset",
            "dataset_version_id",
            "farm",
            "source_asset_id",
        ),
        CheckConstraint("farm IN ('A', 'B', 'C')", name="ck_benchmark_events_farm"),
        CheckConstraint("event_id >= 0 AND event_id <= 94", name="ck_benchmark_events_event_id"),
        CheckConstraint("event_label IN ('anomaly', 'normal')", name="ck_benchmark_events_label"),
        CheckConstraint(
            "first_source_row_id >= 0 AND last_source_row_id >= first_source_row_id",
            name="ck_benchmark_events_row_interval",
        ),
        CheckConstraint(
            "train_row_count >= 0 AND prediction_row_count >= 0",
            name="ck_benchmark_events_split_counts",
        ),
        CheckConstraint(
            "event_interval_start >= 0 AND event_interval_end >= event_interval_start",
            name="ck_benchmark_events_event_interval",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_dataset_versions.id"), nullable=False, index=True
    )
    source_file_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_files.id"), nullable=False, unique=True
    )
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    farm: Mapped[str] = mapped_column(String(1), nullable=False)
    source_asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_label: Mapped[str] = mapped_column(String(16), nullable=False)
    first_source_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_source_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    train_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prediction_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_interval_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_interval_end: Mapped[int] = mapped_column(BigInteger, nullable=False)
    truth_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkFeatureMap(Base):
    __tablename__ = "benchmark_feature_maps"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id",
            "mapping_version",
            "farm",
            "source_column",
            name="uq_benchmark_feature_map_source",
        ),
        Index("ix_benchmark_feature_maps_enabled", "dataset_version_id", "farm", "enabled"),
        CheckConstraint("farm IN ('A', 'B', 'C')", name="ck_benchmark_feature_maps_farm"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_dataset_versions.id"), nullable=False, index=True
    )
    mapping_version: Mapped[str] = mapped_column(String(64), nullable=False)
    farm: Mapped[str] = mapped_column(String(1), nullable=False)
    source_column: Mapped[str] = mapped_column(String(160), nullable=False)
    canonical_feature: Mapped[str] = mapped_column(String(160), nullable=False)
    statistic: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    semantics: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkQualityReport(Base):
    __tablename__ = "benchmark_quality_reports"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "quality_rule_version",
            "feature_set_version",
            name="uq_benchmark_quality_report_identity",
        ),
        Index("ix_benchmark_quality_reports_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_events.id"), nullable=False, index=True
    )
    quality_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mask_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    mask_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkEvaluationRun(Base):
    __tablename__ = "benchmark_evaluation_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["model_id", "model_version"],
            ["registered_models.id", "registered_models.version"],
            name="fk_benchmark_evaluation_registered_model_version",
        ),
        UniqueConstraint("input_identity_sha256", name="uq_benchmark_evaluation_input_identity"),
        Index("ix_benchmark_evaluation_dataset_status", "dataset_version_id", "status"),
        Index("ix_benchmark_evaluation_model_created", "model_id", "created_at"),
        CheckConstraint(
            "run_kind IN ('development', 'tuning', 'final-holdout')",
            name="ck_benchmark_evaluation_run_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_benchmark_evaluation_status",
        ),
        CheckConstraint(
            "farm IS NULL OR farm IN ('A', 'B', 'C')", name="ck_benchmark_evaluation_farm"
        ),
        CheckConstraint(
            "requested_event_count >= 0 AND scored_event_count >= 0 "
            "AND failed_event_count >= 0 AND unscorable_event_count >= 0",
            name="ck_benchmark_evaluation_counts_nonnegative",
        ),
        CheckConstraint(
            "status <> 'completed' OR (completed_at IS NOT NULL AND artifact_uri IS NOT NULL "
            "AND length(artifact_sha256) = 64 "
            "AND requested_event_count = scored_event_count + failed_event_count "
            "+ unscorable_event_count)",
            name="ck_benchmark_evaluation_completed",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_dataset_versions.id"), nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    run_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(96), nullable=False)
    farm: Mapped[str | None] = mapped_column(String(1))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    input_identity_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_uri: Mapped[str | None] = mapped_column(String(1024))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    requested_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scored_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unscorable_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extension_data: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BenchmarkEventResult(Base):
    __tablename__ = "benchmark_event_results"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id", "event_id", name="uq_benchmark_event_result_run_event"
        ),
        UniqueConstraint("result_sha256", name="uq_benchmark_event_result_sha256"),
        Index("ix_benchmark_event_results_run_status", "evaluation_run_id", "status"),
        CheckConstraint(
            "status IN ('scored', 'failed', 'unscorable')",
            name="ck_benchmark_event_result_status",
        ),
        CheckConstraint(
            "(status = 'scored' AND scorable = TRUE) OR "
            "(status IN ('failed', 'unscorable') AND scorable = FALSE AND care_score IS NULL)",
            name="ck_benchmark_event_result_score_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_evaluation_runs.id"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_events.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    scorable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    anomaly_detected: Mapped[bool | None] = mapped_column(Boolean)
    care_score: Mapped[float | None] = mapped_column(Float)
    coverage_score: Mapped[float | None] = mapped_column(Float)
    accuracy_score: Mapped[float | None] = mapped_column(Float)
    reliability_score: Mapped[float | None] = mapped_column(Float)
    earliness_score: Mapped[float | None] = mapped_column(Float)
    prediction_artifact_uri: Mapped[str | None] = mapped_column(String(1024))
    prediction_artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(96))
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkMetricSnapshot(Base):
    __tablename__ = "benchmark_metric_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id",
            "metric_name",
            "protocol_version",
            "metric_version",
            name="uq_benchmark_metric_snapshot_identity",
        ),
        Index("ix_benchmark_metric_release", "evaluation_run_id", "is_release_metric"),
        CheckConstraint(
            "threshold_direction IS NULL OR threshold_direction IN ('gte', 'lte', 'eq')",
            name="ck_benchmark_metric_threshold_direction",
        ),
        CheckConstraint(
            "is_release_metric = FALSE OR (threshold_value IS NOT NULL "
            "AND threshold_direction IS NOT NULL AND passed IS NOT NULL)",
            name="ck_benchmark_metric_release_structure",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_evaluation_runs.id"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(96), nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(96), nullable=False)
    metric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    numerator: Mapped[float | None] = mapped_column(Float)
    denominator: Mapped[float | None] = mapped_column(Float)
    is_release_metric: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    threshold_value: Mapped[float | None] = mapped_column(Float)
    threshold_direction: Mapped[str | None] = mapped_column(String(8))
    passed: Mapped[bool | None] = mapped_column(Boolean)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkReplayRun(Base):
    __tablename__ = "benchmark_replay_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["model_id", "model_version"],
            ["registered_models.id", "registered_models.version"],
            name="fk_benchmark_replay_registered_model_version",
        ),
        UniqueConstraint("online_turbine_id", name="uq_benchmark_replay_online_turbine"),
        Index("ix_benchmark_replay_event_status", "event_id", "status"),
        CheckConstraint("farm IN ('A', 'B', 'C')", name="ck_benchmark_replay_farm"),
        CheckConstraint(
            "source_event_number >= 0 AND source_event_number <= 94",
            name="ck_benchmark_replay_event_number",
        ),
        CheckConstraint(
            "source_event_id_rule_version <> ''", name="ck_benchmark_replay_source_rule"
        ),
        CheckConstraint(
            "replay_mode IN ('live-relative', 'historical-fixed')",
            name="ck_benchmark_replay_mode",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'cancelling', 'cancelled', 'completed', 'failed')",
            name="ck_benchmark_replay_status",
        ),
        CheckConstraint("speed > 0", name="ck_benchmark_replay_speed"),
        CheckConstraint(
            "window_start_row_id >= 0 AND window_end_row_id >= window_start_row_id",
            name="ck_benchmark_replay_window",
        ),
        CheckConstraint("checkpoint_revision >= 0", name="ck_benchmark_replay_checkpoint_revision"),
        CheckConstraint(
            "(model_id IS NULL AND model_version IS NULL) OR "
            "(model_id IS NOT NULL AND model_version IS NOT NULL)",
            name="ck_benchmark_replay_model_identity",
        ),
        CheckConstraint(
            "deployment_id IS NULL OR model_id IS NOT NULL",
            name="ck_benchmark_replay_deployment_model",
        ),
        CheckConstraint(
            "status NOT IN ('cancelled', 'completed', 'failed') OR finished_at IS NOT NULL",
            name="ck_benchmark_replay_terminal_time",
        ),
    )

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_dataset_versions.id"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_events.id"), nullable=False, index=True
    )
    source_asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    online_turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False)
    farm: Mapped[str] = mapped_column(String(1), nullable=False)
    source_event_number: Mapped[int] = mapped_column(Integer, nullable=False)
    replay_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    speed: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    replay_anchor_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_variables: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    window_start_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    window_end_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    checkpoint_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkpoint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(64))
    deployment_id: Mapped[str | None] = mapped_column(ForeignKey("model_deployments.id"))
    threshold_policy_version: Mapped[str | None] = mapped_column(String(64))
    threshold_policy_sha256: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[str | None] = mapped_column(String(160))
    error: Mapped[str | None] = mapped_column(Text)


class AnomalyAlertPolicyState(Base):
    __tablename__ = "anomaly_alert_policy_states"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "turbine_id",
            "component",
            "policy_version",
            name="uq_anomaly_alert_policy_scope",
        ),
        Index("ix_anomaly_alert_policy_phase_updated", "phase", "updated_at"),
        CheckConstraint(
            "phase IN ('normal', 'triggering', 'active', 'recovering', 'cooldown')",
            name="ck_anomaly_alert_policy_phase",
        ),
        CheckConstraint(
            "consecutive_trigger_count >= 0 AND consecutive_recovery_count >= 0 AND revision >= 0",
            name="ck_anomaly_alert_policy_counters",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("model_deployments.id"), nullable=False, index=True
    )
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    component: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(24), nullable=False, default="normal")
    consecutive_trigger_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_recovery_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_prediction_id: Mapped[str | None] = mapped_column(ForeignKey("model_predictions.id"))
    last_prediction_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedup_key: Mapped[str | None] = mapped_column(String(128))
    policy_document: Mapped[dict[str, Any]] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    state_document: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GeneratedReport(Base):
    """Immutable, content-addressed report snapshot generated from governed ledgers."""

    __tablename__ = "generated_reports"
    __table_args__ = (
        Index("ix_generated_reports_type_created", "report_type", "created_at"),
        Index("ix_generated_reports_period_created", "period", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_type: Mapped[str] = mapped_column(String(48), nullable=False)
    period: Mapped[str] = mapped_column(String(24), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    generation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    __table_args__ = (Index("ix_resources_type_status_id", "resource_type", "status", "id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default=ResourceStatus.AVAILABLE.value)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResourceReservation(Base):
    __tablename__ = "resource_reservations"
    __table_args__ = (
        UniqueConstraint("mission_id", "resource_id", name="uq_reservation_mission_resource"),
        Index("ix_reservations_resource_created_id", "resource_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WeatherWindow(Base):
    __tablename__ = "weather_windows"
    __table_args__ = (
        Index("ix_weather_farm_starts_ends_id", "wind_farm_id", "starts_at", "ends_at", "id"),
        Index(
            "ix_weather_farm_suitable_starts_ends_id",
            "wind_farm_id",
            "suitable",
            "starts_at",
            "ends_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    wind_farm_id: Mapped[str] = mapped_column(ForeignKey("wind_farms.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    wind_speed_ms: Mapped[float] = mapped_column(Float, nullable=False)
    wave_height_m: Mapped[float] = mapped_column(Float, nullable=False)
    suitable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
