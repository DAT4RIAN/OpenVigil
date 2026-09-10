from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.errors import DomainError
from windops_backend.main import create_app
from windops_backend.models import (
    Alarm,
    CommandReceipt,
    DelegatedRequestAudit,
    DelegatedRequestNonce,
    DomainEvent,
    IngestReceipt,
    Mission,
    MissionComment,
)
from windops_backend.services import idempotency as idempotency_service
from windops_backend.services.idempotency import (
    execute_idempotent_command,
    replace_idempotent_response,
)

SECRET = "test-delegation-secret-with-at-least-forty-eight-characters"
MISSION_ID = "MISSION-REPLAY-TEST-001"


async def _seed_comment_mission(app: FastAPI) -> None:
    async with app.state.session_factory() as session, session.begin():
        if await session.get(Mission, MISSION_ID) is not None:
            return
        session.add(
            IngestReceipt(
                source_event_id="replay-test-source-event",
                source_id="scada-default",
                payload_hash="a" * 64,
            )
        )
        await session.flush()
        session.add(
            Alarm(
                id="ALARM-REPLAY-TEST-001",
                turbine_id="WT-023",
                source_event_id="replay-test-source-event",
                code="REPLAY_TEST",
                subsystem="test",
                title="Replay protection test alarm",
                triggered_at=datetime.now(UTC),
            )
        )
        await session.flush()
        session.add(
            Mission(
                id=MISSION_ID,
                alarm_id="ALARM-REPLAY-TEST-001",
                turbine_id="WT-023",
                title="Replay protection test mission",
            )
        )


def _delegation(
    *,
    body: bytes,
    target: str,
    jti: str,
    method: str = "POST",
    expires_in: int = 60,
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": "windops-sites-gateway",
            "aud": "windops-python-backend",
            "sub": "sites-user-replay-test",
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
            "jti": jti,
            "method": method,
            "target": target,
            "body_sha256": hashlib.sha256(body).hexdigest(),
        },
        SECRET,
        algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_delegated_write_nonce_is_consumed_but_reads_remain_replayable(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'replay.sqlite'}",
        schema_bootstrap=True,
        demo_seed=True,
        knowledge_graph_backend="memory",
        auth_mode="sites_delegation",
        gateway_delegation_secret=SECRET,
        identity_role_mappings={"sites-user-replay-test": ["field_technician"]},
    )
    app = create_app(settings)
    target = f"/api/v1/missions/{MISSION_ID}/comments"
    body = json.dumps({"body": "Replay-safe field note"}, separators=(",", ":")).encode()
    token = _delegation(body=body, target=target, jti="serial-write-nonce")
    headers = {
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "idempotency-key": "serial-comment-key-001",
    }
    async with app.router.lifespan_context(app):
        await _seed_comment_mission(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(target, content=body, headers=headers)
            replay = await client.post(target, content=body, headers=headers)

            assert first.status_code == 201, first.text
            assert replay.status_code == 401, replay.text
            assert replay.json()["error"]["code"] == "DELEGATED_IDENTITY_REPLAYED"

            read_target = target
            read_token = _delegation(
                body=b"",
                target=read_target,
                jti="replayable-read-nonce",
                method="GET",
            )
            read_headers = {"authorization": f"Bearer {read_token}"}
            assert (await client.get(read_target, headers=read_headers)).status_code == 200
            assert (await client.get(read_target, headers=read_headers)).status_code == 200

        async with app.state.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(MissionComment)) == 1
            assert (
                await session.scalar(select(func.count()).select_from(DelegatedRequestNonce)) == 1
            )
            outcomes = list(
                (
                    await session.scalars(
                        select(DelegatedRequestAudit.outcome).order_by(
                            DelegatedRequestAudit.occurred_at
                        )
                    )
                ).all()
            )
            assert outcomes == ["accepted", "replayed"]


@pytest.mark.asyncio
async def test_concurrent_use_of_one_delegated_write_executes_one_side_effect(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'concurrent-replay.sqlite'}",
        schema_bootstrap=True,
        demo_seed=True,
        knowledge_graph_backend="memory",
        auth_mode="sites_delegation",
        gateway_delegation_secret=SECRET,
        identity_role_mappings={"sites-user-replay-test": ["field_technician"]},
    )
    app = create_app(settings)
    target = f"/api/v1/missions/{MISSION_ID}/comments"
    body = json.dumps({"body": "Concurrent replay note"}, separators=(",", ":")).encode()
    token = _delegation(body=body, target=target, jti="concurrent-write-nonce")
    headers = {
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "idempotency-key": "concurrent-comment-key-001",
    }
    async with app.router.lifespan_context(app):
        await _seed_comment_mission(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = await asyncio.gather(
                client.post(target, content=body, headers=headers),
                client.post(target, content=body, headers=headers),
            )
        assert sorted(response.status_code for response in responses) == [201, 401]
        async with app.state.session_factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(MissionComment)
                .where(MissionComment.body == "Concurrent replay note")
            )
            assert count == 1


