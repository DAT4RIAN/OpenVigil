import hashlib
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.api.deps import (
    APPROVAL_ROLES,
    Principal,
    _drain_or_dispatch_graph_projection_events,
    _utc_iso,
    get_runtime_settings,
    get_session,
    require_read_access,
    require_roles,
)
from windops_backend.config import Settings
from windops_backend.errors import (
    NotFoundError,
)
from windops_backend.models import (
    AgentExecution,
    Alarm,
    Approval,
    Decision,
    Evidence,
    Mission,
    MissionComment,
    WorkOrder,
)
from windops_backend.outbox import (
    mark_dispatched,
    pending_events_for_missions,
    process_outbox_event,
)
from windops_backend.schemas import (
    ApprovalRequest,
    MissionBatchCreateRequest,
    MissionCommentCreateRequest,
    MissionCreateRequest,
)
from windops_backend.services.idempotency import (
    execute_idempotent_command,
    replace_idempotent_response,
)
from windops_backend.services.missions import create_mission
from windops_backend.services.platform_governance import (
    create_mission_comment,
)
from windops_backend.services.workflow import advance_mission_to_review, record_approval

router = APIRouter()


@router.get("/missions", tags=["missions"])
async def missions(
    turbine_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = select(Mission)
    if turbine_id:
        statement = statement.where(Mission.turbine_id == turbine_id)
    if status_filter:
        statement = statement.where(Mission.status == status_filter)
    if cursor:
        statement = statement.where(Mission.id > cursor)
    rows = list((await session.scalars(statement.order_by(Mission.id).limit(limit + 1))).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    alarm_rows = (
        (
            await session.scalars(select(Alarm).where(Alarm.id.in_([row.alarm_id for row in page])))
        ).all()
        if page
        else []
    )
    decision_rows = (
        (
            await session.scalars(
                select(Decision).where(Decision.mission_id.in_([row.id for row in page]))
            )
        ).all()
        if page
        else []
    )
    work_order_rows = (
        (
            await session.scalars(
                select(WorkOrder).where(WorkOrder.mission_id.in_([row.id for row in page]))
            )
        ).all()
        if page
        else []
    )
    alarm_by_id = {row.id: row for row in alarm_rows}
    decision_by_mission = {row.mission_id: row for row in decision_rows}
    work_order_by_mission = {row.mission_id: row for row in work_order_rows}
    return {
        "count": len(page),
        "next_cursor": page[-1].id if has_more and page else None,
        "missions": [
            {
                "mission_id": row.id,
                "alarm_id": row.alarm_id,
                "turbine_id": row.turbine_id,
                "title": row.title,
                "status": row.status,
                "revision": row.revision,
                "severity": alarm_by_id[row.alarm_id].severity,
                "analysis_profile": row.public_state.get("analysis_profile", {}),
                "diagnosis": row.public_state.get("diagnosis"),
                "evidence_ids": [
                    str(item.get("evidence_id"))
                    for item in row.public_state.get("evidence", [])
                    if item.get("evidence_id")
                ],
                "decision_id": (
                    decision_by_mission[row.id].id if row.id in decision_by_mission else None
                ),
                "work_order_id": (
                    work_order_by_mission[row.id].id if row.id in work_order_by_mission else None
                ),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in page
        ],
    }


@router.post("/missions", status_code=status.HTTP_202_ACCEPTED, tags=["missions"])
async def create_mission_command(
    payload: MissionCreateRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    result, replayed = await create_mission(
        session,
        payload,
        idempotency_key=idempotency_key,
        subject=principal.subject,
    )
    event_ids = await pending_events_for_missions(session, [str(result["mission_id"])])
    await session.commit()
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    if event_ids:
        if settings.outbox_inline_drain:
            for event_id in event_ids:
                await process_outbox_event(factory, settings, event_id, advance_mission_to_review)
        else:
            from windops_backend.workers import dispatch_event_ids

            dispatch_event_ids(event_ids)
            await mark_dispatched(factory, event_ids)
    await _drain_or_dispatch_graph_projection_events(request, settings)
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return {**result, "replayed": False}


@router.post("/missions/batch", status_code=status.HTTP_202_ACCEPTED, tags=["missions"])
async def create_mission_batch_command(
    payload: MissionBatchCreateRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    connection = await session.connection()
    if connection.dialect.name == "sqlite":
        # Python's sqlite3 legacy transaction mode does not BEGIN for SELECT.
        # create_mission uses a SAVEPOINT, which would otherwise be released as
        # a standalone committed transaction before a later batch item fails.
        await connection.exec_driver_sql("BEGIN IMMEDIATE")

    async def operation() -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        replayed_count = 0
        for index, mission_payload in enumerate(payload.missions):
            item_key = hashlib.sha256(
                f"mission-batch-v1:{idempotency_key.strip()}:{index}".encode()
            ).hexdigest()
            item_result, item_replayed = await create_mission(
                session,
                mission_payload,
                idempotency_key=item_key,
                subject=principal.subject,
            )
            results.append({**item_result, "replayed": item_replayed})
            replayed_count += int(item_replayed)
        return {
            "count": len(results),
            "replayed_count": replayed_count,
            "missions": results,
        }

    try:
        result, replayed = await execute_idempotent_command(
            session,
            subject=principal.subject,
            command_type="mission.batch.create.v1",
            target="batch",
            idempotency_key=idempotency_key,
            payload=payload,
            status_code=status.HTTP_202_ACCEPTED,
            operation=operation,
        )
    except BaseException:
        # Some SQLite drivers can release a first SAVEPOINT before the request
        # dependency observes a later item failure. The command boundary owns
        # atomicity, so explicitly roll back every accumulated item here; the
        # same rollback is harmless and required for PostgreSQL as well.
        await session.rollback()
        raise
    mission_ids = [str(item["mission_id"]) for item in result["missions"]]
    event_ids = await pending_events_for_missions(session, mission_ids)
    await session.commit()
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    if event_ids:
        if settings.outbox_inline_drain:
            for event_id in event_ids:
                await process_outbox_event(factory, settings, event_id, advance_mission_to_review)
        else:
            from windops_backend.workers import dispatch_event_ids

            dispatch_event_ids(event_ids)
            await mark_dispatched(factory, event_ids)
    await _drain_or_dispatch_graph_projection_events(request, settings)
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.get("/missions/{mission_id}/comments", tags=["missions"])
async def mission_comments(
    mission_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    if await session.get(Mission, mission_id) is None:
        raise NotFoundError(f"mission {mission_id} was not found")
    rows = list(
        (
            await session.scalars(
                select(MissionComment)
                .where(MissionComment.mission_id == mission_id)
                .order_by(MissionComment.created_at, MissionComment.id)
            )
        ).all()
    )
    return {
        "mission_id": mission_id,
        "count": len(rows),
        "comments": [
            {
                "comment_id": row.id,
                "body": row.body,
                "author_subject": row.author_subject,
                "author_email": row.author_email,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@router.post(
    "/missions/{mission_id}/comments",
    status_code=status.HTTP_201_CREATED,
    tags=["missions"],
)
async def create_mission_comment_command(
    mission_id: str,
    payload: MissionCommentCreateRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(
        require_roles("operations_manager", "operations_approver", "field_technician")
    ),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        row = await create_mission_comment(
            session,
            mission_id=mission_id,
            body=payload.body,
            subject=principal.subject,
            email=principal.email,
        )
        return {
            "comment_id": row.id,
            "mission_id": row.mission_id,
            "body": row.body,
            "author_subject": row.author_subject,
            "author_email": row.author_email,
            "created_at": row.created_at,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="mission.comment.create.v1",
        target=mission_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.get("/decisions", tags=["decisions"])
async def decision_collection(
    turbine_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = select(Decision)
    if turbine_id:
        statement = statement.join(Mission, Mission.id == Decision.mission_id).where(
            Mission.turbine_id == turbine_id
        )
    if status_filter:
        statement = statement.where(Decision.status == status_filter)
    if cursor:
        statement = statement.where(Decision.id > cursor)
    rows = list((await session.scalars(statement.order_by(Decision.id).limit(limit + 1))).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    missions_by_id = {
        row.id: row
        for row in (
            (
                await session.scalars(
                    select(Mission).where(Mission.id.in_([item.mission_id for item in page]))
                )
            ).all()
            if page
            else []
        )
    }
    approval_rows = (
        (
            await session.scalars(
                select(Approval)
                .where(Approval.mission_id.in_([item.mission_id for item in page]))
                .order_by(Approval.created_at)
            )
        ).all()
        if page
        else []
    )
    latest_approval_by_mission = {row.mission_id: row for row in approval_rows}
    return {
        "count": len(page),
        "next_cursor": page[-1].id if has_more and page else None,
        "decisions": [
            {
                "decision_id": row.id,
                "mission_id": row.mission_id,
                "mission_revision": missions_by_id[row.mission_id].revision,
                "turbine_id": missions_by_id[row.mission_id].turbine_id,
                "incident": missions_by_id[row.mission_id].title,
                "diagnosis": missions_by_id[row.mission_id].public_state.get("diagnosis"),
                "evidence_ids": [
                    str(item.get("evidence_id"))
                    for item in missions_by_id[row.mission_id].public_state.get("evidence", [])
                    if item.get("evidence_id")
                ],
                "status": row.status,
                "alternatives": row.alternatives,
                "recommended_alternative_id": row.recommended_alternative_id,
                "selected_alternative_id": row.selected_alternative_id,
                "recommendation_reason": row.recommendation_reason,
                "risks": row.risks,
                "approval": (
                    {
                        "approval_id": latest_approval_by_mission[row.mission_id].id,
                        "action": latest_approval_by_mission[row.mission_id].action,
                        "selected_alternative_id": latest_approval_by_mission[
                            row.mission_id
                        ].selected_alternative_id,
                        "approver": latest_approval_by_mission[row.mission_id].approver,
                        "reason": latest_approval_by_mission[row.mission_id].reason,
                        "comment": latest_approval_by_mission[row.mission_id].comment,
                        "created_at": latest_approval_by_mission[row.mission_id].created_at,
                    }
                    if row.mission_id in latest_approval_by_mission
                    else None
                ),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in page
        ],
    }


@router.get("/missions/{mission_id}", tags=["missions"])
async def mission_detail(
    mission_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    mission = await session.get(Mission, mission_id)
    if mission is None:
        raise NotFoundError(f"mission {mission_id} was not found")
    approvals = (
        await session.scalars(
            select(Approval).where(Approval.mission_id == mission_id).order_by(Approval.created_at)
        )
    ).all()
    work_order_id = await session.scalar(
        select(WorkOrder.id).where(WorkOrder.mission_id == mission_id)
    )
    executions = (
        await session.scalars(
            select(AgentExecution)
            .where(AgentExecution.mission_id == mission_id)
            .order_by(AgentExecution.started_at)
        )
    ).all()
    evidence_entities = (
        await session.scalars(
            select(Evidence).where(Evidence.mission_id == mission_id).order_by(Evidence.created_at)
        )
    ).all()
    decision = await session.scalar(select(Decision).where(Decision.mission_id == mission_id))
    return {
        "mission_id": mission.id,
        "alarm_id": mission.alarm_id,
        "turbine_id": mission.turbine_id,
        "title": mission.title,
        "status": mission.status,
        "revision": mission.revision,
        "public_state": mission.public_state,
        "work_order_id": work_order_id,
        "created_at": _utc_iso(mission.created_at),
        "updated_at": _utc_iso(mission.updated_at),
        "evidence": [
            {
                "evidence_id": row.id,
                "source_key": row.source_key,
                "evidence_type": row.evidence_type,
                "summary": row.summary,
                "source_refs": row.source_refs,
                "metrics": row.metrics,
                "citation_uri": row.citation_uri,
                "retrieval_method": row.retrieval_method,
                "created_at": row.created_at,
            }
            for row in evidence_entities
        ],
        "decision": (
            {
                "decision_id": decision.id,
                "status": decision.status,
                "alternatives": decision.alternatives,
                "recommended_alternative_id": decision.recommended_alternative_id,
                "selected_alternative_id": decision.selected_alternative_id,
                "recommendation_reason": decision.recommendation_reason,
                "risks": decision.risks,
                "approval_id": decision.approval_id,
                "created_at": decision.created_at,
                "updated_at": decision.updated_at,
            }
            if decision is not None
            else None
        ),
        "approvals": [
            {
                "approval_id": row.id,
                "mission_revision": row.mission_revision,
                "action": row.action,
                "selected_alternative_id": row.selected_alternative_id,
                "approver": row.approver,
                "reason": row.reason,
                "comment": row.comment,
                "created_at": row.created_at,
            }
            for row in approvals
        ],
        "executions": [
            {
                "execution_id": row.id,
                "catalog_version_id": row.catalog_version_id,
                "agent_definition_id": row.agent_definition_id,
                "node": row.node,
                "agent_role": row.agent_role,
                "status": row.status,
                "input_refs": row.input_refs,
                "public_output": row.public_output,
                "tool_calls": row.tool_calls,
                "latency_ms": row.latency_ms,
                "provider": row.provider,
                "model": row.model,
                "token_usage": row.token_usage,
                "evaluation_result": row.evaluation_result,
                "degradation_policy": row.degradation_policy,
                "started_at": row.started_at,
                "completed_at": row.completed_at,
            }
            for row in executions
        ],
    }


@router.post("/missions/{mission_id}/approvals", tags=["missions"])
async def approve_mission(
    mission_id: str,
    payload: ApprovalRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(
        require_roles(
            "operations_manager",
            "operations_approver",
            "maintenance_reviewer",
        )
    ),
) -> dict[str, Any]:
    required_role = APPROVAL_ROLES[payload.action.value]
    if "test_system" not in principal.roles and required_role not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Insufficient role for approval action"},
        )
    trusted_payload = payload.model_copy(update={"approver": principal.subject})
    event_ids: list[str] = []

    async def operation() -> dict[str, Any]:
        mission, approval, work_order = await record_approval(
            session, settings, mission_id, trusted_payload
        )
        event_ids.extend(await pending_events_for_missions(session, [mission_id]))
        return {
            "mission_id": mission.id,
            "mission_status": mission.status,
            "revision": mission.revision,
            "approval_id": approval.id,
            "action": approval.action,
            "selected_alternative_id": approval.selected_alternative_id,
            "work_order_id": work_order.id if work_order else None,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="mission.approval.record.v1",
        target=mission_id,
        idempotency_key=idempotency_key,
        payload=trusted_payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    if event_ids:
        app_factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
        if settings.outbox_inline_drain:
            for event_id in event_ids:
                await process_outbox_event(
                    app_factory, settings, event_id, advance_mission_to_review
                )
            async with app_factory() as refresh_session:
                refreshed = await refresh_session.get(Mission, mission_id)
                if refreshed is not None:
                    result["mission_status"] = refreshed.status
                    result["revision"] = refreshed.revision
                await replace_idempotent_response(
                    refresh_session,
                    subject=principal.subject,
                    command_type="mission.approval.record.v1",
                    target=mission_id,
                    idempotency_key=idempotency_key,
                    response_body=result,
                )
                await refresh_session.commit()
        else:
            from windops_backend.workers import dispatch_event_ids

            dispatch_event_ids(event_ids)
            await mark_dispatched(app_factory, event_ids)
    await _drain_or_dispatch_graph_projection_events(request, settings)
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result
