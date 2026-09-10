from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.enums import (
    ExecutionStatus,
)
from windops_backend.model_base import JSON_VALUE, Base, utcnow


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
