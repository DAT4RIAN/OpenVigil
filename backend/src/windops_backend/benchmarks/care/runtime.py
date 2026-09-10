from __future__ import annotations

from functools import lru_cache
from urllib.parse import parse_qs, urlparse

from minio import Minio
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CareWorkerSettings(BaseSettings):
    """Least-privilege configuration for the isolated CARE batch workload."""

    model_config = SettingsConfigDict(
        env_prefix="WINDOPS_CARE_",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: SecretStr
    minio_endpoint: str = Field(min_length=3)
    minio_access_key: str = Field(min_length=3)
    minio_secret_key: SecretStr
    minio_secure: bool
    minio_bucket: str = Field(min_length=3)
    forbidden_buckets: str = Field(min_length=3)

    @model_validator(mode="after")
    def validate_production_boundaries(self) -> CareWorkerSettings:
        database = urlparse(self.database_url.get_secret_value())
        if database.scheme != "postgresql+asyncpg" or not database.hostname:
            raise ValueError("CARE worker PostgreSQL must use postgresql+asyncpg")
        tls_values = parse_qs(database.query).get("ssl", []) + parse_qs(database.query).get(
            "sslmode", []
        )
        if not any(
            value.casefold() in {"require", "verify-ca", "verify-full"} for value in tls_values
        ):
            raise ValueError("CARE worker PostgreSQL must require TLS")
        if (database.password or "").casefold() in {"", "windops", "password", "change-me"}:
            raise ValueError("CARE worker PostgreSQL credentials cannot be missing or examples")
        endpoint = self.minio_endpoint.casefold()
        if (
            not self.minio_secure
            or "://" in endpoint
            or endpoint.startswith("localhost")
            or endpoint.startswith("127.0.0.1")
        ):
            raise ValueError("CARE worker MinIO must use a non-local TLS endpoint")
        if len(self.minio_secret_key.get_secret_value()) < 32:
            raise ValueError("CARE worker MinIO secret must contain at least 32 characters")
        forbidden = self.forbidden_bucket_names
        if len(forbidden) < 4 or self.minio_bucket in forbidden:
            raise ValueError("CARE worker forbidden-bucket scope is incomplete")
        return self

    @property
    def forbidden_bucket_names(self) -> tuple[str, ...]:
        names = tuple(value.strip() for value in self.forbidden_buckets.split(",") if value.strip())
        if len(names) != len(set(names)):
            raise ValueError("CARE worker forbidden buckets cannot contain duplicates")
        return names


@lru_cache
def get_care_worker_settings() -> CareWorkerSettings:
    return CareWorkerSettings()


def care_minio_client(settings: CareWorkerSettings) -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key.get_secret_value(),
        secure=settings.minio_secure,
    )
