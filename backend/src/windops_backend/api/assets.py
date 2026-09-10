from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import and_, case, desc, exists, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.api.deps import (
    ALLOWED_TWIN_CONTENT_TYPES,
    MAX_TWIN_ARTIFACT_BYTES,
    Principal,
    _utc_iso,
    get_artifact_verifier,
    get_runtime_settings,
    get_session,
    require_read_access,
    require_roles,
)
from windops_backend.config import Settings
from windops_backend.errors import (
    InvalidTransitionError,
    NotFoundError,
)
from windops_backend.models import (
    Alarm,
    AssetHealthEvent,
    AssetTwinProfile,
    Mission,
    ScadaSample,
    Turbine,
    WindFarm,
    WorkOrder,
)
from windops_backend.schemas import (
    AssetTwinArtifactUploadRequest,
    AssetTwinProfileRequest,
)
from windops_backend.services.asset_details import asset_detail_snapshot
from windops_backend.services.dashboard import dashboard_snapshot
from windops_backend.services.idempotency import execute_idempotent_command
from windops_backend.services.operational_views import (
    digital_twin_snapshot,
)
from windops_backend.services.platform_governance import (
    upsert_asset_twin_profile,
)
from windops_backend.storage import ArtifactVerifier

router = APIRouter()


@router.get("/turbines", tags=["assets"])
async def turbines(
    status_filter: str | None = Query(default=None, alias="status"),
    wind_farm_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = select(Turbine)
    if status_filter:
        statement = statement.where(Turbine.status == status_filter)
    if wind_farm_id:
        statement = statement.where(Turbine.wind_farm_id == wind_farm_id)
    if cursor:
        statement = statement.where(Turbine.id > cursor)
    rows = list((await session.scalars(statement.order_by(Turbine.id).limit(limit + 1))).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    turbine_ids = [row.id for row in page]
    profiles = (
        list(
            (
                await session.scalars(
                    select(AssetTwinProfile).where(AssetTwinProfile.turbine_id.in_(turbine_ids))
                )
            ).all()
        )
        if turbine_ids
        else []
    )
    samples = []
    if turbine_ids:
        signal_variables = [
            "active_power",
            "wind_speed",
            "nacelle_wind_speed",
            "rotor_speed",
            "nacelle_direction",
            "availability_percent",
        ]
        latest_samples = (
            select(
                ScadaSample.id.label("sample_id"),
                func.row_number()
                .over(
                    partition_by=(ScadaSample.turbine_id, ScadaSample.variable),
                    order_by=(desc(ScadaSample.observed_at), desc(ScadaSample.id)),
                )
                .label("row_number"),
            )
            .where(
                ScadaSample.turbine_id.in_(turbine_ids),
                ScadaSample.variable.in_(signal_variables),
            )
            .subquery()
        )
        samples = list(
            (
                await session.scalars(
                    select(ScadaSample)
                    .join(latest_samples, latest_samples.c.sample_id == ScadaSample.id)
                    .where(latest_samples.c.row_number == 1)
                )
            ).all()
        )
    alarm_counts = (
        (
            await session.execute(
                select(Alarm.turbine_id, func.count())
                .where(Alarm.turbine_id.in_(turbine_ids), Alarm.status != "resolved")
                .group_by(Alarm.turbine_id)
            )
        ).all()
        if turbine_ids
        else []
    )
    latest_missions = (
        select(
            Mission.id.label("mission_id"),
            func.row_number()
            .over(
                partition_by=Mission.turbine_id,
                order_by=(desc(Mission.updated_at), desc(Mission.id)),
            )
            .label("row_number"),
        )
        .where(Mission.turbine_id.in_(turbine_ids))
        .subquery()
        if turbine_ids
        else None
    )
    mission_rows = (
        list(
            (
                await session.scalars(
                    select(Mission)
                    .join(latest_missions, latest_missions.c.mission_id == Mission.id)
                    .where(latest_missions.c.row_number == 1)
                )
            ).all()
        )
        if latest_missions is not None
        else []
    )
    now = datetime.now(UTC)
    latest_completed_orders = (
        select(
            WorkOrder.id.label("work_order_id"),
            func.row_number()
            .over(
                partition_by=WorkOrder.turbine_id,
                order_by=(desc(WorkOrder.updated_at), desc(WorkOrder.id)),
            )
            .label("row_number"),
        )
        .where(
            WorkOrder.turbine_id.in_(turbine_ids),
            WorkOrder.completed_at.is_not(None),
        )
        .subquery()
        if turbine_ids
        else None
    )
    completed_orders = (
        list(
            (
                await session.scalars(
                    select(WorkOrder)
                    .join(
                        latest_completed_orders,
                        latest_completed_orders.c.work_order_id == WorkOrder.id,
                    )
                    .where(latest_completed_orders.c.row_number == 1)
                )
            ).all()
        )
        if latest_completed_orders is not None
        else []
    )
    next_work_orders = (
        select(
            WorkOrder.id.label("work_order_id"),
            func.row_number()
            .over(
                partition_by=WorkOrder.turbine_id,
                order_by=(WorkOrder.planned_start, desc(WorkOrder.updated_at), desc(WorkOrder.id)),
            )
            .label("row_number"),
        )
        .where(
            WorkOrder.turbine_id.in_(turbine_ids),
            WorkOrder.planned_start.is_not(None),
            WorkOrder.planned_start >= now,
        )
        .subquery()
        if turbine_ids
        else None
    )
    upcoming_orders = (
        list(
            (
                await session.scalars(
                    select(WorkOrder)
                    .join(next_work_orders, next_work_orders.c.work_order_id == WorkOrder.id)
                    .where(next_work_orders.c.row_number == 1)
                )
            ).all()
        )
        if next_work_orders is not None
        else []
    )
    farms = (
        list(
            (
                await session.scalars(
                    select(WindFarm).where(WindFarm.id.in_({row.wind_farm_id for row in page}))
                )
            ).all()
        )
        if page
        else []
    )
    profile_by_turbine = {row.turbine_id: row for row in profiles}
    latest_signals: dict[tuple[str, str], ScadaSample] = {}
    for sample in samples:
        latest_signals.setdefault((sample.turbine_id, sample.variable), sample)
    alarm_count_by_turbine = {str(turbine_id): int(count) for turbine_id, count in alarm_counts}
    mission_by_turbine: dict[str, Mission] = {}
    for mission in mission_rows:
        mission_by_turbine.setdefault(mission.turbine_id, mission)
    completed_by_turbine: dict[str, WorkOrder] = {}
    next_order_by_turbine: dict[str, WorkOrder] = {}
    completed_by_turbine.update({row.turbine_id: row for row in completed_orders})
    next_order_by_turbine.update({row.turbine_id: row for row in upcoming_orders})

    def signal(turbine_id: str, *variables: str) -> ScadaSample | None:
        return next(
            (
                latest_signals[(turbine_id, variable)]
                for variable in variables
                if (turbine_id, variable) in latest_signals
            ),
            None,
        )

    def signal_value(turbine_id: str, *variables: str) -> float | None:
        sample = signal(turbine_id, *variables)
        return float(sample.value) if sample is not None else None

    return {
        "count": len(page),
        "next_cursor": page[-1].id if has_more and page else None,
        "turbines": [
            {
                "turbine_id": row.id,
                "wind_farm_id": row.wind_farm_id,
                "model": row.model,
                "status": row.status,
                "health_score": row.health_score,
                "manufacturer": (
                    profile_by_turbine[row.id].manufacturer
                    if row.id in profile_by_turbine
                    else None
                ),
                "latitude": (
                    profile_by_turbine[row.id].latitude if row.id in profile_by_turbine else None
                ),
                "longitude": (
                    profile_by_turbine[row.id].longitude if row.id in profile_by_turbine else None
                ),
                "active_power_mw": signal_value(row.id, "active_power"),
                "wind_speed_ms": signal_value(row.id, "wind_speed", "nacelle_wind_speed"),
                "rotor_speed_rpm": signal_value(row.id, "rotor_speed"),
                "nacelle_direction_deg": signal_value(row.id, "nacelle_direction"),
                "availability_percent": signal_value(row.id, "availability_percent"),
                "telemetry_observed_at": max(
                    (
                        sample.observed_at
                        for (sample_turbine_id, _), sample in latest_signals.items()
                        if sample_turbine_id == row.id
                    ),
                    default=None,
                ),
                "active_alarm_count": alarm_count_by_turbine.get(row.id, 0),
                "current_mission_id": (
                    mission_by_turbine[row.id].id if row.id in mission_by_turbine else None
                ),
                "last_maintenance_at": (
                    completed_by_turbine[row.id].completed_at
                    if row.id in completed_by_turbine
                    else None
                ),
                "next_inspection_at": (
                    next_order_by_turbine[row.id].planned_start
                    if row.id in next_order_by_turbine
                    else None
                ),
                "updated_at": _utc_iso(row.updated_at),
            }
            for row in page
        ],
        "wind_farms": [
            {
                "wind_farm_id": farm.id,
                "name": farm.name,
                "capacity_mw": farm.capacity_mw,
            }
            for farm in farms
        ],
    }


@router.get("/dashboard", tags=["operations"])
async def operations_dashboard(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    return {
        "data": await dashboard_snapshot(
            session,
            expose_global_sequence=principal.graph_access_policy().unrestricted,
        ),
        "meta": {"fixture_fallback": False, "read_only": True},
    }


@router.get("/turbines/{turbine_id}", tags=["assets"])
async def turbine_detail(
    turbine_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    snapshot = await asset_detail_snapshot(session, turbine_id)
    if snapshot is None:
        raise NotFoundError(f"turbine {turbine_id} was not found")
    return {
        "data": snapshot,
        "meta": {
            "source": "postgresql-timescaledb-governed-asset",
            "fixture_fallback": False,
        },
    }


@router.get("/turbines/{turbine_id}/health", tags=["assets"])
async def turbine_health(
    turbine_id: str,
    cursor: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    turbine = await session.get(Turbine, turbine_id)
    if turbine is None:
        raise NotFoundError(f"turbine {turbine_id} was not found")
    statement = select(AssetHealthEvent).where(AssetHealthEvent.turbine_id == turbine_id)
    if cursor:
        cursor_event = await session.get(AssetHealthEvent, cursor)
        if cursor_event is None or cursor_event.turbine_id != turbine_id:
            raise NotFoundError(f"health cursor {cursor} was not found")
        statement = statement.where(
            or_(
                AssetHealthEvent.recorded_at < cursor_event.recorded_at,
                and_(
                    AssetHealthEvent.recorded_at == cursor_event.recorded_at,
                    AssetHealthEvent.id < cursor_event.id,
                ),
            )
        )
    event_rows = list(
        (
            await session.scalars(
                statement.order_by(
                    AssetHealthEvent.recorded_at.desc(),
                    AssetHealthEvent.id.desc(),
                ).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(event_rows) > limit
    events = event_rows[:limit]
    return {
        "turbine_id": turbine.id,
        "status": turbine.status,
        "health_score": turbine.health_score,
        "count": len(events),
        "next_cursor": events[-1].id if has_more and events else None,
        "history": [
            {
                "health_event_id": event.id,
                "mission_id": event.mission_id,
                "score": event.score,
                "status": event.status,
                "reason": event.reason,
                "recorded_at": event.recorded_at,
            }
            for event in events
        ],
    }


@router.get("/health/assessments", tags=["assets"])
async def health_assessments(
    turbine_id: str | None = None,
    state: str | None = None,
    risk: str | None = None,
    cursor: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    health_state_expression = case(
        (Turbine.status == "maintenance", "maintenance"),
        (Turbine.status == "offline", "offline"),
        (Turbine.health_score < 60, "critical"),
        (Turbine.health_score < 75, "degraded"),
        (Turbine.health_score < 90, "watch"),
        else_="healthy",
    )
    critical_alarm = exists(
        select(Alarm.id).where(
            Alarm.turbine_id == Turbine.id,
            Alarm.status != "resolved",
            Alarm.severity == "critical",
        )
    )
    major_alarm = exists(
        select(Alarm.id).where(
            Alarm.turbine_id == Turbine.id,
            Alarm.status != "resolved",
            Alarm.severity.in_(("major", "high")),
        )
    )
    active_alarm = exists(
        select(Alarm.id).where(
            Alarm.turbine_id == Turbine.id,
            Alarm.status != "resolved",
        )
    )
    risk_expression = case(
        (or_(critical_alarm, Turbine.health_score < 60), "critical"),
        (or_(major_alarm, Turbine.health_score < 75), "high"),
        (or_(active_alarm, Turbine.health_score < 90), "medium"),
        else_="low",
    )
    turbine_statement = select(Turbine)
    if turbine_id:
        turbine_statement = turbine_statement.where(Turbine.id == turbine_id)
    if state:
        turbine_statement = turbine_statement.where(health_state_expression == state)
    if risk:
        turbine_statement = turbine_statement.where(risk_expression == risk)
    total = int(
        await session.scalar(
            select(func.count()).select_from(turbine_statement.order_by(None).subquery())
        )
        or 0
    )
    if cursor:
        turbine_statement = turbine_statement.where(Turbine.id > cursor)
    raw_turbine_rows = list(
        (await session.scalars(turbine_statement.order_by(Turbine.id).limit(limit + 1))).all()
    )
    has_more = len(raw_turbine_rows) > limit
    turbine_rows = raw_turbine_rows[:limit]
    turbine_ids = [row.id for row in turbine_rows]
    if turbine_ids and session.bind is not None and session.bind.dialect.name == "postgresql":
        page_turbines = (
            select(Turbine.id.label("page_turbine_id"))
            .where(Turbine.id.in_(turbine_ids))
            .subquery()
        )
        latest_event_ids = (
            select(AssetHealthEvent.id.label("health_event_id"))
            .where(AssetHealthEvent.turbine_id == page_turbines.c.page_turbine_id)
            .order_by(
                AssetHealthEvent.recorded_at.desc(),
                AssetHealthEvent.id.desc(),
            )
            .limit(2)
            .lateral("latest_health_events")
        )
        health_statement = (
            select(AssetHealthEvent)
            .select_from(page_turbines)
            .join(latest_event_ids, true())
            .join(AssetHealthEvent, AssetHealthEvent.id == latest_event_ids.c.health_event_id)
        )
    else:
        ranked_health = (
            select(
                AssetHealthEvent.id.label("health_event_id"),
                func.row_number()
                .over(
                    partition_by=AssetHealthEvent.turbine_id,
                    order_by=(
                        AssetHealthEvent.recorded_at.desc(),
                        AssetHealthEvent.id.desc(),
                    ),
                )
                .label("event_rank"),
            )
            .where(AssetHealthEvent.turbine_id.in_(turbine_ids))
            .subquery()
        )
        health_statement = (
            select(AssetHealthEvent)
            .join(
                ranked_health,
                ranked_health.c.health_event_id == AssetHealthEvent.id,
            )
            .where(ranked_health.c.event_rank <= 2)
        )
    health_rows = (
        list(
            (
                await session.scalars(
                    health_statement.order_by(
                        AssetHealthEvent.turbine_id,
                        AssetHealthEvent.recorded_at.desc(),
                        AssetHealthEvent.id.desc(),
                    )
                )
            ).all()
        )
        if turbine_ids
        else []
    )
    health_by_turbine: dict[str, list[AssetHealthEvent]] = {}
    for event in health_rows:
        health_by_turbine.setdefault(event.turbine_id, []).append(event)
    severity_rank = case(
        (Alarm.severity == "critical", 3),
        (Alarm.severity.in_(("major", "high")), 2),
        else_=1,
    )
    alarm_aggregates = (
        list(
            (
                await session.execute(
                    select(
                        Alarm.turbine_id,
                        func.count(Alarm.id),
                        func.max(severity_rank),
                        func.max(Alarm.title),
                    )
                    .where(
                        Alarm.turbine_id.in_(turbine_ids),
                        Alarm.status != "resolved",
                    )
                    .group_by(Alarm.turbine_id)
                )
            ).all()
        )
        if turbine_ids
        else []
    )
    alarms_by_turbine = {
        str(row_turbine_id): (int(count), int(max_rank), str(title))
        for row_turbine_id, count, max_rank, title in alarm_aggregates
    }

    def health_state(turbine: Turbine) -> str:
        if turbine.status == "maintenance":
            return "maintenance"
        if turbine.status == "offline":
            return "offline"
        if turbine.health_score < 60:
            return "critical"
        if turbine.health_score < 75:
            return "degraded"
        if turbine.health_score < 90:
            return "watch"
        return "healthy"

    def risk_level(turbine: Turbine, alarm_rank: int) -> str:
        if alarm_rank >= 3 or turbine.health_score < 60:
            return "critical"
        if alarm_rank >= 2 or turbine.health_score < 75:
            return "high"
        if alarm_rank or turbine.health_score < 90:
            return "medium"
        return "low"

    assessments = []
    for turbine in turbine_rows:
        events = health_by_turbine.get(turbine.id, [])
        latest = events[0] if events else None
        previous = events[1] if len(events) > 1 else None
        trend = "stable"
        if latest is not None and previous is not None:
            if latest.score > previous.score:
                trend = "improving"
            elif latest.score < previous.score:
                trend = "declining"
        alarm_count, alarm_rank, alarm_title = alarms_by_turbine.get(turbine.id, (0, 0, ""))
        current_state = health_state(turbine)
        current_risk = risk_level(turbine, alarm_rank)
        primary_finding = (
            latest.reason
            if latest is not None
            else (alarm_title if alarm_count else "No active condition finding is recorded")
        )
        assessments.append(
            {
                "assessment_id": f"HEALTH-{turbine.id}",
                "turbine_id": turbine.id,
                "turbine_model": turbine.model,
                "health_score": turbine.health_score,
                "state": current_state,
                "trend": trend,
                "risk_level": current_risk,
                "active_alarm_count": alarm_count,
                "failure_probability_30d": None,
                "remaining_useful_life_days": None,
                "anomaly_score": None,
                "prediction_available": False,
                "primary_finding": primary_finding,
                "mission_id": latest.mission_id if latest is not None else None,
                "assessed_at": latest.recorded_at if latest is not None else turbine.updated_at,
            }
        )
    return {
        "assessments": assessments,
        "meta": {
            "count": len(assessments),
            "total": total,
            "next_cursor": turbine_rows[-1].id if has_more and turbine_rows else None,
            "has_more": has_more,
            "snapshot_at": datetime.now(UTC),
            "prediction_provider": None,
        },
    }


@router.get("/digital-twin", tags=["assets"])
async def digital_twin(
    turbine_id: str = Query(alias="turbineId", min_length=3, max_length=32),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    snapshot = await digital_twin_snapshot(session, turbine_id)
    if snapshot is None:
        raise NotFoundError(f"turbine {turbine_id} was not found")
    return {
        "data": snapshot,
        "meta": {
            "turbine_id": turbine_id,
            "snapshot_at": snapshot["snapshotAt"],
            "source": "postgresql-timescaledb",
            "fixture_fallback": False,
        },
    }


@router.post("/turbines/{turbine_id}/twin-profile/artifacts/presign", tags=["assets"])
async def presign_twin_artifact(
    turbine_id: str,
    payload: AssetTwinArtifactUploadRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        if await session.get(Turbine, turbine_id) is None:
            raise NotFoundError(f"turbine {turbine_id} was not found")
        try:
            upload = await artifact_verifier.create_object_upload(
                bucket=settings.minio_twin_bucket,
                prefix=f"turbines/{turbine_id}/twin",
                file_name=payload.file_name,
                content_type=payload.content_type,
                artifact_sha256=payload.artifact_sha256,
                allowed_content_types=ALLOWED_TWIN_CONTENT_TYPES,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        return {"turbine_id": turbine_id, **upload}

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="asset.twin-artifact.presign.v1",
        target=turbine_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post("/turbines/{turbine_id}/twin-profile", tags=["assets"])
async def configure_twin_profile(
    turbine_id: str,
    payload: AssetTwinProfileRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        try:
            await artifact_verifier.read_verified_object(
                payload.geometry_uri,
                payload.geometry_sha256,
                bucket=settings.minio_twin_bucket,
                prefix=f"turbines/{turbine_id}/twin",
                allowed_content_types=ALLOWED_TWIN_CONTENT_TYPES,
                max_bytes=MAX_TWIN_ARTIFACT_BYTES,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        row = await upsert_asset_twin_profile(
            session,
            turbine_id=turbine_id,
            request=payload,
            subject=principal.subject,
        )
        return {
            "turbine_id": row.turbine_id,
            "manufacturer": row.manufacturer,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "elevation_m": row.elevation_m,
            "coordinate_reference_system": row.coordinate_reference_system,
            "geometry_uri": row.geometry_uri,
            "geometry_sha256": row.geometry_sha256,
            "verified": True,
            "updated_at": row.updated_at,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="asset.twin-profile.configure.v1",
        target=turbine_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.get("/turbines/{turbine_id}/twin-profile/artifacts/view", tags=["assets"])
async def view_twin_artifact(
    turbine_id: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    profile = await session.get(AssetTwinProfile, turbine_id)
    if profile is None:
        raise NotFoundError(f"twin profile for turbine {turbine_id} was not found")
    try:
        _, content_type = await artifact_verifier.read_verified_object(
            profile.geometry_uri,
            profile.geometry_sha256,
            bucket=settings.minio_twin_bucket,
            prefix=f"turbines/{turbine_id}/twin",
            allowed_content_types=ALLOWED_TWIN_CONTENT_TYPES,
            max_bytes=MAX_TWIN_ARTIFACT_BYTES,
        )
        download = await artifact_verifier.create_object_download(
            profile.geometry_uri,
            bucket=settings.minio_twin_bucket,
            prefix=f"turbines/{turbine_id}/twin",
            response_content_type=content_type,
        )
    except ValueError as exc:
        raise InvalidTransitionError(str(exc)) from exc
    return {
        "turbine_id": turbine_id,
        "artifact_sha256": profile.geometry_sha256,
        "content_type": content_type,
        **download,
    }
