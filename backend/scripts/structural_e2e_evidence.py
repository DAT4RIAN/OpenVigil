"""Exact persisted evidence for the isolated structural browser scenario."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from windops_backend.config import Settings
from windops_backend.knowledge_graph.domain import NodeType
from windops_backend.knowledge_graph.factory import create_knowledge_graph_store
from windops_backend.knowledge_graph.projection import KNOWLEDGE_GRAPH_PROJECTION_ID
from windops_backend.models import (
    Approval,
    EngineeringClaim,
    EngineeringClaimReview,
    HealthBaseline,
    KnowledgeCase,
    Mission,
    ModalObservation,
    PrestressObservation,
    ReadAccessAudit,
    Resource,
    SensorChannel,
    StructuralAnalysisRun,
    StructuralCaseReview,
    StructuralHealthReview,
    TendonAssembly,
    TowerComponent,
    WaveformRecord,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.operations.structural_provenance_evidence import verify_persisted_execution
from windops_backend.storage import FieldTaskEvidence, OutboxEvent
from windops_backend.structural_contract import algorithm_identity
from windops_backend.structural_provenance import deployment_identity


async def seed_structural_equipment(config: dict[str, Any]) -> None:
    engine = create_async_engine(config["database_url"])
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            session.add(
                Resource(
                    id="SYNTHETIC-E2E-KIT",
                    resource_type="measurement_equipment",
                    name="Synthetic software acceptance equipment",
                    quantity=1,
                    status="available",
                )
            )
    finally:
        await engine.dispose()


async def structural_database_evidence(config: dict[str, Any], folder: Path) -> dict[str, Any]:
    settings = Settings(
        **{"_env_file": None, **{k: v for k, v in config.items() if k != "fixture"}}
    )
    browser = json.loads((folder / "structural-browser.json").read_text(encoding="utf-8"))
    modal = browser.get("scenario") == "modal_frequency_review"
    expected = {
        TowerComponent: 1,
        TendonAssembly: 0 if modal else 1,
        SensorChannel: 2 if modal else 3,
        WaveformRecord: 32 if modal else 2,
        StructuralAnalysisRun: 32 if modal else 2,
        ModalObservation: len(browser["modal_ids"]),
        PrestressObservation: 0 if modal else 3,
        Mission: 1,
        Approval: 1,
        WorkOrder: 1,
        WorkOrderTask: 2,
        FieldTaskEvidence: 2,
        StructuralHealthReview: 1,
        KnowledgeCase: 1,
        StructuralCaseReview: 1,
        EngineeringClaim: 1 if modal else 2,
        EngineeringClaimReview: 1 if modal else 3,
    }
    if modal:
        expected[HealthBaseline] = 1
        assert len(set(browser["training_modal_ids"])) == 30
        assert len(set(browser["run_ids"])) == len(set(browser["modal_ids"])) == 32
    engine = create_async_engine(config["database_url"])
    factory = async_sessionmaker(engine)
    try:
        async with factory() as session:
            counts = {
                model.__tablename__: int(
                    await session.scalar(select(func.count()).select_from(model)) or 0
                )
                for model in expected
            }
            if counts != {model.__tablename__: count for model, count in expected.items()}:
                raise RuntimeError(f"Structural persisted counts differ: {counts}")
            mission = await session.get(Mission, browser["mission_id"])
            order = await session.get(WorkOrder, browser["work_order_id"])
            assert mission is not None and mission.status == "completed"
            assert order is not None and order.status == "completed"
            rows = list(await session.scalars(select(StructuralAnalysisRun)))
            assert {row.status for row in rows} == (
                {"succeeded"} if modal else {"succeeded", "insufficient_data"}
            )
            assert {row.id for row in rows} == set(browser["run_ids"])
            identity = algorithm_identity()
            declared = deployment_identity(settings, "api")
            if declared is not None:
                identity["deployment_declared"] = declared
            execution_receipts = [verify_persisted_execution(row, settings) for row in rows]
            for row in rows:
                assert row.algorithm_identity == identity
                assert row.attempts == 1
                event = await session.scalar(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == row.id,
                        OutboxEvent.event_type == "structural.analysis.requested",
                    )
                )
                assert event is not None and event.status == "succeeded"
                assert event.attempts == 1 and event.processed_at is not None
            if not modal:
                bad = next(row for row in rows if row.status == "insufficient_data")
                assert not list(
                    await session.scalars(
                        select(ModalObservation).where(ModalObservation.run_id == bad.id)
                    )
                )
            for _ in range(30):
                audit_count = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ReadAccessAudit)
                        .where(ReadAccessAudit.subject == "business-manager")
                    )
                    or 0
                )
                if audit_count:
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Structural reads were not persisted by the audit worker")
            artifact_rows: tuple[WaveformRecord | PrestressObservation | FieldTaskEvidence, ...] = (
                *list(await session.scalars(select(WaveformRecord))),
                *list(await session.scalars(select(PrestressObservation))),
                *list(await session.scalars(select(FieldTaskEvidence))),
            )
            artifacts = [
                {"uri": row.artifact_uri, "sha256": row.artifact_sha256} for row in artifact_rows
            ]
        raw = {key: value for key, value in config.items() if key != "fixture"}
        store = create_knowledge_graph_store(Settings(**{"_env_file": None, **raw}))
        try:
            for _ in range(60):
                snapshot = await store.snapshot(KNOWLEDGE_GRAPH_PROJECTION_ID)
                if snapshot is not None:
                    nodes = {node.entity_id: node for node in snapshot.nodes}
                    if (
                        browser["case_id"] in nodes
                        and browser["work_order_id"] in nodes
                        and (
                            browser["baseline_id"] in nodes and browser["claim_id"] in nodes
                            if modal
                            else browser["modal_claim_id"] not in nodes
                        )
                    ):
                        break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Actual Neo4j projection never reached the structural closure")
            assert snapshot is not None
            assert nodes[browser["case_id"]].node_type is NodeType.KNOWLEDGE_CASE
            if modal:
                baseline_node = nodes[browser["baseline_id"]]
                assert baseline_node.node_type is NodeType.HEALTH_BASELINE
                assert baseline_node.properties["trainingWindowCount"] == 30
                validation = json.loads(str(baseline_node.properties["validationJson"]))
                assert validation["training_count"] == 24 and validation["validation_count"] == 6
            else:
                assert not any(
                    node.node_type is NodeType.ENGINEERING_CLAIM
                    and node.entity_id == browser["modal_claim_id"]
                    for node in snapshot.nodes
                )
            measurements = [
                node for node in snapshot.nodes if node.node_type is NodeType.FIELD_MEASUREMENT
            ]
            assessments = [
                node for node in snapshot.nodes if node.node_type is NodeType.CLOSURE_ASSESSMENT
            ]
            assert len(measurements) == len(assessments) == 1
            assert measurements[0].properties["verifiedBy"] == "business-field"
            graph_evidence = {
                "backend": "neo4j",
                "source_revision": snapshot.source_revision,
                "nodes": len(snapshot.nodes),
                "relationships": len(snapshot.relationships),
                "field_measurements": len(measurements),
                "closure_assessments": len(assessments),
            }
        finally:
            await store.close()
        return {
            "counts": counts,
            "structural_read_audits": audit_count,
            "algorithm_identity": identity,
            "execution_receipts": execution_receipts,
            "graph": graph_evidence,
            "artifacts": artifacts,
            "browser_receipt_sha256": hashlib.sha256(
                (folder / "structural-browser.json").read_bytes()
            ).hexdigest(),
        }
    finally:
        await engine.dispose()
