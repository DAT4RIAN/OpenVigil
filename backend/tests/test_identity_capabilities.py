from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI


async def _session_for_role(app: FastAPI, role: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-WindOps-Test-Principal": f"capability-{role}",
            "X-WindOps-Test-Role": role,
        },
    ) as client:
        return await client.get("/api/v1/session")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "present", "absent"),
    [
        (
            "field_technician",
            {"mission.comment", "work_order.task.complete"},
            {"alarm.command", "mission.approve", "platform.manage", "model.manage"},
        ),
        (
            "operations_approver",
            {"alarm.command", "mission.approve", "mission.reject", "mission.comment"},
            {"mission.request_revision", "mission.escalate", "platform.manage"},
        ),
        (
            "maintenance_reviewer",
            {"mission.request_revision"},
            {"mission.approve", "mission.comment", "alarm.command", "platform.manage"},
        ),
        (
            "operations_manager",
            {
                "alarm.command",
                "mission.create",
                "mission.escalate",
                "resource.manage",
                "model.manage",
                "platform.manage",
            },
            {"mission.approve", "mission.request_revision", "work_order.task.complete"},
        ),
    ],
)
async def test_session_returns_server_owned_role_capabilities(
    app: FastAPI,
    role: str,
    present: set[str],
    absent: set[str],
) -> None:
    response = await _session_for_role(app, role)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subject"] == f"capability-{role}"
    assert body["roles"] == [role]
    capabilities = set(body["capabilities"])
    assert present <= capabilities
    assert absent.isdisjoint(capabilities)
    assert body["scope"]["allow_global"] is True


@pytest.mark.asyncio
async def test_machine_identity_cannot_bootstrap_a_business_session(app: FastAPI) -> None:
    response = await _session_for_role(app, "scada_ingestor")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "BUSINESS_READ_FORBIDDEN"


@pytest.mark.asyncio
async def test_client_capability_claim_cannot_bypass_backend_role_authorization(
    app: FastAPI,
) -> None:
    transport = httpx.ASGITransport(app=app)
    headers: dict[str, str] = {
        "X-WindOps-Test-Principal": "capability-field_technician",
        "X-WindOps-Test-Role": "field_technician",
        "X-WindOps-Capabilities": "platform.manage,model.manage",
        "Idempotency-Key": "tampered-capability-key",
    }
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=headers,
    ) as client:
        response = await client.post(
            "/api/v1/platform/configurations",
            json={
                "configuration_key": "backup_policy",
                "value": {"retention_days": 30},
                "expected_revision": 0,
                "reason": "attempted client capability escalation",
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
