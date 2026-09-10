from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.models import (
    AgentDefinition,
    AgentExecution,
    Alarm,
    DomainEvent,
    Mission,
    ScadaSample,
    Turbine,
    WindFarm,
)

_ACTIVE_MISSION_STATES = {
    "detected",
    "investigating",
    "diagnosed",
    "decision_pending",
    "decision-pending",
    "under_review",
    "under-review",
    "approved",
    "executing",
}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def dashboard_snapshot(
    session: AsyncSession,
    *,
    expose_global_sequence: bool = True,
) -> dict[str, Any]:
    snapshot_at = datetime.now(UTC)
    window_started_at = snapshot_at - timedelta(hours=24)
    farm = await session.scalar(select(WindFarm).order_by(WindFarm.id).limit(1))
    turbines = list((await session.scalars(select(Turbine).order_by(Turbine.id))).all())
    turbine_ids = [row.id for row in turbines]
    samples = (
        list(
            (
                await session.scalars(
                    select(ScadaSample)
                    .where(
                        ScadaSample.turbine_id.in_(turbine_ids),
                        ScadaSample.variable.in_(["active_power", "availability_percent"]),
                        ScadaSample.observed_at >= window_started_at,
                        ScadaSample.quality != "bad",
                    )
                    .order_by(ScadaSample.observed_at)
                )
            ).all()
        )
        if turbine_ids
        else []
    )
    alarms = list(
        (
            await session.scalars(
                select(Alarm)
                .where(Alarm.status != "resolved")
                .order_by(desc(Alarm.triggered_at))
                .limit(20)
            )
        ).all()
    )
    open_alarm_count = int(
        await session.scalar(
            select(func.count()).select_from(Alarm).where(Alarm.status != "resolved")
        )
        or 0
    )
    high_priority_alarm_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Alarm)
            .where(
                Alarm.status != "resolved",
                Alarm.severity.in_(["critical", "major"]),
            )
        )
        or 0
    )
    active_mission_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Mission)
            .where(Mission.status.in_(_ACTIVE_MISSION_STATES))
        )
        or 0
    )
    missions = list(
        (await session.scalars(select(Mission).order_by(desc(Mission.updated_at)).limit(50))).all()
    )
    agent_executions = list(
        (
            await session.scalars(
                select(AgentExecution)
                .where(AgentExecution.started_at >= window_started_at)
                .order_by(desc(AgentExecution.started_at))
            )
        ).all()
    )
    active_agent_count = len(
        (
            await session.scalars(
                select(AgentDefinition.agent_key).where(AgentDefinition.active.is_(True)).distinct()
            )
        ).all()
    )
    events = list(
        (
            await session.scalars(
                select(DomainEvent).order_by(desc(DomainEvent.sequence)).limit(20)
            )
        ).all()
    )

    latest_signals: dict[tuple[str, str], ScadaSample] = {}
    power_by_bucket: dict[datetime, dict[str, float]] = defaultdict(dict)
    for sample in samples:
        latest_signals[(sample.turbine_id, sample.variable)] = sample
        if sample.variable != "active_power":
            continue
        observed_at = _utc(sample.observed_at)
        bucket = observed_at.replace(
            minute=(observed_at.minute // 15) * 15,
            second=0,
            microsecond=0,
        )
        power_by_bucket[bucket][sample.turbine_id] = float(sample.value)

    power_trend = [
        {
            "timestamp": bucket,
            "power_mw": round(sum(asset_values.values()), 4),
            "asset_count": len(asset_values),
        }
        for bucket, asset_values in sorted(power_by_bucket.items())
    ]
    current_power_mw = sum(
        float(sample.value)
        for (turbine_id, variable), sample in latest_signals.items()
        if turbine_id in turbine_ids and variable == "active_power"
    )
    availability_values = [
        float(sample.value)
        for (_, variable), sample in latest_signals.items()
        if variable == "availability_percent"
    ]
    latest_observed_at = max(
        (_utc(sample.observed_at) for sample in latest_signals.values()),
        default=None,
    )
    energy_24h_gwh = (
        round(
            sum(sum(asset_values.values()) * 0.25 for asset_values in power_by_bucket.values())
            / 1000,
            6,
        )
        if len(power_trend) >= 2
        else None
    )
    status_counts: dict[str, int] = defaultdict(int)
    for turbine in turbines:
        status_counts[turbine.status] += 1
    active_missions = [row for row in missions if row.status in _ACTIVE_MISSION_STATES]
    severity_weight = {"critical": 4, "major": 3, "minor": 2, "warning": 1}
    alarms.sort(
        key=lambda row: (severity_weight.get(row.severity, 0), _utc(row.triggered_at)),
        reverse=True,
    )
    return {
        "snapshot_at": snapshot_at,
        "window_started_at": window_started_at,
        "source": "postgresql-timescaledb-domain-events",
        "farm": (
            {
                "id": farm.id,
                "name": farm.name,
                "capacity_mw": farm.capacity_mw,
            }
            if farm is not None
            else None
        ),
        "fleet": {
            "asset_count": len(turbines),
            "status_counts": dict(status_counts),
            "operating_count": sum(
                count
                for status, count in status_counts.items()
                if status not in {"maintenance", "offline", "communication-lost"}
            ),
            "average_health_score": (
                round(sum(row.health_score for row in turbines) / len(turbines), 2)
                if turbines
                else None
            ),
            "current_power_mw": round(current_power_mw, 4),
            "energy_24h_gwh": energy_24h_gwh,
            "energy_coverage_percent": round(min(len(power_trend) / 96, 1) * 100, 2),
            "average_availability_percent": (
                round(sum(availability_values) / len(availability_values), 2)
                if availability_values
                else None
            ),
            "telemetry_asset_count": len(
                {
                    turbine_id
                    for turbine_id, variable in latest_signals
                    if variable == "active_power"
                }
            ),
            "latest_telemetry_at": latest_observed_at,
            "open_alarm_count": open_alarm_count,
            "high_priority_alarm_count": high_priority_alarm_count,
            "active_mission_count": active_mission_count,
        },
        "power_trend": power_trend,
        "alarms": [
            {
                "id": row.id,
                "turbine_id": row.turbine_id,
                "code": row.code,
                "title": row.title,
                "severity": row.severity,
                "status": row.status,
                "triggered_at": row.triggered_at,
            }
            for row in alarms[:6]
        ],
        "missions": [
            {
                "id": row.id,
                "turbine_id": row.turbine_id,
                "title": row.title,
                "status": row.status,
                "revision": row.revision,
                "updated_at": row.updated_at,
            }
            for row in active_missions[:6]
        ],
        "agents": {
            "active_definition_count": active_agent_count,
            "execution_count_24h": len(agent_executions),
            "succeeded_24h": sum(row.status == "succeeded" for row in agent_executions),
            "failed_24h": sum(row.status == "failed" for row in agent_executions),
        },
        "activity": [
            {
                "sequence": row.sequence if expose_global_sequence else row.id,
                "event_type": row.event_type,
                "aggregate_type": row.aggregate_type,
                "aggregate_id": row.aggregate_id,
                "occurred_at": row.occurred_at,
                "summary": str(
                    row.payload.get("summary")
                    or row.payload.get("reason")
                    or row.payload.get("status")
                    or row.event_type
                ),
            }
            for row in events[:8]
        ],
    }
