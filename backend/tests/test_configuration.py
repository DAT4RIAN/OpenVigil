import pytest
from pydantic import ValidationError

from windops_backend.config import Settings
from windops_backend.enums import Environment


def test_sqlite_cannot_masquerade_as_production() -> None:
    with pytest.raises(ValidationError, match="SQLite is test-only"):
        Settings(
            environment=Environment.PRODUCTION,
            database_url="sqlite+aiosqlite:///:memory:",
            agent_mode="litellm",
        )


def test_production_requires_litellm_and_alembic_managed_postgres() -> None:
    with pytest.raises(ValidationError, match="LiteLLM"):
        Settings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+asyncpg://windops:secret@db/windops",
            agent_mode="deterministic",
        )
    with pytest.raises(ValidationError, match="Alembic"):
        Settings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+asyncpg://windops:secret@db/windops",
            agent_mode="litellm",
            schema_bootstrap=True,
        )


def test_explicit_sqlite_test_configuration_is_valid() -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url="sqlite+aiosqlite:///:memory:",
        schema_bootstrap=True,
        demo_seed=True,
    )
    assert settings.is_sqlite is True
    assert settings.environment is Environment.TEST
