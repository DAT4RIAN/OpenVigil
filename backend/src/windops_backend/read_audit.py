from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import math
import platform
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import delete, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.config import Settings
from windops_backend.models import ReadAccessAudit, ReadAccessAuditArchive

READ_AUDIT_SCHEMA = "windops.read-access.v2"
READ_AUDIT_ARCHIVE_SCHEMA = "windops.read-access-archive.v1"
READ_AUDIT_MAINTENANCE_LOCK = "windops.read-audit-maintenance.v1"
logger = logging.getLogger(__name__)
READ_AUDIT_ENQUEUE_SCRIPT = """
local current = redis.call('XLEN', KEYS[1])
if current >= tonumber(ARGV[1]) then
  return false
end
return redis.call('XADD', KEYS[1], '*', 'event', ARGV[2])
""".strip()
READ_AUDIT_ACK_DELETE_SCRIPT = """
local acknowledged = redis.call('XACK', KEYS[1], ARGV[1], unpack(ARGV, 2))
local deleted = redis.call('XDEL', KEYS[1], unpack(ARGV, 2))
return {acknowledged, deleted}
""".strip()


class ReadAuditEnqueueError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReadAuditEvent:
    schema: str
    id: str
    subject: str
    role: str
    method: str
    endpoint: str
    query: dict[str, object]
    accessed_at: str

    def payload(self) -> bytes:
        return json.dumps(
            asdict(self), ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @classmethod
    def from_payload(cls, payload: bytes | str) -> ReadAuditEvent:
        raw = json.loads(payload)
        if not isinstance(raw, dict) or raw.get("schema") != READ_AUDIT_SCHEMA:
            raise ValueError("unsupported read audit event schema")
        query = raw.get("query")
        if not isinstance(query, dict):
            raise ValueError("read audit event query metadata must be an object")
        event = cls(
            schema=str(raw["schema"]),
            id=str(raw["id"]),
            subject=str(raw["subject"]),
            role=str(raw["role"]),
            method=str(raw["method"]),
            endpoint=str(raw["endpoint"]),
            query=cast(dict[str, object], query),
            accessed_at=str(raw["accessed_at"]),
        )
        if len(event.id) != 36 or len(event.subject) > 160 or len(event.endpoint) > 320:
            raise ValueError("read audit event exceeds bounded storage contract")
        datetime.fromisoformat(event.accessed_at.replace("Z", "+00:00"))
        return event


class ReadAuditSink(Protocol):
    async def record(self, event: ReadAuditEvent) -> None: ...


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def minimized_read_metadata(
    query: Mapping[str, Sequence[str]], authorization: Mapping[str, object]
) -> dict[str, object]:
    """Retain proof of query/scope identity without retaining caller-controlled values."""

    normalized_query = sorted(
        (str(key), sorted(str(value) for value in values)) for key, values in query.items()
    )
    normalized_scope = {
        key: sorted(cast(Sequence[str], value)) if isinstance(value, (list, tuple)) else value
        for key, value in authorization.items()
    }
    return {
        "schema": "windops.read-access-metadata.v1",
        "parameter_count": sum(len(values) for _, values in normalized_query),
        "query_fingerprint_sha256": _canonical_sha256(normalized_query),
        "authorization": {
            "tenant_count": len(cast(Sequence[object], normalized_scope.get("tenant_ids", []))),
            "wind_farm_count": len(
                cast(Sequence[object], normalized_scope.get("wind_farm_ids", []))
            ),
            "turbine_count": len(cast(Sequence[object], normalized_scope.get("turbine_ids", []))),
            "entity_count": len(cast(Sequence[object], normalized_scope.get("entity_ids", []))),
            "data_scope_count": len(
                cast(Sequence[object], normalized_scope.get("data_scopes", []))
            ),
            "allow_global": bool(normalized_scope.get("allow_global", False)),
            "unrestricted": bool(normalized_scope.get("unrestricted", False)),
            "scope_fingerprint_sha256": _canonical_sha256(normalized_scope),
        },
    }


def build_read_audit_event(
    *,
    subject: str,
    roles: Sequence[str],
    method: str,
    endpoint: str,
    query: Mapping[str, Sequence[str]],
    authorization: Mapping[str, object],
    now: datetime | None = None,
) -> ReadAuditEvent:
    accessed_at = (now or datetime.now(UTC)).astimezone(UTC)
    return ReadAuditEvent(
        schema=READ_AUDIT_SCHEMA,
        id=str(uuid4()),
        subject=subject,
        role=",".join(sorted(roles)),
        method=method,
        endpoint=endpoint,
        query=minimized_read_metadata(query, authorization),
        accessed_at=accessed_at.isoformat().replace("+00:00", "Z"),
    )


def _audit_row(event: ReadAuditEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "subject": event.subject,
        "role": event.role,
        "method": event.method,
        "endpoint": event.endpoint,
        "query": event.query,
        "accessed_at": datetime.fromisoformat(event.accessed_at.replace("Z", "+00:00")),
    }


async def persist_read_audit_batch(
    factory: async_sessionmaker[AsyncSession], events: Sequence[ReadAuditEvent]
) -> int:
    if not events:
        return 0
    rows = [_audit_row(event) for event in events]
    async with factory() as session, session.begin():
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "postgresql":
            postgres_statement = postgresql_insert(ReadAccessAudit).values(rows)
            await session.execute(
                postgres_statement.on_conflict_do_nothing(index_elements=["accessed_at", "id"])
            )
        elif dialect == "sqlite":
            sqlite_statement = sqlite_insert(ReadAccessAudit).values(rows)
            await session.execute(
                sqlite_statement.on_conflict_do_nothing(index_elements=["accessed_at", "id"])
            )
        else:
            session.add_all(ReadAccessAudit(**row) for row in rows)
    return len(rows)


class DatabaseReadAuditSink:
    """Isolated deterministic sink for tests; production uses the Redis stream sink."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def record(self, event: ReadAuditEvent) -> None:
        try:
            await persist_read_audit_batch(self._factory, [event])
        except Exception as exc:
            raise ReadAuditEnqueueError(
                "READ_AUDIT_UNAVAILABLE", "Read audit attribution is unavailable"
            ) from exc


class RedisReadAuditSink:
    """Atomically admission-check and append one event to a durable Redis stream."""

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._stream = settings.read_audit_stream_key
        self._max_pending = settings.read_audit_stream_max_pending
        self._timeout_seconds = settings.read_audit_enqueue_timeout_ms / 1_000

    async def record(self, event: ReadAuditEvent) -> None:
        try:
            entry_id = await asyncio.wait_for(
                cast(Any, self._redis).eval(
                    READ_AUDIT_ENQUEUE_SCRIPT,
                    1,
                    self._stream,
                    self._max_pending,
                    event.payload(),
                ),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            raise ReadAuditEnqueueError(
                "READ_AUDIT_UNAVAILABLE", "Read audit admission timed out"
            ) from exc
        except Exception as exc:
            raise ReadAuditEnqueueError(
                "READ_AUDIT_UNAVAILABLE", "Read audit admission is unavailable"
            ) from exc
        if not entry_id:
            raise ReadAuditEnqueueError(
                "READ_AUDIT_BACKPRESSURE",
                "Read audit backlog reached its governed capacity",
            )


class ReadAuditStreamConsumer:
    def __init__(
        self,
        redis: Redis,
        factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        consumer_name: str,
    ) -> None:
        self._redis = redis
        self._factory = factory
        self._stream = settings.read_audit_stream_key
        self._group = settings.read_audit_consumer_group
        self._consumer = consumer_name
        self._batch_size = settings.read_audit_batch_size
        self._block_ms = settings.read_audit_worker_block_ms
        self._reclaim_idle_ms = settings.read_audit_reclaim_idle_ms

    async def ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(self._stream, self._group, id="0-0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def drain_once(self) -> int:
        await self.ensure_group()
        reclaimed = await self._redis.xautoclaim(
            self._stream,
            self._group,
            self._consumer,
            min_idle_time=self._reclaim_idle_ms,
            start_id="0-0",
            count=self._batch_size,
        )
        reclaimed_messages = reclaimed[1] if len(reclaimed) > 1 else []
        if reclaimed_messages:
            response = [(self._stream, reclaimed_messages)]
        else:
            response = await self._redis.xreadgroup(
                self._group,
                self._consumer,
                {self._stream: ">"},
                count=self._batch_size,
                block=self._block_ms,
            )
            if not response:
                return 0
        message_ids: list[bytes | str] = []
        events: list[ReadAuditEvent] = []
        for _stream_name, messages in response:
            for message_id, fields in messages:
                payload = fields.get(b"event") if b"event" in fields else fields.get("event")
                if payload is None:
                    raise ValueError("read audit stream entry has no event payload")
                message_ids.append(message_id)
                events.append(ReadAuditEvent.from_payload(payload))
        await persist_read_audit_batch(self._factory, events)
        if message_ids:
            result = await cast(Any, self._redis).eval(
                READ_AUDIT_ACK_DELETE_SCRIPT,
                1,
                self._stream,
                self._group,
                *message_ids,
            )
            if not isinstance(result, (list, tuple)) or int(result[0]) != len(message_ids):
                raise RuntimeError("read audit batch acknowledgement was incomplete")
        return len(events)


def _archive_payload(rows: Sequence[ReadAccessAudit]) -> bytes:
    lines = [
        json.dumps(
            {
                "schema": READ_AUDIT_SCHEMA,
                "id": row.id,
                "subject": row.subject,
                "role": row.role,
                "method": row.method,
                "endpoint": row.endpoint,
                "query": row.query,
                "accessed_at": row.accessed_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in rows
    ]
    return gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), compresslevel=9, mtime=0)


async def maintain_read_audit_retention(
    factory: async_sessionmaker[AsyncSession], settings: Settings, *, now: datetime | None = None
) -> dict[str, object]:
    """Compress old live rows atomically and purge only archives past the retention window."""

    current = (now or datetime.now(UTC)).astimezone(UTC)
    archive_before = current - timedelta(days=settings.read_audit_archive_after_days)
    archived = 0
    archive_sha256: str | None = None
    async with factory() as session, session.begin():
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "postgresql":
            # Kubernetes prevents ordinary CronJob overlap, while this database
            # lock also serializes manual starts, retries, and duplicate schedulers.
            # It must be acquired before selecting live rows and held through
            # archive insertion, deletion, and expiry cleanup.
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_name, 0))"),
                {"lock_name": READ_AUDIT_MAINTENANCE_LOCK},
            )
        rows = list(
            (
                await session.scalars(
                    select(ReadAccessAudit)
                    .where(ReadAccessAudit.accessed_at < archive_before)
                    .order_by(ReadAccessAudit.accessed_at, ReadAccessAudit.id)
                    .limit(settings.read_audit_maintenance_batch_size)
                )
            ).all()
        )
        if rows:
            payload = _archive_payload(rows)
            archive_sha256 = hashlib.sha256(payload).hexdigest()
            first_at = min(row.accessed_at for row in rows)
            last_at = max(row.accessed_at for row in rows)
            archive_id = archive_sha256
            session.add(
                ReadAccessAuditArchive(
                    id=archive_id,
                    schema=READ_AUDIT_ARCHIVE_SCHEMA,
                    period_start=first_at,
                    period_end=last_at,
                    row_count=len(rows),
                    payload_gzip=payload,
                    payload_sha256=archive_sha256,
                    created_at=current,
                    expires_at=last_at + timedelta(days=settings.read_audit_retention_days),
                )
            )
            await session.execute(
                delete(ReadAccessAudit).where(
                    tuple_(ReadAccessAudit.accessed_at, ReadAccessAudit.id).in_(
                        [(row.accessed_at, row.id) for row in rows]
                    )
                )
            )
            archived = len(rows)

        expired_ids = list(
            (
                await session.scalars(
                    select(ReadAccessAuditArchive.id).where(
                        ReadAccessAuditArchive.expires_at < current
                    )
                )
            ).all()
        )
        if expired_ids:
            await session.execute(
                delete(ReadAccessAuditArchive).where(ReadAccessAuditArchive.id.in_(expired_ids))
            )
    return {
        "schema": "windops.read-audit-maintenance.v1",
        "archived_rows": archived,
        "archive_sha256": archive_sha256,
        "purged_archives": len(expired_ids),
        "archive_after_days": settings.read_audit_archive_after_days,
        "retention_days": settings.read_audit_retention_days,
    }


async def ensure_read_audit_partitions(
    factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    async with factory() as session:
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect != "postgresql":
            return
        async with session.begin():
            await session.execute(
                text("SELECT windops_ensure_read_audit_partitions(:months_ahead)"),
                {"months_ahead": settings.read_audit_partition_months_ahead},
            )


async def benchmark_sink(
    sink: ReadAuditSink, event: ReadAuditEvent, *, requests: int, concurrency: int
) -> dict[str, float | int | str]:
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []

    async def one() -> None:
        async with semaphore:
            started = time.perf_counter()
            await sink.record(event)
            latencies.append((time.perf_counter() - started) * 1_000)

    await asyncio.gather(*(one() for _ in range(requests)))
    ordered = sorted(latencies)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    return {
        "schema": "windops.read-audit-benchmark.v1",
        "requests": requests,
        "concurrency": concurrency,
        "enqueue_p95_ms": round(p95, 3),
    }


async def _read_audit_worker_loop() -> None:
    from windops_backend.config import get_settings
    from windops_backend.db import create_engine, create_session_factory

    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=5)
    consumer = ReadAuditStreamConsumer(
        redis,
        factory,
        settings,
        consumer_name=f"{platform.node() or 'worker'}-{uuid4()}",
    )
    try:
        while True:
            try:
                await consumer.drain_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Unacknowledged stream entries remain durable and are retried;
                # API admission eventually fails closed at the bounded backlog.
                logger.exception("read audit batch failed; entries remain unacknowledged")
                await asyncio.sleep(1)
    finally:
        await redis.aclose()
        await engine.dispose()


def run_read_audit_worker() -> None:
    asyncio.run(_read_audit_worker_loop())


async def _maintain_read_audits() -> dict[str, object]:
    from windops_backend.config import get_settings
    from windops_backend.db import create_engine, create_session_factory

    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        await ensure_read_audit_partitions(factory, settings)
        return await maintain_read_audit_retention(factory, settings)
    finally:
        await engine.dispose()


def run_read_audit_maintenance() -> None:
    print(json.dumps(asyncio.run(_maintain_read_audits()), sort_keys=True))
