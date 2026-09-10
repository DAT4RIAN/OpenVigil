from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import event, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from windops_backend.benchmarks.care.anomaly import (
    ActivationGateEvidence,
    ActivationGatePolicy,
    evaluate_activation_gate,
)
from windops_backend.benchmarks.care.anomaly import (
    BenchmarkMetricSnapshot as ActivationMetricSnapshot,
)
from windops_backend.benchmarks.care.evaluation import (
    EVALUATION_SUITE_PROTOCOL,
    register_offline_evaluations,
)
from windops_backend.benchmarks.care.fullscale import (
    MIN_REPLAY_WRITE_ROWS_PER_SECOND,
    register_full_scale_evaluation,
    register_full_scale_import,
)
from windops_backend.benchmarks.care.importer import register_a_minimal_import
from windops_backend.benchmarks.care.online import (
    CareJsonPackageInferenceClient,
    OnlineWindowSelection,
    build_online_runtime_configuration,
    load_replay_rows,
    replay_variables_from_import,
    select_online_window,
)
from windops_backend.benchmarks.care.quality import FEATURE_SET_VERSION, QUALITY_RULE_VERSION
from windops_backend.benchmarks.care.replay import (
    CARE_REPLAY_SOURCE_ID,
    BenchmarkReplayRun,
    ReplaySourceRow,
    advance_checkpoint,
    build_replay_sample,
    create_replay_run,
    transition_replay_run,
)
from windops_backend.config import (
    ModelInferenceTarget,
    Settings,
    TelemetrySourcePolicy,
    TelemetryVariablePolicy,
)
from windops_backend.enums import Environment
from windops_backend.main import create_app
from windops_backend.models import (
    AgentExecution,
    Alarm,
    AnomalyAlertPolicyState,
    BenchmarkQualityArtifact,
    BenchmarkQualityReport,
    CommandReceipt,
    Decision,
    DomainEvent,
    Evidence,
    IngestReceipt,
    Mission,
    ModelPrediction,
    RegisteredModel,
    ScadaSample,
    Turbine,
)
from windops_backend.models import (
    BenchmarkReplayRun as PersistedReplayRun,
)
from windops_backend.schemas import (
    BenchmarkQualityReportCreateRequest,
    BenchmarkReplayRunCreateRequest,
)
from windops_backend.services.benchmark_metadata import (
    build_benchmark_trace,
    persist_replay_run_progress,
    register_quality_report,
    register_replay_run,
)
from windops_backend.services.events import append_domain_event
from windops_backend.services.models import (
    activate_deployment,
    create_deployment,
)

pytestmark = [
    pytest.mark.external_release,
    pytest.mark.skipif(
        os.getenv("WINDOPS_RUN_POSTGRES_CONTRACT_TESTS") != "1",
        reason="requires an isolated migrated PostgreSQL database",
    ),
]

SUBJECT = "integration-test-system"
FULL_SCALE_SUBJECT = "care-full-scale-stage-upgrade"
TARGET_ID = "care-json-package"
ANOMALY_RUN_ID = "h5a00001"
NORMAL_RUN_ID = "h5n00001"
ISOLATED_RUN_ID = "h5a00002"
MAX_REPLAY_WRITE_SQL_STATEMENTS_PER_BATCH = 40


@dataclass
class _SqlProfile:
    statement_count: int = 0
    elapsed_seconds: float = 0.0


@contextmanager
def _capture_sql_profile(engine: AsyncEngine) -> Iterator[_SqlProfile]:
    profile = _SqlProfile()

    def before_cursor_execute(
        _connection: Any,
        _cursor: Any,
        _statement: Any,
        _parameters: Any,
        context: Any,
        _executemany: Any,
    ) -> None:
        context._windops_profile_started = time.perf_counter()

    def after_cursor_execute(
        _connection: Any,
        _cursor: Any,
        _statement: Any,
        _parameters: Any,
        context: Any,
        _executemany: Any,
    ) -> None:
        profile.statement_count += 1
        profile.elapsed_seconds += time.perf_counter() - context._windops_profile_started

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
    event.listen(sync_engine, "after_cursor_execute", after_cursor_execute)
    try:
        yield profile
    finally:
        event.remove(sync_engine, "before_cursor_execute", before_cursor_execute)
        event.remove(sync_engine, "after_cursor_execute", after_cursor_execute)


