from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.benchmarks.care.replay import CARE_REPLAY_SOURCE_ID
from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.models import (
    Alarm,
    AnomalyAlertPolicyState,
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkEvent,
    BenchmarkEventResult,
    BenchmarkFeatureMap,
    BenchmarkFile,
    BenchmarkMetricSnapshot,
    BenchmarkQualityArtifact,
    BenchmarkQualityReport,
    BenchmarkReplayRun,
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
    ScadaSample,
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
    BenchmarkTraceResponse,
)
from windops_backend.services.events import append_domain_event

_local_locks: dict[str, asyncio.Lock] = {}


def _document_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _advisory_lock_id(scope: str) -> int:
    digest = hashlib.sha256(scope.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _same_instant(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return left is right
    normalized_left = left.replace(tzinfo=UTC) if left.tzinfo is None else left.astimezone(UTC)
    normalized_right = right.replace(tzinfo=UTC) if right.tzinfo is None else right.astimezone(UTC)
    return normalized_left == normalized_right


@asynccontextmanager
async def _claim_identity(session: AsyncSession, scope: str) -> AsyncIterator[None]:
    dialect = session.bind.dialect.name if session.bind is not None else "unknown"
    if dialect == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _advisory_lock_id(scope)},
        )
        yield
        return
    lock = _local_locks.setdefault(scope, asyncio.Lock())
    async with lock:
        yield


async def register_dataset_version(
    session: AsyncSession,
    request: BenchmarkDatasetVersionCreateRequest,
    *,
    subject: str,
) -> tuple[BenchmarkDatasetVersion, bool]:
    async with _claim_identity(session, f"benchmark-dataset:{request.content_sha256}"):
        existing = await session.scalar(
            select(BenchmarkDatasetVersion).where(
                (BenchmarkDatasetVersion.id == request.dataset_version_id)
                | (
                    (BenchmarkDatasetVersion.dataset_id == request.dataset_id)
                    & (BenchmarkDatasetVersion.version == request.version)
                )
                | (BenchmarkDatasetVersion.content_sha256 == request.content_sha256)
            )
        )
        if existing is not None:
            if (
                existing.dataset_id == request.dataset_id
                and existing.version == request.version
                and existing.content_sha256 == request.content_sha256
                and existing.manifest_sha256 == request.manifest_sha256
            ):
                return existing, True
            raise ConflictError("benchmark dataset identity already exists with different content")
        dataset = BenchmarkDatasetVersion(
            id=request.dataset_version_id,
            tenant_id=request.tenant_id,
            dataset_id=request.dataset_id,
            version=request.version,
            status=request.status,
            source_uri=request.source_uri,
            manifest_uri=request.manifest_uri,
            manifest_sha256=request.manifest_sha256,
            content_sha256=request.content_sha256,
            source_archive_md5=request.source_archive_md5,
            source_archive_sha256=request.source_archive_sha256,
            size_bytes=request.size_bytes,
            file_count=request.file_count,
            license_name=request.license_name,
            license_url=request.license_url,
            doi=request.doi,
            citation=request.citation,
            attribution=request.attribution,
            created_by=subject,
        )
        session.add(dataset)
        await session.flush()
        append_domain_event(
            session,
            event_type="benchmark.import.registered",
            aggregate_type="benchmark_dataset",
            aggregate_id=dataset.id,
            payload={
                "tenant_id": dataset.tenant_id,
                "dataset_id": dataset.dataset_id,
                "dataset_version": dataset.version,
                "content_sha256": dataset.content_sha256,
                "manifest_sha256": dataset.manifest_sha256,
                "requested_by": subject,
            },
        )
        return dataset, False


