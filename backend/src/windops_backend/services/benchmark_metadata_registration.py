from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.models import (
    BenchmarkDatasetVersion,
    BenchmarkEvent,
    BenchmarkFeatureMap,
    BenchmarkFile,
    BenchmarkQualityArtifact,
    BenchmarkQualityReport,
)
from windops_backend.schemas import (
    BenchmarkDatasetVersionCreateRequest,
    BenchmarkEventCreateRequest,
    BenchmarkFeatureMapCreateRequest,
    BenchmarkFileCreateRequest,
    BenchmarkQualityReportCreateRequest,
)
from windops_backend.services.benchmark_metadata_contracts import (
    _claim_identity,
    _document_sha256,
)
from windops_backend.services.events import append_domain_event


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
