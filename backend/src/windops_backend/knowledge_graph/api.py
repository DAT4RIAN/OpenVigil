from __future__ import annotations

from collections.abc import Awaitable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.api.deps import (
    Principal,
    get_runtime_settings,
    get_session,
    require_global_roles,
    require_knowledge_graph_read_access,
)
from windops_backend.config import Settings
from windops_backend.errors import DomainError, KnowledgeGraphUnavailableError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.knowledge_graph.projection import (
    KNOWLEDGE_GRAPH_PROJECTION_ID,
    ProjectionLimits,
)
from windops_backend.knowledge_graph.retrieval import HybridKnowledgeRetrievalService
from windops_backend.knowledge_graph.service import KnowledgeGraphService
from windops_backend.knowledge_graph.store import KnowledgeGraphStore
from windops_backend.outbox import (
    enqueue_knowledge_graph_projection,
    mark_dispatched,
    process_knowledge_graph_projection_event,
)
from windops_backend.services.idempotency import (
    execute_idempotent_command,
    replace_idempotent_response,
)
from windops_backend.storage import OutboxEvent

router = APIRouter(prefix="/knowledge-graph", tags=["knowledge-graph"])


def get_graph_store(request: Request) -> KnowledgeGraphStore:
    return cast(KnowledgeGraphStore, request.app.state.knowledge_graph_store)


def _meta(store: KnowledgeGraphStore) -> dict[str, str]:
    return {
        "authoritativeSource": "postgresql",
        "projectionBackend": store.backend_name,
        "consistency": "eventually-consistent-rebuildable-projection",
    }


async def _available[GraphResult](operation: Awaitable[GraphResult]) -> GraphResult:
    try:
        return await operation
    except DomainError:
        raise
    except Exception as exc:
        raise KnowledgeGraphUnavailableError(
            "knowledge graph projection is temporarily unavailable"
        ) from exc


async def _dispatch_projection_event(
    request: Request,
    settings: Settings,
    store: KnowledgeGraphStore,
    event_id: str,
    policy: GraphAccessPolicy | None = None,
) -> tuple[str, dict[str, object] | None]:
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    if settings.outbox_inline_drain:
        await _available(
            process_knowledge_graph_projection_event(
                factory,
                event_id,
                store,
                ProjectionLimits.from_settings(settings),
            )
        )
        summary = await _available(KnowledgeGraphService(store).summary(policy))
        return "succeeded", summary.as_dict()

    from windops_backend.workers import dispatch_graph_event_ids

    dispatch_graph_event_ids([event_id])
    await mark_dispatched(factory, [event_id])
    return "dispatched", None


@router.get("/summary")
async def graph_summary(
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(require_knowledge_graph_read_access),
) -> dict[str, Any]:
    summary = await _available(
        KnowledgeGraphService(store).summary(principal.graph_access_policy())
    )
    return {"data": summary.as_dict(), "meta": _meta(store)}


@router.get("/entities/{entity_id}/subgraph")
async def entity_subgraph(
    entity_id: str,
    depth: int = Query(default=2, ge=1, le=4),
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(require_knowledge_graph_read_access),
) -> dict[str, Any]:
    graph = await _available(
        KnowledgeGraphService(store).subgraph(
            entity_id,
            depth=depth,
            policy=principal.graph_access_policy(),
        )
    )
    return {"data": graph.as_dict(), "meta": _meta(store)}


@router.get("/search")
async def hybrid_search(
    query: str = Query(min_length=3, max_length=500),
    entity_id: str | None = Query(default=None, alias="entityId", max_length=160),
    limit: int = Query(default=5, ge=1, le=10),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(require_knowledge_graph_read_access),
) -> dict[str, Any]:
    result = await _available(
        HybridKnowledgeRetrievalService(store).search(
            session,
            settings,
            query=query.strip(),
            entity_id=entity_id.strip() if entity_id else None,
            limit=limit,
            policy=principal.graph_access_policy(),
        )
    )
    return {"data": result, "meta": _meta(store)}


@router.get("/turbines/{turbine_id}/fault-trace")
async def turbine_fault_trace(
    turbine_id: str,
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(require_knowledge_graph_read_access),
) -> dict[str, Any]:
    graph = await _available(
        KnowledgeGraphService(store).fault_trace(
            turbine_id,
            policy=principal.graph_access_policy(),
        )
    )
    return {"data": graph.as_dict(), "meta": _meta(store)}