@pytest.mark.asyncio
async def test_comment_idempotency_returns_stable_result_and_rejects_payload_reuse(
    app: FastAPI,
    client: Any,
) -> None:
    await _seed_comment_mission(app)
    target = f"/api/v1/missions/{MISSION_ID}/comments"
    headers = {"Idempotency-Key": "stable-comment-response-001"}
    first = await client.post(target, headers=headers, json={"body": "Stable retry note"})
    replay = await client.post(target, headers=headers, json={"body": "Stable retry note"})
    conflict = await client.post(target, headers=headers, json={"body": "Changed retry note"})

    assert first.status_code == 201, first.text
    assert replay.status_code == 201, replay.text
    assert first.json() == replay.json()
    assert first.headers["Idempotency-Replayed"] == "false"
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    async with app.state.session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MissionComment)
                .where(MissionComment.body == "Stable retry note")
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DomainEvent)
                .where(DomainEvent.event_type == "mission.comment.created")
            )
            == 1
        )
        receipt = await session.scalar(
            select(CommandReceipt).where(
                CommandReceipt.subject == "integration-test-system",
                CommandReceipt.command_type == "mission.comment.create.v1",
                CommandReceipt.target == MISSION_ID,
                CommandReceipt.idempotency_key == "stable-comment-response-001",
            )
        )
        assert receipt is not None
        assert receipt.replay_count == 1
        assert receipt.last_replayed_at is not None


@pytest.mark.asyncio
async def test_delegated_write_fails_closed_and_is_observable_when_store_is_unavailable(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'store-outage.sqlite'}",
        schema_bootstrap=True,
        demo_seed=True,
        knowledge_graph_backend="memory",
        auth_mode="sites_delegation",
        gateway_delegation_secret=SECRET,
        identity_role_mappings={"sites-user-replay-test": ["field_technician"]},
    )
    app = create_app(settings)
    target = f"/api/v1/missions/{MISSION_ID}/comments"
    body = json.dumps({"body": "Must fail closed"}, separators=(",", ":")).encode()

    class FailingFactory:
        def __init__(self, delegate: Any) -> None:
            self.delegate = delegate
            self.calls = 0

        def __call__(self) -> Any:
            self.calls += 1
            if self.calls == 2:
                raise SQLAlchemyError("simulated replay-store outage")
            return self.delegate()

    async with app.router.lifespan_context(app):
        original_factory = app.state.session_factory
        app.state.session_factory = FailingFactory(original_factory)
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    target,
                    content=body,
                    headers={
                        "authorization": (
                            "Bearer "
                            + _delegation(
                                body=body,
                                target=target,
                                jti="replay-store-outage",
                            )
                        ),
                        "content-type": "application/json",
                        "idempotency-key": "store-outage-comment-001",
                    },
                )
        finally:
            app.state.session_factory = original_factory

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DELEGATION_REPLAY_STORE_UNAVAILABLE"
        metric = app.state.observability.delegated_write_security_events.labels(
            outcome="store_failure"
        )
        assert metric._value.get() == 1  # noqa: SLF001 - metric contract assertion


@pytest.mark.asyncio
async def test_nonce_retention_covers_clock_skew_and_cleanup_removes_expired_rows(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'clock-skew.sqlite'}",
        schema_bootstrap=True,
        demo_seed=True,
        knowledge_graph_backend="memory",
        auth_mode="sites_delegation",
        gateway_delegation_secret=SECRET,
        delegation_clock_skew_seconds=15,
        identity_role_mappings={"sites-user-replay-test": ["field_technician"]},
    )
    app = create_app(settings)
    target = f"/api/v1/missions/{MISSION_ID}/comments"
    body = json.dumps({"body": "Accepted inside clock skew"}, separators=(",", ":")).encode()
    token = _delegation(
        body=body,
        target=target,
        jti="clock-skew-nonce",
        expires_in=-5,
    )
    async with app.router.lifespan_context(app):
        await _seed_comment_mission(app)
        async with app.state.session_factory() as session, session.begin():
            session.add(
                DelegatedRequestNonce(
                    jti_sha256="f" * 64,
                    subject="expired-subject",
                    method="POST",
                    target="/expired",
                    body_sha256="0" * 64,
                    expires_at=datetime.now(UTC) - timedelta(minutes=1),
                )
            )
        transport = httpx.ASGITransport(app=app)
        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "idempotency-key": "clock-skew-comment-001",
        }
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(target, content=body, headers=headers)
            replay = await client.post(target, content=body, headers=headers)
        assert first.status_code == 201, first.text
        assert replay.status_code == 401

        async with app.state.session_factory() as session:
            rows = list((await session.scalars(select(DelegatedRequestNonce))).all())
            assert len(rows) == 1
            assert rows[0].jti_sha256 != "f" * 64
            # The nonce outlives exp for the full configured JWT leeway.
            assert rows[0].expires_at.replace(tzinfo=UTC) > datetime.now(UTC)


