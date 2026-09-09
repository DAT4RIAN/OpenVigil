from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from windops_backend.config import Settings
from windops_backend.enums import Environment


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


def test_production_requires_tls_and_external_role_secrets() -> None:
    production = {
        "environment": Environment.PRODUCTION,
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
        "scada_ingest_api_key": "scada-external-secret-00000000000001",
        "operations_approver_api_key": "approver-external-secret-0000000001",
        "maintenance_reviewer_api_key": "reviewer-external-secret-0000000001",
        "operations_manager_api_key": "manager-external-secret-00000000001",
        "field_technician_api_key": "field-external-secret-0000000000001",
    }
    settings = Settings(**production)
    assert settings.environment is Environment.PRODUCTION

    with pytest.raises(ValidationError, match="PostgreSQL requires TLS"):
        Settings(**{**production, "database_url": "postgresql+asyncpg://user:secret@db/windops"})
    with pytest.raises(ValidationError, match="Redis requires TLS"):
        Settings(**{**production, "redis_url": "redis://redis.internal:6379/0"})
    with pytest.raises(ValidationError, match="HTTPS MinIO public base"):
        Settings(**{**production, "minio_public_base": "http://localhost:9000"})
    with pytest.raises(ValidationError, match="embedding model"):
        Settings(**{**production, "embedding_model": ""})
    with pytest.raises(ValidationError, match="external, non-example API secrets"):
        Settings(**{**production, "scada_ingest_api_key": "dev-scada-key-replace-before-use-0001"})
