from __future__ import annotations

from collections import defaultdict

from sqlalchemy import (
    case,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.models import (
    AgentExecution,
    Evidence,
    Resource,
    ResourceReservation,
    WorkOrderTask,
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
