from __future__ import annotations

import gc
import tracemalloc
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from windops_backend.knowledge_graph.domain import NodeType
from windops_backend.knowledge_graph.projection import (
    ProjectionLimitExceeded,
    ProjectionLimits,
    build_knowledge_graph_snapshot,
)
from windops_backend.knowledge_graph.service import KnowledgeGraphService
from windops_backend.knowledge_graph.store import (
    InMemoryKnowledgeGraphStore,
    Neo4jKnowledgeGraphStore,
)
from windops_backend.models import (
    Alarm,
    Approval,
    Evidence,
    IngestReceipt,
    KnowledgeCase,
    KnowledgeDocument,
    Mission,
    Resource,
    ResourceReservation,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.storage import OutboxEvent


def anomaly_sample(event_id: str = "SCADA-WT023-GRAPH-001") -> dict[str, Any]:
    return {
        "samples": [
            {
                "source_event_id": event_id,
                "turbine_id": "WT-023",
                "observed_at": "2026-08-13T02:14:03Z",
                "variable": "main_bearing_vibration_rms",
                "value": 4.81,
                "unit": "mm/s",
                "quality": "good",
                "attributes": {
                    "baseline": 3.79,
                    "anomaly_score": 0.86,
                    "temperature_delta_c": 8.4,
                },
            }
        ]
    }


def valid_field_measurements() -> list[dict[str, Any]]:
    return [
        {"lubrication_condition": "acceptable", "water_content_ppm": 120.0},
        {"vibration_rms_mm_s": 3.8, "bpfo_band_energy_pct": 4.2},
        {"bearing_temperature_c": 68.4},
        {"defect_severity": "minor", "spall_area_mm2": 1.2},
        {
            "photo_count": 5,
            "main_bearing_health_score": 78,
            "turbine_health_score": 82,
        },
    ]


@pytest.mark.asyncio
async def test_projection_batches_sources_and_fails_before_atomic_replace_on_budget(
    app: FastAPI,
) -> None:
    store = app.state.knowledge_graph_store
    before = await store.summary("windops-operational-knowledge-v1")
    async with app.state.session_factory() as session:
        batched = await build_knowledge_graph_snapshot(
            session,
            limits=ProjectionLimits(batch_size=1, max_source_rows=10_000),
        )
        assert batched.nodes
        with pytest.raises(ProjectionLimitExceeded, match="source-row budget"):
            await KnowledgeGraphService(
                store,
                limits=ProjectionLimits(batch_size=1, max_source_rows=1),
            ).rebuild(session)
    after = await store.summary("windops-operational-knowledge-v1")
    assert after.source_revision == before.source_revision


@pytest.mark.asyncio
async def test_projection_streams_rows_and_enforces_source_bytes_before_replace(
    app: FastAPI,
) -> None:
    store = app.state.knowledge_graph_store
    before = await store.summary("windops-operational-knowledge-v1")
    async with app.state.session_factory() as session, session.begin():
        session.add(
            KnowledgeDocument(
                id="KB-GRAPH-BUDGET-001",
                tenant_id="tenant-east-china",
                wind_farm_id="WF-001",
                turbine_id="WT-023",
                title="Large projection budget fixture",
                document_type="engineering-note",
                body="large-source-payload " * 20_000,
                citation_uri="windops://knowledge/documents/KB-GRAPH-BUDGET-001",
            )
        )

    async with app.state.session_factory() as session:
        with pytest.raises(ProjectionLimitExceeded, match="source-byte budget"):
            await KnowledgeGraphService(
                store,
                limits=ProjectionLimits(
                    batch_size=1,
                    max_source_rows=10_000,
                    max_source_bytes=32 * 1024,
                ),
            ).rebuild(session)
    after = await store.summary("windops-operational-knowledge-v1")
    assert after.source_revision == before.source_revision


@pytest.mark.asyncio
async def test_projection_memory_limit_bounds_production_shaped_peak_before_replace(
    app: FastAPI,
    record_testsuite_property: Callable[[str, object], None],
) -> None:
    entity_count = 250
    evidence_per_mission = 4
    tasks_per_work_order = 3
    reservations_per_mission = 2
    now = datetime.now(UTC)
    async with app.state.session_factory() as session, session.begin():
        resources = [
            Resource(
                id=f"MEM-RESOURCE-{index:03d}",
                resource_type="spare_part" if index % 2 == 0 else "crew",
                name=f"Projection stress resource {index}",
                quantity=10_000,
                status="available",
                attributes={"supplier": "controlled-memory-fixture", "revision": index},
            )
            for index in range(20)
        ]
        session.add_all(resources)
        for index in range(entity_count):
            suffix = f"{index:05d}"
            receipt_id = f"MEM-EVENT-{suffix}"
            alarm_id = f"MEM-ALARM-{suffix}"
            mission_id = f"MEM-MISSION-{suffix}"
            approval_id = f"MEM-APPROVAL-{suffix}"
            work_order_id = f"MEM-WO-{suffix}"
            session.add_all(
                [
                    IngestReceipt(
                        source_event_id=receipt_id,
                        source_id="scada-default",
                        payload_hash=f"{index:064x}",
                        disposition="accepted",
                    ),
                    Alarm(
                        id=alarm_id,
                        turbine_id="WT-023",
                        source_event_id=receipt_id,
                        code="MEMORY_STRESS",
                        subsystem="main_bearing",
                        title=f"Production-shaped memory stress alarm {index}",
                        severity="major",
                        status="open",
                        ai_status="completed",
                        triggered_at=now,
                        evidence={"samples": [index, index + 1], "shape": "production"},
                    ),
                    Mission(
                        id=mission_id,
                        alarm_id=alarm_id,
                        turbine_id="WT-023",
                        title=f"Production-shaped projection mission {index}",
                        status="approved",
                        revision=2,
                        public_state={
                            "diagnosis": {
                                "failure_mode": f"bearing_mode_{index % 7}",
                                "severity": "major",
                                "confidence": 0.91,
                            }
                        },
                    ),
                    Approval(
                        id=approval_id,
                        mission_id=mission_id,
                        mission_revision=1,
                        action="approve",
                        approver="memory-stress-operator",
                        reason="Bounded projection stress fixture",
                    ),
                    WorkOrder(
                        id=work_order_id,
                        mission_id=mission_id,
                        approval_id=approval_id,
                        turbine_id="WT-023",
                        title=f"Projection stress work order {index}",
                        selected_alternative_id="inspect",
                        selected_action="Inspect and document the affected subsystem.",
                        status="in_progress",
                        safety_plan={"controls": ["isolation", "permit"]},
                        closure_policy={"requiredEvidence": tasks_per_work_order},
                    ),
                    KnowledgeCase(
                        id=f"MEM-CASE-{suffix}",
                        mission_id=mission_id,
                        work_order_id=work_order_id,
                        turbine_id="WT-023",
                        title=f"Projection stress knowledge case {index}",
                        diagnosis={"confidence": 0.91, "mode": index % 7},
                        resolution={"outcome": "controlled", "revision": index},
                    ),
                ]
            )
            session.add_all(
                [
                    Evidence(
                        id=f"MEM-EVIDENCE-{suffix}-{evidence_index}",
                        mission_id=mission_id,
                        source_key=f"memory-source-{evidence_index}",
                        evidence_type="sensor-analysis",
                        summary=(
                            f"Production-shaped supporting evidence {evidence_index} "
                            f"for mission {mission_id}."
                        ),
                        source_refs=[receipt_id, f"sensor-{evidence_index}"],
                        metrics={
                            "stance": "supporting",
                            "confidence": 0.8 + evidence_index / 100,
                            "samples": list(range(12)),
                        },
                        citation_uri="windops://knowledge/documents/KB-MB-GW165-001",
                        retrieval_method="production-shaped-memory-test",
                    )
                    for evidence_index in range(evidence_per_mission)
                ]
            )
            session.add_all(
                [
                    WorkOrderTask(
                        id=f"MEM-TASK-{suffix}-{task_index}",
                        work_order_id=work_order_id,
                        sequence=task_index + 1,
                        title=f"Projection stress task {task_index + 1}",
                        schema_version="memory-test-v1",
                        measurement_schema={
                            "type": "object",
                            "properties": {"value": {"type": "number"}},
                        },
                        status="pending",
                    )
                    for task_index in range(tasks_per_work_order)
                ]
            )
            session.add_all(
                [
                    ResourceReservation(
                        id=f"MEM-RESERVATION-{suffix}-{reservation_index}",
                        mission_id=mission_id,
                        resource_id=(f"MEM-RESOURCE-{(index + reservation_index) % 20:03d}"),
                        quantity=reservation_index + 1,
                    )
                    for reservation_index in range(reservations_per_mission)
                ]
            )

    resources.clear()
    del resources
    gc.collect()
    limits = ProjectionLimits(
        batch_size=50,
        max_source_rows=25_000,
        max_nodes=20_000,
        max_relationships=40_000,
        max_source_bytes=64 * 1024 * 1024,
        max_graph_bytes=32 * 1024 * 1024,
        max_estimated_memory_bytes=32 * 1024 * 1024,
        max_runtime_seconds=120,
    )
    tracemalloc.start(1)
    baseline_current, _baseline_peak = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    try:
        async with app.state.session_factory() as session:
            snapshot = await build_knowledge_graph_snapshot(session, limits=limits)
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    peak_increment = max(current, peak) - baseline_current
    record_testsuite_property("knowledge_graph_python_peak_bytes", peak_increment)
    record_testsuite_property(
        "knowledge_graph_memory_limit_bytes",
        limits.max_estimated_memory_bytes,
    )
    record_testsuite_property("knowledge_graph_stress_primary_entities", entity_count)
    assert peak_increment <= int(limits.max_estimated_memory_bytes * 0.90)
    assert {
        "Mission",
        "Evidence",
        "WorkOrder",
        "Procedure",
        "Part",
        "Resource",
        "KnowledgeCase",
    } <= {node.node_type.value for node in snapshot.nodes}

    store = app.state.knowledge_graph_store
    before = await store.summary("windops-operational-knowledge-v1")
    for _attempt in range(2):
        async with app.state.session_factory() as session:
            with pytest.raises(ProjectionLimitExceeded, match="memory budget"):
                await KnowledgeGraphService(
                    store,
                    limits=ProjectionLimits(
                        batch_size=50,
                        max_source_rows=25_000,
                        max_estimated_memory_bytes=128 * 1024,
                    ),
                ).rebuild(session)
    after = await store.summary("windops-operational-knowledge-v1")
    assert after.source_revision == before.source_revision


@pytest.mark.asyncio
async def test_seeded_graph_is_a_rebuildable_database_projection(
    client: httpx.AsyncClient,
) -> None:
    ready = await client.get("/api/v1/readyz")
    assert ready.json() == {
        "status": "ready",
        "knowledge_graph": "memory-test-double",
    }
    response = await client.get("/api/v1/knowledge-graph/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {
        "authoritativeSource": "postgresql",
        "projectionBackend": "memory-test-double",
        "consistency": "eventually-consistent-rebuildable-projection",
    }
    summary = body["data"]
    assert summary["sourceRevision"]
    assert summary["nodeTypeCounts"]["WindFarm"] == 1
    assert summary["nodeTypeCounts"]["Turbine"] == 1
    assert summary["nodeTypeCounts"]["KnowledgeDocument"] == 1
    assert summary["nodeTypeCounts"]["KnowledgePassage"] == 1
    assert summary["relationshipCount"] > 0


@pytest.mark.asyncio
async def test_alarm_workflow_updates_fault_trace_and_reconciles(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    ingested = await client.post("/api/v1/scada/ingest", json=anomaly_sample())
    assert ingested.status_code == 202
    result = ingested.json()["results"][0]
    alarm_id = result["alarm_id"]
    mission_id = result["mission_id"]
    assert alarm_id and mission_id

    trace = await client.get("/api/v1/knowledge-graph/turbines/WT-023/fault-trace")
    assert trace.status_code == 200
    trace_data = trace.json()["data"]
    node_types = {node["type"] for node in trace_data["nodes"]}
    relationship_types = {relationship["type"] for relationship in trace_data["relationships"]}
    assert {"Turbine", "Subsystem", "Alarm", "Anomaly", "Mission", "FailureMode"} <= (node_types)
    assert {"AFFECTS", "TRIGGERED", "INDICATES"} <= relationship_types

    impact = await client.get(f"/api/v1/knowledge-graph/alarms/{alarm_id}/impact")
    assert impact.status_code == 200
    assert any(node["entityId"] == mission_id for node in impact.json()["data"]["nodes"])

    reconciliation = await client.get("/api/v1/knowledge-graph/reconcile")
    assert reconciliation.status_code == 200
    assert reconciliation.json()["data"]["consistent"] is True

    search = await client.get(
        "/api/v1/knowledge-graph/search",
        params={
            "query": "main bearing rising RMS temperature inspection",
            "entityId": "WT-023",
        },
    )
    assert search.status_code == 200
    search_data = search.json()["data"]
    assert search_data["matches"]
    top_match = search_data["matches"][0]
    assert top_match["retrieval_method"] == "deterministic_test_cosine"
    assert top_match["scopeMatched"] is True
    assert top_match["graphExpansion"]["failureModeIds"]
    assert top_match["graphExpansion"]["paths"]
    assert search_data["retrieval"]["vector"] == ["deterministic_test_cosine"]
    assert search_data["retrieval"]["fusion"].startswith("0.70*vectorScore")

    support = await client.get("/api/v1/knowledge-graph/passages/KB-MB-GW165-001%23body/support")
    assert support.status_code == 200
    support_analysis = support.json()["data"]["supportAnalysis"]
    assert support_analysis["diagnosisIds"] == ["early_main_bearing_degradation"]
    assert len(support_analysis["supportingEvidenceIds"]) >= 1
    assert support_analysis["hasContradictingEvidence"] is False

    observability = await client.get("/api/v1/knowledge-graph/observability")
    assert observability.status_code == 200
    metrics = observability.json()["data"]
    assert metrics["outboxStatusCounts"]["succeeded"] >= 1
    assert metrics["unsupportedFailureModeCount"] == 0
    assert metrics["graphReadLatencyMs"] >= 0

    async with app.state.session_factory() as session:
        snapshot = await build_knowledge_graph_snapshot(session)
        assert len(snapshot.nodes) == len({node.uid for node in snapshot.nodes})
        assert len(snapshot.relationships) == len(
            {relationship.uid for relationship in snapshot.relationships}
        )
        assert all(node.node_type.value != "ScadaSample" for node in snapshot.nodes)
        graph_events = (
            await session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == "knowledge-graph.projection.requested"
                )
            )
        ).all()
        assert graph_events
        assert all(event.status == "succeeded" for event in graph_events)


