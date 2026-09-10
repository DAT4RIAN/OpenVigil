from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

from test_care_anomaly import (
    _evaluation_artifact,
    _manager_headers,
    _model_request,
    _online_runtime,
    _persist_authoritative_activation_evidence,
)
from windops_backend.api.deps import _consume_delegated_write_nonce
from windops_backend.config import ModelInferenceTarget, Settings
from windops_backend.enums import ApprovalAction, Environment
from windops_backend.errors import ConflictError, InvalidTransitionError
from windops_backend.main import create_app
from windops_backend.models import (
    Alarm,
    Approval,
    BenchmarkEvaluationRun,
    BenchmarkEventResult,
    CommandReceipt,
    Decision,
    DelegatedRequestAudit,
    DelegatedRequestNonce,
    DomainEvent,
    IngestReceipt,
    Mission,
    ModelDeployment,
    RegisteredModel,
    Turbine,
    WindFarm,
)
from windops_backend.observability import create_observability_runtime
from windops_backend.outbox import claim_event
from windops_backend.schemas import (
    ApprovalRequest,
    BenchmarkDatasetVersionCreateRequest,
    BenchmarkEvaluationRunCreateRequest,
    BenchmarkEventCreateRequest,
    BenchmarkEventResultCreateRequest,
    BenchmarkFileCreateRequest,
)
from windops_backend.services.benchmark_metadata import (
    get_or_create_evaluation_run,
    record_event_result,
    register_benchmark_event,
    register_benchmark_file,
    register_dataset_version,
)
from windops_backend.services.idempotency import execute_idempotent_command
from windops_backend.services.workflow import record_approval
from windops_backend.storage import InMemoryArtifactVerifier, OutboxEvent

pytestmark = [
    pytest.mark.external_release,
    pytest.mark.skipif(
        os.getenv("WINDOPS_RUN_POSTGRES_CONTRACT_TESTS") != "1",
        reason="requires an isolated migrated PostgreSQL database",
    ),
]


