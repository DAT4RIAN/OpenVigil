from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import NotFoundError
from windops_backend.knowledge_graph.domain import (
    GraphAccessPolicy,
    GraphSnapshot,
    GraphSubgraph,
    GraphSummary,
    ReconciliationReport,
)
from windops_backend.knowledge_graph.projection import (
    KNOWLEDGE_GRAPH_PROJECTION_ID,
    ProjectionLimits,
    build_knowledge_graph_snapshot,
)
from windops_backend.knowledge_graph.store import KnowledgeGraphStore


class KnowledgeGraphService:
    def __init__(
        self,
        store: KnowledgeGraphStore,
        *,
        limits: ProjectionLimits | None = None,
    ) -> None:
        self.store = store
        self.limits = limits

    async def rebuild(self, session: AsyncSession) -> GraphSummary:
        snapshot = await build_knowledge_graph_snapshot(session, limits=self.limits)
        await self.store.replace_projection(snapshot)
        return await self.store.summary(snapshot.projection_id)

    async def summary(self, policy: GraphAccessPolicy | None = None) -> GraphSummary:
        return await self.store.summary(KNOWLEDGE_GRAPH_PROJECTION_ID, policy)

    async def subgraph(
        self,
        entity_id: str,
        *,
        depth: int,
        policy: GraphAccessPolicy | None = None,
    ) -> GraphSubgraph:
        uid = await self.store.resolve_uid(KNOWLEDGE_GRAPH_PROJECTION_ID, entity_id, policy)
        if uid is None:
            raise NotFoundError(f"knowledge graph entity {entity_id} was not found")
        subgraph = await self.store.subgraph(
            KNOWLEDGE_GRAPH_PROJECTION_ID,
            uid,
            depth=depth,
            policy=policy,
        )
        if not subgraph.nodes:
            raise NotFoundError(f"knowledge graph entity {entity_id} was not found")
        return subgraph

    async def fault_trace(
        self, turbine_id: str, policy: GraphAccessPolicy | None = None
    ) -> GraphSubgraph:
        return await self.subgraph(turbine_id, depth=4, policy=policy)

    async def alarm_impact(
        self, alarm_id: str, policy: GraphAccessPolicy | None = None
    ) -> GraphSubgraph:
        return await self.subgraph(alarm_id, depth=4, policy=policy)

    async def similar_cases(
        self, failure_mode_id: str, policy: GraphAccessPolicy | None = None
    ) -> GraphSubgraph:
        return await self.subgraph(failure_mode_id, depth=2, policy=policy)

    async def passage_support(
        self, passage_id: str, policy: GraphAccessPolicy | None = None
    ) -> GraphSubgraph:
        return await self.subgraph(passage_id, depth=4, policy=policy)

    async def reconcile(
        self,
        session: AsyncSession,
        policy: GraphAccessPolicy | None = None,
    ) -> ReconciliationReport:
        expected = await build_knowledge_graph_snapshot(session, limits=self.limits)
        if policy is not None:
            expected = policy.filter_snapshot(expected)
        actual_summary = await self.store.summary(expected.projection_id, policy)
        actual_nodes, actual_relationships = await self.store.identity_sets(
            expected.projection_id, policy
        )
        expected_nodes = {node.uid for node in expected.nodes}
        expected_relationships = {relationship.uid for relationship in expected.relationships}
        missing_nodes = tuple(sorted(expected_nodes - actual_nodes))
        unexpected_nodes = tuple(sorted(actual_nodes - expected_nodes))
        missing_relationships = tuple(sorted(expected_relationships - actual_relationships))
        unexpected_relationships = tuple(sorted(actual_relationships - expected_relationships))
        consistent = (
            actual_summary.source_revision == expected.source_revision
            and not missing_nodes
            and not unexpected_nodes
            and not missing_relationships
            and not unexpected_relationships
        )
        return ReconciliationReport(
            consistent=consistent,
            expected_revision=expected.source_revision,
            actual_revision=actual_summary.source_revision,
            missing_node_uids=missing_nodes,
            unexpected_node_uids=unexpected_nodes,
            missing_relationship_uids=missing_relationships,
            unexpected_relationship_uids=unexpected_relationships,
        )


async def project_authoritative_graph(
    session: AsyncSession,
    store: KnowledgeGraphStore,
    *,
    projection_sequence: str,
    limits: ProjectionLimits | None = None,
) -> GraphSnapshot:
    snapshot = await build_knowledge_graph_snapshot(
        session,
        projection_sequence=projection_sequence,
        limits=limits,
    )
    await store.replace_projection(snapshot)
    return snapshot
