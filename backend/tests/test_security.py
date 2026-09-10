from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.main import create_app
from windops_backend.security import ApiSecurityHeadersMiddleware


def anomaly_sample() -> dict[str, Any]:
    return {
        "samples": [
            {
                "source_event_id": "SECURITY-ACTOR-WT023-001",
                "turbine_id": "WT-023",
                "observed_at": "2026-08-13T02:14:03Z",
                "variable": "main_bearing_vibration_rms",
                "value": 4.81,
                "unit": "mm/s",
                "quality": "good",
                "attributes": {
                    "baseline": 3.79,
                    "anomaly_score": 0.86,
                    "temperature_delta_c": 8.4,
                },
            }
        ]
    }


async def unauthenticated_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_disabled_api_documentation_has_no_runtime_routes() -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url="sqlite+aiosqlite:///:memory:",
        schema_bootstrap=True,
        knowledge_graph_backend="memory",
        docs_enabled=False,
    )
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path)
            assert response.status_code == 404


@pytest.mark.asyncio
async def test_write_routes_fail_closed_with_uniform_auth_errors(app: FastAPI) -> None:
    async for anonymous in unauthenticated_client(app):
        response = await anonymous.post("/api/v1/scada/ingest", json=anomaly_sample())
        assert response.status_code == 401
        assert response.json() == {
            "error": {"code": "UNAUTHENTICATED", "message": "Authentication required"}
        }
        assert "key" not in response.text.lower()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-WindOps-Test-Principal": "field-user-42",
            "X-WindOps-Test-Role": "field_technician",
            "Idempotency-Key": "security-approval-forbidden-001",
        },
    ) as wrong_role:
        response = await wrong_role.post("/api/v1/scada/ingest", json=anomaly_sample())
        assert response.status_code == 403
        assert response.json() == {"error": {"code": "FORBIDDEN", "message": "Insufficient role"}}


@pytest.mark.asyncio
async def test_request_body_cannot_forge_approval_or_task_actor(
    client: httpx.AsyncClient,
) -> None:
    anomaly = await client.post("/api/v1/scada/ingest", json=anomaly_sample())
    mission_id = anomaly.json()["results"][0]["mission_id"]
    mission = (await client.get(f"/api/v1/missions/{mission_id}")).json()

    wrong_role = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        headers={
            "X-WindOps-Test-Principal": "field-user-42",
            "X-WindOps-Test-Role": "field_technician",
        },
        json={
            "action": "approve",
            "expected_revision": mission["revision"],
            "approver": "forged-admin",
            "reason": "Attempted role escalation",
        },
    )
    assert wrong_role.status_code == 403

    approval = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        headers={
            "X-WindOps-Test-Principal": "trusted-approver-17",
            "X-WindOps-Test-Role": "operations_approver",
            "Idempotency-Key": "security-approval-trusted-001",
        },
        json={
            "action": "approve",
            "expected_revision": mission["revision"],
            "approver": "forged-admin",
            "reason": "Engineering review complete",
        },
    )
    assert approval.status_code == 200
    mission_after = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert mission_after["approvals"][0]["approver"] == "trusted-approver-17"

    work_order_id = approval.json()["work_order_id"]
    work_order = (await client.get(f"/api/v1/work-orders/{work_order_id}")).json()
    task_id = work_order["tasks"][0]["task_id"]
    completed = await client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{task_id}/complete",
        headers={
            "X-WindOps-Test-Principal": "field-tech-23",
            "X-WindOps-Test-Role": "field_technician",
            "Idempotency-Key": "security-task-complete-001",
        },
        json={
            "completed_by": "forged-supervisor",
            "result": "Evidence retained.",
            "artifact_uri": "minio://test/security-evidence.json",
            "artifact_sha256": "a" * 64,
            "measurement": {
                "lubrication_condition": "acceptable",
                "water_content_ppm": 120,
            },
        },
    )
    assert completed.status_code == 200
    work_order_after = (await client.get(f"/api/v1/work-orders/{work_order_id}")).json()
    assert work_order_after["tasks"][0]["completed_by"] == "field-tech-23"


def test_auth_bypass_cannot_be_enabled_outside_test() -> None:
    with pytest.raises(ValidationError, match="test authentication bypass is test-only"):
        Settings(environment=Environment.DEVELOPMENT, test_auth_bypass_enabled=True)


