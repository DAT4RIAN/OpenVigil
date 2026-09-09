from datetime import UTC, datetime, timedelta
from typing import Any

import dramatiq
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from windops_backend import workers
from windops_backend.config import Settings
from windops_backend.db import bootstrap_schema, create_engine, create_session_factory
from windops_backend.enums import Environment
from windops_backend.models import (
    AgentExecution,
    Alarm,
    Decision,
    Mission,
    Turbine,
    WindFarm,
    WorkOrder,
)
from windops_backend.outbox import claim_event, mark_event_succeeded, process_outbox_event
from windops_backend.reference_import import _import_reference_pack
from windops_backend.storage import OutboxEvent


def anomaly(event_id: str) -> dict[str, Any]:
    return {
        "samples": [
            {
                "source_event_id": event_id,
                "turbine_id": "WT-023",
                "observed_at": "2026-08-13T02:14:03Z",
                "variable": "main_bearing_vibration_rms",
                "value": 4.81,
                "unit": "mm/s",
                "quality": "good",
                "attributes": {"anomaly_score": 0.86, "baseline": 3.79},
            }
        ]
    }


@pytest.mark.asyncio
async def test_stale_processing_outbox_lease_can_be_reclaimed(app: FastAPI) -> None:
    async with app.state.session_factory() as session, session.begin():
        event = OutboxEvent(
            event_type="mission.analysis.requested",
            aggregate_type="mission",
            aggregate_id="missing-for-lease-only",
            payload={"mission_id": "missing-for-lease-only"},
            status="processing",
            claimed_at=datetime.now(UTC) - timedelta(minutes=6),
        )
        session.add(event)
        await session.flush()
        event_id = event.id

    async with app.state.session_factory() as session, session.begin():
        reclaimed = await claim_event(session, event_id)
        assert reclaimed is not None
        assert reclaimed.status == "processing"
        assert reclaimed.attempts == 1
        assert reclaimed.claim_token is not None


