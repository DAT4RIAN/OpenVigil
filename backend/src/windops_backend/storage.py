from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from minio import Minio
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.models import Base

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def utcnow() -> datetime:
    return datetime.now(UTC)


class OutboxEvent(Base):
    """A durable event written in the same transaction as its aggregate."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_status_created", "status", "created_at"),
        Index("ix_outbox_status_lease", "status", "lease_expires_at"),
        Index("ix_outbox_aggregate", "aggregate_type", "aggregate_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_type: Mapped[str] = mapped_column(String(96), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(96), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FieldTaskEvidence(Base):
    """Verified, immutable evidence required to complete one field task."""

    __tablename__ = "field_task_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("work_order_tasks.id"), nullable=False, unique=True, index=True
    )
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    verified_by: Mapped[str] = mapped_column(String(160), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArtifactVerifier(Protocol):
    async def verify(self, artifact_uri: str, artifact_sha256: str) -> None: ...


class InMemoryArtifactVerifier:
    """Explicit test double; callers must register every accepted artifact."""

    def __init__(self) -> None:
        self._artifacts: dict[str, str] = {}

    def register(self, artifact_uri: str, artifact_sha256: str) -> None:
        _validate_sha256(artifact_sha256)
        self._artifacts[artifact_uri] = artifact_sha256

    async def verify(self, artifact_uri: str, artifact_sha256: str) -> None:
        _validate_sha256(artifact_sha256)
        if self._artifacts.get(artifact_uri) != artifact_sha256:
            raise ValueError("field artifact is absent or its SHA-256 does not match")


class MinioArtifactVerifier:
    """Production verifier that requires the referenced MinIO object to exist."""

    def __init__(self, client: Minio) -> None:
        self.client = client

    async def verify(self, artifact_uri: str, artifact_sha256: str) -> None:
        _validate_sha256(artifact_sha256)
        parsed = urlparse(artifact_uri)
        if parsed.scheme != "minio" or not parsed.netloc or not parsed.path.lstrip("/"):
            raise ValueError("production field artifacts require minio://bucket/object URIs")
        bucket = parsed.netloc
        object_name = parsed.path.lstrip("/")
        stat = await asyncio.to_thread(self.client.stat_object, bucket, object_name)
        metadata = {str(key).lower(): str(value) for key, value in (stat.metadata or {}).items()}
        stored_hash = metadata.get("x-amz-meta-sha256") or metadata.get("sha256")
        if stored_hash is not None and stored_hash.lower() != artifact_sha256:
            raise ValueError("MinIO artifact SHA-256 metadata does not match the submitted hash")
        if stored_hash is None:
            actual_hash = await asyncio.to_thread(
                self._calculate_object_sha256, bucket, object_name
            )
            if actual_hash != artifact_sha256:
                raise ValueError("MinIO artifact content SHA-256 does not match the submitted hash")

    def _calculate_object_sha256(self, bucket: str, object_name: str) -> str:
        response = self.client.get_object(bucket, object_name)
        digest = hashlib.sha256()
        try:
            for chunk in response.stream(amt=1024 * 1024):
                digest.update(chunk)
        finally:
            response.close()
            response.release_conn()
        return digest.hexdigest()


def _validate_sha256(value: str) -> None:
    if SHA256_PATTERN.fullmatch(value.lower()) is None:
        raise ValueError("artifact_sha256 must be a 64-character hexadecimal SHA-256")
