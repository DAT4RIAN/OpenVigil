from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    Float,
    String,
    and_,
    case,
    cast,
    desc,
    exists,
    func,
    literal,
    literal_column,
    or_,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    AgentExecution,
    Alarm,
    AssetTwinProfile,
    Decision,
    Evidence,
    IngestSource,
    KnowledgeDocument,
    Mission,
    ModelPrediction,
    Resource,
    ResourceReservation,
    ScadaSample,
    Turbine,
    WeatherWindow,
    WindFarm,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.services.benchmark_catalog import (
    BENCHMARK_DATASET_PAGE_MAX,
    benchmark_dataset_page,
)

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


async def _bounded_evidence_by_mission(
    session: AsyncSession,
    mission_ids: list[str],
) -> tuple[dict[str, list[Evidence]], set[str]]:
    ranked = (
        select(
            Evidence.id.label("evidence_id"),
            func.row_number()
            .over(
                partition_by=Evidence.mission_id,
                order_by=(Evidence.created_at.desc(), Evidence.id.desc()),
            )
            .label("fanout_rank"),
        )
        .where(Evidence.mission_id.in_(mission_ids))
        .subquery()
    )
    rows = list(
        (
            await session.scalars(
                select(Evidence)
                .join(ranked, ranked.c.evidence_id == Evidence.id)
                .where(ranked.c.fanout_rank <= DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT + 1)
                .order_by(Evidence.mission_id, Evidence.created_at, Evidence.id)
                # mission_ids come only from the access-controlled Mission
                # hydration above; the FK makes this an authorized child load.
                .execution_options(skip_windops_access_control=True)
            )
        ).all()
    )
    grouped: dict[str, list[Evidence]] = defaultdict(list)
    truncated: set[str] = set()
    for row in rows:
        parent_rows = grouped[row.mission_id]
        if len(parent_rows) < DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT:
            parent_rows.append(row)
        else:
            truncated.add(row.mission_id)
    return grouped, truncated


async def _bounded_executions_by_mission(
    session: AsyncSession,
    mission_ids: list[str],
) -> tuple[dict[str, list[AgentExecution]], set[str]]:
    ranked = (
        select(
            AgentExecution.id.label("execution_id"),
            func.row_number()
            .over(
                partition_by=AgentExecution.mission_id,
                order_by=(AgentExecution.started_at.desc(), AgentExecution.id.desc()),
            )
            .label("fanout_rank"),
        )
        .where(AgentExecution.mission_id.in_(mission_ids))
        .subquery()
    )
    rows = list(
        (
            await session.scalars(
                select(AgentExecution)
                .join(ranked, ranked.c.execution_id == AgentExecution.id)
                .where(ranked.c.fanout_rank <= DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT + 1)
                .order_by(
                    AgentExecution.mission_id,
                    AgentExecution.started_at,
                    AgentExecution.id,
                )
                # mission_ids come only from the access-controlled Mission
                # hydration above; the FK makes this an authorized child load.
                .execution_options(skip_windops_access_control=True)
            )
        ).all()
    )
    grouped: dict[str, list[AgentExecution]] = defaultdict(list)
    truncated: set[str] = set()
    for row in rows:
        parent_rows = grouped[row.mission_id]
        if len(parent_rows) < DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT:
            parent_rows.append(row)
        else:
            truncated.add(row.mission_id)
    return grouped, truncated


async def _task_progress_by_work_order(
    session: AsyncSession,
    work_order_ids: list[str],
) -> dict[str, tuple[int, int]]:
    rows = (
        await session.execute(
            select(
                WorkOrderTask.work_order_id,
                func.count(WorkOrderTask.id),
                func.sum(case((WorkOrderTask.status == "completed", 1), else_=0)),
            )
            .where(WorkOrderTask.work_order_id.in_(work_order_ids))
            .group_by(WorkOrderTask.work_order_id)
            # work_order_ids come only from the access-controlled WorkOrder
            # hydration; the FK makes this an authorized aggregate child load.
            .execution_options(skip_windops_access_control=True)
        )
    ).all()
    return {
        work_order_id: (int(total), int(completed or 0)) for work_order_id, total, completed in rows
    }


async def _bounded_resources_by_mission(
    session: AsyncSession,
    mission_ids: list[str],
) -> tuple[dict[str, dict[str, list[Resource]]], set[tuple[str, str]]]:
    ranked = (
        select(
            ResourceReservation.resource_id.label("resource_id"),
            ResourceReservation.mission_id.label("mission_id"),
            Resource.resource_type.label("resource_type"),
            func.row_number()
            .over(
                partition_by=(
                    ResourceReservation.mission_id,
                    Resource.resource_type,
                ),
                order_by=(
                    ResourceReservation.created_at.desc(),
                    ResourceReservation.id.desc(),
                ),
            )
            .label("fanout_rank"),
        )
        .join(Resource, Resource.id == ResourceReservation.resource_id)
        .where(ResourceReservation.mission_id.in_(mission_ids))
        .subquery()
    )
    rows = (
        await session.execute(
            select(Resource, ranked.c.mission_id, ranked.c.resource_type)
            .join(ranked, ranked.c.resource_id == Resource.id)
            .where(ranked.c.fanout_rank <= MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT + 1)
            .order_by(
                ranked.c.mission_id,
                ranked.c.resource_type,
                Resource.updated_at.desc(),
                Resource.id.desc(),
            )
            # mission_ids come only from access-controlled WorkOrders. Both
            # reservation and resource rows are constrained by that FK-derived
            # page set, so recompiling the global policy is redundant here.
            .execution_options(skip_windops_access_control=True)
        )
    ).all()
    grouped: dict[str, dict[str, list[Resource]]] = defaultdict(lambda: defaultdict(list))
    truncated: set[tuple[str, str]] = set()
    for resource, mission_id, resource_type in rows:
        parent_rows = grouped[mission_id][resource_type]
        if len(parent_rows) < MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT:
            parent_rows.append(resource)
        else:
            truncated.add((mission_id, resource_type))
    return grouped, truncated


def _diagnosis_risk_expression(
    alarm_severity: Any = Alarm.severity,
    health_score: Any = Turbine.health_score,
) -> Any:
    return case(
        (or_(alarm_severity == "critical", health_score < 60), "critical"),
        (or_(alarm_severity.in_(("major", "high")), health_score < 75), "high"),
        (
            or_(alarm_severity.in_(("minor", "warning")), health_score < 90),
            "medium",
        ),
        else_="low",
    )


def _diagnosis_status_expression(work_order_status: Any = WorkOrder.status) -> Any:
    return case(
        (work_order_status.in_(("completed", "closed")), "closed"),
        (work_order_status.in_(("in_progress", "in-progress")), "in-progress"),
        (work_order_status.in_(("scheduled", "ready")), "scheduled"),
        (Mission.status.in_(("under_review", "under-review")), "awaiting-review"),
        (
            Mission.status.in_(("revision_requested", "revision-requested")),
            "revision-needed",
        ),
        (Mission.status == "rejected", "rejected"),
        (Mission.status.in_(("diagnosed", "decision_pending", "decision-pending")), "analyzed"),
        (Mission.status == "investigating", "triage"),
        else_="monitoring",
    )


def _diagnosis_risk_weight_expression(
    alarm_severity: Any = Alarm.severity,
    health_score: Any = Turbine.health_score,
) -> Any:
    """Numeric priority without repeatedly nesting the public risk CASE."""

    return case(
        (or_(alarm_severity == "critical", health_score < 60), 4),
        (or_(alarm_severity.in_(("major", "high")), health_score < 75), 3),
        (
            or_(alarm_severity.in_(("minor", "warning")), health_score < 90),
            2,
        ),
        else_=1,
    )


