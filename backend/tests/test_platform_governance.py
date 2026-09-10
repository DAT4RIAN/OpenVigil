from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI

from windops_backend.models import Alarm, IngestReceipt, Resource
from windops_backend.storage import InMemoryArtifactVerifier


async def _seed_batch_alarms(app: FastAPI) -> list[str]:
    now = datetime.now(UTC)
    alarm_ids = ["ALARM-BATCH-001", "ALARM-BATCH-002"]
    async with app.state.session_factory() as session, session.begin():
        for index, alarm_id in enumerate(alarm_ids, start=1):
            event_id = f"platform-governance-event-{index}"
            session.add(IngestReceipt(source_event_id=event_id, payload_hash=f"{index:064x}"))
            session.add(
                Alarm(
                    id=alarm_id,
                    turbine_id="WT-023",
                    source_event_id=event_id,
                    code=f"GOVERNANCE-{index}",
                    subsystem="main_bearing",
                    title=f"Governed batch alarm {index}",
                    severity="major",
                    triggered_at=now,
                    evidence={
                        "variable": "main_bearing_temperature",
                        "value": 79.0 + index,
                        "unit": "celsius",
                    },
                )
            )
    return alarm_ids


def _mission_payload(alarm_id: str) -> dict[str, Any]:
    return {
        "alarm_id": alarm_id,
        "title": f"Governed investigation for {alarm_id}",
        "analysis_profile": {
            "component": "main_bearing",
            "primary_variable": "main_bearing_temperature",
            "related_variables": ["active_power"],
            "failure_mode_hint": "thermal degradation",
            "knowledge_query": "main bearing thermal inspection",
        },
    }


@pytest.mark.asyncio
async def test_platform_configuration_contract_batch_comments_and_twin_artifact(
    app: FastAPI, client: Any
) -> None:
    alarm_ids = await _seed_batch_alarms(app)
    batch = await client.post(
        "/api/v1/missions/batch",
        headers={"Idempotency-Key": "governed-mission-batch-001"},
        json={"missions": [_mission_payload(alarm_id) for alarm_id in alarm_ids]},
    )
    assert batch.status_code == 202, batch.text
    assert batch.json()["count"] == 2
    mission_id = batch.json()["missions"][0]["mission_id"]

    replay = await client.post(
        "/api/v1/missions/batch",
        headers={"Idempotency-Key": "governed-mission-batch-001"},
        json={"missions": [_mission_payload(alarm_id) for alarm_id in alarm_ids]},
    )
    assert replay.status_code == 202, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == batch.json()

    changed_batch = await client.post(
        "/api/v1/missions/batch",
        headers={"Idempotency-Key": "governed-mission-batch-001"},
        json={
            "missions": [
                {**_mission_payload(alarm_ids[0]), "title": "Changed payload"},
                _mission_payload(alarm_ids[1]),
            ]
        },
    )
    assert changed_batch.status_code == 409
    assert changed_batch.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    comment = await client.post(
        f"/api/v1/missions/{mission_id}/comments",
        headers={"Idempotency-Key": "governed-mission-comment-001"},
        json={"body": "Coordinate the inspection with the governed weather window."},
    )
    assert comment.status_code == 201, comment.text
    comments = await client.get(f"/api/v1/missions/{mission_id}/comments")
    assert comments.status_code == 200
    assert comments.json()["comments"][0]["author_subject"] == "integration-test-system"

    source = await client.post(
        "/api/v1/platform/data-sources",
        headers={"Idempotency-Key": "governed-data-source-001"},
        json={
            "source_id": "governed-opcua",
            "display_name": "Governed OPC UA source",
            "source_kind": "opcua",
            "allowed_turbines": ["WT-023"],
            "allowed_variables": ["main_bearing_temperature"],
            "secret_reference": "vault://windops/scada/governed-opcua",
            "reason": "commissioned under change request DATA-101",
        },
    )
    assert source.status_code == 200, source.text
    assert source.json()["secret_configured"] is True

    contract = await client.post(
        "/api/v1/platform/data-contracts",
        headers={"Idempotency-Key": "governed-data-contract-001"},
        json={
            "source_id": "governed-opcua",
            "variable": "main_bearing_temperature",
            "contract": {
                "label": "Main bearing temperature",
                "unit": "celsius",
                "normal_min": -20,
                "normal_max": 75,
                "warning_threshold": 80,
                "critical_threshold": 90,
            },
            "expected_revision": 0,
            "reason": "activate the approved telemetry contract",
        },
    )
    assert contract.status_code == 201, contract.text
    assert contract.json()["revision"] == 1

    configuration = await client.post(
        "/api/v1/platform/configurations",
        headers={"Idempotency-Key": "governed-platform-config-001"},
        json={
            "configuration_key": "backup_policy",
            "value": {"rpo_minutes": 15, "rto_minutes": 60},
            "expected_revision": 0,
            "reason": "approved continuity target for production",
        },
    )
    assert configuration.status_code == 201, configuration.text
    platform = await client.get("/api/v1/platform/configurations")
    assert platform.status_code == 200
    assert platform.json()["meta"]["secrets_redacted"] is True
    assert platform.json()["meta"]["serialization_verified"] is True
    assert platform.json()["data_sources"][0]["secret_configured"] is True

    verifier = app.state.artifact_verifier
    assert isinstance(verifier, InMemoryArtifactVerifier)
    geometry_uri = "minio://windops-twin-artifacts/turbines/WT-023/twin/wt-023.glb"
    geometry_sha256 = verifier.register_object(
        geometry_uri,
        b"verified-gltf-binary",
        "model/gltf-binary",
    )
    twin = await client.post(
        "/api/v1/turbines/WT-023/twin-profile",
        headers={"Idempotency-Key": "governed-twin-profile-001"},
        json={
            "manufacturer": "Goldwind",
            "latitude": 31.245,
            "longitude": 122.617,
            "elevation_m": 12,
            "coordinate_reference_system": "EPSG:4326",
            "geometry_uri": geometry_uri,
            "geometry_sha256": geometry_sha256,
            "reason": "commission verified geometry under asset change control",
        },
    )
    assert twin.status_code == 200, twin.text
    snapshot = await client.get("/api/v1/digital-twin", params={"turbineId": "WT-023"})
    assert snapshot.status_code == 200
    assert snapshot.json()["data"]["model"]["geometryConfigured"] is True
    assert snapshot.json()["data"]["model"]["gisConfigured"] is True
    view = await client.get("/api/v1/turbines/WT-023/twin-profile/artifacts/view")
    assert view.status_code == 200, view.text
    assert view.json()["artifact_sha256"] == geometry_sha256
    assert view.json()["content_type"] == "model/gltf-binary"
    assert view.json()["download_url"].startswith("memory://download/")


