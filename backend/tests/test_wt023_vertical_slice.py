from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.errors import ApprovalGateError
from windops_backend.models import WorkOrder


def normal_samples() -> dict[str, Any]:
    return {
        "samples": [
            {
                "source_event_id": "SCADA-WT023-NORMAL-VIB-001",
                "turbine_id": "WT-023",
                "observed_at": "2026-08-13T01:00:00Z",
                "variable": "main_bearing_vibration_rms",
                "value": 3.0,
                "unit": "mm/s",
                "quality": "good",
                "attributes": {"baseline": 3.0, "anomaly_score": 0.08},
            },
            {
                "source_event_id": "SCADA-WT023-NORMAL-TEMP-001",
                "turbine_id": "WT-023",
                "observed_at": "2026-08-13T01:00:00Z",
                "variable": "main_bearing_temperature",
                "value": 67.1,
                "unit": "degC",
                "quality": "good",
            },
            {
                "source_event_id": "SCADA-WT023-NORMAL-POWER-001",
                "turbine_id": "WT-023",
                "observed_at": "2026-08-13T01:00:00Z",
                "variable": "active_power",
                "value": 5.42,
                "unit": "MW",
                "quality": "good",
            },
        ]
    }


def anomaly_sample(event_id: str = "SCADA-WT023-ANOMALY-001") -> dict[str, Any]:
    return {
        "samples": [
            {
                "source_event_id": event_id,
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
                    "power_fluctuation_pct": 6,
                },
            }
        ]
    }


def valid_field_measurements() -> list[dict[str, Any]]:
    return [
        {"lubrication_condition": "acceptable", "water_content_ppm": 120.0},
        {"vibration_rms_mm_s": 3.8, "bpfo_band_energy_pct": 4.2},
        {"bearing_temperature_c": 68.4},
        {"defect_severity": "minor", "spall_area_mm2": 1.2},
        {
            "photo_count": 5,
            "main_bearing_health_score": 78,
            "turbine_health_score": 82,
        },
    ]


