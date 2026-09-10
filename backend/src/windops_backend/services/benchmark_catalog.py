from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from sqlalchemy import String, case, false, func, literal, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.access_control import data_scope_allowed, turbine_scope_clause
from windops_backend.benchmarks.care.replay import CARE_REPLAY_SOURCE_ID
from windops_backend.errors import NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
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
    Mission,
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
    ScadaSample,
)

BENCHMARK_DATASET_PAGE_MAX = 50
BENCHMARK_EVENT_PAGE_MAX = 64
BENCHMARK_EVENT_COUNT_MAX = 95
BENCHMARK_CURVE_POINT_MAX = 512
BENCHMARK_CURVE_POINT_MIN = 16
BENCHMARK_REPLAYS_PER_EVENT_MAX = 5
BENCHMARK_VARIABLES_PER_REPLAY_MAX = 64
BENCHMARK_EVALUATION_PAGE_MAX = 32
BENCHMARK_EVALUATION_METRICS_MAX = 64
BENCHMARK_EVENT_RESULT_PAGE_MAX = 64
BENCHMARK_DEPLOYMENTS_PER_MODEL_MAX = 8
BENCHMARK_DIAGNOSIS_PAGE_MAX = 32
BENCHMARK_PREDICTIONS_PER_REPLAY_MAX = 64
BENCHMARK_SIGNAL_SUMMARY_MAX = 64


def benchmark_truth_allowed(policy: GraphAccessPolicy) -> bool:
    if policy.unrestricted:
        return True
    normalized = {value.casefold() for value in policy.data_scopes}
    return "*" in normalized or "benchmark_truth" in normalized


def benchmark_domains_allowed(policy: GraphAccessPolicy, *domains: str) -> bool:
    """Require every named domain instead of the alias helper's any-domain semantics."""

    return policy.unrestricted or all(data_scope_allowed(policy, domain) for domain in domains)


def benchmark_dataset_scope_clause(policy: GraphAccessPolicy) -> Any:
    if policy.unrestricted:
        return true()
    if not data_scope_allowed(policy, "benchmark"):
        return false()
    if policy.allow_global:
        return true()
    tenant_ids = {value.casefold() for value in policy.tenant_ids}
    if not tenant_ids or "*" in tenant_ids:
        return false()
    return func.lower(BenchmarkDatasetVersion.tenant_id).in_(tuple(sorted(tenant_ids)))


