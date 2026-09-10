from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    return datetime.now(UTC)


JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")
DEFAULT_TENANT_ID = "tenant-east-china"


class Base(DeclarativeBase):
    pass