def _database_url() -> str:
    value = os.getenv("WINDOPS_POSTGRES_TEST_URL", "").strip()
    if value.startswith("postgres://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    if not value:
        raise RuntimeError("WINDOPS_POSTGRES_TEST_URL is required")
    return make_url(value).render_as_string(hide_password=False)


def _artifact_root() -> Path:
    value = os.getenv("WINDOPS_CARE_REAL_ARTIFACT_ROOT", "").strip()
    if not value:
        raise RuntimeError("WINDOPS_CARE_REAL_ARTIFACT_ROOT is required")
    return Path(value).resolve(strict=True)


def _full_scale_root() -> Path:
    value = os.getenv("WINDOPS_CARE_FULL_SCALE_ROOT", "").strip()
    if not value:
        raise RuntimeError("WINDOPS_CARE_FULL_SCALE_ROOT is required")
    return Path(value).resolve(strict=True)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path} is not a JSON object")
    return value


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _load_artifact(root: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    relative = Path(str(reference["local_relative_path"]))
    path = (root / relative).resolve(strict=True)
    assert path.is_relative_to(root.resolve(strict=True))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == reference["file_sha256"]
    return _read_json(path)


def _headers(
    role: str,
    *,
    subject: str = SUBJECT,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    result = {
        "X-WindOps-Test-Principal": subject,
        "X-WindOps-Test-Role": role,
    }
    if idempotency_key is not None:
        result["Idempotency-Key"] = idempotency_key
    return result


def _request_for_run(
    run: BenchmarkReplayRun,
    *,
    model_version: str,
    threshold_policy: Mapping[str, Any],
) -> BenchmarkReplayRunCreateRequest:
    checkpoint = run.checkpoint.to_document()
    return BenchmarkReplayRunCreateRequest(
        benchmark_replay_run_id=run.benchmark_replay_run_id,
        dataset_version_id="care-v6",
        event_id=f"care-v6-event-a-{run.event_id}",
        source_asset_id=run.source_asset_id,
        logical_asset_id=run.logical_asset_id,
        online_turbine_id=run.online_turbine_id,
        farm="A",
        source_event_number=run.event_id,
        replay_mode=run.replay_mode,
        speed=run.speed,
        status=run.status,
        replay_anchor_at=run.replay_anchor_at,
        time_rule_version=run.time_rule_version,
        sequence_rule_version=run.sequence_rule_version,
        source_event_id_rule_version=run.source_event_id_rule_version,
        selected_variables=[value.to_document() for value in run.selected_variables],
        window_start_row_id=run.window_start_row_id,
        window_end_row_id=run.window_end_row_id,
        checkpoint=checkpoint,
        checkpoint_revision=run.checkpoint.revision,
        checkpoint_sha256=_canonical_hash(checkpoint),
        model_id=run.model_id,
        model_version=model_version,
        deployment_id=run.deployment_id,
        threshold_policy_version=str(threshold_policy["version"]),
        threshold_policy_sha256=str(threshold_policy["threshold_policy_sha256"]),
        started_at=run.started_at,
        finished_at=run.finished_at,
        cancelled_by=run.cancelled_by,
        error=run.error,
    )


@asynccontextmanager
async def _running_app(
    settings: Settings,
    inference_client: CareJsonPackageInferenceClient | None,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        if inference_client is not None:
            app.state.model_inference_client = inference_client
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield app, client


async def _persist_run(
    app: FastAPI,
    run: BenchmarkReplayRun,
    *,
    model_version: str,
    threshold_policy: Mapping[str, Any],
) -> bool:
    async with app.state.session_factory() as session, session.begin():
        _row, replayed = await persist_replay_run_progress(
            session,
            _request_for_run(
                run,
                model_version=model_version,
                threshold_policy=threshold_policy,
            ),
            subject=SUBJECT,
        )
    return replayed


async def _process_row(
    app: FastAPI,
    client: httpx.AsyncClient,
    run: BenchmarkReplayRun,
    row: ReplaySourceRow,
    *,
    model_version: str,
    threshold_policy: Mapping[str, Any],
    ingest_timings: list[float],
    ingest_sql_profiles: list[_SqlProfile],
    retry: bool = False,
) -> tuple[BenchmarkReplayRun, dict[str, Any], dict[str, Any]]:
    samples = [
        build_replay_sample(
            run,
            row,
            variable,
            quality_rule_id=QUALITY_RULE_VERSION,
        )
        for variable in run.selected_variables
    ]
    assert len(samples) == 54
    with _capture_sql_profile(app.state.engine) as sql_profile:
        ingest_started = time.perf_counter()
        ingest = await client.post(
            "/api/v1/scada/ingest",
            headers=_headers(
                "scada_ingestor",
                subject=f"ingest-source:{CARE_REPLAY_SOURCE_ID}",
            ),
            json={"source_id": CARE_REPLAY_SOURCE_ID, "samples": samples},
        )
    ingest_timings.append(time.perf_counter() - ingest_started)
    ingest_sql_profiles.append(sql_profile)
    assert ingest.status_code == 202, ingest.text
    assert ingest.json()["accepted"] == 54
    assert ingest.json()["quarantined"] == 0
    if retry:
        repeated_ingest = await client.post(
            "/api/v1/scada/ingest",
            headers=_headers(
                "scada_ingestor",
                subject=f"ingest-source:{CARE_REPLAY_SOURCE_ID}",
            ),
            json={"source_id": CARE_REPLAY_SOURCE_ID, "samples": samples},
        )
        assert repeated_ingest.status_code == 202, repeated_ingest.text
        assert repeated_ingest.json()["accepted"] == 0
        assert repeated_ingest.json()["duplicates"] == 54

    advanced = advance_checkpoint(run, samples)
    assert (
        await _persist_run(
            app,
            advanced,
            model_version=model_version,
            threshold_policy=threshold_policy,
        )
        is False
    )
    assert (
        await _persist_run(
            app,
            advanced,
            model_version=model_version,
            threshold_policy=threshold_policy,
        )
        is True
    )

    inference_key = f"care-h005-infer-{run.benchmark_replay_run_id}-{row.source_row_id}"
    inference = await client.post(
        f"/api/v1/models/deployments/{run.deployment_id}/anomaly-predictions/run",
        headers=_headers("operations_manager", idempotency_key=inference_key),
        json={
            "benchmark_replay_run_id": run.benchmark_replay_run_id,
            "source_row_id": row.source_row_id,
        },
    )
    assert inference.status_code == 200, inference.text
    assert inference.headers["Idempotency-Replayed"] == "false"
    prediction = inference.json()
    assert prediction["status"] == "succeeded"
    prediction_id = str(prediction["prediction_id"])
    before_retry_calls = app.state.model_inference_client.call_count
    if retry:
        repeated_inference = await client.post(
            f"/api/v1/models/deployments/{run.deployment_id}/anomaly-predictions/run",
            headers=_headers("operations_manager", idempotency_key=inference_key),
            json={
                "benchmark_replay_run_id": run.benchmark_replay_run_id,
                "source_row_id": row.source_row_id,
            },
        )
        assert repeated_inference.status_code == 200, repeated_inference.text
        assert repeated_inference.headers["Idempotency-Replayed"] == "true"
        assert repeated_inference.json() == prediction
        assert app.state.model_inference_client.call_count == before_retry_calls

    alert_key = f"care-h005-alert-{run.benchmark_replay_run_id}-{row.source_row_id}"
    alert_response = await client.post(
        f"/api/v1/model-predictions/{prediction_id}/alert-evaluation",
        headers=_headers("operations_manager", idempotency_key=alert_key),
    )
    assert alert_response.status_code == 200, alert_response.text
    assert alert_response.headers["Idempotency-Replayed"] == "false"
    alert = alert_response.json()
    if retry:
        repeated_alert = await client.post(
            f"/api/v1/model-predictions/{prediction_id}/alert-evaluation",
            headers=_headers("operations_manager", idempotency_key=alert_key),
        )
        assert repeated_alert.status_code == 200, repeated_alert.text
        assert repeated_alert.headers["Idempotency-Replayed"] == "true"
        assert repeated_alert.json() == alert
    return advanced, prediction, alert


def _selection_by_event(
    evaluation_root: Path,
    model: Mapping[str, Any],
) -> dict[int, OnlineWindowSelection]:
    result: dict[int, OnlineWindowSelection] = {}
    for reference in model["prediction_artifacts"]:
        prediction = _load_artifact(evaluation_root, reference)
        selection = select_online_window(prediction)
        result[selection.event_id] = selection
    assert set(result) == {0, 24}
    return result


@pytest.mark.asyncio
async def test_real_postgres_care_replay_alert_mission_diagnosis_vertical_slice(
    record_testsuite_property: Any,
) -> None:
    artifact_root = _artifact_root()
    source_manifest = _read_json(artifact_root / "contract/manifest.json")
    quality = _read_json(artifact_root / "quality/quality-contract.json")
    import_root = artifact_root / "minimal-import"
    evaluation_root = artifact_root / "offline-evaluation"
    imported = _read_json(import_root / "care/v6/reports/a-minimal-import/manifest.json")
    evaluated = _read_json(evaluation_root / "care/v6/reports/offline-evaluation/manifest.json")
    model = next(
        value
        for value in evaluated["models"]
        if value["algorithm"] == "care-random-projection-ensemble-v1"
    )
    package = _load_artifact(evaluation_root, model["package"])
    evaluation = _load_artifact(evaluation_root, model["evaluation_artifact"])
    variables = replay_variables_from_import(
        imported,
        import_root,
        feature_columns=package["feature_columns"],
    )
    assert len(variables) == 54
    selections = _selection_by_event(evaluation_root, model)
    assert selections[0].binary_predictions == (True, True, True)
    assert not all(selections[24].binary_predictions)
    rows_by_event = {
        event_id: load_replay_rows(
            imported,
            import_root,
            event_id=event_id,
            start_source_row_id=selection.start_source_row_id,
            end_source_row_id=selection.end_source_row_id,
            variables=variables,
        )
        for event_id, selection in selections.items()
    }

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
    settings.model_inference_targets[TARGET_ID] = ModelInferenceTarget(
        endpoint_url="https://care-model.invalid/v1/predict",
        api_token=SecretStr("not-used-by-safe-json-package-adapter"),
    )
    inference_client = CareJsonPackageInferenceClient(package)
    threshold_policy: Mapping[str, Any]
    ingest_timings: list[float] = []
    ingest_sql_profiles: list[_SqlProfile] = []
    anomaly_run: BenchmarkReplayRun
    normal_run: BenchmarkReplayRun
    isolated_run: BenchmarkReplayRun

    async with _running_app(settings, inference_client) as (app, client):
        async with app.state.session_factory() as session, session.begin():
            imported_registration = await register_a_minimal_import(
                session,
                imported,
                source_manifest,
                quality,
                tenant_id="tenant-east-china",
                subject=SUBJECT,
            )
            evaluated_registration = await register_offline_evaluations(
                session,
                evaluated,
                artifact_root=evaluation_root,
                subject=SUBJECT,
            )
            assert imported_registration.created_count == 88
            assert evaluated_registration.created_count > 0

            runtime = build_online_runtime_configuration(
                package,
                evaluation_run_id=str(model["evaluation_run_id"]),
                evidence_artifact_uri=(
                    "minio://windops-models/care/v6/reports/models/"
                    "model=care-a-minimal-rp-ensemble-v1/package.json"
                ),
                evidence_artifact_sha256=str(package["model_package_sha256"]),
                primary_variable=variables[0].canonical_variable,
                related_variables=[
                    variables[1].canonical_variable,
                    variables[2].canonical_variable,
                ],
            )
            threshold_policy = runtime["online_threshold_policy"]
            deployment = await create_deployment(
                session,
                settings,
                model_id=str(model["model_id"]),
                target_id=TARGET_ID,
                stage="benchmark-development",
                evaluation_gate={"care_online_runtime": runtime},
                subject=SUBJECT,
            )
            approval_event = append_domain_event(
                session,
                event_type="model.activation.approved",
                aggregate_type="model_deployment",
                aggregate_id=deployment.id,
                payload={
                    "deployment_id": deployment.id,
                    "evaluation_run_id": model["evaluation_run_id"],
                    "release_claim": "development-vertical-slice-only",
                },
            )
            audit_event = append_domain_event(
                session,
                event_type="model.activation.evidence-audited",
                aggregate_type="benchmark_evaluation_run",
                aggregate_id=str(model["evaluation_run_id"]),
                payload={
                    "deployment_id": deployment.id,
                    "model_package_sha256": package["model_package_sha256"],
                },
            )
            prediction_evidence = evaluation["predictions"][0]
            activation_policy = ActivationGatePolicy(
                policy_version="care-h005-development-activation-v1",
                minimum_care_score=0.0,
                minimum_event_detection_rate=0.0,
                maximum_normal_event_false_positive_rate=0.0,
                required_farms=("A",),
                required_generalization_protocols=(EVALUATION_SUITE_PROTOCOL,),
                required_feature_set_version=prediction_evidence["feature_set_version"],
                required_feature_set_sha256=prediction_evidence["feature_set_sha256"],
                required_quality_rule_version=prediction_evidence["quality_rule_version"],
                required_quality_contract_sha256=prediction_evidence["quality_contract_sha256"],
                required_threshold_policy_version=prediction_evidence["threshold_policy"][
                    "version"
                ],
                required_threshold_policy_sha256=prediction_evidence["threshold_policy"][
                    "threshold_policy_sha256"
                ],
            )
            authorization = evaluate_activation_gate(
                activation_policy,
                ActivationGateEvidence(
                    evaluation_run_id=str(model["evaluation_run_id"]),
                    evaluation_status="completed",
                    invalidated=False,
                    evaluation_artifact=evaluation,
                    metric_snapshot=ActivationMetricSnapshot.from_evaluation_artifact(evaluation),
                    model_id=str(model["model_id"]),
                    model_version=str(model["model_version"]),
                    model_artifact_sha256=str(model["package"]["file_sha256"]),
                    deployment_id=deployment.id,
                    deployment_version=deployment.id,
                    approval_ids=(approval_event.id,),
                    audit_event_ids=(audit_event.id,),
                ),
                authorized_at=datetime.now(UTC),
            )
            active = await activate_deployment(
                session,
                deployment_id=deployment.id,
                traffic_percent=100,
                reason="server-verified CARE development vertical slice",
                subject=SUBJECT,
                anomaly_authorization=authorization,
            )
            assert active.status == "active"
            registered_model = await session.get(RegisteredModel, str(model["model_id"]))
            assert registered_model is not None
            assert (
                registered_model.metrics["model_package_sha256"] == package["model_package_sha256"]
            )

            anchor = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=25)
            anomaly_run = create_replay_run(
                benchmark_replay_run_id=ANOMALY_RUN_ID,
                farm="A",
                event_id=0,
                source_asset_id="0",
                replay_anchor_at=anchor,
                selected_variables=variables,
                window_start_row_id=selections[0].start_source_row_id,
                window_end_row_id=selections[0].end_source_row_id,
                created_by=SUBJECT,
                created_at=anchor,
                model_id=str(model["model_id"]),
                deployment_id=deployment.id,
                threshold_policy_id=str(threshold_policy["threshold_policy_sha256"]),
            )
            normal_run = create_replay_run(
                benchmark_replay_run_id=NORMAL_RUN_ID,
                farm="A",
                event_id=24,
                source_asset_id="0",
                replay_anchor_at=anchor,
                selected_variables=variables,
                window_start_row_id=selections[24].start_source_row_id,
                window_end_row_id=selections[24].end_source_row_id,
                created_by=SUBJECT,
                created_at=anchor,
                model_id=str(model["model_id"]),
                deployment_id=deployment.id,
                threshold_policy_id=str(threshold_policy["threshold_policy_sha256"]),
            )
            isolated_start = selections[0].start_source_row_id
            isolated_run = create_replay_run(
                benchmark_replay_run_id=ISOLATED_RUN_ID,
                farm="A",
                event_id=0,
                source_asset_id="0",
                replay_anchor_at=anchor,
                selected_variables=variables,
                window_start_row_id=isolated_start,
                window_end_row_id=isolated_start,
                created_by=SUBJECT,
                created_at=anchor,
                model_id=str(model["model_id"]),
                deployment_id=deployment.id,
                threshold_policy_id=str(threshold_policy["threshold_policy_sha256"]),
            )
            for run in (anomaly_run, normal_run, isolated_run):
                session.add(
                    Turbine(
                        id=run.online_turbine_id,
                        wind_farm_id="WF-EAST-01",
                        model="CARE v6 isolated replay",
                        status="running",
                        health_score=100,
                    )
                )
            await session.flush()
            for run in (anomaly_run, normal_run, isolated_run):
                persisted, replayed = await register_replay_run(
                    session,
                    _request_for_run(
                        run,
                        model_version=str(model["model_version"]),
                        threshold_policy=threshold_policy,
                    ),
                    subject=SUBJECT,
                )
                assert persisted.id == run.benchmark_replay_run_id
                assert replayed is False

        all_turbines = [
            anomaly_run.online_turbine_id,
            normal_run.online_turbine_id,
            isolated_run.online_turbine_id,
        ]
        variable_contracts = {
            value.canonical_variable: TelemetryVariablePolicy(
                label=f"CARE {value.canonical_variable}",
                unit=value.unit,
                normal_min=-1_000_000_000_000.0,
                normal_max=1_000_000_000_000.0,
            )
            for value in variables
        }
        settings.telemetry_source_policies[CARE_REPLAY_SOURCE_ID] = TelemetrySourcePolicy(
            display_name="CARE v6 governed replay",
            source_kind="rest",
            sequence_required=True,
            max_lateness_seconds=86_400,
            max_future_skew_seconds=3_600,
            expected_heartbeat_seconds=600,
            allowed_turbines=all_turbines,
            allowed_variables=list(variable_contracts),
            variable_contracts=variable_contracts,
        )
        started_at = datetime.now(UTC)
        anomaly_run = transition_replay_run(anomaly_run, "running", at=started_at)
        normal_run = transition_replay_run(normal_run, "running", at=started_at)
        isolated_run = transition_replay_run(isolated_run, "running", at=started_at)
        for run in (anomaly_run, normal_run, isolated_run):
            assert (
                await _persist_run(
                    app,
                    run,
                    model_version=str(model["model_version"]),
                    threshold_policy=threshold_policy,
                )
                is False
            )

        anomaly_run, first_prediction, first_alert = await _process_row(
            app,
            client,
            anomaly_run,
            rows_by_event[0][0],
            model_version=str(model["model_version"]),
            threshold_policy=threshold_policy,
            ingest_timings=ingest_timings,
            ingest_sql_profiles=ingest_sql_profiles,
            retry=True,
        )
        assert first_prediction["output"]["binary_prediction"] is True
        assert first_alert["action"] == "none"
        assert first_alert["state_revision"] == 1
        assert inference_client.call_count == 1

    # A fresh application/session factory must restore the persisted policy state.
    async with _running_app(settings, inference_client) as (app, client):
        anomaly_alerts = [first_alert]
        anomaly_predictions = [first_prediction]
        for row in rows_by_event[0][1:]:
            anomaly_run, prediction, alert = await _process_row(
                app,
                client,
                anomaly_run,
                row,
                model_version=str(model["model_version"]),
                threshold_policy=threshold_policy,
                ingest_timings=ingest_timings,
                ingest_sql_profiles=ingest_sql_profiles,
            )
            anomaly_predictions.append(prediction)
            anomaly_alerts.append(alert)
        assert [value["action"] for value in anomaly_alerts] == ["none", "none", "trigger"]
        trigger = anomaly_alerts[-1]
        assert trigger["alarm_id"]
        assert trigger["mission_id"]

        normal_alerts: list[dict[str, Any]] = []
        normal_predictions: list[dict[str, Any]] = []
        for row in rows_by_event[24]:
            normal_run, prediction, alert = await _process_row(
                app,
                client,
                normal_run,
                row,
                model_version=str(model["model_version"]),
                threshold_policy=threshold_policy,
                ingest_timings=ingest_timings,
                ingest_sql_profiles=ingest_sql_profiles,
            )
            normal_predictions.append(prediction)
            normal_alerts.append(alert)
        assert not all(value["output"]["binary_prediction"] for value in normal_predictions)
        assert all(value["alarm_id"] is None for value in normal_alerts)
        assert all(value["mission_id"] is None for value in normal_alerts)

        isolated_rows = load_replay_rows(
            imported,
            import_root,
            event_id=0,
            start_source_row_id=isolated_run.window_start_row_id,
            end_source_row_id=isolated_run.window_end_row_id,
            variables=variables,
        )
        isolated_run, isolated_prediction, isolated_alert = await _process_row(
            app,
            client,
            isolated_run,
            isolated_rows[0],
            model_version=str(model["model_version"]),
            threshold_policy=threshold_policy,
            ingest_timings=ingest_timings,
            ingest_sql_profiles=ingest_sql_profiles,
        )
        assert isolated_prediction["output"]["binary_prediction"] is True
        assert isolated_alert["action"] == "none"
        assert isolated_alert["state_revision"] == 1
        assert isolated_prediction["prediction_id"] != first_prediction["prediction_id"]
        assert inference_client.call_count == 7

        finished_at = datetime.now(UTC)
        anomaly_run = transition_replay_run(anomaly_run, "completed", at=finished_at)
        normal_run = transition_replay_run(normal_run, "completed", at=finished_at)
        isolated_run = transition_replay_run(isolated_run, "completed", at=finished_at)
        for run in (anomaly_run, normal_run, isolated_run):
            assert (
                await _persist_run(
                    app,
                    run,
                    model_version=str(model["model_version"]),
                    threshold_policy=threshold_policy,
                )
                is False
            )
            assert (
                await _persist_run(
                    app,
                    run,
                    model_version=str(model["model_version"]),
                    threshold_policy=threshold_policy,
                )
                is True
            )

        mission_id = str(trigger["mission_id"])
        mission_detail = await client.get(
            f"/api/v1/missions/{mission_id}",
            headers=_headers("operations_manager"),
        )
        assert mission_detail.status_code == 200, mission_detail.text
        mission_payload = mission_detail.json()
        assert mission_payload["status"] == "under_review"
        assert mission_payload["public_state"]["diagnosis"]
        assert mission_payload["public_state"]["alternatives"]
        assert mission_payload["public_state"]["decision_id"]

        diagnoses = await client.get(
            "/api/v1/diagnoses",
            headers=_headers("operations_manager"),
            params={"limit": 50},
        )
        assert diagnoses.status_code == 200, diagnoses.text
        assert any(item["missionId"] == mission_id for item in diagnoses.json()["data"])
        decisions = await client.get(
            "/api/v1/decisions",
            headers=_headers("operations_manager"),
        )
        assert decisions.status_code == 200, decisions.text
        assert any(item["mission_id"] == mission_id for item in decisions.json()["decisions"])

        benchmark_headers = {
            "X-WindOps-Test-Principal": "care-benchmark-reader",
            "X-WindOps-Test-Role": "operations_manager",
            "X-WindOps-Test-Tenant-Ids": "tenant-east-china",
            "X-WindOps-Test-Data-Scopes": "benchmark",
        }
        benchmark_catalog = await client.get(
            "/api/v1/benchmarks/datasets?limit=10",
            headers=benchmark_headers,
        )
        assert benchmark_catalog.status_code == 200, benchmark_catalog.text
        benchmark_body = benchmark_catalog.json()
        assert benchmark_body["meta"]["filtered_total"] == 1
        assert benchmark_body["meta"]["bounds"]["dataset_page_max"] == 50
        assert benchmark_body["data"][0]["dataset_version_id"] == "care-v6"
        assert benchmark_body["data"][0]["coverage"]["registered_event_count"] == 2
        assert benchmark_body["data"][0]["coverage"]["time_point_count"] == 109_989
        assert benchmark_body["data"][0]["coverage"]["truth_summary"] == {
            "access": "restricted",
            "anomaly_event_count": None,
            "normal_event_count": None,
        }
        assert benchmark_body["data"][0]["mapping"]["total"] == 81
        assert benchmark_body["data"][0]["mapping"]["enabled"] == 54
        assert benchmark_body["data"][0]["runs"]["evaluation"]["completed"] == 2
        assert benchmark_body["data"][0]["runs"]["replay"]["completed"] == 3

        benchmark_events = await client.get(
            "/api/v1/benchmarks/datasets/care-v6/events?limit=12",
            headers=benchmark_headers,
        )
        assert benchmark_events.status_code == 200, benchmark_events.text
        event_body = benchmark_events.json()
        assert event_body["meta"]["filtered_total"] == 2
        assert all(value["truth"]["event_label"] is None for value in event_body["data"])
        assert all(value["truth"]["access"] == "restricted" for value in event_body["data"])
        truth_denied = await client.get(
            "/api/v1/benchmarks/datasets/care-v6/events?revealTruth=true",
            headers=benchmark_headers,
        )
        assert truth_denied.status_code == 403
        assert truth_denied.json()["error"]["code"] == "BENCHMARK_TRUTH_FORBIDDEN"

        curve = await client.get(
            f"/api/v1/benchmarks/replay-runs/{ANOMALY_RUN_ID}/curve",
            params={"variable": variables[0].canonical_variable, "maxPoints": 16},
            headers=benchmark_headers,
        )
        assert curve.status_code == 200, curve.text
        curve_body = curve.json()
        assert 1 <= len(curve_body["data"]) <= 16
        assert curve_body["meta"]["source_point_count"] == 3
        assert curve_body["meta"]["bounded"] is True
        assert curve_body["meta"]["raw_csv_loaded"] is False
        assert curve_body["meta"]["truth_included"] is False
        assert all(value["observed_at_is_synthetic"] is True for value in curve_body["data"])

        governed_catalog = await client.get(
            "/api/v1/data-catalog?category=benchmark&limit=1",
            headers={
                **benchmark_headers,
                "X-WindOps-Test-Data-Scopes": "platform,benchmark",
            },
        )
        assert governed_catalog.status_code == 200, governed_catalog.text
        assert governed_catalog.json()["data"][0]["id"] == "BENCHMARK-care-v6"

        benchmark_model_headers = {
            **benchmark_headers,
            "X-WindOps-Test-Data-Scopes": "benchmark,model,mission",
        }
        benchmark_evaluations = await client.get(
            "/api/v1/benchmarks/evaluations",
            params={"modelId": model["model_id"], "limit": 16},
            headers=benchmark_model_headers,
        )
        assert benchmark_evaluations.status_code == 200, benchmark_evaluations.text
        evaluation_body = benchmark_evaluations.json()
        assert evaluation_body["meta"]["filtered_total"] == 1
        evaluation_row = evaluation_body["data"][0]
        assert evaluation_row["model"]["kind"] == "anomaly"
        assert evaluation_row["model"]["evaluation_role"] == "target"
        assert evaluation_row["model"]["algorithm"]
        assert evaluation_row["run"]["prediction_truth_used"] is False
        assert evaluation_row["run"]["dependency_identity"]
        assert evaluation_row["event_accounting"] == {
            "requested": 2,
            "scored": 2,
            "failed": 0,
            "unscorable": 0,
        }
        assert evaluation_row["evaluation_artifact"]["immutable"] is True
        assert any(metric["is_release_metric"] for metric in evaluation_row["metrics"])
        assert any(
            deployment["authorization_state"] == "current"
            for deployment in evaluation_row["deployments"]
        )

        evaluation_results = await client.get(
            f"/api/v1/benchmarks/evaluations/{model['evaluation_run_id']}/results",
            params={"limit": 64},
            headers=benchmark_model_headers,
        )
        assert evaluation_results.status_code == 200, evaluation_results.text
        result_body = evaluation_results.json()
        assert result_body["meta"]["filtered_total"] == 2
        assert result_body["meta"]["truth_revealed"] is False
        assert all(result["truth"]["event_label"] is None for result in result_body["data"])
        assert all(
            result["status"] in {"scored", "failed", "unscorable"} for result in result_body["data"]
        )

        benchmark_diagnoses = await client.get(
            "/api/v1/benchmarks/diagnoses",
            params={"limit": 16},
            headers=benchmark_model_headers,
        )
        assert benchmark_diagnoses.status_code == 200, benchmark_diagnoses.text
        diagnosis_body = benchmark_diagnoses.json()
        assert diagnosis_body["meta"]["filtered_total"] == 3
        assert diagnosis_body["meta"]["truth_revealed"] is False
        diagnosis_by_run = {value["replay_run_id"]: value for value in diagnosis_body["data"]}
        anomaly_diagnosis = diagnosis_by_run[ANOMALY_RUN_ID]
        normal_diagnosis = diagnosis_by_run[NORMAL_RUN_ID]
        assert anomaly_diagnosis["replay"]["time_semantics"] == (
            "synthetic-replay-time-not-field-time"
        )
        assert anomaly_diagnosis["deployment"]["stale"] is False
        assert len(anomaly_diagnosis["predictions"]) == 3
        assert anomaly_diagnosis["first_alert"]["alarm_id"] == trigger["alarm_id"]
        assert anomaly_diagnosis["first_alert"]["mission_id"] == mission_id
        assert anomaly_diagnosis["first_alert"]["lead_source_rows"] is None
        assert anomaly_diagnosis["first_alert"]["lead_semantics"] == ("source-row-offset-not-rul")
        assert all(
            prediction["time_evidence"]["observed_at_is_synthetic"] is True
            and prediction["time_evidence"]["anonymous_observed_at"]
            and prediction["threshold"]["value"] is not None
            and prediction["evidence_artifact"]["present"] is True
            for prediction in anomaly_diagnosis["predictions"]
        )
        assert len(normal_diagnosis["predictions"]) == 3
        assert normal_diagnosis["first_alert"] is None
        assert "remaining_useful_life" not in benchmark_diagnoses.text
        assert "failure_probability_30d" not in benchmark_diagnoses.text

        truth_headers = {
            **benchmark_model_headers,
            "X-WindOps-Test-Data-Scopes": "benchmark,model,mission,benchmark_truth",
        }
        revealed_diagnoses = await client.get(
            "/api/v1/benchmarks/diagnoses",
            params={"limit": 16, "revealTruth": "true"},
            headers=truth_headers,
        )
        assert revealed_diagnoses.status_code == 200, revealed_diagnoses.text
        revealed_by_run = {
            value["replay_run_id"]: value for value in revealed_diagnoses.json()["data"]
        }
        assert revealed_by_run[ANOMALY_RUN_ID]["truth"]["event_label"] == "anomaly"
        assert revealed_by_run[NORMAL_RUN_ID]["truth"]["event_label"] == "normal"
        assert (
            revealed_by_run[ANOMALY_RUN_ID]["first_alert"]["lead_semantics"]
            == "source-row-offset-not-rul"
        )

        export_headers = {
            **benchmark_model_headers,
            "X-WindOps-Test-Data-Scopes": "benchmark,model,benchmark_export",
            "Idempotency-Key": "care-real-pg-export-0001",
        }
        export_path = f"/api/v1/benchmarks/evaluations/{model['evaluation_run_id']}/exports"
        export_request = {
            "format": "json",
            "distribution": "internal",
            "includeTruth": False,
            "changesMade": (
                "Exported the governed real PostgreSQL evaluation summary without raw signals."
            ),
            "expectedSourceArtifactSha256": evaluation_row["evaluation_artifact"]["sha256"],
            "attributionConfirmed": False,
            "licenseLinkConfirmed": False,
            "shareAlikeConfirmed": False,
            "legalReviewReference": None,
        }
        governed_export = await client.post(
            export_path,
            headers=export_headers,
            json=export_request,
        )
        assert governed_export.status_code == 200, governed_export.text
        assert governed_export.json()["license"]["doi"] == "10.5281/zenodo.15846963"
        assert governed_export.json()["license"]["share_alike_required"] is True
        assert governed_export.json()["report"]["truth_included"] is False
        assert "event_description" not in governed_export.text
        assert (
            governed_export.headers["x-windops-artifact-sha256"]
            == hashlib.sha256(governed_export.content).hexdigest()
        )
        repeated_export = await client.post(
            export_path,
            headers=export_headers,
            json=export_request,
        )
        assert repeated_export.status_code == 200, repeated_export.text
        assert repeated_export.content == governed_export.content
        assert repeated_export.headers["x-windops-export-replayed"] == "true"

        external_denied = await client.post(
            export_path,
            headers={**export_headers, "Idempotency-Key": "care-real-pg-export-denied"},
            json={
                **export_request,
                "format": "csv",
                "distribution": "external",
            },
        )
        assert external_denied.status_code == 403
        assert external_denied.json()["error"]["code"] == ("BENCHMARK_EXPORT_REVIEW_REQUIRED")

        async with app.state.session_factory() as session:
            alarm = await session.get(Alarm, str(trigger["alarm_id"]))
            mission = await session.get(Mission, mission_id)
            assert alarm is not None and mission is not None
            assert alarm.source_event_id is None
            assert alarm.model_prediction_id == anomaly_predictions[-1]["prediction_id"]
            assert mission.alarm_id == alarm.id
            assert mission.status == "under_review"
            trace = await build_benchmark_trace(session, alarm_id=alarm.id)
            assert trace.dataset_version_id == "care-v6"
            assert trace.event_id == "care-v6-event-a-0"
            assert trace.model_id == model["model_id"]
            assert trace.model_version == model["model_version"]
            assert trace.evaluation_run_id == model["evaluation_run_id"]
            assert trace.replay_run_id == ANOMALY_RUN_ID
            assert trace.prediction_id == alarm.model_prediction_id
            assert trace.alarm_id == alarm.id
            assert trace.source_event_id is None

            assert int(await session.scalar(select(func.count(ScadaSample.id))) or 0) == 7 * 54
            assert (
                int(await session.scalar(select(func.count(IngestReceipt.source_event_id))) or 0)
                == 7 * 54
            )
            assert int(await session.scalar(select(func.count(ModelPrediction.id))) or 0) == 7
            assert int(await session.scalar(select(func.count(Alarm.id))) or 0) == 1
            assert int(await session.scalar(select(func.count(Mission.id))) or 0) == 1
            assert (
                int(await session.scalar(select(func.count(AnomalyAlertPolicyState.id))) or 0) == 3
            )
            assert (
                int(
                    await session.scalar(
                        select(func.count(PersistedReplayRun.id)).where(
                            PersistedReplayRun.id.in_(
                                [ANOMALY_RUN_ID, NORMAL_RUN_ID, ISOLATED_RUN_ID]
                            ),
                            PersistedReplayRun.status == "completed",
                        )
                    )
                    or 0
                )
                == 3
            )
            states = {
                value.turbine_id: value
                for value in (await session.scalars(select(AnomalyAlertPolicyState))).all()
            }
            assert states[anomaly_run.online_turbine_id].revision == 3
            assert states[anomaly_run.online_turbine_id].phase == "active"
            assert states[normal_run.online_turbine_id].revision == 3
            assert states[normal_run.online_turbine_id].phase != "active"
            assert states[isolated_run.online_turbine_id].revision == 1
            assert states[isolated_run.online_turbine_id].phase == "triggering"
            assert int(await session.scalar(select(func.count(Decision.id))) or 0) == 1
            evidence_rows = list(
                (
                    await session.scalars(select(Evidence).where(Evidence.mission_id == mission_id))
                ).all()
            )
            assert {value.evidence_type for value in evidence_rows} == {
                "condition_signal",
                "knowledge_citation",
                "scada_anomaly",
            }
            assert all(value.source_refs for value in evidence_rows)
            assert int(await session.scalar(select(func.count(AgentExecution.id))) or 0) >= 6
            assert int(await session.scalar(select(func.count(CommandReceipt.id))) or 0) >= 14
            export_audits = list(
                (
                    await session.scalars(
                        select(DomainEvent).where(DomainEvent.aggregate_type == "benchmark_export")
                    )
                ).all()
            )
            assert {value.event_type for value in export_audits} == {
                "benchmark.export.completed",
                "benchmark.export.denied",
            }
            assert (
                sum(value.event_type == "benchmark.export.completed" for value in export_audits)
                == 1
            )
            governance_event_types = set(
                (
                    await session.scalars(
                        select(DomainEvent.event_type).where(
                            DomainEvent.event_type.in_(
                                [
                                    "benchmark.import.registered",
                                    "benchmark.transform.quality.completed",
                                    "benchmark.evaluation.completed",
                                    "benchmark.replay.registered",
                                ]
                            )
                        )
                    )
                ).all()
            )
            assert governance_event_types == {
                "benchmark.import.registered",
                "benchmark.transform.quality.completed",
                "benchmark.evaluation.completed",
                "benchmark.replay.registered",
            }

            events = list(
                (
                    await session.scalars(
                        select(DomainEvent).where(
                            DomainEvent.event_type.in_(
                                [
                                    "model.anomaly-alert.evaluated",
                                    "alarm.opened.from-model-prediction",
                                    "mission.created",
                                    "mission.review_ready",
                                ]
                            )
                        )
                    )
                ).all()
            )
            event_types = {value.event_type for value in events}
            assert event_types == {
                "model.anomaly-alert.evaluated",
                "alarm.opened.from-model-prediction",
                "mission.created",
                "mission.review_ready",
            }
            assert all(
                "ground_truth" not in json.dumps(value.payload, sort_keys=True) for value in events
            )
            for prediction in (
                await session.scalars(select(ModelPrediction).order_by(ModelPrediction.id))
            ).all():
                persisted = json.dumps(
                    {
                        "input": prediction.input_snapshot,
                        "output": prediction.output,
                    },
                    sort_keys=True,
                )
                assert "ground_truth" not in persisted
                assert '"event_label"' not in persisted
                assert prediction.benchmark_replay_run_id in {
                    ANOMALY_RUN_ID,
                    NORMAL_RUN_ID,
                    ISOLATED_RUN_ID,
                }

    assert len(ingest_timings) == 7
    assert len(ingest_sql_profiles) == 7
    replay_write_rows_per_second = (7 * 54) / sum(ingest_timings)
    record_testsuite_property("care.ingested_samples", str(7 * 54))
    record_testsuite_property("care.replay_write_elapsed_seconds", f"{sum(ingest_timings):.6f}")
    record_testsuite_property(
        "care.replay_write_batch_seconds",
        ",".join(f"{elapsed:.6f}" for elapsed in ingest_timings),
    )
    record_testsuite_property(
        "care.replay_write_rows_per_second", f"{replay_write_rows_per_second:.3f}"
    )
    record_testsuite_property(
        "care.replay_write_sql_statements",
        ",".join(str(profile.statement_count) for profile in ingest_sql_profiles),
    )
    record_testsuite_property(
        "care.replay_write_sql_seconds",
        ",".join(f"{profile.elapsed_seconds:.6f}" for profile in ingest_sql_profiles),
    )
    record_testsuite_property(
        "care.replay_write_max_batch_sql_statements",
        str(max(profile.statement_count for profile in ingest_sql_profiles)),
    )
    record_testsuite_property(
        "care.replay_write_db_elapsed_seconds",
        f"{sum(profile.elapsed_seconds for profile in ingest_sql_profiles):.6f}",
    )
    record_testsuite_property(
        "care.replay_write_min_rows_per_second",
        f"{MIN_REPLAY_WRITE_ROWS_PER_SECOND:.3f}",
    )
    assert all(
        profile.statement_count <= MAX_REPLAY_WRITE_SQL_STATEMENTS_PER_BATCH
        for profile in ingest_sql_profiles
    )
    assert replay_write_rows_per_second >= MIN_REPLAY_WRITE_ROWS_PER_SECOND
    record_testsuite_property("care.dataset_version", "v6")
    record_testsuite_property("care.contract_sha256", source_manifest["manifest_sha256"])
    record_testsuite_property(
        "care.import_identity_sha256", imported["immutable_registration_identity"]
    )
    record_testsuite_property(
        "care.evaluation_identity_sha256", evaluated["evaluation_identity_sha256"]
    )
    record_testsuite_property("care.model_id", model["model_id"])
    record_testsuite_property("care.model_version", model["model_version"])
    record_testsuite_property("care.model_package_sha256", package["model_package_sha256"])
    record_testsuite_property(
        "care.replay_run_ids",
        ",".join((ANOMALY_RUN_ID, NORMAL_RUN_ID, ISOLATED_RUN_ID)),
    )
    record_testsuite_property("care.predictions", "7")
    record_testsuite_property("care.alarms", "1")
    record_testsuite_property("care.missions", "1")
    record_testsuite_property("care.decisions", "1")
    record_testsuite_property(
        "care.evidence_types", "condition_signal,knowledge_citation,scada_anomaly"
    )
    record_testsuite_property("care.normal_event_alarm_suppressed", "true")
    record_testsuite_property("care.restart_state_restored", "true")
    record_testsuite_property("care.same_run_idempotent", "true")
    record_testsuite_property("care.new_run_isolated", "true")
    record_testsuite_property("care.prediction_truth_used", "false")
    record_testsuite_property("care.benchmark_api_dataset_count", "1")
    record_testsuite_property("care.benchmark_api_event_count", "2")
    record_testsuite_property("care.benchmark_api_curve_point_max", "16")
    record_testsuite_property("care.benchmark_api_raw_csv_loaded", "false")
    record_testsuite_property("care.benchmark_api_truth_scope_enforced", "true")
    record_testsuite_property("care.model_ui_evaluation_count", "1")
    record_testsuite_property("care.model_ui_event_result_count", "2")
    record_testsuite_property("care.diagnosis_ui_replay_count", "3")
    record_testsuite_property("care.diagnosis_ui_prediction_count", "7")
    record_testsuite_property("care.diagnosis_ui_truth_scope_enforced", "true")
    record_testsuite_property("care.export_json_count", "1")
    record_testsuite_property("care.export_idempotent", "true")
    record_testsuite_property("care.export_sharealike_gate_enforced", "true")


@pytest.mark.asyncio
async def test_same_database_stage_upgrade_is_append_only_and_concurrently_idempotent(
    record_testsuite_property: Any,
) -> None:
    """Append full-scale evidence to the database populated by the vertical slice."""

    base_root = _artifact_root()
    full_root = _full_scale_root()
    source_manifest = _read_json(base_root / "contract/manifest.json")
    quality = _read_json(base_root / "quality/quality-contract.json")
    minimal_import = _read_json(
        base_root / "minimal-import/care/v6/reports/a-minimal-import/manifest.json"
    )
    full_import = _read_json(full_root / "care/v6/reports/full-import/manifest.json")
    full_evaluation = _read_json(full_root / "care/v6/reports/full-evaluation/manifest.json")
    metric_count = sum(
        5
        + sum(
            summary.get(name) is not None
            for name in (
                "care_score",
                "normal_event_false_positive_rate",
                "event_detection_rate",
            )
        )
        for summary in full_evaluation["fold_summaries"]
    )
    expected_evaluation_records = 3 + 36 + 95 + metric_count

    settings = Settings(
        environment=Environment.TEST,
        database_url=_database_url(),
        schema_bootstrap=False,
        demo_seed=True,
        test_auth_bypass_enabled=True,
        knowledge_graph_backend="memory",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        first_full_event = next(event for event in full_import["events"] if event["event_id"] == 0)
        first_full_quality = first_full_event["quality"]
        first_full_quality_request = BenchmarkQualityReportCreateRequest(
            quality_report_id="care-v6-quality-a-0",
            event_id="care-v6-event-a-0",
            quality_rule_version=QUALITY_RULE_VERSION,
            feature_set_version=FEATURE_SET_VERSION,
            canonical_content_sha256=str(first_full_quality["source_quality_report_sha256"]),
            artifact_stage="full-scale-import",
            status="completed",
            artifact_uri=str(first_full_quality["report"]["artifact_uri"]),
            artifact_sha256=str(first_full_quality["report"]["file_sha256"]),
            mask_uri=str(first_full_quality["mask"]["artifact_uri"]),
            mask_sha256=str(first_full_quality["mask"]["file_sha256"]),
            summary={
                "row_count": first_full_event["row_count"],
                "feature_summary_count": first_full_quality["feature_summary_count"],
                "mask_count": first_full_quality["mask_count"],
                "raw_values_modified": False,
            },
        )

        async def register_first_quality_stage() -> bool:
            async with app.state.session_factory() as session, session.begin():
                _row, replayed = await register_quality_report(
                    session,
                    first_full_quality_request,
                    subject=FULL_SCALE_SUBJECT,
                )
            return replayed

        assert sorted(
            await asyncio.gather(
                register_first_quality_stage(),
                register_first_quality_stage(),
            )
        ) == [False, True]

        async def register_all() -> tuple[Any, Any]:
            async with app.state.session_factory() as session, session.begin():
                imported = await register_full_scale_import(
                    session,
                    full_import,
                    source_manifest,
                    quality,
                    artifact_root=full_root,
                    tenant_id="tenant-east-china",
                    subject=FULL_SCALE_SUBJECT,
                )
                evaluated = await register_full_scale_evaluation(
                    session,
                    full_evaluation,
                    full_import,
                    artifact_root=full_root,
                    subject=FULL_SCALE_SUBJECT,
                )
            return imported, evaluated

        imported, evaluated = await register_all()
        assert (imported.created_count, imported.replayed_count) == (1484, 87)
        assert (evaluated.created_count, evaluated.replayed_count) == (
            expected_evaluation_records,
            0,
        )
        assert await asyncio.gather(
            register_first_quality_stage(),
            register_first_quality_stage(),
        ) == [True, True]

        async with app.state.session_factory() as session:
            quality_reports = list((await session.scalars(select(BenchmarkQualityReport))).all())
            quality_artifacts = list(
                (await session.scalars(select(BenchmarkQualityArtifact))).all()
            )
            quality_events = list(
                (
                    await session.scalars(
                        select(DomainEvent).where(
                            DomainEvent.event_type == "benchmark.transform.quality.completed"
                        )
                    )
                ).all()
            )
            assert len(quality_reports) == 95
            assert all(row.canonical_content_sha256 is not None for row in quality_reports)
            assert len(quality_artifacts) == 97
            assert sum(row.artifact_stage == "minimal-import" for row in quality_artifacts) == 2
            assert sum(row.artifact_stage == "full-scale-import" for row in quality_artifacts) == 95
            assert sum(row.audit_subject == SUBJECT for row in quality_artifacts) == 2
            assert sum(row.audit_subject == FULL_SCALE_SUBJECT for row in quality_artifacts) == 95
            assert len(quality_events) == 97
            assert sum(event.payload["requested_by"] == SUBJECT for event in quality_events) == 2
            assert (
                sum(event.payload["requested_by"] == FULL_SCALE_SUBJECT for event in quality_events)
                == 95
            )

            artifacts_by_report: dict[str, list[BenchmarkQualityArtifact]] = {}
            for artifact in quality_artifacts:
                artifacts_by_report.setdefault(artifact.quality_report_id, []).append(artifact)
            minimal_quality_by_report = {
                f"care-v6-quality-{str(minimal_import['farm']).lower()}-{event['event_id']}": event[
                    "quality"
                ]
                for event in minimal_import["events"]
            }
            reports_by_id = {report.id: report for report in quality_reports}
            for report_id, minimal_quality in minimal_quality_by_report.items():
                report = reports_by_id[report_id]
                assert (
                    report.canonical_content_sha256
                    == minimal_quality["source_quality_report_sha256"]
                )
                assert report.artifact_sha256 == minimal_quality["report"]["file_sha256"]
                assert report.mask_sha256 == minimal_quality["mask"]["file_sha256"]
                assert {artifact.artifact_stage for artifact in artifacts_by_report[report_id]} == {
                    "minimal-import",
                    "full-scale-import",
                }

            assert int(await session.scalar(select(func.count()).select_from(Alarm)) or 0) == 1
            assert int(await session.scalar(select(func.count()).select_from(Mission)) or 0) == 1
            assert int(await session.scalar(select(func.count()).select_from(Decision)) or 0) == 1

    record_testsuite_property("care.stage_upgrade.import_created", "1484")
    record_testsuite_property("care.stage_upgrade.import_preexisting_replayed", "87")
    record_testsuite_property(
        "care.stage_upgrade.evaluation_records", str(expected_evaluation_records)
    )
    record_testsuite_property("care.stage_upgrade.quality_parent_count", "95")
    record_testsuite_property("care.stage_upgrade.quality_artifact_count", "97")
    record_testsuite_property("care.stage_upgrade.concurrent_create_exact", "true")
    record_testsuite_property("care.stage_upgrade.concurrent_replay_exact", "true")
    record_testsuite_property(
        "care.stage_upgrade.full_import_manifest_sha256", full_import["manifest_sha256"]
    )
    record_testsuite_property(
        "care.stage_upgrade.full_evaluation_manifest_sha256",
        full_evaluation["manifest_sha256"],
    )
    record_testsuite_property(
        "care.stage_upgrade.approved_root_sha256",
        full_evaluation["care_approval"]["approved_root_sha256"],
    )