def test_every_retryable_post_declares_a_required_idempotency_key() -> None:
    app = create_app(
        Settings(
            environment=Environment.TEST,
            database_url="sqlite+aiosqlite:///:memory:",
            schema_bootstrap=True,
            demo_seed=False,
            knowledge_graph_backend="memory",
        )
    )
    missing: list[str] = []
    for path, path_item in app.openapi()["paths"].items():
        operation = path_item.get("post")
        if operation is None or path == "/api/v1/scada/ingest":
            continue
        parameters = operation.get("parameters", [])
        has_required_key = any(
            parameter.get("in") == "header"
            and parameter.get("name", "").lower() == "idempotency-key"
            and parameter.get("required") is True
            for parameter in parameters
        )
        if not has_required_key:
            missing.append(path)

    assert missing == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command_type", "target", "idempotency_key", "message"),
    [
        ("", "target", "valid-key", "command type"),
        ("command", "x" * 161, "valid-key", "target"),
        ("command", "target", "short", "Idempotency-Key"),
    ],
)
async def test_idempotency_scope_rejects_ambiguous_or_unbounded_values(
    app: FastAPI,
    command_type: str,
    target: str,
    idempotency_key: str,
    message: str,
) -> None:
    async with app.state.session_factory() as session:
        with pytest.raises(DomainError, match=message):
            await execute_idempotent_command(
                session,
                subject="scope-test",
                command_type=command_type,
                target=target,
                idempotency_key=idempotency_key,
                payload={},
                status_code=200,
                operation=lambda: asyncio.sleep(0, result={"ok": True}),
            )


@pytest.mark.asyncio
async def test_idempotent_operation_requires_an_object_and_rolls_back_reservation(
    app: FastAPI,
) -> None:
    async with app.state.session_factory() as session, session.begin():

        async def invalid_operation() -> Any:
            return ["not", "an", "object"]

        with pytest.raises(TypeError, match="object response"):
            await execute_idempotent_command(
                session,
                subject="shape-test",
                command_type="shape.check.v1",
                target="shape-target",
                idempotency_key="shape-check-key",
                payload={"input": True},
                status_code=200,
                operation=invalid_operation,
            )

    async with app.state.session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CommandReceipt)
                .where(CommandReceipt.subject == "shape-test")
            )
            == 0
        )


@pytest.mark.asyncio
async def test_idempotent_response_finalization_updates_existing_receipt_and_fails_closed(
    app: FastAPI,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        response, replayed = await execute_idempotent_command(
            session,
            subject="finalize-test",
            command_type="workflow.finalize.v1",
            target="mission-finalize",
            idempotency_key="finalize-command-key",
            payload={"revision": 1},
            status_code=200,
            operation=lambda: asyncio.sleep(0, result={"state": "reserved"}),
        )
        assert response == {"state": "reserved"}
        assert replayed is False
        await replace_idempotent_response(
            session,
            subject="finalize-test",
            command_type="workflow.finalize.v1",
            target="mission-finalize",
            idempotency_key="finalize-command-key",
            response_body={"state": "complete", "revision": 2},
        )

    async with app.state.session_factory() as session, session.begin():
        replay, replayed = await execute_idempotent_command(
            session,
            subject="finalize-test",
            command_type="workflow.finalize.v1",
            target="mission-finalize",
            idempotency_key="finalize-command-key",
            payload={"revision": 1},
            status_code=200,
            operation=lambda: asyncio.sleep(0, result={"unexpected": True}),
        )
        assert replay == {"state": "complete", "revision": 2}
        assert replayed is True
        with pytest.raises(RuntimeError, match="receipt disappeared"):
            await replace_idempotent_response(
                session,
                subject="finalize-test",
                command_type="workflow.missing.v1",
                target="mission-finalize",
                idempotency_key="missing-finalize-key",
                response_body={"state": "complete"},
            )


@pytest.mark.asyncio
async def test_concurrent_receipt_integrity_failure_replays_the_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = CommandReceipt(
        id="winning-receipt",
        command_type="concurrent.command.v1",
        target="target",
        idempotency_key="concurrent-command-key",
        request_hash=idempotency_service.canonical_request_hash({"value": 1}),
        subject="concurrent-subject",
        response_body={"winner": True},
        status_code=200,
        replay_count=0,
    )
    lookups = iter([None, receipt])

    async def find_winner(*args: Any, **kwargs: Any) -> CommandReceipt | None:
        del args, kwargs
        return next(lookups)

    class FailingReservation:
        async def __aenter__(self) -> None:
            raise IntegrityError("insert command_receipts", {}, Exception("unique violation"))

        async def __aexit__(self, *args: Any) -> None:
            del args

    class ConcurrentSession:
        def begin_nested(self) -> FailingReservation:
            return FailingReservation()

        async def flush(self) -> None:
            return None

    monkeypatch.setattr(idempotency_service, "_find_receipt", find_winner)
    operation_called = False

    async def losing_operation() -> dict[str, Any]:
        nonlocal operation_called
        operation_called = True
        return {"winner": False}

    response, replayed = await execute_idempotent_command(
        ConcurrentSession(),  # type: ignore[arg-type]
        subject="concurrent-subject",
        command_type="concurrent.command.v1",
        target="target",
        idempotency_key="concurrent-command-key",
        payload={"value": 1},
        status_code=200,
        operation=losing_operation,
    )

    assert response == {"winner": True}
    assert replayed is True
    assert operation_called is False
    assert receipt.replay_count == 1
