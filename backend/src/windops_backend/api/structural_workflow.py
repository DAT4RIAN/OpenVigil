from typing import Any, cast

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.api.deps import (
    Principal,
    _drain_or_dispatch_graph_projection_events,
    get_artifact_verifier,
    get_runtime_settings,
    get_session,
    require_read_access,
    require_roles,
)
from windops_backend.api.structural import _command
from windops_backend.config import Settings
from windops_backend.errors import InvalidTransitionError, NotFoundError
from windops_backend.model_structural_workflow import (
    StructuralCaseReview,
    StructuralHealthReview,
    StructuralRetestHandoff,
)
from windops_backend.models import KnowledgeCase, WorkOrder, WorkOrderTask
from windops_backend.outbox import (
    mark_dispatched,
    pending_events_for_missions,
    process_outbox_event,
)
from windops_backend.schema_operations import ArtifactUploadRequest
from windops_backend.schema_structural_workflow import (
    StructuralCaseReviewRequest,
    StructuralHealthReviewRequest,
    StructuralMissionCreate,
    StructuralRetestSubmission,
)
from windops_backend.services.structural import asset_scope, serialize
from windops_backend.services.structural_closure import health_review, review_case
from windops_backend.services.structural_missions import (
    create_structural_mission,
    prepare_context,
    structural_mission_detail,
)
from windops_backend.services.structural_retests import submit_followup_retest
from windops_backend.services.workflow import advance_mission_to_review
from windops_backend.storage import ArtifactVerifier

router = APIRouter(tags=["structural-workflow"])