def _diagnosis_priority_bucket_predicates(
    alarm_severity: Any,
    health_score: Any,
) -> dict[str, tuple[Any, ...]]:
    """Return disjoint predicates for the public diagnosis risk buckets.

    Splitting each cross-table OR into mutually exclusive branches lets
    PostgreSQL limit each ordered branch before merging at most ``2 * page``
    candidates.  Literal fixed-vocabulary values also avoid a generic prepared
    plan that cannot estimate the alarm-severity selectivity.
    """

    critical: Any = literal_column("'critical'")
    major: Any = literal_column("'major'")
    high: Any = literal_column("'high'")
    minor: Any = literal_column("'minor'")
    warning: Any = literal_column("'warning'")
    critical_or_higher = (critical,)
    high_or_higher = (critical, major, high)
    medium_or_higher = (critical, major, high, minor, warning)
    return {
        "critical": (
            alarm_severity == critical,
            and_(alarm_severity.not_in(critical_or_higher), health_score < 60),
        ),
        "high": (
            and_(alarm_severity.in_((major, high)), health_score >= 60),
            and_(
                alarm_severity.not_in(high_or_higher),
                health_score >= 60,
                health_score < 75,
            ),
        ),
        "medium": (
            and_(alarm_severity.in_((minor, warning)), health_score >= 75),
            and_(
                alarm_severity.not_in(medium_or_higher),
                health_score >= 75,
                health_score < 90,
            ),
        ),
        "low": (and_(alarm_severity.not_in(medium_or_higher), health_score >= 90),),
    }


def build_diagnosis_query(
    *,
    query: str = "",
    tenant_id: str | None = None,
    wind_farm_id: str | None = None,
    turbine_id: str | None = None,
    status_filter: str | None = None,
    risk: str | None = None,
    sort_mode: str = "priority-desc",
    offset: int = 0,
    limit: int = 64,
) -> DiagnosisQueryPlan:
    """Build the production diagnosis page query used by the API service.

    Keeping this builder public lets the PostgreSQL performance gate EXPLAIN
    the same joins, computed predicates, ordering, filters, and pagination as
    the real request instead of a hand-written substitute query.
    """

    # Mission is the authoritative scoped row for this page.  The related
    # tables are deliberately Core aliases: applying the same correlated
    # asset-scope loader criterion independently to Mission, Alarm, Turbine,
    # WorkOrder, and WindFarm makes one bounded page perform several redundant
    # scope probes. Mission retains the ORM loader criterion; related rows are
    # joined only through its authoritative foreign keys.
    alarm_table = Alarm.__table__.alias("diagnosis_alarm")
    turbine_table = Turbine.__table__.alias("diagnosis_turbine")
    work_order_table = WorkOrder.__table__.alias("diagnosis_work_order")
    wind_farm_table = WindFarm.__table__.alias("diagnosis_wind_farm")
    risk_expression = _diagnosis_risk_expression(
        alarm_table.c.severity,
        turbine_table.c.health_score,
    )
    priority_bucket_predicates = _diagnosis_priority_bucket_predicates(
        alarm_table.c.severity,
        turbine_table.c.health_score,
    )
    status_expression = _diagnosis_status_expression(work_order_table.c.status)
    confidence_expression = func.coalesce(
        cast(Mission.public_state["diagnosis"]["confidence"].as_string(), Float),
        0.0,
    )
    base_statement = (
        select(Mission.id)
        .join(alarm_table, alarm_table.c.id == Mission.alarm_id)
        .join(turbine_table, turbine_table.c.id == Mission.turbine_id)
    )
    if status_filter:
        base_statement = base_statement.outerjoin(
            work_order_table,
            work_order_table.c.mission_id == Mission.id,
        )
    if tenant_id is not None or wind_farm_id is not None:
        base_statement = base_statement.join(
            wind_farm_table,
            wind_farm_table.c.id == turbine_table.c.wind_farm_id,
        )
    filters: list[Any] = []
    if tenant_id:
        filters.append(wind_farm_table.c.tenant_id == tenant_id)
    if wind_farm_id:
        filters.append(turbine_table.c.wind_farm_id == wind_farm_id)
    if turbine_id:
        filters.append(Mission.turbine_id == turbine_id)
    if status_filter:
        filters.append(status_expression == status_filter)
    if risk:
        filters.append(risk_expression == risk)
    normalized_query = query.strip().lower()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        filters.append(
            or_(
                func.lower(literal("DX-") + Mission.id).like(pattern),
                func.lower(Mission.id).like(pattern),
                func.lower(Mission.turbine_id).like(pattern),
                func.lower(Mission.title).like(pattern),
                func.lower(alarm_table.c.title).like(pattern),
                func.lower(cast(Mission.public_state, String)).like(pattern),
            )
        )
    filtered_statement = base_statement.where(*filters)
    filtered_count_statement = select(func.count(Mission.id)).select_from(Mission)
    if risk or normalized_query:
        filtered_count_statement = filtered_count_statement.join(
            alarm_table,
            alarm_table.c.id == Mission.alarm_id,
        )
    if risk or tenant_id is not None or wind_farm_id is not None:
        filtered_count_statement = filtered_count_statement.join(
            turbine_table,
            turbine_table.c.id == Mission.turbine_id,
        )
    if status_filter:
        filtered_count_statement = filtered_count_statement.outerjoin(
            work_order_table,
            work_order_table.c.mission_id == Mission.id,
        )
    if tenant_id is not None or wind_farm_id is not None:
        filtered_count_statement = filtered_count_statement.join(
            wind_farm_table,
            wind_farm_table.c.id == turbine_table.c.wind_farm_id,
        )
    filtered_count_statement = filtered_count_statement.where(*filters)
    risk_weight = _diagnosis_risk_weight_expression(
        alarm_table.c.severity,
        turbine_table.c.health_score,
    )
    if sort_mode == "updated-desc":
        ordering: tuple[Any, ...] = (Mission.updated_at.desc(), Mission.id.desc())
    elif sort_mode == "confidence-desc":
        ordering = (confidence_expression.desc(), Mission.updated_at.desc(), Mission.id.desc())
    elif sort_mode == "turbine-asc":
        ordering = (Mission.turbine_id.asc(), Mission.id.asc())
    else:
        ordering = (
            risk_weight.desc(),
            Mission.updated_at.desc(),
            Mission.id.desc(),
        )
    return DiagnosisQueryPlan(
        filtered=filtered_statement,
        filtered_count=filtered_count_statement,
        page=filtered_statement.order_by(*ordering).offset(offset).limit(limit),
        risk_expression=risk_expression,
        priority_bucket_predicates=priority_bucket_predicates,
        status_expression=status_expression,
        confidence_expression=confidence_expression,
    )


def build_diagnosis_priority_bucket_query(
    query_plan: DiagnosisQueryPlan,
    *,
    risk_bucket: str,
    fetch_limit: int,
) -> Any:
    """Build one bounded priority bucket from the shared filtered query.

    A global computed-risk sort must evaluate and sort every matching Mission.
    Each mutually exclusive branch keeps only its top candidates; the final
    merge therefore sorts at most twice the requested page while preserving
    the exact risk and updated-at ordering.
    """

    if risk_bucket not in DIAGNOSIS_RISK_PRIORITY:
        raise ValueError("unsupported diagnosis risk bucket")
    if fetch_limit < 1:
        raise ValueError("diagnosis priority fetch limit must be positive")
    branch_statements = []
    for index, predicate in enumerate(query_plan.priority_bucket_predicates[risk_bucket]):
        limited_branch = (
            query_plan.filtered.add_columns(Mission.updated_at.label("priority_updated_at"))
            .where(predicate)
            .order_by(Mission.updated_at.desc(), Mission.id.desc())
            .limit(fetch_limit)
            .subquery(f"diagnosis_priority_branch_{index}")
        )
        branch_statements.append(select(limited_branch.c.id, limited_branch.c.priority_updated_at))
    candidates = union_all(*branch_statements).subquery("diagnosis_priority_candidates")
    return (
        select(candidates.c.id)
        .order_by(candidates.c.priority_updated_at.desc(), candidates.c.id.desc())
        .limit(fetch_limit)
    )


