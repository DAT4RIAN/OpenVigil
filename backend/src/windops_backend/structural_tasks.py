"""Dedicated Dramatiq entrypoint: --queues structural-analysis --threads 1."""

import asyncio

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from minio import Minio

from windops_backend.config import get_settings
from windops_backend.db import create_engine, create_session_factory
from windops_backend.outbox import redelivery_retry_delay_ms
from windops_backend.storage import MinioArtifactVerifier
from windops_backend.structural_worker import process_structural_event

dramatiq.set_broker(RedisBroker(url=get_settings().redis_url))  # type: ignore[no-untyped-call]


@dramatiq.actor(
    queue_name="structural-analysis",
    max_retries=2,
    time_limit=180_000,
    min_backoff=5_000,
    max_backoff=60_000,
)
def process_structural_analysis(event_id: str) -> None:
    asyncio.run(_process(event_id))


async def _process(event_id: str) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key.get_secret_value(),
        secure=settings.minio_secure,
    )
    verifier = MinioArtifactVerifier(client, settings.minio_field_evidence_bucket)
    try:
        processed = await process_structural_event(
            factory, verifier, settings.minio_field_evidence_bucket, event_id, settings=settings
        )
        if not processed:
            delay = await redelivery_retry_delay_ms(factory, event_id)
            if delay is not None:
                raise dramatiq.Retry(message="structural analysis lease is active", delay=delay)  # type: ignore[no-untyped-call]
    finally:
        await engine.dispose()