@router.post("/structural-missions", status_code=202)
async def add_structural_mission(
    payload: StructuralMissionCreate,
    request: Request,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    # Recheck the actual source grants even when replaying a command receipt.
    await prepare_context(session, payload)
    result = await _command(
        session,
        response,
        principal,
        key,
        "mission.create",
        payload.turbine_id,
        payload,
        lambda: create_structural_mission(session, payload, principal.subject),
        status_code=202,
    )
    events = await pending_events_for_missions(session, [result["mission_id"]])
    await session.commit()
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    if events:
        if settings.outbox_inline_drain:
            for event in events:
                await process_outbox_event(factory, settings, event, advance_mission_to_review)
        else:
            from windops_backend.workers import dispatch_event_ids

            dispatch_event_ids(events)
            await mark_dispatched(factory, events)
    await _drain_or_dispatch_graph_projection_events(request, settings)
    return result


@router.get("/structural-missions/{mission_id}")
async def mission_context(
    mission_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    return await structural_mission_detail(session, mission_id)


@router.get("/structural-work-orders/{work_order_id}")
async def structural_work_order(
    work_order_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    row = await session.get(WorkOrder, work_order_id)
    if row is None or row.closure_policy.get("kind") != "structural_retest":
        raise NotFoundError("structural work order was not found")
    context = await structural_mission_detail(session, row.mission_id)
    tasks = (
        await session.scalars(
            select(WorkOrderTask)
            .where(WorkOrderTask.work_order_id == row.id)
            .order_by(WorkOrderTask.sequence)
        )
    ).all()
    reviews = (
        await session.scalars(
            select(StructuralHealthReview)
            .where(StructuralHealthReview.work_order_id == row.id)
            .order_by(StructuralHealthReview.created_at)
        )
    ).all()
    handoffs = (
        await session.scalars(
            select(StructuralRetestHandoff)
            .where(StructuralRetestHandoff.work_order_id == row.id)
            .order_by(StructuralRetestHandoff.verified_at, StructuralRetestHandoff.id)
        )
    ).all()
    return {
        "work_order": serialize(row),
        "tasks": [serialize(task) for task in tasks],
        "context": context,
        "health_reviews": [serialize(review) for review in reviews],
        "retest_handoffs": [serialize(handoff) for handoff in handoffs],
    }


@router.post("/structural-work-orders/{work_order_id}/health-review")
async def review_health(
    work_order_id: str,
    payload: StructuralHealthReviewRequest,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager", "maintenance_reviewer")),
    settings: Settings = Depends(get_runtime_settings),
    verifier: ArtifactVerifier = Depends(get_artifact_verifier),
) -> dict[str, Any]:
    row = await session.get(WorkOrder, work_order_id)
    if row is None:
        raise NotFoundError("structural work order was not found")
    await structural_mission_detail(session, row.mission_id)
    return await _command(
        session,
        response,
        principal,
        key,
        "health.review",
        work_order_id,
        payload,
        lambda: health_review(
            session, work_order_id, payload, principal.subject, verifier, settings
        ),
        status_code=200,
    )


@router.get("/structural-cases")
async def structural_cases(
    turbine_id: str,
    status: str = Query("pending", pattern="^(pending|approved|rejected)$"),
    cursor: str | None = Query(None, max_length=40),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    await asset_scope(session, turbine_id)
    query = (
        select(StructuralCaseReview, KnowledgeCase)
        .join(KnowledgeCase, KnowledgeCase.id == StructuralCaseReview.case_id)
        .where(StructuralCaseReview.turbine_id == turbine_id, StructuralCaseReview.status == status)
    )
    if cursor:
        query = query.where(StructuralCaseReview.case_id > cursor)
    rows = (
        await session.execute(query.order_by(StructuralCaseReview.case_id).limit(limit + 1))
    ).all()
    return {
        "items": [
            {"review": serialize(review), "case": serialize(case)} for review, case in rows[:limit]
        ],
        "next_cursor": rows[limit - 1][0].case_id if len(rows) > limit else None,
    }


@router.post("/structural-cases/{case_id}/review")
async def review_structural_case(
    case_id: str,
    payload: StructuralCaseReviewRequest,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager", "maintenance_reviewer")),
    verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    if await session.get(StructuralCaseReview, case_id) is None:
        raise NotFoundError("structural case was not found")
    return await _command(
        session,
        response,
        principal,
        key,
        "case.review",
        case_id,
        payload,
        lambda: review_case(session, case_id, payload, principal.subject, verifier, settings),
        status_code=200,
    )


@router.post("/structural-work-orders/{work_order_id}/retests", status_code=201)
async def add_followup_retest(
    work_order_id: str,
    payload: StructuralRetestSubmission,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("field_technician", "operations_manager")),
    verifier: ArtifactVerifier = Depends(get_artifact_verifier),
) -> dict[str, Any]:
    order = await session.get(WorkOrder, work_order_id)
    if order is None:
        raise NotFoundError("structural work order was not found")
    await structural_mission_detail(session, order.mission_id)
    return await _command(
        session,
        response,
        principal,
        key,
        "retest.submit",
        work_order_id,
        payload,
        lambda: submit_followup_retest(
            session, work_order_id, payload, principal.subject, verifier
        ),
    )


@router.post("/structural-work-orders/{work_order_id}/retests/uploads/presign")
async def followup_upload(
    work_order_id: str,
    payload: ArtifactUploadRequest,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("field_technician", "operations_manager")),
    verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    order = await session.get(WorkOrder, work_order_id)
    if order is None:
        raise NotFoundError("structural work order was not found")
    await structural_mission_detail(session, order.mission_id)
    review = await session.scalar(
        select(StructuralHealthReview)
        .where(StructuralHealthReview.work_order_id == order.id)
        .order_by(StructuralHealthReview.created_at.desc(), StructuralHealthReview.id.desc())
        .limit(1)
    )
    if (
        order.status != "awaiting_health_review"
        or not review
        or review.action != "requires_followup"
    ):
        raise InvalidTransitionError("follow-up upload requires an unresolved health review")
    task = await session.scalar(
        select(WorkOrderTask)
        .where(WorkOrderTask.work_order_id == order.id)
        .order_by(WorkOrderTask.sequence.desc())
        .limit(1)
    )
    if task is None:
        raise InvalidTransitionError("structural field handoff was not found")

    async def upload() -> dict[str, Any]:
        try:
            result = await verifier.create_upload(
                bucket=settings.minio_field_evidence_bucket,
                work_order_id=order.id,
                task_id=task.id,
                file_name=payload.file_name,
                content_type=payload.content_type,
                artifact_sha256=payload.artifact_sha256,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        return {**result, "task_id": task.id}

    return await _command(
        session,
        response,
        principal,
        key,
        "retest.upload",
        order.id,
        payload,
        upload,
        status_code=200,
    )
