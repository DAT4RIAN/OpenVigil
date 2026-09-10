from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.enums import (
    AlarmSeverity,
    AlarmStatus,
    MissionStatus,
)
from windops_backend.model_base import JSON_VALUE, Base, utcnow


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
