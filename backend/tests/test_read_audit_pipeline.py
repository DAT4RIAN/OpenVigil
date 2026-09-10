from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.models import ReadAccessAudit, ReadAccessAuditArchive
from windops_backend.read_audit import (
    READ_AUDIT_ACK_DELETE_SCRIPT,
    ReadAuditEnqueueError,
    ReadAuditStreamConsumer,
    RedisReadAuditSink,
    benchmark_sink,
    build_read_audit_event,
    maintain_read_audit_retention,
    minimized_read_metadata,
    persist_read_audit_batch,
)


def settings() -> Settings:
    return Settings(
        environment=Environment.TEST,
        database_url="sqlite+aiosqlite:///:memory:",
        schema_bootstrap=True,
        agent_mode="deterministic",
        test_auth_bypass_enabled=True,
        knowledge_graph_backend="memory",
    )


def event(at: datetime | None = None):
    return build_read_audit_event(
        subject="audit-test-subject",
        roles=["field_technician"],
        method="GET",
        endpoint="/api/v1/turbines",
        query={"search": ["private blade note"], "limit": ["50"]},
        authorization={
            "tenant_ids": ["tenant-secret"],
            "wind_farm_ids": ["WF-PRIVATE"],
            "turbine_ids": ["WT-PRIVATE"],
            "entity_ids": [],
            "data_scopes": ["asset"],
            "allow_global": False,
            "unrestricted": False,
        },
        now=at,
    )


def test_query_and_scope_values_are_minimized_but_stably_attributed() -> None:
    first = event()
    second = build_read_audit_event(
        subject=first.subject,
        roles=["field_technician"],
        method="GET",
        endpoint=first.endpoint,
        query={"search": ["different private note"], "limit": ["50"]},
        authorization={
            "tenant_ids": ["tenant-secret"],
            "wind_farm_ids": ["WF-PRIVATE"],
            "turbine_ids": ["WT-PRIVATE"],
            "entity_ids": [],
            "data_scopes": ["asset"],
            "allow_global": False,
            "unrestricted": False,
        },
    )
    encoded = first.payload().decode()
    assert "private blade note" not in encoded
    assert "tenant-secret" not in encoded
    assert "WT-PRIVATE" not in encoded
    assert first.query["parameter_count"] == 2
    assert first.query["query_fingerprint_sha256"] != second.query["query_fingerprint_sha256"]
    assert (
        first.query["authorization"]["scope_fingerprint_sha256"]
        == second.query["authorization"]["scope_fingerprint_sha256"]
    )


class FakeRedis:
    def __init__(self, *, enqueue_result: object = b"1-0", enqueue_error: Exception | None = None):
        self.enqueue_result = enqueue_result
        self.enqueue_error = enqueue_error
        self.messages: list[tuple[bytes, dict[bytes, bytes]]] = []
        self.acknowledged: list[bytes] = []

    async def eval(self, script: str, _keys: int, *_args: object) -> object:
        if script == READ_AUDIT_ACK_DELETE_SCRIPT:
            ids = [value for value in _args[2:] if isinstance(value, bytes)]
            self.acknowledged.extend(ids)
            return [len(ids), len(ids)]
        if self.enqueue_error is not None:
            raise self.enqueue_error
        return self.enqueue_result

    async def xgroup_create(self, *_args: object, **_kwargs: object) -> None:
        return None

    async def xautoclaim(self, *_args: object, **_kwargs: object) -> list[object]:
        return [b"0-0", []]

    async def xreadgroup(self, *_args: object, **_kwargs: object) -> list[object]:
        if not self.messages:
            return []
        messages = self.messages
        self.messages = []
        return [(b"windops:read-audit:v2", messages)]


@pytest.mark.asyncio
async def test_redis_admission_fails_closed_on_storage_failure_and_backpressure() -> None:
    accepted = RedisReadAuditSink(FakeRedis(), settings())  # type: ignore[arg-type]
    await accepted.record(event())

    for fake, code in [
        (FakeRedis(enqueue_result=None), "READ_AUDIT_BACKPRESSURE"),
        (FakeRedis(enqueue_error=ConnectionError("redis unavailable")), "READ_AUDIT_UNAVAILABLE"),
    ]:
        with pytest.raises(ReadAuditEnqueueError) as captured:
            await RedisReadAuditSink(fake, settings()).record(event())  # type: ignore[arg-type]
        assert captured.value.code == code


