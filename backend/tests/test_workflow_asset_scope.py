from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from windops_backend.access_control import attach_access_policy
from windops_backend.errors import NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    AgentDefinition,
    Approval,
    Resource,
    ResourceReservation,
    WeatherWindow,
    WindFarm,
    WorkOrder,
)
from windops_backend.services.workflow import _mission_knowledge_policy


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("foreign_weather", "allow_global", "active_agent"),
    [
        (False, True, True),
        (True, True, True),
        (False, False, True),
        (True, False, True),
        (False, False, False),
    ],
)
async def test_turbine_scoped_approver_can_execute_persisted_weather_plan(
    app: FastAPI,
    client: AsyncClient,
    foreign_weather: bool,
    allow_global: bool,
    active_agent: bool,
) -> None:
    created = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": "scoped-approval-weather",
                    "turbine_id": "WT-023",
                    "observed_at": datetime.now(UTC).isoformat(),
                    "variable": "main_bearing_vibration_rms",
                    "value": 5.2,
                    "unit": "mm/s",
                    "quality": "good",
                    "attributes": {"baseline": 3.7, "anomaly_score": 0.92},
                }
            ]
        },
    )
    assert created.status_code == 202, created.text
    mission_id = created.json()["results"][0]["mission_id"]
    path = f"/api/v1/missions/{mission_id}"
    mission = (await client.get(path)).json()
    if foreign_weather:
        async with app.state.session_factory() as session, session.begin():
            session.add(
                WindFarm(
                    id="WF-UNAUTHORIZED",
                    tenant_id="tenant-east-china",
                    name="Unrelated farm",
                    capacity_mw=100,
                )
            )
            await session.flush()
            window = await session.get(WeatherWindow, "WEATHER-WINDOW-WT023")
            assert window is not None
            window.wind_farm_id = "WF-UNAUTHORIZED"
    if not active_agent:
        async with app.state.session_factory() as session, session.begin():
            definition = await session.get(AgentDefinition, "agent:work_order_agent@2026.10.1")
            assert definition is not None
            definition.active = False
    if not allow_global:
        async with app.state.session_factory() as session, session.begin():
            session.add(
                Resource(
                    id="UNRESERVED-SCOPED-TEST",
                    resource_type="tool",
                    name="Unrelated global tool",
                    quantity=1,
                    status="available",
                )
            )
    headers = {
        "X-WindOps-Test-Principal": "scoped-approver",
        "X-WindOps-Test-Role": "operations_approver",
        "X-WindOps-Test-Turbine-Ids": "WT-023",
        "X-WindOps-Test-Allow-Global": str(allow_global).lower(),
        "Idempotency-Key": "scoped-weather-approval",
    }
    if not allow_global:
        catalog = await client.get("/api/v1/catalog", headers=headers)
        assert catalog.status_code == 200
        assert catalog.json()["agents"] == []
        resources = await client.get("/api/v1/resources", headers=headers)
        assert resources.status_code == 200
        assert resources.json()["resources"] == []
    response = await client.post(
        path + "/approvals",
        headers=headers,
        json={
            "action": "approve",
            "expected_revision": mission["revision"],
            "reason": "Review persisted plan for my turbine",
        },
    )
    if foreign_weather or not active_agent:
        assert response.status_code == (409 if active_agent else 422), response.text
        if not active_agent:
            assert "stopped or has no active governed release" in response.text
        async with app.state.session_factory() as session:
            assert list(await session.scalars(select(Approval))) == []
            assert list(await session.scalars(select(WorkOrder))) == []
        return
    assert response.status_code == 200, response.text
    assert response.json()["work_order_id"].startswith("WO-")
    if not allow_global:
        resources = await client.get("/api/v1/resources", headers=headers)
        assert resources.status_code == 200
        async with app.state.session_factory() as session:
            reserved = set(
                await session.scalars(
                    select(ResourceReservation.resource_id).where(
                        ResourceReservation.mission_id == mission_id
                    )
                )
            )
        assert len(reserved) == 3
        assert {row["resource_id"] for row in resources.json()["resources"]} == reserved
        assert "UNRESERVED-SCOPED-TEST" not in reserved
        catalog = await client.get("/api/v1/catalog", headers=headers)
        assert catalog.status_code == 200
        assert catalog.json()["agents"] == []
    farms = await client.get("/api/v1/turbines", headers=headers)
    assert farms.status_code == 200
    assert farms.json()["wind_farms"] == []


@pytest.mark.asyncio
async def test_workflow_resolves_owned_turbine_tenant_without_exposing_farm(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        attach_access_policy(
            session,
            GraphAccessPolicy.from_values(turbine_ids=["WT-023"], data_scopes=["*"]),
        )
        assert list(await session.scalars(select(WindFarm))) == []
        policy = await _mission_knowledge_policy(session, "WT-023")
        assert policy.tenant_ids == frozenset({"tenant-east-china"})
        assert list(await session.scalars(select(WindFarm))) == []


@pytest.mark.asyncio
async def test_workflow_rejects_turbine_outside_caller_grant(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        attach_access_policy(
            session,
            GraphAccessPolicy.from_values(turbine_ids=["WT-NOT-OWNED"], data_scopes=["*"]),
        )
        with pytest.raises(NotFoundError):
            await _mission_knowledge_policy(session, "WT-023")
