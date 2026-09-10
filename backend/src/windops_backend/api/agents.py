from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.api.deps import (
    Principal,
    _p95,
    _token_total,
    get_runtime_settings,
    get_session,
    require_global_roles,
    require_read_access,
)
from windops_backend.config import Settings
from windops_backend.models import (
    AgentDefinition,
    AgentExecution,
    AgentSkillLink,
    AgentToolInvocation,
    AgentToolLink,
    CatalogVersion,
    SkillDefinition,
    ToolDefinition,
)
from windops_backend.schemas import (
    AgentControlRequest,
    AgentReleaseRequest,
    AgentToolExecuteRequest,
)
from windops_backend.services.agent_governance import (
    agent_catalog_rows,
    control_agent,
    create_agent_release,
    execute_agent_tool,
    normalize_agent_key,
    serialize_invocation,
)
from windops_backend.services.idempotency import execute_idempotent_command

router = APIRouter()


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


@router.get("/agents", tags=["agents"])
async def governed_agents(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    agents = await agent_catalog_rows(session)
    window_start = datetime.now(UTC) - timedelta(hours=24)
    executions = list(
        (
            await session.scalars(
                select(AgentExecution).where(AgentExecution.started_at >= window_start)
            )
        ).all()
    )
    by_agent: dict[str, list[AgentExecution]] = {}
    for execution in executions:
        by_agent.setdefault(execution.agent_role, []).append(execution)
    for agent in agents:
        history = by_agent.get(str(agent["agent_key"]), [])
        succeeded = sum(item.status == "succeeded" for item in history)
        agent["metrics"] = {
            "requests": len(history),
            "tool_calls": sum(len(item.tool_calls) for item in history),
            "token_usage": sum(int(item.token_usage.get("total", 0) or 0) for item in history),
            "succeeded": succeeded,
            "failed": len(history) - succeeded,
            "success_rate": round(succeeded / len(history), 4) if history else None,
            "average_latency_ms": (
                round(sum(item.latency_ms for item in history) / len(history)) if history else None
            ),
            "last_active_at": (
                max(
                    (item.completed_at or item.started_at for item in history),
                    default=None,
                )
            ),
            "window_started_at": window_start,
        }
    return {"count": len(agents), "agents": agents}


@router.post("/agents/{agent_key}/commands", tags=["agents"])
async def govern_agent_runtime(
    agent_key: str,
    payload: AgentControlRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="agent")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        definition = await control_agent(
            session,
            agent_key=agent_key,
            expected_definition_id=payload.expected_definition_id,
            enabled=payload.action == "start",
            reason=payload.reason,
            subject=principal.subject,
        )
        return {
            "definition_id": definition.id,
            "agent_key": definition.agent_key,
            "active": definition.active,
            "version": definition.version,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="agent.runtime.control.v1",
        target=agent_key,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post(
    "/agents/{agent_key}/releases",
    status_code=status.HTTP_201_CREATED,
    tags=["agents"],
)
async def deploy_agent_release(
    agent_key: str,
    payload: AgentReleaseRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="agent")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        definition = await create_agent_release(
            session,
            agent_key=agent_key,
            request=payload,
            subject=principal.subject,
        )
        return {
            "definition_id": definition.id,
            "agent_key": definition.agent_key,
            "display_name": definition.display_name,
            "role": definition.role,
            "version": definition.version,
            "active": definition.active,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="agent.release.deploy.v1",
        target=agent_key,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.get("/agent-tools", tags=["agents"])
async def agent_tool_ledger(
    agent_id: str | None = Query(default=None, alias="agentId"),
    mission_id: str | None = Query(default=None, alias="missionId"),
    status_filter: str | None = Query(default=None, alias="status"),
    tool_name: str | None = Query(default=None, alias="toolName"),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = select(AgentToolInvocation)
    if agent_id:
        statement = statement.where(AgentToolInvocation.agent_key == normalize_agent_key(agent_id))
    if mission_id:
        statement = statement.where(AgentToolInvocation.mission_id == mission_id)
    if status_filter:
        statement = statement.where(AgentToolInvocation.status == status_filter)
    if tool_name:
        statement = statement.where(AgentToolInvocation.tool_key == tool_name)
    rows = list(
        (
            await session.scalars(
                statement.order_by(desc(AgentToolInvocation.completed_at)).limit(limit)
            )
        ).all()
    )
    catalog = [
        {
            "name": row.tool_key,
            "mode": row.mode,
            "version": row.version,
        }
        for row in (
            await session.scalars(select(ToolDefinition).order_by(ToolDefinition.tool_key))
        ).all()
    ]
    return {
        "ok": True,
        "data": {
            "catalog": catalog,
            "executionHistory": [serialize_invocation(row) for row in rows],
        },
        "error": None,
        "meta": {
            "persisted": True,
            "persistence": "postgresql",
            "historyCount": len(rows),
            "deterministic": False,
        },
    }


@router.post("/agent-tools", tags=["agents"])
async def execute_governed_agent_tool(
    payload: AgentToolExecuteRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="agent")),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    trusted_payload = payload.model_copy(update={"idempotency_key": idempotency_key})
    target = trusted_payload.mission_id or str(
        trusted_payload.args.get("mission_id") or trusted_payload.args.get("missionId") or "global"
    )

    async def operation() -> dict[str, Any]:
        invocation, invocation_replayed = await execute_agent_tool(
            session,
            trusted_payload,
            subject=principal.subject,
            eam_enabled=settings.eam_enabled,
            knowledge_policy=principal.graph_access_policy(),
        )
        execution = serialize_invocation(invocation)
        body = {
            "ok": invocation.status == "succeeded",
            "data": {"execution": execution},
            "error": (
                None
                if invocation.status == "succeeded"
                else {
                    "code": invocation.error_code,
                    "message": "The governed Agent Tool command was rejected.",
                }
            ),
            "meta": {
                "persisted": True,
                "persistence": "postgresql",
                "replayed": invocation_replayed,
                "dryRun": invocation.dry_run,
                "executionId": invocation.id,
                "deterministic": False,
            },
        }
        return {
            "body": body,
            "status_code": (
                status.HTTP_422_UNPROCESSABLE_ENTITY
                if invocation.status == "failed"
                else status.HTTP_200_OK
            ),
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="agent.tool.execute.v1",
        target=target,
        idempotency_key=idempotency_key,
        payload=trusted_payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    response.status_code = int(result["status_code"])
    return dict(result["body"])


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
                "evaluation_result": row.evaluation_result,
                "degradation_policy": row.degradation_policy,
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
            "evaluations_passed": sum(
                row.evaluation_result.get("status") == "passed" for row in executions
            ),
            "evaluations_failed": sum(
                row.evaluation_result.get("status") == "failed" for row in executions
            ),
            "fail_closed_executions": sum(
                row.degradation_policy.get("mode") == "fail_closed" for row in executions
            ),
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
                "evaluation_result": row.evaluation_result,
                "degradation_policy": row.degradation_policy,
            }
            for row in executions
            if row.status == "failed"
        ][-50:],
    }
