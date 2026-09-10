import hashlib
import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.config import TelemetrySourcePolicy
from windops_backend.enums import AlarmSeverity, MissionStatus, TurbineStatus
from windops_backend.errors import IdempotencyConflictError, NotFoundError
from windops_backend.models import (
    Alarm,
    AssetHealthEvent,
    IngestReceipt,
    IngestSource,
    IngestStreamState,
    Mission,
    QuarantinedScadaSample,
    ScadaSample,
    Turbine,
)
from windops_backend.outbox import enqueue_knowledge_graph_projection, enqueue_mission_analysis
from windops_backend.schemas import IngestResult, ScadaSampleIn
from windops_backend.services.events import append_domain_event


class _BatchIngestFallback(RuntimeError):
    """Retry a batch through the fully general per-sample path."""


def _payload_hash(sample: ScadaSampleIn, source_id: str) -> str:
    encoded = json.dumps(
        {"source_id": source_id, "sample": sample.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_main_bearing_anomaly(sample: ScadaSampleIn) -> bool:
    raw_anomaly_score = sample.attributes.get("anomaly_score", 0)
    if isinstance(raw_anomaly_score, bool):
        anomaly_score = 0.0
    else:
        try:
            anomaly_score = float(raw_anomaly_score)
        except (TypeError, ValueError):
            anomaly_score = 0.0
    if not math.isfinite(anomaly_score):
        anomaly_score = 0.0
    return (
        sample.quality == "good"
        and sample.variable == "main_bearing_vibration_rms"
        and (sample.value >= 4.5 or anomaly_score >= 0.8)
    )


async def ensure_ingest_source(
    session: AsyncSession,
    source_id: str,
    policy: TelemetrySourcePolicy,
) -> IngestSource:
    source = await session.get(IngestSource, source_id)
    policy_document = policy.model_dump(mode="json")
    now = datetime.now(UTC)
    if source is None:
        values = {
            "id": source_id,
            "display_name": policy.display_name,
            "source_kind": policy.source_kind,
            "enabled": policy.enabled,
            "policy": policy_document,
            "updated_at": now,
        }
        bind = session.bind
        dialect = bind.dialect.name if bind is not None else "unknown"
        if dialect == "postgresql":
            await session.execute(
                postgres_insert(IngestSource)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[IngestSource.id])
            )
            source = await session.get(IngestSource, source_id)
        elif dialect == "sqlite":
            await session.execute(
                sqlite_insert(IngestSource)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[IngestSource.id])
            )
            source = await session.get(IngestSource, source_id)
        else:
            source = IngestSource(**values)
            session.add(source)
            await session.flush()
            return source
        if source is None:  # pragma: no cover - the insert violated its own contract
            raise RuntimeError(f"failed to initialize ingest source {source_id}")
        return source
    source.display_name = policy.display_name
    source.source_kind = policy.source_kind
    source.enabled = policy.enabled
    source.policy = policy_document
    source.updated_at = now
    return source


async def _stream_state(
    session: AsyncSession,
    source_id: str,
    stream_key: str,
) -> IngestStreamState:
    state = await session.get(
        IngestStreamState,
        {"source_id": source_id, "stream_key": stream_key},
        with_for_update=True,
    )
    if state is None:
        values = {"source_id": source_id, "stream_key": stream_key}
        bind = session.bind
        dialect = bind.dialect.name if bind is not None else "unknown"
        if dialect == "postgresql":
            await session.execute(
                postgres_insert(IngestStreamState)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[IngestStreamState.source_id, IngestStreamState.stream_key]
                )
            )
        elif dialect == "sqlite":
            await session.execute(
                sqlite_insert(IngestStreamState)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[IngestStreamState.source_id, IngestStreamState.stream_key]
                )
            )
        else:
            state = IngestStreamState(**values)
            session.add(state)
            await session.flush()
            return state
        state = await session.get(
            IngestStreamState,
            {"source_id": source_id, "stream_key": stream_key},
            with_for_update=True,
        )
        if state is None:  # pragma: no cover - the insert violated its own contract
            raise RuntimeError(f"failed to initialize ingest stream {source_id}/{stream_key}")
    return state


