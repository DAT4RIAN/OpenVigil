from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.config import Settings
from windops_backend.enums import ExecutionStatus
from windops_backend.knowledge_graph.projection import ProjectionLimits
from windops_backend.knowledge_graph.service import project_authoritative_graph
from windops_backend.knowledge_graph.store import KnowledgeGraphStore
from windops_backend.models import AgentExecution
from windops_backend.storage import OutboxEvent

MISSION_ANALYSIS_REQUESTED = "mission.analysis.requested"
KNOWLEDGE_GRAPH_PROJECTION_REQUESTED = "knowledge-graph.projection.requested"
OUTBOX_LEASE = timedelta(minutes=5)
# Redis delivery is considered visible for one lease window.  A relay that
# sent an event but never sees the worker claim it must get another chance.
OUTBOX_DISPATCH_VISIBILITY = timedelta(minutes=5)


class OutboxLeaseLostError(RuntimeError):
    """Raised internally when a stale worker no longer owns an event lease."""


def enqueue_mission_analysis(session: AsyncSession, mission_id: str) -> OutboxEvent:
    event = OutboxEvent(
        event_type=MISSION_ANALYSIS_REQUESTED,
        aggregate_type="mission",
        aggregate_id=mission_id,
        payload={"mission_id": mission_id},
    )
    session.add(event)
    return event


def enqueue_knowledge_graph_projection(
    session: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: str,
    reason: str,
) -> OutboxEvent:
    """Request an idempotent rebuild of the derived graph projection.

    The row is committed in the same PostgreSQL transaction as the authoritative
    business mutation. Replaying it is safe because the projector replaces the
    named Neo4j projection from current SQL state.
    """

    event = OutboxEvent(
        event_type=KNOWLEDGE_GRAPH_PROJECTION_REQUESTED,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload={
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "reason": reason,
        },
    )
    session.add(event)
    return event


async def claim_event(session: AsyncSession, event_id: str) -> OutboxEvent | None:
    now = datetime.now(UTC)
    stale_before = now - OUTBOX_LEASE
    claim_token = str(uuid4())
    result = await session.execute(
        update(OutboxEvent)
        .where(
            OutboxEvent.id == event_id,
            (
                OutboxEvent.status.in_(("pending", "dispatched", "failed"))
                | (
                    (OutboxEvent.status == "processing")
                    & or_(
                        OutboxEvent.lease_expires_at <= now,
                        (
                            OutboxEvent.lease_expires_at.is_(None)
                            & (OutboxEvent.claimed_at < stale_before)
                        ),
                    )
                )
            ),
        )
        .values(
            status="processing",
            attempts=OutboxEvent.attempts + 1,
            last_error=None,
            claimed_at=now,
            claim_token=claim_token,
            lease_expires_at=now + OUTBOX_LEASE,
        )
    )
    if getattr(result, "rowcount", 0) != 1:
        return None
    await session.flush()
    return await session.get(OutboxEvent, event_id)


async def mark_event_succeeded(
    factory: async_sessionmaker[AsyncSession], event_id: str, claim_token: str
) -> bool:
    async with factory() as session, session.begin():
        result = await session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.id == event_id,
                OutboxEvent.status == "processing",
                OutboxEvent.claim_token == claim_token,
            )
            .values(
                status="succeeded",
                processed_at=datetime.now(UTC),
                last_error=None,
                claim_token=None,
                lease_expires_at=None,
            )
        )
        return getattr(result, "rowcount", 0) == 1


