from __future__ import annotations

import asyncio
import time

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from windops_backend.config import get_settings
from windops_backend.db import create_engine, create_session_factory
from windops_backend.outbox import (
    mark_dispatched,
    pending_event_ids,
    process_outbox_event,
    redelivery_retry_delay_ms,
)
from windops_backend.services.workflow import advance_mission_to_review


def configure_broker(redis_url: str) -> RedisBroker:
    broker = RedisBroker(url=redis_url)
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
                raise dramatiq.Retry(message="outbox event lease is still active", delay=delay)
    finally:
        await engine.dispose()


def dispatch_event_ids(event_ids: list[str]) -> None:
    for event_id in event_ids:
        process_mission_analysis.send(event_id)


async def relay_pending_once() -> int:
    """Dispatch durable pending rows left by API crashes or Redis outages."""

    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        event_ids = await pending_event_ids(factory)
        dispatch_event_ids(event_ids)
        await mark_dispatched(factory, event_ids)
        return len(event_ids)
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
