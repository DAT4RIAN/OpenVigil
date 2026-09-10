from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.errors import ConflictError, DomainError, NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    AgentDefinition,
    AgentSkillLink,
    AgentToolInvocation,
    AgentToolLink,
    Approval,
    Mission,
    Resource,
    ResourceReservation,
    SkillDefinition,
    ToolDefinition,
    WorkOrder,
)
from windops_backend.outbox import enqueue_knowledge_graph_projection
from windops_backend.schemas import (
    AgentReleaseRequest,
    AgentToolExecuteRequest,
    MaintenanceAlternative,
    WorkOrderScheduleUpdateRequest,
)
from windops_backend.services.eam import enqueue_eam_work_order_publish
from windops_backend.services.events import append_domain_event
from windops_backend.services.platform_governance import update_work_order_schedule

WRITE_TOOLS = frozenset({"create_decision", "create_work_order", "update_work_order"})
DEFAULT_AGENT_BY_TOOL = {
    "get_turbine_status": "scada_analysis_agent",
    "query_scada": "scada_analysis_agent",
    "query_alarm_history": "failure_diagnosis_agent",
    "query_vibration": "vibration_diagnosis_agent",
    "query_weather": "maintenance_strategy_agent",
    "query_maintenance_history": "maintenance_strategy_agent",
    "query_similar_failures": "failure_diagnosis_agent",
    "calculate_health_score": "maintenance_strategy_agent",
    "assess_condition_evidence": "maintenance_strategy_agent",
    "create_decision": "maintenance_strategy_agent",
    "create_work_order": "work_order_agent",
    "query_manual": "knowledge_agent",
    "query_work_orders": "work_order_agent",
    "query_spare_parts": "work_order_agent",
    "query_crew": "work_order_agent",
    "query_vessels": "work_order_agent",
    "update_work_order": "work_order_agent",
}
AGENT_ID_ALIASES = {
    "agent-scada-analysis": "scada_analysis_agent",
    "agent-vibration-diagnosis": "vibration_diagnosis_agent",
    "agent-failure-diagnosis": "failure_diagnosis_agent",
    "agent-knowledge": "knowledge_agent",
    "agent-maintenance-strategy": "maintenance_strategy_agent",
    "agent-review-committee": "review_committee",
    "agent-human-approval-gate": "human_approval_gate",
    "agent-work-order": "work_order_agent",
}


def normalize_agent_key(value: str) -> str:
    normalized = value.strip().lower()
    return AGENT_ID_ALIASES.get(normalized, normalized.replace("-", "_"))


def _stable_hash(value: dict[str, Any]) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def _argument(arguments: dict[str, Any], snake: str, camel: str | None = None) -> Any:
    if snake in arguments:
        return arguments[snake]
    return arguments.get(camel or snake)


async def control_agent(
    session: AsyncSession,
    *,
    agent_key: str,
    expected_definition_id: str,
    enabled: bool,
    reason: str,
    subject: str,
) -> AgentDefinition:
    definition = await session.scalar(
        select(AgentDefinition)
        .where(AgentDefinition.agent_key == agent_key)
        .order_by(desc(AgentDefinition.version))
        .with_for_update()
        .limit(1)
    )
    if definition is None:
        raise NotFoundError(f"agent {agent_key} was not found")
    if definition.id != expected_definition_id:
        raise ConflictError("the agent definition changed; refresh before retrying the command")
    definition.active = enabled
    append_domain_event(
        session,
        event_type="agent.started" if enabled else "agent.stopped",
        aggregate_type="agent_definition",
        aggregate_id=definition.id,
        payload={
            "agent_key": agent_key,
            "definition_id": definition.id,
            "reason": reason,
            "subject": subject,
            "in_flight_policy": "finish-current-no-new-work" if not enabled else "accept-new-work",
        },
    )
    await session.flush()
    return definition


