from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import Integer, case, func, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.api.deps import (
    Principal,
    _drain_or_dispatch_graph_projection_events,
    get_runtime_settings,
    get_session,
    require_read_access,
    require_roles,
)
from windops_backend.config import Settings, TelemetrySourcePolicy
from windops_backend.errors import (
    NotFoundError,
)
from windops_backend.models import (
    IngestSource,
    IngestStreamState,
    ScadaSample,
    Turbine,
)
from windops_backend.outbox import (
    mark_dispatched,
    pending_events_for_missions,
    process_outbox_event,
)
from windops_backend.schemas import (
    ScadaIngestRequest,
    ScadaIngestResponse,
)
from windops_backend.services.ingest import ingest_sample
from windops_backend.services.workflow import advance_mission_to_review

router = APIRouter()


@router.post(
    "/scada/ingest",
    response_model=ScadaIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["scada"],
)
async def ingest_scada(
    payload: ScadaIngestRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(require_roles("scada_ingestor")),
) -> ScadaIngestResponse:
    policy = settings.telemetry_source_policies.get(payload.source_id)
    if policy is None:
        configured_source = await session.get(IngestSource, payload.source_id)
        if configured_source is not None:
            if not configured_source.enabled:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"code": "INGEST_SOURCE_DISABLED", "message": "Source is disabled"},
                )
            policy = TelemetrySourcePolicy.model_validate(configured_source.policy)
    if policy is None:
        if settings.environment.value == "production":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "UNKNOWN_INGEST_SOURCE", "message": "Source is not configured"},
            )
        policy = TelemetrySourcePolicy(
            display_name="Default normalized SCADA source",
            source_kind="rest",
            sequence_required=False,
        )
    authenticated_source = f"ingest-source:{payload.source_id}"
    if "test_system" not in principal.roles and principal.subject not in {
        authenticated_source,
        "scada-ingestor",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INGEST_SOURCE_MISMATCH",
                "message": "Credential is not authorized for this source",
            },
        )
    results = []
    for sample in payload.samples:
        result = await ingest_sample(
            session,
            sample,
            source_id=payload.source_id,
            policy=policy,
        )
        results.append(result)
    mission_ids = list({item.mission_id for item in results if item.mission_id is not None})
    event_ids = await pending_events_for_missions(session, mission_ids)
    await session.commit()
    app_factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    if settings.outbox_inline_drain:
        for event_id in event_ids:
            await process_outbox_event(app_factory, settings, event_id, advance_mission_to_review)
    else:
        from windops_backend.workers import dispatch_event_ids

        dispatch_event_ids(event_ids)
        await mark_dispatched(app_factory, event_ids)
    await _drain_or_dispatch_graph_projection_events(request, settings)
    return ScadaIngestResponse(
        accepted=sum(item.disposition == "accepted" for item in results),
        duplicates=sum(item.disposition == "duplicate" for item in results),
        quarantined=sum(item.disposition == "quarantined" for item in results),
        results=results,
    )


@router.get("/ingest/sources", tags=["scada"])
async def ingest_sources(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    now = datetime.now(UTC)
    sources = list((await session.scalars(select(IngestSource).order_by(IngestSource.id))).all())
    states = list(
        (
            await session.scalars(
                select(IngestStreamState).order_by(
                    IngestStreamState.source_id, IngestStreamState.stream_key
                )
            )
        ).all()
    )
    states_by_source: dict[str, list[IngestStreamState]] = {}
    for stream_state in states:
        states_by_source.setdefault(stream_state.source_id, []).append(stream_state)

    def source_health(source: IngestSource) -> tuple[str, int | None]:
        if not source.enabled:
            return "disabled", None
        if source.last_seen_at is None:
            return "never_seen", None
        last_seen = source.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)
        age_seconds = max(0, round((now - last_seen).total_seconds()))
        expected_heartbeat = int(source.policy.get("expected_heartbeat_seconds", 60))
        if age_seconds > expected_heartbeat * 2:
            return "stale", age_seconds
        return source.status, age_seconds

    return {
        "count": len(sources),
        "sources": [
            {
                "source_id": source.id,
                "display_name": source.display_name,
                "source_kind": source.source_kind,
                "enabled": source.enabled,
                "status": source_health(source)[0],
                "last_seen_at": source.last_seen_at,
                "seconds_since_last_seen": source_health(source)[1],
                "policy": source.policy,
                "streams": [
                    {
                        "stream_key": stream.stream_key,
                        "highest_sequence": stream.highest_sequence,
                        "watermark_observed_at": stream.watermark_observed_at,
                        "accepted_count": stream.accepted_count,
                        "duplicate_count": stream.duplicate_count,
                        "late_count": stream.late_count,
                        "quarantined_count": stream.quarantined_count,
                        "updated_at": stream.updated_at,
                    }
                    for stream in states_by_source.get(source.id, [])
                ],
            }
            for source in sources
        ],
    }


