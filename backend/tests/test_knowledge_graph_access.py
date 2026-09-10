from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from windops_backend.api.deps import Principal, require_knowledge_graph_read_access
from windops_backend.config import IdentityAccessScope
from windops_backend.knowledge_graph.domain import (
    GraphAccessPolicy,
    GraphNode,
    GraphRelationship,
    GraphSnapshot,
    NodeType,
    RelationshipType,
    graph_uid,
)
from windops_backend.knowledge_graph.store import InMemoryKnowledgeGraphStore


@pytest.mark.asyncio
async def test_graph_scope_dependency_fails_closed_without_asset_grant() -> None:
    with pytest.raises(HTTPException) as missing_scope:
        await require_knowledge_graph_read_access(
            Principal(subject="unmapped", roles=("field_technician",))
        )
    assert missing_scope.value.status_code == 403
    assert missing_scope.value.detail["code"] == "GRAPH_SCOPE_REQUIRED"

    with pytest.raises(HTTPException) as data_only:
        await require_knowledge_graph_read_access(
            Principal(
                subject="data-only",
                roles=("field_technician",),
                data_scopes=("asset",),
                scope_configured=True,
            )
        )
    assert data_only.value.detail["code"] == "GRAPH_SCOPE_REQUIRED"


def scoped_snapshot() -> GraphSnapshot:
    nodes = (
        GraphNode(
            uid=graph_uid(NodeType.WIND_FARM, "WF-A"),
            node_type=NodeType.WIND_FARM,
            entity_id="WF-A",
            properties={"tenantId": "TENANT-A", "dataScope": "asset"},
        ),
        GraphNode(
            uid=graph_uid(NodeType.TURBINE, "WT-A"),
            node_type=NodeType.TURBINE,
            entity_id="WT-A",
            properties={
                "tenantId": "TENANT-A",
                "windFarmId": "WF-A",
                "turbineId": "WT-A",
                "dataScope": "asset",
            },
        ),
        GraphNode(
            uid=graph_uid(NodeType.ALARM, "ALARM-A"),
            node_type=NodeType.ALARM,
            entity_id="ALARM-A",
            properties={
                "tenantId": "TENANT-A",
                "windFarmId": "WF-A",
                "turbineId": "WT-A",
                "dataScope": "alarm",
            },
        ),
        GraphNode(
            uid=graph_uid(NodeType.TURBINE, "WT-B"),
            node_type=NodeType.TURBINE,
            entity_id="WT-B",
            properties={
                "tenantId": "TENANT-B",
                "windFarmId": "WF-B",
                "turbineId": "WT-B",
                "dataScope": "asset",
            },
        ),
        GraphNode(
            uid=graph_uid(NodeType.KNOWLEDGE_DOCUMENT, "MANUAL-GLOBAL"),
            node_type=NodeType.KNOWLEDGE_DOCUMENT,
            entity_id="MANUAL-GLOBAL",
            properties={"dataScope": "knowledge"},
        ),
    )
    relationships = (
        GraphRelationship(
            uid="HAS_TURBINE:A",
            relationship_type=RelationshipType.HAS_TURBINE,
            source_uid=graph_uid(NodeType.WIND_FARM, "WF-A"),
            target_uid=graph_uid(NodeType.TURBINE, "WT-A"),
        ),
        GraphRelationship(
            uid="TRIGGERED:A",
            relationship_type=RelationshipType.TRIGGERED,
            source_uid=graph_uid(NodeType.ALARM, "ALARM-A"),
            target_uid=graph_uid(NodeType.TURBINE, "WT-A"),
        ),
    )
    return GraphSnapshot(
        projection_id="test-scope",
        projection_sequence="1",
        source_revision="revision",
        generated_at=datetime.now(UTC),
        nodes=nodes,
        relationships=relationships,
    )


@pytest.mark.asyncio
async def test_graph_store_filters_tenant_farm_and_data_scope() -> None:
    store = InMemoryKnowledgeGraphStore()
    snapshot = scoped_snapshot()
    await store.replace_projection(snapshot)
    policy = GraphAccessPolicy.from_values(
        tenant_ids=["tenant-a"],
        wind_farm_ids=["wf-a"],
        data_scopes=["asset", "alarm"],
        allow_global=False,
    )

    summary = await store.summary("test-scope", policy)
    assert summary.node_count == 3
    assert summary.node_type_counts == {"WindFarm": 1, "Turbine": 1, "Alarm": 1}
    graph = await store.subgraph(
        "test-scope",
        graph_uid(NodeType.TURBINE, "WT-A"),
        depth=2,
        policy=policy,
    )
    assert {node.entity_id for node in graph.nodes} == {"WF-A", "WT-A", "ALARM-A"}
    assert all("WT-B" not in node.entity_id for node in graph.nodes)

    farm_only = GraphAccessPolicy.from_values(
        wind_farm_ids=["wf-a"],
        data_scopes=["asset"],
    )
    farm_visible = await store.resolve_uid("test-scope", "WF-A", farm_only)
    assert farm_visible == graph_uid(NodeType.WIND_FARM, "WF-A")

    data_only = GraphAccessPolicy.from_values(data_scopes=["asset"])
    assert (await store.summary("test-scope", data_only)).node_count == 0


@pytest.mark.asyncio
async def test_knowledge_graph_api_requires_scope_and_returns_only_granted_tenant(
    app: FastAPI,
) -> None:
    app.state.settings.identity_scope_mappings["scoped-reader"] = IdentityAccessScope(
        tenant_ids=["tenant-that-does-not-exist"],
        data_scopes=["asset"],
    )
    scoped_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-WindOps-Test-Principal": "scoped-reader",
            "X-WindOps-Test-Role": "field_technician",
        },
    )
    async with scoped_client:
        summary = await scoped_client.get("/api/v1/knowledge-graph/summary")
        assert summary.status_code == 200
        assert summary.json()["data"]["nodeCount"] == 0

        hidden = await scoped_client.get("/api/v1/knowledge-graph/entities/WT-023/subgraph?depth=1")
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "NOT_FOUND"

    app.state.settings.identity_scope_mappings["asset-reader"] = IdentityAccessScope(
        tenant_ids=["tenant-east-china"],
        data_scopes=["asset"],
    )
    asset_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-WindOps-Test-Principal": "asset-reader",
            "X-WindOps-Test-Role": "field_technician",
        },
    )
    async with asset_client:
        asset_summary = await asset_client.get("/api/v1/knowledge-graph/summary")
        assert asset_summary.status_code == 200
        assert asset_summary.json()["data"]["nodeTypeCounts"].get("Alarm", 0) == 0