async def create_agent_release(
    session: AsyncSession,
    *,
    agent_key: str,
    request: AgentReleaseRequest,
    subject: str,
) -> AgentDefinition:
    source = await session.get(AgentDefinition, request.source_definition_id)
    if source is None or source.agent_key != agent_key:
        raise NotFoundError("the source definition does not belong to the requested agent")
    release_id = f"agent:{agent_key}@{request.version}"
    if await session.get(AgentDefinition, release_id) is not None:
        raise ConflictError(f"agent release {agent_key}@{request.version} already exists")
    links = list(
        (
            await session.scalars(
                select(AgentSkillLink).where(AgentSkillLink.agent_definition_id == source.id)
            )
        ).all()
    )
    tool_links = list(
        (
            await session.scalars(
                select(AgentToolLink).where(AgentToolLink.agent_definition_id == source.id)
            )
        ).all()
    )
    await session.execute(
        update(AgentDefinition)
        .where(AgentDefinition.agent_key == agent_key, AgentDefinition.active.is_(True))
        .values(active=False)
    )
    release = AgentDefinition(
        id=release_id,
        agent_key=agent_key,
        display_name=request.display_name,
        role=request.role,
        version=request.version,
        catalog_version_id=source.catalog_version_id,
        description=request.description,
        active=True,
    )
    session.add(release)
    await session.flush()
    for skill_link in links:
        session.add(
            AgentSkillLink(
                agent_definition_id=release.id,
                skill_definition_id=skill_link.skill_definition_id,
                catalog_version_id=skill_link.catalog_version_id,
            )
        )
    for agent_tool_link in tool_links:
        session.add(
            AgentToolLink(
                agent_definition_id=release.id,
                tool_definition_id=agent_tool_link.tool_definition_id,
                catalog_version_id=agent_tool_link.catalog_version_id,
            )
        )
    append_domain_event(
        session,
        event_type="agent.release.deployed",
        aggregate_type="agent_definition",
        aggregate_id=release.id,
        payload={
            "agent_key": agent_key,
            "source_definition_id": source.id,
            "definition_id": release.id,
            "version": release.version,
            "reason": request.reason,
            "subject": subject,
        },
    )
    await session.flush()
    return release


async def _active_agent_for_tool(
    session: AsyncSession, agent_key: str, tool_key: str
) -> AgentDefinition:
    definition = await session.scalar(
        select(AgentDefinition)
        .where(AgentDefinition.agent_key == agent_key, AgentDefinition.active.is_(True))
        .order_by(desc(AgentDefinition.version))
        .limit(1)
    )
    if definition is None:
        raise ConflictError(f"agent {agent_key} is stopped or has no active release")
    allowed = await session.scalar(
        select(AgentToolLink.agent_definition_id)
        .join(ToolDefinition, ToolDefinition.id == AgentToolLink.tool_definition_id)
        .where(
            AgentToolLink.agent_definition_id == definition.id,
            ToolDefinition.tool_key == tool_key,
        )
    )
    if allowed is None:
        raise ConflictError(f"agent {agent_key} is not allowed to execute {tool_key}")
    return definition


def _bounded_limit(args: dict[str, Any], *, default: int, maximum: int) -> int:
    try:
        value = int(args.get("limit", default))
    except (TypeError, ValueError) as exc:
        raise ConflictError("limit must be an integer") from exc
    if not 1 <= value <= maximum:
        raise ConflictError(f"limit must be between 1 and {maximum}")
    return value


