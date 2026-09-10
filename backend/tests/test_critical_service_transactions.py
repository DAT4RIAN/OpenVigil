from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.enums import (
    AlarmStatus,
    ApprovalAction,
    MissionStatus,
    TaskStatus,
    WorkOrderStatus,
)
from windops_backend.errors import ConflictError
from windops_backend.models import (
    AgentDefinition,
    AgentSkillLink,
    AgentToolLink,
    Alarm,
    Approval,
    CommandReceipt,
    Decision,
    DomainEvent,
    IngestReceipt,
    KnowledgeCase,
    Mission,
    PlatformConfigurationRevision,
    Resource,
    ResourceReservation,
    Turbine,
    WeatherWindow,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.schemas import (
    AgentReleaseRequest,
    AlarmCommandRequest,
    ApprovalRequest,
    PlatformConfigurationCreateRequest,
    ResourceReassignRequest,
    ResourceStockAdjustRequest,
    TaskCompletionRequest,
    WorkOrderScheduleUpdateRequest,
)
from windops_backend.services import agent_governance, alarms, platform_governance, workflow
from windops_backend.services.agent_governance import control_agent, create_agent_release
from windops_backend.services.alarms import execute_alarm_command
from windops_backend.services.platform_governance import (
    active_platform_configurations,
    adjust_resource_stock,
    create_platform_configuration_revision,
    reassign_resource,
    update_work_order_schedule,
)
from windops_backend.services.workflow import record_approval
from windops_backend.services.workorders import complete_task
from windops_backend.storage import FieldTaskEvidence, InMemoryArtifactVerifier


async def _seed_single_task_work_order(app: FastAPI, suffix: str) -> tuple[str, str, str, str]:
    receipt_id = f"M002-WO-RECEIPT-{suffix}"
    alarm_id = f"M002-WO-ALARM-{suffix}"
    mission_id = f"M002-WO-MISSION-{suffix}"
    approval_id = str(uuid4())
    work_order_id = f"M002-WO-{suffix}"
    task_id = str(uuid4())
    async with app.state.session_factory() as session, session.begin():
        session.add(IngestReceipt(source_event_id=receipt_id, payload_hash="a" * 64))
        await session.flush()
        session.add(
            Alarm(
                id=alarm_id,
                turbine_id="WT-023",
                source_event_id=receipt_id,
                code="M002-WORKORDER",
                subsystem="main_bearing",
                title="M-002 work-order rollback contract",
                severity="major",
                status=AlarmStatus.ACKNOWLEDGED.value,
                triggered_at=datetime.now(UTC),
                evidence={},
            )
        )
        await session.flush()
        session.add(
            Mission(
                id=mission_id,
                alarm_id=alarm_id,
                turbine_id="WT-023",
                title="M-002 work-order rollback contract",
                status=MissionStatus.EXECUTING.value,
                revision=2,
                public_state={"workflow_status": MissionStatus.EXECUTING.value},
            )
        )
        await session.flush()
        session.add(
            Approval(
                id=approval_id,
                mission_id=mission_id,
                mission_revision=1,
                action=ApprovalAction.APPROVE.value,
                approver="m002-reviewer",
                reason="M-002 transaction contract",
            )
        )
        await session.flush()
        session.add(
            WorkOrder(
                id=work_order_id,
                mission_id=mission_id,
                approval_id=approval_id,
                turbine_id="WT-023",
                title="M-002 governed field task",
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
    return work_order_id, task_id, mission_id, alarm_id


@pytest.mark.asyncio
async def test_work_order_late_failure_rolls_back_and_retry_commits_once(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = uuid4().hex[:8]
    work_order_id, task_id, mission_id, alarm_id = await _seed_single_task_work_order(app, suffix)
    artifact_uri = f"minio://test/m002/{task_id}.json"
    artifact_sha256 = "b" * 64
    verifier = InMemoryArtifactVerifier()
    verifier.register(artifact_uri, artifact_sha256)
    request = TaskCompletionRequest(
        result="Return-to-service measurement verified",
        artifact_uri=artifact_uri,
        artifact_sha256=artifact_sha256,
        measurement={"turbine_health_score": 88},
        completed_by="m002-field-technician",
    )

    async def fail_health_side_effect(self: SQLToolAdapter, **kwargs: Any) -> dict[str, Any]:
        del self, kwargs
        raise RuntimeError("injected asset-health persistence failure")

    with monkeypatch.context() as context:
        context.setattr(SQLToolAdapter, "update_asset_health", fail_health_side_effect)
        with pytest.raises(RuntimeError, match="asset-health persistence failure"):
            async with app.state.session_factory() as session, session.begin():
                await complete_task(session, work_order_id, task_id, request, verifier)

    async with app.state.session_factory() as session:
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
        event_count = int(
            await session.scalar(
                select(func.count())
                .select_from(DomainEvent)
                .where(DomainEvent.aggregate_id == work_order_id)
            )
            or 0
        )
    assert task is not None and task.status == TaskStatus.PENDING.value
    assert work_order is not None and work_order.status == WorkOrderStatus.SCHEDULED.value
    assert mission is not None and mission.status == MissionStatus.EXECUTING.value
    assert alarm is not None and alarm.status == AlarmStatus.ACKNOWLEDGED.value
    assert evidence_count == 0
    assert event_count == 0

    async with app.state.session_factory() as session, session.begin():
        result = await complete_task(session, work_order_id, task_id, request, verifier)
    assert result["workflow_finalized"] is True
    assert result["already_completed"] is False

    async with app.state.session_factory() as session:
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
        case_count = int(
            await session.scalar(
                select(func.count())
                .select_from(KnowledgeCase)
                .where(KnowledgeCase.mission_id == mission_id)
            )
            or 0
        )
    assert task is not None and task.status == TaskStatus.COMPLETED.value
    assert work_order is not None and work_order.status == WorkOrderStatus.COMPLETED.value
    assert mission is not None and mission.status == MissionStatus.COMPLETED.value
    assert alarm is not None and alarm.status == AlarmStatus.RESOLVED.value
    assert evidence_count == 1
    assert case_count == 1


@pytest.mark.asyncio
async def test_approval_projection_failure_has_no_partial_write_and_retry_is_consistent(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_event_id = f"M002-WORKFLOW-{uuid4().hex[:10]}"
    created = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": source_event_id,
                    "turbine_id": "WT-023",
                    "observed_at": datetime.now(UTC).isoformat(),
                    "variable": "main_bearing_vibration_rms",
                    "value": 5.2,
                    "unit": "mm/s",
                    "quality": "good",
                    "attributes": {"baseline": 3.7, "anomaly_score": 0.92},
                }
            ]
        },
    )
    assert created.status_code == 202, created.text
    mission_id = created.json()["results"][0]["mission_id"]

    async with app.state.session_factory() as session:
        mission = await session.get(Mission, mission_id)
        decision = await session.scalar(select(Decision).where(Decision.mission_id == mission_id))
        assert mission is not None and decision is not None
        original_revision = mission.revision
        selected_alternative_id = decision.recommended_alternative_id

    request = ApprovalRequest(
        action=ApprovalAction.APPROVE,
        expected_revision=original_revision,
        selected_alternative_id=selected_alternative_id,
        approver="m002-approver",
        reason="M-002 approval rollback contract",
    )

    def fail_projection(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("injected projection enqueue failure")

    with monkeypatch.context() as context:
        context.setattr(workflow, "enqueue_knowledge_graph_projection", fail_projection)
        with pytest.raises(RuntimeError, match="projection enqueue failure"):
            async with app.state.session_factory() as session, session.begin():
                await record_approval(session, app.state.settings, mission_id, request)

    async with app.state.session_factory() as session:
        mission = await session.get(Mission, mission_id)
        approval_count = int(
            await session.scalar(
                select(func.count()).select_from(Approval).where(Approval.mission_id == mission_id)
            )
            or 0
        )
        work_order_count = int(
            await session.scalar(
                select(func.count())
                .select_from(WorkOrder)
                .where(WorkOrder.mission_id == mission_id)
            )
            or 0
        )
        reservation_count = int(
            await session.scalar(
                select(func.count())
                .select_from(ResourceReservation)
                .where(ResourceReservation.mission_id == mission_id)
            )
            or 0
        )
    assert mission is not None
    assert mission.status == MissionStatus.UNDER_REVIEW.value
    assert mission.revision == original_revision
    assert approval_count == 0
    assert work_order_count == 0
    assert reservation_count == 0

    async with app.state.session_factory() as session, session.begin():
        mission, approval, work_order = await record_approval(
            session, app.state.settings, mission_id, request
        )
    assert mission.status == MissionStatus.EXECUTING.value
    assert mission.revision == original_revision + 1
    assert approval.action == ApprovalAction.APPROVE.value
    assert work_order is not None


@pytest.mark.asyncio
async def test_platform_revision_failure_restores_active_row_and_retry_advances_once(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_request = PlatformConfigurationCreateRequest(
        configuration_key="event_stream",
        value={"transport": "sse", "max_batch_size": 100},
        expected_revision=0,
        reason="M-002 initial governed event stream",
    )
    async with app.state.session_factory() as session, session.begin():
        first = await create_platform_configuration_revision(
            session, first_request, subject="m002-platform-manager"
        )
        first_id = first.id

    second_request = PlatformConfigurationCreateRequest(
        configuration_key="event_stream",
        value={"transport": "sse", "max_batch_size": 200},
        expected_revision=1,
        reason="M-002 revised governed event stream",
    )

    def fail_event(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("injected platform event failure")

    with monkeypatch.context() as context:
        context.setattr(platform_governance, "append_domain_event", fail_event)
        with pytest.raises(RuntimeError, match="platform event failure"):
            async with app.state.session_factory() as session, session.begin():
                await create_platform_configuration_revision(
                    session, second_request, subject="m002-platform-manager"
                )

    async with app.state.session_factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(PlatformConfigurationRevision)
                    .where(PlatformConfigurationRevision.configuration_key == "event_stream")
                    .order_by(PlatformConfigurationRevision.revision)
                )
            ).all()
        )
    assert [(row.id, row.revision, row.active) for row in rows] == [(first_id, 1, True)]

    async with app.state.session_factory() as session, session.begin():
        second = await create_platform_configuration_revision(
            session, second_request, subject="m002-platform-manager"
        )
    assert second.revision == 2
    async with app.state.session_factory() as session:
        active = await active_platform_configurations(session)
        event_stream_rows = [row for row in active if row.configuration_key == "event_stream"]
    assert [row.revision for row in event_stream_rows] == [2]


@pytest.mark.asyncio
async def test_platform_resource_and_schedule_side_effect_failures_are_atomic(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = uuid4().hex[:8]
    work_order_id, _, mission_id, _ = await _seed_single_task_work_order(app, suffix)
    source_id = f"M2-CREW-SRC-{suffix}"
    target_id = f"M2-CREW-DST-{suffix}"
    wrong_type_id = f"M2-VESSEL-{suffix}"
    stock_id = f"M2-SPARE-{suffix}"
    source_reservation_id = str(uuid4())
    async with app.state.session_factory() as session, session.begin():
        session.add_all(
            [
                Resource(
                    id=source_id,
                    resource_type="crew",
                    name="M-002 source crew",
                    quantity=1,
                    status="reserved",
                    attributes={},
                ),
                Resource(
                    id=target_id,
                    resource_type="crew",
                    name="M-002 target crew",
                    quantity=1,
                    status="available",
                    attributes={},
                ),
                Resource(
                    id=wrong_type_id,
                    resource_type="vessel",
                    name="M-002 wrong-type vessel",
                    quantity=1,
                    status="available",
                    attributes={},
                ),
                Resource(
                    id=stock_id,
                    resource_type="spare_part",
                    name="M-002 governed spare",
                    quantity=1,
                    status="reserved",
                    attributes={},
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ResourceReservation(
                    id=source_reservation_id,
                    mission_id=mission_id,
                    resource_id=source_id,
                    quantity=1,
                ),
                ResourceReservation(
                    id=str(uuid4()),
                    mission_id=mission_id,
                    resource_id=stock_id,
                    quantity=1,
                ),
            ]
        )

    async with app.state.session_factory() as session:
        stock = await session.get(Resource, stock_id)
        assert stock is not None
        stock_updated_at = stock.updated_at
    with pytest.raises(ConflictError, match="reserved quantity"):
        async with app.state.session_factory() as session, session.begin():
            await adjust_resource_stock(
                session,
                resource_id=stock_id,
                request=ResourceStockAdjustRequest(
                    quantity_delta=-1,
                    expected_updated_at=stock_updated_at,
                    reason="M-002 reject stock below reservation",
                ),
                subject="m002-resource-manager",
            )
    async with app.state.session_factory() as session, session.begin():
        stock = await adjust_resource_stock(
            session,
            resource_id=stock_id,
            request=ResourceStockAdjustRequest(
                quantity_delta=1,
                expected_updated_at=stock_updated_at,
                reason="M-002 replenish governed spare",
            ),
            subject="m002-resource-manager",
        )
        assert stock.quantity == 2

    with pytest.raises(ConflictError, match="same resource type"):
        async with app.state.session_factory() as session, session.begin():
            await reassign_resource(
                session,
                ResourceReassignRequest(
                    mission_id=mission_id,
                    from_resource_id=source_id,
                    to_resource_id=wrong_type_id,
                    reason="M-002 reject cross-type reassignment",
                ),
                subject="m002-resource-manager",
                eam_enabled=False,
            )

    def fail_eam_enqueue(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("injected EAM enqueue failure")

    reassign_request = ResourceReassignRequest(
        mission_id=mission_id,
        from_resource_id=source_id,
        to_resource_id=target_id,
        reason="M-002 atomic crew reassignment",
    )
    with monkeypatch.context() as context:
        context.setattr(platform_governance, "enqueue_eam_work_order_publish", fail_eam_enqueue)
        with pytest.raises(RuntimeError, match="EAM enqueue failure"):
            async with app.state.session_factory() as session, session.begin():
                await reassign_resource(
                    session,
                    reassign_request,
                    subject="m002-resource-manager",
                    eam_enabled=True,
                )

    async with app.state.session_factory() as session:
        reservation = await session.get(ResourceReservation, source_reservation_id)
        source = await session.get(Resource, source_id)
        target = await session.get(Resource, target_id)
        work_order = await session.get(WorkOrder, work_order_id)
    assert reservation is not None and reservation.resource_id == source_id
    assert source is not None and source.status == "reserved"
    assert target is not None and target.status == "available"
    assert work_order is not None and work_order.assigned_team != "M-002 target crew"

    async with app.state.session_factory() as session, session.begin():
        reservation = await reassign_resource(
            session,
            reassign_request,
            subject="m002-resource-manager",
            eam_enabled=False,
        )
        assert reservation.resource_id == target_id

    async with app.state.session_factory() as session:
        work_order = await session.get(WorkOrder, work_order_id)
        turbine = await session.get(Turbine, "WT-023")
        assert work_order is not None and turbine is not None
        weather = await session.scalar(
            select(WeatherWindow)
            .where(
                WeatherWindow.wind_farm_id == turbine.wind_farm_id,
                WeatherWindow.suitable.is_(True),
            )
            .order_by(WeatherWindow.starts_at)
        )
        assert weather is not None
        planned_start = (
            weather.starts_at.replace(tzinfo=UTC)
            if weather.starts_at.tzinfo is None
            else weather.starts_at
        )
        deadline = (
            weather.ends_at.replace(tzinfo=UTC)
            if weather.ends_at.tzinfo is None
            else weather.ends_at
        )
        schedule_request = WorkOrderScheduleUpdateRequest(
            planned_start=planned_start,
            deadline=deadline,
            assigned_team="M-002 target crew",
            expected_updated_at=work_order.updated_at,
            reason="M-002 governed weather schedule",
        )

    async with app.state.session_factory() as session, session.begin():
        dry_run = await update_work_order_schedule(
            session,
            work_order_id=work_order_id,
            request=schedule_request,
            subject="m002-scheduler",
            eam_enabled=False,
            dry_run=True,
        )
        assert dry_run.planned_start is None

    with monkeypatch.context() as context:
        context.setattr(platform_governance, "enqueue_eam_work_order_publish", fail_eam_enqueue)
        with pytest.raises(RuntimeError, match="EAM enqueue failure"):
            async with app.state.session_factory() as session, session.begin():
                await update_work_order_schedule(
                    session,
                    work_order_id=work_order_id,
                    request=schedule_request,
                    subject="m002-scheduler",
                    eam_enabled=True,
                )
    async with app.state.session_factory() as session:
        work_order = await session.get(WorkOrder, work_order_id)
    assert work_order is not None and work_order.planned_start is None

    async with app.state.session_factory() as session, session.begin():
        scheduled = await update_work_order_schedule(
            session,
            work_order_id=work_order_id,
            request=schedule_request,
            subject="m002-scheduler",
            eam_enabled=False,
        )
        assert scheduled.planned_start is not None
    with pytest.raises(ConflictError, match="changed"):
        async with app.state.session_factory() as session, session.begin():
            await update_work_order_schedule(
                session,
                work_order_id=work_order_id,
                request=schedule_request,
                subject="m002-scheduler",
                eam_enabled=False,
            )


@pytest.mark.asyncio
async def test_alarm_event_failure_rolls_back_then_same_key_replays_exactly_once(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = uuid4().hex[:8]
    receipt_id = f"M002-ALARM-RECEIPT-{suffix}"
    alarm_id = f"M002-ALARM-{suffix}"
    async with app.state.session_factory() as session, session.begin():
        session.add(IngestReceipt(source_event_id=receipt_id, payload_hash="c" * 64))
        await session.flush()
        session.add(
            Alarm(
                id=alarm_id,
                turbine_id="WT-023",
                source_event_id=receipt_id,
                code="M002-ALARM",
                subsystem="gearbox",
                title="M-002 alarm rollback contract",
                severity="major",
                status=AlarmStatus.OPEN.value,
                triggered_at=datetime.now(UTC),
                evidence={},
            )
        )
    request = AlarmCommandRequest(
        action="acknowledge",
        expected_revision=1,
        reason="M-002 acknowledge transaction contract",
    )
    idempotency_key = f"m002-alarm-{suffix}"

    def fail_event(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("injected alarm event failure")

    with monkeypatch.context() as context:
        context.setattr(alarms, "append_domain_event", fail_event)
        with pytest.raises(RuntimeError, match="alarm event failure"):
            async with app.state.session_factory() as session, session.begin():
                await execute_alarm_command(
                    session,
                    alarm_id,
                    request,
                    idempotency_key=idempotency_key,
                    subject="m002-operator",
                )

    async with app.state.session_factory() as session:
        alarm = await session.get(Alarm, alarm_id)
        receipt_count = int(
            await session.scalar(
                select(func.count())
                .select_from(CommandReceipt)
                .where(CommandReceipt.target == alarm_id)
            )
            or 0
        )
    assert alarm is not None
    assert alarm.status == AlarmStatus.OPEN.value
    assert alarm.revision == 1
    assert receipt_count == 0

    async with app.state.session_factory() as session, session.begin():
        first, first_replayed = await execute_alarm_command(
            session,
            alarm_id,
            request,
            idempotency_key=idempotency_key,
            subject="m002-operator",
        )
    async with app.state.session_factory() as session, session.begin():
        replay, replayed = await execute_alarm_command(
            session,
            alarm_id,
            request,
            idempotency_key=idempotency_key,
            subject="m002-operator",
        )
    assert first_replayed is False
    assert replayed is True
    assert replay == first

    async with app.state.session_factory() as session:
        receipt = await session.scalar(
            select(CommandReceipt).where(CommandReceipt.target == alarm_id)
        )
        event_count = int(
            await session.scalar(
                select(func.count())
                .select_from(DomainEvent)
                .where(DomainEvent.aggregate_id == alarm_id)
            )
            or 0
        )
    assert receipt is not None and receipt.replay_count == 1
    assert event_count == 1


@pytest.mark.asyncio
async def test_agent_control_failure_rolls_back_and_release_clones_governed_links(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with app.state.session_factory() as session:
        source = await session.scalar(
            select(AgentDefinition)
            .where(
                AgentDefinition.agent_key == "scada_analysis_agent",
                AgentDefinition.active.is_(True),
            )
            .order_by(AgentDefinition.version.desc())
        )
        assert source is not None
        source_id = source.id
        skill_count = int(
            await session.scalar(
                select(func.count())
                .select_from(AgentSkillLink)
                .where(AgentSkillLink.agent_definition_id == source_id)
            )
            or 0
        )
        tool_count = int(
            await session.scalar(
                select(func.count())
                .select_from(AgentToolLink)
                .where(AgentToolLink.agent_definition_id == source_id)
            )
            or 0
        )

    def fail_event(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("injected agent event failure")

    with monkeypatch.context() as context:
        context.setattr(agent_governance, "append_domain_event", fail_event)
        with pytest.raises(RuntimeError, match="agent event failure"):
            async with app.state.session_factory() as session, session.begin():
                await control_agent(
                    session,
                    agent_key="scada_analysis_agent",
                    expected_definition_id=source_id,
                    enabled=False,
                    reason="M-002 rollback contract",
                    subject="m002-agent-manager",
                )

    async with app.state.session_factory() as session:
        source = await session.get(AgentDefinition, source_id)
    assert source is not None and source.active is True

    version = f"m002-{uuid4().hex[:8]}"
    async with app.state.session_factory() as session, session.begin():
        stopped = await control_agent(
            session,
            agent_key="scada_analysis_agent",
            expected_definition_id=source_id,
            enabled=False,
            reason="M-002 controlled stop",
            subject="m002-agent-manager",
        )
        assert stopped.active is False
        release = await create_agent_release(
            session,
            agent_key="scada_analysis_agent",
            request=AgentReleaseRequest(
                source_definition_id=source_id,
                version=version,
                display_name="M-002 SCADA Analysis Agent",
                role="scada_analysis_agent",
                description="M-002 failure-path coverage release",
                reason="M-002 governed release contract",
            ),
            subject="m002-agent-manager",
        )
        release_id = release.id

    async with app.state.session_factory() as session:
        released = await session.get(AgentDefinition, release_id)
        released_skill_count = int(
            await session.scalar(
                select(func.count())
                .select_from(AgentSkillLink)
                .where(AgentSkillLink.agent_definition_id == release_id)
            )
            or 0
        )
        released_tool_count = int(
            await session.scalar(
                select(func.count())
                .select_from(AgentToolLink)
                .where(AgentToolLink.agent_definition_id == release_id)
            )
            or 0
        )
    assert released is not None and released.active is True
    assert released_skill_count == skill_count
    assert released_tool_count == tool_count

    with pytest.raises(ConflictError):
        async with app.state.session_factory() as session, session.begin():
            await create_agent_release(
                session,
                agent_key="scada_analysis_agent",
                request=AgentReleaseRequest(
                    source_definition_id=source_id,
                    version=version,
                    display_name="Duplicate M-002 release",
                    role="scada_analysis_agent",
                    description="Duplicate release must be rejected",
                    reason="M-002 duplicate release contract",
                ),
                subject="m002-agent-manager",
            )