@router.get("/alarms/{alarm_id}/impact")
async def alarm_impact(
    alarm_id: str,
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(require_knowledge_graph_read_access),
) -> dict[str, Any]:
    graph = await _available(
        KnowledgeGraphService(store).alarm_impact(
            alarm_id,
            policy=principal.graph_access_policy(),
        )
    )
    return {"data": graph.as_dict(), "meta": _meta(store)}


@router.get("/failure-modes/{failure_mode_id}/similar-cases")
async def similar_cases(
    failure_mode_id: str,
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(require_knowledge_graph_read_access),
) -> dict[str, Any]:
    graph = await _available(
        KnowledgeGraphService(store).similar_cases(
            failure_mode_id,
            policy=principal.graph_access_policy(),
        )
    )
    return {"data": graph.as_dict(), "meta": _meta(store)}


@router.get("/passages/{passage_id:path}/support")
async def passage_support(
    passage_id: str,
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(require_knowledge_graph_read_access),
) -> dict[str, Any]:
    graph = await _available(
        KnowledgeGraphService(store).passage_support(
            passage_id,
            policy=principal.graph_access_policy(),
        )
    )
    supporting_ids = {
        relationship.target_uid
        for relationship in graph.relationships
        if relationship.relationship_type.value == "SUPPORTED_BY"
    }
    contradicting_ids = {
        relationship.target_uid
        for relationship in graph.relationships
        if relationship.relationship_type.value == "CONTRADICTED_BY"
    }
    data = graph.as_dict()
    data["supportAnalysis"] = {
        "diagnosisIds": [
            node.entity_id for node in graph.nodes if node.node_type.value == "FailureMode"
        ],
        "supportingEvidenceIds": [
            node.entity_id for node in graph.nodes if node.uid in supporting_ids
        ],
        "contradictingEvidenceIds": [
            node.entity_id for node in graph.nodes if node.uid in contradicting_ids
        ],
        "hasContradictingEvidence": bool(contradicting_ids),
    }
    return {"data": data, "meta": _meta(store)}


@router.get("/observability")
async def graph_observability(
    session: AsyncSession = Depends(get_session),
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(require_knowledge_graph_read_access),
) -> dict[str, Any]:
    started = perf_counter()
    policy = principal.graph_access_policy()
    summary = await _available(KnowledgeGraphService(store).summary(policy))
    unsupported = await _available(
        store.unsupported_failure_mode_uids(KNOWLEDGE_GRAPH_PROJECTION_ID, policy)
    )
    graph_read_latency_ms = max(0, round((perf_counter() - started) * 1000))
    event_type = "knowledge-graph.projection.requested"
    status_counts = {
        str(event_status): int(count)
        for event_status, count in (
            await session.execute(
                select(OutboxEvent.status, func.count(OutboxEvent.id))
                .where(OutboxEvent.event_type == event_type)
                .group_by(OutboxEvent.status)
            )
        ).all()
    }
    oldest_pending = await session.scalar(
        select(func.min(OutboxEvent.created_at)).where(
            OutboxEvent.event_type == event_type,
            OutboxEvent.status.in_(("pending", "dispatched", "processing", "failed")),
        )
    )
    oldest_pending_seconds = 0
    if oldest_pending is not None:
        oldest = oldest_pending
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=UTC)
        oldest_pending_seconds = max(0, round((datetime.now(UTC) - oldest).total_seconds()))
    projection_age_seconds: int | None = None
    if summary.generated_at:
        projected_at = datetime.fromisoformat(summary.generated_at)
        if projected_at.tzinfo is None:
            projected_at = projected_at.replace(tzinfo=UTC)
        projection_age_seconds = max(0, round((datetime.now(UTC) - projected_at).total_seconds()))
    latest_sync_latency_ms: int | None = None
    latest = (
        await session.execute(
            select(OutboxEvent.created_at, OutboxEvent.processed_at)
            .where(
                OutboxEvent.event_type == event_type,
                OutboxEvent.processed_at.is_not(None),
            )
            .order_by(OutboxEvent.processed_at.desc())
            .limit(1)
        )
    ).one_or_none()
    if latest is not None:
        created_at, processed_at = latest
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if processed_at.tzinfo is None:
            processed_at = processed_at.replace(tzinfo=UTC)
        latest_sync_latency_ms = max(0, round((processed_at - created_at).total_seconds() * 1000))
    return {
        "data": {
            "projection": summary.as_dict(),
            "projectionAgeSeconds": projection_age_seconds,
            "latestProjectionSyncLatencyMs": latest_sync_latency_ms,
            "graphReadLatencyMs": graph_read_latency_ms,
            "outboxStatusCounts": dict(status_counts),
            "oldestUnfinishedEventSeconds": oldest_pending_seconds,
            "unsupportedFailureModeCount": len(unsupported),
            "unsupportedFailureModeUids": sorted(unsupported),
        },
        "meta": _meta(store),
    }


