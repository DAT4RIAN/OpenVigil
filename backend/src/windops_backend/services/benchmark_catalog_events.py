from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import String, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    BenchmarkDatasetVersion,
    BenchmarkEvent,
    BenchmarkEventResult,
    BenchmarkQualityReport,
    BenchmarkReplayRun,
)
from windops_backend.services.benchmark_catalog_policy import (
    BENCHMARK_EVENT_PAGE_MAX,
    BENCHMARK_REPLAYS_PER_EVENT_MAX,
    BENCHMARK_VARIABLES_PER_REPLAY_MAX,
    benchmark_dataset_scope_clause,
    benchmark_truth_allowed,
)


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