@pytest.mark.asyncio
async def test_operator_rebuild_is_idempotent(client: httpx.AsyncClient) -> None:
    reindexed = await client.post(
        "/api/v1/knowledge-graph/reindex",
        headers={"Idempotency-Key": "graph-reindex-operator-001"},
    )
    assert reindexed.status_code == 202
    index_result = reindexed.json()["data"]["index"]
    assert index_result["document_count"] >= 1
    assert index_result["embedding_provider"] == "deterministic_test"

    before = (await client.get("/api/v1/knowledge-graph/summary")).json()["data"]
    rebuilt = await client.post(
        "/api/v1/knowledge-graph/rebuild",
        headers={"Idempotency-Key": "graph-rebuild-operator-001"},
    )
    assert rebuilt.status_code == 202
    rebuilt_body = rebuilt.json()
    assert rebuilt_body["status"] == "succeeded"
    assert rebuilt_body["data"]["sourceRevision"] == before["sourceRevision"]
    after = (await client.get("/api/v1/knowledge-graph/summary")).json()["data"]
    assert after["nodeCount"] == before["nodeCount"]
    assert after["relationshipCount"] == before["relationshipCount"]


@pytest.mark.asyncio
async def test_passage_support_distinguishes_contradicting_evidence(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    ingested = await client.post(
        "/api/v1/scada/ingest", json=anomaly_sample("SCADA-WT023-GRAPH-CONTRA-001")
    )
    mission_id = ingested.json()["results"][0]["mission_id"]
    async with app.state.session_factory() as session:
        session.add(
            Evidence(
                id="EV-GRAPH-CONTRADICT-001",
                mission_id=mission_id,
                source_key="graph-contradicting-evidence",
                evidence_type="engineering-review",
                summary="Independent oil analysis does not support lubricant degradation.",
                source_refs=["LAB-OIL-REVIEW-001"],
                metrics={"stance": "contradicting"},
                citation_uri="windops://knowledge/documents/KB-MB-GW165-001",
                retrieval_method="controlled-engineering-review",
            )
        )
        await session.commit()
    rebuilt = await client.post(
        "/api/v1/knowledge-graph/rebuild",
        headers={"Idempotency-Key": "graph-rebuild-contradiction-001"},
    )
    assert rebuilt.status_code == 202
    support = await client.get("/api/v1/knowledge-graph/passages/KB-MB-GW165-001%23body/support")
    analysis = support.json()["data"]["supportAnalysis"]
    assert "EV-GRAPH-CONTRADICT-001" in analysis["contradictingEvidenceIds"]
    assert analysis["hasContradictingEvidence"] is True


@pytest.mark.asyncio
async def test_closed_workflow_projects_case_resources_and_stable_acceptance_paths(
    client: httpx.AsyncClient,
) -> None:
    ingested = await client.post(
        "/api/v1/scada/ingest", json=anomaly_sample("SCADA-WT023-GRAPH-CLOSED-001")
    )
    result = ingested.json()["results"][0]
    alarm_id = result["alarm_id"]
    mission_id = result["mission_id"]
    mission = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    approved = await client.post(
        f"/api/v1/missions/{mission_id}/approvals",
        headers={"Idempotency-Key": "graph-mission-approval-001"},
        json={
            "action": "approve",
            "expected_revision": mission["revision"],
            "reason": "Graph acceptance test approval",
            "comment": "Execute the controlled inspection package.",
        },
    )
    assert approved.status_code == 200
    work_order_id = approved.json()["work_order_id"]
    work_order = (await client.get(f"/api/v1/work-orders/{work_order_id}")).json()
    for index, task in enumerate(work_order["tasks"], start=1):
        completed = await client.post(
            f"/api/v1/work-orders/{work_order_id}/tasks/{task['task_id']}/complete",
            headers={"Idempotency-Key": f"graph-task-complete-{index:03d}"},
            json={
                "result": f"Graph acceptance task {index} completed.",
                "artifact_uri": f"minio://test/field-task-{index}.json",
                "artifact_sha256": f"{index:064x}",
                "measurement": valid_field_measurements()[index - 1],
            },
        )
        assert completed.status_code == 200

    impact_before = (await client.get(f"/api/v1/knowledge-graph/alarms/{alarm_id}/impact")).json()[
        "data"
    ]
    impact_types = {node["type"] for node in impact_before["nodes"]}
    assert {"WorkOrder", "Procedure", "Part", "Resource", "KnowledgeCase"} <= impact_types
    failure_mode = next(
        node["entityId"] for node in impact_before["nodes"] if node["type"] == "FailureMode"
    )
    similar = (
        await client.get(f"/api/v1/knowledge-graph/failure-modes/{failure_mode}/similar-cases")
    ).json()["data"]
    assert any(node["type"] == "KnowledgeCase" for node in similar["nodes"])
    assert any(relationship["type"] == "SIMILAR_TO" for relationship in similar["relationships"])
    assert any(relationship["type"] == "RESOLVED_BY" for relationship in similar["relationships"])

    before_node_uids = {node["uid"] for node in impact_before["nodes"]}
    before_relationship_uids = {
        relationship["uid"] for relationship in impact_before["relationships"]
    }
    rebuilt = await client.post(
        "/api/v1/knowledge-graph/rebuild",
        headers={"Idempotency-Key": "graph-rebuild-stability-001"},
    )
    assert rebuilt.status_code == 202
    impact_after = (await client.get(f"/api/v1/knowledge-graph/alarms/{alarm_id}/impact")).json()[
        "data"
    ]
    assert {node["uid"] for node in impact_after["nodes"]} == before_node_uids
    assert {
        relationship["uid"] for relationship in impact_after["relationships"]
    } == before_relationship_uids


@pytest.mark.asyncio
async def test_neo4j_projection_writer_uses_constrained_typed_batches(
    app: FastAPI,
) -> None:
    class FakeResult:
        async def consume(self) -> None:
            return None

        async def single(self) -> dict[str, str]:
            return {"previous_sequence": ""}

    class FakeTransaction:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        async def run(self, query: str, **parameters: object) -> FakeResult:
            self.calls.append((query, parameters))
            return FakeResult()

    async with app.state.session_factory() as session:
        snapshot = await build_knowledge_graph_snapshot(session)
    transaction = FakeTransaction()
    await Neo4jKnowledgeGraphStore._ensure_schema(transaction)
    await Neo4jKnowledgeGraphStore._replace_transaction(
        transaction,
        snapshot,
        write_batch_size=2,
    )

    queries = "\n".join(query for query, _parameters in transaction.calls)
    assert "CREATE CONSTRAINT windops_knowledge_uid IF NOT EXISTS" in queries
    assert "CREATE CONSTRAINT windops_graph_projection_id IF NOT EXISTS" in queries
    assert "projectionWriteLock" in queries
    assert "DETACH DELETE" in queries
    assert "WindOpsKnowledge:Turbine" in queries
    assert "WindOpsKnowledge:KnowledgePassage" in queries
    assert "WindOpsGraphProjection" in queries
    write_batches = [
        parameters["rows"] for query, parameters in transaction.calls if "UNWIND $rows" in query
    ]
    assert write_batches
    assert all(len(rows) <= 2 for rows in write_batches)
    assert all(node.node_type.value in {item.value for item in NodeType} for node in snapshot.nodes)


@pytest.mark.asyncio
async def test_projection_sequence_fences_a_stale_external_writer(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        older = await build_knowledge_graph_snapshot(
            session, projection_sequence="2026-08-14T01:00:00+00:00:event-a"
        )
        newer = await build_knowledge_graph_snapshot(
            session, projection_sequence="2026-08-14T01:01:00+00:00:event-b"
        )
    store = InMemoryKnowledgeGraphStore()
    await store.replace_projection(newer)
    await store.replace_projection(older)
    summary = await store.summary(newer.projection_id)
    assert summary.projection_sequence == newer.projection_sequence
    assert summary.source_revision == newer.source_revision
