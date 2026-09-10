from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.model_base import JSON_VALUE, Base, utcnow


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
    __table_args__ = (
        Index("ix_read_access_subject_accessed", "subject", "accessed_at"),
        Index("ix_read_access_endpoint_accessed", "endpoint", "accessed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(96), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(320), nullable=False)
    query: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, default=utcnow
    )


class ReadAccessAuditArchive(Base):
    """Compressed immutable audit batches retained after hot partitions age out."""

    __tablename__ = "read_access_audit_archives"
    __table_args__ = (
        CheckConstraint("row_count > 0", name="ck_read_access_archive_row_count"),
        CheckConstraint("period_end >= period_start", name="ck_read_access_archive_period"),
        CheckConstraint("expires_at > period_end", name="ck_read_access_archive_expiry"),
        Index("ix_read_access_archive_period", "period_start", "period_end"),
        Index("ix_read_access_archive_expires", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    schema: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_gzip: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