def _quarantine_reason(
    sample: ScadaSampleIn,
    policy: TelemetrySourcePolicy,
    state: IngestStreamState,
    received_at: datetime,
) -> str | None:
    observed_at = _as_utc(sample.observed_at)
    watermark = (
        _as_utc(state.watermark_observed_at) if state.watermark_observed_at is not None else None
    )
    if not policy.enabled:
        return "source_disabled"
    if policy.allowed_turbines and sample.turbine_id not in policy.allowed_turbines:
        return "turbine_not_allowed"
    allowed_variables = set(policy.allowed_variables) or set(policy.variable_contracts)
    if allowed_variables and sample.variable not in allowed_variables:
        return "variable_not_allowed"
    variable_contract = policy.variable_contracts.get(sample.variable)
    if variable_contract is not None and sample.unit != variable_contract.unit:
        return "unit_mismatch"
    if policy.sequence_required and sample.source_sequence is None:
        return "source_sequence_required"
    if observed_at > received_at + timedelta(seconds=policy.max_future_skew_seconds):
        return "future_observation"
    if watermark is not None and observed_at < watermark - timedelta(
        seconds=policy.max_lateness_seconds
    ):
        return "beyond_lateness_window"
    if (
        sample.source_sequence is not None
        and state.highest_sequence is not None
        and sample.source_sequence == state.highest_sequence
    ):
        return "source_sequence_reused"
    return None


async def _record_quarantine(
    session: AsyncSession,
    *,
    source: IngestSource,
    state: IngestStreamState,
    receipt: IngestReceipt,
    sample: ScadaSampleIn,
    stream_key: str,
    reason_code: str,
    received_at: datetime,
) -> IngestResult:
    receipt.disposition = "quarantined"
    source.status = "degraded"
    source.last_seen_at = received_at
    source.updated_at = received_at
    state.quarantined_count += 1
    state.updated_at = received_at
    session.add(
        QuarantinedScadaSample(
            id=str(uuid4()),
            source_event_id=sample.source_event_id,
            source_id=source.id,
            stream_key=stream_key,
            reason_code=reason_code,
            observed_at=sample.observed_at,
            received_at=received_at,
            payload=sample.model_dump(mode="json"),
        )
    )
    append_domain_event(
        session,
        event_type="scada.sample.quarantined",
        aggregate_type="ingest_source",
        aggregate_id=source.id,
        payload={
            "source_event_id": sample.source_event_id,
            "stream_key": stream_key,
            "reason_code": reason_code,
            "observed_at": sample.observed_at.isoformat(),
        },
    )
    await session.flush()
    return IngestResult(
        source_event_id=sample.source_event_id,
        disposition="quarantined",
        reason_code=reason_code,
    )


