from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import DomainError, IdempotencyConflictError
from windops_backend.models import CommandReceipt

IdempotentOperation = Callable[[], Awaitable[dict[str, Any]]]


def canonical_request_hash(payload: Any) -> str:
    encoded = json.dumps(
        jsonable_encoder(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_scope(
    *,
    command_type: str,
    target: str,
    idempotency_key: str,
) -> tuple[str, str, str]:
    normalized_command = command_type.strip()
    normalized_target = target.strip()
    normalized_key = idempotency_key.strip()
    if not 1 <= len(normalized_command) <= 96:
        raise DomainError("idempotency command type must contain between 1 and 96 characters")
    if len(normalized_target) > 160:
        raise DomainError("idempotency command target cannot exceed 160 characters")
    if not 8 <= len(normalized_key) <= 128:
        raise DomainError("Idempotency-Key must contain between 8 and 128 characters")
    return normalized_command, normalized_target, normalized_key


async def _find_receipt(
    session: AsyncSession,
    *,
    subject: str,
    command_type: str,
    target: str,
    idempotency_key: str,
) -> CommandReceipt | None:
    return cast(
        CommandReceipt | None,
        await session.scalar(
            select(CommandReceipt).where(
                CommandReceipt.subject == subject,
                CommandReceipt.command_type == command_type,
                CommandReceipt.target == target,
                CommandReceipt.idempotency_key == idempotency_key,
            )
        ),
    )


async def _replay(
    session: AsyncSession,
    receipt: CommandReceipt,
    *,
    request_hash: str,
) -> tuple[dict[str, Any], bool]:
    if receipt.request_hash != request_hash:
        raise IdempotencyConflictError(
            "the idempotency key was already used for a different request"
        )
    receipt.replay_count += 1
    receipt.last_replayed_at = datetime.now(UTC)
    await session.flush()
    return dict(receipt.response_body), True


async def execute_idempotent_command(
    session: AsyncSession,
    *,
    subject: str,
    command_type: str,
    target: str,
    idempotency_key: str,
    payload: Any,
    status_code: int,
    operation: IdempotentOperation,
) -> tuple[dict[str, Any], bool]:
    """Run one command and persist its stable response in the side-effect transaction."""

    command_type, target, idempotency_key = _normalized_scope(
        command_type=command_type,
        target=target,
        idempotency_key=idempotency_key,
    )
    request_hash = canonical_request_hash(payload)
    receipt = await _find_receipt(
        session,
        subject=subject,
        command_type=command_type,
        target=target,
        idempotency_key=idempotency_key,
    )
    if receipt is not None:
        return await _replay(session, receipt, request_hash=request_hash)

    try:
        async with session.begin_nested():
            receipt = CommandReceipt(
                id=str(uuid4()),
                command_type=command_type,
                target=target,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                subject=subject,
                response_body={"state": "executing"},
                status_code=status_code,
            )
            session.add(receipt)
            # Reserve the unique subject/endpoint/target/key before any external
            # or database side effect. A concurrent caller waits for this
            # transaction and then replays the committed response.
            await session.flush()
            raw_response = await operation()
            encoded = jsonable_encoder(raw_response)
            if not isinstance(encoded, dict):
                raise TypeError("idempotent command operations must return an object response")
            receipt.response_body = encoded
            await session.flush()
    except IntegrityError:
        receipt = await _find_receipt(
            session,
            subject=subject,
            command_type=command_type,
            target=target,
            idempotency_key=idempotency_key,
        )
        if receipt is None:
            raise
        return await _replay(session, receipt, request_hash=request_hash)
    return dict(receipt.response_body), False


async def replace_idempotent_response(
    session: AsyncSession,
    *,
    subject: str,
    command_type: str,
    target: str,
    idempotency_key: str,
    response_body: dict[str, Any],
) -> None:
    """Persist a post-commit workflow result before its first HTTP response is sent."""

    command_type, target, idempotency_key = _normalized_scope(
        command_type=command_type,
        target=target,
        idempotency_key=idempotency_key,
    )
    receipt = await _find_receipt(
        session,
        subject=subject,
        command_type=command_type,
        target=target,
        idempotency_key=idempotency_key,
    )
    if receipt is None:
        raise RuntimeError("idempotency receipt disappeared before response finalization")
    encoded = jsonable_encoder(response_body)
    if not isinstance(encoded, dict):  # pragma: no cover - typed caller invariant
        raise TypeError("idempotent response must be an object")
    receipt.response_body = encoded
    await session.flush()
