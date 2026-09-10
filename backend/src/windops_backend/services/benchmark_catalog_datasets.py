from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkEvent,
    BenchmarkFeatureMap,
    BenchmarkFile,
    BenchmarkQualityReport,
    BenchmarkReplayRun,
)
from windops_backend.services.benchmark_catalog_policy import (
    BENCHMARK_DATASET_PAGE_MAX,
    BENCHMARK_EVENT_COUNT_MAX,
    _status_counts,
    benchmark_dataset_scope_clause,
    benchmark_truth_allowed,
)


async def benchmark_dataset_page(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    query: str = "",
    status: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if not 1 <= limit <= BENCHMARK_DATASET_PAGE_MAX:
        raise ValueError(f"limit must be within 1..{BENCHMARK_DATASET_PAGE_MAX}")
    reveal_truth = benchmark_truth_allowed(policy)
    scope = benchmark_dataset_scope_clause(policy)
    base = (
        select(BenchmarkDatasetVersion)
        .where(scope)
        .execution_options(skip_windops_access_control=True)
    )
    total = int(
        await session.scalar(
            select(func.count(BenchmarkDatasetVersion.id))
            .where(scope)
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    filters: list[Any] = []
    normalized_query = query.strip().casefold()
    if normalized_query:
        filters.append(
            or_(
                func.lower(BenchmarkDatasetVersion.id).contains(normalized_query, autoescape=True),
                func.lower(BenchmarkDatasetVersion.dataset_id).contains(
                    normalized_query, autoescape=True
                ),
                func.lower(BenchmarkDatasetVersion.version).contains(
                    normalized_query, autoescape=True
                ),
                func.lower(BenchmarkDatasetVersion.doi).contains(normalized_query, autoescape=True),
                func.lower(BenchmarkDatasetVersion.license_name).contains(
                    normalized_query, autoescape=True
                ),
            )
        )
    if status:
        filters.append(BenchmarkDatasetVersion.status == status)
    filtered = base.where(*filters)
    filtered_total = int(
        await session.scalar(
            select(func.count())
            .select_from(filtered.order_by(None).subquery())
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    datasets = list(
        (
            await session.scalars(
                filtered.order_by(
                    BenchmarkDatasetVersion.dataset_id,
                    BenchmarkDatasetVersion.version,
                    BenchmarkDatasetVersion.id,
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    dataset_ids = [row.id for row in datasets]
    if not dataset_ids:
        return {
            "data": [],
            "meta": {
                "count": 0,
                "total": total,
                "filtered_total": filtered_total,
                "offset": offset,
                "limit": limit,
                "has_more": False,
                "next_offset": None,
                "bounds": {
                    "dataset_page_max": BENCHMARK_DATASET_PAGE_MAX,
                    "event_count_per_dataset_max": BENCHMARK_EVENT_COUNT_MAX,
                },
            },
        }

    event_aggregates = {
        str(row.dataset_version_id): row
        for row in (
            await session.execute(
                select(
                    BenchmarkEvent.dataset_version_id,
                    func.count(BenchmarkEvent.id).label("event_count"),
                    func.count(func.distinct(BenchmarkEvent.farm)).label("farm_count"),
                    func.count(func.distinct(BenchmarkEvent.logical_asset_id)).label("asset_count"),
                    func.coalesce(func.sum(BenchmarkEvent.train_row_count), 0).label("train_rows"),
                    func.coalesce(func.sum(BenchmarkEvent.prediction_row_count), 0).label(
                        "prediction_rows"
                    ),
                    (
                        func.coalesce(
                            func.sum(case((BenchmarkEvent.event_label == "anomaly", 1), else_=0)),
                            0,
                        )
                        if reveal_truth
                        else literal(None)
                    ).label("anomaly_count"),
                    (
                        func.coalesce(
                            func.sum(case((BenchmarkEvent.event_label == "normal", 1), else_=0)),
                            0,
                        )
                        if reveal_truth
                        else literal(None)
                    ).label("normal_count"),
                )
                .where(BenchmarkEvent.dataset_version_id.in_(dataset_ids))
                .group_by(BenchmarkEvent.dataset_version_id)
                .execution_options(skip_windops_access_control=True)
            )
        ).all()
    }
    file_aggregates = {
        str(row.dataset_version_id): row
        for row in (
            await session.execute(
                select(
                    BenchmarkFile.dataset_version_id,
                    func.count(BenchmarkFile.id).label("registered_file_count"),
                    func.coalesce(func.sum(BenchmarkFile.row_count), 0).label("registered_rows"),
                    func.coalesce(
                        func.sum(case((BenchmarkFile.file_kind == "event", 1), else_=0)), 0
                    ).label("standard_event_count"),
                )
                .where(BenchmarkFile.dataset_version_id.in_(dataset_ids))
                .group_by(BenchmarkFile.dataset_version_id)
                .execution_options(skip_windops_access_control=True)
            )
        ).all()
    }
    mapping_aggregates = {
        str(row.dataset_version_id): row
        for row in (
            await session.execute(
                select(
                    BenchmarkFeatureMap.dataset_version_id,
                    func.count(BenchmarkFeatureMap.id).label("mapping_count"),
                    func.coalesce(
                        func.sum(case((BenchmarkFeatureMap.enabled.is_(True), 1), else_=0)), 0
                    ).label("enabled_count"),
                    func.coalesce(
                        func.sum(case((BenchmarkFeatureMap.enabled.is_(False), 1), else_=0)), 0
                    ).label("disabled_count"),
                    func.coalesce(
                        func.sum(case((BenchmarkFeatureMap.unit == "unknown", 1), else_=0)), 0
                    ).label("unknown_unit_count"),
                )
                .where(BenchmarkFeatureMap.dataset_version_id.in_(dataset_ids))
                .group_by(BenchmarkFeatureMap.dataset_version_id)
                .execution_options(skip_windops_access_control=True)
            )
        ).all()
    }
    ranked_quality = (
        select(
            BenchmarkEvent.dataset_version_id.label("dataset_version_id"),
            BenchmarkQualityReport.id.label("report_id"),
            BenchmarkQualityReport.event_id.label("event_id"),
            BenchmarkQualityReport.status.label("status"),
            BenchmarkQualityReport.summary.label("summary"),
            BenchmarkQualityReport.quality_rule_version.label("quality_rule_version"),
            BenchmarkQualityReport.feature_set_version.label("feature_set_version"),
            func.row_number()
            .over(
                partition_by=BenchmarkQualityReport.event_id,
                order_by=(
                    BenchmarkQualityReport.created_at.desc(),
                    BenchmarkQualityReport.id.desc(),
                ),
            )
            .label("position"),
        )
        .join(BenchmarkEvent, BenchmarkQualityReport.event_id == BenchmarkEvent.id)
        .where(BenchmarkEvent.dataset_version_id.in_(dataset_ids))
        .subquery()
    )
    quality_rows = list(
        (
            await session.execute(
                select(ranked_quality)
                .where(ranked_quality.c.position == 1)
                .order_by(
                    ranked_quality.c.dataset_version_id,
                    ranked_quality.c.event_id,
                    ranked_quality.c.report_id,
                )
                .limit(len(dataset_ids) * BENCHMARK_EVENT_COUNT_MAX)
                .execution_options(skip_windops_access_control=True)
            )
        ).mappings()
    )
    quality_by_dataset: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "report_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "mask_count": 0,
            "raw_values_modified": False,
            "quality_rule_versions": set(),
            "feature_set_versions": set(),
        }
    )
    for report in quality_rows:
        summary = report["summary"] if isinstance(report["summary"], dict) else {}
        aggregate = quality_by_dataset[str(report["dataset_version_id"])]
        aggregate["report_count"] += 1
        aggregate["completed_count"] += int(report["status"] == "completed")
        aggregate["failed_count"] += int(report["status"] == "failed")
        aggregate["mask_count"] += int(summary.get("mask_count", 0))
        aggregate["raw_values_modified"] = bool(aggregate["raw_values_modified"]) or bool(
            summary.get("raw_values_modified", False)
        )
        aggregate["quality_rule_versions"].add(report["quality_rule_version"])
        aggregate["feature_set_versions"].add(report["feature_set_version"])

    evaluation_counts = _status_counts(
        [
            (str(dataset_id), str(run_status), int(count))
            for dataset_id, run_status, count in (
                await session.execute(
                    select(
                        BenchmarkEvaluationRun.dataset_version_id,
                        BenchmarkEvaluationRun.status,
                        func.count(BenchmarkEvaluationRun.id),
                    )
                    .where(BenchmarkEvaluationRun.dataset_version_id.in_(dataset_ids))
                    .group_by(
                        BenchmarkEvaluationRun.dataset_version_id,
                        BenchmarkEvaluationRun.status,
                    )
                    .execution_options(skip_windops_access_control=True)
                )
            ).all()
        ]
    )
    replay_counts = _status_counts(
        [
            (str(dataset_id), str(run_status), int(count))
            for dataset_id, run_status, count in (
                await session.execute(
                    select(
                        BenchmarkReplayRun.dataset_version_id,
                        BenchmarkReplayRun.status,
                        func.count(BenchmarkReplayRun.id),
                    )
                    .where(BenchmarkReplayRun.dataset_version_id.in_(dataset_ids))
                    .group_by(
                        BenchmarkReplayRun.dataset_version_id,
                        BenchmarkReplayRun.status,
                    )
                    .execution_options(skip_windops_access_control=True)
                )
            ).all()
        ]
    )

    result: list[dict[str, Any]] = []
    for dataset in datasets:
        event_summary = event_aggregates.get(dataset.id)
        file_summary = file_aggregates.get(dataset.id)
        mapping_summary = mapping_aggregates.get(dataset.id)
        quality = quality_by_dataset.get(dataset.id)
        quality_payload = quality or {
            "report_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "mask_count": 0,
            "raw_values_modified": False,
            "quality_rule_versions": set(),
            "feature_set_versions": set(),
        }
        train_rows = int(event_summary.train_rows) if event_summary is not None else 0
        prediction_rows = int(event_summary.prediction_rows) if event_summary is not None else 0
        result.append(
            {
                "dataset_version_id": dataset.id,
                "dataset_id": dataset.dataset_id,
                "version": dataset.version,
                "status": dataset.status,
                "source_uri": dataset.source_uri,
                "manifest": {
                    "uri": dataset.manifest_uri,
                    "sha256": dataset.manifest_sha256,
                },
                "archive": {
                    "size_bytes": dataset.size_bytes,
                    "file_count": dataset.file_count,
                    "content_sha256": dataset.content_sha256,
                    "md5": dataset.source_archive_md5,
                    "sha256": dataset.source_archive_sha256,
                },
                "license": {
                    "name": dataset.license_name,
                    "url": dataset.license_url,
                    "doi": dataset.doi,
                    "citation": dataset.citation,
                    "attribution": dataset.attribution,
                },
                "coverage": {
                    "registered_file_count": (
                        int(file_summary.registered_file_count) if file_summary is not None else 0
                    ),
                    "registered_event_count": (
                        int(event_summary.event_count) if event_summary is not None else 0
                    ),
                    "farm_count": int(event_summary.farm_count) if event_summary is not None else 0,
                    "asset_count": int(event_summary.asset_count)
                    if event_summary is not None
                    else 0,
                    "truth_summary": {
                        "access": "revealed" if reveal_truth else "restricted",
                        "anomaly_event_count": (
                            int(event_summary.anomaly_count)
                            if reveal_truth and event_summary is not None
                            else None
                        ),
                        "normal_event_count": (
                            int(event_summary.normal_count)
                            if reveal_truth and event_summary is not None
                            else None
                        ),
                    },
                    "train_row_count": train_rows,
                    "prediction_row_count": prediction_rows,
                    "time_point_count": train_rows + prediction_rows,
                },
                "layers": {
                    "raw": {"status": "registered", "file_count": dataset.file_count},
                    "standard": {
                        "status": (
                            "ready"
                            if file_summary is not None
                            and int(file_summary.standard_event_count) > 0
                            else "not-started"
                        ),
                        "event_count": int(file_summary.standard_event_count)
                        if file_summary is not None
                        else 0,
                    },
                    "quality": {
                        "status": (
                            "failed"
                            if int(quality_payload["failed_count"]) > 0
                            else "ready"
                            if int(quality_payload["completed_count"]) > 0
                            else "not-started"
                        ),
                        "report_count": int(quality_payload["report_count"]),
                    },
                },
                "mapping": {
                    "total": int(mapping_summary.mapping_count)
                    if mapping_summary is not None
                    else 0,
                    "enabled": int(mapping_summary.enabled_count)
                    if mapping_summary is not None
                    else 0,
                    "disabled": int(mapping_summary.disabled_count)
                    if mapping_summary is not None
                    else 0,
                    "unknown_unit": int(mapping_summary.unknown_unit_count)
                    if mapping_summary is not None
                    else 0,
                    "failed": 0,
                },
                "quality": {
                    "report_count": int(quality_payload["report_count"]),
                    "completed_count": int(quality_payload["completed_count"]),
                    "failed_count": int(quality_payload["failed_count"]),
                    "mask_count": int(quality_payload["mask_count"]),
                    "raw_values_modified": bool(quality_payload["raw_values_modified"]),
                    "quality_rule_versions": sorted(quality_payload["quality_rule_versions"]),
                    "feature_set_versions": sorted(quality_payload["feature_set_versions"]),
                },
                "runs": {
                    "import": {"status": dataset.status},
                    "evaluation": evaluation_counts.get(dataset.id, {}),
                    "replay": replay_counts.get(dataset.id, {}),
                },
                "created_at": dataset.created_at,
            }
        )
    return {
        "data": result,
        "meta": {
            "count": len(result),
            "total": total,
            "filtered_total": filtered_total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(result) < filtered_total,
            "next_offset": offset + len(result) if offset + len(result) < filtered_total else None,
            "bounds": {
                "dataset_page_max": BENCHMARK_DATASET_PAGE_MAX,
                "event_count_per_dataset_max": BENCHMARK_EVENT_COUNT_MAX,
                "quality_rows_loaded_max": len(dataset_ids) * BENCHMARK_EVENT_COUNT_MAX,
            },
        },
    }
