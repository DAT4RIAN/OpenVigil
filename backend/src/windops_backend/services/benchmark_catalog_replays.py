from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.benchmarks.care.replay import CARE_REPLAY_SOURCE_ID
from windops_backend.errors import NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    BenchmarkDatasetVersion,
    BenchmarkReplayRun,
    ScadaSample,
)
from windops_backend.services.benchmark_catalog_policy import (
    BENCHMARK_CURVE_POINT_MAX,
    BENCHMARK_CURVE_POINT_MIN,
    benchmark_dataset_scope_clause,
)


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
