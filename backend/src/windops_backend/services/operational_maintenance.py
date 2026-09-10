from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import (
    case,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from windops_backend.models import (
    Resource,
    ResourceReservation,
    Turbine,
    WeatherWindow,
    WindFarm,
    WorkOrder,
)
from windops_backend.services.operational_contracts import (
    MaintenanceQueryPlan,
    OperationalPage,
    _maintenance_related_data_boundaries,
    _risk,
)
from windops_backend.services.operational_related import (
    _bounded_resources_by_mission,
    _task_progress_by_work_order,
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
    _query_builder: Callable[..., MaintenanceQueryPlan] | None = None,
) -> OperationalPage:
    dialect_name = session.bind.dialect.name if session.bind is not None else "postgresql"
    query_plan = (_query_builder or build_maintenance_query)(
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