async def register_benchmark_file(
    session: AsyncSession,
    request: BenchmarkFileCreateRequest,
) -> tuple[BenchmarkFile, bool]:
    async with _claim_identity(
        session,
        f"benchmark-file:{request.dataset_version_id}:{request.relative_path}",
    ):
        existing = await session.scalar(
            select(BenchmarkFile).where(
                BenchmarkFile.dataset_version_id == request.dataset_version_id,
                BenchmarkFile.relative_path == request.relative_path,
            )
        )
        if existing is not None:
            if (
                existing.content_sha256 == request.content_sha256
                and existing.schema_sha256 == request.schema_sha256
                and existing.row_count == request.row_count
            ):
                return existing, True
            raise ConflictError("benchmark file path already exists with different content")
        if await session.get(BenchmarkDatasetVersion, request.dataset_version_id) is None:
            raise NotFoundError(f"benchmark dataset {request.dataset_version_id} was not found")
        row = BenchmarkFile(
            id=request.file_id,
            dataset_version_id=request.dataset_version_id,
            file_kind=request.file_kind,
            relative_path=request.relative_path,
            farm=request.farm,
            event_id=request.event_id,
            size_bytes=request.size_bytes,
            row_count=request.row_count,
            schema_sha256=request.schema_sha256,
            content_sha256=request.content_sha256,
            metadata_=request.metadata,
        )
        session.add(row)
        await session.flush()
        return row, False


async def register_benchmark_event(
    session: AsyncSession,
    request: BenchmarkEventCreateRequest,
) -> tuple[BenchmarkEvent, bool]:
    scope = f"benchmark-event:{request.dataset_version_id}:{request.event_id}"
    async with _claim_identity(session, scope):
        existing = await session.scalar(
            select(BenchmarkEvent).where(
                BenchmarkEvent.dataset_version_id == request.dataset_version_id,
                BenchmarkEvent.event_id == request.event_id,
            )
        )
        if existing is not None:
            if (
                existing.source_file_id == request.source_file_id
                and existing.farm == request.farm
                and existing.source_asset_id == request.source_asset_id
                and existing.event_label == request.event_label
            ):
                return existing, True
            raise ConflictError("benchmark event identity already exists with different metadata")
        source_file = await session.get(BenchmarkFile, request.source_file_id)
        if source_file is None:
            raise NotFoundError(f"benchmark file {request.source_file_id} was not found")
        if (
            source_file.dataset_version_id != request.dataset_version_id
            or source_file.file_kind != "event"
            or source_file.farm != request.farm
            or source_file.event_id != request.event_id
        ):
            raise InvalidTransitionError("benchmark event does not match its immutable source file")
        row = BenchmarkEvent(
            id=request.benchmark_event_id,
            dataset_version_id=request.dataset_version_id,
            source_file_id=request.source_file_id,
            event_id=request.event_id,
            farm=request.farm,
            source_asset_id=request.source_asset_id,
            logical_asset_id=request.logical_asset_id,
            event_label=request.event_label,
            first_source_row_id=request.first_source_row_id,
            last_source_row_id=request.last_source_row_id,
            train_row_count=request.train_row_count,
            prediction_row_count=request.prediction_row_count,
            event_interval_start=request.event_interval_start,
            event_interval_end=request.event_interval_end,
            truth_metadata=request.truth_metadata,
        )
        session.add(row)
        await session.flush()
        return row, False


async def register_feature_map(
    session: AsyncSession,
    request: BenchmarkFeatureMapCreateRequest,
) -> tuple[BenchmarkFeatureMap, bool]:
    scope = (
        f"benchmark-feature-map:{request.dataset_version_id}:{request.mapping_version}:"
        f"{request.farm}:{request.source_column}"
    )
    async with _claim_identity(session, scope):
        existing = await session.scalar(
            select(BenchmarkFeatureMap).where(
                BenchmarkFeatureMap.dataset_version_id == request.dataset_version_id,
                BenchmarkFeatureMap.mapping_version == request.mapping_version,
                BenchmarkFeatureMap.farm == request.farm,
                BenchmarkFeatureMap.source_column == request.source_column,
            )
        )
        if existing is not None:
            if (
                existing.canonical_feature == request.canonical_feature
                and existing.statistic == request.statistic
                and existing.unit == request.unit
                and existing.enabled == request.enabled
                and existing.semantics == request.semantics
            ):
                return existing, True
            raise ConflictError("feature-map identity already exists with different semantics")
        if await session.get(BenchmarkDatasetVersion, request.dataset_version_id) is None:
            raise NotFoundError(f"benchmark dataset {request.dataset_version_id} was not found")
        row = BenchmarkFeatureMap(
            id=request.feature_map_id,
            dataset_version_id=request.dataset_version_id,
            mapping_version=request.mapping_version,
            farm=request.farm,
            source_column=request.source_column,
            canonical_feature=request.canonical_feature,
            statistic=request.statistic,
            unit=request.unit,
            enabled=request.enabled,
            semantics=request.semantics,
        )
        session.add(row)
        await session.flush()
        return row, False