def _database_url() -> str:
    value = os.getenv("WINDOPS_POSTGRES_TEST_URL", "").strip()
    if value.startswith("postgres://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    if not value:
        raise RuntimeError("WINDOPS_POSTGRES_TEST_URL is required")
    return make_url(value).render_as_string(hide_password=False)


@pytest.mark.asyncio
async def test_anomaly_http_activation_serializes_and_rolls_back_on_postgres() -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url=_database_url(),
        schema_bootstrap=False,
        demo_seed=True,
        agent_mode="deterministic",
        test_auth_bypass_enabled=True,
        outbox_inline_drain=True,
        knowledge_graph_backend="memory",
    )
    settings.model_inference_targets["anomaly-primary"] = ModelInferenceTarget(
        endpoint_url="http://anomaly.test/v1/predict",
        api_token=SecretStr("postgres-anomaly-token"),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        verifier = app.state.artifact_verifier
        assert isinstance(verifier, InMemoryArtifactVerifier)
        package = b"postgres CARE anomaly package"
        package_sha = hashlib.sha256(package).hexdigest()
        model_payload = _model_request()
        model_payload["artifact_sha256"] = package_sha
        model_uri = str(model_payload["artifact_uri"])
        verifier.register_object(model_uri, package, "application/onnx")
        artifact, threshold = _evaluation_artifact()
        runtime = _online_runtime(
            model_artifact_uri=model_uri,
            evaluation_run_id="eval-final-1",
            threshold=threshold,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            registered = await client.post(
                "/api/v1/models",
                headers=_manager_headers("postgres-anomaly-register-1"),
                json=model_payload,
            )
            assert registered.status_code == 201, registered.text
            staged = await client.post(
                "/api/v1/models/ANOM-CARE-001/deployments",
                headers=_manager_headers("postgres-anomaly-stage-1"),
                json={
                    "target_id": "anomaly-primary",
                    "stage": "production",
                    "evaluation_gate": {"care_online_runtime": runtime},
                },
            )
            assert staged.status_code == 201, staged.text
            deployment_id = str(staged.json()["deployment_id"])
            await _persist_authoritative_activation_evidence(
                app,
                artifact,
                threshold,
                model_artifact_uri=model_uri,
                model_artifact_sha256=package_sha,
            )

            async def activate(key: str) -> httpx.Response:
                return await client.post(
                    f"/api/v1/models/deployments/{deployment_id}/activate",
                    headers=_manager_headers(key),
                    json={
                        "traffic_percent": 100,
                        "reason": "serialize the governed PostgreSQL activation",
                    },
                )

            first, second = await asyncio.wait_for(
                asyncio.gather(
                    activate("postgres-anomaly-concurrent-1"),
                    activate("postgres-anomaly-concurrent-2"),
                ),
                timeout=10,
            )
            assert sorted((first.status_code, second.status_code)) == [200, 409]
            rejected = second if second.status_code == 409 else first
            assert rejected.json()["error"]["code"] == "ANOMALY_ACTIVATION_CONCURRENT_CHANGE"

            replacement = await client.post(
                "/api/v1/models/ANOM-CARE-001/deployments",
                headers=_manager_headers("postgres-anomaly-stage-2"),
                json={
                    "target_id": "anomaly-primary",
                    "stage": "production",
                    "evaluation_gate": {"care_online_runtime": runtime},
                },
            )
            assert replacement.status_code == 201, replacement.text
            replacement_id = str(replacement.json()["deployment_id"])
            replacement_activation = await client.post(
                f"/api/v1/models/deployments/{replacement_id}/activate",
                headers=_manager_headers("postgres-anomaly-activate-2"),
                json={"traffic_percent": 100, "reason": "activate replacement"},
            )
            assert replacement_activation.status_code == 200, replacement_activation.text
            rollback = await client.post(
                "/api/v1/models/ANOM-CARE-001/rollback",
                headers=_manager_headers("postgres-anomaly-rollback-1"),
                json={
                    "target_deployment_id": deployment_id,
                    "reason": "rollback through the governed public endpoint",
                },
            )
            assert rollback.status_code == 200, rollback.text
            assert rollback.json()["rollback_from_id"] == replacement_id

        async with app.state.session_factory() as session:
            active = list(
                (
                    await session.scalars(
                        select(ModelDeployment).where(
                            ModelDeployment.stage == "production",
                            ModelDeployment.status == "active",
                            ModelDeployment.model_id == "ANOM-CARE-001",
                        )
                    )
                ).all()
            )
            assert [(row.id, row.traffic_percent) for row in active] == [(deployment_id, 100)]


@pytest.mark.asyncio
async def test_outbox_claim_is_atomic_across_sessions() -> None:
    engine = create_async_engine(_database_url(), pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    event_id: str
    async with factory() as session, session.begin():
        event = OutboxEvent(
            event_type="postgres.contract.outbox",
            aggregate_type="contract",
            aggregate_id=str(uuid4()),
            payload={"contract": "atomic-claim"},
        )
        session.add(event)
        await session.flush()
        event_id = event.id

    barrier = asyncio.Barrier(2)

    async def claim() -> str | None:
        async with factory() as session, session.begin():
            await barrier.wait()
            claimed = await claim_event(session, event_id)
            return claimed.claim_token if claimed is not None else None

    try:
        claims = await asyncio.wait_for(asyncio.gather(claim(), claim()), timeout=5)
        assert sum(token is not None for token in claims) == 1
        async with factory() as session:
            persisted = await session.get(OutboxEvent, event_id)
            assert persisted is not None
            assert persisted.status == "processing"
            assert persisted.attempts == 1
            assert persisted.claim_token == next(token for token in claims if token is not None)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_command_receipt_unique_constraint_survives_concurrent_commits() -> None:
    engine = create_async_engine(_database_url(), pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    command_type = f"postgres-contract-{uuid4()}"
    idempotency_key = f"concurrent-{uuid4()}"
    barrier = asyncio.Barrier(2)

    async def insert_receipt(identifier: str) -> str:
        async with factory() as session:
            session.add(
                CommandReceipt(
                    id=identifier,
                    command_type=command_type,
                    idempotency_key=idempotency_key,
                    request_hash="a" * 64,
                    subject="postgres-contract",
                    response_body={"identifier": identifier},
                    status_code=201,
                )
            )
            await barrier.wait()
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return "conflict"
            return "committed"

    try:
        results = await asyncio.wait_for(
            asyncio.gather(insert_receipt(str(uuid4())), insert_receipt(str(uuid4()))),
            timeout=5,
        )
        assert sorted(results) == ["committed", "conflict"]
        async with factory() as session:
            count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(CommandReceipt)
                    .where(
                        CommandReceipt.command_type == command_type,
                        CommandReceipt.idempotency_key == idempotency_key,
                    )
                )
                or 0
            )
        assert count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delegated_nonce_is_atomic_across_application_instances() -> None:
    database_url = _database_url()
    engine = create_async_engine(database_url, pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        environment=Environment.TEST,
        database_url=database_url,
        schema_bootstrap=False,
        demo_seed=False,
    )
    apps = [FastAPI(), FastAPI()]
    runtimes = [create_observability_runtime(settings) for _ in apps]
    for app, runtime in zip(apps, runtimes, strict=True):
        app.state.session_factory = factory
        app.state.observability = runtime

    delegation_id = f"postgres-multi-instance-{uuid4()}"
    jti_sha256 = hashlib.sha256(delegation_id.encode()).hexdigest()
    path = "/api/v1/missions/MISSION-CONCURRENT/comments"
    body_sha256 = "c" * 64
    barrier = asyncio.Barrier(2)

    async def consume(app: FastAPI) -> str:
        request = Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "https",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [],
                "server": ("windops.test", 443),
                "client": ("127.0.0.1", 12345),
                "root_path": "",
                "app": app,
            }
        )
        await barrier.wait()
        try:
            await _consume_delegated_write_nonce(
                request,
                subject="postgres-multi-instance-subject",
                delegation_id=delegation_id,
                expires_at=datetime.now(UTC) + timedelta(minutes=1),
                body_sha256=body_sha256,
                clock_skew_seconds=15,
            )
        except HTTPException as exc:
            assert exc.status_code == 401
            return "replayed"
        return "accepted"

    try:
        results = await asyncio.wait_for(asyncio.gather(*(consume(app) for app in apps)), timeout=8)
        assert sorted(results) == ["accepted", "replayed"]
        async with factory() as session:
            nonce_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(DelegatedRequestNonce)
                    .where(DelegatedRequestNonce.jti_sha256 == jti_sha256)
                )
                or 0
            )
            outcomes = list(
                (
                    await session.scalars(
                        select(DelegatedRequestAudit.outcome)
                        .where(DelegatedRequestAudit.jti_sha256 == jti_sha256)
                        .order_by(DelegatedRequestAudit.occurred_at)
                    )
                ).all()
            )
        assert nonce_count == 1
        assert sorted(outcomes) == ["accepted", "replayed"]
    finally:
        for runtime in runtimes:
            runtime.shutdown()
        await engine.dispose()


