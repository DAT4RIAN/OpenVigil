from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol, cast
from uuid import uuid4

from windops_backend.benchmarks.care.artifact_utils import (
    canonical_json_sha256 as _sha256_json,
)
from windops_backend.benchmarks.care.artifact_utils import (
    sha256_file as _sha256_file,
)

PIPELINE_CONTRACT_VERSION = "care-v6-benchmark-pipeline-v2"
PARQUET_LAYOUT_VERSION = "care-v6-wide-parquet-v2"
JOB_STATE_SCHEMA_VERSION = "care-v6-benchmark-job-v1"
CHECKPOINT_SCHEMA_VERSION = "care-v6-parquet-checkpoint-v1"
PARQUET_COMPRESSION = "zstd"
PARQUET_COMPRESSION_LEVEL = 3
PARQUET_ROW_GROUP_SIZE = 8192
CSV_BLOCK_SIZE_BYTES = 1 * 1024 * 1024
COPY_BUFFER_BYTES = 1 * 1024 * 1024
MAX_JOB_ATTEMPTS = 3
QUALITY_RULE_VERSION = "care-v6-quality-rules-v1"
FEATURE_SET_VERSION = "care-v6-avg-feature-set-v1"


class CarePipelineError(RuntimeError):
    """Raised when the independent CARE pipeline violates an execution boundary."""


class BenchmarkJobCancelled(CarePipelineError):
    """Raised at a durable cancellation boundary."""


class RetryableBenchmarkError(CarePipelineError):
    """Raised for a bounded retry such as temporary object-store unavailability."""


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _normalize_column_selection(
    source_path: Path,
    selected_columns: Sequence[str] | None,
    model_input_columns: Sequence[str] | None,
) -> tuple[tuple[str, ...] | None, tuple[str, ...]]:
    selected = tuple(selected_columns) if selected_columns is not None else None
    model_inputs = tuple(model_input_columns or ())
    for label, columns in (("selected", selected or ()), ("model-input", model_inputs)):
        if len(columns) != len(set(columns)) or any(not column.strip() for column in columns):
            raise CarePipelineError(f"{label} columns must be non-empty and unique")
    if model_inputs and selected is None:
        raise CarePipelineError("model-input columns require an explicit selected-column set")
    if selected is not None:
        if not selected:
            raise CarePipelineError("selected CARE columns cannot be empty")
        with source_path.open("r", encoding="utf-8-sig", newline="") as stream:
            source_columns = tuple(stream.readline().rstrip("\r\n").split(";"))
        unknown = [column for column in selected if column not in source_columns]
        if unknown:
            raise CarePipelineError(f"selected CARE columns are absent from source: {unknown}")
        source_order = tuple(column for column in source_columns if column in set(selected))
        if source_order != selected:
            raise CarePipelineError("selected CARE columns must preserve immutable source order")
        if not set(model_inputs).issubset(selected):
            raise CarePipelineError("model-input columns must be a subset of selected columns")
    return selected, model_inputs


