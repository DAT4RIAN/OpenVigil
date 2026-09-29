from copy import deepcopy

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from windops_backend.models import Approval, Decision, Mission, ResourceReservation, WorkOrder
from windops_backend.schemas import MissionAnalysisProfile
from windops_backend.work_plan_binding import describe_execution_plan


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plan_id", [None, "unregistered-bearing-replacement-v1", "existing_binding", "stale_plan"]
)
async def test_unbound_replacement_does_not_create_an_inspection_work_order(
    app: FastAPI, client: httpx.AsyncClient, plan_id: str | None
) -> None:
    ingested = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": "PLAN-BINDING-ANOMALY",
                    "turbine_id": "WT-023",
                    "observed_at": "2026-09-27T00:00:00Z",
                    "variable": "main_bearing_vibration_rms",
                    "value": 4.81,
                    "unit": "mm/s",
                    "quality": "good",
                    "attributes": {"baseline": 3.79, "anomaly_score": 0.86},
                }
            ]
        },
    )
    assert ingested.status_code == 202
    mission_id = ingested.json()["results"][0]["mission_id"]
    async with app.state.session_factory() as session, session.begin():
        decision = await session.scalar(select(Decision).where(Decision.mission_id == mission_id))
        assert decision is not None
        alternatives = deepcopy(decision.alternatives)
        recommended = next(item for item in alternatives if item["recommended"])
        if plan_id != "stale_plan":
            recommended.update(
                action="Replace the main bearing with an upgraded bearing assembly.",
                estimated_downtime_hours=60,
            )
        if plan_id == "stale_plan":
            mission = await session.get(Mission, mission_id)
            assert mission is not None
            profile = MissionAnalysisProfile.model_validate(
                mission.public_state["analysis_profile"]
            )
            changed_plan = describe_execution_plan(profile, "WT-023")["plan"]
            changed_plan["safety_plan"]["estimated_duration_hours"] += 1
            mission.public_state = {
                **mission.public_state,
                "analysis_profile": {
                    **mission.public_state["analysis_profile"],
                    "work_order_plan": changed_plan,
                },
            }
        elif plan_id == "existing_binding":
            assert recommended["execution_plan_id"].startswith("workplan:")
        elif plan_id is not None:
            recommended["execution_plan_id"] = plan_id
        else:
            recommended.pop("execution_plan_id", None)
        decision.alternatives = alternatives
    detail = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    response = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        headers={"Idempotency-Key": "unsupported-plan-approval"},
        json={
            "action": "approve",
            "expected_revision": detail["revision"],
            "selected_alternative_id": detail["decision"]["recommended_alternative_id"],
            "reason": "Regression: an unsupported replacement must not become inspection",
        },
    )
    assert response.status_code == 409, response.text
    final = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert final["status"] == "under_review"
    assert final["revision"] == detail["revision"]
    assert final["work_order_id"] is None
    async with app.state.session_factory() as session:
        for model in (Approval, WorkOrder, ResourceReservation):
            count = await session.scalar(
                select(func.count()).select_from(model).where(model.mission_id == mission_id)
            )
            assert count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("custom", [False, True])
async def test_valid_binding_executes_exact_plan_and_preserves_idempotency(
    app: FastAPI, client: httpx.AsyncClient, custom: bool
) -> None:
    ingested = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": "PLAN-VALID-ANOMALY",
                    "turbine_id": "WT-023",
                    "observed_at": "2026-09-27T00:00:00Z",
                    "variable": "main_bearing_vibration_rms",
                    "value": 4.81,
                    "unit": "mm/s",
                    "quality": "good",
                    "attributes": {"baseline": 3.79, "anomaly_score": 0.86},
                }
            ]
        },
    )
    assert ingested.status_code == 202
    mission_id = ingested.json()["results"][0]["mission_id"]
    path = f"/api/v1/missions/{mission_id}"
    detail = (await client.get(path)).json()
    profile = MissionAnalysisProfile.model_validate(detail["public_state"]["analysis_profile"])
    expected = describe_execution_plan(profile, "WT-023")
    if custom:
        plan = expected["plan"]
        plan["title"] = "WT-023 Site-specific bearing inspection"
        plan["tasks"][0]["title"] = "Verify the site-specific lubrication sample"
        plan["safety_plan"]["estimated_duration_hours"] = 11
        async with app.state.session_factory() as session, session.begin():
            mission = await session.get(Mission, mission_id)
            assert mission is not None
            mission.public_state = {
                **mission.public_state,
                "analysis_profile": {
                    **mission.public_state["analysis_profile"],
                    "work_order_plan": plan,
                },
            }
        revision = await client.post(
            path + "/approvals",
            headers={"Idempotency-Key": "plan-change-request-revision"},
            json={
                "action": "request_revision",
                "expected_revision": detail["revision"],
                "reason": "Use the new controlled site-specific plan",
            },
        )
        assert revision.status_code == 200, revision.text
        detail = (await client.get(path)).json()
        assert detail["status"] == "under_review"
        profile = MissionAnalysisProfile.model_validate(detail["public_state"]["analysis_profile"])
        expected = describe_execution_plan(profile, "WT-023")
    selected = next(item for item in detail["decision"]["alternatives"] if item["recommended"])
    assert selected["execution_plan_id"] == expected["execution_plan_id"]
    assert selected["action"] == expected["action"]
    payload = {
        "action": "approve",
        "expected_revision": detail["revision"],
        "selected_alternative_id": selected["alternative_id"],
        "reason": "Approve this exact controlled execution plan",
    }
    headers = {"Idempotency-Key": "plan-bound-approval-command"}
    approved = await client.post(path + "/approvals", headers=headers, json=payload)
    assert approved.status_code == 200, approved.text
    replay = await client.post(path + "/approvals", headers=headers, json=payload)
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == approved.json()
    order = (await client.get("/api/v1/work-orders/" + approved.json()["work_order_id"])).json()
    assert order["selected_action"] == expected["action"]
    assert order["safety_plan"]["execution_plan_id"] == expected["execution_plan_id"]
    assert [item["title"] for item in order["tasks"]] == [
        item["title"] for item in expected["plan"]["tasks"]
    ]
    assert [item["measurement_schema"] for item in order["tasks"]] == [
        item["measurement_schema"] for item in expected["plan"]["tasks"]
    ]
    for key, value in expected["plan"]["safety_plan"].items():
        assert order["safety_plan"][key] == value
    assert (
        order["estimated_duration_hours"]
        == expected["plan"]["safety_plan"]["estimated_duration_hours"]
    )
    assert order["closure_policy"]["healthy_threshold"] == expected["plan"]["healthy_threshold"]