SCADA_WINDOWS = {
    "LIVE": timedelta(minutes=15),
    "1H": timedelta(hours=1),
    "6H": timedelta(hours=6),
    "24H": timedelta(hours=24),
    "7D": timedelta(days=7),
    "30D": timedelta(days=30),
}


def _normalized_scada_window(
    range_name: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
) -> tuple[str, datetime, datetime]:
    if (starts_at is None) != (ends_at is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_SCADA_WINDOW",
                "message": "from and to must be supplied together",
            },
        )
    if starts_at is not None and ends_at is not None:
        if starts_at.tzinfo is None or ends_at.tzinfo is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "INVALID_SCADA_WINDOW",
                    "message": "from and to must include explicit timezones",
                },
            )
        normalized_start = starts_at.astimezone(UTC)
        normalized_end = ends_at.astimezone(UTC)
        if normalized_start >= normalized_end or normalized_end - normalized_start > timedelta(
            days=365
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "INVALID_SCADA_WINDOW",
                    "message": "custom SCADA windows must be positive and no longer than 365 days",
                },
            )
        return "CUSTOM", normalized_start, normalized_end
    normalized_range = range_name.strip().upper()
    duration = SCADA_WINDOWS.get(normalized_range)
    if duration is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_SCADA_RANGE",
                "message": f"range must be one of {', '.join(SCADA_WINDOWS)}",
            },
        )
    end = datetime.now(UTC)
    return normalized_range, end - duration, end


def _quality_from_rank(rank: int) -> str:
    return "bad" if rank >= 2 else "uncertain" if rank == 1 else "good"


