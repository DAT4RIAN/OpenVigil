"""Structural graph facts must respect the authoritative SQL row grants."""

from dataclasses import replace

import pytest
from sqlalchemy import select

from test_hybrid_structure import identities
from test_structural_graph import graph, rebuild, scoped_headers
from windops_backend.access_control import ACCESS_POLICY_SESSION_KEY
from windops_backend.knowledge_graph.domain import GraphAccessPolicy, GraphNode, NodeType, graph_uid
from windops_backend.models import SensorChannel, TowerComponent


@pytest.mark.parametrize(
    ("kind", "related_property"),
    [
        (NodeType.TENDON_ASSEMBLY, "componentId"),
        (NodeType.SENSOR_CHANNEL, "componentId"),
        (NodeType.SENSOR_CHANNEL, "tendonId"),
        (NodeType.STRUCTURAL_ANALYSIS_RUN, "recordId"),
        (NodeType.MODAL_OBSERVATION, "runId"),
        (NodeType.PRESTRESS_OBSERVATION, "sensorId"),
        (NodeType.HEALTH_BASELINE, "componentId"),
        (NodeType.FIELD_MEASUREMENT, "missionId"),
        (NodeType.CLOSURE_ASSESSMENT, "workOrderId"),
    ],
)
def test_related_structural_fact_is_not_an_entity_permission(kind, related_property):
    node = GraphNode(
        graph_uid(kind, "SYNTHETIC-ROW"),
        kind,
        "SYNTHETIC-ROW",
        {"turbineId": "WT-023", related_property: "SYNTHETIC-RELATED"},
    )
    policy = GraphAccessPolicy.from_values(
        turbine_ids=["WT-023"], entity_ids=["SYNTHETIC-RELATED"], data_scopes=["structural"]
    )
    assert not policy.allows(node)
    assert replace(policy, entity_ids=frozenset({"synthetic-row"})).allows(node)
    assert replace(policy, entity_ids=frozenset({"wt-023"})).allows(node)
    assert replace(policy, entity_ids=frozenset({"*"})).allows(node)
    assert not replace(
        policy, entity_ids=frozenset({"*"}), data_scopes=frozenset({"knowledge"})
    ).allows(node)


async def test_component_only_graph_does_not_expose_sql_denied_sensor_rows(app, client):
    component, sensors = await identities(client)
    policy = GraphAccessPolicy.from_values(
        turbine_ids=["WT-023"], entity_ids=[component["id"]], data_scopes=["structural"]
    )
    async with app.state.session_factory() as session:
        session.info[ACCESS_POLICY_SESSION_KEY] = policy
        assert await session.scalar(select(TowerComponent.id)) == component["id"]
        assert not list(await session.scalars(select(SensorChannel)))
    await rebuild(app)
    response = await graph(
        client,
        component["id"],
        headers=scoped_headers(
            **{
                "X-WindOps-Test-Entity-Ids": component["id"],
                "X-WindOps-Test-Data-Scopes": "structural",
            }
        ),
    )
    assert response.status_code == 200, response.text
    nodes = response.json()["data"]["nodes"]
    assert {node["entityId"] for node in nodes} == {component["id"]}
    assert not {sensor["id"] for sensor in sensors}.intersection(node["entityId"] for node in nodes)
