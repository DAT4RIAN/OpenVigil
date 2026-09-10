from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.enums import AlarmStatus
from windops_backend.errors import (
    ConflictError,
    DomainError,
    IdempotencyConflictError,
    InvalidTransitionError,
    NotFoundError,
)
from windops_backend.models import Alarm, CommandReceipt
from windops_backend.schemas import AlarmCommandRequest
from windops_backend.services.events import append_domain_event

ALARM_COMMAND = "alarm.command.v1"


def _request_hash(alarm_id: str, payload: AlarmCommandRequest) -> str:
    canonical = json.dumps(
        {"alarm_id": alarm_id, **payload.model_dump(mode="json", exclude_none=True)},
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
            CommandReceipt.command_type == ALARM_COMMAND,
            CommandReceipt.subject == subject,
            CommandReceipt.target == target,
            CommandReceipt.idempotency_key == idempotency_key,
        )
    )
    if receipt is None:
        return None
    if receipt.request_hash != request_hash:
        raise IdempotencyConflictError(
            "the idempotency key was already used for a different alarm command"
        )
    receipt.replay_count += 1
    receipt.last_replayed_at = datetime.now(UTC)
    await session.flush()
    return dict(receipt.response_body)


def serialize_alarm_command(alarm: Alarm, *, action: str, changed: bool) -> dict[str, Any]:
    return {
        "alarm_id": alarm.id,
        "turbine_id": alarm.turbine_id,
        "action": action,
        "status": alarm.status,
        "assigned_to": alarm.assigned_to,
        "acknowledged_by": alarm.acknowledged_by,
        "acknowledged_at": alarm.acknowledged_at.isoformat() if alarm.acknowledged_at else None,
        "resolved_at": alarm.resolved_at.isoformat() if alarm.resolved_at else None,
        "revision": alarm.revision,
        "updated_at": alarm.updated_at.isoformat(),
        "changed": changed,
    }


async def execute_alarm_command(
    session: AsyncSession,
    alarm_id: str,
    payload: AlarmCommandRequest,
    *,
    idempotency_key: str,
    subject: str,
) -> tuple[dict[str, Any], bool]:
    """Apply one auditable, replay-safe alarm state transition."""

    normalized_key = idempotency_key.strip()
    if not 8 <= len(normalized_key) <= 128:
        raise DomainError("Idempotency-Key must contain between 8 and 128 characters")
    payload_hash = _request_hash(alarm_id, payload)
    replay = await _replay_receipt(
        session,
        idempotency_key=normalized_key,
        request_hash=payload_hash,
        subject=subject,
        target=alarm_id,
    )
    if replay is not None:
        return replay, True

    alarm = await session.scalar(select(Alarm).where(Alarm.id == alarm_id).with_for_update())
    if alarm is None:
        raise NotFoundError(f"alarm {alarm_id} was not found")

    # A concurrent request can miss an uncommitted receipt, then wait here for
    # the winning request's alarm-row lock.  Re-check after acquiring the lock
    # so the loser replays the committed result instead of reporting a stale
    # revision conflict for the same idempotency key.
    replay = await _replay_receipt(
        session,
        idempotency_key=normalized_key,
        request_hash=payload_hash,
        subject=subject,
        target=alarm_id,
    )
    if replay is not None:
        return replay, True
    if alarm.revision != payload.expected_revision:
        raise ConflictError("the alarm changed; refresh before retrying the command")
    if alarm.status == AlarmStatus.RESOLVED.value:
        raise InvalidTransitionError("resolved alarms cannot be acknowledged or assigned")

    try:
        async with session.begin_nested():
            now = datetime.now(UTC)
            previous = (
                alarm.status,
                alarm.assigned_to,
                alarm.acknowledged_at,
                alarm.acknowledged_by,
            )
            if payload.action == "acknowledge":
                if alarm.status == AlarmStatus.OPEN.value:
                    alarm.status = AlarmStatus.ACKNOWLEDGED.value
                    alarm.acknowledged_at = now
                    alarm.acknowledged_by = subject
            elif payload.action == "assign":
                alarm.assigned_to = subject
            else:
                alarm.assigned_to = None

            current = (
                alarm.status,
                alarm.assigned_to,
                alarm.acknowledged_at,
                alarm.acknowledged_by,
            )
            changed = current != previous
            if changed:
                alarm.revision += 1
                alarm.updated_at = now
            response_body = serialize_alarm_command(
                alarm,
                action=payload.action,
                changed=changed,
            )
            if changed:
                event_type = {
                    "acknowledge": "alarm.acknowledged",
                    "assign": "alarm.assigned",
                    "unassign": "alarm.unassigned",
                }[payload.action]
                append_domain_event(
                    session,
                    event_type=event_type,
                    aggregate_type="alarm",
                    aggregate_id=alarm.id,
                    payload={
                        **response_body,
                        "actor": subject,
                        "reason": payload.reason,
                    },
                )
            session.add(
                CommandReceipt(
                    id=str(uuid4()),
                    command_type=ALARM_COMMAND,
                    target=alarm_id,
                    idempotency_key=normalized_key,
                    request_hash=payload_hash,
                    subject=subject,
                    response_body=response_body,
                    status_code=200,
                )
            )
            await session.flush()
    except IntegrityError:
        replay = await _replay_receipt(
            session,
            idempotency_key=normalized_key,
            request_hash=payload_hash,
            subject=subject,
            target=alarm_id,
        )
        if replay is not None:
            return replay, True
        raise
    return response_body, False
