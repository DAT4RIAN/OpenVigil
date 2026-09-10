import asyncio
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from windops_backend.services.models import _claim_prediction_key

pytestmark = [
    pytest.mark.external_release,
    pytest.mark.skipif(
        os.getenv("WINDOPS_RUN_POSTGRES_CONCURRENCY_TESTS") != "1",
        reason="requires an isolated PostgreSQL test database",
    ),
]


def _async_database_url() -> str:
    value = os.getenv("WINDOPS_POSTGRES_TEST_URL", "").strip()
    if value.startswith("postgres://"):
        return "postgresql+asyncpg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize("iteration", range(3))
async def test_postgres_prediction_lock_releases_after_item_commit(iteration: int) -> None:
    database_url = _async_database_url()
    if not database_url:
        pytest.skip("WINDOPS_POSTGRES_TEST_URL is not configured")

    engine = create_async_engine(database_url, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    observed_at = datetime(2026, 8, 14, 9, 30, tzinfo=UTC)
    acquired = asyncio.Event()
    second_connection_ready = asyncio.Event()

    async def claim_from_second_session() -> None:
        async with factory() as second_session:
            await second_session.connection()
            second_connection_ready.set()
            async with _claim_prediction_key(
                second_session,
                f"deployment-concurrency-test-{iteration}",
                "WT-023",
                observed_at,
            ):
                acquired.set()

    try:
        async with factory() as first_session:
            async with _claim_prediction_key(
                first_session,
                f"deployment-concurrency-test-{iteration}",
                "WT-023",
                observed_at,
            ):
                second_task = asyncio.create_task(claim_from_second_session())
                await asyncio.wait_for(second_connection_ready.wait(), timeout=10)
                await asyncio.sleep(0.05)
                assert not acquired.is_set()

            # The API commits after each turbine. A transaction-scoped
            # advisory lock must be available to the other session now.
            await first_session.commit()
            await asyncio.wait_for(acquired.wait(), timeout=5)
            await asyncio.wait_for(second_task, timeout=5)
    finally:
        await engine.dispose()
