from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.access_control import domain_event_scope_clause
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import DomainEvent


@dataclass(frozen=True, slots=True)
class EventCursorCodec:
    """Authenticated opaque cursors that do not expose global event sequence gaps."""

    secret: bytes
    subject: str

    @classmethod
    def from_secret(cls, secret: str, subject: str) -> EventCursorCodec:
        return cls(secret=secret.encode(), subject=subject)

    def encode(self, sequence: int) -> str:
        if sequence < 0:
            raise ValueError("event cursor cannot be negative")
        nonce = secrets.token_bytes(12)
        plaintext = sequence.to_bytes(8, "big")
        key_stream = hmac.new(
            self.secret,
            b"windops-event-cursor-encryption\0" + self.subject.encode() + nonce,
            hashlib.sha256,
        ).digest()[: len(plaintext)]
        ciphertext = bytes(left ^ right for left, right in zip(plaintext, key_stream, strict=True))
        tag = hmac.new(
            self.secret,
            b"windops-event-cursor-authentication\0" + self.subject.encode() + nonce + ciphertext,
            hashlib.sha256,
        ).digest()[:16]
        token = base64.urlsafe_b64encode(nonce + ciphertext + tag).decode().rstrip("=")
        return f"v1.{token}"

    def decode(self, cursor: str) -> int:
        if not cursor.startswith("v1."):
            raise ValueError("event cursor is not an opaque WindOps cursor")
        encoded = cursor[3:]
        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except Exception as exc:
            raise ValueError("event cursor encoding is invalid") from exc
        if len(raw) != 36:
            raise ValueError("event cursor length is invalid")
        nonce, ciphertext, supplied_tag = raw[:12], raw[12:20], raw[20:]
        expected_tag = hmac.new(
            self.secret,
            b"windops-event-cursor-authentication\0" + self.subject.encode() + nonce + ciphertext,
            hashlib.sha256,
        ).digest()[:16]
        if not hmac.compare_digest(supplied_tag, expected_tag):
            raise ValueError("event cursor authentication failed")
        key_stream = hmac.new(
            self.secret,
            b"windops-event-cursor-encryption\0" + self.subject.encode() + nonce,
            hashlib.sha256,
        ).digest()[: len(ciphertext)]
        plaintext = bytes(left ^ right for left, right in zip(ciphertext, key_stream, strict=True))
        return int.from_bytes(plaintext, "big")


def append_domain_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> DomainEvent:
    """Append a public event in the caller's authoritative SQL transaction."""

    event = DomainEvent(
        id=str(uuid4()),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )
    session.add(event)
    return event


async def read_domain_events(
    session: AsyncSession,
    *,
    after: int,
    limit: int,
    event_types: list[str] | None = None,
    policy: GraphAccessPolicy | None = None,
) -> list[DomainEvent]:
    statement = select(DomainEvent).where(DomainEvent.sequence > after)
    if policy is not None:
        statement = statement.where(domain_event_scope_clause(policy)).execution_options(
            skip_windops_access_control=True
        )
    if event_types:
        statement = statement.where(DomainEvent.event_type.in_(event_types))
    return list(
        (await session.scalars(statement.order_by(DomainEvent.sequence.asc()).limit(limit))).all()
    )


async def latest_domain_event_sequence(
    session: AsyncSession,
    *,
    policy: GraphAccessPolicy | None = None,
) -> int:
    statement = select(func.max(DomainEvent.sequence))
    if policy is not None:
        statement = statement.where(domain_event_scope_clause(policy)).execution_options(
            skip_windops_access_control=True
        )
    return int(await session.scalar(statement) or 0)


def serialize_domain_event(
    event: DomainEvent,
    *,
    cursor: str | int | None = None,
) -> dict[str, Any]:
    return {
        "sequence": event.sequence if cursor is None else cursor,
        "event_id": event.id,
        "event_type": event.event_type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "payload": event.payload,
        "occurred_at": event.occurred_at,
    }
