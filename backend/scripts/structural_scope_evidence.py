"""Owned synthetic topology, infrastructure challenges and authoritative evidence."""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from windops_backend.access_control import ACCESS_POLICY_SESSION_KEY
from windops_backend.config import Settings
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.knowledge_graph.factory import create_knowledge_graph_store
from windops_backend.knowledge_graph.projection import KNOWLEDGE_GRAPH_PROJECTION_ID
from windops_backend.models import (
    EngineeringClaim,
    EngineeringClaimReview,
    Mission,
    ModalObservation,
    ReadAccessAudit,
    SensorChannel,
    StructuralAnalysisRun,
    TowerComponent,
    WaveformRecord,
    WorkOrder,
)
from windops_backend.operations.structural_provenance_evidence import verify_persisted_execution
from windops_backend.schema_structural import ComponentCreate, SensorCreate
from windops_backend.services.seed import seed_wt023_demo
from windops_backend.services.structural import create_component, create_sensor
from windops_backend.storage import OutboxEvent


async def seed_scope_topology(config: dict[str, Any]) -> dict[str, Any]:
    """Create explicit identity fixtures before the immutable API scope configuration."""
    engine = create_async_engine(config["database_url"])
    try:
        async with async_sessionmaker(engine)() as session:
            # The existing master-data seed owns its commit. The topology below
            # starts a new transaction and commits all identities together.
            await seed_wt023_demo(session)
            components = []
            sensors = []
            now = datetime.now(UTC)
            for index in range(2):
                component = await create_component(
                    session,
                    ComponentCreate(
                        turbine_id="WT-023",
                        code=f"SYNTHETIC-SCOPE-C{index}",
                        name=f"Synthetic scope fixture component {index}",
                        component_type="concrete_segment",
                        revision="synthetic-r1",
                        design_reference="Software authorization fixture; no field qualification",
                    ),
                    "synthetic-scope-fixture",
                )
                components.append(component)
                for sensor_index in range(2 if index == 0 else 1):
                    sensors.append(
                        await create_sensor(
                            session,
                            SensorCreate(
                                turbine_id="WT-023",
                                component_id=component["id"],
                                code=f"SYNTHETIC-SCOPE-A{index}-{sensor_index}",
                                revision="synthetic-r1",
                                quantity="acceleration",
                                unit="m/s2",
                                direction="X",
                                range_min=-10,
                                range_max=10,
                                calibration_version="synthetic-cal1",
                                calibration_at=now - timedelta(days=30),
                                calibration_valid_until=now + timedelta(days=30),
                                calibration_reference="Synthetic software calibration fixture",
                                synchronization_source="synthetic-shared-clock",
                            ),
                            "synthetic-scope-fixture",
                        )
                    )
            await session.commit()
            return {"components": components, "sensors": sensors}
    finally:
        await engine.dispose()


class OwnedInfrastructureChallenges:
    """Accept only explicit operations on this runner's compose project and worker."""

    def __init__(
        self,
        folder: Path,
        docker: list[str],
        project: str,
        stop_worker: Callable[[], None],
        start_worker: Callable[[], None],
    ) -> None:
        self.folder, self.docker, self.project = folder, docker, project
        self.stop_worker, self.start_worker = stop_worker, start_worker
        self.completed: set[str] = set()
        self.paused: set[str] = set()
        self.actions: list[dict[str, str]] = []

    def _container_action(self, service: str, action: str) -> None:
        if service not in {"redis", "minio", "neo4j"} or action not in {"pause", "unpause"}:
            raise ValueError("unsupported infrastructure challenge")
        identity = subprocess.check_output(
            self.docker + ["ps", "--quiet", service], text=True
        ).strip()
        if not identity or "\n" in identity:
            raise ValueError("expected one owned dependency container")
        inspected = json.loads(subprocess.check_output(["docker", "inspect", identity], text=True))[
            0
        ]
        if inspected["Config"]["Labels"].get("com.docker.compose.project") != self.project:
            raise ValueError("refusing to change a container outside the current owned project")
        subprocess.run(["docker", action, identity], check=True, capture_output=True, timeout=30)
        if action == "pause":
            self.paused.add(service)
        else:
            self.paused.discard(service)

    def handle_pending(self) -> None:
        for path in sorted(self.folder.glob("fault-request-*.json")):
            request = json.loads(path.read_text(encoding="utf-8"))
            identity = path.stem.removeprefix("fault-request-")
            if identity in self.completed:
                continue
            if request != {
                "id": identity,
                "service": request.get("service"),
                "action": request.get("action"),
            }:
                raise ValueError("invalid challenge request")
            service, action = request["service"], request["action"]
            if service == "structural-worker":
                if action == "stop":
                    self.stop_worker()
                elif action == "start":
                    self.start_worker()
                else:
                    raise ValueError("unsupported worker challenge")
            else:
                self._container_action(service, action)
            receipt = {"id": identity, "service": service, "action": action, "status": "applied"}
            self.actions.append(receipt)
            self.completed.add(identity)
            target = self.folder / f"fault-response-{identity}.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(receipt), encoding="utf-8")
            temporary.replace(target)

    def restore(self) -> None:
        for service in sorted(self.paused.copy()):
            self._container_action(service, "unpause")