async def register_quality_report(
    session: AsyncSession,
    request: BenchmarkQualityReportCreateRequest,
    *,
    subject: str = "benchmark-worker",
) -> tuple[BenchmarkQualityReport, bool]:
    scope = (
        f"benchmark-quality-canonical:{request.event_id}:{request.quality_rule_version}:"
        f"{request.feature_set_version}"
    )
    async with _claim_identity(session, scope):
        existing = await session.scalar(
            select(BenchmarkQualityReport).where(
                BenchmarkQualityReport.event_id == request.event_id,
                BenchmarkQualityReport.quality_rule_version == request.quality_rule_version,
                BenchmarkQualityReport.feature_set_version == request.feature_set_version,
            )
        )
        if existing is not None:
            if existing.status != request.status or (
                existing.canonical_content_sha256 is not None
                and existing.canonical_content_sha256 != request.canonical_content_sha256
            ):
                raise ConflictError("quality-report identity already exists with different content")
            if existing.canonical_content_sha256 is None:
                existing.canonical_content_sha256 = request.canonical_content_sha256
            row = existing
        else:
            if await session.get(BenchmarkEvent, request.event_id) is None:
                raise NotFoundError(f"benchmark event {request.event_id} was not found")
            row = BenchmarkQualityReport(
                id=request.quality_report_id,
                event_id=request.event_id,
                quality_rule_version=request.quality_rule_version,
                feature_set_version=request.feature_set_version,
                canonical_content_sha256=request.canonical_content_sha256,
                status=request.status,
                artifact_uri=request.artifact_uri,
                artifact_sha256=request.artifact_sha256,
                mask_uri=request.mask_uri,
                mask_sha256=request.mask_sha256,
                summary=request.summary,
            )
            session.add(row)
        await session.flush()

        artifact_identity = _document_sha256(
            {
                "quality_report_id": row.id,
                "canonical_content_sha256": request.canonical_content_sha256,
                "artifact_stage": request.artifact_stage,
                "artifact_uri": request.artifact_uri,
                "artifact_sha256": request.artifact_sha256,
                "mask_uri": request.mask_uri,
                "mask_sha256": request.mask_sha256,
                "summary": request.summary,
            }
        )
        artifact = await session.scalar(
            select(BenchmarkQualityArtifact).where(
                BenchmarkQualityArtifact.identity_sha256 == artifact_identity
            )
        )
        if artifact is not None:
            if (
                artifact.quality_report_id != row.id
                or artifact.artifact_stage != request.artifact_stage
                or artifact.artifact_uri != request.artifact_uri
                or artifact.artifact_sha256 != request.artifact_sha256
                or artifact.mask_uri != request.mask_uri
                or artifact.mask_sha256 != request.mask_sha256
                or artifact.summary != request.summary
            ):
                raise ConflictError(
                    "quality artifact identity already exists with different content"
                )
            return row, True
        artifact = BenchmarkQualityArtifact(
            id=f"care-qa-{artifact_identity[:56]}",
            quality_report_id=row.id,
            artifact_stage=request.artifact_stage,
            identity_sha256=artifact_identity,
            artifact_uri=request.artifact_uri,
            artifact_sha256=request.artifact_sha256,
            mask_uri=request.mask_uri,
            mask_sha256=request.mask_sha256,
            summary=request.summary,
            audit_subject=subject,
        )
        session.add(artifact)
        await session.flush()
        append_domain_event(
            session,
            event_type="benchmark.transform.quality.completed",
            aggregate_type="benchmark_event",
            aggregate_id=request.event_id,
            payload={
                "quality_report_id": row.id,
                "quality_artifact_id": artifact.id,
                "artifact_stage": artifact.artifact_stage,
                "canonical_content_sha256": request.canonical_content_sha256,
                "quality_rule_version": row.quality_rule_version,
                "feature_set_version": row.feature_set_version,
                "artifact_sha256": artifact.artifact_sha256,
                "mask_sha256": artifact.mask_sha256,
                "requested_by": subject,
            },
        )
        return row, False


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