@router.get("/scada/history", tags=["scada"])
async def scada_history(
    turbine_id: str,
    range_name: str = Query(default="24H", alias="range"),
    starts_at: datetime | None = Query(default=None, alias="from"),
    ends_at: datetime | None = Query(default=None, alias="to"),
    variable: list[str] | None = Query(default=None),
    points_per_series: int = Query(default=500, ge=10, le=2000),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    if await session.get(Turbine, turbine_id) is None:
        raise NotFoundError(f"turbine {turbine_id} was not found")
    selected_range, window_start, window_end = _normalized_scada_window(
        range_name, starts_at, ends_at
    )
    duration_seconds = max(1, round((window_end - window_start).total_seconds()))
    interval_seconds = max(1, ceil(duration_seconds / points_per_series))
    quality_rank = case(
        (ScadaSample.quality == "bad", 2),
        (ScadaSample.quality == "uncertain", 1),
        else_=0,
    )
    records: list[dict[str, Any]] = []
    filters = [
        ScadaSample.turbine_id == turbine_id,
        ScadaSample.observed_at >= window_start,
        ScadaSample.observed_at <= window_end,
    ]
    if variable:
        filters.append(ScadaSample.variable.in_(variable))
    if settings.is_sqlite:
        samples = list(
            (
                await session.scalars(
                    select(ScadaSample).where(*filters).order_by(ScadaSample.observed_at.asc())
                )
            ).all()
        )
        grouped: dict[tuple[str, str, str, int], dict[str, Any]] = {}
        for sample in samples:
            observed = sample.observed_at
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=UTC)
            bucket_number = max(
                0, int((observed - window_start).total_seconds()) // interval_seconds
            )
            key = (sample.variable, sample.source_id, sample.unit, bucket_number)
            group = grouped.setdefault(
                key,
                {
                    "variable": sample.variable,
                    "source_id": sample.source_id,
                    "unit": sample.unit,
                    "bucket_at": window_start + timedelta(seconds=bucket_number * interval_seconds),
                    "value_sum": 0.0,
                    "value_count": 0,
                    "quality_rank": 0,
                    "late": False,
                },
            )
            group["value_sum"] += sample.value
            group["value_count"] += 1
            group["quality_rank"] = max(
                int(group["quality_rank"]),
                2 if sample.quality == "bad" else 1 if sample.quality == "uncertain" else 0,
            )
            group["late"] = bool(group["late"] or sample.is_late)
        records = [
            {
                **group,
                "value": float(group["value_sum"]) / int(group["value_count"]),
            }
            for group in grouped.values()
        ]
    else:
        bucket = func.time_bucket(
            func.make_interval(0, 0, 0, 0, 0, 0, interval_seconds),
            ScadaSample.observed_at,
        ).label("bucket_at")
        rows = (
            await session.execute(
                select(
                    ScadaSample.variable,
                    ScadaSample.source_id,
                    ScadaSample.unit,
                    bucket,
                    func.avg(ScadaSample.value).label("value"),
                    func.max(quality_rank).label("quality_rank"),
                    func.max(sql_cast(ScadaSample.is_late, Integer)).label("late"),
                )
                .where(*filters)
                .group_by(
                    ScadaSample.variable,
                    ScadaSample.source_id,
                    ScadaSample.unit,
                    bucket,
                )
                .order_by(ScadaSample.variable, bucket)
            )
        ).mappings()
        records = [dict(row) for row in rows]

    source_ids = sorted({str(record["source_id"]) for record in records})
    sources = (
        list(
            (
                await session.scalars(select(IngestSource).where(IngestSource.id.in_(source_ids)))
            ).all()
        )
        if source_ids
        else []
    )
    source_by_id = {source.id: source for source in sources}
    series_records: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        series_records.setdefault((str(record["variable"]), str(record["source_id"])), []).append(
            record
        )

    series: list[dict[str, Any]] = []
    for (variable_name, source_id), point_records in sorted(series_records.items()):
        source = source_by_id.get(source_id)
        raw_contract = (
            source.policy.get("variable_contracts", {}).get(variable_name, {})
            if source is not None
            else {}
        )
        direction = str(raw_contract.get("threshold_direction", "above"))
        thresholds = [
            {
                "id": f"{turbine_id}-{variable_name}-{severity}",
                "label": f"{severity.title()} threshold",
                "value": float(value),
                "direction": direction,
                "severity": severity,
            }
            for severity, value in (
                ("warning", raw_contract.get("warning_threshold")),
                ("critical", raw_contract.get("critical_threshold")),
            )
            if isinstance(value, int | float)
        ]
        points = [
            {
                "timestamp": record["bucket_at"],
                "value": float(record["value"]),
                "quality": _quality_from_rank(int(record["quality_rank"])),
                "late": bool(record["late"]),
                "is_anomaly": any(
                    (
                        float(record["value"]) >= cast(float, threshold["value"])
                        if threshold["direction"] == "above"
                        else float(record["value"]) <= cast(float, threshold["value"])
                    )
                    for threshold in thresholds
                ),
            }
            for record in sorted(point_records, key=lambda item: item["bucket_at"])
        ]
        series.append(
            {
                "series_id": f"{source_id}:{turbine_id}:{variable_name}",
                "source_id": source_id,
                "turbine_id": turbine_id,
                "variable": variable_name,
                "label": str(raw_contract.get("label", variable_name.replace("_", " "))),
                "unit": str(raw_contract.get("unit", point_records[0]["unit"])),
                "precision": int(raw_contract.get("precision", 2)),
                "normal_range": [
                    float(raw_contract.get("normal_min", 0)),
                    float(raw_contract.get("normal_max", 0)),
                ],
                "thresholds": thresholds,
                "points": points,
            }
        )
    return {
        "data": series,
        "meta": {
            "count": len(series),
            "point_count": sum(len(item["points"]) for item in series),
            "turbine_id": turbine_id,
            "range": selected_range,
            "interval_seconds": interval_seconds,
            "starts_at": window_start,
            "ends_at": window_end,
            "snapshot_at": datetime.now(UTC),
            "deterministic": False,
        },
    }


