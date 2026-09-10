from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.config import Settings
from windops_backend.enums import (
    AlarmStatus,
    ApprovalAction,
    Environment,
    MissionStatus,
    TaskStatus,
    WorkOrderStatus,
)
from windops_backend.errors import ConflictError
from windops_backend.main import create_app
from windops_backend.models import (
    Alarm,
    Approval,
    AssetHealthEvent,
    CommandReceipt,
    Decision,
    DomainEvent,
    IngestReceipt,
    Mission,
    PlatformConfigurationRevision,
    Tenant,
    Turbine,
    WindFarm,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.schemas import (
    AlarmCommandRequest,
    ApprovalRequest,
    PlatformConfigurationCreateRequest,
    TaskCompletionRequest,
)
from windops_backend.services import workflow
from windops_backend.services.alarms import execute_alarm_command
from windops_backend.services.platform_governance import create_platform_configuration_revision
from windops_backend.services.workflow import record_approval
from windops_backend.services.workorders import complete_task
from windops_backend.storage import FieldTaskEvidence, InMemoryArtifactVerifier

pytestmark = [
    pytest.mark.external_release,
    pytest.mark.skipif(
        os.getenv("WINDOPS_RUN_POSTGRES_CONTRACT_TESTS") != "1",
        reason="requires an isolated migrated PostgreSQL database",
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


class _FirstEmptyScalarBarrierSession(AsyncSession):
    """Pause two real transactions after their first authoritative empty read."""

    async def scalar(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        result = await super().scalar(statement, *args, **kwargs)
        barrier = self.info.get("first_empty_scalar_barrier")
        if result is None and barrier is not None and not self.info.get("barrier_released"):
            self.info["barrier_released"] = True
            await barrier.wait()
        return result


async def _ensure_tenant(session: AsyncSession, tenant_id: str) -> None:
    if await session.get(Tenant, tenant_id) is None:
        session.add(Tenant(id=tenant_id, name=f"M-002 tenant {tenant_id}"))
        await session.flush()


async def _seed_mission(
    session: AsyncSession,
    *,
    suffix: str,
    tenant_id: str = "tenant-east-china",
    status: str,
    revision: int,
) -> tuple[str, str, str, str]:
    await _ensure_tenant(session, tenant_id)
    farm_id = f"WF-M2-{suffix}"
    turbine_id = f"WT-M2-{suffix}"
    receipt_id = f"M2-RECEIPT-{suffix}"
    alarm_id = f"AL-M2-{suffix}"
    mission_id = f"MI-M2-{suffix}"
    session.add(
        WindFarm(
            id=farm_id,
            tenant_id=tenant_id,
            name=f"M-002 resilience farm {suffix}",
            capacity_mw=12,
        )
    )
    await session.flush()
    session.add(
        Turbine(
            id=turbine_id,
            wind_farm_id=farm_id,
            model="M002-RESILIENCE",
            health_score=72,
        )
    )
    session.add(IngestReceipt(source_event_id=receipt_id, payload_hash="d" * 64))
    await session.flush()
    session.add(
        Alarm(
            id=alarm_id,
            turbine_id=turbine_id,
            source_event_id=receipt_id,
            code="M002-RESILIENCE",
            subsystem="main_bearing",
            title=f"M-002 resilience alarm {suffix}",
            severity="major",
            status=AlarmStatus.OPEN.value,
            triggered_at=datetime.now(UTC),
            evidence={},
        )
    )
    await session.flush()
    session.add(
        Mission(
            id=mission_id,
            alarm_id=alarm_id,
            turbine_id=turbine_id,
            title=f"M-002 resilience mission {suffix}",
            status=status,
            revision=revision,
            public_state={"workflow_status": status},
        )
    )
    await session.flush()
    return farm_id, turbine_id, alarm_id, mission_id


@pytest.mark.asyncio
async def test_postgres_work_order_late_failure_rolls_back_and_retry_commits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(_database_url(), pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:10]
    approval_id = str(uuid4())
    work_order_id = f"WO-M2-{suffix}"
    task_id = str(uuid4())
    async with factory() as session, session.begin():
        _, turbine_id, alarm_id, mission_id = await _seed_mission(
            session,
            suffix=suffix,
            status=MissionStatus.EXECUTING.value,
            revision=2,
        )
        session.add(
            Approval(
                id=approval_id,
                mission_id=mission_id,
                mission_revision=1,
                action=ApprovalAction.APPROVE.value,
                approver="m002-postgres-reviewer",
                reason="M-002 PostgreSQL work-order contract",
            )
        )
        await session.flush()
        session.add(
            WorkOrder(
                id=work_order_id,
                mission_id=mission_id,
                approval_id=approval_id,
                turbine_id=turbine_id,
                title="M-002 PostgreSQL governed task",
                selected_alternative_id="m002-repair",
                selected_action="Complete the governed M-002 repair",
                status=WorkOrderStatus.SCHEDULED.value,
                closure_policy={
                    "health_score_field": "turbine_health_score",
                    "healthy_threshold": 82,
                    "component": "main_bearing",
                },
            )
        )
        await session.flush()
        session.add(
            WorkOrderTask(
                id=task_id,
                work_order_id=work_order_id,
                sequence=1,
                title="Verify return to service",
                schema_version="m002-v1",
                measurement_schema={
                    "type": "object",
                    "properties": {"turbine_health_score": {"type": "number", "minimum": 82}},
                    "required": ["turbine_health_score"],
                    "additionalProperties": False,
                },
                status=TaskStatus.PENDING.value,
            )
        )

    artifact_uri = f"minio://test/m002/{task_id}.json"
    artifact_sha256 = "e" * 64
    verifier = InMemoryArtifactVerifier()
    verifier.register(artifact_uri, artifact_sha256)
    request = TaskCompletionRequest(
        result="PostgreSQL return-to-service measurement verified",
        artifact_uri=artifact_uri,
        artifact_sha256=artifact_sha256,
        measurement={"turbine_health_score": 89},
        completed_by="m002-postgres-technician",
    )

    async def fail_health_side_effect(self: SQLToolAdapter, **kwargs: Any) -> dict[str, Any]:
        del self, kwargs
        raise RuntimeError("injected PostgreSQL asset-health failure")

    try:
        with monkeypatch.context() as context:
            context.setattr(SQLToolAdapter, "update_asset_health", fail_health_side_effect)
            with pytest.raises(RuntimeError, match="asset-health failure"):
                async with factory() as session, session.begin():
                    await complete_task(session, work_order_id, task_id, request, verifier)

        async with factory() as session:
            task = await session.get(WorkOrderTask, task_id)
            work_order = await session.get(WorkOrder, work_order_id)
            mission = await session.get(Mission, mission_id)
            evidence_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(FieldTaskEvidence)
                    .where(FieldTaskEvidence.task_id == task_id)
                )
                or 0
            )
            health_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(AssetHealthEvent)
                    .where(AssetHealthEvent.mission_id == mission_id)
                )
                or 0
            )
        assert task is not None and task.status == TaskStatus.PENDING.value
        assert work_order is not None and work_order.status == WorkOrderStatus.SCHEDULED.value
        assert mission is not None and mission.status == MissionStatus.EXECUTING.value
        assert evidence_count == 0
        assert health_count == 0

        async with factory() as session, session.begin():
            result = await complete_task(session, work_order_id, task_id, request, verifier)
        assert result["workflow_finalized"] is True
        async with factory() as session:
            task = await session.get(WorkOrderTask, task_id)
            work_order = await session.get(WorkOrder, work_order_id)
            mission = await session.get(Mission, mission_id)
            alarm = await session.get(Alarm, alarm_id)
            evidence_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(FieldTaskEvidence)
                    .where(FieldTaskEvidence.task_id == task_id)
                )
                or 0
            )
        assert task is not None and task.status == TaskStatus.COMPLETED.value
        assert work_order is not None and work_order.status == WorkOrderStatus.COMPLETED.value
        assert mission is not None and mission.status == MissionStatus.COMPLETED.value
        assert alarm is not None and alarm.status == AlarmStatus.RESOLVED.value
        assert evidence_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_approval_failure_has_no_partial_write_and_retry_is_consistent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _database_url()
    engine = create_async_engine(database_url, pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:10]
    async with factory() as session, session.begin():
        _, _, _, mission_id = await _seed_mission(
            session,
            suffix=suffix,
            status=MissionStatus.UNDER_REVIEW.value,
            revision=1,
        )
        session.add(
            Decision(
                id=f"DE-M2-{suffix}",
                mission_id=mission_id,
                status="pending_approval",
                alternatives=[{"alternative_id": "monitor"}],
                recommended_alternative_id="monitor",
                recommendation_reason="M-002 PostgreSQL rollback contract",
                risks=[],
            )
        )
    settings = Settings(
        environment=Environment.TEST,
        database_url=database_url,
        schema_bootstrap=False,
        demo_seed=False,
    )
    request = ApprovalRequest(
        action=ApprovalAction.REJECT,
        expected_revision=1,
        approver="m002-postgres-approver",
        reason="M-002 PostgreSQL approval rollback contract",
    )

    def fail_projection(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("injected PostgreSQL projection failure")

    try:
        with monkeypatch.context() as context:
            context.setattr(workflow, "enqueue_knowledge_graph_projection", fail_projection)
            with pytest.raises(RuntimeError, match="projection failure"):
                async with factory() as session, session.begin():
                    await record_approval(session, settings, mission_id, request)

        async with factory() as session:
            mission = await session.get(Mission, mission_id)
            approval_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Approval)
                    .where(Approval.mission_id == mission_id)
                )
                or 0
            )
            event_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(DomainEvent)
                    .where(DomainEvent.aggregate_id == mission_id)
                )
                or 0
            )
        assert mission is not None
        assert mission.status == MissionStatus.UNDER_REVIEW.value
        assert mission.revision == 1
        assert approval_count == 0
        assert event_count == 0

        async with factory() as session, session.begin():
            mission, approval, work_order = await record_approval(
                session, settings, mission_id, request
            )
        assert mission.status == MissionStatus.REJECTED.value
        assert mission.revision == 2
        assert approval.action == ApprovalAction.REJECT.value
        assert work_order is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_platform_first_revision_unique_race_is_atomic_and_retryable() -> None:
    engine = create_async_engine(_database_url(), pool_size=4, max_overflow=0)
    factory = async_sessionmaker(
        engine,
        class_=_FirstEmptyScalarBarrierSession,
        expire_on_commit=False,
    )
    async with factory() as session, session.begin():
        existing_ids = list(
            await session.scalars(
                select(PlatformConfigurationRevision.id).where(
                    PlatformConfigurationRevision.configuration_key == "event_stream"
                )
            )
        )
        if existing_ids:
            await session.execute(
                delete(DomainEvent).where(DomainEvent.aggregate_id.in_(existing_ids))
            )
        await session.execute(
            delete(PlatformConfigurationRevision).where(
                PlatformConfigurationRevision.configuration_key == "event_stream"
            )
        )

    request = PlatformConfigurationCreateRequest(
        configuration_key="event_stream",
        value={"transport": "sse", "max_batch_size": 100},
        expected_revision=0,
        reason="M-002 PostgreSQL unique-revision race",
    )
    barrier = asyncio.Barrier(2)

    async def create(subject: str) -> str:
        async with factory() as session:
            session.info["first_empty_scalar_barrier"] = barrier
            try:
                async with session.begin():
                    await create_platform_configuration_revision(session, request, subject=subject)
            except ConflictError:
                return "conflict"
            return "committed"

    try:
        results = await asyncio.wait_for(
            asyncio.gather(create("m002-platform-a"), create("m002-platform-b")), timeout=8
        )
        assert sorted(results) == ["committed", "conflict"]
        async with factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(PlatformConfigurationRevision)
                        .where(PlatformConfigurationRevision.configuration_key == "event_stream")
                        .order_by(PlatformConfigurationRevision.revision)
                    )
                ).all()
            )
        assert [(row.revision, row.active) for row in rows] == [(1, True)]

        retry = PlatformConfigurationCreateRequest(
            configuration_key="event_stream",
            value={"transport": "sse", "max_batch_size": 200},
            expected_revision=1,
            reason="M-002 PostgreSQL consistent retry",
        )
        async with factory() as session, session.begin():
            second = await create_platform_configuration_revision(
                session, retry, subject="m002-platform-retry"
            )
        assert second.revision == 2
        async with factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(PlatformConfigurationRevision)
                        .where(PlatformConfigurationRevision.configuration_key == "event_stream")
                        .order_by(PlatformConfigurationRevision.revision)
                    )
                ).all()
            )
            event_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(DomainEvent)
                    .where(DomainEvent.aggregate_id.in_([row.id for row in rows]))
                )
                or 0
            )
        assert [(row.revision, row.active) for row in rows] == [(1, False), (2, True)]
        assert event_count == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_alarm_same_key_race_replays_winner_and_stale_update_is_atomic() -> None:
    engine = create_async_engine(_database_url(), pool_size=4, max_overflow=0)
    factory = async_sessionmaker(
        engine,
        class_=_FirstEmptyScalarBarrierSession,
        expire_on_commit=False,
    )
    suffix = uuid4().hex[:10]
    async with factory() as session, session.begin():
        _, _, alarm_id, _ = await _seed_mission(
            session,
            suffix=suffix,
            status=MissionStatus.DETECTED.value,
            revision=1,
        )
    request = AlarmCommandRequest(
        action="acknowledge",
        expected_revision=1,
        reason="M-002 PostgreSQL concurrent replay",
    )
    idempotency_key = f"m002-alarm-{suffix}"
    barrier = asyncio.Barrier(2)

    async def acknowledge() -> tuple[dict[str, Any], bool]:
        async with factory() as session:
            session.info["first_empty_scalar_barrier"] = barrier
            async with session.begin():
                return await execute_alarm_command(
                    session,
                    alarm_id,
                    request,
                    idempotency_key=idempotency_key,
                    subject="m002-postgres-operator",
                )

    try:
        results = await asyncio.wait_for(asyncio.gather(acknowledge(), acknowledge()), timeout=8)
        assert results[0][0] == results[1][0]
        assert sorted(result[1] for result in results) == [False, True]
        async with factory() as session:
            alarm = await session.get(Alarm, alarm_id)
            receipts = list(
                (
                    await session.scalars(
                        select(CommandReceipt).where(CommandReceipt.target == alarm_id)
                    )
                ).all()
            )
            event_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(DomainEvent)
                    .where(DomainEvent.aggregate_id == alarm_id)
                )
                or 0
            )
        assert alarm is not None
        assert alarm.status == AlarmStatus.ACKNOWLEDGED.value
        assert alarm.revision == 2
        assert len(receipts) == 1 and receipts[0].replay_count == 1
        assert event_count == 1

        update_barrier = asyncio.Barrier(2)

        async def assign(subject: str) -> str:
            payload = AlarmCommandRequest(
                action="assign",
                expected_revision=2,
                reason="M-002 competing assignment",
            )
            async with factory() as session:
                await update_barrier.wait()
                try:
                    async with session.begin():
                        await execute_alarm_command(
                            session,
                            alarm_id,
                            payload,
                            idempotency_key=f"m002-assign-{subject}",
                            subject=subject,
                        )
                except ConflictError:
                    return "conflict"
                return "committed"

        updates = await asyncio.wait_for(
            asyncio.gather(assign("operator-a"), assign("operator-b")), timeout=8
        )
        assert sorted(updates) == ["committed", "conflict"]
        async with factory() as session:
            alarm = await session.get(Alarm, alarm_id)
            receipt_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(CommandReceipt)
                    .where(CommandReceipt.target == alarm_id)
                )
                or 0
            )
            event_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(DomainEvent)
                    .where(DomainEvent.aggregate_id == alarm_id)
                )
                or 0
            )
        assert alarm is not None and alarm.revision == 3
        assert alarm.assigned_to in {"operator-a", "operator-b"}
        assert receipt_count == 2
        assert event_count == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_operational_views_enforce_tenant_scope_on_real_routes() -> None:
    database_url = _database_url()
    engine = create_async_engine(database_url, pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:8]
    mission_ids: dict[str, str] = {}
    work_order_ids: dict[str, str] = {}
    async with factory() as session, session.begin():
        for marker in ("a", "b"):
            tenant_id = f"tenant-m2-{suffix}-{marker}"
            chain_suffix = f"{suffix}{marker}"
            _, turbine_id, _, mission_id = await _seed_mission(
                session,
                suffix=chain_suffix,
                tenant_id=tenant_id,
                status=MissionStatus.EXECUTING.value,
                revision=2,
            )
            approval_id = str(uuid4())
            work_order_id = f"WO-M2-SCOPE-{chain_suffix}"
            planned_start = datetime.now(UTC) + timedelta(days=1)
            session.add(
                Approval(
                    id=approval_id,
                    mission_id=mission_id,
                    mission_revision=1,
                    action=ApprovalAction.APPROVE.value,
                    approver="m002-scope-reviewer",
                    reason="M-002 operational scope contract",
                )
            )
            await session.flush()
            session.add(
                WorkOrder(
                    id=work_order_id,
                    mission_id=mission_id,
                    approval_id=approval_id,
                    turbine_id=turbine_id,
                    title=f"M-002 scope {suffix} work order {marker}",
                    selected_alternative_id="monitor",
                    selected_action="Monitor scoped asset",
                    status=WorkOrderStatus.SCHEDULED.value,
                    planned_start=planned_start,
                    deadline=planned_start + timedelta(hours=2),
                    estimated_duration_hours=2,
                )
            )
            await session.flush()
            mission_ids[marker] = mission_id
            work_order_ids[marker] = work_order_id
    await engine.dispose()

    settings = Settings(
        environment=Environment.TEST,
        database_url=database_url,
        schema_bootstrap=False,
        demo_seed=False,
        agent_mode="deterministic",
        test_auth_bypass_enabled=True,
        outbox_inline_drain=True,
        knowledge_graph_backend="memory",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        headers = {
            "X-WindOps-Test-Principal": "m002-scoped-operator",
            "X-WindOps-Test-Role": "test_system",
            "X-WindOps-Test-Tenant-Ids": f"tenant-m2-{suffix}-a",
        }
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers=headers,
        ) as client:
            diagnoses = await client.get("/api/v1/diagnoses", params={"q": suffix, "limit": 64})
            plans = await client.get("/api/v1/maintenance-plans", params={"q": suffix, "limit": 50})
    assert diagnoses.status_code == 200, diagnoses.text
    assert plans.status_code == 200, plans.text
    diagnosis_body = diagnoses.json()
    plan_body = plans.json()
    assert diagnosis_body["meta"]["filtered_total"] == 1
    assert [row["missionId"] for row in diagnosis_body["data"]] == [mission_ids["a"]]
    assert mission_ids["b"] not in {row["missionId"] for row in diagnosis_body["data"]}
    assert plan_body["meta"]["filtered_total"] == 1
    assert [row["workOrderId"] for row in plan_body["data"]] == [work_order_ids["a"]]
    assert work_order_ids["b"] not in {row["workOrderId"] for row in plan_body["data"]}
