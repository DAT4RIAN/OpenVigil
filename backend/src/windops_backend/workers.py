from __future__ import annotations

import asyncio
import time

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from windops_backend.config import get_settings
from windops_backend.db import create_engine, create_session_factory
from windops_backend.knowledge_graph.factory import create_knowledge_graph_store
from windops_backend.knowledge_graph.projection import ProjectionLimits
from windops_backend.outbox import (
    KNOWLEDGE_GRAPH_PROJECTION_REQUESTED,
    MISSION_ANALYSIS_REQUESTED,
    mark_dispatched,
    pending_events,
    process_knowledge_graph_projection_event,
    process_outbox_event,
    redelivery_retry_delay_ms,
)
from windops_backend.services.eam import (
    EAM_WORK_ORDER_PUBLISH_REQUESTED,
    process_eam_publish_event,
)
from windops_backend.services.knowledge import (
    KNOWLEDGE_DOCUMENT_INDEX_REQUESTED,
    process_knowledge_document_index_event,
)
from windops_backend.services.workflow import advance_mission_to_review


def configure_broker(redis_url: str) -> RedisBroker:
    broker = RedisBroker(url=redis_url)  # type: ignore[no-untyped-call]
    dramatiq.set_broker(broker)
    return broker


configure_broker(get_settings().redis_url)


@dramatiq.actor(max_retries=5, min_backoff=1_000, max_backoff=60_000)
def process_mission_analysis(event_id: str) -> None:
    """Production entrypoint. API processes never execute the agent graph inline."""

    asyncio.run(_process(event_id))


async def _process(event_id: str) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        processed = await process_outbox_event(
            factory, settings, event_id, advance_mission_to_review
        )
        if not processed:
            delay = await redelivery_retry_delay_ms(factory, event_id)
            if delay is not None:
                raise dramatiq.Retry(  # type: ignore[no-untyped-call]
                    message="outbox event lease is still active", delay=delay
                )
    finally:
        await engine.dispose()


@dramatiq.actor(max_retries=5, min_backoff=1_000, max_backoff=60_000)
def project_knowledge_graph(event_id: str) -> None:
    """Rebuild the Neo4j read projection from authoritative PostgreSQL state."""

    asyncio.run(_project(event_id))


async def _project(event_id: str) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    store = create_knowledge_graph_store(settings)
    try:
        processed = await process_knowledge_graph_projection_event(
            factory,
            event_id,
            store,
            ProjectionLimits.from_settings(settings),
        )
        if not processed:
            delay = await redelivery_retry_delay_ms(factory, event_id)
            if delay is not None:
                raise dramatiq.Retry(  # type: ignore[no-untyped-call]
                    message="outbox event lease is still active", delay=delay
                )
    finally:
        await store.close()
        await engine.dispose()


def dispatch_event_ids(event_ids: list[str]) -> None:
    for event_id in event_ids:
        process_mission_analysis.send(event_id)


def dispatch_graph_event_ids(event_ids: list[str]) -> None:
    for event_id in event_ids:
        project_knowledge_graph.send(event_id)


@dramatiq.actor(max_retries=8, min_backoff=2_000, max_backoff=300_000)
def publish_eam_work_order(event_id: str) -> None:
    """Publish approved work orders with an idempotency key and fenced retry lease."""

    asyncio.run(_publish_eam(event_id))


async def _publish_eam(event_id: str) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        processed = await process_eam_publish_event(factory, settings, event_id)
        if not processed:
            delay = await redelivery_retry_delay_ms(factory, event_id)
            if delay is not None:
                raise dramatiq.Retry(  # type: ignore[no-untyped-call]
                    message="EAM outbox event lease is still active", delay=delay
                )
    finally:
        await engine.dispose()


def dispatch_eam_event_ids(event_ids: list[str]) -> None:
    for event_id in event_ids:
        publish_eam_work_order.send(event_id)


@dramatiq.actor(max_retries=8, min_backoff=2_000, max_backoff=300_000)
def index_knowledge_document(event_id: str) -> None:
    """Extracted text is embedded asynchronously with a fenced durable claim."""

    asyncio.run(_index_knowledge_document(event_id))


async def _index_knowledge_document(event_id: str) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        processed = await process_knowledge_document_index_event(factory, settings, event_id)
        if not processed:
            delay = await redelivery_retry_delay_ms(factory, event_id)
            if delay is not None:
                raise dramatiq.Retry(  # type: ignore[no-untyped-call]
                    message="knowledge index outbox lease is still active", delay=delay
                )
    finally:
        await engine.dispose()


def dispatch_knowledge_document_event_ids(event_ids: list[str]) -> None:
    for event_id in event_ids:
        index_knowledge_document.send(event_id)


async def relay_pending_once() -> int:
    """Dispatch pending rows and visibility-expired deliveries left by outages."""

    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        event_rows = await pending_events(factory)
        dispatched: list[str] = []
        for event_id, event_type in event_rows:
            if event_type == MISSION_ANALYSIS_REQUESTED:
                process_mission_analysis.send(event_id)
                dispatched.append(event_id)
            elif event_type == KNOWLEDGE_GRAPH_PROJECTION_REQUESTED:
                project_knowledge_graph.send(event_id)
                dispatched.append(event_id)
            elif event_type == EAM_WORK_ORDER_PUBLISH_REQUESTED:
                publish_eam_work_order.send(event_id)
                dispatched.append(event_id)
            elif event_type == KNOWLEDGE_DOCUMENT_INDEX_REQUESTED:
                index_knowledge_document.send(event_id)
                dispatched.append(event_id)
        await mark_dispatched(factory, dispatched)
        return len(dispatched)
    finally:
        await engine.dispose()


def run_outbox_relay() -> None:
    """Production relay process; run alongside Dramatiq workers."""

    while True:
        try:
            asyncio.run(relay_pending_once())
        except Exception:
            # Redis/database outages leave events pending for the next iteration.
            time.sleep(5)
        else:
            time.sleep(2)
