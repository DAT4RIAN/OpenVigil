from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Owned declarations follow; their order is part of the compatibility contract.
class ResourceStockAdjustRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity_delta: int = Field(ge=-1_000_000, le=1_000_000)
    expected_updated_at: datetime
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("quantity_delta")
    @classmethod
    def nonzero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("quantity_delta must not be zero")
        return value


class ResourceReassignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_id: str = Field(min_length=3, max_length=40)
    from_resource_id: str = Field(min_length=3, max_length=64)
    to_resource_id: str = Field(min_length=3, max_length=64)
    reason: str = Field(min_length=3, max_length=500)


class WorkOrderScheduleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planned_start: datetime
    deadline: datetime
    assigned_team: str | None = Field(default=None, min_length=3, max_length=160)
    expected_updated_at: datetime
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_window(self) -> WorkOrderScheduleUpdateRequest:
        if self.planned_start.tzinfo is None or self.deadline.tzinfo is None:
            raise ValueError("schedule timestamps must include explicit timezones")
        if self.deadline <= self.planned_start:
            raise ValueError("deadline must be after planned_start")
        return self


class StrictTaskMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LubricationTaskMeasurement(StrictTaskMeasurement):
    lubrication_condition: Literal["acceptable", "clean"]
    water_content_ppm: float = Field(ge=0, le=500)


class VibrationTaskMeasurement(StrictTaskMeasurement):
    vibration_rms_mm_s: float = Field(ge=0, le=4.5)
    bpfo_band_energy_pct: float = Field(ge=0, le=10)


class TemperatureTaskMeasurement(StrictTaskMeasurement):
    bearing_temperature_c: float = Field(ge=-40, le=75)


class BorescopeTaskMeasurement(StrictTaskMeasurement):
    defect_severity: Literal["none", "minor"]
    spall_area_mm2: float = Field(ge=0, le=5)


class ClosureTaskMeasurement(StrictTaskMeasurement):
    photo_count: int = Field(ge=3, le=100)
    main_bearing_health_score: float = Field(ge=78, le=100)
    turbine_health_score: float = Field(ge=82, le=100)


TASK_MEASUREMENT_SCHEMAS: dict[int, type[StrictTaskMeasurement]] = {
    1: LubricationTaskMeasurement,
    2: VibrationTaskMeasurement,
    3: TemperatureTaskMeasurement,
    4: BorescopeTaskMeasurement,
    5: ClosureTaskMeasurement,
}
