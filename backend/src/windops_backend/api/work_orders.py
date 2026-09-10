from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.api.deps import (
    Principal,
    _drain_or_dispatch_graph_projection_events,
    _utc_iso,
    get_artifact_verifier,
    get_runtime_settings,
    get_session,
    require_read_access,
    require_roles,
)
from windops_backend.config import Settings
from windops_backend.errors import (
    InvalidTransitionError,
    NotFoundError,
)
from windops_backend.models import (
    ExternalWorkOrderLink,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.schemas import (
    ArtifactUploadRequest,
    EamWorkOrderStatusUpdate,
    TaskCompletionRequest,
    WorkOrderScheduleUpdateRequest,
)
from windops_backend.services.eam import record_eam_status
from windops_backend.services.idempotency import execute_idempotent_command
from windops_backend.services.platform_governance import (
    update_work_order_schedule,
)
from windops_backend.services.workorders import complete_task
from windops_backend.storage import ArtifactVerifier

router = APIRouter()


@router.get("/work-orders", tags=["work-orders"])
async def work_orders(
    turbine_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = select(WorkOrder)
    if turbine_id:
        statement = statement.where(WorkOrder.turbine_id == turbine_id)
    if status_filter:
        statement = statement.where(WorkOrder.status == status_filter)
    if cursor:
        statement = statement.where(WorkOrder.id > cursor)
    rows = list((await session.scalars(statement.order_by(WorkOrder.id).limit(limit + 1))).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    task_rows = (
        (
            await session.scalars(
                select(WorkOrderTask)
                .where(WorkOrderTask.work_order_id.in_([row.id for row in page]))
                .order_by(WorkOrderTask.work_order_id, WorkOrderTask.sequence)
            )
        ).all()
        if page
        else []
    )
    tasks_by_work_order: dict[str, list[WorkOrderTask]] = {}
    for task in task_rows:
        tasks_by_work_order.setdefault(task.work_order_id, []).append(task)
    external_links = (
        list(
            (
                await session.scalars(
                    select(ExternalWorkOrderLink).where(
                        ExternalWorkOrderLink.work_order_id.in_([row.id for row in page])
                    )
                )
            ).all()
        )
        if page
        else []
    )
    external_by_work_order = {link.work_order_id: link for link in external_links}
    return {
        "count": len(page),
        "next_cursor": page[-1].id if has_more and page else None,
        "work_orders": [
            {
                "work_order_id": row.id,
                "mission_id": row.mission_id,
                "turbine_id": row.turbine_id,
                "title": row.title,
                "selected_alternative_id": row.selected_alternative_id,
                "selected_action": row.selected_action,
                "status": row.status,
                "priority": row.priority,
                "assigned_team": row.assigned_team,
                "created_by": row.created_by,
                "safety_plan": row.safety_plan,
                "closure_policy": row.closure_policy,
                "tasks": [
                    {
                        "task_id": task.id,
                        "sequence": task.sequence,
                        "title": task.title,
                        "status": task.status,
                        "schema_version": task.schema_version,
                        "measurement_schema": task.measurement_schema,
                        "result": task.result,
                        "completed_by": task.completed_by,
                        "completed_at": task.completed_at,
                    }
                    for task in tasks_by_work_order.get(row.id, [])
                ],
                "planned_start": _utc_iso(row.planned_start),
                "deadline": _utc_iso(row.deadline),
                "estimated_duration_hours": row.estimated_duration_hours,
                "created_at": _utc_iso(row.created_at),
                "updated_at": _utc_iso(row.updated_at),
                "completed_at": _utc_iso(row.completed_at),
                "eam": (
                    {
                        "provider": external_by_work_order[row.id].provider,
                        "external_id": external_by_work_order[row.id].external_id,
                        "sync_status": external_by_work_order[row.id].sync_status,
                        "external_updated_at": external_by_work_order[row.id].external_updated_at,
                        "updated_at": external_by_work_order[row.id].updated_at,
                    }
                    if row.id in external_by_work_order
                    else {"sync_status": "pending"}
                    if settings.eam_enabled
                    else None
                ),
            }
            for row in page
        ],
    }


@router.get("/work-orders/{work_order_id}", tags=["work-orders"])
async def work_order_detail(
    work_order_id: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    work_order = await session.get(WorkOrder, work_order_id)
    if work_order is None:
        raise NotFoundError(f"work order {work_order_id} was not found")
    tasks = (
        await session.scalars(
            select(WorkOrderTask)
            .where(WorkOrderTask.work_order_id == work_order_id)
            .order_by(WorkOrderTask.sequence)
        )
    ).all()
    external_link = await session.get(ExternalWorkOrderLink, work_order_id)
    return {
        "work_order_id": work_order.id,
        "mission_id": work_order.mission_id,
        "approval_id": work_order.approval_id,
        "turbine_id": work_order.turbine_id,
        "title": work_order.title,
        "selected_alternative_id": work_order.selected_alternative_id,
        "selected_action": work_order.selected_action,
        "status": work_order.status,
        "priority": work_order.priority,
        "assigned_team": work_order.assigned_team,
        "created_by": work_order.created_by,
        "safety_plan": work_order.safety_plan,
        "closure_policy": work_order.closure_policy,
        "planned_start": _utc_iso(work_order.planned_start),
        "deadline": _utc_iso(work_order.deadline),
        "estimated_duration_hours": work_order.estimated_duration_hours,
        "created_at": _utc_iso(work_order.created_at),
        "updated_at": _utc_iso(work_order.updated_at),
        "eam": (
            {
                "provider": external_link.provider,
                "external_id": external_link.external_id,
                "sync_status": external_link.sync_status,
                "external_updated_at": external_link.external_updated_at,
                "updated_at": external_link.updated_at,
            }
            if external_link is not None
            else {"sync_status": "pending"}
            if settings.eam_enabled
            else None
        ),
        "tasks": [
            {
                "task_id": task.id,
                "sequence": task.sequence,
                "title": task.title,
                "schema_version": task.schema_version,
                "measurement_schema": task.measurement_schema,
                "status": task.status,
                "result": task.result,
                "completed_by": task.completed_by,
                "completed_at": task.completed_at,
            }
            for task in tasks
        ],
    }


@router.post("/work-orders/{work_order_id}/schedule", tags=["work-orders"])
async def update_work_order_schedule_command(
    work_order_id: str,
    payload: WorkOrderScheduleUpdateRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        row = await update_work_order_schedule(
            session,
            work_order_id=work_order_id,
            request=payload,
            subject=principal.subject,
            eam_enabled=settings.eam_enabled,
        )
        return {
            "work_order_id": row.id,
            "planned_start": row.planned_start,
            "deadline": row.deadline,
            "assigned_team": row.assigned_team,
            "updated_at": row.updated_at,
            "eam_sync_status": "pending" if settings.eam_enabled else None,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="work-order.schedule.update.v1",
        target=work_order_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post(
    "/integrations/eam/work-orders/{work_order_id}/status",
    tags=["integrations"],
)
async def update_eam_work_order_status(
    work_order_id: str,
    payload: EamWorkOrderStatusUpdate,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("eam_integrator")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        link, source_replayed = await record_eam_status(
            session,
            work_order_id,
            payload,
            subject=principal.subject,
        )
        return {
            "work_order_id": link.work_order_id,
            "external_id": link.external_id,
            "sync_status": link.sync_status,
            "external_updated_at": link.external_updated_at,
            "replayed": source_replayed,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="eam.work-order.status.v1",
        target=work_order_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post("/work-orders/{work_order_id}/tasks/{task_id}/complete", tags=["work-orders"])
async def complete_work_order_task(
    work_order_id: str,
    task_id: str,
    payload: TaskCompletionRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_roles("field_technician")),
) -> dict[str, Any]:
    trusted_payload = payload.model_copy(update={"completed_by": principal.subject})

    async def operation() -> dict[str, Any]:
        return await complete_task(
            session, work_order_id, task_id, trusted_payload, artifact_verifier
        )

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="work-order.task.complete.v1",
        target=f"{work_order_id}:{task_id}",
        idempotency_key=idempotency_key,
        payload=trusted_payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    await _drain_or_dispatch_graph_projection_events(request, settings)
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post(
    "/work-orders/{work_order_id}/tasks/{task_id}/artifacts/presign",
    tags=["work-orders"],
)
async def presign_field_artifact(
    work_order_id: str,
    task_id: str,
    payload: ArtifactUploadRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_roles("field_technician")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        work_order = await session.get(WorkOrder, work_order_id)
        if work_order is None:
            raise NotFoundError(f"work order {work_order_id} was not found")
        task = await session.get(WorkOrderTask, task_id)
        if task is None or task.work_order_id != work_order_id:
            raise NotFoundError(f"task {task_id} was not found in {work_order_id}")
        if task.status == "completed" or work_order.status == "completed":
            raise InvalidTransitionError(
                "completed field tasks cannot accept replacement artifacts"
            )
        try:
            upload = await artifact_verifier.create_upload(
                bucket=settings.minio_field_evidence_bucket,
                work_order_id=work_order_id,
                task_id=task_id,
                file_name=payload.file_name,
                content_type=payload.content_type,
                artifact_sha256=payload.artifact_sha256,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        return {
            "work_order_id": work_order_id,
            "task_id": task_id,
            "schema_version": task.schema_version,
            **upload,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="work-order.task-artifact.presign.v1",
        target=f"{work_order_id}:{task_id}",
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result
