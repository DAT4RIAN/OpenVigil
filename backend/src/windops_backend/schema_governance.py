from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from windops_backend.platform_configuration import (
    ConfigurationKey,
    PlatformConfigurationValidationError,
    inspect_platform_configuration_material,
    validate_platform_configuration_value,
    validate_secret_manager_reference,
)


# Owned declarations follow; their order is part of the compatibility contract.
class IngestSourcePolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,95}$")
    display_name: str = Field(min_length=3, max_length=160)
    source_kind: Literal["opcua", "mqtt", "iec61400_25", "cms", "weather", "rest"]
    enabled: bool = True
    sequence_required: bool = True
    max_lateness_seconds: int = Field(default=300, ge=0, le=86_400)
    max_future_skew_seconds: int = Field(default=120, ge=0, le=3_600)
    expected_heartbeat_seconds: int = Field(default=60, ge=5, le=86_400)
    allowed_turbines: list[str] = Field(default_factory=list, max_length=10_000)
    allowed_variables: list[str] = Field(default_factory=list, max_length=10_000)
    secret_reference: str | None = Field(
        default=None,
        pattern=r"^(?:vault|aws-secretsmanager|azure-keyvault|gcp-secretmanager)://[^\s]+$",
        max_length=512,
    )
    expected_updated_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("secret_reference")
    @classmethod
    def validate_secret_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_secret_manager_reference(value)
        except PlatformConfigurationValidationError as exc:
            raise ValueError(str(exc)) from None


class DataContractCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,95}$")
    variable: str = Field(pattern=r"^[a-z][a-z0-9_]{1,95}$")
    contract: dict[str, Any]
    expected_revision: int = Field(default=0, ge=0)
    reason: str = Field(min_length=3, max_length=500)


class PlatformConfigurationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configuration_key: ConfigurationKey
    value: dict[str, Any]
    secret_reference: str | None = Field(default=None, max_length=512)
    expected_revision: int = Field(default=0, ge=0)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("secret_reference")
    @classmethod
    def validate_secret_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_secret_manager_reference(value)
        except PlatformConfigurationValidationError as exc:
            raise ValueError(str(exc)) from None

    @model_validator(mode="after")
    def validate_configuration_value(self) -> Self:
        try:
            self.value = validate_platform_configuration_value(
                self.configuration_key,
                self.value,
                secret_reference=self.secret_reference,
                reason=self.reason,
            )
        except PlatformConfigurationValidationError as exc:
            raise ValueError(str(exc)) from None
        return self


class PlatformConfigurationRotationConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replacement_secret_reference: str = Field(max_length=512)
    rotation_evidence: str = Field(min_length=8, max_length=500)

    @field_validator("replacement_secret_reference")
    @classmethod
    def validate_replacement_secret_reference(cls, value: str) -> str:
        try:
            return validate_secret_manager_reference(value)
        except PlatformConfigurationValidationError as exc:
            raise ValueError(str(exc)) from None

    @field_validator("rotation_evidence")
    @classmethod
    def reject_secret_evidence(cls, value: str) -> str:
        try:
            inspection = inspect_platform_configuration_material({}, reason=value)
        except PlatformConfigurationValidationError as exc:
            raise ValueError(str(exc)) from None
        if inspection.finding_categories:
            raise ValueError("rotation evidence must not contain credential material")
        return value


class AssetTwinProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manufacturer: str = Field(min_length=2, max_length=160)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float = Field(default=0, ge=-1000, le=15_000)
    coordinate_reference_system: str = Field(default="EPSG:4326", min_length=4, max_length=96)
    geometry_uri: str = Field(min_length=16, max_length=1024)
    geometry_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    expected_updated_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)


class AssetTwinArtifactUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(min_length=1, max_length=240)
    content_type: Literal[
        "model/gltf+json",
        "model/gltf-binary",
        "application/octet-stream",
        "application/zip",
    ]
    artifact_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
