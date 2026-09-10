from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from windops_backend.errors import ConflictError
from windops_backend.models import (
    Alarm,
    AnomalyAlertPolicyState,
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkEventResult,
    BenchmarkFeatureMap,
    BenchmarkMetricSnapshot,
    BenchmarkQualityArtifact,
    BenchmarkQualityReport,
    BenchmarkReplayRun,
    DomainEvent,
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
    Turbine,
)
from windops_backend.schemas import (
    AnomalyAlertPolicyStateRequest,
    BenchmarkDatasetVersionCreateRequest,
    BenchmarkEvaluationRunCreateRequest,
    BenchmarkEventCreateRequest,
    BenchmarkEventResultCreateRequest,
    BenchmarkFeatureMapCreateRequest,
    BenchmarkFileCreateRequest,
    BenchmarkMetricSnapshotCreateRequest,
    BenchmarkQualityReportCreateRequest,
    BenchmarkReplayRunCreateRequest,
)
from windops_backend.services.benchmark_metadata import (
    build_benchmark_trace,
    complete_evaluation_run,
    get_or_create_evaluation_run,
    persist_anomaly_alert_policy_state,
    record_event_result,
    record_metric_snapshot,
    register_benchmark_event,
    register_benchmark_file,
    register_dataset_version,
    register_feature_map,
    register_quality_report,
    register_replay_run,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def _dataset_request() -> BenchmarkDatasetVersionCreateRequest:
    return BenchmarkDatasetVersionCreateRequest(
        dataset_version_id="care-v6",
        tenant_id="tenant-east-china",
        dataset_id="CARE",
        version="6",
        status="ready",
        source_uri="file:///readonly/CARE_To_Compare.zip",
        manifest_uri="minio://care/raw/manifest.json",
        manifest_sha256=SHA_A,
        content_sha256=SHA_B,
        source_archive_md5="1" * 32,
        source_archive_sha256=SHA_C,
        size_bytes=1234,
        file_count=101,
        license_name="CC BY-SA 4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        doi="10.24406/publica-1179",
        citation="CARE v6 benchmark dataset",
        attribution={"changes_made": False, "transformation_version": "source"},
    )


def _file_request() -> BenchmarkFileCreateRequest:
    return BenchmarkFileCreateRequest(
        file_id="care-file-a-event-0",
        dataset_version_id="care-v6",
        file_kind="event",
        relative_path="A/event_0.csv",
        farm="A",
        event_id=0,
        size_bytes=1000,
        row_count=10,
        schema_sha256=SHA_A,
        content_sha256=SHA_C,
        metadata={"delimiter": ";"},
    )


def _event_request() -> BenchmarkEventCreateRequest:
    return BenchmarkEventCreateRequest(
        benchmark_event_id="care-v6-event-0",
        dataset_version_id="care-v6",
        source_file_id="care-file-a-event-0",
        event_id=0,
        farm="A",
        source_asset_id="1",
        logical_asset_id="CARE-A-1",
        event_label="anomaly",
        first_source_row_id=0,
        last_source_row_id=9,
        train_row_count=8,
        prediction_row_count=2,
        event_interval_start=8,
        event_interval_end=9,
        truth_metadata={"visibility": "evaluation-only"},
    )


def _feature_map_request() -> BenchmarkFeatureMapCreateRequest:
    return BenchmarkFeatureMapCreateRequest(
        feature_map_id="care-feature-map-h002",
        dataset_version_id="care-v6",
        mapping_version="care-v6-column-mapping-v1",
        farm="A",
        source_column="sensor_1_avg",
        canonical_feature="sensor_1",
        statistic="average",
        unit="1",
        enabled=True,
        semantics={"raw_value_preserved": True},
    )


def _quality_report_request() -> BenchmarkQualityReportCreateRequest:
    return BenchmarkQualityReportCreateRequest(
        quality_report_id="care-quality-report-h002",
        event_id="care-v6-event-0",
        quality_rule_version="care-v6-quality-v1",
        feature_set_version="care-v6-avg-v1",
        canonical_content_sha256=SHA_C,
        artifact_stage="minimal-import",
        status="completed",
        artifact_uri="minio://care/quality/event-0-report.json",
        artifact_sha256=SHA_A,
        mask_uri="minio://care/quality/event-0-mask.json",
        mask_sha256=SHA_B,
        summary={"raw_values_preserved": True},
    )


@pytest.mark.asyncio
async def test_quality_registration_preserves_stage_artifacts_and_canonical_identity(
    app: FastAPI,
) -> None:
    minimal = _quality_report_request()
    full_scale = minimal.model_copy(
        update={
            "artifact_stage": "full-scale-import",
            "artifact_uri": "minio://care/full-scale/quality/event-0-report.json",
            "artifact_sha256": SHA_B,
            "mask_uri": "minio://care/full-scale/quality/event-0-mask.json",
            "mask_sha256": SHA_A,
        }
    )
    async with app.state.session_factory() as session, session.begin():
        await register_dataset_version(session, _dataset_request(), subject="care-minimal-worker")
        await register_benchmark_file(session, _file_request())
        await register_benchmark_event(session, _event_request())
        canonical, minimal_replayed = await register_quality_report(
            session,
            minimal,
            subject="care-minimal-worker",
        )
        upgraded, full_scale_replayed = await register_quality_report(
            session,
            full_scale,
            subject="care-full-scale-worker",
        )
        assert canonical.id == upgraded.id
        assert minimal_replayed is False
        assert full_scale_replayed is False
        assert canonical.canonical_content_sha256 == SHA_C
        assert canonical.artifact_sha256 == SHA_A

    async with app.state.session_factory() as session, session.begin():
        _, replayed = await register_quality_report(
            session,
            full_scale,
            subject="care-full-scale-retry",
        )
        assert replayed is True

    async with app.state.session_factory() as session:
        artifacts = list(
            (
                await session.scalars(
                    select(BenchmarkQualityArtifact).order_by(
                        BenchmarkQualityArtifact.artifact_stage
                    )
                )
            ).all()
        )
        assert [artifact.artifact_stage for artifact in artifacts] == [
            "full-scale-import",
            "minimal-import",
        ]
        assert {artifact.audit_subject for artifact in artifacts} == {
            "care-full-scale-worker",
            "care-minimal-worker",
        }
        events = list(
            (
                await session.scalars(
                    select(DomainEvent).where(
                        DomainEvent.event_type == "benchmark.transform.quality.completed"
                    )
                )
            ).all()
        )
        assert len(events) == 2
        assert {event.payload["artifact_stage"] for event in events} == {
            "minimal-import",
            "full-scale-import",
        }
        assert {event.payload["requested_by"] for event in events} == {
            "care-minimal-worker",
            "care-full-scale-worker",
        }

    conflicting = minimal.model_copy(
        update={
            "artifact_stage": "conflicting-import",
            "canonical_content_sha256": SHA_A,
        }
    )
    async with app.state.session_factory() as session:
        with pytest.raises(ConflictError, match="different content"):
            async with session.begin():
                await register_quality_report(
                    session,
                    conflicting,
                    subject="care-conflicting-worker",
                )


def _evaluation_request() -> BenchmarkEvaluationRunCreateRequest:
    return BenchmarkEvaluationRunCreateRequest(
        evaluation_run_id="care-evaluation-h002",
        dataset_version_id="care-v6",
        model_id="ANOM-H002-1",
        model_version="1.0.0",
        run_kind="final-holdout",
        protocol_version="care-score-v6",
        farm="A",
        feature_set_version="care-v6-avg-v1",
        quality_rule_version="care-v6-quality-v1",
        threshold_policy_version="threshold-v1",
        threshold_policy_sha256=SHA_A,
        random_seed=42,
        input_identity_sha256=SHA_B,
        requested_event_count=1,
        extension_data={"dependency_lock_sha256": SHA_C},
    )


def _result_request() -> BenchmarkEventResultCreateRequest:
    return BenchmarkEventResultCreateRequest(
        event_result_id="care-event-result-h002",
        evaluation_run_id="care-evaluation-h002",
        event_id="care-v6-event-0",
        status="scored",
        scorable=True,
        anomaly_detected=True,
        care_score=0.91,
        coverage_score=0.9,
        accuracy_score=1.0,
        reliability_score=0.8,
        earliness_score=0.75,
        prediction_artifact_uri="minio://care/predictions/eval-event-0.json",
        prediction_artifact_sha256=SHA_B,
        result_sha256=SHA_C,
        details={"rounding": "final-only"},
    )


def _metric_request() -> BenchmarkMetricSnapshotCreateRequest:
    return BenchmarkMetricSnapshotCreateRequest(
        metric_snapshot_id="care-metric-h002",
        evaluation_run_id="care-evaluation-h002",
        metric_name="care.score",
        protocol_version="care-score-v6",
        metric_version="1",
        value=0.91,
        unit="ratio",
        numerator=91,
        denominator=100,
        is_release_metric=True,
        threshold_value=0.8,
        threshold_direction="gte",
        passed=True,
        details={"server_owned": True},
    )


def _replay_request(online_turbine_id: str, deployment_id: str) -> BenchmarkReplayRunCreateRequest:
    return BenchmarkReplayRunCreateRequest(
        benchmark_replay_run_id="abcd1234",
        dataset_version_id="care-v6",
        event_id="care-v6-event-0",
        source_asset_id="1",
        logical_asset_id="CARE-A-1",
        online_turbine_id=online_turbine_id,
        farm="A",
        source_event_number=0,
        replay_mode="historical-fixed",
        speed=1.0,
        status="running",
        replay_anchor_at=NOW,
        time_rule_version="care-v6-fixed-10m-window-relative-v1",
        sequence_rule_version="care-v6-source-row-sequence-v1",
        source_event_id_rule_version="care-v6-source-event-id-v1",
        selected_variables=[
            {
                "short_id": "v123456789ab",
                "canonical_variable": "sensor_1",
                "statistic": "average",
                "unit": "1",
            }
        ],
        window_start_row_id=8,
        window_end_row_id=9,
        checkpoint={
            "benchmark_replay_run_id": "abcd1234",
            "revision": 0,
            "last_confirmed_rows": {"v123456789ab": 7},
        },
        checkpoint_revision=0,
        checkpoint_sha256=SHA_A,
        model_id="ANOM-H002-1",
        model_version="1.0.0",
        deployment_id=deployment_id,
        threshold_policy_version="threshold-v1",
        threshold_policy_sha256=SHA_A,
        started_at=NOW,
    )


def _policy_state_request(
    online_turbine_id: str,
    deployment_id: str,
    prediction_id: str,
) -> AnomalyAlertPolicyStateRequest:
    return AnomalyAlertPolicyStateRequest(
        policy_state_id="care-policy-state-h002",
        deployment_id=deployment_id,
        turbine_id=online_turbine_id,
        component="unknown",
        policy_version="policy-v1",
        policy_sha256=SHA_A,
        phase="active",
        consecutive_trigger_count=3,
        consecutive_recovery_count=0,
        cooldown_until=None,
        last_prediction_id=prediction_id,
        last_prediction_created_at=NOW,
        dedup_key="care-h002-alert",
        policy_document={"trigger_windows": 3, "recovery_windows": 2},
        state_document={"last_score": 0.91},
        revision=0,
    )


def test_benchmark_api_schemas_fail_closed_for_unbounded_or_partial_data() -> None:
    with pytest.raises(ValidationError, match="release metrics require"):
        BenchmarkMetricSnapshotCreateRequest(
            metric_snapshot_id="metric-invalid",
            evaluation_run_id="evaluation-invalid",
            metric_name="care.score",
            protocol_version="care-score-v6",
            metric_version="1",
            value=0.9,
            unit="ratio",
            is_release_metric=True,
        )
    with pytest.raises(ValidationError, match="exceeds 65536 bytes"):
        BenchmarkDatasetVersionCreateRequest(
            **{
                **_dataset_request().model_dump(),
                "attribution": {"oversized": "x" * 70_000},
            }
        )
    with pytest.raises(ValidationError, match="terminal replay runs require"):
        BenchmarkReplayRunCreateRequest(
            **{
                **_replay_request("CARE-A-1-E0-abcd1234", str(uuid4())).model_dump(),
                "status": "completed",
                "finished_at": None,
            }
        )
    with pytest.raises(ValidationError, match="deployment_id requires model_id"):
        BenchmarkReplayRunCreateRequest(
            **{
                **_replay_request("CARE-A-1-E0-abcd1234", str(uuid4())).model_dump(),
                "model_id": None,
                "model_version": None,
            }
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AnomalyAlertPolicyStateRequest(
            policy_state_id="policy-state-h002",
            deployment_id=str(uuid4()),
            turbine_id="CARE-A-1-E0-abcd1234",
            component="unknown",
            policy_version="policy-v1",
            policy_sha256=SHA_A,
            phase="normal",
            consecutive_trigger_count=0,
            consecutive_recovery_count=0,
            policy_document={},
            state_document={},
            revision=0,
            ungoverned_metric=1,
        )


@pytest.mark.asyncio
async def test_benchmark_metadata_trace_and_idempotent_retries(app: FastAPI) -> None:
    online_turbine_id = "CARE-A-1-E0-abcd1234"
    deployment_id = str(uuid4())
    prediction_id = str(uuid4())
    alarm_id = str(uuid4())
    async with app.state.session_factory() as session, session.begin():
        dataset, dataset_replayed = await register_dataset_version(
            session, _dataset_request(), subject="care-worker"
        )
        assert dataset.id == "care-v6" and dataset_replayed is False
        await register_benchmark_file(session, _file_request())
        await register_benchmark_event(session, _event_request())
        await register_feature_map(session, _feature_map_request())
        await register_quality_report(session, _quality_report_request())
        session.add(
            RegisteredModel(
                id="ANOM-H002-1",
                name="CARE H002 anomaly",
                version="1.0.0",
                kind="anomaly",
                status="active",
                artifact_uri="minio://care/models/anom-h002.onnx",
                artifact_sha256=SHA_A,
                content_type="application/onnx",
                content_size_bytes=10,
                input_schema={"type": "object", "additionalProperties": False},
                output_schema={"type": "object", "additionalProperties": False},
                metrics={},
                description="H002 trace model",
                created_by="care-worker",
            )
        )
        session.add(
            ModelDeployment(
                id=deployment_id,
                model_id="ANOM-H002-1",
                target_id="anomaly-primary",
                stage="production",
                status="active",
                traffic_percent=100,
                evaluation_gate={},
                deployed_by="care-worker",
            )
        )
        session.add(
            Turbine(
                id=online_turbine_id,
                wind_farm_id="WF-EAST-01",
                model="CARE v6 isolated replay",
                status="running",
                health_score=100,
            )
        )
        await session.flush()
        evaluation, evaluation_replayed = await get_or_create_evaluation_run(
            session, _evaluation_request(), subject="care-worker"
        )
        assert evaluation.id == "care-evaluation-h002" and evaluation_replayed is False
        await record_event_result(session, _result_request())
        await record_metric_snapshot(session, _metric_request())
        await complete_evaluation_run(
            session,
            evaluation_run_id=evaluation.id,
            artifact_uri="minio://care/reports/evaluation-h002.json",
            artifact_sha256=SHA_C,
            completed_at=NOW,
        )
        replay, replayed = await register_replay_run(
            session,
            _replay_request(online_turbine_id, deployment_id),
            subject="care-worker",
        )
        assert replay.id == "abcd1234" and replayed is False
        session.add(
            ModelPrediction(
                id=prediction_id,
                model_id="ANOM-H002-1",
                deployment_id=deployment_id,
                turbine_id=online_turbine_id,
                feature_observed_at=NOW,
                prediction_kind="anomaly",
                benchmark_replay_run_id=replay.id,
                benchmark_evaluation_run_id=evaluation.id,
                feature_window_start=NOW,
                feature_window_end=NOW,
                feature_start_sequence=8,
                feature_end_sequence=9,
                anomaly_score=0.91,
                binary_prediction=True,
                component="unknown",
                threshold_policy_version="threshold-v1",
                threshold_policy_sha256=SHA_A,
                feature_set_version="care-v6-avg-v1",
                quality_rule_version="care-v6-quality-v1",
                evidence_artifact_uri="minio://care/predictions/window-h002.json",
                evidence_artifact_sha256=SHA_B,
                input_digest=SHA_C,
                input_snapshot={"prediction_truth_present": False},
                output={"anomaly_score": 0.91, "binary_prediction": True},
                status="succeeded",
                requested_by="care-worker",
            )
        )
        await session.flush()
        policy_state, policy_replayed = await persist_anomaly_alert_policy_state(
            session,
            _policy_state_request(online_turbine_id, deployment_id, prediction_id),
        )
        assert policy_state.revision == 0 and policy_replayed is False
        session.add(
            Alarm(
                id=alarm_id,
                turbine_id=online_turbine_id,
                source_event_id=None,
                model_prediction_id=prediction_id,
                code="CARE-ANOMALY",
                subsystem="benchmark",
                title="CARE anomaly prediction alert",
                severity="major",
                status="open",
                ai_status="queued",
                triggered_at=NOW,
                evidence={"prediction_id": prediction_id},
            )
        )
        await session.flush()
        trace = await build_benchmark_trace(session, alarm_id=alarm_id)
        assert trace.model_id == "ANOM-H002-1"
        assert trace.dataset_version_id == "care-v6"
        assert trace.event_id == "care-v6-event-0"
        assert trace.replay_run_id == "abcd1234"
        assert trace.metric_snapshot_ids == ["care-metric-h002"]
        assert trace.source_event_id is None

    async with app.state.session_factory() as session, session.begin():
        _, dataset_replayed = await register_dataset_version(
            session, _dataset_request(), subject="care-worker"
        )
        _, feature_map_replayed = await register_feature_map(session, _feature_map_request())
        _, quality_report_replayed = await register_quality_report(
            session, _quality_report_request()
        )
        _, evaluation_replayed = await get_or_create_evaluation_run(
            session,
            _evaluation_request().model_copy(
                update={"evaluation_run_id": "care-evaluation-retry-h002"}
            ),
            subject="care-worker",
        )
        _, result_replayed = await record_event_result(
            session,
            _result_request().model_copy(
                update={"event_result_id": "care-event-result-retry-h002"}
            ),
        )
        _, metric_replayed = await record_metric_snapshot(session, _metric_request())
        _, replay_replayed = await register_replay_run(
            session,
            _replay_request(online_turbine_id, deployment_id),
            subject="care-worker",
        )
        _, policy_replayed = await persist_anomaly_alert_policy_state(
            session,
            _policy_state_request(online_turbine_id, deployment_id, prediction_id),
        )
        assert all(
            (
                dataset_replayed,
                feature_map_replayed,
                quality_report_replayed,
                evaluation_replayed,
                result_replayed,
                metric_replayed,
                replay_replayed,
                policy_replayed,
            )
        )

    async with app.state.session_factory() as session:
        assert int(await session.scalar(select(func.count(BenchmarkDatasetVersion.id))) or 0) == 1
        assert int(await session.scalar(select(func.count(BenchmarkFeatureMap.id))) or 0) == 1
        assert int(await session.scalar(select(func.count(BenchmarkQualityReport.id))) or 0) == 1
        assert int(await session.scalar(select(func.count(BenchmarkEvaluationRun.id))) or 0) == 1
        assert int(await session.scalar(select(func.count(BenchmarkEventResult.id))) or 0) == 1
        assert int(await session.scalar(select(func.count(BenchmarkMetricSnapshot.id))) or 0) == 1
        assert int(await session.scalar(select(func.count(BenchmarkReplayRun.id))) or 0) == 1
        assert int(await session.scalar(select(func.count(AnomalyAlertPolicyState.id))) or 0) == 1


@pytest.mark.asyncio
async def test_alarm_and_anomaly_structure_constraints_reject_partial_sources(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        session.add(
            Alarm(
                id=str(uuid4()),
                turbine_id="WT-023",
                source_event_id=None,
                model_prediction_id=None,
                code="INVALID-SOURCE",
                subsystem="benchmark",
                title="invalid source-less alarm",
                severity="major",
                status="open",
                ai_status="queued",
                triggered_at=NOW,
                evidence={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