@pytest.mark.asyncio
async def test_idempotent_command_replays_across_application_instances() -> None:
    engine = create_async_engine(_database_url(), pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    command_type = f"postgres-idempotency-{suffix}"
    idempotency_key = f"same-key-{suffix}"
    event_type = f"postgres.idempotency.{suffix}"
    barrier = asyncio.Barrier(2)

    async def execute(instance: str) -> tuple[dict[str, object], bool]:
        async with factory() as session:
            await barrier.wait()

            async def operation() -> dict[str, object]:
                event_id = str(uuid4())
                session.add(
                    DomainEvent(
                        id=event_id,
                        event_type=event_type,
                        aggregate_type="postgres_idempotency_contract",
                        aggregate_id=suffix,
                        payload={"executed_by": instance},
                    )
                )
                return {"event_id": event_id, "state": "committed"}

            async with session.begin():
                return await execute_idempotent_command(
                    session,
                    subject="postgres-multi-instance-subject",
                    command_type=command_type,
                    target=suffix,
                    idempotency_key=idempotency_key,
                    payload={"value": 42},
                    status_code=201,
                    operation=operation,
                )

    try:
        results = await asyncio.wait_for(
            asyncio.gather(execute("instance-a"), execute("instance-b")), timeout=8
        )
        assert results[0][0] == results[1][0]
        assert sorted(result[1] for result in results) == [False, True]
        async with factory() as session:
            receipt_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(CommandReceipt)
                    .where(
                        CommandReceipt.command_type == command_type,
                        CommandReceipt.target == suffix,
                        CommandReceipt.idempotency_key == idempotency_key,
                    )
                )
                or 0
            )
            event_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(DomainEvent)
                    .where(DomainEvent.event_type == event_type)
                )
                or 0
            )
        assert receipt_count == 1
        assert event_count == 1
    finally:
        await engine.dispose()


