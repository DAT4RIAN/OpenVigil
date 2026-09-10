import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select

from windops_backend.benchmarks.care.replay import CARE_REPLAY_SOURCE_ID
from windops_backend.models import (
    Alarm,
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkEvent,
    BenchmarkEventResult,
    BenchmarkFeatureMap,
    BenchmarkFile,
    BenchmarkMetricSnapshot,
    BenchmarkQualityReport,
    BenchmarkReplayRun,
    DomainEvent,
    IngestReceipt,
    IngestSource,
    Mission,
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
    ScadaSample,
    Tenant,
    Turbine,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _headers(*scopes: str, tenant_id: str = "tenant-east-china") -> dict[str, str]:
    return {
        "X-WindOps-Test-Principal": "benchmark-reader",
        "X-WindOps-Test-Role": "operations_manager",
        "X-WindOps-Test-Tenant-Ids": tenant_id,
        "X-WindOps-Test-Data-Scopes": ",".join(scopes),
    }


async def _seed_benchmark_dataset_only(app: FastAPI) -> None:
    anchor = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
    async with app.state.session_factory() as session, session.begin():
        session.add(
            BenchmarkDatasetVersion(
                id="care-v6",
                tenant_id="tenant-east-china",
                dataset_id="CARE",
                version="v6",
                status="ready",
                source_uri="file:///governed-read-only/CARE_To_Compare",
                manifest_uri="minio://care/raw/manifest.json",
                manifest_sha256=HASH_A,
                content_sha256=HASH_B,
                source_archive_md5="c" * 32,
                source_archive_sha256=HASH_C,
                size_bytes=5_908_333_109,
                file_count=101,
                license_name="CC BY-SA 4.0",
                license_url="https://creativecommons.org/licenses/by-sa/4.0/",
                doi="10.5281/zenodo.15846963",
                citation=(
                    "G\u00fcck, C.; Roelofs, C.M.A.; Faulstich, S. CARE to Compare: A Real-World "
                    "Benchmark Dataset for Early Fault Detection in Wind Turbine Data."
                ),
                attribution={
                    "creators": ["Christian G\u00fcck", "Cyriana M. A. Roelofs"],
                    "changes_made": True,
                    "share_alike_review": "required",
                },
                created_by="catalog-test",
                created_at=anchor,
            )
        )


async def _seed_benchmark_model_and_diagnosis(app: FastAPI) -> None:
    await _seed_benchmark_dataset_only(app)
    anchor = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
    async with app.state.session_factory() as session, session.begin():
        model = RegisteredModel(
            id="care-anomaly-model",
            name="CARE deterministic target",
            version="1.0.0",
            kind="anomaly",
            status="active",
            artifact_uri="minio://care/reports/models/target/package.json",
            artifact_sha256=HASH_A,
            content_type="application/json",
            content_size_bytes=4096,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            metrics={
                "algorithm": "care-random-projection-squared-distance-v1",
                "evaluation_role": "target",
                "dependency_identity": {"numpy": "2.4.2"},
            },
            description="truth-free anomaly model",
            created_by="catalog-test",
            created_at=anchor,
            updated_at=anchor,
        )
        session.add(model)
        deployment = ModelDeployment(
            id="care-deployment-0001",
            model_id=model.id,
            target_id="care-json-runtime",
            stage="benchmark-development",
            status="active",
            traffic_percent=100,
            evaluation_gate={
                "server_authorization": {
                    "evaluation_run_id": "care-eval-complete",
                    "gate_policy_version": "care-gate-v1",
                    "authorized_at": anchor.isoformat(),
                }
            },
            deployed_by="catalog-test",
            deployed_at=anchor,
            activated_at=anchor,
        )
        session.add(deployment)
        evaluations = [
            BenchmarkEvaluationRun(
                id="care-eval-complete",
                dataset_version_id="care-v6",
                model_id=model.id,
                model_version=model.version,
                run_kind="final-holdout",
                protocol_version="care-a0-a24-final-holdout-v1",
                farm="A",
                status="completed",
                feature_set_version="care-v6-approved-avg-v1",
                quality_rule_version="care-v6-quality-rules-v1",
                threshold_policy_version="care-threshold-v1",
                threshold_policy_sha256=HASH_B,
                random_seed=20260826,
                input_identity_sha256=HASH_C,
                artifact_uri="minio://care/reports/evaluations/complete.json",
                artifact_sha256=HASH_A,
                requested_event_count=1,
                scored_event_count=1,
                failed_event_count=0,
                unscorable_event_count=0,
                extension_data={
                    "algorithm": "care-random-projection-squared-distance-v1",
                    "evaluation_role": "target",
                    "dependency_identity": {"numpy": "2.4.2"},
                    "prediction_truth_used": False,
                },
                created_by="catalog-test",
                created_at=anchor + timedelta(minutes=3),
                started_at=anchor + timedelta(minutes=3),
                completed_at=anchor + timedelta(minutes=4),
            ),
            BenchmarkEvaluationRun(
                id="care-eval-failed",
                dataset_version_id="care-v6",
                model_id=model.id,
                model_version=model.version,
                run_kind="final-holdout",
                protocol_version="care-a0-a24-final-holdout-v1",
                farm="A",
                status="completed",
                feature_set_version="care-v6-approved-avg-v1",
                quality_rule_version="care-v6-quality-rules-v1",
                threshold_policy_version="care-threshold-v1",
                threshold_policy_sha256=HASH_B,
                random_seed=20260826,
                input_identity_sha256="d" * 64,
                artifact_uri="minio://care/reports/evaluations/failed.json",
                artifact_sha256=HASH_B,
                requested_event_count=1,
                scored_event_count=0,
                failed_event_count=1,
                unscorable_event_count=0,
                extension_data={"prediction_truth_used": False},
                created_by="catalog-test",
                created_at=anchor + timedelta(minutes=2),
                started_at=anchor + timedelta(minutes=2),
                completed_at=anchor + timedelta(minutes=3),
            ),
            BenchmarkEvaluationRun(
                id="care-eval-unscorable",
                dataset_version_id="care-v6",
                model_id=model.id,
                model_version=model.version,
                run_kind="final-holdout",
                protocol_version="care-a0-a24-final-holdout-v1",
                farm="A",
                status="completed",
                feature_set_version="care-v6-approved-avg-v1",
                quality_rule_version="care-v6-quality-rules-v1",
                threshold_policy_version="care-threshold-v1",
                threshold_policy_sha256=HASH_B,
                random_seed=20260826,
                input_identity_sha256="e" * 64,
                artifact_uri="minio://care/reports/evaluations/unscorable.json",
                artifact_sha256=HASH_C,
                requested_event_count=1,
                scored_event_count=0,
                failed_event_count=0,
                unscorable_event_count=1,
                extension_data={"prediction_truth_used": False},
                created_by="catalog-test",
                created_at=anchor + timedelta(minutes=1),
                started_at=anchor + timedelta(minutes=1),
                completed_at=anchor + timedelta(minutes=2),
            ),
        ]
        session.add_all(evaluations)
        session.add_all(
            [
                BenchmarkMetricSnapshot(
                    id="care-eval-complete-care-score",
                    evaluation_run_id="care-eval-complete",
                    metric_name="care_score",
                    protocol_version="care-score-v6",
                    metric_version="care-metric-v1",
                    value=0.91,
                    unit="ratio",
                    is_release_metric=True,
                    threshold_value=0.5,
                    threshold_direction="gte",
                    passed=True,
                ),
                BenchmarkMetricSnapshot(
                    id="care-eval-failed-data-failure",
                    evaluation_run_id="care-eval-failed",
                    metric_name="data_failure_event_count",
                    protocol_version="care-score-v6",
                    metric_version="care-metric-v1",
                    value=1,
                    unit="events",
                    is_release_metric=True,
                    threshold_value=0,
                    threshold_direction="eq",
                    passed=False,
                ),
                BenchmarkMetricSnapshot(
                    id="care-eval-unscorable-count",
                    evaluation_run_id="care-eval-unscorable",
                    metric_name="unscorable_event_count",
                    protocol_version="care-score-v6",
                    metric_version="care-metric-v1",
                    value=1,
                    unit="events",
                    is_release_metric=True,
                    threshold_value=0,
                    threshold_direction="eq",
                    passed=False,
                ),
            ]
        )
        session.add_all(
            [
                BenchmarkEventResult(
                    id="care-result-scored",
                    evaluation_run_id="care-eval-complete",
                    event_id="care-event-a0",
                    status="scored",
                    scorable=True,
                    anomaly_detected=True,
                    care_score=0.91,
                    coverage_score=0.9,
                    accuracy_score=0.88,
                    reliability_score=1.0,
                    earliness_score=0.82,
                    prediction_artifact_uri="minio://care/predictions/a0.json",
                    prediction_artifact_sha256=HASH_A,
                    result_sha256="1" * 64,
                    details={
                        "event_label": "anomaly",
                        "failure_type": "restricted-bearing-description",
                        "evaluation_artifact_uri": "minio://care/reports/evaluations/complete.json",
                        "evaluation_artifact_sha256": HASH_A,
                    },
                ),
                BenchmarkEventResult(
                    id="care-result-failed",
                    evaluation_run_id="care-eval-failed",
                    event_id="care-event-a0",
                    status="failed",
                    scorable=False,
                    failure_code="PREDICTION_ARTIFACT_INVALID",
                    result_sha256="2" * 64,
                    details={"failure_type": "restricted-failure"},
                ),
                BenchmarkEventResult(
                    id="care-result-unscorable",
                    evaluation_run_id="care-eval-unscorable",
                    event_id="care-event-a0",
                    status="unscorable",
                    scorable=False,
                    failure_code="NO_SCORABLE_POINTS",
                    result_sha256="3" * 64,
                    details={"failure_type": "restricted-unscorable"},
                ),
            ]
        )
        replay = BenchmarkReplayRun(
            id="cat00001",
            dataset_version_id="care-v6",
            event_id="care-event-a0",
            source_asset_id="0",
            logical_asset_id="care-a-asset-0",
            online_turbine_id="WT-023",
            farm="A",
            source_event_number=0,
            replay_mode="historical-fixed",
            speed=1.0,
            status="completed",
            replay_anchor_at=anchor,
            time_rule_version="care-v6-synthetic-time-v1",
            sequence_rule_version="care-v6-sequence-v1",
            source_event_id_rule_version="care-v6-source-event-v1",
            selected_variables=[
                {"canonical_variable": "sensor_0.avg", "unit": "°C"},
                {"canonical_variable": "sensor_1.avg", "unit": "1"},
            ],
            window_start_row_id=0,
            window_end_row_id=39,
            checkpoint={"next_source_row_id": 40},
            checkpoint_revision=40,
            checkpoint_sha256=HASH_C,
            model_id=model.id,
            model_version=model.version,
            deployment_id=deployment.id,
            threshold_policy_version="care-threshold-v1",
            threshold_policy_sha256=HASH_B,
            created_by="catalog-test",
            created_at=anchor,
            started_at=anchor,
            finished_at=anchor + timedelta(minutes=1),
        )
        session.add(replay)
        prediction = ModelPrediction(
            id="care-prediction-0001",
            model_id=model.id,
            deployment_id=deployment.id,
            turbine_id="WT-023",
            feature_observed_at=anchor + timedelta(seconds=2),
            prediction_kind="anomaly",
            benchmark_replay_run_id=replay.id,
            benchmark_evaluation_run_id="care-eval-complete",
            feature_window_start=anchor + timedelta(seconds=2),
            feature_window_end=anchor + timedelta(seconds=2),
            feature_start_sequence=3,
            feature_end_sequence=3,
            anomaly_score=0.92,
            binary_prediction=True,
            component="unknown",
            threshold_policy_version="care-threshold-v1",
            threshold_policy_sha256=HASH_B,
            feature_set_version="care-v6-approved-avg-v1",
            quality_rule_version="care-v6-quality-rules-v1",
            evidence_artifact_uri="minio://care/reports/models/target/package.json",
            evidence_artifact_sha256=HASH_A,
            input_digest=HASH_C,
            input_snapshot={
                "signals": [
                    {
                        "quality": "uncertain",
                        "quality_mask_refs": ["mask://care-a0-row-2"],
                    }
                ]
            },
            output={
                "threshold_value": 0.8,
                "threshold_comparison": "strict-greater-than",
                "observed_at_time_claim": "synthetic-replay-time-not-field-time",
            },
            status="succeeded",
            latency_ms=7,
            requested_by="catalog-test",
            created_at=anchor + timedelta(seconds=2),
        )
        session.add(prediction)
        alarm = Alarm(
            id="care-alarm-0001",
            turbine_id="WT-023",
            model_prediction_id=prediction.id,
            code="CARE_ANOMALY",
            subsystem="unknown",
            title="Governed CARE anomaly",
            severity="major",
            status="open",
            ai_status="diagnosed",
            triggered_at=anchor + timedelta(seconds=2),
            evidence={"prediction_id": prediction.id},
        )
        session.add(alarm)
        session.add(
            Mission(
                id="CARE-MISSION-0001",
                alarm_id=alarm.id,
                turbine_id="WT-023",
                title="CARE anomaly review",
                status="under_review",
                public_state={
                    "diagnosis": {"component": "unknown", "confidence": 0.9},
                    "decision_id": "CARE-DECISION-0001",
                },
                created_at=anchor + timedelta(seconds=3),
                updated_at=anchor + timedelta(seconds=3),
            )
        )
        session.add(
            BenchmarkFile(
                id="care-file-a0",
                dataset_version_id="care-v6",
                file_kind="event",
                relative_path="WindFarmA/event_0.csv",
                farm="A",
                event_id=0,
                size_bytes=4096,
                row_count=40,
                schema_sha256=HASH_A,
                content_sha256=HASH_B,
                metadata_={
                    "standard_parquet": {
                        "uri": "minio://care/standard/dataset_version=care-v6/farm=A/event=0/data.parquet",
                        "sha256": HASH_C,
                    }
                },
            )
        )
        session.add(
            BenchmarkEvent(
                id="care-event-a0",
                dataset_version_id="care-v6",
                source_file_id="care-file-a0",
                event_id=0,
                farm="A",
                source_asset_id="0",
                logical_asset_id="care-a-asset-0",
                event_label="anomaly",
                first_source_row_id=0,
                last_source_row_id=39,
                train_row_count=30,
                prediction_row_count=10,
                event_interval_start=31,
                event_interval_end=39,
                truth_metadata={"description": "restricted"},
            )
        )
        session.add_all(
            [
                BenchmarkFeatureMap(
                    id=f"care-map-{index}",
                    dataset_version_id="care-v6",
                    mapping_version="care-v6-column-mapping-v1",
                    farm="A",
                    source_column=f"sensor_{index}_Avg",
                    canonical_feature=f"sensor_{index}.avg",
                    statistic="Avg",
                    unit="°C" if index == 0 else "unknown",
                    enabled=index < 2,
                    semantics={"raw_value_preserved": True},
                )
                for index in range(3)
            ]
        )
        session.add(
            BenchmarkQualityReport(
                id="care-quality-a0",
                event_id="care-event-a0",
                quality_rule_version="care-v6-quality-rules-v1",
                feature_set_version="care-v6-approved-avg-v1",
                status="completed",
                artifact_uri="minio://care/quality/a0/report.json",
                artifact_sha256=HASH_A,
                mask_uri="minio://care/quality/a0/mask.json",
                mask_sha256=HASH_B,
                summary={"mask_count": 4, "raw_values_modified": False},
            )
        )
        if await session.get(IngestSource, CARE_REPLAY_SOURCE_ID) is None:
            session.add(
                IngestSource(
                    id=CARE_REPLAY_SOURCE_ID,
                    display_name="CARE v6 replay",
                    source_kind="benchmark-replay",
                    policy={"dataset_version": "v6"},
                    status="ready",
                )
            )
        for index in range(40):
            source_event_id = f"catalog-care-run-row-{index:03}"
            observed_at = anchor + timedelta(seconds=index)
            session.add(
                IngestReceipt(
                    source_event_id=source_event_id,
                    source_id=CARE_REPLAY_SOURCE_ID,
                    payload_hash=f"{index + 1:064x}",
                )
            )
            session.add(
                ScadaSample(
                    id=f"catalog-sample-{index:03}",
                    observed_at=observed_at,
                    source_event_id=source_event_id,
                    source_id=CARE_REPLAY_SOURCE_ID,
                    source_sequence=index + 1,
                    turbine_id="WT-023",
                    variable="sensor_0.avg",
                    value=float(index),
                    unit="°C",
                    quality="good",
                    attributes={
                        "source_row_id": index,
                        "anonymous_observed_at": f"anonymous-{index}",
                        "source_time_stamp": index,
                        "status_type_id": 0,
                        "quality_mask_refs": [],
                        "observed_at_is_synthetic": True,
                        "time_claim": "synthetic-replay-time-not-field-time",
                    },
                )
            )

        session.add(Tenant(id="tenant-benchmark-other", name="Other benchmark tenant"))
        session.add(
            BenchmarkDatasetVersion(
                id="other-v1",
                tenant_id="tenant-benchmark-other",
                dataset_id="OTHER",
                version="v1",
                status="failed",
                source_uri="minio://other/raw",
                manifest_uri="minio://other/manifest.json",
                manifest_sha256="d" * 64,
                content_sha256="e" * 64,
                size_bytes=1,
                file_count=0,
                license_name="Proprietary",
                license_url="https://example.invalid/license",
                doi="not-applicable",
                citation="Other dataset",
                attribution={},
                created_by="catalog-test",
                created_at=anchor,
            )
        )


# Keep the public seed name used by the M001 tests while extending the same
# bounded fixture with the M002 model/diagnosis chain.
_seed_benchmark_catalog = _seed_benchmark_model_and_diagnosis


@pytest.mark.asyncio
async def test_benchmark_catalog_is_paginated_scoped_and_truth_restricted(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)

    unrestricted = await client.get("/api/v1/benchmarks/datasets?limit=1")
    assert unrestricted.status_code == 200, unrestricted.text
    unrestricted_body = unrestricted.json()
    assert unrestricted_body["meta"] == {
        **unrestricted_body["meta"],
        "count": 1,
        "total": 2,
        "filtered_total": 2,
        "offset": 0,
        "limit": 1,
        "has_more": True,
        "next_offset": 1,
    }
    assert unrestricted_body["meta"]["bounds"]["dataset_page_max"] == 50

    reader = _headers("benchmark")
    scoped = await client.get("/api/v1/benchmarks/datasets?q=care", headers=reader)
    assert scoped.status_code == 200, scoped.text
    body = scoped.json()
    assert body["meta"]["total"] == 1
    assert body["meta"]["filtered_total"] == 1
    assert [row["dataset_version_id"] for row in body["data"]] == ["care-v6"]
    dataset = body["data"][0]
    assert dataset["manifest"]["sha256"] == HASH_A
    assert dataset["archive"] == {
        "size_bytes": 5_908_333_109,
        "file_count": 101,
        "content_sha256": HASH_B,
        "md5": "c" * 32,
        "sha256": HASH_C,
    }
    assert dataset["license"]["doi"] == "10.5281/zenodo.15846963"
    assert dataset["coverage"]["registered_event_count"] == 1
    assert dataset["coverage"]["time_point_count"] == 40
    assert dataset["coverage"]["truth_summary"] == {
        "access": "restricted",
        "anomaly_event_count": None,
        "normal_event_count": None,
    }
    assert dataset["mapping"] == {
        "total": 3,
        "enabled": 2,
        "disabled": 1,
        "unknown_unit": 2,
        "failed": 0,
    }
    assert dataset["quality"]["mask_count"] == 4
    assert dataset["quality"]["raw_values_modified"] is False
    assert dataset["runs"]["replay"] == {"completed": 1}

    cross_tenant = await client.get("/api/v1/benchmarks/datasets/other-v1/events", headers=reader)
    assert cross_tenant.status_code == 404
    denied = await client.get("/api/v1/benchmarks/datasets", headers=_headers("platform"))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "DATA_SCOPE_FORBIDDEN"


@pytest.mark.asyncio
async def test_benchmark_catalog_counts_farm_namespaced_logical_assets(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    async with app.state.session_factory() as session, session.begin():
        session.add(
            BenchmarkFile(
                id="care-file-b1",
                dataset_version_id="care-v6",
                file_kind="event",
                relative_path="WindFarmB/event_1.csv",
                farm="B",
                event_id=1,
                size_bytes=2048,
                row_count=20,
                schema_sha256=HASH_A,
                content_sha256=HASH_C,
                metadata_={},
            )
        )
        session.add(
            BenchmarkEvent(
                id="care-event-b1",
                dataset_version_id="care-v6",
                source_file_id="care-file-b1",
                event_id=1,
                farm="B",
                source_asset_id="0",
                logical_asset_id="care-b-asset-0",
                event_label="normal",
                first_source_row_id=0,
                last_source_row_id=19,
                train_row_count=15,
                prediction_row_count=5,
                event_interval_start=16,
                event_interval_end=19,
                truth_metadata={},
            )
        )

    response = await client.get("/api/v1/benchmarks/datasets?q=care", headers=_headers("benchmark"))
    assert response.status_code == 200, response.text
    coverage = response.json()["data"][0]["coverage"]
    assert coverage["registered_event_count"] == 2
    assert coverage["asset_count"] == 2


@pytest.mark.asyncio
async def test_benchmark_events_fail_closed_without_truth_scope(app: FastAPI, client: Any) -> None:
    await _seed_benchmark_catalog(app)
    reader = _headers("benchmark")

    response = await client.get(
        "/api/v1/benchmarks/datasets/care-v6/events?limit=1", headers=reader
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["truth_revealed"] is False
    assert body["meta"]["bounds"] == {
        "event_page_max": 64,
        "recent_replays_per_event_max": 5,
        "variables_per_replay_max": 64,
    }
    event = body["data"][0]
    assert event["truth"] == {
        "access": "restricted",
        "event_label": None,
        "event_interval_start": None,
        "event_interval_end": None,
    }
    assert event["recent_replays"][0]["variables"] == ["sensor_0.avg", "sensor_1.avg"]

    forbidden = await client.get(
        "/api/v1/benchmarks/datasets/care-v6/events?revealTruth=true", headers=reader
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "BENCHMARK_TRUTH_FORBIDDEN"

    truth_reader = _headers("benchmark", "benchmark_truth")
    revealed = await client.get(
        "/api/v1/benchmarks/datasets/care-v6/events?eventLabel=anomaly&revealTruth=true",
        headers=truth_reader,
    )
    assert revealed.status_code == 200, revealed.text
    assert revealed.json()["data"][0]["truth"]["event_label"] == "anomaly"


@pytest.mark.asyncio
async def test_benchmark_curve_is_server_bounded_and_never_loads_raw_csv(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    reader = _headers("benchmark")

    response = await client.get(
        "/api/v1/benchmarks/replay-runs/cat00001/curve?variable=sensor_0.avg&maxPoints=16",
        headers=reader,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert 2 <= len(body["data"]) <= 16
    assert body["data"][0]["source_row_id"] == 0
    assert body["data"][-1]["source_row_id"] == 39
    assert all(point["observed_at_is_synthetic"] is True for point in body["data"])
    assert body["meta"]["source_point_count"] == 40
    assert body["meta"]["bounded"] is True
    assert body["meta"]["raw_csv_loaded"] is False
    assert body["meta"]["truth_included"] is False
    assert body["meta"]["bounds"]["curve_point_max"] == 512

    unknown_variable = await client.get(
        "/api/v1/benchmarks/replay-runs/cat00001/curve?variable=truth_label",
        headers=reader,
    )
    assert unknown_variable.status_code == 404
    too_many = await client.get(
        "/api/v1/benchmarks/replay-runs/cat00001/curve?variable=sensor_0.avg&maxPoints=513",
        headers=reader,
    )
    assert too_many.status_code == 422


@pytest.mark.asyncio
async def test_governed_data_catalog_exposes_only_authorized_benchmark_rows(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    headers = _headers("platform", "benchmark")
    response = await client.get(
        "/api/v1/data-catalog?category=benchmark&q=care&limit=1", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["benchmark_total"] == 1
    assert body["meta"]["filtered_total"] == 1
    assert body["meta"]["has_more"] is False
    assert [row["id"] for row in body["data"]] == ["BENCHMARK-care-v6"]
    assert body["data"][0]["category"] == "benchmark"
    assert body["data"][0]["recordCount"] == 40

    platform_only = await client.get(
        "/api/v1/data-catalog?category=benchmark", headers=_headers("platform")
    )
    assert platform_only.status_code == 200, platform_only.text
    assert platform_only.json()["data"] == []
    assert platform_only.json()["meta"]["benchmark_total"] == 0


@pytest.mark.asyncio
async def test_benchmark_dataset_status_and_offset_filters_are_stable(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    filtered = await client.get("/api/v1/benchmarks/datasets?status=failed&offset=0&limit=1")
    assert filtered.status_code == 200, filtered.text
    assert [row["dataset_version_id"] for row in filtered.json()["data"]] == ["other-v1"]
    empty_page = await client.get("/api/v1/benchmarks/datasets?offset=2&limit=1")
    assert empty_page.status_code == 200, empty_page.text
    assert empty_page.json()["data"] == []
    assert empty_page.json()["meta"]["filtered_total"] == 2

    async with app.state.session_factory() as session:
        assert await session.scalar(select(Turbine.id).where(Turbine.id == "WT-023")) == "WT-023"


@pytest.mark.asyncio
async def test_benchmark_model_evaluations_are_bounded_complete_and_gate_auditable(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    headers = _headers("benchmark", "model")
    response = await client.get(
        "/api/v1/benchmarks/evaluations?modelId=care-anomaly-model&limit=3",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["bounds"] == {
        "evaluation_page_max": 32,
        "metrics_per_evaluation_max": 64,
        "deployments_per_model_max": 8,
    }
    assert body["meta"]["filtered_total"] == 3
    by_id = {row["evaluation_run_id"]: row for row in body["data"]}
    complete = by_id["care-eval-complete"]
    assert complete["model"]["kind"] == "anomaly"
    assert complete["model"]["evaluation_role"] == "target"
    assert complete["run"]["protocol_version"] == "care-a0-a24-final-holdout-v1"
    assert complete["run"]["random_seed"] == 20260826
    assert complete["run"]["dependency_identity"] == {"numpy": "2.4.2"}
    assert complete["event_accounting"] == {
        "requested": 1,
        "scored": 1,
        "failed": 0,
        "unscorable": 0,
    }
    assert complete["server_gate"] == {
        "eligible": True,
        "reasons": [],
        "release_metric_count": 1,
    }
    assert complete["evaluation_artifact"]["immutable"] is True
    assert complete["deployments"][0]["authorization_state"] == "current"
    assert by_id["care-eval-failed"]["server_gate"]["eligible"] is False
    assert "FAILED_EVENTS_PRESENT" in by_id["care-eval-failed"]["server_gate"]["reasons"]
    assert "RELEASE_METRIC_FAILED" in by_id["care-eval-failed"]["server_gate"]["reasons"]
    assert "UNSCORABLE_EVENTS_PRESENT" in by_id["care-eval-unscorable"]["server_gate"]["reasons"]
    serialized = response.text
    assert "remaining_useful_life" not in serialized
    assert "failure_probability_30d" not in serialized

    empty = await client.get(
        "/api/v1/benchmarks/evaluations?modelId=missing-model", headers=headers
    )
    assert empty.status_code == 200
    assert empty.json()["data"] == []
    assert empty.json()["meta"]["filtered_total"] == 0


@pytest.mark.asyncio
async def test_benchmark_event_results_keep_failures_and_truth_fail_closed(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    headers = _headers("benchmark", "model")
    failed = await client.get(
        "/api/v1/benchmarks/evaluations/care-eval-failed/results?status=failed",
        headers=headers,
    )
    assert failed.status_code == 200, failed.text
    assert failed.json()["data"][0]["failure_code"] == "PREDICTION_ARTIFACT_INVALID"
    assert failed.json()["data"][0]["truth"] == {
        "access": "restricted",
        "event_label": None,
        "event_interval_start": None,
        "event_interval_end": None,
        "failure_type": None,
        "description": None,
    }
    assert "restricted-failure" not in failed.text

    unscorable = await client.get(
        "/api/v1/benchmarks/evaluations/care-eval-unscorable/results?status=unscorable",
        headers=headers,
    )
    assert unscorable.status_code == 200, unscorable.text
    assert unscorable.json()["data"][0]["status"] == "unscorable"
    assert unscorable.json()["data"][0]["scorable"] is False

    denied = await client.get(
        "/api/v1/benchmarks/evaluations/care-eval-complete/results?revealTruth=true",
        headers=headers,
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "BENCHMARK_TRUTH_FORBIDDEN"
    revealed = await client.get(
        "/api/v1/benchmarks/evaluations/care-eval-complete/results?revealTruth=true",
        headers=_headers("benchmark", "model", "benchmark_truth"),
    )
    assert revealed.status_code == 200, revealed.text
    truth = revealed.json()["data"][0]["truth"]
    assert truth["event_label"] == "anomaly"
    assert truth["failure_type"] == "restricted-bearing-description"
    assert truth["description"] == "restricted"


@pytest.mark.asyncio
async def test_benchmark_diagnosis_links_prediction_alarm_mission_and_time_evidence(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    headers = _headers("benchmark", "model", "mission")
    response = await client.get("/api/v1/benchmarks/diagnoses?limit=1", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["bounds"] == {
        "diagnosis_page_max": 32,
        "predictions_per_replay_max": 64,
        "signals_inspected_per_prediction_max": 64,
    }
    assert body["meta"]["truth_revealed"] is False
    assert body["meta"]["truth_reveal_allowed"] is False
    diagnosis = body["data"][0]
    assert diagnosis["replay"]["time_semantics"] == "synthetic-replay-time-not-field-time"
    assert diagnosis["deployment"]["stale"] is False
    assert diagnosis["model"]["kind"] == "anomaly"
    prediction = diagnosis["predictions"][0]
    assert prediction["anomaly_score"] == 0.92
    assert prediction["binary_prediction"] is True
    assert prediction["threshold"]["value"] == 0.8
    assert prediction["time_evidence"]["observed_at_is_synthetic"] is True
    assert prediction["time_evidence"]["anonymous_observed_at"] == "anonymous-2"
    assert prediction["quality"]["quality_counts"]["uncertain"] == 1
    assert prediction["quality"]["quality_mask_refs"] == ["mask://care-a0-row-2"]
    assert prediction["links"] == {
        "alarm_id": "care-alarm-0001",
        "alarm_status": "open",
        "alarm_triggered_at": prediction["links"]["alarm_triggered_at"],
        "mission_id": "CARE-MISSION-0001",
        "mission_status": "under_review",
        "decision_id": "CARE-DECISION-0001",
    }
    assert prediction["links"]["alarm_triggered_at"].startswith("2026-08-26T00:00:02")
    assert diagnosis["first_alert"]["lead_source_rows"] is None
    assert diagnosis["first_alert"]["lead_semantics"] == "source-row-offset-not-rul"
    assert diagnosis["truth"]["access"] == "restricted"
    assert "remaining_useful_life" not in response.text
    assert "failure_probability_30d" not in response.text

    revealed = await client.get(
        "/api/v1/benchmarks/diagnoses?limit=1&revealTruth=true",
        headers=_headers("benchmark", "model", "mission", "benchmark_truth"),
    )
    assert revealed.status_code == 200, revealed.text
    assert revealed.json()["data"][0]["truth"]["event_label"] == "anomaly"
    assert revealed.json()["data"][0]["first_alert"]["lead_source_rows"] == 28


@pytest.mark.asyncio
async def test_benchmark_model_and_diagnosis_permissions_and_limits_fail_closed(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    model_denied = await client.get("/api/v1/benchmarks/evaluations", headers=_headers("benchmark"))
    assert model_denied.status_code == 403
    assert model_denied.json()["error"]["code"] == "BENCHMARK_MODEL_FORBIDDEN"
    diagnosis_denied = await client.get(
        "/api/v1/benchmarks/diagnoses", headers=_headers("benchmark", "model")
    )
    assert diagnosis_denied.status_code == 403
    assert diagnosis_denied.json()["error"]["code"] == "BENCHMARK_DIAGNOSIS_FORBIDDEN"
    truth_denied = await client.get(
        "/api/v1/benchmarks/diagnoses?revealTruth=true",
        headers=_headers("benchmark", "model", "mission"),
    )
    assert truth_denied.status_code == 403
    assert truth_denied.json()["error"]["code"] == "BENCHMARK_TRUTH_FORBIDDEN"
    too_many_evaluations = await client.get(
        "/api/v1/benchmarks/evaluations?limit=33",
        headers=_headers("benchmark", "model"),
    )
    assert too_many_evaluations.status_code == 422
    too_many_diagnoses = await client.get(
        "/api/v1/benchmarks/diagnoses?limit=33",
        headers=_headers("benchmark", "model", "mission"),
    )
    assert too_many_diagnoses.status_code == 422


def _export_request(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "format": "json",
        "distribution": "internal",
        "includeTruth": False,
        "changesMade": "Exported governed evaluation summaries without raw signal values.",
        "expectedSourceArtifactSha256": HASH_A,
        "attributionConfirmed": False,
        "licenseLinkConfirmed": False,
        "shareAlikeConfirmed": False,
        "legalReviewReference": None,
    }
    value.update(overrides)
    return value


def _export_headers(
    *scopes: str,
    idempotency_key: str = "care-export-test-0001",
    tenant_id: str = "tenant-east-china",
) -> dict[str, str]:
    return {
        **_headers(*scopes, tenant_id=tenant_id),
        "Idempotency-Key": idempotency_key,
    }


@pytest.mark.asyncio
async def test_benchmark_json_export_is_licensed_truth_safe_and_idempotently_audited(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    headers = _export_headers("benchmark", "model", "benchmark_export")
    path = "/api/v1/benchmarks/evaluations/care-eval-complete/exports"
    response = await client.post(path, headers=headers, json=_export_request())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "care-v6-governed-evaluation-export-v1"
    assert body["license"]["doi"] == "10.5281/zenodo.15846963"
    assert body["license"]["license_url"] == ("https://creativecommons.org/licenses/by-sa/4.0/")
    assert body["license"]["share_alike_required"] is True
    assert body["license"]["code_license_is_separate"] is True
    assert body["report"]["truth_included"] is False
    assert body["report"]["event_results"][0]["truth"]["event_label"] is None
    assert "restricted-bearing-description" not in response.text
    assert response.headers["x-windops-data-license"] == "CC BY-SA 4.0"
    assert (
        response.headers["x-windops-artifact-sha256"]
        == hashlib.sha256(response.content).hexdigest()
    )
    audit_id = response.headers["x-windops-audit-event-id"]

    repeated = await client.post(path, headers=headers, json=_export_request())
    assert repeated.status_code == 200, repeated.text
    assert repeated.content == response.content
    assert repeated.headers["x-windops-audit-event-id"] == audit_id
    assert repeated.headers["x-windops-export-replayed"] == "true"
    conflict = await client.post(
        path,
        headers=headers,
        json=_export_request(format="csv"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    async with app.state.session_factory() as session:
        audits = list(
            (
                await session.scalars(
                    select(DomainEvent).where(
                        DomainEvent.aggregate_type == "benchmark_export",
                        DomainEvent.event_type == "benchmark.export.completed",
                    )
                )
            ).all()
        )
    assert len(audits) == 1
    assert audits[0].payload["artifact_sha256"] == response.headers["x-windops-artifact-sha256"]
    assert audits[0].payload["license"]["changes_made"] == _export_request()["changesMade"]


@pytest.mark.asyncio
async def test_external_csv_export_requires_sharealike_review_and_records_denials(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    headers = _export_headers(
        "benchmark",
        "model",
        "benchmark_export",
        idempotency_key="care-export-external-denied",
    )
    path = "/api/v1/benchmarks/evaluations/care-eval-complete/exports"
    denied_request = _export_request(
        format="csv",
        distribution="external",
    )
    denied = await client.post(path, headers=headers, json=denied_request)
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "BENCHMARK_EXPORT_REVIEW_REQUIRED"

    approved_request = _export_request(
        format="csv",
        distribution="external",
        attributionConfirmed=True,
        licenseLinkConfirmed=True,
        shareAlikeConfirmed=True,
        legalReviewReference="LEGAL-CARE-2026-0001",
    )
    approved = await client.post(
        path,
        headers={**headers, "Idempotency-Key": "care-export-external-approved"},
        json=approved_request,
    )
    assert approved.status_code == 200, approved.text
    assert approved.headers["content-type"].startswith("text/csv")
    first_line, csv_body = approved.content.split(b"\n", 1)
    assert first_line.startswith(b"# windops-care-export-metadata=")
    metadata = json.loads(first_line.split(b"=", 1)[1])
    assert metadata["license"]["external_distribution_review"] == "required"
    assert metadata["license"]["share_alike_required"] is True
    assert metadata["csv_payload_sha256"] == hashlib.sha256(csv_body).hexdigest()
    async with app.state.session_factory() as session:
        event_types = list(
            (
                await session.scalars(
                    select(DomainEvent.event_type)
                    .where(DomainEvent.aggregate_type == "benchmark_export")
                    .order_by(DomainEvent.event_type.asc())
                )
            ).all()
        )
    assert event_types == ["benchmark.export.completed", "benchmark.export.denied"]


@pytest.mark.asyncio
async def test_benchmark_export_permissions_truth_source_and_tenant_fail_closed(
    app: FastAPI, client: Any
) -> None:
    await _seed_benchmark_catalog(app)
    path = "/api/v1/benchmarks/evaluations/care-eval-complete/exports"
    missing_export_scope = await client.post(
        path,
        headers=_export_headers("benchmark", "model"),
        json=_export_request(),
    )
    assert missing_export_scope.status_code == 403
    assert missing_export_scope.json()["error"]["code"] == "BENCHMARK_EXPORT_FORBIDDEN"
    truth_denied = await client.post(
        path,
        headers=_export_headers(
            "benchmark",
            "model",
            "benchmark_export",
            idempotency_key="care-export-truth-denied",
        ),
        json=_export_request(includeTruth=True),
    )
    assert truth_denied.status_code == 403
    assert truth_denied.json()["error"]["code"] == "BENCHMARK_TRUTH_FORBIDDEN"
    cross_tenant = await client.post(
        path,
        headers=_export_headers(
            "benchmark",
            "model",
            "benchmark_export",
            tenant_id="tenant-benchmark-other",
            idempotency_key="care-export-cross-tenant",
        ),
        json=_export_request(),
    )
    assert cross_tenant.status_code == 404
    source_changed = await client.post(
        path,
        headers=_export_headers(
            "benchmark",
            "model",
            "benchmark_export",
            idempotency_key="care-export-source-changed",
        ),
        json=_export_request(expectedSourceArtifactSha256=HASH_B),
    )
    assert source_changed.status_code == 422
    assert source_changed.json()["error"]["code"] == "BENCHMARK_ARTIFACT_SCOPE_INVALID"

    truth_allowed = await client.post(
        path,
        headers=_export_headers(
            "benchmark",
            "model",
            "benchmark_export",
            "benchmark_truth",
            idempotency_key="care-export-truth-approved",
        ),
        json=_export_request(includeTruth=True),
    )
    assert truth_allowed.status_code == 200, truth_allowed.text
    assert truth_allowed.json()["report"]["event_results"][0]["truth"]["event_label"] == ("anomaly")

    async with app.state.session_factory() as session:
        await session.execute(
            delete(BenchmarkEventResult).where(
                BenchmarkEventResult.evaluation_run_id == "care-eval-complete"
            )
        )
        await session.commit()
    incomplete = await client.post(
        path,
        headers=_export_headers(
            "benchmark",
            "model",
            "benchmark_export",
            idempotency_key="care-export-incomplete-results",
        ),
        json=_export_request(),
    )
    assert incomplete.status_code == 422
    assert incomplete.json()["error"]["code"] == "BENCHMARK_ARTIFACT_SCOPE_INVALID"
