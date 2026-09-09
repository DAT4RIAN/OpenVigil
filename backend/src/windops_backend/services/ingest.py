import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.enums import AlarmSeverity, MissionStatus, TurbineStatus
from windops_backend.errors import IdempotencyConflictError, NotFoundError
from windops_backend.models import (
    Alarm,
    AssetHealthEvent,
    IngestReceipt,
    Mission,
    ScadaSample,
    Turbine,
)
from windops_backend.outbox import enqueue_mission_analysis
from windops_backend.schemas import IngestResult, ScadaSampleIn


def _payload_hash(sample: ScadaSampleIn) -> str:
    encoded = json.dumps(
        sample.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _is_main_bearing_anomaly(sample: ScadaSampleIn) -> bool:
    return (
        sample.quality == "good"
        and sample.variable == "main_bearing_vibration_rms"
        and (sample.value >= 4.5 or float(sample.attributes.get("anomaly_score", 0)) >= 0.8)
    )


async def ingest_sample(session: AsyncSession, sample: ScadaSampleIn) -> IngestResult:
    turbine = await session.get(Turbine, sample.turbine_id)
    if turbine is None:
        raise NotFoundError(f"turbine {sample.turbine_id} was not found")

    payload_hash = _payload_hash(sample)
    receipt = IngestReceipt(source_event_id=sample.source_event_id, payload_hash=payload_hash)
    try:
        async with session.begin_nested():
            session.add(receipt)
            await session.flush()
    except IntegrityError as exc:
        existing = await session.get(IngestReceipt, sample.source_event_id)
        if existing is None:  # pragma: no cover - database violated its own constraint
            raise
        if existing.payload_hash != payload_hash:
            raise IdempotencyConflictError(
                f"source_event_id {sample.source_event_id} was already used for another payload"
            ) from exc
        alarm = await session.scalar(
            select(Alarm).where(Alarm.source_event_id == sample.source_event_id)
        )
        mission_id = None
        if alarm is not None:
            mission_id = await session.scalar(
                select(Mission.id).where(Mission.alarm_id == alarm.id)
            )
        return IngestResult(
            source_event_id=sample.source_event_id,
            disposition="duplicate",
            alarm_id=alarm.id if alarm else None,
            mission_id=mission_id,
        )

    session.add(
        ScadaSample(
            id=str(uuid4()),
            observed_at=sample.observed_at,
            source_event_id=sample.source_event_id,
            turbine_id=sample.turbine_id,
            variable=sample.variable,
            value=sample.value,
            unit=sample.unit,
            quality=sample.quality,
            attributes=sample.attributes,
        )
    )
    await session.flush()
    if not _is_main_bearing_anomaly(sample):
        return IngestResult(source_event_id=sample.source_event_id, disposition="accepted")

    alarm_id = f"ALARM-{uuid4().hex[:12].upper()}"
    mission_id = f"MISSION-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:6].upper()}"
    alarm = Alarm(
        id=alarm_id,
        turbine_id=sample.turbine_id,
        source_event_id=sample.source_event_id,
        code="MB-VIB-RMS-HIGH",
        subsystem="main_bearing",
        title="WT-023 main-bearing vibration RMS sustained high",
        severity=AlarmSeverity.MAJOR.value,
        triggered_at=sample.observed_at,
        evidence={
            "variable": sample.variable,
            "value": sample.value,
            "unit": sample.unit,
            "attributes": sample.attributes,
        },
    )
    mission = Mission(
        id=mission_id,
        alarm_id=alarm_id,
        turbine_id=sample.turbine_id,
        title="WT-023 Main Bearing Anomaly",
        status=MissionStatus.DETECTED.value,
        public_state={},
    )
    session.add_all([alarm, mission])
    enqueue_mission_analysis(session, mission_id)
    turbine.status = TurbineStatus.WARNING.value
    turbine.health_score = 68
    turbine.updated_at = datetime.now(UTC)
    session.add(
        AssetHealthEvent(
            id=str(uuid4()),
            turbine_id=sample.turbine_id,
            mission_id=mission_id,
            score=68,
            status=TurbineStatus.WARNING.value,
            reason="main-bearing vibration anomaly opened an active mission",
        )
    )
    await session.flush()
    return IngestResult(
        source_event_id=sample.source_event_id,
        disposition="accepted",
        alarm_id=alarm_id,
        mission_id=mission_id,
    )