async def _query_resources(
    session: AsyncSession,
    args: dict[str, Any],
    *,
    resource_type: str,
) -> list[dict[str, Any]]:
    resources = list(
        (
            await session.scalars(
                select(Resource)
                .where(Resource.resource_type == resource_type)
                .order_by(Resource.id)
            )
        ).all()
    )
    reservations = (
        list(
            (
                await session.scalars(
                    select(ResourceReservation).where(
                        ResourceReservation.resource_id.in_([row.id for row in resources])
                    )
                )
            ).all()
        )
        if resources
        else []
    )
    work_orders = (
        list(
            (
                await session.scalars(
                    select(WorkOrder).where(
                        WorkOrder.mission_id.in_([row.mission_id for row in reservations])
                    )
                )
            ).all()
        )
        if reservations
        else []
    )
    work_order_by_mission = {row.mission_id: row for row in work_orders}
    reservations_by_resource: dict[str, list[dict[str, Any]]] = {}
    for reservation in reservations:
        work_order = work_order_by_mission.get(reservation.mission_id)
        reservations_by_resource.setdefault(reservation.resource_id, []).append(
            {
                "reservation_id": reservation.id,
                "mission_id": reservation.mission_id,
                "work_order_id": work_order.id if work_order is not None else None,
                "turbine_id": work_order.turbine_id if work_order is not None else None,
                "quantity": reservation.quantity,
            }
        )
    work_order_id = str(_argument(args, "work_order_id", "workOrderId") or "")
    turbine_id = str(_argument(args, "turbine_id", "turbineId") or "")
    availability = str(args.get("availability") or args.get("status") or "")
    part_number = str(_argument(args, "part_number", "partNumber") or "").lower()
    specialty = str(args.get("specialty") or "").lower()
    vessel_type = str(_argument(args, "vessel_type", "vesselType") or "").lower()
    rows: list[dict[str, Any]] = []
    for resource in resources:
        linked = reservations_by_resource.get(resource.id, [])
        attributes = dict(resource.attributes)
        if work_order_id and not any(item["work_order_id"] == work_order_id for item in linked):
            continue
        if turbine_id and not any(item["turbine_id"] == turbine_id for item in linked):
            continue
        if availability and resource.status != availability:
            continue
        if part_number and str(attributes.get("part_number", "")).lower() != part_number:
            continue
        specialties = " ".join(map(str, attributes.get("specialties", []))).lower()
        if specialty and specialty not in specialties:
            continue
        if vessel_type and str(attributes.get("vessel_type", "")).lower() != vessel_type:
            continue
        rows.append(
            {
                "resource_id": resource.id,
                "resource_type": resource.resource_type,
                "name": resource.name,
                "quantity": resource.quantity,
                "status": resource.status,
                "attributes": attributes,
                "reservations": linked,
                "updated_at": resource.updated_at,
            }
        )
    return rows[: _bounded_limit(args, default=20, maximum=50)]


