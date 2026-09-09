from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qs, urlparse

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from windops_backend.enums import Environment


class Settings(BaseSettings):
    """Runtime configuration with a hard production/test storage boundary."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WINDOPS_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    database_url: str = "postgresql+asyncpg://windops:windops@localhost:5432/windops"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "windops"
    minio_secret_key: SecretStr = SecretStr("windops-development-only")
    minio_secure: bool = False
    minio_public_base: str = "http://localhost:9000"
    agent_mode: Literal["deterministic", "litellm"] = "deterministic"
    litellm_model: str = "openai/gpt-5-mini"
    embedding_model: str = "text-embedding-3-small"
    schema_bootstrap: bool = False
    demo_seed: bool = False
    # Tests must opt into synchronous draining. Non-test runtimes always dispatch
    # durable outbox events through Dramatiq/Redis.
    outbox_inline_drain: bool = False
    api_prefix: str = "/api/v1"
    test_auth_bypass_enabled: bool = False
    scada_ingest_api_key: SecretStr = SecretStr("dev-scada-key-replace-before-use-0001")
    operations_approver_api_key: SecretStr = SecretStr("dev-approver-key-replace-before-use-01")
    maintenance_reviewer_api_key: SecretStr = SecretStr("dev-reviewer-key-replace-before-use-01")
    operations_manager_api_key: SecretStr = SecretStr("dev-manager-key-replace-before-use-001")
    field_technician_api_key: SecretStr = SecretStr("dev-field-key-replace-before-use-0001")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite+")

    @model_validator(mode="after")
    def enforce_environment_boundaries(self) -> "Settings":
        if self.is_sqlite and self.environment is not Environment.TEST:
            raise ValueError("SQLite is test-only; development and production require PostgreSQL")
        if self.test_auth_bypass_enabled and self.environment is not Environment.TEST:
            raise ValueError("the test authentication bypass is test-only")
        if self.outbox_inline_drain and self.environment is not Environment.TEST:
            raise ValueError("inline outbox draining is test-only")
        if self.environment is Environment.PRODUCTION:
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("production requires postgresql+asyncpg")
            if self.schema_bootstrap:
                raise ValueError("production schema changes must be applied with Alembic")
            if self.demo_seed:
                raise ValueError("production cannot enable demo seeding")
            if self.agent_mode != "litellm":
                raise ValueError("production requires the LiteLLM reasoning provider")
            if not self.litellm_model.strip():
                raise ValueError("production requires an explicit LiteLLM reasoning model")
            if not self.embedding_model.strip():
                raise ValueError("production requires an explicit embedding model")
            database = urlparse(self.database_url)
            tls_values = parse_qs(database.query).get("ssl", []) + parse_qs(database.query).get(
                "sslmode", []
            )
            if not any(
                value.lower() in {"require", "verify-ca", "verify-full"} for value in tls_values
            ):
                raise ValueError("production PostgreSQL requires TLS (ssl=require or stronger)")
            if (database.password or "").lower() in {"", "windops", "change-me", "password"}:
                raise ValueError("production rejects missing or example PostgreSQL credentials")
            if not self.redis_url.startswith("rediss://"):
                raise ValueError("production Redis requires TLS (rediss://)")
            if not self.minio_endpoint.strip():
                raise ValueError("production requires a MinIO endpoint")
            if not self.minio_secure:
                raise ValueError("production requires MinIO TLS")
            public_minio = urlparse(self.minio_public_base)
            if (
                public_minio.scheme != "https"
                or not public_minio.netloc
                or public_minio.hostname in {"localhost", "127.0.0.1", "::1"}
            ):
                raise ValueError("production requires an external HTTPS MinIO public base")
            minio_secret = self.minio_secret_key.get_secret_value()
            if (
                self.minio_access_key.lower() in {"", "windops", "minioadmin", "change-me"}
                or len(minio_secret) < 32
                or minio_secret.lower()
                in {"", "windops-development-only", "minioadmin", "change-me"}
            ):
                raise ValueError("production rejects missing or example MinIO credentials")
            keys = [
                self.scada_ingest_api_key.get_secret_value(),
                self.operations_approver_api_key.get_secret_value(),
                self.maintenance_reviewer_api_key.get_secret_value(),
                self.operations_manager_api_key.get_secret_value(),
                self.field_technician_api_key.get_secret_value(),
            ]
            rejected = {"", "windops", "change-me", "password"}
            if any(
                len(value) < 32
                or value.lower() in rejected
                or value.startswith("dev-")
                or "replace-before-use" in value.lower()
                for value in keys
            ):
                raise ValueError("production requires external, non-example API secrets")
            if len(set(keys)) != len(keys):
                raise ValueError("production API secrets must be unique per role")
        if self.environment is Environment.TEST and not self.is_sqlite:
            # PostgreSQL integration tests remain valid; this only prevents accidental test
            # configuration from being represented as production configuration.
            return self
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