def test_production_requires_tls_sites_delegation_and_external_service_secrets() -> None:
    production = {
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
        "otel_exporter_otlp_headers": {"Authorization": "otel-external-secret-00000000000000001"},
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
        "operations_approver_api_key": "approver-external-secret-0000000001",
        "maintenance_reviewer_api_key": "reviewer-external-secret-0000000001",
        "operations_manager_api_key": "manager-external-secret-00000000001",
        "field_technician_api_key": "field-external-secret-0000000000001",
    }
    settings = Settings(**production)
    assert settings.environment is Environment.PRODUCTION

    with pytest.raises(ValidationError, match="immutable release ID"):
        Settings(**{**production, "release_id": "development"})
    with pytest.raises(ValidationError, match="immutable release ID"):
        Settings(**{**production, "release_id": "release id with spaces"})
    with pytest.raises(ValidationError, match="Git commit SHA"):
        Settings(**{**production, "release_commit_sha": "abc123"})
    with pytest.raises(ValidationError, match="image SHA-256 digest"):
        Settings(**{**production, "release_image_digest": "sha256:" + "0" * 64})

    with pytest.raises(ValidationError, match="PostgreSQL requires TLS"):
        Settings(**{**production, "database_url": "postgresql+asyncpg://user:secret@db/windops"})
    with pytest.raises(ValidationError, match="Redis requires TLS"):
        Settings(**{**production, "redis_url": "redis://redis.internal:6379/0"})
    with pytest.raises(ValidationError, match="Neo4j requires verified TLS"):
        Settings(**{**production, "neo4j_uri": "neo4j://graph.internal:7687"})
    with pytest.raises(ValidationError, match="example Neo4j credentials"):
        Settings(**{**production, "neo4j_password": "change-me"})
    with pytest.raises(ValidationError, match="HTTPS MinIO public base"):
        Settings(**{**production, "minio_public_base": "http://localhost:9000"})
    with pytest.raises(ValidationError, match="embedding model"):
        Settings(**{**production, "embedding_model": ""})
    with pytest.raises(ValidationError, match="OpenTelemetry export"):
        Settings(**{**production, "otel_enabled": False})
    with pytest.raises(ValidationError, match="external HTTPS OTLP"):
        Settings(
            **{
                **production,
                "otel_exporter_otlp_endpoint": "http://localhost:4318/v1/traces",
            }
        )
    with pytest.raises(ValidationError, match="metrics bearer token"):
        Settings(**{**production, "metrics_bearer_token": "dev-replace"})
    with pytest.raises(ValidationError, match="trusted Host"):
        Settings(**{**production, "trusted_hosts": ["*"]})
    with pytest.raises(ValidationError, match="trusted Host"):
        Settings(**{**production, "trusted_hosts": ["localhost"]})
    with pytest.raises(ValidationError, match="non-loopback"):
        Settings(**{**production, "bind_host": "127.0.0.1"})
    with pytest.raises(ValidationError, match="documentation must be disabled"):
        Settings(**{**production, "docs_enabled": True})
    with pytest.raises(ValidationError, match="rate limiting"):
        Settings(**{**production, "rate_limit_enabled": False})
    with pytest.raises(ValidationError, match="non-example secret per telemetry source"):
        Settings(
            **{
                **production,
                "ingest_source_api_keys": {
                    "offshore-opcua-01": "dev-scada-key-replace-before-use-0001"
                },
            }
        )
    with pytest.raises(ValidationError, match="one distinct credential"):
        Settings(**{**production, "telemetry_source_policies": {}})
    with pytest.raises(ValidationError, match="EAM work-order integration"):
        Settings(**{**production, "eam_enabled": False})
    with pytest.raises(ValidationError, match="model inference target"):
        Settings(**{**production, "model_inference_targets": {}})
    with pytest.raises(ValidationError, match="external HTTPS endpoints"):
        Settings(
            **{
                **production,
                "model_inference_targets": {
                    "predictive-primary": {
                        "endpoint_url": "http://localhost:8080/predict",
                        "api_token": "model-inference-external-secret-00000000001",
                    }
                },
            }
        )
    with pytest.raises(ValidationError, match="Sites per-user delegated"):
        Settings(**{**production, "auth_mode": "static_tokens"})
    with pytest.raises(ValidationError, match="identity mappings"):
        Settings(**{**production, "identity_role_mappings": {}})
    with pytest.raises(ValidationError, match="delegation secret"):
        Settings(**{**production, "gateway_delegation_secret": "dev-replace"})


@pytest.mark.asyncio
async def test_production_responses_expose_immutable_release_identity() -> None:
    application = FastAPI()

    @application.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    release_id = "windops-2026.08.14-rc1"
    commit_sha = "a" * 40
    image_digest = "sha256:" + "b" * 64
    secured = ApiSecurityHeadersMiddleware(
        application,
        production=True,
        release_id=release_id,
        release_commit_sha=commit_sha,
        release_image_digest=image_digest,
    )
    transport = httpx.ASGITransport(app=secured)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["x-windops-release-id"] == release_id
    assert response.headers["x-windops-commit-sha"] == commit_sha
    assert response.headers["x-windops-image-digest"] == image_digest


@pytest.mark.asyncio
async def test_api_rejects_host_injection_and_oversized_bodies(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://evil.example") as attacker:
        invalid_host = await attacker.get("/api/v1/healthz")
    assert invalid_host.status_code == 400

    oversized = await client.post(
        "/api/v1/scada/ingest",
        headers={"Content-Length": str(app.state.settings.max_request_body_bytes + 1)},
        content=b"{}",
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "REQUEST_TOO_LARGE"

    class ChunkedBody(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            yield b"x" * app.state.settings.max_request_body_bytes
            yield b"x"

    chunked = await client.post(
        "/api/v1/scada/ingest",
        headers={"Content-Type": "application/json"},
        content=ChunkedBody(),
    )
    assert chunked.status_code == 413
    assert chunked.json()["error"]["code"] == "REQUEST_TOO_LARGE"
