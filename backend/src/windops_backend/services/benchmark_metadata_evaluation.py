from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.models import (
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkEvent,
    BenchmarkEventResult,
    BenchmarkMetricSnapshot,
    RegisteredModel,
)
from windops_backend.schemas import (
    BenchmarkEvaluationRunCreateRequest,
    BenchmarkEventResultCreateRequest,
    BenchmarkMetricSnapshotCreateRequest,
)
from windops_backend.services.benchmark_metadata_contracts import (
    _claim_identity,
)
from windops_backend.services.events import append_domain_event


async def get_or_create_evaluation_run(
    session: AsyncSession,
    request: BenchmarkEvaluationRunCreateRequest,
    *,
    subject: str,
) -> tuple[BenchmarkEvaluationRun, bool]:
    async with _claim_identity(session, f"benchmark-evaluation:{request.input_identity_sha256}"):
        existing = await session.scalar(
            select(BenchmarkEvaluationRun).where(
                BenchmarkEvaluationRun.input_identity_sha256 == request.input_identity_sha256
            )
        )
        if existing is not None:
            immutable_identity = (
                existing.dataset_version_id,
                existing.model_id,
                existing.model_version,
                existing.run_kind,
                existing.protocol_version,
                existing.farm,
                existing.feature_set_version,
                existing.quality_rule_version,
                existing.threshold_policy_version,
                existing.threshold_policy_sha256,
                existing.random_seed,
                existing.input_identity_sha256,
                existing.requested_event_count,
                existing.extension_data,
                existing.created_by,
            )
            requested_identity = (
                request.dataset_version_id,
                request.model_id,
                request.model_version,
                request.run_kind,
                request.protocol_version,
                request.farm,
                request.feature_set_version,
                request.quality_rule_version,
                request.threshold_policy_version,
                request.threshold_policy_sha256,
                request.random_seed,
                request.input_identity_sha256,
                request.requested_event_count,
                request.extension_data,
                subject,
            )
            if immutable_identity == requested_identity:
                return existing, True
            raise ConflictError(
                "evaluation input identity already exists with different provenance"
            )
        if await session.get(BenchmarkDatasetVersion, request.dataset_version_id) is None:
            raise NotFoundError(f"benchmark dataset {request.dataset_version_id} was not found")
        model = await session.get(RegisteredModel, request.model_id)
        if model is None or model.version != request.model_version:
            raise InvalidTransitionError(
                "benchmark evaluation must reference an existing RegisteredModel ID/version"
            )
        row = BenchmarkEvaluationRun(
            id=request.evaluation_run_id,
            dataset_version_id=request.dataset_version_id,
            model_id=request.model_id,
            model_version=request.model_version,
            run_kind=request.run_kind,
            protocol_version=request.protocol_version,
            farm=request.farm,
            status="pending",
            feature_set_version=request.feature_set_version,
            quality_rule_version=request.quality_rule_version,
            threshold_policy_version=request.threshold_policy_version,
            threshold_policy_sha256=request.threshold_policy_sha256,
            random_seed=request.random_seed,
            input_identity_sha256=request.input_identity_sha256,
            requested_event_count=request.requested_event_count,
            extension_data=request.extension_data,
            created_by=subject,
        )
        session.add(row)
        await session.flush()
        return row, False


async def record_event_result(
    session: AsyncSession,
    request: BenchmarkEventResultCreateRequest,
) -> tuple[BenchmarkEventResult, bool]:
    scope = f"benchmark-result:{request.evaluation_run_id}:{request.event_id}"
    async with _claim_identity(session, scope):
        existing = await session.scalar(
            select(BenchmarkEventResult).where(
                BenchmarkEventResult.evaluation_run_id == request.evaluation_run_id,
                BenchmarkEventResult.event_id == request.event_id,
            )
        )
        if existing is not None:
            immutable_identity = (
                existing.status,
                existing.scorable,
                existing.anomaly_detected,
                existing.care_score,
                existing.coverage_score,
                existing.accuracy_score,
                existing.reliability_score,
                existing.earliness_score,
                existing.prediction_artifact_uri,
                existing.prediction_artifact_sha256,
                existing.failure_code,
                existing.result_sha256,
                existing.details,
            )
            requested_identity = (
                request.status,
                request.scorable,
                request.anomaly_detected,
                request.care_score,
                request.coverage_score,
                request.accuracy_score,
                request.reliability_score,
                request.earliness_score,
                request.prediction_artifact_uri,
                request.prediction_artifact_sha256,
                request.failure_code,
                request.result_sha256,
                request.details,
            )
            if immutable_identity == requested_identity:
                return existing, True
            raise ConflictError("event result already exists with different immutable content")
        run = await session.get(BenchmarkEvaluationRun, request.evaluation_run_id)
        event = await session.get(BenchmarkEvent, request.event_id)
        if run is None or event is None:
            raise NotFoundError("benchmark evaluation run or event was not found")
        if run.status in {"completed", "failed", "cancelled"}:
            raise InvalidTransitionError("terminal evaluation runs cannot accept new results")
        if event.dataset_version_id != run.dataset_version_id:
            raise InvalidTransitionError("event result crosses benchmark dataset versions")
        row = BenchmarkEventResult(
            id=request.event_result_id,
            evaluation_run_id=request.evaluation_run_id,
            event_id=request.event_id,
            status=request.status,
            scorable=request.scorable,
            anomaly_detected=request.anomaly_detected,
            care_score=request.care_score,
            coverage_score=request.coverage_score,
            accuracy_score=request.accuracy_score,
            reliability_score=request.reliability_score,
            earliness_score=request.earliness_score,
            prediction_artifact_uri=request.prediction_artifact_uri,
            prediction_artifact_sha256=request.prediction_artifact_sha256,
            failure_code=request.failure_code,
            result_sha256=request.result_sha256,
            details=request.details,
        )
        session.add(row)
        await session.flush()
        return row, False


