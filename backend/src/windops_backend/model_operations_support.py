from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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
    ResourceStatus,
)
from windops_backend.model_base import JSON_VALUE, Base, utcnow


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
