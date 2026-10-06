from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Identity = Annotated[str, Field(min_length=1, max_length=36)]
Version = Annotated[str, Field(min_length=1, max_length=80)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
SourceKind = Literal["field_measurement", "public_sample", "synthetic_test"]


class StructuralRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def normalize_measurement_time(cls, value: Any) -> Any:
        return value.astimezone(UTC) if isinstance(value, datetime) else value


class ComponentCreate(StructuralRequest):
    turbine_id: Identity
    code: Version
    name: Annotated[str, Field(min_length=1, max_length=160)]
    component_type: Literal["concrete_segment", "steel_segment", "transition", "joint", "anchor"]
    revision: Version
    design_reference: Annotated[str, Field(min_length=1, max_length=320)]
    parent_id: Identity | None = None
    geometry: dict[str, Finite] = Field(default_factory=dict, max_length=32)


class TendonCreate(StructuralRequest):
    turbine_id: Identity
    component_id: Identity
    code: Version
    revision: Version
    effective_length_m: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    line_density_kg_m: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    boundary: dict[str, Annotated[str, Field(max_length=320)]] = Field(
        default_factory=dict, max_length=32
    )


class SensorCreate(StructuralRequest):
    turbine_id: Identity
    component_id: Identity
    tendon_id: Identity | None = None
    code: Version
    revision: Version
    quantity: Literal["acceleration", "force", "strain"]
    unit: Literal["m/s2", "g", "kN", "N", "microstrain"]
    direction: Literal["X", "Y", "Z", "axial"]
    range_min: Finite
    range_max: Finite
    calibration_version: Version
    calibration_at: AwareDatetime
    calibration_valid_until: AwareDatetime
    calibration_reference: Annotated[str, Field(min_length=1, max_length=320)]
    synchronization_source: Annotated[str, Field(min_length=1, max_length=160)]

    @model_validator(mode="after")
    def measurement_semantics(self) -> Self:
        units = {"acceleration": {"m/s2", "g"}, "force": {"kN", "N"}, "strain": {"microstrain"}}
        if self.unit not in units[self.quantity]:
            raise ValueError("unit does not match the sensor quantity")
        if self.range_max <= self.range_min:
            raise ValueError("sensor range must be ordered")
        if self.calibration_valid_until <= self.calibration_at:
            raise ValueError("calibration expiry must follow calibration date")
        if self.quantity == "force" and self.tendon_id is None:
            raise ValueError("force sensors must identify a tendon assembly")
        return self


class StructuralUpload(StructuralRequest):
    turbine_id: Identity
    file_name: Annotated[str, Field(min_length=1, max_length=160)]
    artifact_sha256: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")]


class AcquisitionEnvironment(StructuralRequest):
    temperature_c: Finite | None = None
    wind_speed_ms: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    rotor_speed_rpm: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    power_kw: Finite | None = None
    operating_state: Literal["stopped", "running", "unknown"] = "unknown"


class WaveformCreate(StructuralRequest):
    turbine_id: Identity
    channel_ids: Annotated[list[Identity], Field(min_length=1, max_length=16)]
    started_at: AwareDatetime
    ended_at: AwareDatetime
    sample_rate_hz: Annotated[float, Field(gt=0, le=100000, allow_inf_nan=False)]
    sample_count: Annotated[int, Field(ge=16, le=262144)]
    artifact_uri: Annotated[str, Field(min_length=1, max_length=1024)]
    artifact_sha256: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")]
    source_kind: SourceKind
    source_reference: Annotated[str, Field(min_length=1, max_length=320)]
    environment: AcquisitionEnvironment

    @model_validator(mode="after")
    def acquisition_bounds(self) -> Self:
        if len(set(self.channel_ids)) != len(self.channel_ids):
            raise ValueError("waveform channels must be unique")
        if len(self.channel_ids) * self.sample_count > 1048576:
            raise ValueError("waveform exceeds the one-million-sample computation bound")
        duration = (self.ended_at - self.started_at).total_seconds()
        if duration <= 0 or abs(duration * self.sample_rate_hz - self.sample_count) > 1:
            raise ValueError("window is end-exclusive and must match sample count and sample rate")
        return self


class FDDConfiguration(StructuralRequest):
    nperseg: Annotated[int, Field(ge=64, le=8192)] = 1024
    min_frequency_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 0.05
    max_frequency_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 3.0
    max_modes: Annotated[int, Field(ge=1, le=8)] = 4

    @model_validator(mode="after")
    def band_order(self) -> Self:
        if self.max_frequency_hz <= self.min_frequency_hz:
            raise ValueError("analysis frequency band must be ordered")
        return self


class AnalysisCreate(StructuralRequest):
    record_id: Identity
    method: Literal["pyoma2_fdd_v1"] = "pyoma2_fdd_v1"
    config: FDDConfiguration = Field(default_factory=FDDConfiguration)


EnvironmentFeature = Literal["temperature_c", "wind_speed_ms", "rotor_speed_rpm", "power_kw"]


class BaselineCreate(StructuralRequest):
    turbine_id: Identity
    component_id: Identity
    code: Version
    revision: Version
    confirmation_reference: Annotated[str, Field(min_length=1, max_length=320)]
    reference_modal_id: Identity
    training_modal_ids: Annotated[list[Identity], Field(min_length=30, max_length=256)]
    features: Annotated[list[EnvironmentFeature], Field(min_length=1, max_length=4)]
    minimum_mac: Annotated[float, Field(ge=0.8, le=1, allow_inf_nan=False)] = 0.9
    maximum_relative_frequency_shift: Annotated[float, Field(gt=0, le=0.5)] = 0.2
    screening_sigma: Annotated[float, Field(ge=2, le=6, allow_inf_nan=False)] = 3.0
    valid_until: AwareDatetime

    @model_validator(mode="after")
    def unique_inputs(self) -> Self:
        if len(set(self.training_modal_ids)) != len(self.training_modal_ids):
            raise ValueError("baseline observations must be unique")
        if self.reference_modal_id not in self.training_modal_ids:
            raise ValueError("reference mode must be one of the confirmed healthy observations")
        if len(set(self.features)) != len(self.features):
            raise ValueError("baseline features must be unique")
        return self


class DirectForceArtifact(StructuralRequest):
    schema_version: Literal["openvigil.direct-force.v1"]
    tendon_id: Identity
    sensor_id: Identity
    observed_at: AwareDatetime
    value: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    unit: Literal["N", "kN"]
    calibration_version: Version
    uncertainty_kn: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None


class PrestressCreate(StructuralRequest):
    turbine_id: Identity
    tendon_id: Identity
    sensor_id: Identity
    artifact_uri: Annotated[str, Field(min_length=1, max_length=1024)]
    artifact_sha256: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")]
    source_kind: SourceKind


def aware(value: datetime) -> datetime:
    # SQLite loses timezone metadata; stored acquisition timestamps are UTC.
    from datetime import UTC

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value
