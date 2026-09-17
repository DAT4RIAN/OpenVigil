from pathlib import Path

import pytest
from pydantic import ValidationError

import windops_backend.config as config_module
from windops_backend.config import ModelInferenceTarget, Settings
from windops_backend.enums import Environment


def _production_kwargs() -> dict:
    """Smallest settings payload that satisfies every production invariant."""
    return {
        "environment": Environment.PRODUCTION,
        "release_id": "windops-2026.08.14-rc1",
        "release_commit_sha": "a" * 40,
        "release_image_digest": "sha256:" + "b" * 64,
        "bind_host": "0.0.0.0",
        "database_url": (
            "postgresql+asyncpg://windops:external-database-secret@db/windops?ssl=require"
        ),
        "redis_url": "rediss://redis.internal:6379/0",
        "minio_endpoint": "minio.internal:9000",
        "minio_access_key": "windops-production-service",
        "minio_secret_key": "minio-external-secret-00000000000001",
        "minio_secure": True,
        "minio_public_base": "https://evidence.windops.example",
        "agent_mode": "litellm",
        "embedding_model": "text-embedding-3-small",
        "otel_enabled": True,
        "otel_service_name": "windops-production-backend",
        "otel_exporter_otlp_endpoint": "https://otel.windops.example/v1/traces",
        "metrics_bearer_token": "metrics-external-secret-000000000000001",
        "trusted_hosts": ["backend.windops.internal", "windops-api.windops.svc"],
        "docs_enabled": False,
        "rate_limit_enabled": True,
        "neo4j_uri": "neo4j+s://graph.internal:7687",
        "neo4j_user": "windops-graph-service",
        "neo4j_password": "neo4j-external-secret-00000000000001",
        "auth_mode": "sites_delegation",
        "gateway_delegation_secret": "gateway-external-secret-00000000000000000000000001",
        "identity_role_mappings": {
            "sites-manager": ["operations_manager"],
            "sites-approver": ["operations_approver"],
            "sites-reviewer": ["maintenance_reviewer"],
            "sites-technician": ["field_technician"],
        },
        "identity_scope_mappings": {
            "sites-manager": {"tenant_ids": ["*"], "allow_global": True},
            "sites-approver": {"tenant_ids": ["*"]},
            "sites-reviewer": {"tenant_ids": ["*"]},
            "sites-technician": {"tenant_ids": ["*"]},
        },
        "ingest_source_api_keys": {"offshore-opcua-01": "scada-external-secret-00000000000001"},
        "telemetry_source_policies": {
            "offshore-opcua-01": {
                "display_name": "Offshore OPC UA gateway 01",
                "source_kind": "opcua",
                "allowed_turbines": ["WT-023"],
                "allowed_variables": ["main_bearing_vibration_rms"],
                "variable_contracts": {
                    "main_bearing_vibration_rms": {
                        "label": "Main bearing vibration RMS",
                        "unit": "mm/s",
                        "precision": 2,
                        "normal_min": 0,
                        "normal_max": 4.5,
                        "warning_threshold": 4.5,
                        "critical_threshold": 7.1,
                    }
                },
            }
        },
        "eam_enabled": True,
        "eam_base_url": "https://eam.windops.example/api/v1",
        "eam_api_token": "eam-outbound-external-secret-0000000001",
        "eam_webhook_api_key": "eam-inbound-external-secret-00000000001",
        "model_inference_targets": {
            "predictive-primary": {
                "endpoint_url": "https://inference.windops.example/v1/predict",
                "api_token": "model-inference-external-secret-00000000001",
                "timeout_seconds": 15,
            }
        },
        "operations_manager_api_key": "manager-external-secret-00000000001",
    }


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
        knowledge_graph_backend="memory",
    )
    assert settings.is_sqlite is True
    assert settings.environment is Environment.TEST


def test_get_settings_reads_only_repository_root_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "project"
    fake_module_path = repository / "backend" / "src" / "windops_backend" / "config.py"
    fake_module_path.parent.mkdir(parents=True)
    fake_module_path.touch()
    (repository / ".env").write_text("WINDOPS_RELEASE_ID=from-root\n", encoding="utf-8")
    (repository / "backend" / ".env").write_text(
        "WINDOPS_RELEASE_ID=from-backend\n", encoding="utf-8"
    )
    monkeypatch.setattr(config_module, "__file__", str(fake_module_path))
    monkeypatch.delenv("WINDOPS_RELEASE_ID", raising=False)
    config_module.get_settings.cache_clear()
    try:
        assert config_module.get_settings().release_id == "from-root"
    finally:
        config_module.get_settings.cache_clear()


@pytest.mark.parametrize("provider", ["siliconflow", "bailian", "deepseek"])
def test_selected_llm_provider_requires_its_own_key(provider: str) -> None:
    with pytest.raises(ValidationError, match="selected LLM provider requires an API key"):
        Settings(agent_mode="litellm", llm_provider=provider)


def test_selected_llm_provider_rejects_insecure_or_credential_bearing_url() -> None:
    for base_url in ("http://example.com/v1", "https://user:pass@example.com/v1"):
        with pytest.raises(ValidationError, match="credential-free HTTPS base URL"):
            Settings(
                agent_mode="litellm",
                llm_provider="siliconflow",
                siliconflow_base_url=base_url,
                siliconflow_api_key="test-only-key",
            )


def test_production_human_identities_fail_closed_without_explicit_asset_scope() -> None:
    kwargs = _production_kwargs()
    kwargs["identity_scope_mappings"] = {}
    with pytest.raises(ValidationError, match="require explicit access scopes"):
        Settings(**kwargs)

    kwargs = _production_kwargs()
    kwargs["identity_scope_mappings"]["sites-technician"] = {"data_scopes": ["asset"]}
    with pytest.raises(ValidationError, match="require a tenant, asset, entity, or global grant"):
        Settings(**kwargs)


def test_predictive_timeout_contract_keeps_model_below_batch_deadline() -> None:
    target = ModelInferenceTarget(endpoint_url="https://inference.example/predict", api_token="x")
    assert target.timeout_seconds == 15
    assert target.timeout_seconds < 25
    with pytest.raises(ValidationError):
        ModelInferenceTarget(
            endpoint_url="https://inference.example/predict",
            api_token="x",
            timeout_seconds=21,
        )


def test_in_memory_graph_cannot_be_enabled_outside_test() -> None:
    with pytest.raises(ValidationError, match="in-memory knowledge graph is test-only"):
        Settings(
            environment=Environment.DEVELOPMENT,
            knowledge_graph_backend="memory",
        )


def test_production_rejects_the_default_operations_manager_key() -> None:
    kwargs = _production_kwargs()
    del kwargs["operations_manager_api_key"]
    with pytest.raises(ValidationError, match="operations-manager API key"):
        Settings(**kwargs)
    with pytest.raises(ValidationError, match="operations-manager API key"):
        Settings(
            **{
                **kwargs,
                "operations_manager_api_key": "dev-manager-key-replace-before-use-001",
            }
        )


def test_production_accepts_an_explicit_strong_operations_manager_key() -> None:
    settings = Settings(**_production_kwargs())
    assert settings.environment is Environment.PRODUCTION
    assert (
        settings.operations_manager_api_key.get_secret_value()
        == "manager-external-secret-00000000001"
    )
