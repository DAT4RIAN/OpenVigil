from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.enums import MissionStatus
from windops_backend.errors import DomainError, IdempotencyConflictError, NotFoundError
from windops_backend.models import Alarm, CommandReceipt, Mission, Turbine
from windops_backend.outbox import enqueue_knowledge_graph_projection, enqueue_mission_analysis
from windops_backend.schemas import MissionCreateRequest
from windops_backend.services.events import append_domain_event

CREATE_MISSION_COMMAND = "mission.create.v1"


class AlarmAlreadyAssignedError(DomainError):
    code = "ALARM_ALREADY_ASSIGNED"
    status_code = 409


def _request_hash(payload: MissionCreateRequest) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


async def _replay_receipt(
    session: AsyncSession,
    *,
    idempotency_key: str,
    request_hash: str,
    subject: str,
    target: str,
) -> dict[str, Any] | None:
    receipt = await session.scalar(
        select(CommandReceipt).where(
            CommandReceipt.command_type == CREATE_MISSION_COMMAND,
            CommandReceipt.subject == subject,
            CommandReceipt.target == target,
            CommandReceipt.idempotency_key == idempotency_key,
        )
    )
    if receipt is None:
        return None
    if receipt.request_hash != request_hash:
        raise IdempotencyConflictError(
            "the idempotency key was already used for a different mission command"
        )
    receipt.replay_count += 1
    receipt.last_replayed_at = datetime.now(UTC)
    await session.flush()
    return dict(receipt.response_body)


async def create_mission(
    session: AsyncSession,
    payload: MissionCreateRequest,
    *,
    idempotency_key: str,
    subject: str,
) -> tuple[dict[str, Any], bool]:
    """Create a mission and its analysis event in one transaction-safe operation."""

    normalized_key = idempotency_key.strip()
    if not 8 <= len(normalized_key) <= 128:
        raise DomainError("Idempotency-Key must contain between 8 and 128 characters")
    payload_hash = _request_hash(payload)
    target = payload.alarm_id
    replay = await _replay_receipt(
        session,
        idempotency_key=normalized_key,
        request_hash=payload_hash,
        subject=subject,
        target=target,
    )
    if replay is not None:
        return replay, True

    alarm = await session.scalar(
        select(Alarm).where(Alarm.id == payload.alarm_id).with_for_update()
    )
    if alarm is None:
        raise NotFoundError(f"alarm {payload.alarm_id} was not found")
    turbine = await session.get(Turbine, alarm.turbine_id)
    if turbine is None:  # pragma: no cover - protected by the database foreign key
        raise NotFoundError(f"turbine {alarm.turbine_id} was not found")
    existing_mission = await session.scalar(select(Mission).where(Mission.alarm_id == alarm.id))
    if existing_mission is not None:
        raise AlarmAlreadyAssignedError(
            f"alarm {alarm.id} is already assigned to mission {existing_mission.id}"
        )

    mission_id = f"MISSION-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:10].upper()}"
    analysis_profile = payload.analysis_profile.model_dump(mode="json", exclude_none=True)
    response = {
        "mission_id": mission_id,
        "alarm_id": alarm.id,
        "turbine_id": alarm.turbine_id,
        "title": payload.title,
        "status": MissionStatus.DETECTED.value,
        "revision": 1,
        "analysis_profile": analysis_profile,
    }
    try:
        async with session.begin_nested():
            session.add(
                Mission(
                    id=mission_id,
                    alarm_id=alarm.id,
                    turbine_id=alarm.turbine_id,
                    title=payload.title,
                    status=MissionStatus.DETECTED.value,
                    public_state={
                        "analysis_profile": analysis_profile,
                        "created_by": subject,
                    },
                )
            )
            alarm.ai_status = "queued"
            enqueue_mission_analysis(session, mission_id)
            enqueue_knowledge_graph_projection(
                session,
                aggregate_type="mission",
                aggregate_id=mission_id,
                reason="mission-created",
            )
            append_domain_event(
                session,
                event_type="mission.created",
                aggregate_type="mission",
                aggregate_id=mission_id,
                payload={
                    "mission_id": mission_id,
                    "alarm_id": alarm.id,
                    "turbine_id": alarm.turbine_id,
                    "status": MissionStatus.DETECTED.value,
                    "created_by": subject,
                },
            )
            session.add(
                CommandReceipt(
                    id=str(uuid4()),
                    command_type=CREATE_MISSION_COMMAND,
                    target=target,
                    idempotency_key=normalized_key,
                    request_hash=payload_hash,
                    subject=subject,
                    response_body=response,
                    status_code=202,
                )
            )
            await session.flush()
    except IntegrityError as exc:
        replay = await _replay_receipt(
            session,
            idempotency_key=normalized_key,
            request_hash=payload_hash,
            subject=subject,
            target=target,
        )
        if replay is not None:
            return replay, True
        existing_mission = await session.scalar(select(Mission).where(Mission.alarm_id == alarm.id))
        if existing_mission is not None:
            raise AlarmAlreadyAssignedError(
                f"alarm {alarm.id} is already assigned to mission {existing_mission.id}"
            ) from exc
        raise
    return response, False