async def register_replay_run(
    session: AsyncSession,
    request: BenchmarkReplayRunCreateRequest,
    *,
    subject: str,
) -> tuple[BenchmarkReplayRun, bool]:
    async with _claim_identity(session, f"benchmark-replay:{request.benchmark_replay_run_id}"):
        existing = await session.get(BenchmarkReplayRun, request.benchmark_replay_run_id)
        if existing is not None:
            if _replay_run_matches_request(existing, request, subject=subject):
                return existing, True
            raise ConflictError("benchmark replay run ID already exists with different identity")
        event = await session.get(BenchmarkEvent, request.event_id)
        if event is None or event.dataset_version_id != request.dataset_version_id:
            raise InvalidTransitionError("benchmark replay event does not match its dataset")
        if (
            event.farm != request.farm
            or event.event_id != request.source_event_number
            or event.logical_asset_id != request.logical_asset_id
            or event.source_asset_id != request.source_asset_id
        ):
            raise InvalidTransitionError("benchmark replay identity does not match its event")
        if await session.get(Turbine, request.online_turbine_id) is None:
            raise NotFoundError(f"online replay turbine {request.online_turbine_id} was not found")
        if request.model_id is not None:
            model = await session.get(RegisteredModel, request.model_id)
            if model is None or model.version != request.model_version:
                raise InvalidTransitionError("benchmark replay model ID/version is not registered")
        if request.deployment_id is not None:
            deployment = await session.get(ModelDeployment, request.deployment_id)
            if deployment is None:
                raise NotFoundError(
                    f"benchmark replay deployment {request.deployment_id} was not found"
                )
            if deployment.model_id != request.model_id:
                raise InvalidTransitionError(
                    "benchmark replay deployment does not belong to the registered model"
                )
        row = BenchmarkReplayRun(
            id=request.benchmark_replay_run_id,
            dataset_version_id=request.dataset_version_id,
            event_id=request.event_id,
            source_asset_id=request.source_asset_id,
            logical_asset_id=request.logical_asset_id,
            online_turbine_id=request.online_turbine_id,
            farm=request.farm,
            source_event_number=request.source_event_number,
            replay_mode=request.replay_mode,
            speed=request.speed,
            status=request.status,
            replay_anchor_at=request.replay_anchor_at,
            time_rule_version=request.time_rule_version,
            sequence_rule_version=request.sequence_rule_version,
            source_event_id_rule_version=request.source_event_id_rule_version,
            selected_variables=request.selected_variables,
            window_start_row_id=request.window_start_row_id,
            window_end_row_id=request.window_end_row_id,
            checkpoint=request.checkpoint,
            checkpoint_revision=request.checkpoint_revision,
            checkpoint_sha256=request.checkpoint_sha256,
            model_id=request.model_id,
            model_version=request.model_version,
            deployment_id=request.deployment_id,
            threshold_policy_version=request.threshold_policy_version,
            threshold_policy_sha256=request.threshold_policy_sha256,
            created_by=subject,
            started_at=request.started_at,
            finished_at=request.finished_at,
            cancelled_by=request.cancelled_by,
            error=request.error,
        )
        session.add(row)
        await session.flush()
        append_domain_event(
            session,
            event_type="benchmark.replay.registered",
            aggregate_type="benchmark_replay",
            aggregate_id=row.id,
            payload={
                "dataset_version_id": row.dataset_version_id,
                "event_id": row.event_id,
                "online_turbine_id": row.online_turbine_id,
                "model_id": row.model_id,
                "model_version": row.model_version,
                "checkpoint_sha256": row.checkpoint_sha256,
                "requested_by": subject,
            },
        )
        return row, False


def _replay_immutable_identity(
    row: BenchmarkReplayRun,
) -> tuple[object, ...]:
    return (
        row.dataset_version_id,
        row.event_id,
        row.source_asset_id,
        row.logical_asset_id,
        row.online_turbine_id,
        row.farm,
        row.source_event_number,
        row.replay_mode,
        row.speed,
        _as_utc(row.replay_anchor_at),
        row.time_rule_version,
        row.sequence_rule_version,
        row.source_event_id_rule_version,
        row.selected_variables,
        row.window_start_row_id,
        row.window_end_row_id,
        row.model_id,
        row.model_version,
        row.deployment_id,
        row.threshold_policy_version,
        row.threshold_policy_sha256,
        row.created_by,
    )


