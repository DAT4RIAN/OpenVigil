from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.model_base import JSON_VALUE, Base, utcnow


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