def assert_no_private_reasoning(value: Any) -> None:
    forbidden = ("chain_of_thought", "chain-of-thought", "hidden_reasoning", "private_reasoning")
    if isinstance(value, dict):
        for key, child in value.items():
            assert key.lower() not in forbidden
            assert_no_private_reasoning(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_private_reasoning(child)


@pytest.mark.asyncio
async def test_wt023_full_audited_workflow(client: httpx.AsyncClient) -> None:
    health = (await client.get("/api/v1/turbines/WT-023/health")).json()
    assert health["status"] == "running"
    assert health["health_score"] == 96

    normal = await client.post("/api/v1/scada/ingest", json=normal_samples())
    assert normal.status_code == 202
    assert normal.json()["accepted"] == 3
    assert all(item["mission_id"] is None for item in normal.json()["results"])

    replay = await client.post("/api/v1/scada/ingest", json=normal_samples())
    assert replay.status_code == 202
    assert replay.json()["duplicates"] == 3
    count = (await client.get("/api/v1/scada/sample-count")).json()["count"]
    assert count == 3

    anomaly = await client.post("/api/v1/scada/ingest", json=anomaly_sample())
    assert anomaly.status_code == 202
    anomaly_result = anomaly.json()["results"][0]
    mission_id = anomaly_result["mission_id"]
    alarm_id = anomaly_result["alarm_id"]
    assert mission_id and alarm_id
    assert (await client.get("/api/v1/scada/sample-count")).json()["count"] == 4

    # Transport replay cannot create a second alarm, mission, or workflow execution.
    replay_anomaly = await client.post("/api/v1/scada/ingest", json=anomaly_sample())
    assert replay_anomaly.json()["duplicates"] == 1
    assert replay_anomaly.json()["results"][0]["alarm_id"] == alarm_id
    assert replay_anomaly.json()["results"][0]["mission_id"] == mission_id
    mission = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert mission["status"] == "under_review"
    assert mission["work_order_id"] is None
    assert mission["public_state"]["requires_human_approval"] is True
    assert mission["public_state"]["diagnosis"]["confidence"] == 0.87
    assert len(mission["public_state"]["evidence"]) == 3
    assert len(mission["public_state"]["alternatives"]) == 3
    assert sum(item["recommended"] for item in mission["public_state"]["alternatives"]) == 1
    assert len(mission["public_state"]["reviews"]) == 5
    assert [item["node"] for item in mission["executions"]] == [
        "scada",
        "vibration",
        "knowledge",
        "diagnosis",
        "alternatives",
        "reviews",
        "hitl",
    ]
    assert_no_private_reasoning(mission["public_state"])
    assert_no_private_reasoning(mission["executions"])

    tool_catalog = (await client.get("/api/v1/tools")).json()
    assert tool_catalog["count"] == 11
    assert {item["name"] for item in tool_catalog["tools"]} == {
        "get_turbine_status",
        "query_scada",
        "query_alarm_history",
        "query_vibration",
        "query_weather",
        "query_maintenance_history",
        "query_similar_failures",
        "calculate_health_score",
        "predict_rul",
        "create_decision",
        "create_work_order",
    }

    stale = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        json={
            "action": "approve",
            "expected_revision": mission["revision"] - 1,
            "approver": "Li Wei",
            "reason": "Engineering review complete",
            "comment": "Proceed in the controlled weather window.",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVISION_CONFLICT"
    assert (await client.get(f"/api/v1/missions/{mission_id}")).json()["work_order_id"] is None

    approval = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        json={
            "action": "approve",
            "expected_revision": mission["revision"],
            "approver": "Li Wei",
            "reason": "Engineering and safety reviews accepted",
            "comment": "Derate now; execute during the approved marine window.",
        },
    )
    assert approval.status_code == 200
    approved = approval.json()
    assert approved["mission_status"] == "executing"
    work_order_id = approved["work_order_id"]
    assert work_order_id.startswith("WO-")

    work_order = (await client.get(f"/api/v1/work-orders/{work_order_id}")).json()
    assert work_order["mission_id"] == mission_id
    assert work_order["approval_id"] == approved["approval_id"]
    assert work_order["status"] == "scheduled"
    assert len(work_order["tasks"]) == 5
    assert [task["sequence"] for task in work_order["tasks"]] == [1, 2, 3, 4, 5]
    assert "LOTO" in work_order["safety_plan"]["procedures"]

    out_of_order = await client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{work_order['tasks'][1]['task_id']}/complete",
        json={
            "completed_by": "Offshore Team A",
            "result": "Attempted out-of-order completion.",
            "artifact_uri": "minio://test/field-task-2.json",
            "artifact_sha256": f"{2:064x}",
            "measurement": {"sequence": 2},
        },
    )
    assert out_of_order.status_code == 422

    bad_artifact = await client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{work_order['tasks'][0]['task_id']}/complete",
        json={
            "completed_by": "Offshore Team A",
            "result": "Artifact hash does not match object.",
            "artifact_uri": "minio://test/field-task-1.json",
            "artifact_sha256": "f" * 64,
            "measurement": valid_field_measurements()[0],
        },
    )
    assert bad_artifact.status_code == 422

    unsafe_measurement = await client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{work_order['tasks'][0]['task_id']}/complete",
        json={
            "completed_by": "Offshore Team A",
            "result": "Water content is outside the controlled maintenance threshold.",
            "artifact_uri": "minio://test/field-task-1.json",
            "artifact_sha256": f"{1:064x}",
            "measurement": {
                "lubrication_condition": "acceptable",
                "water_content_ppm": 501,
            },
        },
    )
    assert unsafe_measurement.status_code == 422
    assert "operational gate" in unsafe_measurement.json()["error"]["message"]
    gated_health = (await client.get("/api/v1/turbines/WT-023/health")).json()
    assert gated_health["health_score"] == 68

    # Completing fewer than all five tasks cannot close the workflow or create a case.
    for index, task in enumerate(work_order["tasks"], start=1):
        completed = await client.post(
            f"/api/v1/work-orders/{work_order_id}/tasks/{task['task_id']}/complete",
            json={
                "completed_by": "Offshore Team A",
                "result": f"Task {index} completed with traceable field evidence.",
                "artifact_uri": f"minio://test/field-task-{index}.json",
                "artifact_sha256": f"{index:064x}",
                "measurement": valid_field_measurements()[index - 1],
            },
        )
        assert completed.status_code == 200
        if index < 5:
            assert completed.json()["workflow_finalized"] is False
            cases = (await client.get(f"/api/v1/knowledge/cases?mission_id={mission_id}")).json()
            assert cases["count"] == 0
        else:
            assert completed.json()["workflow_finalized"] is True
            assert completed.json()["knowledge_case_id"].startswith("CASE-")

    duplicate_completion = await client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{work_order['tasks'][-1]['task_id']}/complete",
        json={
            "completed_by": "Offshore Team A",
            "result": "Duplicate transport replay.",
            "artifact_uri": "minio://test/field-task-5.json",
            "artifact_sha256": f"{5:064x}",
            "measurement": {"main_bearing_health_score": 78},
        },
    )
    assert duplicate_completion.json()["already_completed"] is True

    final_work_order = (await client.get(f"/api/v1/work-orders/{work_order_id}")).json()
    assert final_work_order["status"] == "completed"
    assert all(task["status"] == "completed" for task in final_work_order["tasks"])
    final_mission = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert final_mission["status"] == "completed"
    assert [item["node"] for item in final_mission["executions"]][-1] == "workorder"
    assert len(final_mission["executions"]) == 8
    final_alarm = (await client.get(f"/api/v1/alarms/{alarm_id}")).json()
    assert final_alarm["status"] == "resolved"

    final_health = (await client.get("/api/v1/turbines/WT-023/health")).json()
    assert final_health["status"] == "running"
    assert final_health["health_score"] == 82
    assert {event["score"] for event in final_health["history"]} == {96, 68, 82}
    cases = (await client.get(f"/api/v1/knowledge/cases?mission_id={mission_id}")).json()
    assert cases["count"] == 1
    assert len(cases["cases"][0]["resolution"]["completed_tasks"]) == 5