@pytest.mark.asyncio
async def test_api_rejects_business_read_before_query_when_audit_admission_fails(
    app: FastAPI,
) -> None:
    class FailingSink:
        async def record(self, _event: object) -> None:
            raise ReadAuditEnqueueError(
                "READ_AUDIT_BACKPRESSURE", "Read audit backlog reached capacity"
            )

    app.state.read_audit_sink = FailingSink()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-WindOps-Test-Principal": "integration-test-system",
            "X-WindOps-Test-Role": "test_system",
        },
    ) as client:
        response = await client.get("/api/v1/turbines?search=must-not-run")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "READ_AUDIT_BACKPRESSURE"
    assert response.headers["retry-after"] == "1"


@pytest.mark.asyncio
async def test_stream_batch_is_committed_before_ack_and_duplicate_delivery_is_idempotent(
    app: FastAPI,
) -> None:
    first = event()
    second = event()
    redis = FakeRedis()
    redis.messages = [
        (b"1-0", {b"event": first.payload()}),
        (b"2-0", {b"event": second.payload()}),
        (b"3-0", {b"event": first.payload()}),
    ]
    consumer = ReadAuditStreamConsumer(
        redis,
        app.state.session_factory,
        settings(),
        consumer_name="test-consumer",  # type: ignore[arg-type]
    )
    assert await consumer.drain_once() == 3
    assert redis.acknowledged == [b"1-0", b"2-0", b"3-0"]
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ReadAccessAudit)) == 2


@pytest.mark.asyncio
async def test_failed_batch_is_not_acknowledged_and_remains_recoverable(app: FastAPI) -> None:
    class FailingFactory:
        def __call__(self) -> None:
            raise RuntimeError("audit database unavailable")

    redis = FakeRedis()
    redis.messages = [(b"1-0", {b"event": event().payload()})]
    consumer = ReadAuditStreamConsumer(
        redis,
        FailingFactory(),  # type: ignore[arg-type]
        settings(),
        consumer_name="test-consumer",
    )
    with pytest.raises(RuntimeError, match="audit database unavailable"):
        await consumer.drain_once()
    assert redis.acknowledged == []


@pytest.mark.asyncio
async def test_retention_archives_complete_rows_and_purges_only_after_expiry(app: FastAPI) -> None:
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    old = [event(now - timedelta(days=31, seconds=index)) for index in range(3)]
    await persist_read_audit_batch(app.state.session_factory, old)

    result = await maintain_read_audit_retention(app.state.session_factory, settings(), now=now)
    assert result["archived_rows"] == 3
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ReadAccessAudit)) == 0
        archive = await session.scalar(select(ReadAccessAuditArchive))
        assert archive is not None
        assert archive.row_count == 3
        assert hashlib.sha256(archive.payload_gzip).hexdigest() == archive.payload_sha256
        lines = gzip.decompress(archive.payload_gzip).decode().splitlines()
        assert len(lines) == 3
        assert all(json.loads(line)["schema"] == "windops.read-access.v2" for line in lines)

    before_expiry = await maintain_read_audit_retention(
        app.state.session_factory, settings(), now=now + timedelta(days=300)
    )
    assert before_expiry["purged_archives"] == 0
    after_expiry = await maintain_read_audit_retention(
        app.state.session_factory, settings(), now=now + timedelta(days=400)
    )
    assert after_expiry["purged_archives"] == 1


@pytest.mark.asyncio
async def test_concurrent_enqueue_evidence_quantifies_p95_and_batch_write_amplification() -> None:
    redis = FakeRedis()
    sink = RedisReadAuditSink(redis, settings())  # type: ignore[arg-type]
    report = await benchmark_sink(sink, event(), requests=1_000, concurrency=50)
    assert report["requests"] == 1_000
    assert report["concurrency"] == 50
    assert float(report["enqueue_p95_ms"]) < 50
    batch_transactions = 1_000 // settings().read_audit_batch_size
    assert batch_transactions == 2
    assert batch_transactions / 1_000 == 0.002


def test_minimized_metadata_is_deterministic_for_query_order() -> None:
    authorization = {"turbine_ids": ["WT-2", "WT-1"], "allow_global": False}
    first = minimized_read_metadata({"b": ["2"], "a": ["1"]}, authorization)
    second = minimized_read_metadata({"a": ["1"], "b": ["2"]}, authorization)
    assert first == second
