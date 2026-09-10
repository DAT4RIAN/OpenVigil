from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.config import Settings
from windops_backend.errors import NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy, NodeType
from windops_backend.knowledge_graph.service import KnowledgeGraphService
from windops_backend.knowledge_graph.store import KnowledgeGraphStore


class HybridKnowledgeRetrievalService:
    """Fuse pgvector candidates with explainable graph neighborhoods."""

    def __init__(self, store: KnowledgeGraphStore) -> None:
        self.store = store

    async def search(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        query: str,
        entity_id: str | None,
        limit: int,
        policy: GraphAccessPolicy | None = None,
    ) -> dict[str, Any]:
        graph_service = KnowledgeGraphService(self.store)
        if entity_id is not None:
            try:
                await graph_service.subgraph(entity_id, depth=1, policy=policy)
            except NotFoundError:
                raise NotFoundError(
                    f"knowledge graph scope entity {entity_id} was not found"
                ) from None

        tools = SQLToolAdapter(session, settings=settings, knowledge_policy=policy)
        candidates = await tools.query_similar_failures(
            query,
            turbine_id=entity_id if entity_id and entity_id.startswith("WT-") else None,
            limit=limit,
            # SQLToolAdapter bounds this compatibility path to a small batch;
            # it can never turn a graph read into whole-corpus indexing.
            vectorize_missing=True,
        )
        ranked: list[dict[str, Any]] = []
        for candidate in candidates:
            match_type = str(candidate.get("match_type", "unknown"))
            lookup_id = (
                f"{candidate['document_id']}#body"
                if match_type == "knowledge_document" and candidate.get("document_id")
                else str(candidate.get("case_id", ""))
            )
            if not lookup_id:
                continue
            try:
                expansion = await graph_service.subgraph(lookup_id, depth=4, policy=policy)
            except NotFoundError:
                continue

            scope_hit = entity_id is None or any(
                node.entity_id == entity_id or node.properties.get("turbineId") == entity_id
                for node in expansion.nodes
            )
            if policy is not None and entity_id is not None:
                # A tenant/farm-scoped controlled manual is valid evidence for
                # an asset query even when the document itself is not tagged to
                # one individual turbine. Graph policy filtering has already
                # established that the document is visible to this principal.
                scope_hit = scope_hit or any(
                    node.node_type in {NodeType.KNOWLEDGE_DOCUMENT, NodeType.KNOWLEDGE_PASSAGE}
                    for node in expansion.nodes
                )
            if policy is not None and entity_id is not None and not scope_hit:
                # A scoped query must not turn a tenant-global passage into a
                # cross-tenant result merely because its vector score is high.
                continue
            failure_modes = [
                node.entity_id for node in expansion.nodes if node.node_type.value == "FailureMode"
            ]
            cases = [
                node.entity_id
                for node in expansion.nodes
                if node.node_type.value == "KnowledgeCase"
            ]
            evidence = [
                node.entity_id for node in expansion.nodes if node.node_type.value == "Evidence"
            ]
            graph_score = min(
                1.0,
                0.15
                + (0.3 if scope_hit else 0.0)
                + min(0.25, len(failure_modes) * 0.1)
                + min(0.2, len(evidence) * 0.04)
                + min(0.1, len(cases) * 0.05),
            )
            raw_similarity = candidate.get("similarity")
            vector_score = (
                max(0.0, min(1.0, float(raw_similarity)))
                if isinstance(raw_similarity, int | float)
                else 0.5
            )
            fused_score = round(vector_score * 0.7 + graph_score * 0.3, 6)
            ranked.append(
                {
                    **candidate,
                    "passageId": lookup_id if match_type == "knowledge_document" else None,
                    "vectorScore": round(vector_score, 6),
                    "graphScore": round(graph_score, 6),
                    "fusedScore": fused_score,
                    "scopeMatched": scope_hit,
                    "graphExpansion": {
                        "rootUid": expansion.root_uid,
                        "failureModeIds": failure_modes,
                        "evidenceIds": evidence,
                        "caseIds": cases,
                        "paths": [path.as_dict() for path in expansion.paths[:10]],
                    },
                }
            )

        ranked.sort(
            key=lambda item: (float(item["fusedScore"]), str(item.get("title", ""))),
            reverse=True,
        )
        top = ranked[0] if ranked else None
        retrieval_methods = sorted(
            {str(item.get("retrieval_method")) for item in ranked if item.get("retrieval_method")}
        )
        return {
            "query": query,
            "scopeEntityId": entity_id,
            "answer": (
                f"最高相关证据为《{top.get('title', top.get('case_id', '未命名证据'))}》，"
                f"融合得分 {top['fusedScore']}；请沿返回的关系路径复核诊断与闭环记录。"
                if top is not None
                else "没有找到已向量化且能够在知识图谱中解释的证据。"
            ),
            "answerMode": "grounded-retrieval-summary-no-generative-claim",
            "matches": ranked[:limit],
            "retrieval": {
                "vector": retrieval_methods,
                "graph": self.store.backend_name,
                "fusion": "0.70*vectorScore + 0.30*graphScore",
                "graphDepth": 4,
            },
        }
