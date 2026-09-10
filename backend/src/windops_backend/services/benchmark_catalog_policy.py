from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import false, func, true

from windops_backend.access_control import data_scope_allowed
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    BenchmarkDatasetVersion,
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