@pytest.mark.asyncio
async def test_resource_stock_reassignment_and_weather_validated_schedule(
    app: FastAPI, client: Any
) -> None:
    alarm_ids = await _seed_batch_alarms(app)
    created = await client.post(
        "/api/v1/missions",
        headers={"Idempotency-Key": "governed-resource-mission-001"},
        json=_mission_payload(alarm_ids[0]),
    )
    assert created.status_code == 202, created.text
    mission_id = created.json()["mission_id"]
    mission = await client.get(f"/api/v1/missions/{mission_id}")
    decision = mission.json()["decision"]
    approval = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        headers={"Idempotency-Key": "governed-mission-approval-001"},
        json={
            "action": "approve",
            "expected_revision": mission.json()["revision"],
            "selected_alternative_id": decision["recommended_alternative_id"],
            "reason": "approved for governed scheduling test",
        },
    )
    assert approval.status_code == 200, approval.text
    work_order_id = approval.json()["work_order_id"]

    resources = await client.get("/api/v1/resources")
    source_crew = next(
        row
        for row in resources.json()["resources"]
        if row["resource_type"] == "crew" and row["reservations"]
    )
    async with app.state.session_factory() as session, session.begin():
        session.add(
            Resource(
                id="CREW-MECH-B",
                resource_type="crew",
                name="Mechanical Maintenance Team B",
                quantity=1,
                status="available",
                attributes={"specialties": ["main_bearing"]},
            )
        )
    reassigned = await client.post(
        "/api/v1/resources/reassignments",
        headers={"Idempotency-Key": "governed-resource-reassign-001"},
        json={
            "mission_id": mission_id,
            "from_resource_id": source_crew["resource_id"],
            "to_resource_id": "CREW-MECH-B",
            "reason": "team B has the approved offshore certification window",
        },
    )
    assert reassigned.status_code == 200, reassigned.text
    assert reassigned.json()["resource_id"] == "CREW-MECH-B"

    stock_rows = await client.get("/api/v1/resources")
    spare = next(
        row for row in stock_rows.json()["resources"] if row["resource_type"] == "spare_part"
    )
    stock = await client.post(
        f"/api/v1/resources/{spare['resource_id']}/stock-adjustments",
        headers={"Idempotency-Key": "governed-resource-stock-001"},
        json={
            "quantity_delta": 2,
            "expected_updated_at": spare["updated_at"],
            "reason": "received and inspected replenishment shipment",
        },
    )
    assert stock.status_code == 200, stock.text
    assert stock.json()["quantity"] == spare["quantity"] + 2

    refreshed_order = await client.get(f"/api/v1/work-orders/{work_order_id}")
    weather = resources.json()["weather_windows"][0]
    scheduled = await client.post(
        f"/api/v1/work-orders/{work_order_id}/schedule",
        headers={"Idempotency-Key": "governed-work-order-schedule-001"},
        json={
            "planned_start": weather["starts_at"],
            "deadline": weather["ends_at"],
            "assigned_team": "Mechanical Maintenance Team B",
            "expected_updated_at": refreshed_order.json()["updated_at"],
            "reason": "align field execution with the governed suitable weather window",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    assert scheduled.json()["assigned_team"] == "Mechanical Maintenance Team B"

    agent_tool = await client.post(
        "/api/v1/agent-tools",
        headers={"Idempotency-Key": "governed-query-crew-001"},
        json={
            "tool": "query_crew",
            "agentId": "work_order_agent",
            "idempotencyKey": "governed-query-crew-001",
            "args": {"workOrderId": work_order_id},
        },
    )
    assert agent_tool.status_code == 200, agent_tool.text
    rows = agent_tool.json()["data"]["execution"]["result"]["data"]["rows"]
    assert rows[0]["resource_id"] == "CREW-MECH-B"
