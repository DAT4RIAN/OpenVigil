from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import String, cast, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.api.deps import (
    Principal,
    _utc_iso,
    get_runtime_settings,
    get_session,
    require_read_access,
    require_roles,
)
from windops_backend.config import Settings
from windops_backend.models import (
    Resource,
    ResourceReservation,
    WeatherWindow,
    WorkOrder,
)
from windops_backend.schemas import (
    ResourceReassignRequest,
    ResourceStockAdjustRequest,
)
from windops_backend.services.idempotency import execute_idempotent_command
from windops_backend.services.platform_governance import (
    adjust_resource_stock,
    reassign_resource,
)

router = APIRouter()


@router.get("/resources", tags=["resources"])
async def resources(
    resource_type: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    query: str = Query(default="", alias="q", max_length=100),
    work_order_id: str | None = Query(default=None, alias="workOrderId", max_length=40),
    cursor: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    weather_cursor: str | None = Query(default=None, max_length=36),
    weather_limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = select(Resource)
    if resource_type:
        statement = statement.where(Resource.resource_type == resource_type)
    if status_filter:
        statement = statement.where(Resource.status == status_filter)
    normalized_query = query.strip().lower()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                func.lower(Resource.id).like(pattern),
                func.lower(Resource.name).like(pattern),
                func.lower(cast(Resource.attributes, String)).like(pattern),
            )
        )
    if work_order_id:
        statement = statement.where(
            exists(
                select(ResourceReservation.id)
                .join(WorkOrder, WorkOrder.mission_id == ResourceReservation.mission_id)
                .where(
                    ResourceReservation.resource_id == Resource.id,
                    WorkOrder.id == work_order_id,
                )
            )
        )
    total = int(
        await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
        or 0
    )
    if cursor:
        statement = statement.where(Resource.id > cursor)
    resource_rows = list(
        (await session.scalars(statement.order_by(Resource.id).limit(limit + 1))).all()
    )
    has_more = len(resource_rows) > limit
    rows = resource_rows[:limit]
    resource_ids = [row.id for row in rows]
    reservations = list(
        (
            await session.scalars(
                select(ResourceReservation)
                .where(ResourceReservation.resource_id.in_(resource_ids))
                .order_by(ResourceReservation.resource_id, ResourceReservation.created_at)
            )
        ).all()
        if resource_ids
        else []
    )
    reservation_work_orders = (
        (
            await session.scalars(
                select(WorkOrder).where(
                    WorkOrder.mission_id.in_([row.mission_id for row in reservations])
                )
            )
        ).all()
        if reservations
        else []
    )
    work_order_by_mission = {row.mission_id: row.id for row in reservation_work_orders}
    reservations_by_resource: dict[str, list[dict[str, Any]]] = {}
    for reservation in reservations:
        reservations_by_resource.setdefault(reservation.resource_id, []).append(
            {
                "reservation_id": reservation.id,
                "mission_id": reservation.mission_id,
                "work_order_id": work_order_by_mission.get(reservation.mission_id),
                "quantity": reservation.quantity,
                "created_at": reservation.created_at,
            }
        )
    weather_statement = select(WeatherWindow)
    if weather_cursor:
        weather_statement = weather_statement.where(WeatherWindow.id > weather_cursor)
    weather_rows = list(
        (
            await session.scalars(
                weather_statement.order_by(WeatherWindow.id).limit(weather_limit + 1)
            )
        ).all()
    )
    weather_has_more = len(weather_rows) > weather_limit
    weather_page = weather_rows[:weather_limit]
    return {
        "count": len(rows),
        "total": total,
        "next_cursor": rows[-1].id if has_more and rows else None,
        "resources": [
            {
                "resource_id": row.id,
                "resource_type": row.resource_type,
                "name": row.name,
                "quantity": row.quantity,
                "status": row.status,
                "attributes": row.attributes,
                "updated_at": _utc_iso(row.updated_at),
                "reservations": reservations_by_resource.get(row.id, []),
            }
            for row in rows
        ],
        "weather_windows": [
            {
                "window_id": row.id,
                "wind_farm_id": row.wind_farm_id,
                "starts_at": _utc_iso(row.starts_at),
                "ends_at": _utc_iso(row.ends_at),
                "wind_speed_ms": row.wind_speed_ms,
                "wave_height_m": row.wave_height_m,
                "suitable": row.suitable,
                "attributes": row.attributes,
            }
            for row in weather_page
        ],
        "weather_count": len(weather_page),
        "weather_next_cursor": (weather_page[-1].id if weather_has_more and weather_page else None),
    }


@router.post("/resources/{resource_id}/stock-adjustments", tags=["resources"])
async def adjust_resource_stock_command(
    resource_id: str,
    payload: ResourceStockAdjustRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        row = await adjust_resource_stock(
            session,
            resource_id=resource_id,
            request=payload,
            subject=principal.subject,
        )
        return {
            "resource_id": row.id,
            "quantity": row.quantity,
            "status": row.status,
            "updated_at": row.updated_at,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="resource.stock-adjust.v1",
        target=resource_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post("/resources/reassignments", tags=["resources"])
async def reassign_resource_command(
    payload: ResourceReassignRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        reservation = await reassign_resource(
            session,
            payload,
            subject=principal.subject,
            eam_enabled=settings.eam_enabled,
        )
        return {
            "reservation_id": reservation.id,
            "mission_id": reservation.mission_id,
            "resource_id": reservation.resource_id,
            "quantity": reservation.quantity,
            "updated_at": datetime.now(UTC),
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="resource.reassign.v1",
        target=(f"{payload.mission_id}:{payload.from_resource_id}:{payload.to_resource_id}"),
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result
