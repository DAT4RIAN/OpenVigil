from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from minio import Minio
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.models import Base

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_FIELD_ARTIFACT_BYTES = 50 * 1024 * 1024
ALLOWED_FIELD_ARTIFACT_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain",
        "video/mp4",
    }
)


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
    __table_args__ = (
        UniqueConstraint("task_id", name="field_task_evidence_task_id_key"),
        Index("ix_field_task_evidence_task_id", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(ForeignKey("work_order_tasks.id"), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    verified_by: Mapped[str] = mapped_column(String(160), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArtifactVerifier(Protocol):
    async def verify(
        self,
        artifact_uri: str,
        artifact_sha256: str,
        *,
        work_order_id: str,
        task_id: str,
    ) -> None: ...

    async def create_upload(
        self,
        *,
        bucket: str,
        work_order_id: str,
        task_id: str,
        file_name: str,
        content_type: str,
        artifact_sha256: str,
    ) -> dict[str, Any]: ...

    async def create_object_upload(
        self,
        *,
        bucket: str,
        prefix: str,
        file_name: str,
        content_type: str,
        artifact_sha256: str,
        allowed_content_types: frozenset[str],
    ) -> dict[str, Any]: ...

    async def read_verified_object(
        self,
        artifact_uri: str,
        artifact_sha256: str,
        *,
        bucket: str,
        prefix: str,
        allowed_content_types: frozenset[str],
        max_bytes: int,
    ) -> tuple[bytes, str]: ...

    async def create_object_download(
        self,
        artifact_uri: str,
        *,
        bucket: str,
        prefix: str,
        response_content_type: str,
    ) -> dict[str, Any]: ...


class InMemoryArtifactVerifier:
    """Explicit test double; callers must register every accepted artifact."""

    def __init__(self) -> None:
        self._artifacts: dict[str, str] = {}
        self._objects: dict[str, tuple[bytes, str]] = {}

    def register(self, artifact_uri: str, artifact_sha256: str) -> None:
        _validate_sha256(artifact_sha256)
        self._artifacts[artifact_uri] = artifact_sha256

    def register_object(self, artifact_uri: str, content: bytes, content_type: str) -> str:
        artifact_sha256 = hashlib.sha256(content).hexdigest()
        self.register(artifact_uri, artifact_sha256)
        self._objects[artifact_uri] = (content, content_type)
        return artifact_sha256

    async def verify(
        self,
        artifact_uri: str,
        artifact_sha256: str,
        *,
        work_order_id: str,
        task_id: str,
    ) -> None:
        del work_order_id, task_id
        _validate_sha256(artifact_sha256)
        if self._artifacts.get(artifact_uri) != artifact_sha256:
            raise ValueError("field artifact is absent or its SHA-256 does not match")

    async def create_upload(
        self,
        *,
        bucket: str,
        work_order_id: str,
        task_id: str,
        file_name: str,
        content_type: str,
        artifact_sha256: str,
    ) -> dict[str, Any]:
        return await self.create_object_upload(
            bucket=bucket,
            prefix=f"work-orders/{work_order_id}/tasks/{task_id}",
            file_name=file_name,
            content_type=content_type,
            artifact_sha256=artifact_sha256,
            allowed_content_types=ALLOWED_FIELD_ARTIFACT_CONTENT_TYPES,
        )

    async def create_object_upload(
        self,
        *,
        bucket: str,
        prefix: str,
        file_name: str,
        content_type: str,
        artifact_sha256: str,
        allowed_content_types: frozenset[str],
    ) -> dict[str, Any]:
        _validate_sha256(artifact_sha256)
        if content_type not in allowed_content_types:
            raise ValueError("object content type is not allowed")
        safe_prefix = _safe_prefix(prefix)
        safe_name = _safe_file_name(file_name)
        artifact_uri = f"minio://{bucket}/{safe_prefix}/{uuid4()}-{safe_name}"
        self.register(artifact_uri, artifact_sha256.lower())
        return {
            "artifact_uri": artifact_uri,
            "upload_url": f"memory://upload/{uuid4()}",
            "expires_at": datetime.now(UTC) + timedelta(minutes=15),
            "required_headers": {"content-type": content_type},
        }

    async def read_verified_object(
        self,
        artifact_uri: str,
        artifact_sha256: str,
        *,
        bucket: str,
        prefix: str,
        allowed_content_types: frozenset[str],
        max_bytes: int,
    ) -> tuple[bytes, str]:
        _validate_object_scope(artifact_uri, bucket=bucket, prefix=prefix)
        content = self._objects.get(artifact_uri)
        if content is None or self._artifacts.get(artifact_uri) != artifact_sha256.lower():
            raise ValueError("object is absent or its SHA-256 does not match")
        body, content_type = content
        if not body or len(body) > max_bytes or content_type not in allowed_content_types:
            raise ValueError("object size or content type is not allowed")
        if hashlib.sha256(body).hexdigest() != artifact_sha256.lower():
            raise ValueError("object content SHA-256 does not match the submitted hash")
        return body, content_type

    async def create_object_download(
        self,
        artifact_uri: str,
        *,
        bucket: str,
        prefix: str,
        response_content_type: str,
    ) -> dict[str, Any]:
        del response_content_type
        _validate_object_scope(artifact_uri, bucket=bucket, prefix=prefix)
        if artifact_uri not in self._objects:
            raise ValueError("object is absent")
        return {
            "download_url": f"memory://download/{uuid4()}",
            "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        }


class MinioArtifactVerifier:
    """Production verifier that requires the referenced MinIO object to exist."""

    def __init__(
        self,
        client: Minio,
        field_evidence_bucket: str,
        upload_client: Minio | None = None,
    ) -> None:
        self.client = client
        self.upload_client = upload_client or client
        self.field_evidence_bucket = field_evidence_bucket

    async def verify(
        self,
        artifact_uri: str,
        artifact_sha256: str,
        *,
        work_order_id: str,
        task_id: str,
    ) -> None:
        _validate_sha256(artifact_sha256)
        expected_prefix = f"work-orders/{work_order_id}/tasks/{task_id}/"
        await self.read_verified_object(
            artifact_uri,
            artifact_sha256,
            bucket=self.field_evidence_bucket,
            prefix=expected_prefix,
            allowed_content_types=ALLOWED_FIELD_ARTIFACT_CONTENT_TYPES,
            max_bytes=MAX_FIELD_ARTIFACT_BYTES,
        )

    async def create_upload(
        self,
        *,
        bucket: str,
        work_order_id: str,
        task_id: str,
        file_name: str,
        content_type: str,
        artifact_sha256: str,
    ) -> dict[str, Any]:
        return await self.create_object_upload(
            bucket=bucket,
            prefix=f"work-orders/{work_order_id}/tasks/{task_id}",
            file_name=file_name,
            content_type=content_type,
            artifact_sha256=artifact_sha256,
            allowed_content_types=ALLOWED_FIELD_ARTIFACT_CONTENT_TYPES,
        )

    async def create_object_upload(
        self,
        *,
        bucket: str,
        prefix: str,
        file_name: str,
        content_type: str,
        artifact_sha256: str,
        allowed_content_types: frozenset[str],
    ) -> dict[str, Any]:
        _validate_sha256(artifact_sha256)
        if content_type not in allowed_content_types:
            raise ValueError("object content type is not allowed")
        if not await asyncio.to_thread(self.client.bucket_exists, bucket):
            raise ValueError("the configured object bucket does not exist")
        safe_name = _safe_file_name(file_name)
        object_name = f"{_safe_prefix(prefix)}/{uuid4()}-{safe_name}"
        expires = timedelta(minutes=15)
        upload_url = await asyncio.to_thread(
            self.upload_client.presigned_put_object,
            bucket,
            object_name,
            expires=expires,
        )
        return {
            "artifact_uri": f"minio://{bucket}/{object_name}",
            "upload_url": upload_url,
            "expires_at": datetime.now(UTC) + expires,
            # presigned_put_object signs the object path and expiry, but not
            # arbitrary x-amz-meta-* request headers. Integrity is therefore
            # verified from the uploaded object bytes before task completion.
            "required_headers": {"content-type": content_type},
        }

    async def read_verified_object(
        self,
        artifact_uri: str,
        artifact_sha256: str,
        *,
        bucket: str,
        prefix: str,
        allowed_content_types: frozenset[str],
        max_bytes: int,
    ) -> tuple[bytes, str]:
        _validate_sha256(artifact_sha256)
        object_name = _validate_object_scope(artifact_uri, bucket=bucket, prefix=prefix)
        stat = await asyncio.to_thread(self.client.stat_object, bucket, object_name)
        if stat.size is None or stat.size <= 0 or stat.size > max_bytes:
            raise ValueError("object size is outside the allowed range")
        content_type = str(stat.content_type or "")
        if content_type not in allowed_content_types:
            raise ValueError("object content type is not allowed")
        body = await asyncio.to_thread(self._read_object, bucket, object_name, max_bytes)
        if hashlib.sha256(body).hexdigest() != artifact_sha256.lower():
            raise ValueError("object content SHA-256 does not match the submitted hash")
        return body, content_type

    async def create_object_download(
        self,
        artifact_uri: str,
        *,
        bucket: str,
        prefix: str,
        response_content_type: str,
    ) -> dict[str, Any]:
        object_name = _validate_object_scope(artifact_uri, bucket=bucket, prefix=prefix)
        expires = timedelta(minutes=5)
        download_url = await asyncio.to_thread(
            self.upload_client.presigned_get_object,
            bucket,
            object_name,
            expires=expires,
            response_headers={"response-content-type": response_content_type},
        )
        return {
            "download_url": download_url,
            "expires_at": datetime.now(UTC) + expires,
        }

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

    def _read_object(self, bucket: str, object_name: str, max_bytes: int) -> bytes:
        response = self.client.get_object(bucket, object_name)
        content = bytearray()
        try:
            for chunk in response.stream(amt=1024 * 1024):
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ValueError("object grew beyond the allowed size while streaming")
        finally:
            response.close()
            response.release_conn()
        return bytes(content)


def _validate_sha256(value: str) -> None:
    if SHA256_PATTERN.fullmatch(value.lower()) is None:
        raise ValueError("artifact_sha256 must be a 64-character hexadecimal SHA-256")


def _safe_file_name(value: str) -> str:
    name = PurePath(value.replace("\\", "/")).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    if not safe:
        raise ValueError("file_name must contain at least one safe character")
    return safe[:160]


def _safe_prefix(value: str) -> str:
    parts = [part for part in value.replace("\\", "/").split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("object prefix is invalid")
    if any(re.fullmatch(r"[A-Za-z0-9._-]+", part) is None for part in parts):
        raise ValueError("object prefix contains unsafe characters")
    return "/".join(parts)


def _validate_object_scope(artifact_uri: str, *, bucket: str, prefix: str) -> str:
    parsed = urlparse(artifact_uri)
    object_name = parsed.path.lstrip("/")
    expected_prefix = f"{_safe_prefix(prefix).rstrip('/')}/"
    if (
        parsed.scheme != "minio"
        or parsed.netloc != bucket
        or not object_name.startswith(expected_prefix)
    ):
        raise ValueError("object does not belong to the authorized bucket and prefix")
    return object_name
