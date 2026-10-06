"""Versioned hybrid-tower identities and immutable, reproducible measurements."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.model_base import JSON_VALUE, Base, utcnow


class StructuralAssetScope:
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    wind_farm_id: Mapped[str] = mapped_column(ForeignKey("wind_farms.id"), nullable=False)
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)


class TowerComponent(StructuralAssetScope, Base):
    __tablename__ = "tower_components"
    __table_args__ = (
        UniqueConstraint("id", "turbine_id", name="uq_tower_component_asset"),
        UniqueConstraint("turbine_id", "code", "revision", name="uq_tower_component_revision"),
        ForeignKeyConstraint(
            ["parent_id", "turbine_id"], ["tower_components.id", "tower_components.turbine_id"]
        ),
        CheckConstraint("parent_id IS NULL OR parent_id != id", name="ck_component_parent"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    component_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(36))
    revision: Mapped[str] = mapped_column(String(80), nullable=False)
    design_reference: Mapped[str] = mapped_column(String(320), nullable=False)
    geometry: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TendonAssembly(StructuralAssetScope, Base):
    __tablename__ = "tendon_assemblies"
    __table_args__ = (
        UniqueConstraint("id", "turbine_id", name="uq_tendon_asset"),
        UniqueConstraint("turbine_id", "code", "revision", name="uq_tendon_revision"),
        ForeignKeyConstraint(
            ["component_id", "turbine_id"], ["tower_components.id", "tower_components.turbine_id"]
        ),
        CheckConstraint("effective_length_m > 0", name="ck_tendon_length"),
        CheckConstraint("line_density_kg_m > 0", name="ck_tendon_density"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    revision: Mapped[str] = mapped_column(String(80), nullable=False)
    component_id: Mapped[str] = mapped_column(String(36), nullable=False)
    effective_length_m: Mapped[float | None] = mapped_column(Float)
    line_density_kg_m: Mapped[float | None] = mapped_column(Float)
    boundary: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SensorChannel(StructuralAssetScope, Base):
    __tablename__ = "sensor_channels"
    __table_args__ = (
        UniqueConstraint("id", "turbine_id", name="uq_sensor_asset"),
        UniqueConstraint("turbine_id", "code", "revision", name="uq_sensor_revision"),
        ForeignKeyConstraint(
            ["component_id", "turbine_id"], ["tower_components.id", "tower_components.turbine_id"]
        ),
        ForeignKeyConstraint(
            ["tendon_id", "turbine_id"], ["tendon_assemblies.id", "tendon_assemblies.turbine_id"]
        ),
        CheckConstraint("range_max > range_min", name="ck_sensor_range"),
        CheckConstraint("calibration_valid_until > calibration_at", name="ck_sensor_calibration"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    revision: Mapped[str] = mapped_column(String(80), nullable=False)
    component_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tendon_id: Mapped[str | None] = mapped_column(String(36))
    quantity: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    range_min: Mapped[float] = mapped_column(Float, nullable=False)
    range_max: Mapped[float] = mapped_column(Float, nullable=False)
    calibration_version: Mapped[str] = mapped_column(String(80), nullable=False)
    calibration_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calibration_valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    calibration_reference: Mapped[str] = mapped_column(String(320), nullable=False)
    synchronization_source: Mapped[str] = mapped_column(String(160), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WaveformRecord(StructuralAssetScope, Base):
    __tablename__ = "waveform_records"
    __table_args__ = (
        UniqueConstraint("id", "turbine_id", name="uq_waveform_asset"),
        UniqueConstraint("turbine_id", "input_fingerprint", name="uq_waveform_fingerprint"),
        CheckConstraint("ended_at > started_at", name="ck_waveform_window"),
        CheckConstraint("sample_rate_hz > 0", name="ck_waveform_rate"),
        CheckConstraint("sample_count > 0", name="ck_waveform_samples"),
        Index("ix_waveform_asset_time", "turbine_id", "started_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_rate_hz: Mapped[float] = mapped_column(Float, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    channel_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    channel_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(320), nullable=False)
    environment: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StructuralAnalysisRun(StructuralAssetScope, Base):
    __tablename__ = "structural_analysis_runs"
    __table_args__ = (
        UniqueConstraint("id", "turbine_id", name="uq_structural_run_asset"),
        UniqueConstraint("turbine_id", "input_fingerprint", name="uq_structural_run_fingerprint"),
        ForeignKeyConstraint(
            ["record_id", "turbine_id"], ["waveform_records.id", "waveform_records.turbine_id"]
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','insufficient_data','failed')",
            name="ck_structural_run_status",
        ),
        Index("ix_structural_run_asset_time", "turbine_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(80), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    algorithm_identity: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE)
    error_code: Mapped[str | None] = mapped_column(String(80))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModalObservation(StructuralAssetScope, Base):
    __tablename__ = "modal_observations"
    __table_args__ = (
        UniqueConstraint("id", "turbine_id", name="uq_modal_asset"),
        ForeignKeyConstraint(
            ["run_id", "turbine_id"],
            ["structural_analysis_runs.id", "structural_analysis_runs.turbine_id"],
        ),
        UniqueConstraint("run_id", "mode_index", name="uq_modal_run_mode"),
        CheckConstraint("frequency_hz > 0", name="ck_modal_frequency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    mode_index: Mapped[int] = mapped_column(Integer, nullable=False)
    frequency_hz: Mapped[float] = mapped_column(Float, nullable=False)
    mode_shape: Mapped[list[dict[str, float]]] = mapped_column(JSON_VALUE, nullable=False)
    quality: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)


class PrestressObservation(StructuralAssetScope, Base):
    __tablename__ = "prestress_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tendon_id", "turbine_id"], ["tendon_assemblies.id", "tendon_assemblies.turbine_id"]
        ),
        ForeignKeyConstraint(
            ["sensor_id", "turbine_id"], ["sensor_channels.id", "sensor_channels.turbine_id"]
        ),
        UniqueConstraint("turbine_id", "input_fingerprint", name="uq_prestress_fingerprint"),
        UniqueConstraint("id", "turbine_id", name="uq_prestress_id_asset"),
        Index("ix_prestress_tendon_time", "tendon_id", "observed_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tendon_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sensor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value_kn: Mapped[float] = mapped_column(Float, nullable=False)
    calibration_version: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HealthBaseline(StructuralAssetScope, Base):
    """Immutable, explicitly confirmed healthy windows; never updated by live data."""

    __tablename__ = "health_baselines"
    __table_args__ = (
        UniqueConstraint("turbine_id", "code", "revision", name="uq_health_baseline_revision"),
        ForeignKeyConstraint(
            ["component_id", "turbine_id"], ["tower_components.id", "tower_components.turbine_id"]
        ),
        ForeignKeyConstraint(
            ["reference_modal_id", "turbine_id"],
            ["modal_observations.id", "modal_observations.turbine_id"],
        ),
        CheckConstraint("valid_until > created_at", name="ck_baseline_expiry"),
        Index("ix_baseline_asset_time", "turbine_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    component_id: Mapped[str] = mapped_column(String(36), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    revision: Mapped[str] = mapped_column(String(80), nullable=False)
    confirmation_reference: Mapped[str] = mapped_column(String(320), nullable=False)
    reference_modal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    training_modal_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