async def _diagnosis_priority_page_ids(
    session: AsyncSession,
    query_plan: DiagnosisQueryPlan,
    *,
    offset: int,
    limit: int,
    requested_risk: str | None,
) -> list[str]:
    buckets = (
        (requested_risk,) if requested_risk in DIAGNOSIS_RISK_PRIORITY else DIAGNOSIS_RISK_PRIORITY
    )
    remaining_offset = offset
    page_ids: list[str] = []
    for risk_bucket in buckets:
        needed = limit - len(page_ids)
        candidates = list(
            (
                await session.scalars(
                    build_diagnosis_priority_bucket_query(
                        query_plan,
                        risk_bucket=risk_bucket,
                        fetch_limit=remaining_offset + needed,
                    )
                )
            ).all()
        )
        if len(candidates) <= remaining_offset:
            remaining_offset -= len(candidates)
            continue
        page_ids.extend(candidates[remaining_offset : remaining_offset + needed])
        remaining_offset = 0
        if len(page_ids) == limit:
            break
    return page_ids


async def diagnosis_rows(
    session: AsyncSession,
    *,
    query: str = "",
    tenant_id: str | None = None,
    wind_farm_id: str | None = None,
    turbine_id: str | None = None,
    status_filter: str | None = None,
    risk: str | None = None,
    sort_mode: str = "priority-desc",
    offset: int = 0,
    limit: int = 64,
) -> OperationalPage:
    query_plan = build_diagnosis_query(
        query=query,
        tenant_id=tenant_id,
        wind_farm_id=wind_farm_id,
        turbine_id=turbine_id,
        status_filter=status_filter,
        risk=risk,
        sort_mode=sort_mode,
        offset=offset,
        limit=limit,
    )
    total = int(await session.scalar(select(func.count(Mission.id))) or 0)
    filtered_total = int(await session.scalar(query_plan.filtered_count) or 0)
    if sort_mode == "priority-desc":
        mission_ids = await _diagnosis_priority_page_ids(
            session,
            query_plan,
            offset=offset,
            limit=limit,
            requested_risk=risk,
        )
    else:
        mission_ids = list((await session.scalars(query_plan.page)).all())
    if not mission_ids:
        return OperationalPage(
            rows=[],
            total=total,
            filtered_total=filtered_total,
            related_data_boundaries=_diagnosis_related_data_boundaries(),
        )
    mission_order = {mission_id: index for index, mission_id in enumerate(mission_ids)}
    page_turbine_table = Turbine.__table__.alias("diagnosis_page_turbine")
    page_alarm_table = Alarm.__table__.alias("diagnosis_page_alarm")
    page_decision_table = Decision.__table__.alias("diagnosis_page_decision")
    page_work_order_table = WorkOrder.__table__.alias("diagnosis_page_work_order")
    # Mission remains the authoritative scoped ORM entity. Its one-to-one
    # turbine/alarm/decision/work-order data can be hydrated in the same query
    # through Core aliases without repeating four access-policy compilations.
    mission_records = list(
        (
            await session.execute(
                select(
                    Mission,
                    page_turbine_table.c.id.label("page_turbine_id"),
                    page_turbine_table.c.status.label("page_turbine_status"),
                    page_turbine_table.c.health_score.label("page_health_score"),
                    page_alarm_table.c.id.label("page_alarm_id"),
                    page_alarm_table.c.severity.label("page_alarm_severity"),
                    page_alarm_table.c.status.label("page_alarm_status"),
                    page_alarm_table.c.evidence.label("page_alarm_evidence"),
                    page_alarm_table.c.subsystem.label("page_alarm_subsystem"),
                    page_alarm_table.c.title.label("page_alarm_title"),
                    page_alarm_table.c.code.label("page_alarm_code"),
                    page_alarm_table.c.triggered_at.label("page_alarm_triggered_at"),
                    page_decision_table.c.status.label("page_decision_status"),
                    page_work_order_table.c.status.label("page_work_order_status"),
                )
                .join(
                    page_turbine_table,
                    page_turbine_table.c.id == Mission.turbine_id,
                )
                .join(
                    page_alarm_table,
                    page_alarm_table.c.id == Mission.alarm_id,
                )
                .outerjoin(
                    page_decision_table,
                    page_decision_table.c.mission_id == Mission.id,
                )
                .outerjoin(
                    page_work_order_table,
                    page_work_order_table.c.mission_id == Mission.id,
                )
                .where(Mission.id.in_(mission_ids))
            )
        ).all()
    )
    mission_records.sort(key=lambda record: mission_order[record[0].id])
    if not mission_records:
        return OperationalPage(
            rows=[],
            total=total,
            filtered_total=filtered_total,
            related_data_boundaries=_diagnosis_related_data_boundaries(),
        )
    loaded_mission_ids = [record[0].id for record in mission_records]
    evidence_by_mission, evidence_truncated = await _bounded_evidence_by_mission(
        session, loaded_mission_ids
    )
    executions_by_mission, execution_truncated = await _bounded_executions_by_mission(
        session, loaded_mission_ids
    )
    rows: list[dict[str, Any]] = []
    for (
        mission,
        page_turbine_id,
        page_turbine_status,
        page_health_score,
        page_alarm_id,
        page_alarm_severity,
        page_alarm_status,
        page_alarm_evidence,
        page_alarm_subsystem,
        page_alarm_title,
        page_alarm_code,
        page_alarm_triggered_at,
        page_decision_status,
        page_work_order_status,
    ) in mission_records:
        diagnosis = mission.public_state.get("diagnosis", {})
        if not isinstance(diagnosis, dict):
            diagnosis = {}
        if not isinstance(page_alarm_evidence, dict):
            page_alarm_evidence = {}
        evidences = evidence_by_mission.get(mission.id, [])
        confidence = _safe_number(diagnosis.get("confidence"))
        health_score = _safe_number(page_health_score)
        evidence_ids = [row.id for row in evidences]
        component = str(diagnosis.get("component") or page_alarm_subsystem)
        failure_mode = str(diagnosis.get("failure_mode") or page_alarm_title)
        conclusion = str(diagnosis.get("conclusion") or page_alarm_title)
        alarm_attributes = page_alarm_evidence.get("attributes", {})
        if not isinstance(alarm_attributes, dict):
            alarm_attributes = {}
        alarm_value = _safe_number(page_alarm_evidence.get("value"))
        anomaly_score = _safe_number(alarm_attributes.get("anomaly_score"))
        signals = [
            {
                "id": f"{page_alarm_id}:primary",
                "label": str(page_alarm_evidence.get("variable") or page_alarm_code),
                "value": alarm_value,
                "baseline": alarm_value,
                "unit": str(page_alarm_evidence.get("unit") or ""),
                "deltaPercent": 0,
                "abnormal": True,
            }
        ]
        citations = [
            {
                "id": evidence.id,
                "title": evidence.source_key,
                "sourceLabel": evidence.evidence_type,
                "sourceType": evidence.evidence_type,
                "observedAt": evidence.created_at,
                "summary": evidence.summary,
                "href": evidence.citation_uri or f"/missions/{mission.id}#evidence",
                "deepLink": True,
            }
            for evidence in evidences
        ]
        collaboration = [
            {
                "id": execution.id,
                "sequence": index,
                "agentId": execution.agent_role,
                "agentName": execution.agent_role.replace("_", " ").title(),
                "role": execution.node,
                "status": "complete" if execution.status == "succeeded" else "monitoring",
                "publicOutput": _public_output_text(execution.public_output),
                "evaluation": execution.evaluation_result,
                "degradationPolicy": execution.degradation_policy,
                "evidenceIds": evidence_ids,
                "toolResults": [
                    {
                        "tool": str(call.get("tool", call.get("name", "governed_tool"))),
                        "result": str(call.get("status", "recorded")),
                    }
                    for call in execution.tool_calls
                    if isinstance(call, dict)
                ],
                "completedAt": execution.completed_at,
            }
            for index, execution in enumerate(executions_by_mission.get(mission.id, []), start=1)
        ]
        gate_state = "review-required"
        if page_work_order_status in {"completed", "closed"}:
            gate_state = "verified"
        elif page_work_order_status in {"in_progress", "in-progress"}:
            gate_state = "active"
        elif page_decision_status == "approved":
            gate_state = "authorized"
        elif page_decision_status is None:
            gate_state = "locked"
        rows.append(
            {
                "id": f"DX-{mission.id}",
                "turbineId": page_turbine_id,
                "turbineStatus": page_turbine_status,
                "healthScore": health_score,
                "risk": _risk(str(page_alarm_severity), health_score),
                "status": _diagnosis_status(mission.status, page_work_order_status),
                "headline": conclusion,
                "overallConfidencePercent": round(confidence * 100),
                "missionId": mission.id,
                "activeAlarmCount": 0 if page_alarm_status == "resolved" else 1,
                "updatedAt": mission.updated_at,
                "anomaly": {
                    "source": "alarm-correlation",
                    "detectedAt": page_alarm_triggered_at,
                    "anomalyScore": anomaly_score,
                    "threshold": _safe_number(alarm_attributes.get("threshold")),
                    "summary": page_alarm_title,
                    "signals": signals,
                },
                "candidates": [
                    {
                        "id": f"{mission.id}:candidate:1",
                        "faultMode": failure_mode,
                        "subsystem": component,
                        "probabilityPercent": round(confidence * 100),
                        "confidencePercent": round(confidence * 100),
                        "supportingEvidenceIds": evidence_ids,
                        "supportingSummary": [row.summary for row in evidences],
                        "counterEvidence": [],
                        "recommendedNextStep": (
                            "Complete human review before any controlled maintenance action."
                        ),
                    }
                ],
                "citations": citations,
                "collaboration": collaboration,
                "gate": {
                    "state": gate_state,
                    "humanReviewRequired": gate_state in {"locked", "review-required"},
                    "title": "Governed human approval gate",
                    "explanation": (
                        "Execution remains controlled by the persisted decision and approval state."
                    ),
                    "allowedActions": ["review evidence", "record approval"],
                    "blockedActions": (
                        ["create work order", "dispatch field work"]
                        if gate_state in {"locked", "review-required"}
                        else []
                    ),
                    "decisionStatus": page_decision_status,
                    "workOrderStatus": page_work_order_status,
                },
            }
        )
    return OperationalPage(
        rows=rows,
        total=total,
        filtered_total=filtered_total,
        related_data_boundaries=_diagnosis_related_data_boundaries(
            evidence_truncated_missions=len(evidence_truncated),
            execution_truncated_missions=len(execution_truncated),
        ),
    )