async def persist_failure_audit(
    factory: async_sessionmaker[AsyncSession],
    *,
    mission_id: str,
    node: str,
    error: BaseException,
) -> None:
    """Persist failure after the failed graph transaction has been rolled back."""

    context = getattr(error, "windops_public_context", {})
    if not isinstance(context, dict):
        context = {}
    async with factory() as session, session.begin():
        session.add(
            AgentExecution(
                id=__import__("uuid").uuid4().hex,
                mission_id=mission_id,
                catalog_version_id=context.get("catalog_version_id"),
                agent_definition_id=context.get("agent_definition_id"),
                node=str(context.get("node", node)),
                agent_role=str(context.get("agent_role", "workflow_dispatcher")),
                status=ExecutionStatus.FAILED.value,
                input_refs=context.get("input_refs", {"mission_id": mission_id}),
                public_output=context.get(
                    "public_output",
                    {
                        "failure": {
                            "node": node,
                            "error_code": type(error).__name__,
                            "message": ("Workflow dispatch failed; inspect secured worker logs."),
                        }
                    },
                ),
                tool_calls=context.get("tool_calls", []),
                latency_ms=int(context.get("latency_ms", 0)),
                provider=str(context.get("provider", "dramatiq")),
                model=context.get("model"),
                token_usage=context.get(
                    "token_usage",
                    {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "source": "not_available_after_failure",
                    },
                ),
                evaluation_result=context.get("evaluation_result", {}),
                degradation_policy=context.get("degradation_policy", {}),
                error_code=str(context.get("error_code", type(error).__name__)),
                completed_at=datetime.now(UTC),
            )
        )


async def mark_event_failed(
    factory: async_sessionmaker[AsyncSession], event_id: str, claim_token: str, error: BaseException
) -> bool:
    async with factory() as session, session.begin():
        result = await session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.id == event_id,
                OutboxEvent.status == "processing",
                OutboxEvent.claim_token == claim_token,
            )
            .values(
                status="failed",
                processed_at=datetime.now(UTC),
                last_error=f"{type(error).__name__}: {error}"[:4000],
                claimed_at=None,
                claim_token=None,
                lease_expires_at=None,
            )
        )
        return getattr(result, "rowcount", 0) == 1


async def assert_current_claim(session: AsyncSession, event_id: str, claim_token: str) -> None:
    event = await session.scalar(
        select(OutboxEvent)
        .where(OutboxEvent.id == event_id, OutboxEvent.status == "processing")
        .with_for_update()
    )
    now = datetime.now(UTC)
    lease_expires_at = event.lease_expires_at if event is not None else None
    if lease_expires_at is not None and lease_expires_at.tzinfo is None:
        lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
    if (
        event is None
        or event.claim_token != claim_token
        or lease_expires_at is None
        or lease_expires_at <= now
    ):
        raise OutboxLeaseLostError(f"outbox lease for {event_id} was fenced by a newer worker")


async def process_outbox_event(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    event_id: str,
    handler: Callable[[AsyncSession, Settings, str], Awaitable[Any]],
) -> bool:
    async with factory() as session:
        async with session.begin():
            event = await claim_event(session, event_id)
        if event is None:
            return False
        claim_token = event.claim_token
        if claim_token is None:  # pragma: no cover - protected by claim update
            raise RuntimeError("claimed outbox event has no fencing token")
        mission_id = str(event.payload["mission_id"])
        try:
            async with session.begin():
                await handler(session, settings, mission_id)
                await assert_current_claim(session, event_id, claim_token)
        except asyncio.CancelledError:
            # Cancellation means the worker is shutting down or the lease
            # holder lost its execution slot. Leave the row as `processing`
            # so the lease reaper can reclaim it instead of recording a false
            # terminal failure.
            raise
        except OutboxLeaseLostError:
            return False
        except BaseException as exc:
            marked = await mark_event_failed(factory, event_id, claim_token, exc)
            if marked:
                await persist_failure_audit(
                    factory, mission_id=mission_id, node="workflow", error=exc
                )
            raise
    return await mark_event_succeeded(factory, event_id, claim_token)


