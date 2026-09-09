from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.enums import (
    AlarmStatus,
    MissionStatus,
    ResourceStatus,
    TaskStatus,
    TurbineStatus,
    WorkOrderStatus,
)
from windops_backend.errors import InvalidTransitionError, NotFoundError
from windops_backend.models import (
    Alarm,
    KnowledgeCase,
    Mission,
    Resource,
    ResourceReservation,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.schemas import TASK_MEASUREMENT_SCHEMAS, TaskCompletionRequest
from windops_backend.storage import ArtifactVerifier, FieldTaskEvidence


async def complete_task(
    session: AsyncSession,
    work_order_id: str,
    task_id: str,
    request: TaskCompletionRequest,
    artifact_verifier: ArtifactVerifier,
) -> dict[str, Any]:
    work_order = await session.scalar(
        select(WorkOrder).where(WorkOrder.id == work_order_id).with_for_update()
    )
    if work_order is None:
        raise NotFoundError(f"work order {work_order_id} was not found")
    task = await session.get(WorkOrderTask, task_id)
    if task is None or task.work_order_id != work_order_id:
        raise NotFoundError(f"task {task_id} was not found in {work_order_id}")
    if task.status == TaskStatus.COMPLETED.value:
        return {
            "task_id": task.id,
            "task_status": task.status,
            "work_order_status": work_order.status,
            "already_completed": True,
        }
    if work_order.status == WorkOrderStatus.COMPLETED.value:
        raise InvalidTransitionError("a completed work order cannot accept new task results")

    earlier_pending = await session.scalar(
        select(func.count())
        .select_from(WorkOrderTask)
        .where(
            WorkOrderTask.work_order_id == work_order_id,
            WorkOrderTask.sequence < task.sequence,
            WorkOrderTask.status != TaskStatus.COMPLETED.value,
        )
    )
    if earlier_pending:
        raise InvalidTransitionError(
            f"task sequence {task.sequence} cannot complete before its predecessors"
        )

    measurement_schema = TASK_MEASUREMENT_SCHEMAS.get(task.sequence)
    if measurement_schema is None:  # pragma: no cover - task creation is fixed at five rows
        raise InvalidTransitionError(f"task sequence {task.sequence} has no measurement schema")
    try:
        normalized_measurement = measurement_schema.model_validate(request.measurement).model_dump()
    except ValidationError as exc:
        issues = "; ".join(
            f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
            for issue in exc.errors(include_url=False)
        )
        raise InvalidTransitionError(
            f"task sequence {task.sequence} measurement failed its operational gate: {issues}"
        ) from exc
    normalized_measurement["schema_version"] = f"wt023-field-task-{task.sequence}-v1"

    try:
        await artifact_verifier.verify(request.artifact_uri, request.artifact_sha256)
    except ValueError as exc:
        raise InvalidTransitionError(str(exc)) from exc

    now = datetime.now(UTC)
    session.add(
        FieldTaskEvidence(
            id=str(uuid4()),
            task_id=task.id,
            artifact_uri=request.artifact_uri,
            artifact_sha256=request.artifact_sha256.lower(),
            measurement=normalized_measurement,
            verified_by=request.completed_by,
            verified_at=now,
        )
    )
    task.status = TaskStatus.COMPLETED.value
    task.result = request.result
    task.completed_by = request.completed_by
    task.completed_at = now
    if work_order.status == WorkOrderStatus.SCHEDULED.value:
        work_order.status = WorkOrderStatus.IN_PROGRESS.value
    await session.flush()

    pending = await session.scalar(
        select(func.count())
        .select_from(WorkOrderTask)
        .where(
            WorkOrderTask.work_order_id == work_order_id,
            WorkOrderTask.status == TaskStatus.PENDING.value,
        )
    )
    evidence_count = await session.scalar(
        select(func.count())
        .select_from(FieldTaskEvidence)
        .join(WorkOrderTask, WorkOrderTask.id == FieldTaskEvidence.task_id)
        .where(WorkOrderTask.work_order_id == work_order_id)
    )
    finalized = pending == 0 and evidence_count == 5
    case_id: str | None = None
    if finalized:
        work_order.status = WorkOrderStatus.COMPLETED.value
        work_order.completed_at = now
        mission = await session.get(Mission, work_order.mission_id)
        if mission is None:  # pragma: no cover - protected by FK
            raise RuntimeError("work order lost its mission")
        mission.status = MissionStatus.COMPLETED.value
        mission.revision += 1
        mission.updated_at = now
        mission.public_state = {**mission.public_state, "workflow_status": "completed"}
        alarm = await session.get(Alarm, mission.alarm_id)
        if alarm is not None:
            alarm.status = AlarmStatus.RESOLVED.value
            alarm.ai_status = "completed"

        tools = SQLToolAdapter(session)
        await tools.update_asset_health(
            turbine_id=work_order.turbine_id,
            mission_id=mission.id,
            score=82,
            status=TurbineStatus.RUNNING.value,
            reason=(
                "five verified field tasks restored turbine health to 82 "
                "and main-bearing health to 78"
            ),
        )
        tasks = (
            await session.scalars(
                select(WorkOrderTask)
                .where(WorkOrderTask.work_order_id == work_order_id)
                .order_by(WorkOrderTask.sequence)
            )
        ).all()
        evidence_rows = (
            await session.scalars(
                select(FieldTaskEvidence)
                .join(WorkOrderTask, WorkOrderTask.id == FieldTaskEvidence.task_id)
                .where(WorkOrderTask.work_order_id == work_order_id)
            )
        ).all()
        evidence_by_task = {row.task_id: row for row in evidence_rows}
        existing_case = await session.scalar(
            select(KnowledgeCase).where(KnowledgeCase.mission_id == mission.id)
        )
        if existing_case is None:
            case_id = f"CASE-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:6].upper()}"
            case = KnowledgeCase(
                id=case_id,
                mission_id=mission.id,
                work_order_id=work_order.id,
                turbine_id=work_order.turbine_id,
                title="WT-023 early main-bearing degradation: inspected and stabilized",
                diagnosis=mission.public_state.get("diagnosis", {}),
                resolution={
                    "verified_health_score": 82,
                    "main_bearing_health_score": 78,
                    "completed_tasks": [
                        {
                            "sequence": row.sequence,
                            "title": row.title,
                            "result": row.result,
                            "evidence": {
                                "artifact_uri": evidence_by_task[row.id].artifact_uri,
                                "artifact_sha256": evidence_by_task[row.id].artifact_sha256,
                                "measurement": evidence_by_task[row.id].measurement,
                                "verified_by": evidence_by_task[row.id].verified_by,
                                "verified_at": evidence_by_task[row.id].verified_at.isoformat(),
                            },
                        }
                        for row in tasks
                    ],
                    "closed_at": now.isoformat(),
                },
            )
            session.add(case)
        else:
            case_id = existing_case.id

        reservations = (
            await session.scalars(
                select(ResourceReservation).where(ResourceReservation.mission_id == mission.id)
            )
        ).all()
        for reservation in reservations:
            resource = await session.get(Resource, reservation.resource_id)
            if resource is not None:
                resource.status = ResourceStatus.AVAILABLE.value
        await session.flush()

    return {
        "task_id": task.id,
        "task_status": task.status,
        "work_order_status": work_order.status,
        "already_completed": False,
        "workflow_finalized": finalized,
        "knowledge_case_id": case_id,
        "evidence": {
            "artifact_uri": request.artifact_uri,
            "artifact_sha256": request.artifact_sha256.lower(),
            "measurement": normalized_measurement,
            "verified_by": request.completed_by,
        },
    }
