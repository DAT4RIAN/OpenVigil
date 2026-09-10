from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from windops_backend.enums import AlarmSeverity
from windops_backend.models import Alarm, CommandReceipt, IngestReceipt, Mission


async def _seed_unassigned_alarm(app: FastAPI, alarm_id: str = "ALARM-GEARBOX-001") -> str:
    source_event_id = f"source-{alarm_id.lower()}"
    async with app.state.session_factory() as session, session.begin():
        session.add(
            IngestReceipt(
                source_event_id=source_event_id,
                payload_hash="a" * 64,
            )
        )
        session.add(
            Alarm(
                id=alarm_id,
                turbine_id="WT-023",
                source_event_id=source_event_id,
                code="GB-OIL-TEMP-HIGH",
                subsystem="gearbox",
                title="Gearbox oil temperature sustained high",
                severity=AlarmSeverity.MAJOR.value,
                triggered_at=datetime.now(UTC),
                evidence={
                    "variable": "gearbox_oil_temperature",
                    "value": 92.4,
                    "unit": "celsius",
                    "attributes": {"anomaly_score": 0.91},
                },
            )
        )
    return alarm_id


async def test_business_collections_are_queryable_and_filterable(
    app: FastAPI, client: AsyncClient
) -> None:
    alarm_id = await _seed_unassigned_alarm(app, "ALARM-COLLECTION-001")
    turbines = await client.get("/api/v1/turbines", params={"status": "running"})
    assert turbines.status_code == 200
    assert turbines.json()["count"] >= 1

    alarms = await client.get("/api/v1/alarms", params={"turbine_id": "WT-023"})
    assert alarms.status_code == 200
    assert alarms.json()["alarms"][0]["alarm_id"] == alarm_id
    assert alarms.json()["alarms"][0]["mission_id"] is None

    missions = await client.get("/api/v1/missions", params={"turbine_id": "WT-023"})
    assert missions.status_code == 200
    assert missions.json()["count"] == 0

    work_orders = await client.get("/api/v1/work-orders")
    assert work_orders.status_code == 200
    assert work_orders.json()["count"] == 0

    resources = await client.get("/api/v1/resources", params={"status": "available"})
    assert resources.status_code == 200
    assert resources.json()["count"] == 3
    resource_body = resources.json()
    crew = next(item for item in resource_body["resources"] if item["resource_type"] == "crew")
    assert "LOTO" in crew["attributes"]["certifications"]
    assert resource_body["weather_windows"][0]["attributes"]["visibility_km"] == 18


