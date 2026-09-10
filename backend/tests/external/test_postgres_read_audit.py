from __future__ import annotations

import asyncio
import gzip
import hashlib
import os
from datetime import UTC, datetime, timedelta
from math import ceil
from time import perf_counter

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.models import ReadAccessAudit, ReadAccessAuditArchive
from windops_backend.read_audit import (
    ReadAuditEvent,
    build_read_audit_event,
    ensure_read_audit_partitions,
    maintain_read_audit_retention,
    persist_read_audit_batch,
)

pytestmark = [
    pytest.mark.external_release,
    pytest.mark.skipif(
        os.getenv("WINDOPS_RUN_POSTGRES_READ_AUDIT_TESTS") != "1",
        reason="requires the migrated isolated PostgreSQL contract database",
    ),
]


def _database_url() -> str:
    value = os.getenv("WINDOPS_POSTGRES_TEST_URL", "").strip()
    if value.startswith("postgres://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    if not value:
        raise RuntimeError("WINDOPS_POSTGRES_TEST_URL is required")
    return make_url(value).render_as_string(hide_password=False)


def _event(*, subject: str, at: datetime) -> ReadAuditEvent:
    return build_read_audit_event(
        subject=subject,
        roles=["test_system"],
        method="GET",
        endpoint="/api/v1/turbines",
        query={"search": ["must-never-be-stored"], "limit": ["50"]},
        authorization={
            "tenant_ids": ["tenant-must-never-be-stored"],
            "wind_farm_ids": [],
            "turbine_ids": [],
            "entity_ids": [],
            "data_scopes": ["asset"],
            "allow_global": False,
            "unrestricted": False,
        },
        now=at,
    )


@pytest.mark.asyncio
async def test_real_postgres_batch_partition_and_archive_contract() -> None:
    engine = create_async_engine(_database_url(), pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        environment=Environment.TEST,
        database_url=_database_url(),
        schema_bootstrap=False,
    )
    now = datetime.now(UTC)
    subject = f"postgres-read-audit-{os.getpid()}-{now:%Y%m%d%H%M%S%f}"
    try:
        await ensure_read_audit_partitions(factory, settings)
        events = [
            _event(subject=subject, at=now + timedelta(microseconds=index))
            for index in range(1_000)
        ]
        batch_latencies_ms: list[float] = []
        for start in range(0, len(events), settings.read_audit_batch_size):
            started = perf_counter()
            inserted = await persist_read_audit_batch(
                factory,
                events[start : start + settings.read_audit_batch_size],
            )
            batch_latencies_ms.append((perf_counter() - started) * 1_000)
            assert inserted == settings.read_audit_batch_size

        ordered = sorted(batch_latencies_ms)
        p95_ms = ordered[max(0, ceil(len(ordered) * 0.95) - 1)]
        transaction_count = len(batch_latencies_ms)
        assert transaction_count == 2
        assert transaction_count / len(events) == 0.002
        assert p95_ms < 500

        async with factory() as session:
            stored = await session.scalar(
                select(func.count())
                .select_from(ReadAccessAudit)
                .where(ReadAccessAudit.subject == subject)
            )
            partitions = set(
                (
                    await session.scalars(
                        text(
                            "SELECT child.relname "
                            "FROM pg_inherits "
                            "JOIN pg_class parent ON pg_inherits.inhparent = parent.oid "
                            "JOIN pg_class child ON pg_inherits.inhrelid = child.oid "
                            "WHERE parent.relname = 'read_access_audits'"
                        )
                    )
                ).all()
            )
        assert stored == 1_000
        assert "read_access_audits_default" in partitions
        assert f"read_access_audits_{now:%Y%m}" in partitions

        old_subject = f"{subject}-archive"
        old_events = [
            _event(subject=old_subject, at=now - timedelta(days=31, seconds=index))
            for index in range(3)
        ]
        await persist_read_audit_batch(factory, old_events)
        result = await maintain_read_audit_retention(factory, settings, now=now)
        assert result["archived_rows"] == 3
        async with factory() as session:
            archive = await session.scalar(
                select(ReadAccessAuditArchive).where(
                    ReadAccessAuditArchive.id == result["archive_sha256"]
                )
            )
            old_live_count = await session.scalar(
                select(func.count())
                .select_from(ReadAccessAudit)
                .where(ReadAccessAudit.subject == old_subject)
            )
        assert old_live_count == 0
        assert archive is not None
        assert archive.row_count == 3
        assert hashlib.sha256(archive.payload_gzip).hexdigest() == archive.payload_sha256
        assert len(gzip.decompress(archive.payload_gzip).decode().splitlines()) == 3

        print(
            "read-audit-postgres-evidence "
            f"requests={len(events)} batch_transactions={transaction_count} "
            f"write_amplification={transaction_count / len(events):.4f} "
            f"batch_p95_ms={p95_ms:.3f} partitions={len(partitions)}"
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_postgres_concurrent_maintenance_is_serialized() -> None:
    engine = create_async_engine(_database_url(), pool_size=6, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        environment=Environment.TEST,
        database_url=_database_url(),
        schema_bootstrap=False,
    )
    now = datetime.now(UTC)
    subject = f"postgres-read-audit-concurrent-{os.getpid()}-{now:%Y%m%d%H%M%S%f}"
    events = [
        _event(subject=subject, at=now - timedelta(days=31, seconds=index)) for index in range(25)
    ]
    try:
        await persist_read_audit_batch(factory, events)
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION windops_test_delay_read_audit_archive()
                    RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN
                      PERFORM pg_sleep(0.5);
                      RETURN NEW;
                    END;
                    $$
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TRIGGER windops_test_delay_read_audit_archive
                    BEFORE INSERT ON read_access_audit_archives
                    FOR EACH ROW EXECUTE FUNCTION windops_test_delay_read_audit_archive()
                    """
                )
            )
        results = await asyncio.gather(
            *(maintain_read_audit_retention(factory, settings, now=now) for _ in range(4))
        )
        assert sorted(int(result["archived_rows"]) for result in results) == [0, 0, 0, 25]
        archive_ids = {
            str(result["archive_sha256"])
            for result in results
            if result["archive_sha256"] is not None
        }
        assert len(archive_ids) == 1
        async with factory() as session:
            live = await session.scalar(
                select(func.count())
                .select_from(ReadAccessAudit)
                .where(ReadAccessAudit.subject == subject)
            )
            archives = await session.scalar(
                select(func.count())
                .select_from(ReadAccessAuditArchive)
                .where(ReadAccessAuditArchive.id.in_(archive_ids))
            )
        assert live == 0
        assert archives == 1
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "DROP TRIGGER IF EXISTS windops_test_delay_read_audit_archive "
                    "ON read_access_audit_archives"
                )
            )
            await session.execute(
                text("DROP FUNCTION IF EXISTS windops_test_delay_read_audit_archive()")
            )
        await engine.dispose()