@pytest.mark.asyncio
async def test_outbox_fencing_prevents_an_old_worker_from_overwriting_new_lease(
    app: FastAPI,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        event = OutboxEvent(
            event_type="mission.analysis.requested",
            aggregate_type="mission",
            aggregate_id="fencing-only",
            payload={"mission_id": "fencing-only"},
        )
        session.add(event)
        await session.flush()
        event_id = event.id

    async with app.state.session_factory() as session, session.begin():
        first_claim = await claim_event(session, event_id)
        assert first_claim is not None and first_claim.claim_token is not None
        first_token = first_claim.claim_token

    async with app.state.session_factory() as session, session.begin():
        claimed = await session.get(OutboxEvent, event_id)
        assert claimed is not None
        claimed.claimed_at = datetime.now(UTC) - timedelta(minutes=6)
        claimed.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    async with app.state.session_factory() as session, session.begin():
        second_claim = await claim_event(session, event_id)
        assert second_claim is not None and second_claim.claim_token is not None
        second_token = second_claim.claim_token
        assert second_token != first_token

    assert await mark_event_succeeded(app.state.session_factory, event_id, first_token) is False
    async with app.state.session_factory() as session:
        still_owned = await session.get(OutboxEvent, event_id)
        assert still_owned is not None
        assert still_owned.status == "processing"
        assert still_owned.claim_token == second_token

    assert await mark_event_succeeded(app.state.session_factory, event_id, second_token) is True


@pytest.mark.asyncio
async def test_expired_lease_rolls_back_handler_changes_before_graph_commit(
    app: FastAPI,
) -> None:
    mission_id = "lease-expiration-mission"
    async with app.state.session_factory() as session, session.begin():
        event = OutboxEvent(
            event_type="mission.analysis.requested",
            aggregate_type="mission",
            aggregate_id=mission_id,
            payload={"mission_id": mission_id},
        )
        session.add(event)
        await session.flush()
        event_id = event.id

    async def expire_during_handler(session: Any, settings: Settings, value: str) -> None:
        del settings, value
        session.add(
            OutboxEvent(
                event_type="must.rollback.after.expired.lease",
                aggregate_type="test",
                aggregate_id="rollback",
                payload={},
            )
        )
        await session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    assert (
        await process_outbox_event(
            app.state.session_factory,
            app.state.settings,
            event_id,
            expire_during_handler,
        )
        is False
    )
    async with app.state.session_factory() as session:
        assert (
            await session.scalar(
                select(OutboxEvent.id).where(
                    OutboxEvent.event_type == "must.rollback.after.expired.lease"
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_early_redelivery_is_retried_until_lease_can_be_reclaimed(
    monkeypatch,
) -> None:
    async def busy(*args: Any, **kwargs: Any) -> bool:
        del args, kwargs
        return False

    class Engine:
        async def dispose(self) -> None:
            return None

    monkeypatch.setattr(workers, "get_settings", lambda: object())
    monkeypatch.setattr(workers, "create_engine", lambda settings: Engine())
    monkeypatch.setattr(workers, "create_session_factory", lambda engine: object())
    monkeypatch.setattr(workers, "process_outbox_event", busy)

    async def leased(factory: Any, event_id: str) -> int:
        del factory, event_id
        return 300_000

    monkeypatch.setattr(workers, "redelivery_retry_delay_ms", leased)
    with pytest.raises(dramatiq.Retry) as retry:
        await workers._process("leased-event")
    assert retry.value.delay == 300_000


@pytest.mark.asyncio
async def test_succeeded_duplicate_redelivery_is_acked(monkeypatch) -> None:
    async def duplicate(*args: Any, **kwargs: Any) -> bool:
        del args, kwargs
        return False

    async def terminal(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        return None

    class Engine:
        async def dispose(self) -> None:
            return None

    monkeypatch.setattr(workers, "get_settings", lambda: object())
    monkeypatch.setattr(workers, "create_engine", lambda settings: Engine())
    monkeypatch.setattr(workers, "create_session_factory", lambda engine: object())
    monkeypatch.setattr(workers, "process_outbox_event", duplicate)
    monkeypatch.setattr(workers, "redelivery_retry_delay_ms", terminal)
    await workers._process("already-succeeded")


@pytest.mark.asyncio
async def test_graph_failure_audit_survives_work_transaction_rollback(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    response = await client.post("/api/v1/scada/ingest", json=anomaly("SCADA-WT023-FAILURE-AUDIT"))
    mission_id = response.json()["results"][0]["mission_id"]
    async with app.state.session_factory() as session, session.begin():
        event = OutboxEvent(
            event_type="mission.analysis.requested",
            aggregate_type="mission",
            aggregate_id=mission_id,
            payload={"mission_id": mission_id},
        )
        session.add(event)
        await session.flush()
        event_id = event.id

    async def fail_handler(session: Any, settings: Settings, value: str) -> None:
        del settings, value
        session.add(
            OutboxEvent(
                event_type="must.rollback",
                aggregate_type="test",
                aggregate_id="rollback",
                payload={},
            )
        )
        raise RuntimeError("external model unavailable")

    with pytest.raises(RuntimeError, match="external model unavailable"):
        await process_outbox_event(
            app.state.session_factory, app.state.settings, event_id, fail_handler
        )

    async with app.state.session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
        assert event is not None and event.status == "failed"
        assert (
            await session.scalar(
                select(OutboxEvent.id).where(OutboxEvent.event_type == "must.rollback")
            )
            is None
        )
        audit = await session.scalar(
            select(AgentExecution).where(
                AgentExecution.mission_id == mission_id,
                AgentExecution.status == "failed",
                AgentExecution.agent_role == "workflow_dispatcher",
            )
        )
        assert audit is not None
        assert audit.error_code == "RuntimeError"


@pytest.mark.asyncio
async def test_reference_import_persists_only_master_data(tmp_path, monkeypatch) -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'reference-import.sqlite'}",
        schema_bootstrap=True,
        demo_seed=False,
        agent_mode="deterministic",
    )
    engine = create_engine(settings)
    await bootstrap_schema(engine, settings)
    await engine.dispose()
    monkeypatch.setattr("windops_backend.reference_import.get_settings", lambda: settings)
    await _import_reference_pack("wt023")
    verification_engine = create_engine(settings)
    factory = create_session_factory(verification_engine)
    async with factory() as session:
        assert await session.get(WindFarm, "WF-EAST-01") is not None
        assert await session.get(Turbine, "WT-023") is not None
        for model in (Alarm, Mission, Decision, WorkOrder, AgentExecution):
            assert (await session.scalars(select(model))).first() is None
    await verification_engine.dispose()