async def test_mission_create_is_authorized_durable_and_idempotent(
    app: FastAPI, client: AsyncClient
) -> None:
    alarm_id = await _seed_unassigned_alarm(app)
    payload = {
        "alarm_id": alarm_id,
        "title": "WT-023 Gearbox Oil Temperature Investigation",
        "analysis_profile": {
            "component": "gearbox",
            "primary_variable": "gearbox_oil_temperature",
            "related_variables": ["active_power", "gearbox_oil_pressure"],
            "failure_mode_hint": "lubrication cooling degradation",
            "knowledge_query": "gearbox oil temperature cooling inspection",
        },
    }
    headers = {"Idempotency-Key": "mission-create-gearbox-001"}

    created = await client.post("/api/v1/missions", json=payload, headers=headers)
    assert created.status_code == 202
    assert created.headers["Idempotency-Replayed"] == "false"
    body = created.json()
    assert body["replayed"] is False
    assert body["analysis_profile"]["component"] == "gearbox"

    replay = await client.post("/api/v1/missions", json=payload, headers=headers)
    assert replay.status_code == 202
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == body

    changed = await client.post(
        "/api/v1/missions",
        json={**payload, "title": "A different command"},
        headers=headers,
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    duplicate_alarm = await client.post(
        "/api/v1/missions",
        json=payload,
        headers={"Idempotency-Key": "mission-create-gearbox-002"},
    )
    assert duplicate_alarm.status_code == 409
    assert duplicate_alarm.json()["error"]["code"] == "ALARM_ALREADY_ASSIGNED"

    detail = await client.get(f"/api/v1/missions/{body['mission_id']}")
    assert detail.status_code == 200
    mission_detail = detail.json()
    assert mission_detail["public_state"]["analysis_profile"] == payload["analysis_profile"]
    assert mission_detail["public_state"]["diagnosis"]["component"] == "gearbox"
    decision_collection = await client.get(
        "/api/v1/decisions", params={"turbine_id": "WT-023", "status": "pending_approval"}
    )
    assert decision_collection.status_code == 200
    decision_body = decision_collection.json()["decisions"][0]
    assert decision_body["mission_id"] == body["mission_id"]
    assert decision_body["mission_revision"] == mission_detail["revision"]
    assert decision_body["alternatives"][1]["estimated_energy_loss_mwh"] == 14
    assert decision_body["alternatives"][1]["deterioration_risk_percent"] == 12

    approved = await client.post(
        f"/api/v1/missions/{body['mission_id']}/approvals",
        headers={"Idempotency-Key": "generic-mission-approval-001"},
        json={
            "action": "approve",
            "expected_revision": mission_detail["revision"],
            "selected_alternative_id": "ALT-A",
            "reason": "Generic gearbox evidence package accepted",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["selected_alternative_id"] == "ALT-A"
    work_order_id = approved.json()["work_order_id"]
    work_order = (await client.get(f"/api/v1/work-orders/{work_order_id}")).json()
    assert work_order["title"] == "WT-023 Gearbox Inspection"
    assert work_order["selected_alternative_id"] == "ALT-A"
    assert work_order["selected_action"].startswith("Stop WT-023")
    assert work_order["safety_plan"]["decision_alternative_id"] == "ALT-A"
    assert work_order["closure_policy"]["component"] == "gearbox"
    assert len(work_order["tasks"]) == 3
    assert all(
        task["measurement_schema"]["additionalProperties"] is False for task in work_order["tasks"]
    )

    measurements = [
        {"inspection_result": "acceptable", "observations": "Cooling circuit is clear."},
        {
            "measured_value": 78.2,
            "unit": "degC",
            "within_operational_limit": True,
        },
        {
            "photo_count": 4,
            "component_health_score": 86,
            "turbine_health_score": 88,
            "return_to_service": True,
        },
    ]
    for index, task in enumerate(work_order["tasks"], start=1):
        artifact_sha256 = f"{index:064x}"
        task_path = f"/api/v1/work-orders/{work_order_id}/tasks/{task['task_id']}"
        field_headers = {
            "X-WindOps-Test-Principal": "technician-42",
            "X-WindOps-Test-Role": "field_technician",
            "Idempotency-Key": f"generic-field-task-{index:03d}",
        }
        if index == 1:
            forbidden = await client.post(
                f"{task_path}/artifacts/presign",
                json={
                    "file_name": "gearbox-evidence.json",
                    "content_type": "application/json",
                    "artifact_sha256": artifact_sha256,
                },
                headers={
                    "X-WindOps-Test-Principal": "operations-manager",
                    "X-WindOps-Test-Role": "operations_manager",
                    "Idempotency-Key": "generic-presign-forbidden-001",
                },
            )
            assert forbidden.status_code == 403
        presigned = await client.post(
            f"{task_path}/artifacts/presign",
            json={
                "file_name": f"gearbox-field-evidence-{index}.json",
                "content_type": "application/json",
                "artifact_sha256": artifact_sha256,
            },
            headers=field_headers,
        )
        assert presigned.status_code == 200
        upload = presigned.json()
        assert upload["artifact_uri"].startswith(
            f"minio://windops-field-evidence/work-orders/{work_order_id}/tasks/{task['task_id']}/"
        )
        assert upload["upload_url"].startswith("memory://upload/")
        assert upload["required_headers"] == {"content-type": "application/json"}
        assert upload["schema_version"] == task["schema_version"]

        completion = await client.post(
            f"{task_path}/complete",
            json={
                "result": f"Generic governed task {index} completed.",
                "artifact_uri": upload["artifact_uri"],
                "artifact_sha256": artifact_sha256,
                "measurement": measurements[index - 1],
            },
            headers=field_headers,
        )
        assert completion.status_code == 200
        assert completion.json()["workflow_finalized"] is (index == 3)
        if index == 1:
            replacement = await client.post(
                f"{task_path}/artifacts/presign",
                json={
                    "file_name": "replacement.json",
                    "content_type": "application/json",
                    "artifact_sha256": artifact_sha256,
                },
                headers={
                    **field_headers,
                    "Idempotency-Key": f"generic-replacement-{index:03d}",
                },
            )
            assert replacement.status_code == 422
            assert replacement.json()["error"]["code"] == "INVALID_TRANSITION"

    health = (await client.get("/api/v1/turbines/WT-023/health")).json()
    assert health["health_score"] == 88

    async with app.state.session_factory() as session:
        receipt_count = await session.scalar(
            select(func.count())
            .select_from(CommandReceipt)
            .where(CommandReceipt.command_type == "mission.create.v1")
        )
        mission_count = await session.scalar(
            select(func.count()).select_from(Mission).where(Mission.alarm_id == alarm_id)
        )
    assert receipt_count == 1
    assert mission_count == 1


async def test_mission_create_requires_manager_role_and_idempotency_key(
    app: FastAPI, client: AsyncClient
) -> None:
    alarm_id = await _seed_unassigned_alarm(app, "ALARM-GEARBOX-002")
    payload = {
        "alarm_id": alarm_id,
        "title": "Gearbox investigation",
        "analysis_profile": {
            "component": "gearbox",
            "primary_variable": "gearbox_oil_temperature",
            "knowledge_query": "gearbox oil inspection",
        },
    }

    missing_key = await client.post("/api/v1/missions", json=payload)
    assert missing_key.status_code == 422

    forbidden = await client.post(
        "/api/v1/missions",
        json=payload,
        headers={
            "Idempotency-Key": "mission-create-forbidden-001",
            "X-WindOps-Test-Principal": "field-user",
            "X-WindOps-Test-Role": "field_technician",
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"


async def test_custom_work_order_plan_is_persisted_and_enforced(
    app: FastAPI, client: AsyncClient
) -> None:
    alarm_id = await _seed_unassigned_alarm(app, "ALARM-CUSTOM-PLAN-001")
    task_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {"condition": {"type": "string", "const": "acceptable"}},
        "required": ["condition"],
    }
    closure_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "verified_health_score": {"type": "number", "minimum": 90, "maximum": 100},
            "return_to_service": {"type": "boolean", "const": True},
        },
        "required": ["verified_health_score", "return_to_service"],
    }
    payload = {
        "alarm_id": alarm_id,
        "title": "Governed gearbox cooling inspection",
        "analysis_profile": {
            "component": "gearbox",
            "primary_variable": "gearbox_oil_temperature",
            "knowledge_query": "gearbox cooling inspection",
            "work_order_plan": {
                "title": "WT-023 Controlled Gearbox Cooling Inspection",
                "priority": "medium",
                "required_resource_types": ["crew"],
                "safety_plan": {
                    "ppe": ["site-approved PPE"],
                    "procedures": ["LOTO"],
                    "estimated_duration_hours": 4,
                    "risk_level": "medium",
                },
                "tasks": [
                    {
                        "title": "Inspect cooling circuit",
                        "schema_version": "gearbox-cooling-inspection-v1",
                        "measurement_schema": task_schema,
                    },
                    {
                        "title": "Verify return-to-service health",
                        "schema_version": "gearbox-cooling-closure-v1",
                        "measurement_schema": closure_schema,
                    },
                ],
                "closure_health_score_field": "verified_health_score",
                "healthy_threshold": 90,
            },
        },
    }
    created = await client.post(
        "/api/v1/missions",
        json=payload,
        headers={"Idempotency-Key": "custom-work-order-plan-001"},
    )
    assert created.status_code == 202
    mission_id = created.json()["mission_id"]
    mission = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    approved = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        headers={"Idempotency-Key": "custom-mission-approval-001"},
        json={
            "action": "approve",
            "expected_revision": mission["revision"],
            "reason": "Controlled custom plan accepted",
        },
    )
    work_order = (
        await client.get(f"/api/v1/work-orders/{approved.json()['work_order_id']}")
    ).json()
    assert work_order["title"] == "WT-023 Controlled Gearbox Cooling Inspection"
    assert work_order["priority"] == "medium"
    assert work_order["estimated_duration_hours"] == 4
    assert work_order["planned_start"] is not None
    assert work_order["deadline"] is not None
    assert len(work_order["tasks"]) == 2

    invalid = await client.post(
        f"/api/v1/work-orders/{work_order['work_order_id']}/tasks/{work_order['tasks'][0]['task_id']}/complete",
        headers={"Idempotency-Key": "custom-task-invalid-001"},
        json={
            "result": "Unexpected field should be rejected.",
            "artifact_uri": "minio://test/field-task-1.json",
            "artifact_sha256": f"{1:064x}",
            "measurement": {"condition": "acceptable", "uncontrolled": True},
        },
    )
    assert invalid.status_code == 422

    for index, (task, measurement) in enumerate(
        zip(
            work_order["tasks"],
            [
                {"condition": "acceptable"},
                {"verified_health_score": 92, "return_to_service": True},
            ],
            strict=True,
        ),
        start=1,
    ):
        completed = await client.post(
            f"/api/v1/work-orders/{work_order['work_order_id']}/tasks/{task['task_id']}/complete",
            headers={"Idempotency-Key": f"custom-task-complete-{index:03d}"},
            json={
                "result": f"Custom task {index} completed.",
                "artifact_uri": f"minio://test/field-task-{index}.json",
                "artifact_sha256": f"{index:064x}",
                "measurement": measurement,
            },
        )
        assert completed.status_code == 200
    assert (await client.get("/api/v1/turbines/WT-023/health")).json()["health_score"] == 92