def _resource_ref(resource: Resource | None, *, missing_label: str) -> dict[str, Any]:
    if resource is None:
        return {
            "id": f"missing:{missing_label}",
            "label": missing_label,
            "state": "untracked",
            "detail": "No governed reservation exists for this resource type.",
        }
    return {
        "id": resource.id,
        "label": resource.name,
        "state": "reserved" if resource.status == "reserved" else resource.status,
        "detail": f"Quantity {resource.quantity}; source is the PostgreSQL resource ledger.",
    }


def _maintenance_risk_expression() -> Any:
    return case(
        (
            or_(WorkOrder.priority == "critical", Turbine.health_score < 60),
            "critical",
        ),
        (
            or_(WorkOrder.priority.in_(("major", "high")), Turbine.health_score < 75),
            "high",
        ),
        (
            or_(WorkOrder.priority.in_(("minor", "warning")), Turbine.health_score < 90),
            "medium",
        ),
        else_="low",
    )


def _resource_type_exists(resource_type: str) -> Any:
    return exists(
        select(ResourceReservation.id)
        .join(Resource, Resource.id == ResourceReservation.resource_id)
        .where(
            ResourceReservation.mission_id == WorkOrder.mission_id,
            Resource.resource_type == resource_type,
        )
    )


def _maintenance_planned_end_expression(dialect_name: str) -> Any:
    if dialect_name == "sqlite":
        return func.datetime(
            WorkOrder.planned_start,
            func.printf("+%f hours", WorkOrder.estimated_duration_hours),
        )
    return WorkOrder.planned_start + func.make_interval(
        0,
        0,
        0,
        0,
        0,
        0,
        WorkOrder.estimated_duration_hours * 3600,
    )


def build_maintenance_weather_query(
    *,
    work_order_ids: list[str],
    dialect_name: str = "postgresql",
) -> Any:
    """Return at most one governed weather row for each authorized work order.

    A correlated Top-1 suitable lookup preserves the business preference without
    materializing all overlapping windows. The second Top-1 lookup is evaluated
    only as a fallback. The outer EXISTS discloses when additional candidates
    were deliberately omitted while keeping the database result page-bounded.
    """

    planned_end_expression = _maintenance_planned_end_expression(dialect_name)

    def candidate_id(*, suitable_only: bool) -> Any:
        statement = select(WeatherWindow.id).where(
            WeatherWindow.wind_farm_id == Turbine.wind_farm_id,
            WeatherWindow.starts_at <= planned_end_expression,
            WeatherWindow.ends_at >= WorkOrder.planned_start,
        )
        if suitable_only:
            statement = statement.where(WeatherWindow.suitable.is_(True))
        return (
            statement.order_by(
                WeatherWindow.starts_at.asc(),
                WeatherWindow.ends_at.asc(),
                WeatherWindow.id.asc(),
            )
            .limit(MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT)
            .correlate(WorkOrder, Turbine)
            .scalar_subquery()
        )

    selected = (
        select(
            WorkOrder.id.label("work_order_id"),
            Turbine.wind_farm_id.label("wind_farm_id"),
            WorkOrder.planned_start.label("planned_start"),
            planned_end_expression.label("planned_end"),
            func.coalesce(
                candidate_id(suitable_only=True),
                candidate_id(suitable_only=False),
            ).label("weather_window_id"),
        )
        .select_from(WorkOrder)
        .join(Turbine, Turbine.id == WorkOrder.turbine_id)
        .where(
            WorkOrder.id.in_(work_order_ids),
            WorkOrder.planned_start.is_not(None),
        )
        .cte("selected_maintenance_weather")
    )
    additional_candidate = aliased(WeatherWindow, name="additional_weather_candidate")
    has_additional_candidate = exists(
        select(additional_candidate.id).where(
            additional_candidate.wind_farm_id == selected.c.wind_farm_id,
            additional_candidate.starts_at <= selected.c.planned_end,
            additional_candidate.ends_at >= selected.c.planned_start,
            additional_candidate.id != selected.c.weather_window_id,
        )
    )
    return (
        select(
            selected.c.work_order_id,
            WeatherWindow,
            has_additional_candidate.label("weather_candidates_truncated"),
        )
        .select_from(selected)
        .outerjoin(WeatherWindow, WeatherWindow.id == selected.c.weather_window_id)
        .order_by(selected.c.work_order_id)
        # Work-order ids come only from the access-controlled page query. The
        # turbine and farm joins above keep the child lookup inside that scope.
        .execution_options(skip_windops_access_control=True)
    )