async def ingest_sample(
    session: AsyncSession,
    sample: ScadaSampleIn,
    *,
    source_id: str = "scada-default",
    policy: TelemetrySourcePolicy | None = None,
) -> IngestResult:
    turbine = await session.get(Turbine, sample.turbine_id)
    if turbine is None:
        raise NotFoundError(f"turbine {sample.turbine_id} was not found")

    resolved_policy = policy or TelemetrySourcePolicy(
        display_name="Default normalized SCADA source",
        source_kind="rest",
        sequence_required=False,
    )
    source = await ensure_ingest_source(session, source_id, resolved_policy)
    payload_hash = _payload_hash(sample, source_id)
    receipt = IngestReceipt(
        source_event_id=sample.source_event_id,
        source_id=source_id,
        payload_hash=payload_hash,
    )
    try:
        async with session.begin_nested():
            session.add(receipt)
            await session.flush()
    except IntegrityError as exc:
        existing = await session.get(IngestReceipt, sample.source_event_id)
        if existing is None:  # pragma: no cover - database violated its own constraint
            raise
        if existing.payload_hash != payload_hash or existing.source_id != source_id:
            raise IdempotencyConflictError(
                f"source_event_id {sample.source_event_id} was already used for another payload"
            ) from exc
        state = await session.get(
            IngestStreamState,
            {"source_id": source_id, "stream_key": f"{sample.turbine_id}:{sample.variable}"},
            with_for_update=True,
        )
        if state is not None:
            state.duplicate_count += 1
            state.updated_at = datetime.now(UTC)
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
            reason_code=(
                "originally_quarantined" if existing.disposition == "quarantined" else None
            ),
            alarm_id=alarm.id if alarm else None,
            mission_id=mission_id,
        )

    received_at = datetime.now(UTC)
    stream_key = f"{sample.turbine_id}:{sample.variable}"
    state = await _stream_state(session, source_id, stream_key)
    reason = _quarantine_reason(sample, resolved_policy, state, received_at)
    if reason is not None:
        return await _record_quarantine(
            session,
            source=source,
            state=state,
            receipt=receipt,
            sample=sample,
            stream_key=stream_key,
            reason_code=reason,
            received_at=received_at,
        )

    watermark = (
        _as_utc(state.watermark_observed_at) if state.watermark_observed_at is not None else None
    )
    observed_at = _as_utc(sample.observed_at)
    is_late = bool(
        (watermark is not None and observed_at < watermark)
        or (
            sample.source_sequence is not None
            and state.highest_sequence is not None
            and sample.source_sequence < state.highest_sequence
        )
    )
    session.add(
        ScadaSample(
            id=str(uuid4()),
            observed_at=sample.observed_at,
            source_event_id=sample.source_event_id,
            source_id=source_id,
            source_sequence=sample.source_sequence,
            received_at=received_at,
            is_late=is_late,
            turbine_id=sample.turbine_id,
            variable=sample.variable,
            value=sample.value,
            unit=sample.unit,
            quality=sample.quality,
            attributes={**sample.attributes, "quality_code": sample.quality_code},
        )
    )
    receipt.disposition = "accepted"
    source.status = "degraded" if sample.quality != "good" or is_late else "healthy"
    source.last_seen_at = received_at
    source.updated_at = received_at
    state.accepted_count += 1
    state.late_count += int(is_late)
    state.updated_at = received_at
    if watermark is None or observed_at > watermark:
        state.watermark_observed_at = sample.observed_at
    if sample.source_sequence is not None and (
        state.highest_sequence is None or sample.source_sequence > state.highest_sequence
    ):
        state.highest_sequence = sample.source_sequence
    append_domain_event(
        session,
        event_type="scada.sample.accepted",
        aggregate_type="turbine",
        aggregate_id=sample.turbine_id,
        payload={
            "source_event_id": sample.source_event_id,
            "source_id": source_id,
            "source_sequence": sample.source_sequence,
            "turbine_id": sample.turbine_id,
            "variable": sample.variable,
            "value": sample.value,
            "unit": sample.unit,
            "quality": sample.quality,
            "quality_code": sample.quality_code,
            "observed_at": sample.observed_at.isoformat(),
            "received_at": received_at.isoformat(),
            "late": is_late,
        },
    )
    await session.flush()
    if not _is_main_bearing_anomaly(sample):
        return IngestResult(
            source_event_id=sample.source_event_id,
            disposition="accepted",
            late=is_late,
        )

    alarm_id = f"ALARM-{uuid4().hex[:12].upper()}"
    mission_id = f"MISSION-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:6].upper()}"
    alarm = Alarm(
        id=alarm_id,
        turbine_id=sample.turbine_id,
        source_event_id=sample.source_event_id,
        code="MB-VIB-RMS-HIGH",
        subsystem="main_bearing",
        title=f"{sample.turbine_id} main-bearing vibration RMS sustained high",
        severity=AlarmSeverity.MAJOR.value,
        triggered_at=sample.observed_at,
        evidence={
            "variable": sample.variable,
            "value": sample.value,
            "unit": sample.unit,
            "quality": sample.quality,
            "quality_code": sample.quality_code,
            "source_id": source_id,
            "source_event_id": sample.source_event_id,
            "attributes": sample.attributes,
        },
    )
    mission = Mission(
        id=mission_id,
        alarm_id=alarm_id,
        turbine_id=sample.turbine_id,
        title=f"{sample.turbine_id} Main Bearing Anomaly",
        status=MissionStatus.DETECTED.value,
        public_state={
            "analysis_profile": {
                "component": "main_bearing",
                "primary_variable": "main_bearing_vibration_rms",
                "related_variables": ["main_bearing_temperature", "active_power"],
                "failure_mode_hint": "main-bearing degradation",
                "knowledge_query": "main bearing rising RMS temperature inspection",
            }
        },
    )
    session.add_all([alarm, mission])
    enqueue_mission_analysis(session, mission_id)
    enqueue_knowledge_graph_projection(
        session,
        aggregate_type="alarm",
        aggregate_id=alarm_id,
        reason="anomaly-ingested",
    )
    append_domain_event(
        session,
        event_type="alarm.opened",
        aggregate_type="alarm",
        aggregate_id=alarm_id,
        payload={
            "alarm_id": alarm_id,
            "mission_id": mission_id,
            "turbine_id": sample.turbine_id,
            "code": alarm.code,
            "severity": alarm.severity,
            "triggered_at": sample.observed_at.isoformat(),
        },
    )
    append_domain_event(
        session,
        event_type="mission.detected",
        aggregate_type="mission",
        aggregate_id=mission_id,
        payload={
            "mission_id": mission_id,
            "alarm_id": alarm_id,
            "turbine_id": sample.turbine_id,
            "status": MissionStatus.DETECTED.value,
        },
    )
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
        late=is_late,
        alarm_id=alarm_id,
        mission_id=mission_id,
    )


