from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# Operational pages are summaries, not ledger exports.  Keep the default page
# useful while ensuring pathological per-parent fan-out cannot turn one bounded
# page into an unbounded response.  Full ledgers remain available from their
# dedicated mission/work-order APIs.
DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT = 1
DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT = 1
MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT = 1
MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT = 1
DIAGNOSIS_RISK_PRIORITY = ("critical", "high", "medium", "low")


def _risk(severity: str, health_score: float) -> str:
    if severity == "critical" or health_score < 60:
        return "critical"
    if severity in {"major", "high"} or health_score < 75:
        return "high"
    if severity in {"minor", "warning"} or health_score < 90:
        return "medium"
    return "low"


def _diagnosis_status(mission_status: str, work_order_status: str | None) -> str:
    if work_order_status is not None:
        if work_order_status in {"completed", "closed"}:
            return "closed"
        if work_order_status in {"in_progress", "in-progress"}:
            return "in-progress"
        if work_order_status in {"scheduled", "ready"}:
            return "scheduled"
    return {
        "under_review": "awaiting-review",
        "under-review": "awaiting-review",
        "revision_requested": "revision-needed",
        "revision-requested": "revision-needed",
        "rejected": "rejected",
        "diagnosed": "analyzed",
        "decision_pending": "analyzed",
        "decision-pending": "analyzed",
        "investigating": "triage",
    }.get(mission_status, "monitoring")


def _public_output_text(output: dict[str, Any]) -> str:
    for key in ("summary", "conclusion", "public_summary", "message"):
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            return value
    diagnosis = output.get("diagnosis")
    if isinstance(diagnosis, dict) and isinstance(diagnosis.get("conclusion"), str):
        return str(diagnosis["conclusion"])
    return "Governed execution completed; inspect the cited evidence and tool ledger."


def _safe_number(value: object, default: float = 0.0) -> float:
    """Read numeric values from JSON ledgers without turning a view into a 500."""

    if isinstance(value, bool):
        return default
    if not isinstance(value, (int, float, str)):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


@dataclass(frozen=True)
class OperationalPage:
    rows: list[dict[str, Any]]
    total: int
    filtered_total: int
    related_data_boundaries: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiagnosisQueryPlan:
    """The exact SQL query shape used by the diagnosis service and its gate."""

    filtered: Any
    filtered_count: Any
    page: Any
    risk_expression: Any
    priority_bucket_predicates: dict[str, tuple[Any, ...]]
    status_expression: Any
    confidence_expression: Any


@dataclass(frozen=True)
class MaintenanceQueryPlan:
    """The exact SQL query shape used by the maintenance-plan service."""

    filtered: Any
    page: Any
    risk_expression: Any
    status_expression: Any
    window_expression: Any
    readiness_expression: Any


def _diagnosis_related_data_boundaries(
    *,
    evidence_truncated_missions: int = 0,
    execution_truncated_missions: int = 0,
) -> dict[str, Any]:
    return {
        "evidence": {
            "strategy": "latest_per_mission",
            "per_mission_limit": DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT,
            "truncated_mission_count": evidence_truncated_missions,
        },
        "agent_executions": {
            "strategy": "latest_per_mission",
            "per_mission_limit": DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT,
            "truncated_mission_count": execution_truncated_missions,
        },
    }


def _maintenance_related_data_boundaries(
    *,
    resource_truncated_groups: int = 0,
    weather_truncated_work_orders: int = 0,
) -> dict[str, Any]:
    return {
        "tasks": {
            "strategy": "aggregate_only",
            "detail": "Only total and completed counts are loaded for page rows.",
        },
        "reservations": {
            "strategy": "latest_per_mission_and_resource_type",
            "per_mission_type_limit": MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT,
            "truncated_group_count": resource_truncated_groups,
        },
        "weather_windows": {
            "strategy": "suitable_first_then_earliest_overlap",
            "per_work_order_limit": MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT,
            "deterministic_order": ["starts_at_asc", "ends_at_asc", "id_asc"],
            "truncated_work_order_count": weather_truncated_work_orders,
        },
    }