async def _bounded_weather_by_work_order(
    session: AsyncSession,
    work_order_ids: list[str],
    *,
    dialect_name: str,
) -> tuple[dict[str, WeatherWindow], set[str]]:
    rows = (
        await session.execute(
            build_maintenance_weather_query(
                work_order_ids=work_order_ids,
                dialect_name=dialect_name,
            )
        )
    ).all()
    selected: dict[str, WeatherWindow] = {}
    truncated: set[str] = set()
    for work_order_id, weather_window, candidates_truncated in rows:
        if weather_window is not None:
            selected[work_order_id] = weather_window
        if candidates_truncated:
            truncated.add(work_order_id)
    return selected, truncated


def build_maintenance_query(
    *,
    dialect_name: str = "postgresql",
    query: str = "",
    tenant_id: str | None = None,
    wind_farm_id: str | None = None,
    turbine_id: str | None = None,
    status_filter: str | None = None,
    risk: str | None = None,
    team: str | None = None,
    window: str | None = None,
    sort_mode: str = "start-asc",
    offset: int = 0,
    limit: int = 50,
) -> MaintenanceQueryPlan:
    """Build the production maintenance page query for EXPLAIN and execution."""

    planned_end_expression = _maintenance_planned_end_expression(dialect_name)
    resource_presence = {
        resource_type: _resource_type_exists(resource_type)
        for resource_type in ("crew", "vessel", "spare_part", "tool")
    }
    weather_any = exists(
        select(WeatherWindow.id).where(
            WeatherWindow.wind_farm_id == Turbine.wind_farm_id,
            WeatherWindow.starts_at <= planned_end_expression,
            WeatherWindow.ends_at >= WorkOrder.planned_start,
        )
    )
    weather_suitable = exists(
        select(WeatherWindow.id).where(
            WeatherWindow.wind_farm_id == Turbine.wind_farm_id,
            WeatherWindow.starts_at <= planned_end_expression,
            WeatherWindow.ends_at >= WorkOrder.planned_start,
            WeatherWindow.suitable.is_(True),
        )
    )
    window_expression = case(
        (weather_suitable, "suitable"),
        (weather_any, "unsafe"),
        else_="unmatched",
    )
    conflict_count: Any = case((weather_suitable, 0), else_=1)
    for present in resource_presence.values():
        conflict_count = conflict_count + case((present, 0), else_=1)
    readiness_expression = 100 - 20 * conflict_count
    status_expression = case(
        (
            WorkOrder.status.in_(
                ("completed", "closed"),
            ),
            "completed",
        ),
        (
            WorkOrder.status.in_(
                ("in_progress", "in-progress"),
            ),
            "in-progress",
        ),
        (conflict_count > 0, "at-risk"),
        else_="ready",
    )
    risk_expression = _maintenance_risk_expression()
    base_statement = (
        select(WorkOrder.id)
        .join(Turbine, Turbine.id == WorkOrder.turbine_id)
        .where(WorkOrder.planned_start.is_not(None))
    )
    if tenant_id is not None or wind_farm_id is not None:
        base_statement = base_statement.join(WindFarm, WindFarm.id == Turbine.wind_farm_id)
    filters: list[Any] = []
    if tenant_id:
        filters.append(WindFarm.tenant_id == tenant_id)
    if wind_farm_id:
        filters.append(Turbine.wind_farm_id == wind_farm_id)
    if turbine_id:
        filters.append(WorkOrder.turbine_id == turbine_id)
    if status_filter:
        filters.append(status_expression == status_filter)
    if risk:
        filters.append(risk_expression == risk)
    if team:
        filters.append(func.lower(WorkOrder.assigned_team) == team.lower())
    if window:
        filters.append(window_expression == window)
    normalized_query = query.strip().lower()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        filters.append(
            or_(
                func.lower(literal("PLAN-") + WorkOrder.id).like(pattern),
                func.lower(WorkOrder.id).like(pattern),
                func.lower(WorkOrder.turbine_id).like(pattern),
                func.lower(WorkOrder.title).like(pattern),
                func.lower(WorkOrder.assigned_team).like(pattern),
            )
        )
    filtered_statement = base_statement.where(*filters)
    risk_weight = case(
        (risk_expression == "critical", 4),
        (risk_expression == "high", 3),
        (risk_expression == "medium", 2),
        else_=1,
    )
    if sort_mode == "risk-desc":
        ordering: tuple[Any, ...] = (
            risk_weight.desc(),
            WorkOrder.planned_start.asc(),
            WorkOrder.id.asc(),
        )
    elif sort_mode == "readiness-desc":
        ordering = (
            readiness_expression.desc(),
            WorkOrder.planned_start.asc(),
            WorkOrder.id.asc(),
        )
    elif sort_mode == "deadline-asc":
        ordering = (WorkOrder.deadline.asc().nulls_last(), WorkOrder.id.asc())
    else:
        ordering = (WorkOrder.planned_start.asc(), WorkOrder.id.asc())
    return MaintenanceQueryPlan(
        filtered=filtered_statement,
        page=filtered_statement.order_by(*ordering).offset(offset).limit(limit),
        risk_expression=risk_expression,
        status_expression=status_expression,
        window_expression=window_expression,
        readiness_expression=readiness_expression,
    )


