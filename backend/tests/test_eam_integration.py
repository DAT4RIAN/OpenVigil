from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from windops_backend.enums import AlarmSeverity
from windops_backend.models import (
    Alarm,
    DomainEvent,
    ExternalWorkOrderLink,
    IngestReceipt,
)
from windops_backend.services.eam import (
    EAM_WORK_ORDER_PUBLISH_REQUESTED,
    EamPublishResult,
    enqueue_eam_work_order_publish,
    process_eam_publish_event,
)
from windops_backend.storage import OutboxEvent


class RecordingPublisher:
    def __init__(self, result: EamPublishResult) -> None:
        self.result = result
        self.calls: list[tuple[dict[str, Any], str]] = []

    async def publish(self, payload: dict[str, Any], *, idempotency_key: str) -> EamPublishResult:
        self.calls.append((payload, idempotency_key))
        return self.result


class RejectingPublisher:
    async def publish(self, payload: dict[str, Any], *, idempotency_key: str) -> EamPublishResult:
        raise AssertionError(f"completed publish was repeated for {idempotency_key}: {payload}")


async def _create_approved_work_order(app: FastAPI, client: AsyncClient) -> str:
    source_event_id = "source-alarm-eam-001"
    async with app.state.session_factory() as session, session.begin():
        session.add(
            IngestReceipt(
                source_event_id=source_event_id,
                payload_hash="e" * 64,
            )
        )
        session.add(
            Alarm(
                id="ALARM-EAM-001",
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
    mission = await client.post(
        "/api/v1/missions",
        headers={"Idempotency-Key": "eam-integration-mission-001"},
        json={
            "alarm_id": "ALARM-EAM-001",
            "title": "WT-023 EAM integration verification",
            "analysis_profile": {
                "component": "gearbox",
                "primary_variable": "gearbox_oil_temperature",
                "related_variables": ["active_power", "gearbox_oil_pressure"],
                "failure_mode_hint": "lubrication cooling degradation",
                "knowledge_query": "gearbox oil temperature cooling inspection",
            },
        },
    )
    assert mission.status_code == 202
    mission_id = mission.json()["mission_id"]
    detail = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    app.state.settings.eam_enabled = True
    approved = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        headers={"Idempotency-Key": "eam-mission-approval-001"},
        json={
            "action": "approve",
            "expected_revision": detail["revision"],
            "selected_alternative_id": "ALT-A",
            "reason": "Governed EAM integration test approval",
        },
    )
    assert approved.status_code == 200
    return str(approved.json()["work_order_id"])


async def test_eam_publish_retry_and_status_callback_are_idempotent(
    app: FastAPI, client: AsyncClient
) -> None:
    work_order_id = await _create_approved_work_order(app, client)
    pending_detail = (await client.get(f"/api/v1/work-orders/{work_order_id}")).json()
    assert pending_detail["eam"] == {"sync_status": "pending"}

    async with app.state.session_factory() as session:
        event = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.event_type == EAM_WORK_ORDER_PUBLISH_REQUESTED,
                OutboxEvent.aggregate_id == work_order_id,
            )
        )
        assert event is not None and event.status == "pending"
        event_id = event.id

    published_at = datetime.now(UTC).replace(microsecond=0)
    publisher = RecordingPublisher(
        EamPublishResult(
            external_id="EAM-WO-9001",
            status="accepted",
            external_updated_at=published_at,
        )
    )
    assert await process_eam_publish_event(
        app.state.session_factory,
        app.state.settings,
        event_id,
        publisher,
    )
    assert len(publisher.calls) == 1
    outbound, idempotency_key = publisher.calls[0]
    assert idempotency_key == f"windops:{work_order_id}"
    assert outbound["work_order_id"] == work_order_id
    assert outbound["selected_alternative_id"] == "ALT-A"
    assert outbound["tasks"]
    assert outbound["resources"]

    published_detail = (await client.get(f"/api/v1/work-orders/{work_order_id}")).json()
    assert published_detail["eam"]["external_id"] == "EAM-WO-9001"
    assert published_detail["eam"]["sync_status"] == "accepted"

    async with app.state.session_factory() as session, session.begin():
        duplicate = enqueue_eam_work_order_publish(session, work_order_id)
        await session.flush()
        duplicate_id = duplicate.id
    assert await process_eam_publish_event(
        app.state.session_factory,
        app.state.settings,
        duplicate_id,
        RejectingPublisher(),
    )

    callback_at = published_at + timedelta(minutes=5)
    callback_headers = {
        "X-WindOps-Test-Principal": "eam-callback",
        "X-WindOps-Test-Role": "eam_integrator",
        "Idempotency-Key": "eam-callback-in-progress-001",
    }
    callback_payload = {
        "external_id": "EAM-WO-9001",
        "status": "in_progress",
        "external_updated_at": callback_at.isoformat(),
    }
    callback = await client.post(
        f"/api/v1/integrations/eam/work-orders/{work_order_id}/status",
        headers=callback_headers,
        json=callback_payload,
    )
    assert callback.status_code == 200
    assert callback.json()["replayed"] is False

    replay = await client.post(
        f"/api/v1/integrations/eam/work-orders/{work_order_id}/status",
        headers=callback_headers,
        json=callback_payload,
    )
    assert replay.status_code == 200
    assert replay.json() == callback.json()
    assert replay.headers["Idempotency-Replayed"] == "true"

    stale = await client.post(
        f"/api/v1/integrations/eam/work-orders/{work_order_id}/status",
        headers={**callback_headers, "Idempotency-Key": "eam-callback-stale-001"},
        json={
            **callback_payload,
            "status": "accepted",
            "external_updated_at": published_at.isoformat(),
        },
    )
    assert stale.status_code == 422
    assert stale.json()["error"]["code"] == "INVALID_TRANSITION"

    forbidden = await client.post(
        f"/api/v1/integrations/eam/work-orders/{work_order_id}/status",
        headers={
            "X-WindOps-Test-Principal": "human-approver",
            "X-WindOps-Test-Role": "operations_approver",
            "Idempotency-Key": "eam-callback-forbidden-001",
        },
        json=callback_payload,
    )
    assert forbidden.status_code == 403

    async with app.state.session_factory() as session:
        link = await session.get(ExternalWorkOrderLink, work_order_id)
        assert link is not None
        assert link.sync_status == "in_progress"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DomainEvent)
                .where(DomainEvent.event_type == "eam.work_order.published")
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DomainEvent)
                .where(DomainEvent.event_type == "eam.work_order.status_updated")
            )
            == 1
        )


async def test_eam_callback_rejects_unknown_external_identity(
    app: FastAPI, client: AsyncClient
) -> None:
    work_order_id = await _create_approved_work_order(app, client)
    callback = await client.post(
        f"/api/v1/integrations/eam/work-orders/{work_order_id}/status",
        headers={
            "X-WindOps-Test-Principal": "eam-callback",
            "X-WindOps-Test-Role": "eam_integrator",
            "Idempotency-Key": "eam-callback-unknown-001",
        },
        json={
            "external_id": "EAM-UNKNOWN",
            "status": "accepted",
            "external_updated_at": datetime.now(UTC).isoformat(),
        },
    )
    assert callback.status_code == 404
    assert callback.json()["error"]["code"] == "NOT_FOUND"