async def _seed_review_mission(
    session: AsyncSession,
    *,
    suffix: str,
) -> str:
    farm_id = f"WF-CAS-{suffix}"
    turbine_id = f"WT-CAS-{suffix}"
    receipt_id = f"receipt-cas-{suffix}"
    alarm_id = f"ALARM-CAS-{suffix}"
    mission_id = f"MISSION-CAS-{suffix}"
    session.add(
        WindFarm(
            id=farm_id,
            tenant_id="tenant-east-china",
            name="PostgreSQL CAS contract farm",
            capacity_mw=10,
        )
    )
    await session.flush()
    session.add(Turbine(id=turbine_id, wind_farm_id=farm_id, model="CAS-CONTRACT"))
    session.add(IngestReceipt(source_event_id=receipt_id, payload_hash="b" * 64))
    await session.flush()
    session.add(
        Alarm(
            id=alarm_id,
            turbine_id=turbine_id,
            source_event_id=receipt_id,
            code="CAS-CONTRACT",
            subsystem="main_bearing",
            title="PostgreSQL approval CAS contract",
            severity="major",
            triggered_at=datetime.now(UTC),
            evidence={},
        )
    )
    await session.flush()
    session.add(
        Mission(
            id=mission_id,
            alarm_id=alarm_id,
            turbine_id=turbine_id,
            title="PostgreSQL approval CAS contract",
            status="under_review",
            revision=1,
            public_state={"workflow_status": "under_review"},
        )
    )
    await session.flush()
    session.add(
        Decision(
            id=f"DECISION-CAS-{suffix}",
            mission_id=mission_id,
            status="pending_approval",
            alternatives=[{"alternative_id": "monitor"}],
            recommended_alternative_id="monitor",
            recommendation_reason="PostgreSQL concurrency contract",
            risks=[],
        )
    )
    await session.flush()
    return mission_id


