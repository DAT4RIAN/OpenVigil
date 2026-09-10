from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from windops_backend.enums import AlarmSeverity, AlarmStatus
from windops_backend.models import Alarm, CommandReceipt, DomainEvent, IngestReceipt


async def _seed_alarm(app: FastAPI, alarm_id: str = "ALARM-COMMAND-001") -> str:
    async with app.state.session_factory() as session, session.begin():
        session.add(IngestReceipt(source_event_id=f"source-{alarm_id}", payload_hash="a" * 64))
        session.add(
            Alarm(
                id=alarm_id,
                turbine_id="WT-023",
                source_event_id=f"source-{alarm_id}",
                code="MB-VIB-HIGH",
                subsystem="main_bearing",
                title="Main-bearing vibration high",
                severity=AlarmSeverity.MAJOR.value,
                status=AlarmStatus.OPEN.value,
                triggered_at=datetime.now(UTC),
                evidence={},
            )
        )
    return alarm_id


async def test_alarm_commands_are_authorized_durable_replay_safe_and_evented(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    alarm_id = await _seed_alarm(app)
    command_path = f"/api/v1/alarms/{alarm_id}"
    acknowledge_payload = {
        "action": "acknowledge",
        "expected_revision": 1,
        "reason": "Operations review accepted the alarm evidence",
    }
    headers = {"Idempotency-Key": "alarm-command-ack-001"}

    forbidden = await client.post(
        command_path,
        json=acknowledge_payload,
        headers={
            **headers,
            "X-WindOps-Test-Principal": "field-technician-7",
            "X-WindOps-Test-Role": "field_technician",
        },
    )
    assert forbidden.status_code == 403

    acknowledged = await client.post(command_path, json=acknowledge_payload, headers=headers)
    assert acknowledged.status_code == 200
    assert acknowledged.headers["Idempotency-Replayed"] == "false"
    body = acknowledged.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_by"] == "integration-test-system"
    assert body["acknowledged_at"]
    assert body["revision"] == 2
    assert body["changed"] is True

    replayed = await client.post(command_path, json=acknowledge_payload, headers=headers)
    assert replayed.status_code == 200
    assert replayed.headers["Idempotency-Replayed"] == "true"
    assert replayed.json() == body

    reused = await client.post(
        command_path,
        json={"action": "assign", "expected_revision": 2},
        headers=headers,
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    stale = await client.post(
        command_path,
        json={"action": "assign", "expected_revision": 1},
        headers={"Idempotency-Key": "alarm-command-stale-001"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVISION_CONFLICT"

    assigned = await client.post(
        command_path,
        json={"action": "assign", "expected_revision": 2},
        headers={"Idempotency-Key": "alarm-command-assign-001"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_to"] == "integration-test-system"
    assert assigned.json()["revision"] == 3

    unassigned = await client.post(
        command_path,
        json={"action": "unassign", "expected_revision": 3},
        headers={"Idempotency-Key": "alarm-command-unassign-001"},
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["assigned_to"] is None
    assert unassigned.json()["revision"] == 4

    collection = await client.get("/api/v1/alarms", params={"turbine_id": "WT-023"})
    persisted = next(item for item in collection.json()["alarms"] if item["alarm_id"] == alarm_id)
    assert persisted["status"] == "acknowledged"
    assert persisted["revision"] == 4
    assert persisted["acknowledged_by"] == "integration-test-system"
    assert persisted["assigned_to"] is None
    assert persisted["updated_at"]

    async with app.state.session_factory() as session:
        event_types = list(
            await session.scalars(
                select(DomainEvent.event_type)
                .where(DomainEvent.aggregate_id == alarm_id)
                .order_by(DomainEvent.sequence)
            )
        )
        receipt_count = await session.scalar(
            select(func.count())
            .select_from(CommandReceipt)
            .where(CommandReceipt.command_type == "alarm.command.v1")
        )
    assert event_types == ["alarm.acknowledged", "alarm.assigned", "alarm.unassigned"]
    assert receipt_count == 3


async def test_resolved_alarm_rejects_operational_commands(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    alarm_id = await _seed_alarm(app, "ALARM-RESOLVED-001")
    async with app.state.session_factory() as session, session.begin():
        alarm = await session.get(Alarm, alarm_id)
        assert alarm is not None
        alarm.status = AlarmStatus.RESOLVED.value
        alarm.resolved_at = datetime.now(UTC)

    response = await client.post(
        f"/api/v1/alarms/{alarm_id}",
        json={"action": "assign", "expected_revision": 1},
        headers={"Idempotency-Key": "alarm-command-resolved-001"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"


async def test_alarm_command_noop_and_missing_paths_are_explicit(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    alarm_id = await _seed_alarm(app, "ALARM-NOOP-001")
    missing = await client.post(
        "/api/v1/alarms/ALARM-MISSING-001",
        json={"action": "assign", "expected_revision": 1},
        headers={"Idempotency-Key": "alarm-command-missing-001"},
    )
    assert missing.status_code == 404

    unassigned = await client.post(
        f"/api/v1/alarms/{alarm_id}",
        json={"action": "unassign", "expected_revision": 1},
        headers={"Idempotency-Key": "alarm-command-noop-001"},
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["changed"] is False
    assert unassigned.json()["revision"] == 1


def test_alarm_command_state_is_migrated() -> None:
    root = Path(__file__).parents[1]
    migration = (root / "alembic" / "versions" / "0015_alarm_command_state.py").read_text(
        encoding="utf-8"
    )
    for column in (
        "acknowledged_at",
        "acknowledged_by",
        "assigned_to",
        "resolved_at",
        "revision",
        "updated_at",
    ):
        assert f'"{column}"' in migration