@router.get("/scada/measurements", tags=["scada"])
async def scada_measurements(
    turbine_id: str | None = None,
    variable: str | None = None,
    starts_at: datetime | None = Query(default=None, alias="from"),
    ends_at: datetime | None = Query(default=None, alias="to"),
    offset: int = Query(default=0, ge=0, le=10_000_000),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    if any(value is not None and value.tzinfo is None for value in (starts_at, ends_at)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_SCADA_WINDOW",
                "message": "from and to must include explicit timezones",
            },
        )
    if starts_at is not None and ends_at is not None and starts_at >= ends_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_SCADA_WINDOW", "message": "from must be before to"},
        )
    filters = []
    if turbine_id:
        filters.append(ScadaSample.turbine_id == turbine_id)
    if variable:
        filters.append(ScadaSample.variable == variable)
    if starts_at:
        filters.append(ScadaSample.observed_at >= starts_at)
    if ends_at:
        filters.append(ScadaSample.observed_at <= ends_at)
    total = int(
        await session.scalar(select(func.count()).select_from(ScadaSample).where(*filters)) or 0
    )
    rows = list(
        (
            await session.scalars(
                select(ScadaSample)
                .where(*filters)
                .order_by(ScadaSample.observed_at.desc(), ScadaSample.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    source_rows = (
        list(
            (
                await session.scalars(
                    select(IngestSource).where(IngestSource.id.in_({row.source_id for row in rows}))
                )
            ).all()
        )
        if rows
        else []
    )
    source_by_id = {source.id: source for source in source_rows}

    def measurement_contract(row: ScadaSample) -> dict[str, Any]:
        source = source_by_id.get(row.source_id)
        if source is None:
            return {}
        value = source.policy.get("variable_contracts", {}).get(row.variable, {})
        return value if isinstance(value, dict) else {}

    def measurement_is_anomaly(row: ScadaSample) -> bool:
        contract = measurement_contract(row)
        direction = contract.get("threshold_direction", "above")
        thresholds = [
            value
            for value in (
                contract.get("warning_threshold"),
                contract.get("critical_threshold"),
            )
            if isinstance(value, int | float)
        ]
        return any(
            row.value >= threshold if direction == "above" else row.value <= threshold
            for threshold in thresholds
        )

    return {
        "measurements": [
            {
                "sample_id": row.id,
                "source_event_id": row.source_event_id,
                "source_id": row.source_id,
                "source_sequence": row.source_sequence,
                "turbine_id": row.turbine_id,
                "variable": row.variable,
                "label": str(
                    measurement_contract(row).get("label", row.variable.replace("_", " "))
                ),
                "observed_at": row.observed_at,
                "received_at": row.received_at,
                "value": row.value,
                "unit": row.unit,
                "quality": row.quality,
                "quality_code": row.attributes.get("quality_code"),
                "late": row.is_late,
                "is_anomaly": measurement_is_anomaly(row),
            }
            for row in rows
        ],
        "meta": {
            "total": total,
            "offset": offset,
            "limit": limit,
            "turbine_id": turbine_id,
            "variable": variable,
            "from": starts_at,
            "to": ends_at,
            "snapshot_at": datetime.now(UTC),
        },
    }


@router.get("/turbines/{turbine_id}/scada", tags=["scada"])
async def turbine_scada(
    turbine_id: str,
    variable: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    if await session.get(Turbine, turbine_id) is None:
        raise NotFoundError(f"turbine {turbine_id} was not found")
    samples = await SQLToolAdapter(session).query_scada(turbine_id, variable, limit)
    return {"turbine_id": turbine_id, "count": len(samples), "samples": samples}


@router.get("/scada/sample-count", tags=["scada"])
async def scada_sample_count(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, int]:
    # Small operational endpoint used to verify transport-level idempotency.
    count = int(await session.scalar(select(func.count()).select_from(ScadaSample)) or 0)
    return {"count": count}