@pytest.mark.asyncio
async def test_mission_approval_lock_allows_exactly_one_concurrent_transition() -> None:
    database_url = _database_url()
    engine = create_async_engine(database_url, pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:12]
    async with factory() as session, session.begin():
        mission_id = await _seed_review_mission(session, suffix=suffix)
    settings = Settings(
        environment=Environment.TEST,
        database_url=database_url,
        schema_bootstrap=False,
        demo_seed=False,
    )
    barrier = asyncio.Barrier(2)

    async def reject(approver: str) -> str:
        async with factory() as session:
            await barrier.wait()
            try:
                async with session.begin():
                    await record_approval(
                        session,
                        settings,
                        mission_id,
                        ApprovalRequest(
                            action=ApprovalAction.REJECT,
                            expected_revision=1,
                            approver=approver,
                            reason="PostgreSQL row-lock contract rejection",
                        ),
                    )
            except (ConflictError, InvalidTransitionError, IntegrityError):
                return "conflict"
            return "committed"

    try:
        results = await asyncio.wait_for(
            asyncio.gather(reject("approver-one"), reject("approver-two")),
            timeout=8,
        )
        assert sorted(results) == ["committed", "conflict"]
        async with factory() as session:
            mission = await session.get(Mission, mission_id)
            approval_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Approval)
                    .where(Approval.mission_id == mission_id)
                )
                or 0
            )
            event_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(DomainEvent)
                    .where(
                        DomainEvent.aggregate_id == mission_id,
                        DomainEvent.event_type == "mission.approval.reject",
                    )
                )
                or 0
            )
        assert mission is not None
        assert mission.status == "rejected"
        assert mission.revision == 2
        assert approval_count == 1
        assert event_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_benchmark_run_and_result_creation_is_concurrent_and_atomic() -> None:
    database_url = _database_url()
    engine = create_async_engine(database_url, pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:10]
    farm_id = f"WF-CARE-{suffix}"
    turbine_id = f"WT-CARE-{suffix}"
    dataset_version_id = f"care-v6-{suffix}"
    file_id = f"care-file-{suffix}"
    event_id = f"care-event-{suffix}"
    model_id = f"CARE-MODEL-{suffix}"
    input_identity = hashlib.sha256(f"evaluation:{suffix}".encode()).hexdigest()
    content_identity = hashlib.sha256(f"dataset:{suffix}".encode()).hexdigest()
    result_identity = hashlib.sha256(f"result:{suffix}".encode()).hexdigest()
    evaluation_ids = [f"care-eval-a-{suffix}", f"care-eval-b-{suffix}"]
    try:
        async with factory() as session, session.begin():
            session.add(
                WindFarm(
                    id=farm_id,
                    tenant_id="tenant-east-china",
                    name="CARE concurrency farm",
                    capacity_mw=1,
                )
            )
            await session.flush()
            session.add(
                Turbine(
                    id=turbine_id,
                    wind_farm_id=farm_id,
                    model="CARE isolated replay",
                    status="running",
                    health_score=100,
                )
            )
            session.add(
                RegisteredModel(
                    id=model_id,
                    name=f"CARE concurrency model {suffix}",
                    version="1.0.0",
                    kind="anomaly",
                    status="registered",
                    artifact_uri=f"minio://care/models/{suffix}.onnx",
                    artifact_sha256="a" * 64,
                    content_type="application/onnx",
                    content_size_bytes=10,
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                    metrics={},
                    description="PostgreSQL benchmark concurrency contract",
                    created_by="postgres-contract",
                )
            )
            await session.flush()
            await register_dataset_version(
                session,
                BenchmarkDatasetVersionCreateRequest(
                    dataset_version_id=dataset_version_id,
                    tenant_id="tenant-east-china",
                    dataset_id=f"CARE-{suffix}",
                    version="6",
                    status="ready",
                    source_uri=f"file:///readonly/{suffix}.zip",
                    manifest_uri=f"minio://care/raw/{suffix}/manifest.json",
                    manifest_sha256="b" * 64,
                    content_sha256=content_identity,
                    size_bytes=100,
                    file_count=1,
                    license_name="CC BY-SA 4.0",
                    license_url="https://creativecommons.org/licenses/by-sa/4.0/",
                    doi=f"10.0000/{suffix}",
                    citation="PostgreSQL benchmark concurrency contract",
                    attribution={},
                ),
                subject="postgres-contract",
            )
            await register_benchmark_file(
                session,
                BenchmarkFileCreateRequest(
                    file_id=file_id,
                    dataset_version_id=dataset_version_id,
                    file_kind="event",
                    relative_path=f"A/event_{suffix}.csv",
                    farm="A",
                    event_id=0,
                    size_bytes=100,
                    row_count=2,
                    schema_sha256="c" * 64,
                    content_sha256="d" * 64,
                    metadata={},
                ),
            )
            await register_benchmark_event(
                session,
                BenchmarkEventCreateRequest(
                    benchmark_event_id=event_id,
                    dataset_version_id=dataset_version_id,
                    source_file_id=file_id,
                    event_id=0,
                    farm="A",
                    source_asset_id="1",
                    logical_asset_id="CARE-A-1",
                    event_label="anomaly",
                    first_source_row_id=0,
                    last_source_row_id=1,
                    train_row_count=1,
                    prediction_row_count=1,
                    event_interval_start=1,
                    event_interval_end=1,
                    truth_metadata={},
                ),
            )

        run_barrier = asyncio.Barrier(2)

        async def create_run(evaluation_id: str) -> tuple[str, bool]:
            async with factory() as session, session.begin():
                await run_barrier.wait()
                row, replayed = await get_or_create_evaluation_run(
                    session,
                    BenchmarkEvaluationRunCreateRequest(
                        evaluation_run_id=evaluation_id,
                        dataset_version_id=dataset_version_id,
                        model_id=model_id,
                        model_version="1.0.0",
                        run_kind="final-holdout",
                        protocol_version="care-score-v6",
                        farm="A",
                        feature_set_version="care-v6-avg-v1",
                        quality_rule_version="care-v6-quality-v1",
                        threshold_policy_version="threshold-v1",
                        threshold_policy_sha256="e" * 64,
                        random_seed=42,
                        input_identity_sha256=input_identity,
                        requested_event_count=1,
                        extension_data={},
                    ),
                    subject="postgres-contract",
                )
                return row.id, replayed

        run_results = await asyncio.wait_for(
            asyncio.gather(*(create_run(identifier) for identifier in evaluation_ids)),
            timeout=8,
        )
        persisted_evaluation_id = run_results[0][0]
        assert {row_id for row_id, _replayed in run_results} == {persisted_evaluation_id}
        assert sorted(replayed for _row_id, replayed in run_results) == [False, True]

        result_barrier = asyncio.Barrier(2)

        async def create_result(identifier: str) -> tuple[str, bool]:
            async with factory() as session, session.begin():
                await result_barrier.wait()
                row, replayed = await record_event_result(
                    session,
                    BenchmarkEventResultCreateRequest(
                        event_result_id=identifier,
                        evaluation_run_id=persisted_evaluation_id,
                        event_id=event_id,
                        status="scored",
                        scorable=True,
                        anomaly_detected=True,
                        care_score=0.9,
                        prediction_artifact_uri=f"minio://care/predictions/{suffix}.json",
                        prediction_artifact_sha256="f" * 64,
                        result_sha256=result_identity,
                        details={},
                    ),
                )
                return row.id, replayed

        result_results = await asyncio.wait_for(
            asyncio.gather(
                create_result(f"care-result-a-{suffix}"),
                create_result(f"care-result-b-{suffix}"),
            ),
            timeout=8,
        )
        persisted_result_id = result_results[0][0]
        assert {row_id for row_id, _replayed in result_results} == {persisted_result_id}
        assert sorted(replayed for _row_id, replayed in result_results) == [False, True]

        async with factory() as session:
            with pytest.raises(ConflictError, match="different immutable content"):
                async with session.begin():
                    await record_event_result(
                        session,
                        BenchmarkEventResultCreateRequest(
                            event_result_id=f"care-result-conflict-{suffix}",
                            evaluation_run_id=persisted_evaluation_id,
                            event_id=event_id,
                            status="scored",
                            scorable=True,
                            anomaly_detected=False,
                            care_score=0.1,
                            prediction_artifact_uri=(
                                f"minio://care/predictions/{suffix}-conflict.json"
                            ),
                            prediction_artifact_sha256="1" * 64,
                            result_sha256="2" * 64,
                            details={},
                        ),
                    )

        async with factory() as session:
            run_count = int(
                await session.scalar(
                    select(func.count(BenchmarkEvaluationRun.id)).where(
                        BenchmarkEvaluationRun.input_identity_sha256 == input_identity
                    )
                )
                or 0
            )
            result_count = int(
                await session.scalar(
                    select(func.count(BenchmarkEventResult.id)).where(
                        BenchmarkEventResult.evaluation_run_id == persisted_evaluation_id
                    )
                )
                or 0
            )
            assert run_count == 1
            assert result_count == 1
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "DELETE FROM benchmark_event_results WHERE evaluation_run_id IN "
                    "(SELECT id FROM benchmark_evaluation_runs "
                    "WHERE input_identity_sha256 = :identity)"
                ),
                {"identity": input_identity},
            )
            await session.execute(
                text(
                    "DELETE FROM benchmark_evaluation_runs WHERE input_identity_sha256 = :identity"
                ),
                {"identity": input_identity},
            )
            await session.execute(
                text("DELETE FROM benchmark_events WHERE dataset_version_id = :dataset"),
                {"dataset": dataset_version_id},
            )
            await session.execute(
                text("DELETE FROM benchmark_files WHERE dataset_version_id = :dataset"),
                {"dataset": dataset_version_id},
            )
            await session.execute(
                text("DELETE FROM benchmark_dataset_versions WHERE id = :dataset"),
                {"dataset": dataset_version_id},
            )
            await session.execute(
                text("DELETE FROM registered_models WHERE id = :model"), {"model": model_id}
            )
            await session.execute(
                text("DELETE FROM turbines WHERE id = :turbine"), {"turbine": turbine_id}
            )
            await session.execute(
                text("DELETE FROM wind_farms WHERE id = :farm"), {"farm": farm_id}
            )
        await engine.dispose()
