from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.config import Settings
from windops_backend.errors import InvalidTransitionError, NotFoundError
from windops_backend.models import (
    ExternalWorkOrderLink,
    Resource,
    ResourceReservation,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.outbox import (
    OutboxLeaseLostError,
    assert_current_claim,
    claim_event,
    mark_event_failed,
    mark_event_succeeded,
)
from windops_backend.schemas import EamWorkOrderStatusUpdate
from windops_backend.services.events import append_domain_event
from windops_backend.storage import OutboxEvent

EAM_WORK_ORDER_PUBLISH_REQUESTED = "eam.work-order.publish.requested"


@dataclass(frozen=True)
class EamPublishResult:
    external_id: str
    status: str
    external_updated_at: datetime | None = None


class EamPublisher(Protocol):
    async def publish(
        self, payload: dict[str, Any], *, idempotency_key: str
    ) -> EamPublishResult: ...


class HttpEamPublisher:
    """Strict HTTPS EAM adapter; credentials never enter domain payloads or logs."""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.eam_base_url.rstrip("/")
        self.token = settings.eam_api_token.get_secret_value()
        self.timeout = settings.eam_timeout_seconds

    async def publish(self, payload: dict[str, Any], *, idempotency_key: str) -> EamPublishResult:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            response = await client.post(
                f"{self.base_url}/work-orders",
                json=payload,
                headers={
                    "accept": "application/json",
                    "authorization": f"Bearer {self.token}",
                    "content-type": "application/json",
                    "idempotency-key": idempotency_key,
                },
            )
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("EAM returned a non-object work-order response")
        external_id = str(body.get("id", "")).strip()
        status = str(body.get("status", "")).strip()
        if not external_id or not status:
            raise RuntimeError("EAM response must include id and status")
        external_updated_at = None
        if body.get("updated_at"):
            external_updated_at = datetime.fromisoformat(
                str(body["updated_at"]).replace("Z", "+00:00")
            )
            if external_updated_at.tzinfo is None:
                raise RuntimeError("EAM updated_at must include an explicit timezone")
        return EamPublishResult(
            external_id=external_id,
            status=status,
            external_updated_at=external_updated_at,
        )


def enqueue_eam_work_order_publish(
    session: AsyncSession,
    work_order_id: str,
) -> OutboxEvent:
    event = OutboxEvent(
        event_type=EAM_WORK_ORDER_PUBLISH_REQUESTED,
        aggregate_type="work_order",
        aggregate_id=work_order_id,
        payload={"work_order_id": work_order_id},
    )
    session.add(event)
    return event


async def _work_order_payload(
    session: AsyncSession, work_order_id: str
) -> tuple[dict[str, Any], str]:
    work_order = await session.get(WorkOrder, work_order_id)
    if work_order is None:
        raise NotFoundError(f"work order {work_order_id} was not found")
    tasks = list(
        (
            await session.scalars(
                select(WorkOrderTask)
                .where(WorkOrderTask.work_order_id == work_order_id)
                .order_by(WorkOrderTask.sequence)
            )
        ).all()
    )
    reservations = list(
        (
            await session.scalars(
                select(ResourceReservation).where(
                    ResourceReservation.mission_id == work_order.mission_id
                )
            )
        ).all()
    )
    resource_ids = [reservation.resource_id for reservation in reservations]
    resources = (
        list((await session.scalars(select(Resource).where(Resource.id.in_(resource_ids)))).all())
        if resource_ids
        else []
    )
    resource_by_id = {resource.id: resource for resource in resources}
    payload = {
        "source_system": "windops",
        "work_order_id": work_order.id,
        "mission_id": work_order.mission_id,
        "approval_id": work_order.approval_id,
        "turbine_id": work_order.turbine_id,
        "title": work_order.title,
        "status": work_order.status,
        "priority": work_order.priority,
        "assigned_team": work_order.assigned_team,
        "selected_alternative_id": work_order.selected_alternative_id,
        "selected_action": work_order.selected_action,
        "planned_start": work_order.planned_start.isoformat() if work_order.planned_start else None,
        "deadline": work_order.deadline.isoformat() if work_order.deadline else None,
        "estimated_duration_hours": work_order.estimated_duration_hours,
        "safety_plan": work_order.safety_plan,
        "tasks": [
            {
                "task_id": task.id,
                "sequence": task.sequence,
                "title": task.title,
                "schema_version": task.schema_version,
                "measurement_schema": task.measurement_schema,
            }
            for task in tasks
        ],
        "resources": [
            {
                "resource_id": reservation.resource_id,
                "resource_type": resource_by_id[reservation.resource_id].resource_type,
                "name": resource_by_id[reservation.resource_id].name,
                "quantity": reservation.quantity,
            }
            for reservation in reservations
            if reservation.resource_id in resource_by_id
        ],
        "created_at": work_order.created_at.isoformat(),
        "updated_at": work_order.updated_at.isoformat(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return payload, hashlib.sha256(canonical).hexdigest()


async def process_eam_publish_event(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    event_id: str,
    publisher: EamPublisher | None = None,
) -> bool:
    async with factory() as claim_session:
        async with claim_session.begin():
            event = await claim_event(claim_session, event_id)
        if event is None:
            return False
        claim_token = event.claim_token
        if claim_token is None:  # pragma: no cover - protected by claim update
            raise RuntimeError("claimed EAM event has no fencing token")
        if event.event_type != EAM_WORK_ORDER_PUBLISH_REQUESTED:
            error = ValueError(f"unexpected EAM event type: {event.event_type}")
            await mark_event_failed(factory, event_id, claim_token, error)
            raise error
        work_order_id = str(event.payload["work_order_id"])
        try:
            async with factory() as read_session:
                payload, payload_hash = await _work_order_payload(read_session, work_order_id)
                existing_link = await read_session.get(ExternalWorkOrderLink, work_order_id)
            # A crash can happen after the authoritative link commits but before the
            # outbox row is acknowledged. The persisted payload hash is the local
            # completion marker, so retries must not call or overwrite EAM again.
            if existing_link is not None and existing_link.last_payload_hash == payload_hash:
                return await mark_event_succeeded(factory, event_id, claim_token)
            result = await (publisher or HttpEamPublisher(settings)).publish(
                payload,
                idempotency_key=f"windops:{work_order_id}",
            )
            async with factory() as write_session, write_session.begin():
                await assert_current_claim(write_session, event_id, claim_token)
                link = await write_session.get(ExternalWorkOrderLink, work_order_id)
                now = datetime.now(UTC)
                if link is None:
                    link = ExternalWorkOrderLink(
                        work_order_id=work_order_id,
                        provider="eam",
                        external_id=result.external_id,
                        sync_status=result.status,
                        last_payload_hash=payload_hash,
                        external_updated_at=result.external_updated_at,
                        updated_at=now,
                    )
                    write_session.add(link)
                else:
                    if link.external_id != result.external_id:
                        raise InvalidTransitionError(
                            "EAM idempotency returned a different external work-order ID"
                        )
                    link.last_payload_hash = payload_hash
                    current_external_at = link.external_updated_at
                    if current_external_at is not None and current_external_at.tzinfo is None:
                        current_external_at = current_external_at.replace(tzinfo=UTC)
                    if current_external_at is None or (
                        result.external_updated_at is not None
                        and result.external_updated_at >= current_external_at
                    ):
                        link.sync_status = result.status
                        link.external_updated_at = result.external_updated_at
                    link.updated_at = now
                append_domain_event(
                    write_session,
                    event_type="eam.work_order.published",
                    aggregate_type="work_order",
                    aggregate_id=work_order_id,
                    payload={
                        "work_order_id": work_order_id,
                        "external_id": result.external_id,
                        "sync_status": link.sync_status,
                    },
                )
        except asyncio.CancelledError:
            # Keep the outbox lease recoverable during worker shutdown. A
            # cancellation is not an EAM delivery failure.
            raise
        except OutboxLeaseLostError:
            return False
        except BaseException as exc:
            await mark_event_failed(factory, event_id, claim_token, exc)
            raise
    return await mark_event_succeeded(factory, event_id, claim_token)


async def record_eam_status(
    session: AsyncSession,
    work_order_id: str,
    update: EamWorkOrderStatusUpdate,
    *,
    subject: str,
) -> tuple[ExternalWorkOrderLink, bool]:
    link = await session.scalar(
        select(ExternalWorkOrderLink)
        .where(ExternalWorkOrderLink.work_order_id == work_order_id)
        .with_for_update()
    )
    if link is None:
        raise NotFoundError(f"work order {work_order_id} has not been published to EAM")
    if link.external_id != update.external_id:
        raise InvalidTransitionError("EAM callback external_id does not match the published link")
    incoming_at = update.external_updated_at.astimezone(UTC)
    current_at = link.external_updated_at
    if current_at is not None and current_at.tzinfo is None:
        current_at = current_at.replace(tzinfo=UTC)
    if current_at is not None and incoming_at < current_at:
        raise InvalidTransitionError("stale EAM status callbacks cannot overwrite newer state")
    if current_at == incoming_at and link.sync_status == update.status:
        return link, True
    link.sync_status = update.status
    link.external_updated_at = incoming_at
    link.updated_at = datetime.now(UTC)
    append_domain_event(
        session,
        event_type="eam.work_order.status_updated",
        aggregate_type="work_order",
        aggregate_id=work_order_id,
        payload={
            "work_order_id": work_order_id,
            "external_id": link.external_id,
            "sync_status": link.sync_status,
            "external_updated_at": incoming_at.isoformat(),
            "recorded_by": subject,
        },
    )
    await session.flush()
    return link, False
