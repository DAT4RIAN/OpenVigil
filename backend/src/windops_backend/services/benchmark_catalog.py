from __future__ import annotations

import windops_backend.services.benchmark_catalog_datasets as _datasets
import windops_backend.services.benchmark_catalog_evaluations as _evaluations
import windops_backend.services.benchmark_catalog_events as _events
import windops_backend.services.benchmark_catalog_policy as _policy
import windops_backend.services.benchmark_catalog_replays as _replays

__all__ = [
    "BENCHMARK_CURVE_POINT_MAX",
    "BENCHMARK_CURVE_POINT_MIN",
    "BENCHMARK_DATASET_PAGE_MAX",
    "BENCHMARK_DEPLOYMENTS_PER_MODEL_MAX",
    "BENCHMARK_DIAGNOSIS_PAGE_MAX",
    "BENCHMARK_EVALUATION_METRICS_MAX",
    "BENCHMARK_EVALUATION_PAGE_MAX",
    "BENCHMARK_EVENT_COUNT_MAX",
    "BENCHMARK_EVENT_PAGE_MAX",
    "BENCHMARK_EVENT_RESULT_PAGE_MAX",
    "BENCHMARK_PREDICTIONS_PER_REPLAY_MAX",
    "BENCHMARK_REPLAYS_PER_EVENT_MAX",
    "BENCHMARK_SIGNAL_SUMMARY_MAX",
    "BENCHMARK_VARIABLES_PER_REPLAY_MAX",
    "benchmark_dataset_page",
    "benchmark_dataset_scope_clause",
    "benchmark_diagnosis_page",
    "benchmark_domains_allowed",
    "benchmark_evaluation_page",
    "benchmark_evaluation_result_page",
    "benchmark_event_page",
    "benchmark_replay_curve",
    "benchmark_truth_allowed",
]

BENCHMARK_DATASET_PAGE_MAX = _policy.BENCHMARK_DATASET_PAGE_MAX
BENCHMARK_EVENT_PAGE_MAX = _policy.BENCHMARK_EVENT_PAGE_MAX
BENCHMARK_EVENT_COUNT_MAX = _policy.BENCHMARK_EVENT_COUNT_MAX
BENCHMARK_CURVE_POINT_MAX = _policy.BENCHMARK_CURVE_POINT_MAX
BENCHMARK_CURVE_POINT_MIN = _policy.BENCHMARK_CURVE_POINT_MIN
BENCHMARK_REPLAYS_PER_EVENT_MAX = _policy.BENCHMARK_REPLAYS_PER_EVENT_MAX
BENCHMARK_VARIABLES_PER_REPLAY_MAX = _policy.BENCHMARK_VARIABLES_PER_REPLAY_MAX
BENCHMARK_EVALUATION_PAGE_MAX = _policy.BENCHMARK_EVALUATION_PAGE_MAX
BENCHMARK_EVALUATION_METRICS_MAX = _policy.BENCHMARK_EVALUATION_METRICS_MAX
BENCHMARK_EVENT_RESULT_PAGE_MAX = _policy.BENCHMARK_EVENT_RESULT_PAGE_MAX
BENCHMARK_DEPLOYMENTS_PER_MODEL_MAX = _policy.BENCHMARK_DEPLOYMENTS_PER_MODEL_MAX
BENCHMARK_DIAGNOSIS_PAGE_MAX = _policy.BENCHMARK_DIAGNOSIS_PAGE_MAX
BENCHMARK_PREDICTIONS_PER_REPLAY_MAX = _policy.BENCHMARK_PREDICTIONS_PER_REPLAY_MAX
BENCHMARK_SIGNAL_SUMMARY_MAX = _policy.BENCHMARK_SIGNAL_SUMMARY_MAX

benchmark_truth_allowed = _policy.benchmark_truth_allowed
benchmark_domains_allowed = _policy.benchmark_domains_allowed
benchmark_dataset_scope_clause = _policy.benchmark_dataset_scope_clause
_status_counts = _policy._status_counts

benchmark_dataset_page = _datasets.benchmark_dataset_page
benchmark_event_page = _events.benchmark_event_page
benchmark_replay_curve = _replays.benchmark_replay_curve

_safe_document = _evaluations._safe_document
_evaluation_gate_reasons = _evaluations._evaluation_gate_reasons
benchmark_evaluation_page = _evaluations.benchmark_evaluation_page
benchmark_evaluation_result_page = _evaluations.benchmark_evaluation_result_page
_prediction_quality_summary = _evaluations._prediction_quality_summary
benchmark_diagnosis_page = _evaluations.benchmark_diagnosis_page