async def _execute(
    session: AsyncSession,
    adapter: SQLToolAdapter,
    tool: str,
    args: dict[str, Any],
    *,
    dry_run: bool,
    eam_enabled: bool,
    subject: str,
    knowledge_policy: GraphAccessPolicy,
) -> dict[str, Any]:
    turbine_id = str(_argument(args, "turbine_id", "turbineId") or "")
    mission_id = str(_argument(args, "mission_id", "missionId") or "")
    if tool in {"create_decision", "create_work_order"} and dry_run:
        if not mission_id or await session.get(Mission, mission_id) is None:
            raise NotFoundError(f"mission {mission_id or '<missing>'} was not found")
        if tool == "create_work_order":
            approval_id = str(_argument(args, "approval_id", "approvalId") or "")
            approval = await session.get(Approval, approval_id)
            if approval is None or approval.mission_id != mission_id:
                raise NotFoundError("the approval does not belong to the requested mission")
        return {"validated": True, "would_persist": True, "tool": tool}
    if tool == "update_work_order":
        work_order_id = str(_argument(args, "work_order_id", "workOrderId") or "")
        schedule_request = WorkOrderScheduleUpdateRequest.model_validate(
            {
                "planned_start": _argument(args, "planned_start", "plannedStart"),
                "deadline": args.get("deadline"),
                "assigned_team": _argument(args, "assigned_team", "assignedTeam"),
                "expected_updated_at": _argument(args, "expected_updated_at", "expectedUpdatedAt"),
                "reason": args.get("reason"),
            }
        )
        row = await update_work_order_schedule(
            session,
            work_order_id=work_order_id,
            request=schedule_request,
            subject=subject,
            eam_enabled=eam_enabled,
            dry_run=dry_run,
        )
        return {
            "validated": True,
            "would_persist": dry_run,
            "work_order_id": row.id,
            "planned_start": schedule_request.planned_start.isoformat(),
            "deadline": schedule_request.deadline.isoformat(),
            "assigned_team": schedule_request.assigned_team or row.assigned_team,
        }
    if tool == "get_turbine_status":
        return await adapter.get_turbine_status(turbine_id)
    if tool == "query_scada":
        raw_variables = _argument(args, "variables")
        variables = (
            [str(value) for value in raw_variables] if isinstance(raw_variables, list) else None
        )
        return {
            "rows": await adapter.query_scada(turbine_id, variables, int(args.get("limit", 100)))
        }
    if tool == "query_alarm_history":
        return {"rows": await adapter.query_alarm_history(turbine_id, int(args.get("limit", 100)))}
    if tool == "query_vibration":
        return await adapter.query_vibration(turbine_id)
    if tool == "query_weather":
        wind_farm_id = str(
            _argument(args, "wind_farm_id", "windFarmId") or args.get("farmId") or ""
        )
        return {"rows": await adapter.query_weather(wind_farm_id)}
    if tool == "query_maintenance_history":
        return {"rows": await adapter.query_maintenance_history(turbine_id)}
    if tool == "query_similar_failures":
        return {
            "rows": await adapter.query_similar_failures(
                str(args.get("query", "")), turbine_id or None, int(args.get("limit", 5))
            )
        }
    if tool == "calculate_health_score":
        return await adapter.calculate_health_score(turbine_id)
    if tool == "assess_condition_evidence":
        component = str(args.get("component") or "asset")
        primary_variable = str(args.get("primary_variable") or "") or None
        return await adapter.assess_condition_evidence(turbine_id, component, primary_variable)
    if tool == "query_manual":
        documents = await adapter.visible_knowledge_documents()
        query = str(args.get("query") or "").strip().lower()
        document_id = str(_argument(args, "document_id", "documentId") or "")
        document_type = str(args.get("type") or "")
        rows = [
            {
                "document_id": row.id,
                "title": row.title,
                "document_type": row.document_type,
                "document_version": row.document_version,
                "citation_uri": row.citation_uri,
                "vectorized": row.vectorized,
                "index_status": row.ingestion_status,
                "metadata": row.metadata_,
                "updated_at": row.updated_at,
            }
            for row in documents
            if (not document_id or row.id == document_id)
            and (not document_type or row.document_type == document_type)
            and (
                not query or query in f"{row.id} {row.title} {row.document_type} {row.body}".lower()
            )
        ]
        return {"rows": rows[: _bounded_limit(args, default=10, maximum=20)]}
    if tool == "query_work_orders":
        statement = select(WorkOrder)
        work_order_id = str(_argument(args, "work_order_id", "workOrderId") or "")
        if work_order_id:
            statement = statement.where(WorkOrder.id == work_order_id)
        if turbine_id:
            statement = statement.where(WorkOrder.turbine_id == turbine_id)
        status_filter = str(args.get("status") or "")
        if status_filter:
            statement = statement.where(WorkOrder.status == status_filter.replace("-", "_"))
        priority = str(args.get("priority") or "")
        if priority:
            statement = statement.where(WorkOrder.priority == priority)
        work_order_rows = list(
            (
                await session.scalars(
                    statement.order_by(desc(WorkOrder.updated_at)).limit(
                        _bounded_limit(args, default=20, maximum=100)
                    )
                )
            ).all()
        )
        return {
            "rows": [
                {
                    "work_order_id": row.id,
                    "mission_id": row.mission_id,
                    "turbine_id": row.turbine_id,
                    "title": row.title,
                    "status": row.status,
                    "priority": row.priority,
                    "assigned_team": row.assigned_team,
                    "planned_start": row.planned_start,
                    "deadline": row.deadline,
                    "updated_at": row.updated_at,
                }
                for row in work_order_rows
            ]
        }
    if tool == "query_spare_parts":
        return {"rows": await _query_resources(session, args, resource_type="spare_part")}
    if tool == "query_crew":
        return {"rows": await _query_resources(session, args, resource_type="crew")}
    if tool == "query_vessels":
        return {"rows": await _query_resources(session, args, resource_type="vessel")}
    if tool == "create_decision":
        raw_alternatives = args.get("alternatives")
        if not isinstance(raw_alternatives, list):
            raise ConflictError("create_decision requires an alternatives array")
        alternatives = [
            MaintenanceAlternative.model_validate(item).model_dump() for item in raw_alternatives
        ]
        result = await adapter.create_decision(
            mission_id,
            alternatives,
            str(_argument(args, "recommended_alternative_id", "recommendedAlternativeId") or ""),
            str(_argument(args, "recommendation_reason", "recommendationReason") or ""),
            list(args.get("risks", [])),
        )
        append_domain_event(
            session,
            event_type="decision.proposed",
            aggregate_type="decision",
            aggregate_id=str(result["decision_id"]),
            payload={
                "decision_id": result["decision_id"],
                "mission_id": mission_id,
                "status": result["status"],
                "recommended_alternative_id": result["recommended_alternative_id"],
            },
        )
        enqueue_knowledge_graph_projection(
            session,
            aggregate_type="mission",
            aggregate_id=mission_id,
            reason="agent-tool-decision-proposed",
        )
        return result
    if tool == "create_work_order":
        result = await adapter.create_work_order(
            mission_id,
            str(_argument(args, "approval_id", "approvalId") or ""),
            turbine_id,
        )
        if result.get("created"):
            work_order_id = str(result["work_order_id"])
            append_domain_event(
                session,
                event_type="work_order.created",
                aggregate_type="work_order",
                aggregate_id=work_order_id,
                payload={
                    "work_order_id": work_order_id,
                    "mission_id": mission_id,
                    "turbine_id": turbine_id,
                },
            )
            if eam_enabled:
                enqueue_eam_work_order_publish(session, work_order_id)
            enqueue_knowledge_graph_projection(
                session,
                aggregate_type="mission",
                aggregate_id=mission_id,
                reason="agent-tool-work-order-created",
            )
        return result
    raise ConflictError(f"unsupported production tool {tool}")


