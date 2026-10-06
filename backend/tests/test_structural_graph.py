"""Real SQL/API/FDD projection challenges using explicit synthetic storage fixtures."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from test_engineering_claims import claim_input, create, review
from test_hybrid_structure import post
from test_hybrid_structure import test_repeated_worker_crashes_are_bounded as _exhausted
from test_structural_workflow import (
    test_out_of_bounds_retest_preserves_unresolved_alarm_and_immutable_followup_review as _followup,
)
from windops_backend.errors import NotFoundError
from windops_backend.knowledge_graph import structural_access
from windops_backend.knowledge_graph.domain import (
    GraphAccessPolicy,
    GraphNode,
    NodeType,
    graph_uid,
)
from windops_backend.knowledge_graph.projection import build_knowledge_graph_snapshot
from windops_backend.knowledge_graph.service import KnowledgeGraphService
from windops_backend.models import (
    EngineeringClaim,
    SensorChannel,
    StructuralHealthReview,
    StructuralRetestHandoff,
)
from windops_backend.outbox import process_knowledge_graph_projection_event
from windops_backend.services.events import append_domain_event
from windops_backend.storage import FieldTaskEvidence, OutboxEvent


async def rebuild(app):
    async with app.state.session_factory() as session:
        snapshot = await build_knowledge_graph_snapshot(session)
    await app.state.knowledge_graph_store.replace_projection(snapshot)
    return snapshot


async def graph(client, entity_id, **kwargs):
    return await client.get(
        f"/api/v1/knowledge-graph/entities/{entity_id}/subgraph", params={"depth": 4}, **kwargs
    )


def scoped_headers(**overrides):
    return {
        "X-WindOps-Test-Principal": "synthetic-graph-reader",
        "X-WindOps-Test-Role": "maintenance_reviewer",
        "X-WindOps-Test-Turbine-Ids": "WT-023",
        "X-WindOps-Test-Data-Scopes": "structural,knowledge",
        "X-WindOps-Test-Allow-Global": "true",
        **overrides,
    }


def assert_connected(data):
    nodes = {n["uid"] for n in data["nodes"]}
    edges = {r["uid"] for r in data["relationships"]}
    assert all(r["sourceUid"] in nodes and r["targetUid"] in nodes for r in data["relationships"])
    assert all(
        set(p["nodeUids"]) <= nodes and set(p["relationshipUids"]) <= edges for p in data["paths"]
    )


async def approved_graph_claim(app, client, *, knowledge=False):
    payload, _ = await claim_input(app, client, knowledge=knowledge)
    claim = await create(client, payload)
    approved = await review(client, claim)
    assert approved.status_code == 200, approved.text
    claim = approved.json()
    snapshot = await rebuild(app)
    visible = await graph(client, claim["id"])
    assert visible.status_code == 200, visible.text
    return claim, snapshot


async def test_summary_projection_keeps_real_identities_and_statement_boundary(app, client):
    payload, _ = await claim_input(app, client)
    claim = await create(client, payload)
    pending = await rebuild(app)
    assert not any(n.node_type is NodeType.ENGINEERING_CLAIM for n in pending.nodes)
    assert (await graph(client, claim["id"])).status_code == 404
    approved = await review(client, claim)
    assert approved.status_code == 200, approved.text
    snapshot = await rebuild(app)
    typed = {kind: [n for n in snapshot.nodes if n.node_type is kind] for kind in NodeType}
    assert len(typed[NodeType.TOWER_COMPONENT]) == 1
    assert len(typed[NodeType.SENSOR_CHANNEL]) == 2
    assert len(typed[NodeType.WAVEFORM_RECORD]) == len(typed[NodeType.STRUCTURAL_ANALYSIS_RUN]) == 1
    assert len(typed[NodeType.MODAL_OBSERVATION]) >= 1
    run = typed[NodeType.STRUCTURAL_ANALYSIS_RUN][0]
    record = typed[NodeType.WAVEFORM_RECORD][0]
    modal = typed[NodeType.MODAL_OBSERVATION][0]
    statement = typed[NodeType.ENGINEERING_CLAIM][0]
    assert run.properties["status"] == "succeeded"
    assert run.properties["method"] == "pyoma2_fdd_v1"
    assert len(run.properties["resultSha256"]) == 64
    assert json.loads(run.properties["algorithmIdentityJson"])["adapter_sha256"]
    assert len(record.properties["artifactSha256"]) == 64
    assert record.properties["sampleCount"] == 4096
    assert modal.properties["frequencyHz"] == pytest.approx(0.5)
    assert modal.properties["unit"] == "Hz" and modal.properties["dampingRatio"] is None
    assert modal.properties["absolutePrestressAvailable"] is False
    assert statement.properties["recordSemantics"] == "reviewed_engineering_statement"
    assert statement.properties["revision"] == 2
    assert statement.properties["contentSha256"] == approved.json()["content_sha256"]
    assert statement.properties["authorizesWork"] is False
    assert statement.properties["fieldQualification"] == "unverified"
    assert all(
        "samples" not in n.properties and "spectrum" not in n.properties for n in snapshot.nodes
    )
    edge_types = {r.relationship_type.value for r in snapshot.relationships}
    assert {
        "HAS_COMPONENT",
        "MONITORED_BY",
        "HAS_ANALYSIS",
        "HAS_OBSERVATION",
        "HAS_CLAIM",
    } <= edge_types
    support = [
        r
        for r in snapshot.relationships
        if r.source_uid == statement.uid and r.relationship_type.value == "SUPPORTED_BY"
    ]
    assert len(support) == 1 and support[0].target_uid == modal.uid
    assert support[0].properties["relationshipSemantics"] == "human_reviewed_reference"
    response = await graph(client, claim["id"])
    assert response.status_code == 200, response.text
    assert_connected(response.json()["data"])
    # An internal ungoverned read cannot consume the statement even when the raw
    # stored projection contains it for reconciliation/reconstruction.
    with pytest.raises(NotFoundError):
        await KnowledgeGraphService(app.state.knowledge_graph_store).subgraph(claim["id"], depth=1)


@pytest.mark.parametrize("mutation", ["withdraw", "expire", "content", "calibration", "raw_bytes"])
async def test_stale_graph_withholds_changed_claim_without_waiting_for_rebuild(
    app, client, mutation
):
    claim, snapshot = await approved_graph_claim(app, client)
    if mutation == "withdraw":
        assert (await review(client, claim, action="withdraw")).status_code == 200
    elif mutation == "raw_bytes":
        source = claim["evidence_cards"][0]["source"]
        app.state.artifact_verifier.register_object(
            source["artifact_uri"], b"{}", "application/json"
        )
    else:
        async with app.state.session_factory() as session, session.begin():
            row = await session.get(EngineeringClaim, claim["id"])
            if mutation == "expire":
                row.created_at = datetime.now(UTC) - timedelta(days=1)
                row.valid_until = datetime.now(UTC) - timedelta(seconds=1)
            elif mutation == "content":
                row.conclusion += " changed after approval"
            else:
                sensor = await session.scalar(select(SensorChannel).limit(1))
                sensor.calibration_version = "synthetic-changed-after-review"
    response = await graph(client, claim["id"])
    assert response.status_code == 404, response.text
    asset = await graph(client, claim["component_id"])
    assert asset.status_code == 200, asset.text
    assert not any(n["type"] == "EngineeringClaim" for n in asset.json()["data"]["nodes"])
    assert any(n["type"] == "SensorChannel" for n in asset.json()["data"]["nodes"])
    assert_connected(asset.json()["data"])
    assert await app.state.knowledge_graph_store.snapshot(snapshot.projection_id) is snapshot


async def test_mixed_claim_requires_current_source_grants_and_cannot_leak_paths(app, client):
    claim, _ = await approved_graph_claim(app, client, knowledge=True)
    visible = await graph(client, claim["id"], headers=scoped_headers())
    assert visible.status_code == 200, visible.text
    for overrides in (
        {"X-WindOps-Test-Data-Scopes": "structural"},
        {"X-WindOps-Test-Turbine-Ids": "WT-999"},
        {"X-WindOps-Test-Data-Scopes": "knowledge"},
    ):
        response = await graph(client, claim["id"], headers=scoped_headers(**overrides))
        assert response.status_code == 404, response.text
        assert claim["conclusion"] not in response.text
    source_id = claim["evidence_cards"][0]["reference"]["source_id"]
    search = await client.get(
        "/api/v1/knowledge-graph/search",
        params={"query": "Record direct force with valid calibration"},
        headers=scoped_headers(),
    )
    assert search.status_code == 200, search.text
    match = next(m for m in search.json()["data"]["matches"] if m.get("passage_id") == source_id)
    assert claim["id"] in match["graphExpansion"]["engineeringClaimIds"]
    assert (
        match["graphExpansion"]["engineeringClaimSemantics"]
        == "reviewed_statements_not_measurement_facts"
    )


@pytest.mark.parametrize("mutation", ["withdraw", "source_change", "content_change"])
async def test_verification_failure_is_unavailable_and_concurrent_changes_fence_read(
    app, client, monkeypatch, mutation
):
    claim, _ = await approved_graph_claim(app, client)
    verifier = app.state.artifact_verifier
    original = verifier.read_verified_object

    async def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic object service unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(verifier, "read_verified_object", unavailable)
        assert (await graph(client, claim["id"])).status_code == 503

    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()

    with monkeypatch.context() as patch:
        patch.setattr(verifier, "read_verified_object", stalled)
        patch.setattr(structural_access, "GRAPH_CLAIM_READ_TIMEOUT_SECONDS", 0.05)
        assert (await graph(client, claim["id"])).status_code == 503
    started, released = asyncio.Event(), asyncio.Event()

    async def pending(*args, **kwargs):
        started.set()
        await released.wait()
        return await original(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(verifier, "read_verified_object", pending)
        task = asyncio.create_task(graph(client, claim["id"]))
        try:
            await asyncio.wait_for(started.wait(), timeout=10)
            async with app.state.session_factory() as session, session.begin():
                if mutation == "withdraw":
                    await session.execute(
                        update(EngineeringClaim)
                        .where(EngineeringClaim.id == claim["id"])
                        .values(review_status="withdrawn", revision=claim["revision"] + 1)
                    )
                elif mutation == "content_change":
                    await session.execute(
                        update(EngineeringClaim)
                        .where(EngineeringClaim.id == claim["id"])
                        .values(
                            conclusion="Synthetic content changed during original-byte verification"
                        )
                    )
                else:
                    await session.execute(
                        update(SensorChannel).values(
                            calibration_version="synthetic-drift-during-read"
                        )
                    )
        finally:
            released.set()
        response = await asyncio.wait_for(task, timeout=10)
        assert response.status_code == 404, response.text


def test_exact_claim_proof_and_component_grants_filter_relationship_endpoints():
    component = GraphNode(
        graph_uid(NodeType.TOWER_COMPONENT, "component-1"),
        NodeType.TOWER_COMPONENT,
        "component-1",
        {"turbineId": "WT-023", "componentId": "component-1"},
    )
    claim = GraphNode(
        graph_uid(NodeType.ENGINEERING_CLAIM, "claim-1"),
        NodeType.ENGINEERING_CLAIM,
        "claim-1",
        {"turbineId": "WT-023", "componentId": "component-1", "readIdentity": "claim-1:2:hash"},
    )
    policy = GraphAccessPolicy.from_values(entity_ids=["component-1"], data_scopes=["*"])
    assert policy.allows(component)
    assert not policy.allows(
        replace(
            component,
            properties={"turbineId": "WT-023", "componentId": "component-2"},
            entity_id="component-2",
        )
    )
    assert not policy.allows(claim)
    assert not GraphAccessPolicy(unrestricted=True).allows(claim)
    assert not replace(policy, validated_claim_identities=frozenset({"claim-1:1:hash"})).allows(
        claim
    )
    assert replace(policy, validated_claim_identities=frozenset({"claim-1:2:hash"})).allows(claim)


async def test_structural_event_and_projection_request_commit_or_rollback_together(app, client):
    async with app.state.session_factory() as session:
        before = await session.scalar(select(func.count()).select_from(OutboxEvent))
        append_domain_event(
            session,
            event_type="structural.synthetic.rollback",
            aggregate_type="synthetic",
            aggregate_id="rollback",
            payload={"source_kind": "synthetic_test"},
        )
        await session.flush()
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == before + 1
        await session.rollback()
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == before
    payload = {
        "turbine_id": "WT-023",
        "code": "SYNTHETIC-GRAPH-C1",
        "name": "Synthetic graph component",
        "component_type": "concrete_segment",
        "revision": "test-r1",
        "design_reference": "Synthetic test only",
    }
    key = str(uuid4())
    result = await post(client, "tower-components", payload, key)
    assert result.status_code == 201, result.text
    component = result.json()
    replay = await post(client, "tower-components", payload, key)
    assert replay.status_code == 201 and replay.json() == component
    assert replay.headers["Idempotency-Replayed"] == "true"
    async with app.state.session_factory() as session:
        events = (
            await session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == "WT-023",
                    OutboxEvent.event_type == "knowledge-graph.projection.requested",
                    OutboxEvent.payload["reason"].as_string() == "structural.identity.created",
                )
            )
        ).all()
        assert len(events) == 1
        event_id = events[0].id
    assert await process_knowledge_graph_projection_event(
        app.state.session_factory, event_id, app.state.knowledge_graph_store
    )
    assert not await process_knowledge_graph_projection_event(
        app.state.session_factory, event_id, app.state.knowledge_graph_store
    )
    assert (await graph(client, component["id"])).status_code == 200


async def test_actual_field_and_followup_history_links_to_each_independent_assessment(app, client):
    # Run the existing full synthetic business loop unchanged, then examine its
    # actual persisted rows and derived graph. No fabricated review rows are used.
    await _followup(app, client)
    snapshot = await rebuild(app)
    nodes = {n.uid: n for n in snapshot.nodes}
    async with app.state.session_factory() as session:
        evidence = (await session.scalars(select(FieldTaskEvidence))).all()
        handoffs = (await session.scalars(select(StructuralRetestHandoff))).all()
        reviews = (await session.scalars(select(StructuralHealthReview))).all()
    measured = [e for e in evidence if e.measurement.get("retest_source_id")]
    assert len(measured) == len(handoffs) == 1 and len(reviews) == 2
    for row in [*measured, *handoffs]:
        node = nodes[graph_uid(NodeType.FIELD_MEASUREMENT, row.id)]
        assert node.properties["artifactSha256"] == row.artifact_sha256
        assert node.properties["verifiedBy"] == row.verified_by
        assert any(
            r.target_uid == node.uid and r.relationship_type.value == "HAS_MEASUREMENT"
            for r in snapshot.relationships
        )
    followup_node = nodes[graph_uid(NodeType.FIELD_MEASUREMENT, handoffs[0].id)]
    assert followup_node.properties["measurementStage"] == "followup"
    assert any(
        r.source_uid == followup_node.uid
        and r.target_uid == graph_uid(NodeType.CLOSURE_ASSESSMENT, handoffs[0].health_review_id)
        and r.relationship_type.value == "FOLLOWUP_TO"
        for r in snapshot.relationships
    )
    for row in reviews:
        node = nodes[graph_uid(NodeType.CLOSURE_ASSESSMENT, row.id)]
        assert json.loads(node.properties["assessmentJson"]) == row.assessment
        assert any(
            r.target_uid == node.uid and r.relationship_type.value == "ASSESSED_BY"
            for r in snapshot.relationships
        )
    force_nodes = [n for n in snapshot.nodes if n.node_type is NodeType.PRESTRESS_OBSERVATION]
    assert force_nodes and all(
        n.properties["unit"] == "kN" and n.properties["method"] == "direct_force"
        for n in force_nodes
    )
    assert not any(
        n.node_type is NodeType.KNOWLEDGE_CASE
        and n.properties.get("workOrderId") == handoffs[0].work_order_id
        for n in snapshot.nodes
    )
    async with app.state.session_factory() as session:
        event_count = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(
                OutboxEvent.aggregate_id == handoffs[0].work_order_id,
                OutboxEvent.event_type == "knowledge-graph.projection.requested",
                OutboxEvent.payload["reason"].as_string() == "structural.health.reviewed",
            )
        )
        assert event_count == 2


async def test_exhausted_analysis_worker_publishes_its_terminal_state_transactionally(app, client):
    await _exhausted(app, client)
    async with app.state.session_factory() as session:
        events = (
            await session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == "knowledge-graph.projection.requested",
                    OutboxEvent.payload["reason"].as_string() == "structural.analysis.failed",
                )
            )
        ).all()
        assert len(events) == 1
        event_id = events[0].id
    assert await process_knowledge_graph_projection_event(
        app.state.session_factory, event_id, app.state.knowledge_graph_store
    )
    snapshot = await app.state.knowledge_graph_store.snapshot("windops-operational-knowledge-v1")
    runs = [node for node in snapshot.nodes if node.node_type is NodeType.STRUCTURAL_ANALYSIS_RUN]
    assert len(runs) == 1
    assert runs[0].properties["status"] == "failed"
    assert runs[0].properties["errorCode"] == "StructuralAttemptsExhausted"
    assert runs[0].properties["resultSha256"] is None