async def maintenance_plan_rows(
    session: AsyncSession,
    *,
    query: str = "",
    tenant_id: str | None = None,
    wind_farm_id: str | None = None,
    turbine_id: str | None = None,
    status_filter: str | None = None,
    risk: str | None = None,
    team: str | None = None,
    window: str | None = None,
    sort_mode: str = "start-asc",
    offset: int = 0,
    limit: int = 50,
) -> OperationalPage:
    dialect_name = session.bind.dialect.name if session.bind is not None else "postgresql"
    query_plan = build_maintenance_query(
        dialect_name=dialect_name,
        query=query,
        tenant_id=tenant_id,
        wind_farm_id=wind_farm_id,
        turbine_id=turbine_id,
        status_filter=status_filter,
        risk=risk,
        team=team,
        window=window,
        sort_mode=sort_mode,
        offset=offset,
        limit=limit,
    )
    total = int(
        await session.scalar(
            select(func.count(WorkOrder.id)).where(WorkOrder.planned_start.is_not(None))
        )
        or 0
    )
    filtered_total = int(
        await session.scalar(
            select(func.count()).select_from(query_plan.filtered.order_by(None).subquery())
        )
        or 0
    )
    work_order_ids = list((await session.scalars(query_plan.page)).all())
    if not work_order_ids:
        return OperationalPage(
            rows=[],
            total=total,
            filtered_total=filtered_total,
            related_data_boundaries=_maintenance_related_data_boundaries(),
        )
    work_order_order = {work_order_id: index for index, work_order_id in enumerate(work_order_ids)}
    work_orders = list(
        (await session.scalars(select(WorkOrder).where(WorkOrder.id.in_(work_order_ids)))).all()
    )
    work_orders.sort(key=lambda work_order: work_order_order[work_order.id])
    if not work_orders:
        return OperationalPage(
            rows=[],
            total=total,
            filtered_total=filtered_total,
            related_data_boundaries=_maintenance_related_data_boundaries(),
        )
    mission_ids = [row.mission_id for row in work_orders]
    turbine_ids = list({row.turbine_id for row in work_orders})
    task_progress = await _task_progress_by_work_order(session, work_order_ids)
    resources_by_mission, resource_truncated = await _bounded_resources_by_mission(
        session, mission_ids
    )
    weather_by_work_order, weather_truncated = await _bounded_weather_by_work_order(
        session,
        work_order_ids,
        dialect_name=dialect_name,
    )
    turbines = {
        row.id: row
        for row in (
            await session.scalars(
                select(Turbine)
                .where(Turbine.id.in_(turbine_ids))
                # turbine_ids are FK values from authorized WorkOrders.
                .execution_options(skip_windops_access_control=True)
            )
        ).all()
    }
    result: list[dict[str, Any]] = []
    for work_order in work_orders:
        turbine = turbines.get(work_order.turbine_id)
        if turbine is None or work_order.planned_start is None:
            continue
        ends_at = work_order.planned_start + timedelta(hours=work_order.estimated_duration_hours)
        match = weather_by_work_order.get(work_order.id)
        by_type = resources_by_mission.get(work_order.mission_id, {})
        task_total, task_completed = task_progress.get(work_order.id, (0, 0))
        progress = round(task_completed / task_total * 100) if task_total else 0
        conflicts: list[dict[str, Any]] = []
        if match is None:
            conflicts.append(
                {
                    "code": "WEATHER_UNMATCHED",
                    "severity": "critical",
                    "message": "No governed weather window overlaps the planned execution period.",
                }
            )
        elif not match.suitable:
            conflicts.append(
                {
                    "code": "WEATHER_UNSAFE",
                    "severity": "critical",
                    "message": "The overlapping governed weather window is not suitable.",
                }
            )
        for resource_type, conflict_code in (
            ("crew", "CREW_UNTRACKED"),
            ("vessel", "VESSEL_CONFLICT"),
            ("spare_part", "PART_UNTRACKED"),
            ("tool", "TOOL_UNTRACKED"),
        ):
            if not by_type.get(resource_type):
                conflicts.append(
                    {
                        "code": conflict_code,
                        "severity": "warning",
                        "message": f"No {resource_type} reservation is linked to the work order.",
                    }
                )
        readiness = max(0, 100 - 20 * len(conflicts))
        status = "ready"
        if work_order.status in {"completed", "closed"}:
            status = "completed"
        elif work_order.status in {"in_progress", "in-progress"}:
            status = "in-progress"
        elif conflicts:
            status = "at-risk"
        result.append(
            {
                "id": f"PLAN-{work_order.id}",
                "workOrderId": work_order.id,
                "turbineId": turbine.id,
                "turbineHealthScore": turbine.health_score,
                "issue": work_order.title,
                "description": work_order.selected_action,
                "assignedTeam": work_order.assigned_team,
                "teamKey": work_order.assigned_team,
                "priority": work_order.priority,
                "risk": _risk(work_order.priority, turbine.health_score),
                "workOrderStatus": work_order.status.replace("_", "-"),
                "status": status,
                "startsAt": work_order.planned_start,
                "endsAt": ends_at,
                "deadline": work_order.deadline or ends_at,
                "updatedAt": work_order.updated_at,
                "dayKey": work_order.planned_start.date().isoformat(),
                "durationHours": work_order.estimated_duration_hours,
                "taskProgressPercent": progress,
                "weather": {
                    "id": match.id if match is not None else None,
                    "state": (
                        "suitable"
                        if match is not None and match.suitable
                        else "unsafe"
                        if match is not None
                        else "unmatched"
                    ),
                    "coverage": "full" if match is not None and match.suitable else "none",
                    "startsAt": match.starts_at if match is not None else None,
                    "endsAt": match.ends_at if match is not None else None,
                    "windSpeedMps": match.wind_speed_ms if match is not None else None,
                    "waveHeightM": match.wave_height_m if match is not None else None,
                    "visibilityKm": (
                        match.attributes.get("visibility_km") if match is not None else None
                    ),
                    "reason": (
                        "Governed suitable window selected."
                        if match is not None and match.suitable
                        else "No suitable governed window is available."
                    ),
                },
                "crew": _resource_ref(
                    next(iter(by_type.get("crew", [])), None), missing_label="crew"
                ),
                "vessels": [
                    _resource_ref(item, missing_label="vessel")
                    for item in by_type.get("vessel", [])
                ],
                "spareParts": [
                    _resource_ref(item, missing_label="spare part")
                    for item in by_type.get("spare_part", [])
                ],
                "tools": [
                    _resource_ref(item, missing_label="tool") for item in by_type.get("tool", [])
                ],
                "readinessPercent": readiness,
                "conflicts": conflicts,
                "relatedMissionId": work_order.mission_id,
                "readOnly": False,
                "source": "postgresql-governed-schedule",
            }
        )
    return OperationalPage(
        rows=result,
        total=total,
        filtered_total=filtered_total,
        related_data_boundaries=_maintenance_related_data_boundaries(
            resource_truncated_groups=len(resource_truncated),
            weather_truncated_work_orders=len(weather_truncated),
        ),
    )


async def digital_twin_snapshot(session: AsyncSession, turbine_id: str) -> dict[str, Any] | None:
    turbine = await session.get(Turbine, turbine_id)
    if turbine is None:
        return None
    profile = await session.get(AssetTwinProfile, turbine_id)
    samples = list(
        (
            await session.scalars(
                select(ScadaSample)
                .where(ScadaSample.turbine_id == turbine_id)
                .order_by(desc(ScadaSample.observed_at))
                .limit(1000)
            )
        ).all()
    )
    latest_signals: dict[str, ScadaSample] = {}
    for sample in samples:
        latest_signals.setdefault(sample.variable, sample)
    alarms = list(
        (
            await session.scalars(
                select(Alarm).where(Alarm.turbine_id == turbine_id, Alarm.status != "resolved")
            )
        ).all()
    )
    mission = await session.scalar(
        select(Mission)
        .where(Mission.turbine_id == turbine_id)
        .order_by(desc(Mission.updated_at))
        .limit(1)
    )
    work_order = (
        await session.scalar(select(WorkOrder).where(WorkOrder.mission_id == mission.id))
        if mission is not None
        else None
    )
    prediction_rows = list(
        (
            await session.scalars(
                select(ModelPrediction)
                .where(
                    ModelPrediction.turbine_id == turbine_id, ModelPrediction.status == "succeeded"
                )
                .order_by(desc(ModelPrediction.created_at))
            )
        ).all()
    )
    latest_predictions: dict[str, ModelPrediction] = {}
    for prediction in prediction_rows:
        component = str(prediction.output.get("component", "asset"))
        latest_predictions.setdefault(component, prediction)
    alarm_count_by_subsystem: dict[str, int] = defaultdict(int)
    for alarm in alarms:
        alarm_count_by_subsystem[alarm.subsystem] += 1
    component_keys = sorted(set(latest_predictions) | set(alarm_count_by_subsystem) | {"asset"})
    latest_observed = max(
        (sample.observed_at for sample in latest_signals.values()), default=turbine.updated_at
    )
    active_power = latest_signals.get("active_power")
    wind_speed = latest_signals.get("wind_speed") or latest_signals.get("nacelle_wind_speed")
    weather = await session.scalar(
        select(WeatherWindow)
        .join(WindFarm, WindFarm.id == WeatherWindow.wind_farm_id)
        .where(WindFarm.id == turbine.wind_farm_id, WeatherWindow.ends_at >= datetime.now(UTC))
        .order_by(WeatherWindow.starts_at)
        .limit(1)
    )
    return {
        "turbine": {
            "id": turbine.id,
            "model": turbine.model,
            "manufacturer": profile.manufacturer if profile is not None else "unconfigured",
            "status": turbine.status,
            "powerMW": active_power.value if active_power is not None else 0,
            "windSpeedMps": wind_speed.value if wind_speed is not None else 0,
            "healthScore": turbine.health_score,
            "latitude": profile.latitude if profile is not None else None,
            "longitude": profile.longitude if profile is not None else None,
        },
        "subsystems": [
            {
                "key": component,
                "name": component.replace("_", " ").title(),
                "healthScore": turbine.health_score,
                "state": (
                    "critical"
                    if turbine.health_score < 60
                    else "degraded"
                    if turbine.health_score < 75
                    else "watch"
                    if turbine.health_score < 90
                    else "healthy"
                ),
                "alertCount": alarm_count_by_subsystem.get(component, 0),
                "failureProbability30d": (
                    _safe_number(
                        latest_predictions[component].output.get("failure_probability_30d")
                    )
                    * 100
                    if component in latest_predictions
                    else 0
                ),
                "remainingUsefulLifeDays": (
                    latest_predictions[component].output.get("remaining_useful_life_days")
                    if component in latest_predictions
                    else None
                ),
                "anomalyScore": (
                    latest_predictions[component].output.get("anomaly_score", 0)
                    if component in latest_predictions
                    else 0
                ),
                "primaryFinding": (
                    str(latest_predictions[component].output.get("primary_finding", ""))
                    if component in latest_predictions
                    else next(
                        (alarm.title for alarm in alarms if alarm.subsystem == component),
                        "No governed finding is recorded for this subsystem.",
                    )
                ),
            }
            for component in component_keys
        ],
        "signals": [
            {
                "metric": sample.variable.replace("_", "-"),
                "label": sample.variable.replace("_", " ").title(),
                "value": sample.value,
                "unit": sample.unit,
                "quality": sample.quality,
                "isAnomaly": bool(sample.attributes.get("is_anomaly", False)),
                "observedAt": sample.observed_at,
                "sourceId": sample.source_id,
            }
            for sample in latest_signals.values()
        ],
        "context": {
            "activeAlarmCount": len(alarms),
            "missionId": mission.id if mission is not None else None,
            "missionStatus": mission.status.replace("_", "-") if mission is not None else None,
            "workOrderId": work_order.id if work_order is not None else None,
            "workOrderStatus": (
                work_order.status.replace("_", "-") if work_order is not None else None
            ),
            "nextWeatherWindowId": weather.id if weather is not None else None,
            "nextWeatherWindowSuitability": (
                "suitable"
                if weather is not None and weather.suitable
                else "unsafe"
                if weather is not None
                else None
            ),
        },
        "model": {
            "mode": "operational-state-twin",
            "realPhysicsSimulation": False,
            "readOnly": True,
            "source": "postgresql-timescaledb",
            "geometryConfigured": profile is not None,
            "geometryUri": profile.geometry_uri if profile is not None else None,
            "geometrySha256": profile.geometry_sha256 if profile is not None else None,
            "gisConfigured": profile is not None,
            "coordinateReferenceSystem": (
                profile.coordinate_reference_system if profile is not None else None
            ),
            "elevationM": profile.elevation_m if profile is not None else None,
            "profileUpdatedAt": profile.updated_at if profile is not None else None,
        },
        "snapshotAt": latest_observed,
    }