async def scope_database_evidence(config: dict[str, Any], folder: Path) -> dict[str, Any]:
    settings = Settings(
        **{"_env_file": None, **{k: v for k, v in config.items() if k != "fixture"}}
    )
    browser = json.loads((folder / "structural-browser.json").read_text(encoding="utf-8"))
    fixture = json.loads((folder / "scope-fixture.json").read_text(encoding="utf-8"))
    expected = {
        TowerComponent: 2,
        SensorChannel: 3,
        WaveformRecord: 3,
        StructuralAnalysisRun: 2,
        ModalObservation: 2,
        Mission: 1,
        EngineeringClaim: 1,
        EngineeringClaimReview: 1,
        WorkOrder: 0,
    }
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
            assert counts == {model.__tablename__: count for model, count in expected.items()}, (
                counts
            )
            records = list(await session.scalars(select(WaveformRecord)))
            assert {row.id for row in records} == set(browser["record_ids"])
            mixed = next(row for row in records if row.id == browser["mixed_record_id"])
            assert {channel["component_id"] for channel in mixed.channel_snapshot} == {
                row["id"] for row in fixture["components"]
            }
            runs = list(await session.scalars(select(StructuralAnalysisRun)))
            modes = list(await session.scalars(select(ModalObservation.id)))
            execution_receipts = [verify_persisted_execution(run, settings) for run in runs]
            for run in runs:
                assert run.status == "succeeded" and run.attempts == 1
                events = list(
                    await session.scalars(
                        select(OutboxEvent).where(
                            OutboxEvent.event_type == "structural.analysis.requested",
                            OutboxEvent.aggregate_id == run.id,
                        )
                    )
                )
                assert len(events) == 1
                assert events[0].status == "succeeded" and events[0].attempts == 1
                assert events[0].processed_at is not None
            claim = await session.get(EngineeringClaim, browser["claim_id"])
            assert claim is not None and claim.review_status == "approved"
            claim_revision = claim.revision
            artifacts = [
                {"uri": row.artifact_uri, "sha256": row.artifact_sha256} for row in records
            ]
            subjects = [
                "business-manager",
                "business-component",
                "business-sensor",
                "business-restricted",
                "business-knowledge-only",
            ]
            audit_counts = {}
            for subject in subjects:
                for _ in range(30):
                    count = int(
                        await session.scalar(
                            select(func.count())
                            .select_from(ReadAccessAudit)
                            .where(ReadAccessAudit.subject == subject)
                        )
                        or 0
                    )
                    if count:
                        break
                    await asyncio.sleep(0.1)
                assert count > 0, subject
                audit_counts[subject] = count
        scoped = {}
        for subject in ("business-component", "business-sensor"):
            async with factory() as session:
                session.info[ACCESS_POLICY_SESSION_KEY] = GraphAccessPolicy.from_values(
                    **config["identity_scope_mappings"][subject]
                )
                scoped[subject] = {
                    "components": list(await session.scalars(select(TowerComponent.id))),
                    "sensors": list(await session.scalars(select(SensorChannel.id))),
                    "records": list(await session.scalars(select(WaveformRecord.id))),
                    "analyses": list(await session.scalars(select(StructuralAnalysisRun.id))),
                }
        assert scoped["business-component"] == {
            "components": [fixture["components"][0]["id"]],
            "sensors": [],
            "records": [],
            "analyses": [],
        }
        assert scoped["business-sensor"] == {
            "components": [],
            "sensors": [fixture["sensors"][0]["id"]],
            "records": [],
            "analyses": [],
        }
    finally:
        await engine.dispose()
    store = create_knowledge_graph_store(
        Settings(
            _env_file=None, **{key: value for key, value in config.items() if key != "fixture"}
        )
    )
    try:
        snapshot = await store.snapshot(KNOWLEDGE_GRAPH_PROJECTION_ID)
        assert snapshot is not None
        projected = {node.entity_id for node in snapshot.nodes}
        required = (
            {row["id"] for row in fixture["components"] + fixture["sensors"]}
            | set(browser["record_ids"])
            | set(browser["run_ids"])
            | {browser["claim_id"]}
            | set(modes)
        )
        assert required <= projected
        statuses = {
            node.entity_id: node.properties.get("status")
            for node in snapshot.nodes
            if node.entity_id in browser["run_ids"]
        }
        assert statuses == {identity: "succeeded" for identity in browser["run_ids"]}
        return {
            "counts": counts,
            "execution_receipts": execution_receipts,
            "artifacts": artifacts,
            "audit_counts": audit_counts,
            "sql_scope_rows": scoped,
            "claim_revision": claim_revision,
            "neo4j_nodes": len(snapshot.nodes),
            "neo4j_relationships": len(snapshot.relationships),
            "projected_required_ids": sorted(required),
        }
    finally:
        await store.close()