@pytest.mark.asyncio
async def test_sql_tool_cannot_bypass_human_approval_gate(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    response = await client.post(
        "/api/v1/scada/ingest", json=anomaly_sample("SCADA-WT023-GATE-001")
    )
    mission_id = response.json()["results"][0]["mission_id"]
    async with app.state.session_factory() as session:
        adapter = SQLToolAdapter(session)
        with pytest.raises(ApprovalGateError):
            await adapter.create_work_order(mission_id, "not-an-approval", "WT-023")
        count = await session.scalar(select(func.count()).select_from(WorkOrder))
        assert count == 0


@pytest.mark.asyncio
async def test_rejection_is_recorded_without_creating_work_order(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/scada/ingest", json=anomaly_sample("SCADA-WT023-REJECT-001")
    )
    mission_id = response.json()["results"][0]["mission_id"]
    mission = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    rejected = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        json={
            "action": "reject",
            "expected_revision": mission["revision"],
            "approver": "Chen Yu",
            "reason": "Unsafe marine access",
            "comment": "Reassess when wave height is below the permit threshold.",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["mission_status"] == "rejected"
    assert rejected.json()["work_order_id"] is None
    detail = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert detail["approvals"][0]["action"] == "reject"
    assert detail["work_order_id"] is None


@pytest.mark.asyncio
async def test_request_revision_reanalyzes_and_can_then_be_approved(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/scada/ingest", json=anomaly_sample("SCADA-WT023-REVISION-001")
    )
    mission_id = response.json()["results"][0]["mission_id"]
    first_review = (await client.get(f"/api/v1/missions/{mission_id}")).json()

    revision = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        json={
            "action": "request_revision",
            "expected_revision": first_review["revision"],
            "reason": "Refresh the evidence package before approval",
            "comment": "Re-run the public graph with the current controlled sources.",
        },
    )
    assert revision.status_code == 200
    assert revision.json()["mission_status"] == "under_review"
    assert revision.json()["revision"] == first_review["revision"] + 2

    revised = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert revised["decision"]["status"] == "pending_approval"
    assert revised["decision"]["approval_id"] is None
    assert [item["action"] for item in revised["approvals"]] == ["request_revision"]
    assert len(revised["evidence"]) == 3
    assert len(revised["executions"]) == 14

    approved = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        json={
            "action": "approve",
            "expected_revision": revised["revision"],
            "reason": "Revised evidence satisfies engineering review",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["mission_status"] == "executing"
    assert approved.json()["work_order_id"].startswith("WO-")


@pytest.mark.asyncio
async def test_escalation_keeps_decision_open_for_a_later_approval(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/scada/ingest", json=anomaly_sample("SCADA-WT023-ESCALATE-001")
    )
    mission_id = response.json()["results"][0]["mission_id"]
    first_review = (await client.get(f"/api/v1/missions/{mission_id}")).json()

    escalated = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        json={
            "action": "escalate",
            "expected_revision": first_review["revision"],
            "reason": "Operations manager review is required",
        },
    )
    assert escalated.status_code == 200
    assert escalated.json()["mission_status"] == "under_review"
    detail = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert detail["decision"]["status"] == "pending_approval"
    assert detail["decision"]["approval_id"] is None
    assert detail["public_state"]["escalation"]["approval_id"] == escalated.json()["approval_id"]

    approved = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        json={
            "action": "approve",
            "expected_revision": detail["revision"],
            "reason": "Escalated review resolved",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["mission_status"] == "executing"


def test_migration_declares_real_timescale_and_vector_capabilities() -> None:
    migration = (
        Path(__file__).parents[1] / "alembic" / "versions" / "0001_wt023_vertical_slice.py"
    ).read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS timescaledb" in migration
    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration
    assert "create_hypertable('scada_samples', 'observed_at'" in migration
    assert "Vector(1536)" in migration


@pytest.mark.asyncio
async def test_reused_ingest_key_with_different_payload_is_a_conflict(
    client: httpx.AsyncClient,
) -> None:
    first = await client.post("/api/v1/scada/ingest", json=normal_samples())
    assert first.status_code == 202
    changed = normal_samples()
    changed["samples"][0]["value"] = 4.81
    response = await client.post("/api/v1/scada/ingest", json=changed)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert (await client.get("/api/v1/scada/sample-count")).json()["count"] == 3
