from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.api.deps import (
    Principal,
    get_session,
    require_read_access,
    require_roles,
)
from windops_backend.errors import (
    NotFoundError,
)
from windops_backend.models import (
    Alarm,
    Mission,
)
from windops_backend.schemas import (
    AlarmCommandRequest,
)
from windops_backend.services.alarms import execute_alarm_command

router = APIRouter()


@router.get("/alarms", tags=["alarms"])
async def alarms(
    turbine_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = select(Alarm)
    if turbine_id:
        statement = statement.where(Alarm.turbine_id == turbine_id)
    if status_filter:
        statement = statement.where(Alarm.status == status_filter)
    if severity:
        statement = statement.where(Alarm.severity == severity)
    if cursor:
        statement = statement.where(Alarm.id > cursor)
    rows = list((await session.scalars(statement.order_by(Alarm.id).limit(limit + 1))).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    mission_rows = (
        (
            await session.execute(
                select(Mission.alarm_id, Mission.id).where(
                    Mission.alarm_id.in_([row.id for row in page])
                )
            )
        ).all()
        if page
        else []
    )
    mission_by_alarm = {str(alarm_id): str(mission_id) for alarm_id, mission_id in mission_rows}
    return {
        "count": len(page),
        "next_cursor": page[-1].id if has_more and page else None,
        "alarms": [
            {
                "alarm_id": row.id,
                "turbine_id": row.turbine_id,
                "code": row.code,
                "subsystem": row.subsystem,
                "title": row.title,
                "severity": row.severity,
                "status": row.status,
                "ai_status": row.ai_status,
                "triggered_at": row.triggered_at,
                "acknowledged_at": row.acknowledged_at,
                "acknowledged_by": row.acknowledged_by,
                "assigned_to": row.assigned_to,
                "resolved_at": row.resolved_at,
                "revision": row.revision,
                "updated_at": row.updated_at,
                "evidence": row.evidence,
                "mission_id": mission_by_alarm.get(row.id),
            }
            for row in page
        ],
    }


@router.post("/alarms/{alarm_id}", tags=["alarms"])
async def execute_alarm_command_api(
    alarm_id: str,
    payload: AlarmCommandRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager", "operations_approver")),
) -> dict[str, Any]:
    result, replayed = await execute_alarm_command(
        session,
        alarm_id,
        payload,
        idempotency_key=idempotency_key,
        subject=principal.subject,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return {**result, "replayed": False}


@router.get("/alarms/{alarm_id}", tags=["alarms"])
async def alarm_detail(
    alarm_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    alarm = await session.get(Alarm, alarm_id)
    if alarm is None:
        raise NotFoundError(f"alarm {alarm_id} was not found")
    mission_id = await session.scalar(select(Mission.id).where(Mission.alarm_id == alarm.id))
    return {
        "alarm_id": alarm.id,
        "turbine_id": alarm.turbine_id,
        "code": alarm.code,
        "subsystem": alarm.subsystem,
        "title": alarm.title,
        "severity": alarm.severity,
        "status": alarm.status,
        "ai_status": alarm.ai_status,
        "triggered_at": alarm.triggered_at,
        "acknowledged_at": alarm.acknowledged_at,
        "acknowledged_by": alarm.acknowledged_by,
        "assigned_to": alarm.assigned_to,
        "resolved_at": alarm.resolved_at,
        "revision": alarm.revision,
        "updated_at": alarm.updated_at,
        "evidence": alarm.evidence,
        "mission_id": mission_id,
    }