async def _ingest_postgres_accepted_batch(
    session: AsyncSession,
    samples: Sequence[ScadaSampleIn],
    *,
    source_id: str,
    policy: TelemetrySourcePolicy,
) -> list[IngestResult]:
    """Persist an all-accepted PostgreSQL batch with bounded database round trips.

    Receipt conflicts, quarantines, and direct alarm-producing samples deliberately
    fall back to ``ingest_sample`` so their established edge-case behavior remains
    unchanged. The savepoint rolls back every speculative batch mutation first.
    """

    turbine_ids = {sample.turbine_id for sample in samples}
    existing_turbines = set(
        (await session.scalars(select(Turbine.id).where(Turbine.id.in_(turbine_ids)))).all()
    )
    for sample in samples:
        if sample.turbine_id not in existing_turbines:
            raise NotFoundError(f"turbine {sample.turbine_id} was not found")

    source = await ensure_ingest_source(session, source_id, policy)
    stream_keys = sorted({f"{sample.turbine_id}:{sample.variable}" for sample in samples})

    try:
        async with session.begin_nested():
            await session.execute(
                postgres_insert(IngestStreamState)
                .values(
                    [
                        {"source_id": source_id, "stream_key": stream_key}
                        for stream_key in stream_keys
                    ]
                )
                .on_conflict_do_nothing(
                    index_elements=[IngestStreamState.source_id, IngestStreamState.stream_key]
                )
            )
            states = {
                state.stream_key: state
                for state in (
                    await session.scalars(
                        select(IngestStreamState)
                        .where(
                            IngestStreamState.source_id == source_id,
                            IngestStreamState.stream_key.in_(stream_keys),
                        )
                        .order_by(IngestStreamState.stream_key)
                        .with_for_update()
                    )
                ).all()
            }
            if len(states) != len(stream_keys):  # pragma: no cover - database contract breach
                raise RuntimeError("failed to initialize every ingest stream in the batch")

            received_at = datetime.now(UTC)
            prepared: list[tuple[ScadaSampleIn, IngestStreamState, bool]] = []
            for sample in samples:
                stream_key = f"{sample.turbine_id}:{sample.variable}"
                state = states[stream_key]
                reason = _quarantine_reason(sample, policy, state, received_at)
                if reason is not None:
                    raise _BatchIngestFallback(reason)

                watermark = (
                    _as_utc(state.watermark_observed_at)
                    if state.watermark_observed_at is not None
                    else None
                )
                observed_at = _as_utc(sample.observed_at)
                is_late = bool(
                    (watermark is not None and observed_at < watermark)
                    or (
                        sample.source_sequence is not None
                        and state.highest_sequence is not None
                        and sample.source_sequence < state.highest_sequence
                    )
                )
                state.accepted_count += 1
                state.late_count += int(is_late)
                state.updated_at = received_at
                if watermark is None or observed_at > watermark:
                    state.watermark_observed_at = sample.observed_at
                if sample.source_sequence is not None and (
                    state.highest_sequence is None
                    or sample.source_sequence > state.highest_sequence
                ):
                    state.highest_sequence = sample.source_sequence
                prepared.append((sample, state, is_late))

            receipt_values = [
                {
                    "source_event_id": sample.source_event_id,
                    "source_id": source_id,
                    "payload_hash": _payload_hash(sample, source_id),
                    "disposition": "accepted",
                    "received_at": received_at,
                }
                for sample in samples
            ]
            inserted_receipt_ids = set(
                (
                    await session.scalars(
                        postgres_insert(IngestReceipt)
                        .values(receipt_values)
                        .on_conflict_do_nothing(index_elements=[IngestReceipt.source_event_id])
                        .returning(IngestReceipt.source_event_id)
                    )
                ).all()
            )
            if inserted_receipt_ids != {sample.source_event_id for sample in samples}:
                raise _BatchIngestFallback("receipt conflict")

            for sample, _state, is_late in prepared:
                session.add(
                    ScadaSample(
                        id=str(uuid4()),
                        observed_at=sample.observed_at,
                        source_event_id=sample.source_event_id,
                        source_id=source_id,
                        source_sequence=sample.source_sequence,
                        received_at=received_at,
                        is_late=is_late,
                        turbine_id=sample.turbine_id,
                        variable=sample.variable,
                        value=sample.value,
                        unit=sample.unit,
                        quality=sample.quality,
                        attributes={**sample.attributes, "quality_code": sample.quality_code},
                    )
                )
                append_domain_event(
                    session,
                    event_type="scada.sample.accepted",
                    aggregate_type="turbine",
                    aggregate_id=sample.turbine_id,
                    payload={
                        "source_event_id": sample.source_event_id,
                        "source_id": source_id,
                        "source_sequence": sample.source_sequence,
                        "turbine_id": sample.turbine_id,
                        "variable": sample.variable,
                        "value": sample.value,
                        "unit": sample.unit,
                        "quality": sample.quality,
                        "quality_code": sample.quality_code,
                        "observed_at": sample.observed_at.isoformat(),
                        "received_at": received_at.isoformat(),
                        "late": is_late,
                    },
                )

            last_sample, _last_state, last_is_late = prepared[-1]
            source.status = (
                "degraded" if last_sample.quality != "good" or last_is_late else "healthy"
            )
            source.last_seen_at = received_at
            source.updated_at = received_at
            await session.flush()
            return [
                IngestResult(
                    source_event_id=sample.source_event_id,
                    disposition="accepted",
                    late=is_late,
                )
                for sample, _state, is_late in prepared
            ]
    except _BatchIngestFallback:
        return [
            await ingest_sample(
                session,
                sample,
                source_id=source_id,
                policy=policy,
            )
            for sample in samples
        ]


async def ingest_samples(
    session: AsyncSession,
    samples: Sequence[ScadaSampleIn],
    *,
    source_id: str = "scada-default",
    policy: TelemetrySourcePolicy | None = None,
) -> list[IngestResult]:
    """Ingest a request batch while preserving the single-sample contract."""

    resolved_policy = policy or TelemetrySourcePolicy(
        display_name="Default normalized SCADA source",
        source_kind="rest",
        sequence_required=False,
    )
    bind = session.bind
    dialect = bind.dialect.name if bind is not None else "unknown"
    source_event_ids = [sample.source_event_id for sample in samples]
    can_batch = (
        dialect == "postgresql"
        and len(samples) > 1
        and len(set(source_event_ids)) == len(source_event_ids)
        and not any(_is_main_bearing_anomaly(sample) for sample in samples)
    )
    if can_batch:
        return await _ingest_postgres_accepted_batch(
            session,
            samples,
            source_id=source_id,
            policy=resolved_policy,
        )
    return [
        await ingest_sample(
            session,
            sample,
            source_id=source_id,
            policy=resolved_policy,
        )
        for sample in samples
    ]