async def process_knowledge_graph_projection_event(
    factory: async_sessionmaker[AsyncSession],
    event_id: str,
    store: KnowledgeGraphStore,
    limits: ProjectionLimits | None = None,
) -> bool:
    """Project the latest authoritative SQL state into Neo4j under a fenced lease."""

    async with factory() as session:
        async with session.begin():
            event = await claim_event(session, event_id)
        if event is None:
            return False
        claim_token = event.claim_token
        if claim_token is None:  # pragma: no cover - protected by claim update
            raise RuntimeError("claimed outbox event has no fencing token")
        if event.event_type != KNOWLEDGE_GRAPH_PROJECTION_REQUESTED:
            error = ValueError(f"unexpected graph projection event type: {event.event_type}")
            await mark_event_failed(factory, event_id, claim_token, error)
            raise error
        try:
            async with session.begin():
                created_at = event.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                await project_authoritative_graph(
                    session,
                    store,
                    projection_sequence=f"{created_at.isoformat()}:{event.id}",
                    limits=limits,
                )
                await assert_current_claim(session, event_id, claim_token)
        except asyncio.CancelledError:
            raise
        except OutboxLeaseLostError:
            return False
        except BaseException as exc:
            await mark_event_failed(factory, event_id, claim_token, exc)
            raise
    return await mark_event_succeeded(factory, event_id, claim_token)


async def pending_events_for_missions(session: AsyncSession, mission_ids: list[str]) -> list[str]:
    if not mission_ids:
        return []
    return list(
        (
            await session.scalars(
                select(OutboxEvent.id).where(
                    OutboxEvent.event_type == MISSION_ANALYSIS_REQUESTED,
                    OutboxEvent.aggregate_id.in_(mission_ids),
                    OutboxEvent.status == "pending",
                )
            )
        ).all()
    )


async def pending_event_ids(
    factory: async_sessionmaker[AsyncSession], limit: int = 100
) -> list[str]:
    async with factory() as session:
        return list(
            (
                await session.scalars(
                    select(OutboxEvent.id)
                    .where(OutboxEvent.status == "pending")
                    .order_by(OutboxEvent.created_at)
                    .limit(limit)
                )
            ).all()
        )


async def pending_event_ids_by_type(
    factory: async_sessionmaker[AsyncSession], event_type: str, limit: int = 100
) -> list[str]:
    async with factory() as session:
        return list(
            (
                await session.scalars(
                    select(OutboxEvent.id)
                    .where(
                        OutboxEvent.status == "pending",
                        OutboxEvent.event_type == event_type,
                    )
                    .order_by(OutboxEvent.created_at)
                    .limit(limit)
                )
            ).all()
        )


async def pending_events(
    factory: async_sessionmaker[AsyncSession], limit: int = 100
) -> list[tuple[str, str]]:
    stale_before = datetime.now(UTC) - OUTBOX_DISPATCH_VISIBILITY
    async with factory() as session:
        rows = (
            await session.execute(
                select(OutboxEvent.id, OutboxEvent.event_type)
                .where(
                    or_(
                        OutboxEvent.status == "pending",
                        (
                            (OutboxEvent.status == "dispatched")
                            & or_(
                                OutboxEvent.dispatched_at <= stale_before,
                                OutboxEvent.dispatched_at.is_(None),
                            )
                        ),
                    )
                )
                .order_by(OutboxEvent.created_at)
                .limit(limit)
            )
        ).all()
        return [(str(event_id), str(event_type)) for event_id, event_type in rows]


async def mark_dispatched(factory: async_sessionmaker[AsyncSession], event_ids: list[str]) -> None:
    if not event_ids:
        return
    async with factory() as session, session.begin():
        await session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.id.in_(event_ids),
                OutboxEvent.status.in_(("pending", "dispatched")),
            )
            .values(status="dispatched", dispatched_at=datetime.now(UTC))
        )


async def redelivery_retry_delay_ms(
    factory: async_sessionmaker[AsyncSession], event_id: str
) -> int | None:
    """Return remaining lease delay only for an actively claimed event."""

    async with factory() as session:
        event = await session.get(OutboxEvent, event_id)
        if event is None or event.status in {"succeeded", "failed"}:
            return None
        if event.status != "processing" or event.claimed_at is None:
            return 1_000
        claimed_at = event.claimed_at
        if claimed_at.tzinfo is None:
            claimed_at = claimed_at.replace(tzinfo=UTC)
        if event.lease_expires_at is not None:
            lease_expires_at = event.lease_expires_at
            if lease_expires_at.tzinfo is None:
                lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
            remaining = lease_expires_at - datetime.now(UTC)
        else:
            remaining = OUTBOX_LEASE - (datetime.now(UTC) - claimed_at)
        return max(1_000, round(remaining.total_seconds() * 1000))