def _validate_job_id(job_id: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", job_id) is None:
        raise CarePipelineError("benchmark job ID must be a portable identifier")
    return job_id


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    try:
        partial.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def _project_local_output(source: Path, output_root: Path) -> tuple[Path, Path]:
    source = source.resolve(strict=True)
    output_root = output_root.resolve()
    if source == output_root or output_root.is_relative_to(source):
        raise CarePipelineError("pipeline output cannot be placed inside the read-only source file")
    if source.is_relative_to(output_root):
        raise CarePipelineError("pipeline source cannot be inside its output root")
    return source, output_root


@dataclass(frozen=True, slots=True)
class BenchmarkDependencyVersions:
    pyarrow: str
    scikit_learn: str | None
    python: str

    def to_document(self) -> dict[str, str | None]:
        return {
            "pyarrow": self.pyarrow,
            "scikit_learn": self.scikit_learn,
            "python": self.python,
        }


def load_benchmark_dependencies(*, require_baseline: bool = False) -> tuple[Any, Any, Any]:
    """Load heavy optional packages only from the independent benchmark entrypoint."""

    try:
        csv_module = importlib.import_module("pyarrow.csv")
        parquet_module = importlib.import_module("pyarrow.parquet")
        arrow_module = importlib.import_module("pyarrow")
    except ImportError as exc:
        raise CarePipelineError(
            "CARE pipeline requires the optional dependency group: uv run --extra benchmark"
        ) from exc
    if require_baseline:
        try:
            importlib.import_module("sklearn")
        except ImportError as exc:
            raise CarePipelineError(
                "CARE training requires the optional benchmark dependency group"
            ) from exc
    return arrow_module, csv_module, parquet_module


def benchmark_dependency_versions(*, require_baseline: bool = False) -> BenchmarkDependencyVersions:
    arrow, _csv, _parquet = load_benchmark_dependencies(require_baseline=require_baseline)
    sklearn_version: str | None = None
    if require_baseline:
        sklearn_version = str(importlib.import_module("sklearn").__version__)
    return BenchmarkDependencyVersions(
        pyarrow=str(arrow.__version__),
        scikit_learn=sklearn_version,
        python=".".join(str(item) for item in sys.version_info[:3]),
    )


@dataclass(frozen=True, slots=True)
class CareObjectStorageLayout:
    bucket: str = "windops-care-benchmarks"
    raw_prefix: str = "care/v6/raw"
    standard_prefix: str = "care/v6/standard"
    quality_prefix: str = "care/v6/quality"
    predictions_prefix: str = "care/v6/predictions"
    reports_prefix: str = "care/v6/reports"

    @classmethod
    def from_settings(cls, settings: Any) -> CareObjectStorageLayout:
        """Build the worker-only layout from validated runtime settings."""

        return cls(
            bucket=str(settings.minio_care_bucket),
            raw_prefix=str(settings.minio_care_raw_prefix),
            standard_prefix=str(settings.minio_care_standard_prefix),
            quality_prefix=str(settings.minio_care_quality_prefix),
            predictions_prefix=str(settings.minio_care_predictions_prefix),
            reports_prefix=str(settings.minio_care_reports_prefix),
        )

    def __post_init__(self) -> None:
        if not self.bucket.strip():
            raise CarePipelineError("CARE object-store bucket cannot be empty")
        prefixes = self.prefixes()
        if len(prefixes) != len(set(prefixes.values())):
            raise CarePipelineError("CARE object-store prefixes must be distinct")
        for name, prefix in prefixes.items():
            parsed = PurePosixPath(prefix)
            if (
                parsed.is_absolute()
                or ".." in parsed.parts
                or not prefix.startswith("care/v6/")
                or "\\" in prefix
                or "//" in prefix
                or str(parsed) != prefix
            ):
                raise CarePipelineError(f"unsafe CARE {name} prefix: {prefix}")

    def prefixes(self) -> dict[str, str]:
        return {
            "raw": self.raw_prefix,
            "standard": self.standard_prefix,
            "quality": self.quality_prefix,
            "predictions": self.predictions_prefix,
            "reports": self.reports_prefix,
        }

    def event_key(self, layer: str, *, farm: str, event_id: int, file_name: str) -> str:
        try:
            prefix = self.prefixes()[layer]
        except KeyError as exc:
            raise CarePipelineError(f"unknown CARE object layer {layer!r}") from exc
        if farm not in {"A", "B", "C"} or not 0 <= event_id <= 94:
            raise CarePipelineError("CARE object event identity is invalid")
        if PurePosixPath(file_name).name != file_name or file_name in {"", ".", ".."}:
            raise CarePipelineError("CARE object file name is unsafe")
        return f"{prefix}/farm={farm}/event={event_id}/{file_name}"

    def contract_document(self) -> dict[str, Any]:
        lifecycle = {
            "raw": {"retention_days": 3650, "versioning": True, "backup": True},
            "standard": {"retention_days": 3650, "versioning": True, "backup": True},
            "quality": {"retention_days": 3650, "versioning": True, "backup": True},
            "predictions": {"retention_days": 1825, "versioning": True, "backup": True},
            "reports": {"retention_days": 3650, "versioning": True, "backup": True},
            "temporary": {
                "prefix": "care/v6/_tmp",
                "expire_after_days": 7,
                "backup": False,
            },
        }
        payload = {
            "bucket": self.bucket,
            "prefixes": self.prefixes(),
            "access": "private-service-account-and-authorized-download-only",
            "public_access": False,
            "server_side_encryption": "required-in-production",
            "lifecycle": lifecycle,
        }
        return {**payload, "layout_sha256": _sha256_json(payload)}


class ImmutableArtifactStore(Protocol):
    def put_immutable(
        self,
        object_key: str,
        source: Path,
        sha256: str,
        *,
        content_type: str = "application/octet-stream",
    ) -> str: ...


def _safe_object_key(object_key: str) -> str:
    path = PurePosixPath(object_key)
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
        raise CarePipelineError("unsafe immutable object key")
    return str(path)


class LocalImmutableArtifactStore:
    """Filesystem test/development store with the same no-overwrite contract as MinIO."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put_immutable(
        self,
        object_key: str,
        source: Path,
        sha256: str,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        del content_type
        key = _safe_object_key(object_key)
        source = source.resolve(strict=True)
        if _sha256_file(source) != sha256:
            raise CarePipelineError("source artifact does not match its declared SHA-256")
        destination = (self.root / Path(*PurePosixPath(key).parts)).resolve()
        if not destination.is_relative_to(self.root):  # pragma: no cover - guarded by key parser
            raise CarePipelineError("immutable object escaped its store root")
        if destination.exists():
            if _sha256_file(destination) != sha256:
                raise CarePipelineError("immutable object key already contains different content")
            return destination.as_uri()
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(f".{destination.name}.{uuid4().hex}.partial")
        try:
            with source.open("rb") as input_stream, partial.open("xb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream, length=COPY_BUFFER_BYTES)
            if _sha256_file(partial) != sha256:
                raise CarePipelineError("copied immutable object failed hash verification")
            try:
                os.link(partial, destination)
            except FileExistsError:
                if _sha256_file(destination) != sha256:
                    raise CarePipelineError(
                        "immutable object key concurrently received different content"
                    ) from None
        finally:
            partial.unlink(missing_ok=True)
        return destination.as_uri()


class MinioImmutableArtifactStore:
    """Synchronous adapter used only by the independent worker process."""

    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def put_immutable(
        self,
        object_key: str,
        source: Path,
        sha256: str,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        key = _safe_object_key(object_key)
        if sha256 not in PurePosixPath(key).name:
            raise CarePipelineError("MinIO immutable object key must contain its content SHA-256")
        source = source.resolve(strict=True)
        if _sha256_file(source) != sha256:
            raise CarePipelineError("source artifact does not match its declared SHA-256")
        try:
            existing = self.client.stat_object(self.bucket, key)
        except Exception as exc:
            if getattr(exc, "code", None) not in {"NoSuchKey", "NoSuchObject"}:
                raise RetryableBenchmarkError("CARE object store is unavailable") from exc
        else:
            metadata = {str(k).lower(): str(v) for k, v in dict(existing.metadata).items()}
            stored_hash = metadata.get("x-amz-meta-sha256") or metadata.get("sha256")
            if stored_hash != sha256 or int(existing.size) != source.stat().st_size:
                raise CarePipelineError("immutable MinIO object key already has different content")
            return f"minio://{self.bucket}/{key}"

        temporary_key = f"care/v6/_tmp/{uuid4().hex}.partial"
        publish_error: Exception | None = None
        try:
            self.client.fput_object(
                self.bucket,
                temporary_key,
                str(source),
                content_type=content_type,
                metadata={"sha256": sha256},
            )
            minio_common = importlib.import_module("minio.commonconfig")
            self.client.copy_object(
                self.bucket,
                key,
                minio_common.CopySource(self.bucket, temporary_key),
                metadata={"sha256": sha256},
                metadata_directive="REPLACE",
            )
            final = self.client.stat_object(self.bucket, key)
            final_metadata = {str(k).lower(): str(v) for k, v in dict(final.metadata).items()}
            final_hash = final_metadata.get("x-amz-meta-sha256") or final_metadata.get("sha256")
            if int(final.size) != source.stat().st_size or final_hash != sha256:
                raise CarePipelineError("published MinIO object identity mismatch")
        except CarePipelineError as exc:
            publish_error = exc
        except Exception as exc:
            publish_error = RetryableBenchmarkError("CARE object store publish failed")
            publish_error.__cause__ = exc
        try:
            self.client.remove_object(self.bucket, temporary_key)
        except Exception as cleanup_exc:
            cleanup_is_lifecycle_deferred = (
                publish_error is None and getattr(cleanup_exc, "code", None) == "AccessDenied"
            )
            if publish_error is None and not cleanup_is_lifecycle_deferred:
                raise RetryableBenchmarkError(
                    "CARE temporary object cleanup failed"
                ) from cleanup_exc
            if publish_error is not None:
                publish_error.add_note(f"temporary object cleanup also failed: {cleanup_exc}")
        if publish_error is not None:
            raise publish_error
        return f"minio://{self.bucket}/{key}"


JobOperation = Literal["import", "quality", "train", "evaluate"]
JobStatus = Literal["pending", "running", "cancelling", "cancelled", "failed", "completed"]


@dataclass(frozen=True, slots=True)
class BenchmarkJobState:
    job_id: str
    operation: JobOperation
    status: JobStatus
    attempt: int
    max_attempts: int
    progress_completed: int
    progress_total: int | None
    current_file: str | None
    heartbeat_at: datetime | None
    cancel_requested: bool
    checkpoint_path: str | None
    artifact_uri: str | None
    resource_stats: Mapping[str, int | float]
    error: str | None
    revision: int = 0

    def __post_init__(self) -> None:
        _validate_job_id(self.job_id)
        if self.operation not in {
            "import",
            "quality",
            "train",
            "evaluate",
        }:
            raise CarePipelineError("benchmark job identity is invalid")
        if self.status not in {
            "pending",
            "running",
            "cancelling",
            "cancelled",
            "failed",
            "completed",
        }:
            raise CarePipelineError("benchmark job status is invalid")
        if not 0 <= self.attempt <= self.max_attempts or self.max_attempts < 1:
            raise CarePipelineError("benchmark job attempt bounds are invalid")
        if self.progress_completed < 0 or (
            self.progress_total is not None
            and (self.progress_total < 0 or self.progress_completed > self.progress_total)
        ):
            raise CarePipelineError("benchmark job progress is invalid")
        if self.heartbeat_at is not None and (
            self.heartbeat_at.tzinfo is None or self.heartbeat_at.utcoffset() is None
        ):
            raise CarePipelineError("benchmark heartbeat must be timezone-aware")
        if self.status == "completed" and not self.artifact_uri:
            raise CarePipelineError("completed benchmark job must reference its artifact")
        if self.status == "failed" and not self.error:
            raise CarePipelineError("failed benchmark job must record its error")

    @classmethod
    def pending(
        cls, job_id: str, operation: JobOperation, *, max_attempts: int = MAX_JOB_ATTEMPTS
    ) -> BenchmarkJobState:
        return cls(
            job_id,
            operation,
            "pending",
            0,
            max_attempts,
            0,
            None,
            None,
            None,
            False,
            None,
            None,
            {},
            None,
        )

    def to_document(self) -> dict[str, Any]:
        payload = {
            "schema_version": JOB_STATE_SCHEMA_VERSION,
            "job_id": self.job_id,
            "operation": self.operation,
            "status": self.status,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "progress_completed": self.progress_completed,
            "progress_total": self.progress_total,
            "current_file": self.current_file,
            "heartbeat_at": self.heartbeat_at.isoformat() if self.heartbeat_at else None,
            "cancel_requested": self.cancel_requested,
            "checkpoint_path": self.checkpoint_path,
            "artifact_uri": self.artifact_uri,
            "resource_stats": dict(self.resource_stats),
            "error": self.error,
            "revision": self.revision,
        }
        return {**payload, "state_sha256": _sha256_json(payload)}

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> BenchmarkJobState:
        actual = value.get("state_sha256")
        if not isinstance(actual, str):
            raise CarePipelineError("benchmark job state is missing its hash")
        unsigned = {key: item for key, item in value.items() if key != "state_sha256"}
        if (
            _sha256_json(unsigned) != actual
            or value.get("schema_version") != JOB_STATE_SCHEMA_VERSION
        ):
            raise CarePipelineError("benchmark job state hash or schema is invalid")
        heartbeat_raw = value.get("heartbeat_at")
        try:
            resource_stats = value.get("resource_stats")
            if not isinstance(resource_stats, Mapping):
                raise CarePipelineError("benchmark resource stats are malformed")
            operation = value["operation"]
            status = value["status"]
            cancel_requested = value["cancel_requested"]
            if operation not in {"import", "quality", "train", "evaluate"}:
                raise CarePipelineError("benchmark job document has an invalid operation")
            if status not in {
                "pending",
                "running",
                "cancelling",
                "cancelled",
                "failed",
                "completed",
            }:
                raise CarePipelineError("benchmark job document has an invalid status")
            if type(cancel_requested) is not bool:
                raise CarePipelineError("benchmark cancel_requested must be boolean")
            return cls(
                job_id=str(value["job_id"]),
                operation=cast(JobOperation, operation),
                status=cast(JobStatus, status),
                attempt=int(value["attempt"]),
                max_attempts=int(value["max_attempts"]),
                progress_completed=int(value["progress_completed"]),
                progress_total=(
                    int(value["progress_total"])
                    if value.get("progress_total") is not None
                    else None
                ),
                current_file=(str(value["current_file"]) if value.get("current_file") else None),
                heartbeat_at=(
                    datetime.fromisoformat(str(heartbeat_raw)) if heartbeat_raw else None
                ),
                cancel_requested=cancel_requested,
                checkpoint_path=(
                    str(value["checkpoint_path"]) if value.get("checkpoint_path") else None
                ),
                artifact_uri=(str(value["artifact_uri"]) if value.get("artifact_uri") else None),
                resource_stats={str(key): float(item) for key, item in resource_stats.items()},
                error=(str(value["error"]) if value.get("error") else None),
                revision=int(value["revision"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CarePipelineError("benchmark job state is malformed") from exc


class FileBenchmarkJobControl:
    def __init__(self, path: Path, initial: BenchmarkJobState | None = None) -> None:
        self.path = path
        if initial is not None and not path.exists():
            _atomic_json(path, initial.to_document())

    def read(self) -> BenchmarkJobState:
        if not self.path.is_file():
            raise CarePipelineError(f"benchmark job state does not exist: {self.path}")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise CarePipelineError("benchmark job state root must be an object")
        return BenchmarkJobState.from_document(raw)

    def write(self, state: BenchmarkJobState) -> BenchmarkJobState:
        _atomic_json(self.path, state.to_document())
        return state

    def start_attempt(self) -> BenchmarkJobState:
        state = self.read()
        if state.status == "completed":
            raise CarePipelineError("completed benchmark job cannot be executed again")
        if state.cancel_requested:
            return self.write(replace(state, status="cancelled", revision=state.revision + 1))
        if state.attempt >= state.max_attempts:
            raise CarePipelineError("benchmark job exhausted its bounded attempts")
        return self.write(
            replace(
                state,
                status="running",
                attempt=state.attempt + 1,
                heartbeat_at=datetime.now(UTC),
                error=None,
                revision=state.revision + 1,
            )
        )

    def heartbeat(
        self,
        *,
        completed: int,
        total: int | None,
        current_file: str,
        checkpoint_path: str | None,
        resource_stats: Mapping[str, int | float],
    ) -> None:
        state = self.read()
        status: JobStatus = "cancelling" if state.cancel_requested else "running"
        self.write(
            replace(
                state,
                status=status,
                progress_completed=completed,
                progress_total=total,
                current_file=current_file,
                heartbeat_at=datetime.now(UTC),
                checkpoint_path=checkpoint_path,
                resource_stats=dict(resource_stats),
                revision=state.revision + 1,
            )
        )

    def cancellation_point(self) -> None:
        state = self.read()
        if state.cancel_requested:
            self.write(
                replace(
                    state,
                    status="cancelled",
                    heartbeat_at=datetime.now(UTC),
                    revision=state.revision + 1,
                )
            )
            raise BenchmarkJobCancelled("benchmark job was cancelled at a durable boundary")

    def request_cancel(self) -> BenchmarkJobState:
        state = self.read()
        if state.status in {"completed", "cancelled", "failed"}:
            return state
        return self.write(
            replace(
                state,
                cancel_requested=True,
                status="cancelling" if state.status == "running" else state.status,
                revision=state.revision + 1,
            )
        )

    def complete(self, artifact_uri: str, resource_stats: Mapping[str, int | float]) -> None:
        state = self.read()
        if state.status == "completed":
            if state.artifact_uri != artifact_uri:
                raise CarePipelineError("completed benchmark job artifact is immutable")
            return
        if state.status in {"cancelled", "failed"}:
            raise CarePipelineError("terminal benchmark job cannot be completed")
        self.write(
            replace(
                state,
                status="completed",
                artifact_uri=artifact_uri,
                heartbeat_at=datetime.now(UTC),
                resource_stats=dict(resource_stats),
                error=None,
                revision=state.revision + 1,
            )
        )

    def fail(self, error: Exception, *, retryable: bool = True) -> BenchmarkJobState:
        state = self.read()
        terminal = not retryable or state.attempt >= state.max_attempts
        return self.write(
            replace(
                state,
                status="failed" if terminal else "pending",
                error=str(error)[:4000] if terminal else None,
                heartbeat_at=datetime.now(UTC),
                revision=state.revision + 1,
            )
        )