def _status_counts(rows: list[tuple[str, str, int]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = defaultdict(dict)
    for dataset_version_id, status, count in rows:
        result[dataset_version_id][status] = int(count)
    return dict(result)


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


async def benchmark_event_page(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    dataset_version_id: str,
    query: str = "",
    farm: str | None = None,
    event_label: str | None = None,
    reveal_truth: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if not 1 <= limit <= BENCHMARK_EVENT_PAGE_MAX:
        raise ValueError(f"limit must be within 1..{BENCHMARK_EVENT_PAGE_MAX}")
    if (reveal_truth or event_label is not None) and not benchmark_truth_allowed(policy):
        raise PermissionError("benchmark truth access was not granted")
    dataset = await session.scalar(
        select(BenchmarkDatasetVersion)
        .where(
            BenchmarkDatasetVersion.id == dataset_version_id,
            benchmark_dataset_scope_clause(policy),
        )
        .execution_options(skip_windops_access_control=True)
    )
    if dataset is None:
        raise NotFoundError(f"benchmark dataset {dataset_version_id} was not found")
    event_columns: list[Any] = [
        BenchmarkEvent.id.label("benchmark_event_id"),
        BenchmarkEvent.event_id.label("event_number"),
        BenchmarkEvent.farm.label("farm"),
        BenchmarkEvent.source_asset_id.label("source_asset_id"),
        BenchmarkEvent.logical_asset_id.label("logical_asset_id"),
        BenchmarkEvent.first_source_row_id.label("first_source_row_id"),
        BenchmarkEvent.last_source_row_id.label("last_source_row_id"),
        BenchmarkEvent.train_row_count.label("train_row_count"),
        BenchmarkEvent.prediction_row_count.label("prediction_row_count"),
        (BenchmarkEvent.event_label if reveal_truth else literal(None)).label("event_label"),
        (BenchmarkEvent.event_interval_start if reveal_truth else literal(None)).label(
            "event_interval_start"
        ),
        (BenchmarkEvent.event_interval_end if reveal_truth else literal(None)).label(
            "event_interval_end"
        ),
    ]
    base = select(*event_columns).where(BenchmarkEvent.dataset_version_id == dataset_version_id)
    total = int(
        await session.scalar(
            select(func.count(BenchmarkEvent.id))
            .where(BenchmarkEvent.dataset_version_id == dataset_version_id)
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    filters: list[Any] = []
    normalized_query = query.strip().casefold()
    if normalized_query:
        filters.append(
            or_(
                func.lower(BenchmarkEvent.id).contains(normalized_query, autoescape=True),
                func.lower(BenchmarkEvent.logical_asset_id).contains(
                    normalized_query, autoescape=True
                ),
                func.lower(BenchmarkEvent.source_asset_id).contains(
                    normalized_query, autoescape=True
                ),
                func.cast(BenchmarkEvent.event_id, String).contains(
                    normalized_query, autoescape=True
                ),
            )
        )
    if farm:
        filters.append(BenchmarkEvent.farm == farm)
    if event_label:
        filters.append(BenchmarkEvent.event_label == event_label)
    filtered = base.where(*filters)
    filtered_total = int(
        await session.scalar(
            select(func.count())
            .select_from(filtered.order_by(None).subquery())
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    events = list(
        (
            await session.execute(
                filtered.order_by(BenchmarkEvent.farm, BenchmarkEvent.event_id)
                .offset(offset)
                .limit(limit)
                .execution_options(skip_windops_access_control=True)
            )
        ).mappings()
    )
    event_ids = [str(row["benchmark_event_id"]) for row in events]
    quality_by_event: dict[str, Any] = {}
    if event_ids:
        ranked_event_quality = (
            select(
                BenchmarkQualityReport.event_id.label("event_id"),
                BenchmarkQualityReport.status.label("status"),
                BenchmarkQualityReport.quality_rule_version.label("quality_rule_version"),
                BenchmarkQualityReport.feature_set_version.label("feature_set_version"),
                BenchmarkQualityReport.summary.label("summary"),
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
            .where(BenchmarkQualityReport.event_id.in_(event_ids))
            .subquery()
        )
        quality_by_event = {
            str(row["event_id"]): row
            for row in (
                await session.execute(
                    select(ranked_event_quality)
                    .where(ranked_event_quality.c.position == 1)
                    .execution_options(skip_windops_access_control=True)
                )
            ).mappings()
        }
    result_counts: dict[str, dict[str, int]] = defaultdict(dict)
    if event_ids:
        for event_id, result_status, count in (
            await session.execute(
                select(
                    BenchmarkEventResult.event_id,
                    BenchmarkEventResult.status,
                    func.count(BenchmarkEventResult.id),
                )
                .where(BenchmarkEventResult.event_id.in_(event_ids))
                .group_by(BenchmarkEventResult.event_id, BenchmarkEventResult.status)
                .execution_options(skip_windops_access_control=True)
            )
        ).all():
            result_counts[str(event_id)][str(result_status)] = int(count)

    replays_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if event_ids:
        ranked = (
            select(
                BenchmarkReplayRun.id,
                BenchmarkReplayRun.event_id,
                BenchmarkReplayRun.status,
                BenchmarkReplayRun.online_turbine_id,
                BenchmarkReplayRun.selected_variables,
                BenchmarkReplayRun.replay_anchor_at,
                BenchmarkReplayRun.created_at,
                func.row_number()
                .over(
                    partition_by=BenchmarkReplayRun.event_id,
                    order_by=(
                        BenchmarkReplayRun.created_at.desc(),
                        BenchmarkReplayRun.id.desc(),
                    ),
                )
                .label("position"),
            )
            .where(BenchmarkReplayRun.event_id.in_(event_ids))
            .subquery()
        )
        for row in (
            await session.execute(
                select(ranked)
                .where(ranked.c.position <= BENCHMARK_REPLAYS_PER_EVENT_MAX)
                .order_by(ranked.c.event_id, ranked.c.position)
                .execution_options(skip_windops_access_control=True)
            )
        ).mappings():
            variables = [
                str(value.get("canonical_variable"))
                for value in row["selected_variables"]
                if isinstance(value, dict) and value.get("canonical_variable")
            ]
            replays_by_event[str(row["event_id"])].append(
                {
                    "replay_run_id": row["id"],
                    "status": row["status"],
                    "online_turbine_id": row["online_turbine_id"],
                    "replay_anchor_at": row["replay_anchor_at"],
                    "created_at": row["created_at"],
                    "variables": variables[:BENCHMARK_VARIABLES_PER_REPLAY_MAX],
                    "variable_count": len(variables),
                    "variables_truncated": len(variables) > BENCHMARK_VARIABLES_PER_REPLAY_MAX,
                }
            )

    rows: list[dict[str, Any]] = []
    for event in events:
        benchmark_event_id = str(event["benchmark_event_id"])
        quality = quality_by_event.get(benchmark_event_id)
        summary = (
            quality["summary"]
            if quality is not None and isinstance(quality["summary"], dict)
            else {}
        )
        rows.append(
            {
                "benchmark_event_id": benchmark_event_id,
                "event_id": event["event_number"],
                "farm": event["farm"],
                "source_asset_id": event["source_asset_id"],
                "logical_asset_id": event["logical_asset_id"],
                "rows": {
                    "first_source_row_id": event["first_source_row_id"],
                    "last_source_row_id": event["last_source_row_id"],
                    "train": event["train_row_count"],
                    "prediction": event["prediction_row_count"],
                    "total": event["train_row_count"] + event["prediction_row_count"],
                },
                "truth": {
                    "access": "revealed" if reveal_truth else "restricted",
                    "event_label": event["event_label"],
                    "event_interval_start": event["event_interval_start"],
                    "event_interval_end": event["event_interval_end"],
                },
                "quality": {
                    "status": quality["status"] if quality is not None else "not-started",
                    "quality_rule_version": quality["quality_rule_version"]
                    if quality is not None
                    else None,
                    "feature_set_version": quality["feature_set_version"]
                    if quality is not None
                    else None,
                    "mask_count": int(summary.get("mask_count", 0)),
                    "raw_values_modified": bool(summary.get("raw_values_modified", False)),
                },
                "evaluation_results": result_counts.get(benchmark_event_id, {}),
                "recent_replays": replays_by_event.get(benchmark_event_id, []),
            }
        )
    return {
        "data": rows,
        "meta": {
            "dataset_version_id": dataset.id,
            "count": len(rows),
            "total": total,
            "filtered_total": filtered_total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(rows) < filtered_total,
            "next_offset": offset + len(rows) if offset + len(rows) < filtered_total else None,
            "truth_revealed": reveal_truth,
            "bounds": {
                "event_page_max": BENCHMARK_EVENT_PAGE_MAX,
                "recent_replays_per_event_max": BENCHMARK_REPLAYS_PER_EVENT_MAX,
                "variables_per_replay_max": BENCHMARK_VARIABLES_PER_REPLAY_MAX,
            },
        },
    }


async def benchmark_replay_curve(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    replay_run_id: str,
    variable: str,
    max_points: int = 256,
) -> dict[str, Any]:
    if not BENCHMARK_CURVE_POINT_MIN <= max_points <= BENCHMARK_CURVE_POINT_MAX:
        raise ValueError(
            f"max_points must be within {BENCHMARK_CURVE_POINT_MIN}..{BENCHMARK_CURVE_POINT_MAX}"
        )
    row = (
        await session.execute(
            select(BenchmarkReplayRun, BenchmarkDatasetVersion)
            .join(
                BenchmarkDatasetVersion,
                BenchmarkDatasetVersion.id == BenchmarkReplayRun.dataset_version_id,
            )
            .where(
                BenchmarkReplayRun.id == replay_run_id,
                benchmark_dataset_scope_clause(policy),
            )
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError(f"benchmark replay run {replay_run_id} was not found")
    replay, dataset = row
    selected_variables = {
        str(value.get("canonical_variable"))
        for value in replay.selected_variables
        if isinstance(value, dict) and value.get("canonical_variable")
    }
    if variable not in selected_variables:
        raise NotFoundError("the requested variable is not part of the governed replay")
    filters = (
        ScadaSample.source_id == CARE_REPLAY_SOURCE_ID,
        ScadaSample.turbine_id == replay.online_turbine_id,
        ScadaSample.variable == variable,
    )
    total = int(
        await session.scalar(select(func.count()).select_from(ScadaSample).where(*filters)) or 0
    )
    if total == 0:
        points: list[dict[str, Any]] = []
        stride = 1
    else:
        stride = max(1, math.ceil((total - 1) / max(1, max_points - 1)))
        ranked = (
            select(
                ScadaSample.id,
                ScadaSample.observed_at,
                ScadaSample.source_sequence,
                ScadaSample.value,
                ScadaSample.unit,
                ScadaSample.quality,
                ScadaSample.attributes,
                func.row_number()
                .over(order_by=(ScadaSample.observed_at, ScadaSample.id))
                .label("position"),
            )
            .where(*filters)
            .subquery()
        )
        sampled = list(
            (
                await session.execute(
                    select(ranked)
                    .where(
                        or_(
                            ranked.c.position == 1,
                            ranked.c.position == total,
                            (ranked.c.position - 1) % stride == 0,
                        )
                    )
                    .order_by(ranked.c.position)
                    .limit(max_points)
                )
            ).mappings()
        )
        points = []
        for sample in sampled:
            attributes = sample["attributes"] if isinstance(sample["attributes"], dict) else {}
            points.append(
                {
                    "observed_at": sample["observed_at"],
                    "value": sample["value"],
                    "unit": sample["unit"],
                    "quality": sample["quality"],
                    "source_sequence": sample["source_sequence"],
                    "source_row_id": attributes.get("source_row_id"),
                    "anonymous_observed_at": attributes.get("anonymous_observed_at"),
                    "source_time_stamp": attributes.get("source_time_stamp"),
                    "status_type_id": attributes.get("status_type_id"),
                    "quality_mask_refs": attributes.get("quality_mask_refs", []),
                    "observed_at_is_synthetic": bool(
                        attributes.get("observed_at_is_synthetic", False)
                    ),
                    "time_claim": attributes.get("time_claim"),
                }
            )
    return {
        "data": points,
        "meta": {
            "dataset_version_id": dataset.id,
            "replay_run_id": replay.id,
            "event_id": replay.event_id,
            "online_turbine_id": replay.online_turbine_id,
            "variable": variable,
            "count": len(points),
            "source_point_count": total,
            "max_points": max_points,
            "stride": stride,
            "downsample_algorithm": "deterministic-endpoint-preserving-stride-v1",
            "bounded": True,
            "raw_csv_loaded": False,
            "truth_included": False,
            "time_semantics": "synthetic-replay-time-not-field-time",
            "bounds": {
                "curve_point_min": BENCHMARK_CURVE_POINT_MIN,
                "curve_point_max": BENCHMARK_CURVE_POINT_MAX,
                "response_point_max": max_points,
            },
        },
    }


def _safe_document(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _evaluation_gate_reasons(
    evaluation: BenchmarkEvaluationRun,
    model: RegisteredModel,
    metrics: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if model.kind != "anomaly":
        reasons.append("MODEL_KIND_NOT_ANOMALY")
    if evaluation.status != "completed":
        reasons.append("EVALUATION_NOT_COMPLETED")
    if evaluation.invalidated_at is not None:
        reasons.append("EVALUATION_INVALIDATED")
    if not evaluation.artifact_uri or not evaluation.artifact_sha256:
        reasons.append("EVALUATION_ARTIFACT_MISSING")
    if evaluation.requested_event_count != (
        evaluation.scored_event_count
        + evaluation.failed_event_count
        + evaluation.unscorable_event_count
    ):
        reasons.append("EVENT_ACCOUNTING_INCOMPLETE")
    if evaluation.failed_event_count:
        reasons.append("FAILED_EVENTS_PRESENT")
    if evaluation.unscorable_event_count:
        reasons.append("UNSCORABLE_EVENTS_PRESENT")
    release_metrics = [metric for metric in metrics if metric["is_release_metric"]]
    if not release_metrics:
        reasons.append("RELEASE_METRICS_MISSING")
    elif any(metric["passed"] is not True for metric in release_metrics):
        reasons.append("RELEASE_METRIC_FAILED")
    return reasons


async def benchmark_evaluation_page(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    query: str = "",
    model_id: str | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if not 1 <= limit <= BENCHMARK_EVALUATION_PAGE_MAX:
        raise ValueError(f"limit must be within 1..{BENCHMARK_EVALUATION_PAGE_MAX}")
    if not benchmark_domains_allowed(policy, "benchmark", "model"):
        raise PermissionError("benchmark model access was not granted")
    base = (
        select(BenchmarkEvaluationRun, RegisteredModel, BenchmarkDatasetVersion)
        .join(RegisteredModel, RegisteredModel.id == BenchmarkEvaluationRun.model_id)
        .join(
            BenchmarkDatasetVersion,
            BenchmarkDatasetVersion.id == BenchmarkEvaluationRun.dataset_version_id,
        )
        .where(benchmark_dataset_scope_clause(policy))
    )
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(base.order_by(None).subquery())
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    filters: list[Any] = []
    normalized_query = query.strip().casefold()
    if normalized_query:
        filters.append(
            or_(
                func.lower(BenchmarkEvaluationRun.id).contains(normalized_query, autoescape=True),
                func.lower(BenchmarkEvaluationRun.model_id).contains(
                    normalized_query, autoescape=True
                ),
                func.lower(RegisteredModel.name).contains(normalized_query, autoescape=True),
                func.lower(BenchmarkEvaluationRun.protocol_version).contains(
                    normalized_query, autoescape=True
                ),
            )
        )
    if model_id:
        filters.append(BenchmarkEvaluationRun.model_id == model_id)
    if status:
        filters.append(BenchmarkEvaluationRun.status == status)
    filtered = base.where(*filters)
    filtered_total = int(
        await session.scalar(
            select(func.count())
            .select_from(filtered.order_by(None).subquery())
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    records = list(
        (
            await session.execute(
                filtered.order_by(
                    BenchmarkEvaluationRun.created_at.desc(), BenchmarkEvaluationRun.id.desc()
                )
                .offset(offset)
                .limit(limit)
                .execution_options(skip_windops_access_control=True)
            )
        ).all()
    )
    evaluation_ids = [record[0].id for record in records]
    model_ids = sorted({record[1].id for record in records})

    metric_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metric_totals: dict[str, int] = {}
    if evaluation_ids:
        metric_totals = {
            str(evaluation_id): int(count)
            for evaluation_id, count in (
                await session.execute(
                    select(
                        BenchmarkMetricSnapshot.evaluation_run_id,
                        func.count(BenchmarkMetricSnapshot.id),
                    )
                    .where(BenchmarkMetricSnapshot.evaluation_run_id.in_(evaluation_ids))
                    .group_by(BenchmarkMetricSnapshot.evaluation_run_id)
                )
            ).all()
        }
        ranked_metrics = (
            select(
                BenchmarkMetricSnapshot.evaluation_run_id,
                BenchmarkMetricSnapshot.metric_name,
                BenchmarkMetricSnapshot.protocol_version,
                BenchmarkMetricSnapshot.metric_version,
                BenchmarkMetricSnapshot.value,
                BenchmarkMetricSnapshot.unit,
                BenchmarkMetricSnapshot.numerator,
                BenchmarkMetricSnapshot.denominator,
                BenchmarkMetricSnapshot.is_release_metric,
                BenchmarkMetricSnapshot.threshold_value,
                BenchmarkMetricSnapshot.threshold_direction,
                BenchmarkMetricSnapshot.passed,
                func.row_number()
                .over(
                    partition_by=BenchmarkMetricSnapshot.evaluation_run_id,
                    order_by=(
                        BenchmarkMetricSnapshot.is_release_metric.desc(),
                        BenchmarkMetricSnapshot.metric_name,
                        BenchmarkMetricSnapshot.id,
                    ),
                )
                .label("position"),
            )
            .where(BenchmarkMetricSnapshot.evaluation_run_id.in_(evaluation_ids))
            .subquery()
        )
        for metric in (
            await session.execute(
                select(ranked_metrics)
                .where(ranked_metrics.c.position <= BENCHMARK_EVALUATION_METRICS_MAX)
                .order_by(ranked_metrics.c.evaluation_run_id, ranked_metrics.c.position)
            )
        ).mappings():
            metric_rows[str(metric["evaluation_run_id"])].append(
                {
                    "name": metric["metric_name"],
                    "protocol_version": metric["protocol_version"],
                    "metric_version": metric["metric_version"],
                    "value": metric["value"],
                    "unit": metric["unit"],
                    "numerator": metric["numerator"],
                    "denominator": metric["denominator"],
                    "is_release_metric": metric["is_release_metric"],
                    "threshold_value": metric["threshold_value"],
                    "threshold_direction": metric["threshold_direction"],
                    "passed": metric["passed"],
                }
            )

    deployments_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if model_ids:
        ranked_deployments = (
            select(
                ModelDeployment.id,
                ModelDeployment.model_id,
                ModelDeployment.target_id,
                ModelDeployment.stage,
                ModelDeployment.status,
                ModelDeployment.traffic_percent,
                ModelDeployment.evaluation_gate,
                ModelDeployment.deployed_at,
                ModelDeployment.activated_at,
                ModelDeployment.retired_at,
                func.row_number()
                .over(
                    partition_by=ModelDeployment.model_id,
                    order_by=(ModelDeployment.deployed_at.desc(), ModelDeployment.id.desc()),
                )
                .label("position"),
            )
            .where(ModelDeployment.model_id.in_(model_ids))
            .subquery()
        )
        for deployment_row in (
            await session.execute(
                select(ranked_deployments)
                .where(ranked_deployments.c.position <= BENCHMARK_DEPLOYMENTS_PER_MODEL_MAX)
                .order_by(ranked_deployments.c.model_id, ranked_deployments.c.position)
                .execution_options(skip_windops_access_control=True)
            )
        ).mappings():
            gate = _safe_document(deployment_row["evaluation_gate"])
            authorization = _safe_document(gate.get("server_authorization"))
            deployments_by_model[str(deployment_row["model_id"])].append(
                {
                    "deployment_id": deployment_row["id"],
                    "target_id": deployment_row["target_id"],
                    "stage": deployment_row["stage"],
                    "status": deployment_row["status"],
                    "traffic_percent": deployment_row["traffic_percent"],
                    "authorized_evaluation_run_id": authorization.get("evaluation_run_id"),
                    "gate_policy_version": authorization.get("gate_policy_version"),
                    "authorized_at": authorization.get("authorized_at"),
                    "deployed_at": deployment_row["deployed_at"],
                    "activated_at": deployment_row["activated_at"],
                    "retired_at": deployment_row["retired_at"],
                }
            )

    rows: list[dict[str, Any]] = []
    for evaluation, model, dataset in records:
        metrics = metric_rows.get(evaluation.id, [])
        gate_reasons = _evaluation_gate_reasons(evaluation, model, metrics)
        model_metrics = _safe_document(model.metrics)
        extension = _safe_document(evaluation.extension_data)
        deployments: list[dict[str, Any]] = []
        for deployment in deployments_by_model.get(model.id, []):
            authorized_run = deployment["authorized_evaluation_run_id"]
            active = deployment["status"] == "active"
            if active and authorized_run == evaluation.id and evaluation.invalidated_at is None:
                authorization_state = "current"
            elif active:
                authorization_state = "stale"
            elif authorized_run == evaluation.id:
                authorization_state = "inactive"
            else:
                authorization_state = "not-authorized-for-run"
            deployments.append({**deployment, "authorization_state": authorization_state})
        rows.append(
            {
                "evaluation_run_id": evaluation.id,
                "dataset": {
                    "dataset_version_id": dataset.id,
                    "dataset_id": dataset.dataset_id,
                    "version": dataset.version,
                },
                "model": {
                    "model_id": model.id,
                    "name": model.name,
                    "version": model.version,
                    "kind": model.kind,
                    "status": model.status,
                    "algorithm": extension.get("algorithm") or model_metrics.get("algorithm"),
                    "evaluation_role": extension.get("evaluation_role")
                    or model_metrics.get("evaluation_role"),
                    "artifact": {
                        "uri": model.artifact_uri,
                        "sha256": model.artifact_sha256,
                        "present": bool(model.artifact_uri and model.artifact_sha256),
                    },
                },
                "run": {
                    "kind": evaluation.run_kind,
                    "status": evaluation.status,
                    "farm": evaluation.farm,
                    "protocol_version": evaluation.protocol_version,
                    "feature_set_version": evaluation.feature_set_version,
                    "quality_rule_version": evaluation.quality_rule_version,
                    "threshold_policy_version": evaluation.threshold_policy_version,
                    "threshold_policy_sha256": evaluation.threshold_policy_sha256,
                    "random_seed": evaluation.random_seed,
                    "input_identity_sha256": evaluation.input_identity_sha256,
                    "prediction_truth_used": extension.get("prediction_truth_used"),
                    "dependency_identity": extension.get("dependency_identity")
                    or model_metrics.get("dependency_identity"),
                    "created_at": evaluation.created_at,
                    "started_at": evaluation.started_at,
                    "completed_at": evaluation.completed_at,
                    "invalidated_at": evaluation.invalidated_at,
                },
                "event_accounting": {
                    "requested": evaluation.requested_event_count,
                    "scored": evaluation.scored_event_count,
                    "failed": evaluation.failed_event_count,
                    "unscorable": evaluation.unscorable_event_count,
                },
                "evaluation_artifact": {
                    "uri": evaluation.artifact_uri,
                    "sha256": evaluation.artifact_sha256,
                    "present": bool(evaluation.artifact_uri and evaluation.artifact_sha256),
                    "immutable": bool(
                        evaluation.status == "completed"
                        and evaluation.completed_at is not None
                        and evaluation.artifact_uri
                        and evaluation.artifact_sha256
                    ),
                },
                "metrics": metrics,
                "metrics_truncated": metric_totals.get(evaluation.id, 0) > len(metrics),
                "server_gate": {
                    "eligible": not gate_reasons,
                    "reasons": gate_reasons,
                    "release_metric_count": sum(
                        1 for metric in metrics if metric["is_release_metric"]
                    ),
                },
                "deployments": deployments,
            }
        )
    return {
        "data": rows,
        "meta": {
            "count": len(rows),
            "total": total,
            "filtered_total": filtered_total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(rows) < filtered_total,
            "next_offset": offset + len(rows) if offset + len(rows) < filtered_total else None,
            "bounds": {
                "evaluation_page_max": BENCHMARK_EVALUATION_PAGE_MAX,
                "metrics_per_evaluation_max": BENCHMARK_EVALUATION_METRICS_MAX,
                "deployments_per_model_max": BENCHMARK_DEPLOYMENTS_PER_MODEL_MAX,
            },
        },
    }


async def benchmark_evaluation_result_page(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    evaluation_run_id: str,
    status: str | None = None,
    reveal_truth: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if not 1 <= limit <= BENCHMARK_EVENT_RESULT_PAGE_MAX:
        raise ValueError(f"limit must be within 1..{BENCHMARK_EVENT_RESULT_PAGE_MAX}")
    if not benchmark_domains_allowed(policy, "benchmark", "model"):
        raise PermissionError("benchmark model access was not granted")
    if reveal_truth and not benchmark_truth_allowed(policy):
        raise PermissionError("benchmark truth access was not granted")
    evaluation = await session.scalar(
        select(BenchmarkEvaluationRun)
        .join(
            BenchmarkDatasetVersion,
            BenchmarkDatasetVersion.id == BenchmarkEvaluationRun.dataset_version_id,
        )
        .where(
            BenchmarkEvaluationRun.id == evaluation_run_id,
            benchmark_dataset_scope_clause(policy),
        )
    )
    if evaluation is None:
        raise NotFoundError(f"benchmark evaluation {evaluation_run_id} was not found")
    columns: list[Any] = [
        BenchmarkEventResult.id.label("result_id"),
        BenchmarkEventResult.event_id.label("benchmark_event_id"),
        BenchmarkEventResult.status,
        BenchmarkEventResult.scorable,
        BenchmarkEventResult.anomaly_detected,
        BenchmarkEventResult.care_score,
        BenchmarkEventResult.coverage_score,
        BenchmarkEventResult.accuracy_score,
        BenchmarkEventResult.reliability_score,
        BenchmarkEventResult.earliness_score,
        BenchmarkEventResult.prediction_artifact_uri,
        BenchmarkEventResult.prediction_artifact_sha256,
        BenchmarkEventResult.failure_code,
        BenchmarkEventResult.result_sha256,
        BenchmarkEventResult.details,
        BenchmarkEvent.event_id.label("event_number"),
        BenchmarkEvent.farm,
        BenchmarkEvent.logical_asset_id,
        (BenchmarkEvent.event_label if reveal_truth else literal(None)).label("event_label"),
        (BenchmarkEvent.event_interval_start if reveal_truth else literal(None)).label(
            "event_interval_start"
        ),
        (BenchmarkEvent.event_interval_end if reveal_truth else literal(None)).label(
            "event_interval_end"
        ),
        (BenchmarkEvent.truth_metadata if reveal_truth else literal(None)).label("truth_metadata"),
    ]
    base = (
        select(*columns)
        .join(BenchmarkEvent, BenchmarkEvent.id == BenchmarkEventResult.event_id)
        .where(BenchmarkEventResult.evaluation_run_id == evaluation_run_id)
    )
    total = int(
        await session.scalar(
            select(func.count(BenchmarkEventResult.id)).where(
                BenchmarkEventResult.evaluation_run_id == evaluation_run_id
            )
        )
        or 0
    )
    filtered = base.where(BenchmarkEventResult.status == status) if status else base
    filtered_total = int(
        await session.scalar(select(func.count()).select_from(filtered.order_by(None).subquery()))
        or 0
    )
    records = list(
        (
            await session.execute(
                filtered.order_by(BenchmarkEvent.farm, BenchmarkEvent.event_id)
                .offset(offset)
                .limit(limit)
            )
        ).mappings()
    )
    rows: list[dict[str, Any]] = []
    for record in records:
        details = _safe_document(record["details"])
        truth_metadata = _safe_document(record["truth_metadata"])
        rows.append(
            {
                "result_id": record["result_id"],
                "benchmark_event_id": record["benchmark_event_id"],
                "event_id": record["event_number"],
                "farm": record["farm"],
                "logical_asset_id": record["logical_asset_id"],
                "status": record["status"],
                "scorable": record["scorable"],
                "anomaly_detected": record["anomaly_detected"],
                "scores": {
                    "care": record["care_score"],
                    "coverage": record["coverage_score"],
                    "accuracy": record["accuracy_score"],
                    "reliability": record["reliability_score"],
                    "earliness": record["earliness_score"],
                },
                "failure_code": record["failure_code"],
                "result_sha256": record["result_sha256"],
                "prediction_artifact": {
                    "uri": record["prediction_artifact_uri"],
                    "sha256": record["prediction_artifact_sha256"],
                    "present": bool(
                        record["prediction_artifact_uri"] and record["prediction_artifact_sha256"]
                    ),
                },
                "evaluation_artifact": {
                    "uri": details.get("evaluation_artifact_uri"),
                    "sha256": details.get("evaluation_artifact_sha256"),
                },
                "truth": {
                    "access": "revealed" if reveal_truth else "restricted",
                    "event_label": record["event_label"],
                    "event_interval_start": record["event_interval_start"],
                    "event_interval_end": record["event_interval_end"],
                    "failure_type": details.get("failure_type") if reveal_truth else None,
                    "description": (
                        truth_metadata.get("event_description")
                        or truth_metadata.get("description")
                        or truth_metadata.get("failure_description")
                    )
                    if reveal_truth
                    else None,
                },
            }
        )
    return {
        "data": rows,
        "meta": {
            "evaluation_run_id": evaluation.id,
            "count": len(rows),
            "total": total,
            "filtered_total": filtered_total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(rows) < filtered_total,
            "next_offset": offset + len(rows) if offset + len(rows) < filtered_total else None,
            "truth_revealed": reveal_truth,
            "truth_reveal_allowed": benchmark_truth_allowed(policy),
            "bounds": {"event_result_page_max": BENCHMARK_EVENT_RESULT_PAGE_MAX},
        },
    }


def _prediction_quality_summary(prediction: ModelPrediction) -> dict[str, Any]:
    snapshot = _safe_document(prediction.input_snapshot)
    raw_signals = snapshot.get("signals")
    signals = raw_signals if isinstance(raw_signals, list) else []
    quality_counts = {"good": 0, "uncertain": 0, "bad": 0, "unknown": 0}
    mask_refs: set[str] = set()
    for value in signals[:BENCHMARK_SIGNAL_SUMMARY_MAX]:
        signal = value if isinstance(value, dict) else {}
        quality = signal.get("quality")
        key = str(quality) if quality in {"good", "uncertain", "bad"} else "unknown"
        quality_counts[key] += 1
        refs = signal.get("quality_mask_refs")
        if isinstance(refs, list):
            mask_refs.update(str(ref) for ref in refs if isinstance(ref, str))
    return {
        "signal_count": len(signals),
        "signals_inspected": min(len(signals), BENCHMARK_SIGNAL_SUMMARY_MAX),
        "signals_truncated": len(signals) > BENCHMARK_SIGNAL_SUMMARY_MAX,
        "quality_counts": quality_counts,
        "quality_mask_refs": sorted(mask_refs)[:BENCHMARK_SIGNAL_SUMMARY_MAX],
        "quality_mask_refs_truncated": len(mask_refs) > BENCHMARK_SIGNAL_SUMMARY_MAX,
    }


async def benchmark_diagnosis_page(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    query: str = "",
    status: str | None = None,
    reveal_truth: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if not 1 <= limit <= BENCHMARK_DIAGNOSIS_PAGE_MAX:
        raise ValueError(f"limit must be within 1..{BENCHMARK_DIAGNOSIS_PAGE_MAX}")
    if not benchmark_domains_allowed(policy, "benchmark", "model", "mission"):
        raise PermissionError("benchmark diagnosis access was not granted")
    if reveal_truth and not benchmark_truth_allowed(policy):
        raise PermissionError("benchmark truth access was not granted")
    columns: list[Any] = [
        BenchmarkReplayRun.id.label("replay_run_id"),
        BenchmarkReplayRun.dataset_version_id,
        BenchmarkDatasetVersion.dataset_id,
        BenchmarkDatasetVersion.version.label("dataset_version"),
        BenchmarkReplayRun.event_id.label("benchmark_event_id"),
        BenchmarkReplayRun.source_event_number.label("event_number"),
        BenchmarkReplayRun.farm,
        BenchmarkReplayRun.logical_asset_id,
        BenchmarkReplayRun.online_turbine_id,
        BenchmarkReplayRun.status.label("replay_status"),
        BenchmarkReplayRun.replay_mode,
        BenchmarkReplayRun.replay_anchor_at,
        BenchmarkReplayRun.time_rule_version,
        BenchmarkReplayRun.window_start_row_id,
        BenchmarkReplayRun.window_end_row_id,
        BenchmarkReplayRun.model_id,
        BenchmarkReplayRun.model_version,
        BenchmarkReplayRun.deployment_id,
        BenchmarkReplayRun.threshold_policy_version,
        BenchmarkReplayRun.threshold_policy_sha256,
        BenchmarkReplayRun.created_at,
        BenchmarkReplayRun.started_at,
        BenchmarkReplayRun.finished_at,
        BenchmarkReplayRun.error,
        RegisteredModel.name.label("model_name"),
        RegisteredModel.kind.label("model_kind"),
        RegisteredModel.artifact_uri.label("model_artifact_uri"),
        RegisteredModel.artifact_sha256.label("model_artifact_sha256"),
        ModelDeployment.status.label("deployment_status"),
        ModelDeployment.target_id.label("deployment_target_id"),
        (BenchmarkEvent.event_label if reveal_truth else literal(None)).label("event_label"),
        (BenchmarkEvent.event_interval_start if reveal_truth else literal(None)).label(
            "event_interval_start"
        ),
        (BenchmarkEvent.event_interval_end if reveal_truth else literal(None)).label(
            "event_interval_end"
        ),
        (BenchmarkEvent.truth_metadata if reveal_truth else literal(None)).label("truth_metadata"),
    ]
    base = (
        select(*columns)
        .join(
            BenchmarkDatasetVersion,
            BenchmarkDatasetVersion.id == BenchmarkReplayRun.dataset_version_id,
        )
        .join(BenchmarkEvent, BenchmarkEvent.id == BenchmarkReplayRun.event_id)
        .outerjoin(RegisteredModel, RegisteredModel.id == BenchmarkReplayRun.model_id)
        .outerjoin(ModelDeployment, ModelDeployment.id == BenchmarkReplayRun.deployment_id)
        .where(
            benchmark_dataset_scope_clause(policy),
            turbine_scope_clause(
                policy,
                BenchmarkReplayRun.online_turbine_id,
                entity_columns=(BenchmarkReplayRun.id, BenchmarkReplayRun.event_id),
                data_scopes="benchmark",
            ),
        )
    )
    filters: list[Any] = []
    normalized_query = query.strip().casefold()
    if normalized_query:
        filters.append(
            or_(
                func.lower(BenchmarkReplayRun.id).contains(normalized_query, autoescape=True),
                func.lower(BenchmarkReplayRun.online_turbine_id).contains(
                    normalized_query, autoescape=True
                ),
                func.lower(BenchmarkReplayRun.logical_asset_id).contains(
                    normalized_query, autoescape=True
                ),
                func.lower(BenchmarkReplayRun.model_id).contains(normalized_query, autoescape=True),
            )
        )
    if status:
        filters.append(BenchmarkReplayRun.status == status)
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(base.order_by(None).subquery())
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    filtered = base.where(*filters)
    filtered_total = int(
        await session.scalar(
            select(func.count())
            .select_from(filtered.order_by(None).subquery())
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    replay_rows = list(
        (
            await session.execute(
                filtered.order_by(
                    BenchmarkReplayRun.created_at.desc(), BenchmarkReplayRun.id.desc()
                )
                .offset(offset)
                .limit(limit)
                .execution_options(skip_windops_access_control=True)
            )
        ).mappings()
    )
    replay_ids = [str(row["replay_run_id"]) for row in replay_rows]
    event_ids = [str(row["benchmark_event_id"]) for row in replay_rows]

    prediction_totals: dict[str, int] = {}
    predictions_by_replay: dict[str, list[ModelPrediction]] = defaultdict(list)
    if replay_ids:
        prediction_totals = {
            str(replay_id): int(count)
            for replay_id, count in (
                await session.execute(
                    select(
                        ModelPrediction.benchmark_replay_run_id,
                        func.count(ModelPrediction.id),
                    )
                    .where(ModelPrediction.benchmark_replay_run_id.in_(replay_ids))
                    .group_by(ModelPrediction.benchmark_replay_run_id)
                )
            ).all()
        }
        ranked_prediction_ids = (
            select(
                ModelPrediction.id.label("prediction_id"),
                ModelPrediction.benchmark_replay_run_id.label("replay_run_id"),
                func.row_number()
                .over(
                    partition_by=ModelPrediction.benchmark_replay_run_id,
                    order_by=(ModelPrediction.created_at, ModelPrediction.id),
                )
                .label("position"),
            )
            .where(ModelPrediction.benchmark_replay_run_id.in_(replay_ids))
            .subquery()
        )
        prediction_ids = list(
            (
                await session.scalars(
                    select(ranked_prediction_ids.c.prediction_id)
                    .where(ranked_prediction_ids.c.position <= BENCHMARK_PREDICTIONS_PER_REPLAY_MAX)
                    .order_by(
                        ranked_prediction_ids.c.replay_run_id,
                        ranked_prediction_ids.c.position,
                    )
                )
            ).all()
        )
        if prediction_ids:
            predictions = list(
                (
                    await session.scalars(
                        select(ModelPrediction)
                        .where(ModelPrediction.id.in_(prediction_ids))
                        .order_by(ModelPrediction.created_at, ModelPrediction.id)
                    )
                ).all()
            )
            for prediction in predictions:
                if prediction.benchmark_replay_run_id:
                    predictions_by_replay[prediction.benchmark_replay_run_id].append(prediction)

    loaded_predictions = [
        prediction for predictions in predictions_by_replay.values() for prediction in predictions
    ]
    prediction_ids = [prediction.id for prediction in loaded_predictions]
    alarms_by_prediction: dict[str, Alarm] = {}
    missions_by_alarm: dict[str, Mission] = {}
    sample_evidence_by_prediction: dict[str, dict[str, Any]] = {}
    if prediction_ids:
        alarms = list(
            (
                await session.scalars(
                    select(Alarm).where(Alarm.model_prediction_id.in_(prediction_ids))
                )
            ).all()
        )
        alarms_by_prediction = {
            str(alarm.model_prediction_id): alarm
            for alarm in alarms
            if alarm.model_prediction_id is not None
        }
        alarm_ids = [alarm.id for alarm in alarms]
        if alarm_ids:
            missions = list(
                (
                    await session.scalars(select(Mission).where(Mission.alarm_id.in_(alarm_ids)))
                ).all()
            )
            missions_by_alarm = {mission.alarm_id: mission for mission in missions}
        ranked_samples = (
            select(
                ModelPrediction.id.label("prediction_id"),
                ScadaSample.observed_at,
                ScadaSample.source_sequence,
                ScadaSample.quality,
                ScadaSample.attributes,
                func.row_number()
                .over(
                    partition_by=ModelPrediction.id,
                    order_by=(ScadaSample.variable, ScadaSample.id),
                )
                .label("position"),
            )
            .join(
                ScadaSample,
                (ScadaSample.turbine_id == ModelPrediction.turbine_id)
                & (ScadaSample.source_sequence == ModelPrediction.feature_end_sequence)
                & (ScadaSample.source_id == CARE_REPLAY_SOURCE_ID),
            )
            .where(ModelPrediction.id.in_(prediction_ids))
            .subquery()
        )
        sample_evidence_by_prediction = {
            str(row["prediction_id"]): dict(row)
            for row in (
                await session.execute(select(ranked_samples).where(ranked_samples.c.position == 1))
            ).mappings()
        }

    quality_by_event: dict[str, dict[str, Any]] = {}
    if event_ids:
        ranked_quality = (
            select(
                BenchmarkQualityReport.id.label("quality_report_id"),
                BenchmarkQualityReport.event_id,
                BenchmarkQualityReport.status,
                BenchmarkQualityReport.quality_rule_version,
                BenchmarkQualityReport.feature_set_version,
                BenchmarkQualityReport.artifact_uri,
                BenchmarkQualityReport.artifact_sha256,
                BenchmarkQualityReport.mask_uri,
                BenchmarkQualityReport.mask_sha256,
                BenchmarkQualityReport.summary,
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
            .where(BenchmarkQualityReport.event_id.in_(event_ids))
            .subquery()
        )
        quality_by_event = {
            str(row["event_id"]): dict(row)
            for row in (
                await session.execute(select(ranked_quality).where(ranked_quality.c.position == 1))
            ).mappings()
        }

    rows: list[dict[str, Any]] = []
    for replay in replay_rows:
        replay_id = str(replay["replay_run_id"])
        truth_metadata = _safe_document(replay["truth_metadata"])
        prediction_payloads: list[dict[str, Any]] = []
        first_alert_payload: dict[str, Any] | None = None
        for prediction in predictions_by_replay.get(replay_id, []):
            output = _safe_document(prediction.output)
            sample = sample_evidence_by_prediction.get(prediction.id, {})
            attributes = _safe_document(sample.get("attributes"))
            alarm = alarms_by_prediction.get(prediction.id)
            mission = missions_by_alarm.get(alarm.id) if alarm is not None else None
            link = {
                "alarm_id": alarm.id if alarm is not None else None,
                "alarm_status": alarm.status if alarm is not None else None,
                "alarm_triggered_at": alarm.triggered_at if alarm is not None else None,
                "mission_id": mission.id if mission is not None else None,
                "mission_status": mission.status if mission is not None else None,
                "decision_id": (
                    _safe_document(mission.public_state).get("decision_id")
                    if mission is not None
                    else None
                ),
            }
            if alarm is not None and first_alert_payload is None:
                lead_rows = None
                if reveal_truth and prediction.feature_end_sequence is not None:
                    lead_rows = int(replay["event_interval_start"]) - int(
                        prediction.feature_end_sequence
                    )
                first_alert_payload = {
                    **link,
                    "prediction_id": prediction.id,
                    "synthetic_observed_at": prediction.feature_observed_at,
                    "anonymous_observed_at": attributes.get("anonymous_observed_at"),
                    "source_sequence": prediction.feature_end_sequence,
                    "lead_source_rows": lead_rows,
                    "lead_semantics": "source-row-offset-not-rul",
                }
            prediction_payloads.append(
                {
                    "prediction_id": prediction.id,
                    "status": prediction.status,
                    "error_code": prediction.error_code,
                    "anomaly_score": prediction.anomaly_score,
                    "binary_prediction": prediction.binary_prediction,
                    "component": prediction.component,
                    "model_id": prediction.model_id,
                    "deployment_id": prediction.deployment_id,
                    "evaluation_run_id": prediction.benchmark_evaluation_run_id,
                    "feature_window": {
                        "start": prediction.feature_window_start,
                        "end": prediction.feature_window_end,
                        "start_sequence": prediction.feature_start_sequence,
                        "end_sequence": prediction.feature_end_sequence,
                    },
                    "threshold": {
                        "value": output.get("threshold_value"),
                        "comparison": output.get("threshold_comparison"),
                        "policy_version": prediction.threshold_policy_version,
                        "policy_sha256": prediction.threshold_policy_sha256,
                    },
                    "time_evidence": {
                        "synthetic_observed_at": prediction.feature_observed_at,
                        "observed_at_is_synthetic": bool(
                            attributes.get("observed_at_is_synthetic", True)
                        ),
                        "time_claim": attributes.get("time_claim")
                        or output.get("observed_at_time_claim"),
                        "anonymous_observed_at": attributes.get("anonymous_observed_at"),
                        "source_time_stamp": attributes.get("source_time_stamp"),
                        "source_row_id": attributes.get("source_row_id"),
                    },
                    "quality": _prediction_quality_summary(prediction),
                    "evidence_artifact": {
                        "uri": prediction.evidence_artifact_uri,
                        "sha256": prediction.evidence_artifact_sha256,
                        "present": bool(
                            prediction.evidence_artifact_uri and prediction.evidence_artifact_sha256
                        ),
                    },
                    "links": link,
                    "latency_ms": prediction.latency_ms,
                    "created_at": prediction.created_at,
                }
            )
        quality = quality_by_event.get(str(replay["benchmark_event_id"]))
        quality_summary = _safe_document(quality.get("summary")) if quality else {}
        deployment_stale = bool(replay["deployment_id"] and replay["deployment_status"] != "active")
        rows.append(
            {
                "replay_run_id": replay_id,
                "dataset": {
                    "dataset_version_id": replay["dataset_version_id"],
                    "dataset_id": replay["dataset_id"],
                    "version": replay["dataset_version"],
                },
                "event": {
                    "benchmark_event_id": replay["benchmark_event_id"],
                    "event_id": replay["event_number"],
                    "farm": replay["farm"],
                    "logical_asset_id": replay["logical_asset_id"],
                    "online_turbine_id": replay["online_turbine_id"],
                },
                "replay": {
                    "status": replay["replay_status"],
                    "mode": replay["replay_mode"],
                    "anchor_at": replay["replay_anchor_at"],
                    "time_rule_version": replay["time_rule_version"],
                    "time_semantics": "synthetic-replay-time-not-field-time",
                    "window_start_row_id": replay["window_start_row_id"],
                    "window_end_row_id": replay["window_end_row_id"],
                    "created_at": replay["created_at"],
                    "started_at": replay["started_at"],
                    "finished_at": replay["finished_at"],
                    "error": replay["error"],
                },
                "model": {
                    "model_id": replay["model_id"],
                    "name": replay["model_name"],
                    "version": replay["model_version"],
                    "kind": replay["model_kind"],
                    "artifact_uri": replay["model_artifact_uri"],
                    "artifact_sha256": replay["model_artifact_sha256"],
                    "artifact_present": bool(
                        replay["model_artifact_uri"] and replay["model_artifact_sha256"]
                    ),
                },
                "deployment": {
                    "deployment_id": replay["deployment_id"],
                    "status": replay["deployment_status"],
                    "target_id": replay["deployment_target_id"],
                    "stale": deployment_stale,
                    "threshold_policy_version": replay["threshold_policy_version"],
                    "threshold_policy_sha256": replay["threshold_policy_sha256"],
                },
                "quality_report": {
                    "quality_report_id": quality.get("quality_report_id") if quality else None,
                    "status": quality.get("status") if quality else "missing",
                    "quality_rule_version": quality.get("quality_rule_version")
                    if quality
                    else None,
                    "feature_set_version": quality.get("feature_set_version") if quality else None,
                    "mask_count": int(quality_summary.get("mask_count", 0)),
                    "mask_artifact": {
                        "uri": quality.get("mask_uri") if quality else None,
                        "sha256": quality.get("mask_sha256") if quality else None,
                        "present": bool(
                            quality and quality.get("mask_uri") and quality.get("mask_sha256")
                        ),
                    },
                },
                "predictions": prediction_payloads,
                "predictions_truncated": prediction_totals.get(replay_id, 0)
                > len(prediction_payloads),
                "first_alert": first_alert_payload,
                "truth": {
                    "access": "revealed" if reveal_truth else "restricted",
                    "event_label": replay["event_label"],
                    "event_interval_start": replay["event_interval_start"],
                    "event_interval_end": replay["event_interval_end"],
                    "description": (
                        truth_metadata.get("event_description")
                        or truth_metadata.get("description")
                        or truth_metadata.get("failure_description")
                    )
                    if reveal_truth
                    else None,
                },
            }
        )
    return {
        "data": rows,
        "meta": {
            "count": len(rows),
            "total": total,
            "filtered_total": filtered_total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(rows) < filtered_total,
            "next_offset": offset + len(rows) if offset + len(rows) < filtered_total else None,
            "truth_revealed": reveal_truth,
            "truth_reveal_allowed": benchmark_truth_allowed(policy),
            "source": "postgresql-governed-benchmark-replay",
            "bounds": {
                "diagnosis_page_max": BENCHMARK_DIAGNOSIS_PAGE_MAX,
                "predictions_per_replay_max": BENCHMARK_PREDICTIONS_PER_REPLAY_MAX,
                "signals_inspected_per_prediction_max": BENCHMARK_SIGNAL_SUMMARY_MAX,
            },
        },
    }