async def live_report_rows(
    session: AsyncSession, *, generated_at: datetime | None = None
) -> list[dict[str, Any]]:
    generated_at = generated_at or datetime.now(UTC)
    window_started_at = generated_at - timedelta(hours=24)
    farm = await session.scalar(select(WindFarm).order_by(WindFarm.id).limit(1))
    turbine_count = int(await session.scalar(select(func.count()).select_from(Turbine)) or 0)
    alarm_count = int(
        await session.scalar(
            select(func.count()).select_from(Alarm).where(Alarm.triggered_at >= window_started_at)
        )
        or 0
    )
    open_alarm_count = int(
        await session.scalar(
            select(func.count()).select_from(Alarm).where(Alarm.status != "resolved")
        )
        or 0
    )
    mission_count = int(await session.scalar(select(func.count()).select_from(Mission)) or 0)
    work_order_count = int(await session.scalar(select(func.count()).select_from(WorkOrder)) or 0)
    completed_order_count = int(
        await session.scalar(
            select(func.count())
            .select_from(WorkOrder)
            .where(WorkOrder.status.in_(["completed", "closed"]))
        )
        or 0
    )
    latest_mission = await session.scalar(
        select(Mission).order_by(desc(Mission.updated_at)).limit(1)
    )
    latest_decision = (
        await session.scalar(select(Decision).where(Decision.mission_id == latest_mission.id))
        if latest_mission is not None
        else None
    )
    latest_order = (
        await session.scalar(select(WorkOrder).where(WorkOrder.mission_id == latest_mission.id))
        if latest_mission is not None
        else None
    )
    latest_tasks = (
        list(
            (
                await session.scalars(
                    select(WorkOrderTask).where(WorkOrderTask.work_order_id == latest_order.id)
                )
            ).all()
        )
        if latest_order is not None
        else []
    )
    workflow = {
        "turbineId": latest_mission.turbine_id if latest_mission is not None else "unavailable",
        "missionStatus": latest_mission.status if latest_mission is not None else "unavailable",
        "decisionStatus": latest_decision.status if latest_decision is not None else "unavailable",
        "workOrderStatus": latest_order.status if latest_order is not None else "unavailable",
        "completedTaskCount": sum(task.status == "completed" for task in latest_tasks),
        "totalTaskCount": len(latest_tasks),
        "healthScore": 0,
        "mainBearingHealthScore": 0,
        "revision": latest_mission.revision if latest_mission is not None else 0,
        "knowledgeCaseId": None,
    }
    definitions = (
        ("daily-operations", "Operations daily report", "Fleet operations and work queue"),
        ("alarm-analysis", "Alarm analysis report", "Alarm volume and open response queue"),
        ("ai-diagnosis", "AI diagnosis report", "Governed Mission diagnosis and evidence"),
        ("maintenance", "Maintenance report", "Work-order execution and completion"),
        ("asset-health", "Asset health report", "Persisted fleet health state"),
        ("weekly-wind-farm", "Wind-farm weekly report", "Seven-day operational summary"),
    )
    reports: list[dict[str, Any]] = []
    for report_type, title, subtitle in definitions:
        report_id = f"RPT-{report_type.upper()}-{generated_at:%Y%m%d}"
        reports.append(
            {
                "id": report_id,
                "type": report_type,
                "typeLabel": title,
                "title": title,
                "subtitle": subtitle,
                "period": "weekly" if report_type == "weekly-wind-farm" else "daily",
                "periodLabel": (
                    "Previous seven days"
                    if report_type == "weekly-wind-farm"
                    else "Previous 24 hours"
                ),
                "periodStart": (
                    generated_at - timedelta(days=7)
                    if report_type == "weekly-wind-farm"
                    else window_started_at
                ),
                "periodEnd": generated_at,
                "generatedAt": generated_at,
                "status": "ready",
                "ownerAgent": "report_agent",
                "assetScope": farm.name if farm is not None else "Configured fleet",
                "highlight": (
                    f"{turbine_count} assets, {open_alarm_count} open alarms, "
                    f"{mission_count} missions, and {work_order_count} governed work orders."
                ),
                "tags": ["production", "governed", report_type],
                "metrics": [
                    {
                        "label": "Assets",
                        "value": str(turbine_count),
                        "context": "PostgreSQL asset ledger",
                        "tone": "neutral",
                    },
                    {
                        "label": "Alarms in 24h",
                        "value": str(alarm_count),
                        "context": f"{open_alarm_count} remain open",
                        "tone": "attention" if open_alarm_count else "positive",
                    },
                    {
                        "label": "Missions",
                        "value": str(mission_count),
                        "context": "Governed Mission ledger",
                        "tone": "neutral",
                    },
                    {
                        "label": "Completed work orders",
                        "value": str(completed_order_count),
                        "context": f"{work_order_count} total",
                        "tone": "positive",
                    },
                ],
                "sections": [
                    {
                        "heading": "Operational scope",
                        "summary": subtitle,
                        "findings": [
                            "The report was generated at "
                            f"{generated_at.isoformat()} from authoritative ledgers.",
                            f"Open alarm queue: {open_alarm_count}.",
                            "Completed work orders: "
                            f"{completed_order_count} of {work_order_count}.",
                        ],
                    },
                    {
                        "heading": "Governance",
                        "summary": (
                            "The report contains only persisted records visible to the "
                            "delegated user."
                        ),
                        "findings": [
                            "No fixture records are merged into this production report.",
                            "Linked entities retain their authoritative identifiers.",
                        ],
                    },
                ],
                "linkedEntityIds": [
                    item
                    for item in (
                        farm.id if farm is not None else None,
                        latest_mission.id if latest_mission is not None else None,
                        latest_order.id if latest_order is not None else None,
                    )
                    if item is not None
                ],
                "workflow": workflow,
            }
        )
    return reports