@router.get("/reconcile")
async def reconcile_graph(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(require_knowledge_graph_read_access),
) -> dict[str, Any]:
    report = await _available(
        KnowledgeGraphService(
            store,
            limits=ProjectionLimits.from_settings(settings),
        ).reconcile(session, principal.graph_access_policy())
    )
    return {"data": report.as_dict(), "meta": _meta(store)}


@router.post("/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild_graph(
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(
        require_global_roles("operations_manager", data_scopes="knowledge")
    ),
) -> dict[str, Any]:
    event_ids: list[str] = []

    async def operation() -> dict[str, Any]:
        event = enqueue_knowledge_graph_projection(
            session,
            aggregate_type="knowledge_graph",
            aggregate_id="windops-operational-knowledge-v1",
            reason="operator-requested-rebuild",
        )
        await session.flush()
        event_ids.append(event.id)
        return {"eventId": event.id}

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="knowledge-graph.rebuild.v1",
        target=KNOWLEDGE_GRAPH_PROJECTION_ID,
        idempotency_key=idempotency_key,
        payload={},
        status_code=status.HTTP_202_ACCEPTED,
        operation=operation,
    )
    await session.commit()
    if event_ids:
        projection_status, summary = await _dispatch_projection_event(
            request,
            settings,
            store,
            event_ids[0],
            principal.graph_access_policy(),
        )
        result.update({"status": projection_status, "meta": _meta(store)})
        if summary is not None:
            result["data"] = summary
        factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
        async with factory() as finalize_session, finalize_session.begin():
            await replace_idempotent_response(
                finalize_session,
                subject=principal.subject,
                command_type="knowledge-graph.rebuild.v1",
                target=KNOWLEDGE_GRAPH_PROJECTION_ID,
                idempotency_key=idempotency_key,
                response_body=result,
            )
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post("/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex_knowledge(
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    store: KnowledgeGraphStore = Depends(get_graph_store),
    principal: Principal = Depends(
        require_global_roles("operations_manager", data_scopes="knowledge")
    ),
) -> dict[str, Any]:
    event_ids: list[str] = []

    async def operation() -> dict[str, Any]:
        index_result = await SQLToolAdapter(session, settings=settings).index_knowledge_documents()
        event = enqueue_knowledge_graph_projection(
            session,
            aggregate_type="knowledge_graph",
            aggregate_id=KNOWLEDGE_GRAPH_PROJECTION_ID,
            reason="knowledge-documents-reindexed",
        )
        await session.flush()
        event_ids.append(event.id)
        return {"eventId": event.id, "index": index_result}

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="knowledge-graph.reindex.v1",
        target=KNOWLEDGE_GRAPH_PROJECTION_ID,
        idempotency_key=idempotency_key,
        payload={},
        status_code=status.HTTP_202_ACCEPTED,
        operation=operation,
    )
    await session.commit()
    if event_ids:
        projection_status, summary = await _dispatch_projection_event(
            request,
            settings,
            store,
            event_ids[0],
            principal.graph_access_policy(),
        )
        result = {
            "eventId": event_ids[0],
            "status": projection_status,
            "data": {"index": result["index"], "projection": summary},
            "meta": _meta(store),
        }
        factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
        async with factory() as finalize_session, finalize_session.begin():
            await replace_idempotent_response(
                finalize_session,
                subject=principal.subject,
                command_type="knowledge-graph.reindex.v1",
                target=KNOWLEDGE_GRAPH_PROJECTION_ID,
                idempotency_key=idempotency_key,
                response_body=result,
            )
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result
