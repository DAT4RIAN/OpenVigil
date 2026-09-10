from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.models import (
    Alarm,
    AssetHealthEvent,
    KnowledgeDocument,
    Mission,
    Turbine,
    WindFarm,
    WorkOrder,
)
from windops_backend.services.operational_views import digital_twin_snapshot


def _document_matches_turbine(document: KnowledgeDocument, turbine_id: str) -> bool:
    metadata = document.metadata_ if isinstance(document.metadata_, dict) else {}
    related = metadata.get("related_turbine_ids", [])
    return metadata.get("turbine_id") == turbine_id or (
        isinstance(related, list) and turbine_id in related
    )


async def asset_detail_snapshot(session: AsyncSession, turbine_id: str) -> dict[str, Any] | None:
    turbine = await session.get(Turbine, turbine_id)
    if turbine is None:
        return None
    farm = await session.get(WindFarm, turbine.wind_farm_id)
    twin = await digital_twin_snapshot(session, turbine_id)
    if twin is None:  # pragma: no cover - guarded by the turbine lookup
        return None
    alarms = list(
        (
            await session.scalars(
                select(Alarm)
                .where(Alarm.turbine_id == turbine_id)
                .order_by(desc(Alarm.triggered_at))
                .limit(100)
            )
        ).all()
    )
    missions = list(
        (
            await session.scalars(
                select(Mission)
                .where(Mission.turbine_id == turbine_id)
                .order_by(desc(Mission.updated_at))
                .limit(100)
            )
        ).all()
    )
    work_orders = list(
        (
            await session.scalars(
                select(WorkOrder)
                .where(WorkOrder.turbine_id == turbine_id)
                .order_by(desc(WorkOrder.updated_at))
                .limit(100)
            )
        ).all()
    )
    health_events = list(
        (
            await session.scalars(
                select(AssetHealthEvent)
                .where(AssetHealthEvent.turbine_id == turbine_id)
                .order_by(desc(AssetHealthEvent.recorded_at))
                .limit(100)
            )
        ).all()
    )
    document_candidates = list(
        (
            await session.scalars(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.ingestion_status == "indexed")
                .order_by(desc(KnowledgeDocument.updated_at))
                .limit(500)
            )
        ).all()
    )
    documents = [
        document
        for document in document_candidates
        if _document_matches_turbine(document, turbine_id)
    ][:100]
    return {
        "asset": {
            **twin["turbine"],
            "windFarmId": turbine.wind_farm_id,
            "windFarmName": farm.name if farm is not None else None,
            "updatedAt": turbine.updated_at,
        },
        "telemetry": twin["signals"],
        "healthEvents": [
            {
                "id": row.id,
                "score": row.score,
                "status": row.status,
                "reason": row.reason,
                "missionId": row.mission_id,
                "recordedAt": row.recorded_at,
            }
            for row in health_events
        ],
        "alarms": [
            {
                "id": row.id,
                "code": row.code,
                "subsystem": row.subsystem,
                "title": row.title,
                "severity": row.severity,
                "status": row.status,
                "triggeredAt": row.triggered_at,
            }
            for row in alarms
        ],
        "missions": [
            {
                "id": row.id,
                "title": row.title,
                "status": row.status,
                "revision": row.revision,
                "updatedAt": row.updated_at,
            }
            for row in missions
        ],
        "workOrders": [
            {
                "id": row.id,
                "title": row.title,
                "status": row.status,
                "priority": row.priority,
                "assignedTeam": row.assigned_team,
                "plannedStart": row.planned_start,
                "deadline": row.deadline,
                "updatedAt": row.updated_at,
            }
            for row in work_orders
        ],
        "documents": [
            {
                "id": row.id,
                "title": row.title,
                "type": row.document_type,
                "version": row.document_version,
                "citationUri": row.citation_uri,
                "artifactSha256": row.artifact_sha256,
                "vectorized": row.vectorized,
                "updatedAt": row.updated_at,
            }
            for row in documents
        ],
        "context": twin["context"],
        "twinProfile": twin["model"],
        "snapshotAt": twin["snapshotAt"],
    }
