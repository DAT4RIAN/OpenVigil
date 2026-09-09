from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from math import ceil
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.config import Settings
from windops_backend.errors import NotFoundError
from windops_backend.models import (
    AgentDefinition,
    AgentExecution,
    AgentSkillLink,
    AgentToolLink,
    Alarm,
    Approval,
    AssetHealthEvent,
    CatalogVersion,
    Decision,
    Evidence,
    KnowledgeCase,
    KnowledgeDocument,
    Mission,
    ReadAccessAudit,
    ScadaSample,
    SkillDefinition,
    ToolDefinition,
    Turbine,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.outbox import (
    mark_dispatched,
    pending_events_for_missions,
    process_outbox_event,
)
from windops_backend.schemas import (
    ApprovalRequest,
    ScadaIngestRequest,
    ScadaIngestResponse,
    TaskCompletionRequest,
)
from windops_backend.services.ingest import ingest_sample
from windops_backend.services.workflow import advance_mission_to_review, record_approval
from windops_backend.services.workorders import complete_task
from windops_backend.storage import ArtifactVerifier

router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    subject: str
    role: str


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, ceil(len(ordered) * 0.95) - 1)]


def _token_total(execution: AgentExecution) -> int:
    value = execution.token_usage.get("total_tokens", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHENTICATED", "message": "Authentication required"},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    settings = get_runtime_settings(request)
    if settings.test_auth_bypass_enabled:
        subject = request.headers.get("x-windops-test-principal", "").strip()
        role = request.headers.get("x-windops-test-role", "").strip()
        if not subject or not role:
            raise _authentication_error()
        return Principal(subject=subject, role=role)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error()
    supplied = credentials.credentials
    role_keys = (
        ("scada-ingestor", "scada_ingestor", settings.scada_ingest_api_key),
        ("operations-approver", "operations_approver", settings.operations_approver_api_key),
        ("maintenance-reviewer", "maintenance_reviewer", settings.maintenance_reviewer_api_key),
        ("operations-manager", "operations_manager", settings.operations_manager_api_key),
        ("field-technician", "field_technician", settings.field_technician_api_key),
    )
    for subject, role, configured in role_keys:
        if compare_digest(supplied, configured.get_secret_value()):
            return Principal(subject=subject, role=role)
    raise _authentication_error()


def require_roles(*allowed_roles: str) -> Any:
    async def authorize(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role != "test_system" and principal.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Insufficient role"},
            )
        return principal

    return authorize


APPROVAL_ROLES = {
    "approve": "operations_approver",
    "reject": "operations_approver",
    "request_revision": "maintenance_reviewer",
    "escalate": "operations_manager",
}


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise


def get_runtime_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_artifact_verifier(request: Request) -> ArtifactVerifier:
    return cast(ArtifactVerifier, request.app.state.artifact_verifier)


async def require_read_access(
    request: Request,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """Authenticate and durably attribute every business read to a server-owned subject."""

    session.add(
        ReadAccessAudit(
            id=str(uuid4()),
            subject=principal.subject,
            role=principal.role,
            method=request.method,
            endpoint=request.url.path,
            query={key: request.query_params.getlist(key) for key in request.query_params.keys()},
        )
    )
    await session.commit()
    return principal


@router.get("/healthz", tags=["system"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", tags=["system"])
async def readyz(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/tools", tags=["agents"])
async def tool_catalog(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    tools = (await session.scalars(select(ToolDefinition).order_by(ToolDefinition.tool_key))).all()
    return {
        "count": len(tools),
        "tools": [
            {
                "name": row.tool_key,
                "mode": row.mode,
                "version": row.version,
                "catalog_version_id": row.catalog_version_id,
            }
            for row in tools
        ],
    }


@router.get("/catalog", tags=["agents"])
async def agent_catalog(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    version = await session.scalar(
        select(CatalogVersion)
        .where(CatalogVersion.active.is_(True))
        .order_by(CatalogVersion.created_at.desc())
        .limit(1)
    )
    if version is None:
        return {"catalog_version": None, "agents": [], "skills": [], "tools": []}
    agents = (
        await session.scalars(
            select(AgentDefinition)
            .where(AgentDefinition.catalog_version_id == version.id)
            .order_by(AgentDefinition.agent_key)
        )
    ).all()
    skills = (
        await session.scalars(
            select(SkillDefinition)
            .where(SkillDefinition.catalog_version_id == version.id)
            .order_by(SkillDefinition.skill_key)
        )
    ).all()
    tools = (
        await session.scalars(
            select(ToolDefinition)
            .where(ToolDefinition.catalog_version_id == version.id)
            .order_by(ToolDefinition.tool_key)
        )
    ).all()
    skill_links = (
        await session.scalars(
            select(AgentSkillLink).where(AgentSkillLink.catalog_version_id == version.id)
        )
    ).all()
    tool_links = (
        await session.scalars(
            select(AgentToolLink).where(AgentToolLink.catalog_version_id == version.id)
        )
    ).all()
    skill_by_id = {row.id: row.skill_key for row in skills}
    tool_by_id = {row.id: row.tool_key for row in tools}
    agent_skills: dict[str, list[str]] = {}
    agent_tools: dict[str, list[str]] = {}
    for skill_link in skill_links:
        agent_skills.setdefault(skill_link.agent_definition_id, []).append(
            skill_by_id[skill_link.skill_definition_id]
        )
    for tool_link in tool_links:
        agent_tools.setdefault(tool_link.agent_definition_id, []).append(
            tool_by_id[tool_link.tool_definition_id]
        )
    return {
        "catalog_version": {
            "id": version.id,
            "version": version.version,
            "description": version.description,
        },
        "agents": [
            {
                "id": row.id,
                "key": row.agent_key,
                "display_name": row.display_name,
                "role": row.role,
                "version": row.version,
                "skills": sorted(agent_skills.get(row.id, [])),
                "tools": sorted(agent_tools.get(row.id, [])),
            }
            for row in agents
        ],
        "skills": [{"id": row.id, "key": row.skill_key, "version": row.version} for row in skills],
        "tools": [
            {"id": row.id, "key": row.tool_key, "mode": row.mode, "version": row.version}
            for row in tools
        ],
    }


@router.post(
    "/scada/ingest",
    response_model=ScadaIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["scada"],
)
async def ingest_scada(
    payload: ScadaIngestRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(require_roles("scada_ingestor")),
) -> ScadaIngestResponse:
    del principal
    results = []
    for sample in payload.samples:
        result = await ingest_sample(session, sample)
        results.append(result)
    mission_ids = list({item.mission_id for item in results if item.mission_id is not None})
    event_ids = await pending_events_for_missions(session, mission_ids)
    await session.commit()
    app_factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    if settings.outbox_inline_drain:
        for event_id in event_ids:
            await process_outbox_event(app_factory, settings, event_id, advance_mission_to_review)
    else:
        from windops_backend.workers import dispatch_event_ids

        dispatch_event_ids(event_ids)
        await mark_dispatched(app_factory, event_ids)
    return ScadaIngestResponse(
        accepted=sum(item.disposition == "accepted" for item in results),
        duplicates=sum(item.disposition == "duplicate" for item in results),
        results=results,
    )


@router.get("/turbines/{turbine_id}/scada", tags=["scada"])
async def turbine_scada(
    turbine_id: str,
    variable: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    if await session.get(Turbine, turbine_id) is None:
        raise NotFoundError(f"turbine {turbine_id} was not found")
    samples = await SQLToolAdapter(session).query_scada(turbine_id, variable, limit)
    return {"turbine_id": turbine_id, "count": len(samples), "samples": samples}


@router.get("/turbines/{turbine_id}/health", tags=["assets"])
async def turbine_health(
    turbine_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    turbine = await session.get(Turbine, turbine_id)
    if turbine is None:
        raise NotFoundError(f"turbine {turbine_id} was not found")
    events = (
        await session.scalars(
            select(AssetHealthEvent)
            .where(AssetHealthEvent.turbine_id == turbine_id)
            .order_by(desc(AssetHealthEvent.recorded_at))
        )
    ).all()
    return {
        "turbine_id": turbine.id,
        "status": turbine.status,
        "health_score": turbine.health_score,
        "history": [
            {
                "health_event_id": event.id,
                "mission_id": event.mission_id,
                "score": event.score,
                "status": event.status,
                "reason": event.reason,
                "recorded_at": event.recorded_at,
            }
            for event in events
        ],
    }


@router.get("/alarms/{alarm_id}", tags=["alarms"])
async def alarm_detail(
    alarm_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    alarm = await session.get(Alarm, alarm_id)
    if alarm is None:
        raise NotFoundError(f"alarm {alarm_id} was not found")
    mission_id = await session.scalar(select(Mission.id).where(Mission.alarm_id == alarm.id))
    return {
        "alarm_id": alarm.id,
        "turbine_id": alarm.turbine_id,
        "code": alarm.code,
        "subsystem": alarm.subsystem,
        "title": alarm.title,
        "severity": alarm.severity,
        "status": alarm.status,
        "ai_status": alarm.ai_status,
        "triggered_at": alarm.triggered_at,
        "evidence": alarm.evidence,
        "mission_id": mission_id,
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
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    required_role = APPROVAL_ROLES[payload.action.value]
    if principal.role != "test_system" and principal.role != required_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Insufficient role for approval action"},
        )
    trusted_payload = payload.model_copy(update={"approver": principal.subject})
    mission, approval, work_order = await record_approval(
        session, settings, mission_id, trusted_payload
    )
    event_ids = await pending_events_for_missions(session, [mission_id])
    await session.commit()
    response_status = mission.status
    response_revision = mission.revision
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
                    response_status = refreshed.status
                    response_revision = refreshed.revision
        else:
            from windops_backend.workers import dispatch_event_ids

            dispatch_event_ids(event_ids)
            await mark_dispatched(app_factory, event_ids)
    return {
        "mission_id": mission.id,
        "mission_status": response_status,
        "revision": response_revision,
        "approval_id": approval.id,
        "action": approval.action,
        "work_order_id": work_order.id if work_order else None,
    }


@router.get("/agent-executions", tags=["agents"])
async def agent_executions(
    mission_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    executions = (
        await session.scalars(
            select(AgentExecution)
            .where(AgentExecution.mission_id == mission_id)
            .order_by(AgentExecution.started_at)
        )
    ).all()
    return {
        "mission_id": mission_id,
        "count": len(executions),
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
                "error_code": row.error_code,
            }
            for row in executions
        ],
    }


@router.get("/observability/agent-executions/24h", tags=["observability"])
async def agent_execution_observability_24h(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    generated_at = datetime.now(UTC)
    window_started_at = generated_at - timedelta(hours=24)
    executions = (
        await session.scalars(
            select(AgentExecution)
            .where(AgentExecution.started_at >= window_started_at)
            .order_by(AgentExecution.started_at)
        )
    ).all()
    grouped: dict[str, list[AgentExecution]] = {}
    for execution in executions:
        grouped.setdefault(execution.node, []).append(execution)

    latencies = [row.latency_ms for row in executions]
    return {
        "window": "24h",
        "window_started_at": window_started_at,
        "generated_at": generated_at,
        "summary": {
            "total": len(executions),
            "succeeded": sum(row.status == "succeeded" for row in executions),
            "failed": sum(row.status == "failed" for row in executions),
            "running": sum(row.status == "running" for row in executions),
            "average_latency_ms": (round(sum(latencies) / len(latencies), 2) if latencies else 0),
            "p95_latency_ms": _p95(latencies),
            "tool_calls": sum(len(row.tool_calls) for row in executions),
            "total_tokens": sum(_token_total(row) for row in executions),
        },
        "by_node": [
            {
                "node": node,
                "total": len(rows),
                "succeeded": sum(row.status == "succeeded" for row in rows),
                "failed": sum(row.status == "failed" for row in rows),
                "average_latency_ms": round(sum(row.latency_ms for row in rows) / len(rows), 2),
                "p95_latency_ms": _p95([row.latency_ms for row in rows]),
            }
            for node, rows in sorted(grouped.items())
        ],
        "failures": [
            {
                "execution_id": row.id,
                "mission_id": row.mission_id,
                "node": row.node,
                "agent_role": row.agent_role,
                "catalog_version_id": row.catalog_version_id,
                "agent_definition_id": row.agent_definition_id,
                "error_code": row.error_code,
                "input_refs": row.input_refs,
                "public_output": row.public_output,
                "tool_calls": row.tool_calls,
            }
            for row in executions
            if row.status == "failed"
        ][-50:],
    }


@router.get("/work-orders/{work_order_id}", tags=["work-orders"])
async def work_order_detail(
    work_order_id: str,
    session: AsyncSession = Depends(get_session),
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
    return {
        "work_order_id": work_order.id,
        "mission_id": work_order.mission_id,
        "approval_id": work_order.approval_id,
        "turbine_id": work_order.turbine_id,
        "title": work_order.title,
        "status": work_order.status,
        "priority": work_order.priority,
        "assigned_team": work_order.assigned_team,
        "created_by": work_order.created_by,
        "safety_plan": work_order.safety_plan,
        "tasks": [
            {
                "task_id": task.id,
                "sequence": task.sequence,
                "title": task.title,
                "status": task.status,
                "result": task.result,
                "completed_by": task.completed_by,
                "completed_at": task.completed_at,
            }
            for task in tasks
        ],
    }


@router.post("/work-orders/{work_order_id}/tasks/{task_id}/complete", tags=["work-orders"])
async def complete_work_order_task(
    work_order_id: str,
    task_id: str,
    payload: TaskCompletionRequest,
    session: AsyncSession = Depends(get_session),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_roles("field_technician")),
) -> dict[str, Any]:
    trusted_payload = payload.model_copy(update={"completed_by": principal.subject})
    result = await complete_task(
        session, work_order_id, task_id, trusted_payload, artifact_verifier
    )
    await session.commit()
    return result


@router.get("/knowledge/documents/{document_id}", tags=["knowledge"])
async def knowledge_document_detail(
    document_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    document = await session.get(KnowledgeDocument, document_id)
    if document is None:
        raise NotFoundError(f"knowledge document {document_id} was not found")
    return {
        "document_id": document.id,
        "title": document.title,
        "document_type": document.document_type,
        "body": document.body,
        "citation_uri": document.citation_uri,
        "source_storage": "database",
        "vectorized": document.vectorized,
        "updated_at": document.updated_at,
    }


@router.get("/knowledge/cases", tags=["knowledge"])
async def knowledge_cases(
    mission_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = select(KnowledgeCase).order_by(desc(KnowledgeCase.created_at))
    if mission_id:
        statement = statement.where(KnowledgeCase.mission_id == mission_id)
    cases = (await session.scalars(statement)).all()
    return {
        "count": len(cases),
        "cases": [
            {
                "case_id": case.id,
                "mission_id": case.mission_id,
                "work_order_id": case.work_order_id,
                "turbine_id": case.turbine_id,
                "title": case.title,
                "diagnosis": case.diagnosis,
                "resolution": case.resolution,
                "created_at": case.created_at,
            }
            for case in cases
        ],
    }


@router.get("/scada/sample-count", tags=["scada"])
async def scada_sample_count(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, int]:
    # Small operational endpoint used to verify transport-level idempotency.
    count = len((await session.scalars(select(ScadaSample.id))).all())
    return {"count": count}