def _request_replay_immutable_identity(
    request: BenchmarkReplayRunCreateRequest,
    *,
    subject: str,
) -> tuple[object, ...]:
    return (
        request.dataset_version_id,
        request.event_id,
        request.source_asset_id,
        request.logical_asset_id,
        request.online_turbine_id,
        request.farm,
        request.source_event_number,
        request.replay_mode,
        request.speed,
        _as_utc(request.replay_anchor_at),
        request.time_rule_version,
        request.sequence_rule_version,
        request.source_event_id_rule_version,
        request.selected_variables,
        request.window_start_row_id,
        request.window_end_row_id,
        request.model_id,
        request.model_version,
        request.deployment_id,
        request.threshold_policy_version,
        request.threshold_policy_sha256,
        subject,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _replay_run_matches_request(
    row: BenchmarkReplayRun,
    request: BenchmarkReplayRunCreateRequest,
    *,
    subject: str,
) -> bool:
    return (
        _replay_immutable_identity(row)
        == _request_replay_immutable_identity(request, subject=subject)
        and row.status == request.status
        and row.checkpoint == request.checkpoint
        and row.checkpoint_revision == request.checkpoint_revision
        and row.checkpoint_sha256 == request.checkpoint_sha256
        and _same_instant(row.started_at, request.started_at)
        and _same_instant(row.finished_at, request.finished_at)
        and row.cancelled_by == request.cancelled_by
        and row.error == request.error
    )


async def persist_replay_run_progress(
    session: AsyncSession,
    request: BenchmarkReplayRunCreateRequest,
    *,
    subject: str,
) -> tuple[BenchmarkReplayRun, bool]:
    """Advance a registered replay only after every checkpoint row is durably ingested."""

    scope = f"benchmark-replay:{request.benchmark_replay_run_id}"
    async with _claim_identity(session, scope):
        row = await session.scalar(
            select(BenchmarkReplayRun)
            .where(BenchmarkReplayRun.id == request.benchmark_replay_run_id)
            .with_for_update()
        )
        if row is None:
            raise NotFoundError(
                f"benchmark replay run {request.benchmark_replay_run_id} was not found"
            )
        if _replay_run_matches_request(row, request, subject=subject):
            return row, True
        if _replay_immutable_identity(row) != _request_replay_immutable_identity(
            request, subject=subject
        ):
            raise ConflictError("benchmark replay immutable identity cannot be changed")
        status_only = (
            request.checkpoint_revision == row.checkpoint_revision
            and request.checkpoint == row.checkpoint
            and request.checkpoint_sha256 == row.checkpoint_sha256
            and request.status != row.status
        )
        if not status_only and request.checkpoint_revision != row.checkpoint_revision + 1:
            raise ConflictError("benchmark replay checkpoint requires the next revision")
        if request.checkpoint.get("revision") != request.checkpoint_revision:
            raise InvalidTransitionError("benchmark replay checkpoint revision is inconsistent")
        if request.checkpoint_sha256 != _document_sha256(request.checkpoint):
            raise InvalidTransitionError("benchmark replay checkpoint hash is invalid")
        previous_rows = row.checkpoint.get("last_confirmed_rows")
        requested_rows = request.checkpoint.get("last_confirmed_rows")
        if not isinstance(previous_rows, dict) or not isinstance(requested_rows, dict):
            raise InvalidTransitionError("benchmark replay checkpoint rows are malformed")
        variable_by_short_id = {
            str(value["short_id"]): str(value["canonical_variable"])
            for value in row.selected_variables
            if isinstance(value, dict)
        }
        if set(previous_rows) != set(requested_rows) or set(requested_rows) != set(
            variable_by_short_id
        ):
            raise InvalidTransitionError("benchmark replay checkpoint variables drifted")
        for short_id, requested_value in requested_rows.items():
            previous_value = previous_rows[short_id]
            if (
                isinstance(previous_value, bool)
                or not isinstance(previous_value, int)
                or isinstance(requested_value, bool)
                or not isinstance(requested_value, int)
                or requested_value < previous_value
                or requested_value > row.window_end_row_id
            ):
                raise InvalidTransitionError("benchmark replay checkpoint moved outside its window")
            if status_only or requested_value == previous_value:
                continue
            ingested_count = int(
                await session.scalar(
                    select(func.count(func.distinct(ScadaSample.source_sequence))).where(
                        ScadaSample.source_id == CARE_REPLAY_SOURCE_ID,
                        ScadaSample.turbine_id == row.online_turbine_id,
                        ScadaSample.variable == variable_by_short_id[short_id],
                        ScadaSample.source_sequence > previous_value,
                        ScadaSample.source_sequence <= requested_value,
                    )
                )
                or 0
            )
            if ingested_count != requested_value - previous_value:
                raise InvalidTransitionError(
                    "benchmark replay checkpoint cannot skip unconfirmed ingest rows"
                )
        allowed_transitions = {
            "pending": {"pending", "running", "cancelled", "failed"},
            "running": {"running", "cancelling", "completed", "failed"},
            "cancelling": {"cancelling", "cancelled", "failed"},
        }
        if request.status not in allowed_transitions.get(row.status, set()):
            raise InvalidTransitionError("benchmark replay status transition is invalid")
        if request.status == "completed" and any(
            value != row.window_end_row_id for value in requested_rows.values()
        ):
            raise InvalidTransitionError("completed replay requires a complete checkpoint")
        row.status = request.status
        row.checkpoint = request.checkpoint
        row.checkpoint_revision = request.checkpoint_revision
        row.checkpoint_sha256 = request.checkpoint_sha256
        row.started_at = request.started_at
        row.finished_at = request.finished_at
        row.cancelled_by = request.cancelled_by
        row.error = request.error
        append_domain_event(
            session,
            event_type="benchmark.replay.progressed",
            aggregate_type="benchmark_replay_run",
            aggregate_id=row.id,
            payload={
                "benchmark_replay_run_id": row.id,
                "status": row.status,
                "checkpoint_revision": row.checkpoint_revision,
                "checkpoint_sha256": row.checkpoint_sha256,
                "online_turbine_id": row.online_turbine_id,
            },
        )
        await session.flush()
        return row, False


async def persist_anomaly_alert_policy_state(
    session: AsyncSession,
    request: AnomalyAlertPolicyStateRequest,
) -> tuple[AnomalyAlertPolicyState, bool]:
    scope = (
        f"anomaly-alert-policy:{request.deployment_id}:{request.turbine_id}:"
        f"{request.component}:{request.policy_version}"
    )
    async with _claim_identity(session, scope):
        existing = await session.scalar(
            select(AnomalyAlertPolicyState)
            .where(
                AnomalyAlertPolicyState.deployment_id == request.deployment_id,
                AnomalyAlertPolicyState.turbine_id == request.turbine_id,
                AnomalyAlertPolicyState.component == request.component,
                AnomalyAlertPolicyState.policy_version == request.policy_version,
            )
            .with_for_update()
        )
        if existing is not None:
            same_state = (
                existing.id == request.policy_state_id
                and existing.policy_sha256 == request.policy_sha256
                and existing.phase == request.phase
                and existing.consecutive_trigger_count == request.consecutive_trigger_count
                and existing.consecutive_recovery_count == request.consecutive_recovery_count
                and _same_instant(existing.cooldown_until, request.cooldown_until)
                and existing.last_prediction_id == request.last_prediction_id
                and _same_instant(
                    existing.last_prediction_created_at,
                    request.last_prediction_created_at,
                )
                and existing.dedup_key == request.dedup_key
                and existing.policy_document == request.policy_document
                and existing.state_document == request.state_document
                and existing.revision == request.revision
            )
            if same_state:
                return existing, True
            if existing.id != request.policy_state_id:
                raise ConflictError("alert-policy scope already belongs to another state ID")
            if (
                existing.policy_sha256 != request.policy_sha256
                or existing.policy_document != request.policy_document
            ):
                raise ConflictError("alert-policy document is immutable within a policy version")
            if request.revision != existing.revision + 1:
                raise ConflictError("alert-policy state update requires the next revision")
        elif request.revision != 0:
            raise ConflictError("new alert-policy state must start at revision zero")

        deployment = await session.get(ModelDeployment, request.deployment_id)
        turbine = await session.get(Turbine, request.turbine_id)
        if deployment is None or turbine is None:
            raise NotFoundError("alert-policy deployment or turbine was not found")
        if request.last_prediction_id is not None:
            prediction = await session.get(ModelPrediction, request.last_prediction_id)
            if prediction is None:
                raise NotFoundError("alert-policy prediction was not found")
            if (
                prediction.deployment_id != request.deployment_id
                or prediction.turbine_id != request.turbine_id
            ):
                raise InvalidTransitionError(
                    "alert-policy prediction crosses deployment or turbine scope"
                )

        if existing is None:
            existing = AnomalyAlertPolicyState(
                id=request.policy_state_id,
                deployment_id=request.deployment_id,
                turbine_id=request.turbine_id,
                component=request.component,
                policy_version=request.policy_version,
                policy_sha256=request.policy_sha256,
                phase=request.phase,
                consecutive_trigger_count=request.consecutive_trigger_count,
                consecutive_recovery_count=request.consecutive_recovery_count,
                cooldown_until=request.cooldown_until,
                last_prediction_id=request.last_prediction_id,
                last_prediction_created_at=request.last_prediction_created_at,
                dedup_key=request.dedup_key,
                policy_document=request.policy_document,
                state_document=request.state_document,
                revision=request.revision,
            )
            session.add(existing)
        else:
            existing.phase = request.phase
            existing.consecutive_trigger_count = request.consecutive_trigger_count
            existing.consecutive_recovery_count = request.consecutive_recovery_count
            existing.cooldown_until = request.cooldown_until
            existing.last_prediction_id = request.last_prediction_id
            existing.last_prediction_created_at = request.last_prediction_created_at
            existing.dedup_key = request.dedup_key
            existing.state_document = request.state_document
            existing.revision = request.revision
            existing.updated_at = datetime.now(UTC)
        await session.flush()
        return existing, False


async def build_benchmark_trace(
    session: AsyncSession,
    *,
    alarm_id: str,
) -> BenchmarkTraceResponse:
    alarm = await session.get(Alarm, alarm_id)
    if alarm is None:
        raise NotFoundError(f"alarm {alarm_id} was not found")
    if alarm.model_prediction_id is None:
        raise InvalidTransitionError("alarm is not linked to a model prediction")
    prediction = await session.get(ModelPrediction, alarm.model_prediction_id)
    if prediction is None:  # pragma: no cover - protected by the foreign key
        raise NotFoundError("alarm model prediction was not found")
    if prediction.benchmark_replay_run_id is None or prediction.benchmark_evaluation_run_id is None:
        raise InvalidTransitionError("prediction lacks benchmark replay/evaluation provenance")
    replay = await session.get(BenchmarkReplayRun, prediction.benchmark_replay_run_id)
    evaluation = await session.get(BenchmarkEvaluationRun, prediction.benchmark_evaluation_run_id)
    if replay is None or evaluation is None:
        raise NotFoundError("benchmark replay or evaluation provenance was not found")
    event = await session.get(BenchmarkEvent, replay.event_id)
    if event is None:  # pragma: no cover - protected by the foreign key
        raise NotFoundError("benchmark event provenance was not found")
    if (
        evaluation.dataset_version_id != replay.dataset_version_id
        or evaluation.model_id != prediction.model_id
        or replay.online_turbine_id != prediction.turbine_id
    ):
        raise InvalidTransitionError("benchmark trace crosses dataset/model/replay identities")
    metric_ids = list(
        await session.scalars(
            select(BenchmarkMetricSnapshot.id)
            .where(BenchmarkMetricSnapshot.evaluation_run_id == evaluation.id)
            .order_by(BenchmarkMetricSnapshot.id)
        )
    )
    return BenchmarkTraceResponse(
        dataset_version_id=replay.dataset_version_id,
        event_id=event.id,
        model_id=prediction.model_id,
        model_version=evaluation.model_version,
        evaluation_run_id=evaluation.id,
        replay_run_id=replay.id,
        prediction_id=prediction.id,
        alarm_id=alarm.id,
        source_event_id=alarm.source_event_id,
        metric_snapshot_ids=metric_ids,
    )