async def record_metric_snapshot(
    session: AsyncSession,
    request: BenchmarkMetricSnapshotCreateRequest,
) -> tuple[BenchmarkMetricSnapshot, bool]:
    scope = (
        f"benchmark-metric:{request.evaluation_run_id}:{request.metric_name}:"
        f"{request.protocol_version}:{request.metric_version}"
    )
    async with _claim_identity(session, scope):
        existing = await session.scalar(
            select(BenchmarkMetricSnapshot).where(
                BenchmarkMetricSnapshot.evaluation_run_id == request.evaluation_run_id,
                BenchmarkMetricSnapshot.metric_name == request.metric_name,
                BenchmarkMetricSnapshot.protocol_version == request.protocol_version,
                BenchmarkMetricSnapshot.metric_version == request.metric_version,
            )
        )
        if existing is not None:
            immutable_identity = (
                existing.id,
                existing.value,
                existing.unit,
                existing.numerator,
                existing.denominator,
                existing.is_release_metric,
                existing.threshold_value,
                existing.threshold_direction,
                existing.passed,
                existing.details,
            )
            requested_identity = (
                request.metric_snapshot_id,
                request.value,
                request.unit,
                request.numerator,
                request.denominator,
                request.is_release_metric,
                request.threshold_value,
                request.threshold_direction,
                request.passed,
                request.details,
            )
            if immutable_identity == requested_identity:
                return existing, True
            raise ConflictError("metric snapshot identity already exists with different values")
        if await session.get(BenchmarkEvaluationRun, request.evaluation_run_id) is None:
            raise NotFoundError(f"evaluation run {request.evaluation_run_id} was not found")
        row = BenchmarkMetricSnapshot(
            id=request.metric_snapshot_id,
            evaluation_run_id=request.evaluation_run_id,
            metric_name=request.metric_name,
            protocol_version=request.protocol_version,
            metric_version=request.metric_version,
            value=request.value,
            unit=request.unit,
            numerator=request.numerator,
            denominator=request.denominator,
            is_release_metric=request.is_release_metric,
            threshold_value=request.threshold_value,
            threshold_direction=request.threshold_direction,
            passed=request.passed,
            details=request.details,
        )
        session.add(row)
        await session.flush()
        return row, False


async def complete_evaluation_run(
    session: AsyncSession,
    *,
    evaluation_run_id: str,
    artifact_uri: str,
    artifact_sha256: str,
    completed_at: datetime,
    subject: str = "benchmark-worker",
) -> BenchmarkEvaluationRun:
    async with _claim_identity(session, f"benchmark-evaluation-complete:{evaluation_run_id}"):
        run = await session.scalar(
            select(BenchmarkEvaluationRun)
            .where(BenchmarkEvaluationRun.id == evaluation_run_id)
            .with_for_update()
        )
        if run is None:
            raise NotFoundError(f"evaluation run {evaluation_run_id} was not found")
        if run.status == "completed":
            if run.artifact_sha256 == artifact_sha256 and run.artifact_uri == artifact_uri:
                return run
            raise ConflictError("completed evaluation artifact is immutable")
        if run.status in {"failed", "cancelled"}:
            raise InvalidTransitionError("failed/cancelled evaluation runs cannot be completed")
        count_rows = (
            await session.execute(
                select(BenchmarkEventResult.status, func.count(BenchmarkEventResult.id))
                .where(BenchmarkEventResult.evaluation_run_id == evaluation_run_id)
                .group_by(BenchmarkEventResult.status)
            )
        ).all()
        counts: dict[str, int] = {str(row.status): int(row[1]) for row in count_rows}
        scored = int(counts.get("scored", 0))
        failed = int(counts.get("failed", 0))
        unscorable = int(counts.get("unscorable", 0))
        if scored + failed + unscorable != run.requested_event_count:
            raise InvalidTransitionError(
                "evaluation cannot complete until every requested event has an explicit result"
            )
        run.scored_event_count = scored
        run.failed_event_count = failed
        run.unscorable_event_count = unscorable
        run.artifact_uri = artifact_uri
        run.artifact_sha256 = artifact_sha256
        run.completed_at = completed_at.astimezone(UTC)
        run.status = "completed"
        await session.flush()
        append_domain_event(
            session,
            event_type="benchmark.evaluation.completed",
            aggregate_type="benchmark_evaluation",
            aggregate_id=run.id,
            payload={
                "dataset_version_id": run.dataset_version_id,
                "model_id": run.model_id,
                "model_version": run.model_version,
                "artifact_sha256": artifact_sha256,
                "requested_event_count": run.requested_event_count,
                "scored_event_count": run.scored_event_count,
                "failed_event_count": run.failed_event_count,
                "unscorable_event_count": run.unscorable_event_count,
                "requested_by": subject,
            },
        )
        return run