async def execute_agent_tool(
    session: AsyncSession,
    request: AgentToolExecuteRequest,
    *,
    subject: str,
    eam_enabled: bool = False,
    knowledge_policy: GraphAccessPolicy | None = None,
) -> tuple[AgentToolInvocation, bool]:
    agent_key = normalize_agent_key(request.agent_id or DEFAULT_AGENT_BY_TOOL[request.tool])
    idempotency_key = request.idempotency_key or str(uuid4())
    request_body = {
        "agent_key": agent_key,
        "tool": request.tool,
        "args": request.args,
        "mission_id": request.mission_id,
        "dry_run": not request.persist,
    }
    request_hash = _stable_hash(request_body)
    existing = await session.scalar(
        select(AgentToolInvocation).where(
            AgentToolInvocation.subject == subject,
            AgentToolInvocation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ConflictError("the Agent Tool idempotency key was reused with another request")
        return existing, True
    definition = await _active_agent_for_tool(session, agent_key, request.tool)
    started_at = datetime.now(UTC)
    started = perf_counter()
    result: dict[str, Any] = {}
    invocation_status = "succeeded"
    error_code: str | None = None
    adapter = SQLToolAdapter(session, knowledge_policy=knowledge_policy)
    try:
        async with session.begin_nested():
            result = await _execute(
                session,
                adapter,
                request.tool,
                request.args,
                dry_run=not request.persist,
                eam_enabled=eam_enabled,
                subject=subject,
                knowledge_policy=adapter.knowledge_policy,
            )
            result = jsonable_encoder(result)
    except DomainError as exc:
        invocation_status = "failed"
        error_code = exc.code
    except Exception as exc:
        invocation_status = "failed"
        error_code = type(exc).__name__[:96]
    invocation = AgentToolInvocation(
        id=str(uuid4()),
        agent_key=definition.agent_key,
        tool_key=request.tool,
        mission_id=request.mission_id
        or str(_argument(request.args, "mission_id", "missionId") or "")
        or None,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        arguments=request.args,
        result=result,
        status=invocation_status,
        error_code=error_code,
        dry_run=not request.persist,
        subject=subject,
        latency_ms=max(0, round((perf_counter() - started) * 1000)),
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )
    session.add(invocation)
    append_domain_event(
        session,
        event_type=f"agent.tool.{invocation_status}",
        aggregate_type="agent_tool_invocation",
        aggregate_id=invocation.id,
        payload={
            "invocation_id": invocation.id,
            "agent_key": definition.agent_key,
            "tool_key": request.tool,
            "mission_id": invocation.mission_id,
            "status": invocation.status,
            "dry_run": invocation.dry_run,
            "subject": subject,
        },
    )
    await session.flush()
    return invocation, False


def serialize_invocation(invocation: AgentToolInvocation) -> dict[str, Any]:
    return {
        "executionId": invocation.id,
        "agentId": invocation.agent_key,
        "missionId": invocation.mission_id,
        "request": {"tool": invocation.tool_key, "args": invocation.arguments},
        "result": {
            "ok": invocation.status == "succeeded",
            "data": invocation.result,
            "dryRun": invocation.dry_run,
            **(
                {
                    "error": {
                        "code": invocation.error_code,
                        "message": "The governed Agent Tool command was rejected.",
                        "statusCode": 422,
                    }
                }
                if invocation.status == "failed"
                else {}
            ),
        },
        "status": invocation.status,
        "latencyMs": invocation.latency_ms,
        "correlationId": invocation.idempotency_key,
        "startedAt": invocation.started_at,
        "completedAt": invocation.completed_at,
        # Governed tool invocations run deterministic SQL adapters and never
        # touch an inference provider, so no real token usage exists to report.
        "tokenEstimate": None,
    }


async def agent_catalog_rows(session: AsyncSession) -> list[dict[str, Any]]:
    definitions = list(
        (
            await session.scalars(
                select(AgentDefinition).order_by(
                    AgentDefinition.agent_key,
                    desc(AgentDefinition.active),
                    desc(AgentDefinition.version),
                )
            )
        ).all()
    )
    latest: dict[str, AgentDefinition] = {}
    for definition in definitions:
        latest.setdefault(definition.agent_key, definition)
    definition_ids = [item.id for item in latest.values()]
    skill_links = (
        list(
            (
                await session.scalars(
                    select(AgentSkillLink).where(
                        AgentSkillLink.agent_definition_id.in_(definition_ids)
                    )
                )
            ).all()
        )
        if definition_ids
        else []
    )
    tool_links = (
        list(
            (
                await session.scalars(
                    select(AgentToolLink).where(
                        AgentToolLink.agent_definition_id.in_(definition_ids)
                    )
                )
            ).all()
        )
        if definition_ids
        else []
    )
    skills = (
        {
            row.id: row.skill_key
            for row in (
                await session.scalars(
                    select(SkillDefinition).where(
                        SkillDefinition.id.in_([link.skill_definition_id for link in skill_links])
                    )
                )
            ).all()
        }
        if skill_links
        else {}
    )
    tools = (
        {
            row.id: row.tool_key
            for row in (
                await session.scalars(
                    select(ToolDefinition).where(
                        ToolDefinition.id.in_([link.tool_definition_id for link in tool_links])
                    )
                )
            ).all()
        }
        if tool_links
        else {}
    )
    skill_map: dict[str, list[str]] = {}
    tool_map: dict[str, list[str]] = {}
    for skill_link in skill_links:
        skill_map.setdefault(skill_link.agent_definition_id, []).append(
            skills[skill_link.skill_definition_id]
        )
    for agent_tool_link in tool_links:
        tool_map.setdefault(agent_tool_link.agent_definition_id, []).append(
            tools[agent_tool_link.tool_definition_id]
        )
    return [
        {
            "definition_id": item.id,
            "agent_key": item.agent_key,
            "display_name": item.display_name,
            "role": item.role,
            "version": item.version,
            "catalog_version_id": item.catalog_version_id,
            "description": item.description,
            "active": item.active,
            "skills": sorted(skill_map.get(item.id, [])),
            "tools": sorted(tool_map.get(item.id, [])),
        }
        for item in latest.values()
    ]