async def data_catalog_payload(session: AsyncSession, policy: GraphAccessPolicy) -> dict[str, Any]:
    generated_at = datetime.now(UTC)
    sources = list((await session.scalars(select(IngestSource).order_by(IngestSource.id))).all())
    sample_count = int(await session.scalar(select(func.count()).select_from(ScadaSample)) or 0)
    turbine_count = int(await session.scalar(select(func.count()).select_from(Turbine)) or 0)
    alarm_count = int(await session.scalar(select(func.count()).select_from(Alarm)) or 0)
    knowledge_count = int(
        await session.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0
    )
    entries: list[dict[str, Any]] = []
    for source in sources:
        entries.append(
            {
                "id": f"SOURCE-{source.id}",
                "name": source.display_name,
                "description": f"Governed {source.source_kind} telemetry source.",
                "category": "live",
                "status": "ready" if source.enabled and source.status != "failed" else "read-only",
                "recordCount": sample_count,
                "schemaObjectCount": 3,
                "freshness": source.last_seen_at.isoformat()
                if source.last_seen_at
                else "never seen",
                "quality": "Source quality codes and quarantine are preserved",
                "retention": str(source.policy.get("retention", "operator policy")),
                "source": source.id,
                "queryHref": "/api/scada-measurements?limit=100",
                "queryLabel": "Query archive",
                "deterministic": False,
                "readOnly": False,
            }
        )
    entries.extend(
        [
            {
                "id": "DATA-SCADA-ARCHIVE",
                "name": "TimescaleDB SCADA archive",
                "description": "Quality-aware ordered telemetry archive.",
                "category": "archive",
                "status": "ready",
                "recordCount": sample_count,
                "schemaObjectCount": 4,
                "freshness": generated_at.isoformat(),
                "quality": "Governed quality, lateness, and source sequence",
                "retention": "Operator-configured database retention",
                "source": "PostgreSQL/TimescaleDB",
                "queryHref": "/api/scada-measurements?limit=100",
                "queryLabel": "Query archive",
                "deterministic": False,
                "readOnly": True,
            },
            {
                "id": "DATA-DOMAIN-LEDGERS",
                "name": "Operational domain ledgers",
                "description": "Assets, alarms, missions, decisions, work orders, and evidence.",
                "category": "api",
                "status": "ready",
                "recordCount": turbine_count + alarm_count,
                "schemaObjectCount": 12,
                "freshness": generated_at.isoformat(),
                "quality": "Transactional constraints and command idempotency",
                "retention": "Database lifecycle policy",
                "source": "FastAPI/PostgreSQL",
                "queryHref": "/api/missions",
                "queryLabel": "Query Missions",
                "deterministic": False,
                "readOnly": True,
            },
            {
                "id": "DATA-KNOWLEDGE",
                "name": "Governed knowledge corpus",
                "description": (
                    "Verified artifacts, extracted text, embeddings, and graph projections."
                ),
                "category": "schema",
                "status": "ready",
                "recordCount": knowledge_count,
                "schemaObjectCount": 5,
                "freshness": generated_at.isoformat(),
                "quality": "Artifact hash and indexing state",
                "retention": "Versioned document lifecycle",
                "source": "MinIO/pgvector/Neo4j",
                "queryHref": "/api/knowledge-documents",
                "queryLabel": "Open corpus",
                "deterministic": False,
                "readOnly": False,
            },
        ]
    )
    benchmark_page = await benchmark_dataset_page(
        session,
        policy,
        limit=BENCHMARK_DATASET_PAGE_MAX,
    )
    for benchmark in benchmark_page["data"]:
        coverage = benchmark["coverage"]
        mapping = benchmark["mapping"]
        quality = benchmark["quality"]
        license_metadata = benchmark["license"]
        created_at = benchmark["created_at"]
        entries.append(
            {
                "id": f"BENCHMARK-{benchmark['dataset_version_id']}",
                "name": f"{benchmark['dataset_id']} {benchmark['version']}",
                "description": (
                    "Immutable governed benchmark with bounded event, quality, "
                    "evaluation, and replay summaries."
                ),
                "category": "benchmark",
                "status": (
                    "ready" if benchmark["status"] in {"registered", "ready"} else "read-only"
                ),
                "recordCount": coverage["time_point_count"],
                "schemaObjectCount": mapping["total"],
                "freshness": created_at.isoformat(),
                "quality": (
                    f"{quality['completed_count']} quality reports; "
                    f"{quality['failed_count']} failed; raw values preserved"
                ),
                "retention": f"Immutable derivative · {license_metadata['name']}",
                "source": license_metadata["doi"],
                "queryHref": "/data#care-benchmarks",
                "queryLabel": "Inspect benchmark",
                "deterministic": True,
                "readOnly": True,
            }
        )
    farm = await session.scalar(select(WindFarm).order_by(WindFarm.id).limit(1))
    focus = await session.scalar(select(Turbine).order_by(Turbine.id).limit(1))
    variables = list(
        (
            await session.execute(
                select(ScadaSample.variable, ScadaSample.unit)
                .distinct()
                .order_by(ScadaSample.variable)
            )
        ).all()
    )
    hierarchy = {
        "farm": {
            "id": farm.id if farm is not None else "unconfigured",
            "name": farm.name if farm is not None else "Unconfigured wind farm",
            "turbineCount": turbine_count,
            "capacityMW": farm.capacity_mw if farm is not None else 0,
        },
        "focusTurbine": {
            "id": focus.id if focus is not None else "unconfigured",
            "model": focus.model if focus is not None else "unconfigured",
            "healthScore": focus.health_score if focus is not None else 0,
        },
        "subsystems": [
            {
                "id": f"SUBSYSTEM-{variable.upper()}",
                "key": variable.replace("_", "-"),
                "name": variable.replace("_", " ").title(),
                "healthScore": focus.health_score if focus is not None else 0,
                "state": "healthy" if focus is not None and focus.health_score >= 90 else "watch",
                "sensors": [
                    {
                        "id": (
                            f"SENSOR-{focus.id if focus is not None else 'UNKNOWN'}-"
                            f"{variable.upper()}"
                        ),
                        "metric": variable.replace("_", "-"),
                        "unit": unit,
                        "source": "live-and-archive",
                        "queryHref": (
                            f"/api/scada-measurements?turbineId={focus.id}"
                            f"&metric={variable.replace('_', '-')}&limit=32"
                            if focus is not None
                            else None
                        ),
                    }
                ],
            }
            for variable, unit in variables
        ],
    }
    return {
        "entries": entries,
        "hierarchy": hierarchy,
        "sample_count": sample_count,
        "schema_object_count": 25,
        "benchmark_total": benchmark_page["meta"]["filtered_total"],
        "benchmark_page_max": BENCHMARK_DATASET_PAGE_MAX,
        "snapshot_at": generated_at,
    }
