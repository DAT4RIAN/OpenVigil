from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_local_locks: dict[str, asyncio.Lock] = {}


def _document_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _advisory_lock_id(scope: str) -> int:
    digest = hashlib.sha256(scope.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _same_instant(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return left is right
    normalized_left = left.replace(tzinfo=UTC) if left.tzinfo is None else left.astimezone(UTC)
    normalized_right = right.replace(tzinfo=UTC) if right.tzinfo is None else right.astimezone(UTC)
    return normalized_left == normalized_right


@asynccontextmanager
async def _claim_identity(session: AsyncSession, scope: str) -> AsyncIterator[None]:
    dialect = session.bind.dialect.name if session.bind is not None else "unknown"
    if dialect == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _advisory_lock_id(scope)},
        )
        yield
        return
    lock = _local_locks.setdefault(scope, asyncio.Lock())
    async with lock:
        yield
