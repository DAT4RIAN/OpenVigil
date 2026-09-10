from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    desc,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    Alarm,
    AssetTwinProfile,
    Decision,
    IngestSource,
    KnowledgeDocument,
    Mission,
    ModelPrediction,
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
from windops_backend.services.operational_contracts import _safe_number

# Operational pages are summaries, not ledger exports.  Keep the default page
# useful while ensuring pathological per-parent fan-out cannot turn one bounded
# page into an unbounded response.  Full ledgers remain available from their
# dedicated mission/work-order APIs.
DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT = 1
DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT = 1
MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT = 1
MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT = 1
DIAGNOSIS_RISK_PRIORITY = ("critical", "high", "medium", "low")


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
