from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.enums import (
    TurbineStatus,
)
from windops_backend.model_base import DEFAULT_TENANT_ID, Base, utcnow


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
