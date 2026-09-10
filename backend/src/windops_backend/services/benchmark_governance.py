from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Protocol, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.access_control import data_scope_allowed
from windops_backend.benchmarks.care.contract import (
    DATASET_ID,
    DATASET_VERSION,
    DOI,
    LICENSE_NAME,
    LICENSE_URL,
)
from windops_backend.benchmarks.care.licensing import build_care_artifact_license
from windops_backend.benchmarks.care.pipeline import CareObjectStorageLayout
from windops_backend.errors import DomainError, IdempotencyConflictError, NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkEvent,
    BenchmarkEventResult,
    BenchmarkMetricSnapshot,
    DomainEvent,
)
from windops_backend.schemas import BenchmarkArtifactExportRequest
from windops_backend.services.benchmark_catalog import benchmark_dataset_scope_clause
from windops_backend.services.events import append_domain_event

BENCHMARK_EXPORT_SCHEMA_VERSION = "care-v6-governed-evaluation-export-v1"
BENCHMARK_CLEANUP_SCHEMA_VERSION = "care-v6-artifact-cleanup-v1"
BENCHMARK_EXPORT_EVENT_TYPE = "benchmark.export.completed"
BENCHMARK_EXPORT_DENIED_EVENT_TYPE = "benchmark.export.denied"
BENCHMARK_CLEANUP_STARTED_EVENT_TYPE = "benchmark.cleanup.started"
BENCHMARK_CLEANUP_EVENT_TYPE = "benchmark.cleanup.completed"
BENCHMARK_CLEANUP_FAILED_EVENT_TYPE = "benchmark.cleanup.failed"
BENCHMARK_EXPORT_RESULT_MAX = 95
BENCHMARK_EXPORT_METRIC_MAX = 64
BENCHMARK_CLEANUP_OBJECT_MAX = 256

_local_locks: dict[str, asyncio.Lock] = {}


class BenchmarkExportReviewError(DomainError):
    code = "BENCHMARK_EXPORT_REVIEW_REQUIRED"
    status_code = 403


class BenchmarkArtifactScopeError(DomainError):
    code = "BENCHMARK_ARTIFACT_SCOPE_INVALID"
    status_code = 422


class BenchmarkArtifactCleanupError(DomainError):
    code = "BENCHMARK_ARTIFACT_CLEANUP_FAILED"
    status_code = 503

    def __init__(self, message: str, *, audit_document: Mapping[str, object]) -> None:
        super().__init__(message)
        self.audit_document = dict(audit_document)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _document_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def benchmark_export_allowed(policy: GraphAccessPolicy) -> bool:
    return policy.unrestricted or (
        data_scope_allowed(policy, "benchmark")
        and data_scope_allowed(policy, "model")
        and data_scope_allowed(policy, "benchmark_export")
    )


@asynccontextmanager
async def _claim_export_identity(session: AsyncSession, export_id: str) -> AsyncIterator[None]:
    dialect = session.bind.dialect.name if session.bind is not None else "unknown"
    if dialect == "postgresql":
        digest = hashlib.sha256(export_id.encode("utf-8")).digest()
        lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
        yield
        return
    lock = _local_locks.setdefault(export_id, asyncio.Lock())
    async with lock:
        yield


@dataclass(frozen=True, slots=True)
class GovernedBenchmarkExport:
    export_id: str
    audit_event_id: str
    content: bytes
    content_type: str
    file_name: str
    artifact_sha256: str
    payload_sha256: str
    license_metadata: dict[str, Any]
    replayed: bool


def _safe_csv_cell(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _render_export(
    *,
    request: BenchmarkArtifactExportRequest,
    dataset: BenchmarkDatasetVersion,
    evaluation: BenchmarkEvaluationRun,
    results: Sequence[dict[str, object]],
    metrics: Sequence[dict[str, object]],
) -> tuple[bytes, str, str, str, dict[str, Any]]:
    source_artifact_sha256 = str(evaluation.artifact_sha256 or "")
    if not _valid_sha256(source_artifact_sha256):
        raise BenchmarkArtifactScopeError(
            "completed benchmark evaluation has no immutable artifact SHA-256"
        )
    if request.expected_source_artifact_sha256 != source_artifact_sha256:
        raise BenchmarkArtifactScopeError("benchmark export source artifact identity changed")
    if (
        dataset.dataset_id.casefold() != DATASET_ID
        or dataset.version != DATASET_VERSION
        or dataset.license_name != LICENSE_NAME
        or dataset.license_url != LICENSE_URL
        or dataset.doi != DOI
        or not _valid_sha256(dataset.content_sha256)
    ):
        raise BenchmarkArtifactScopeError("benchmark dataset license or source identity is invalid")

    artifact_type = f"benchmark-evaluation-{request.export_format}-report"
    license_metadata = build_care_artifact_license(
        artifact_type=artifact_type,
        changes_made=request.changes_made,
        source_dataset_sha256=dataset.content_sha256,
        source_artifact_sha256=source_artifact_sha256,
        transformation_versions={
            "export": BENCHMARK_EXPORT_SCHEMA_VERSION,
            "feature_set": evaluation.feature_set_version,
            "quality_rules": evaluation.quality_rule_version,
            "score_protocol": evaluation.protocol_version,
            "threshold_policy": evaluation.threshold_policy_version,
        },
    )
    report = {
        "dataset": {
            "dataset_version_id": dataset.id,
            "dataset_id": dataset.dataset_id,
            "version": dataset.version,
            "content_sha256": dataset.content_sha256,
        },
        "evaluation": {
            "evaluation_run_id": evaluation.id,
            "model_id": evaluation.model_id,
            "model_version": evaluation.model_version,
            "run_kind": evaluation.run_kind,
            "protocol_version": evaluation.protocol_version,
            "farm": evaluation.farm,
            "status": evaluation.status,
            "feature_set_version": evaluation.feature_set_version,
            "quality_rule_version": evaluation.quality_rule_version,
            "threshold_policy_version": evaluation.threshold_policy_version,
            "threshold_policy_sha256": evaluation.threshold_policy_sha256,
            "random_seed": evaluation.random_seed,
            "artifact_sha256": source_artifact_sha256,
            "requested_event_count": evaluation.requested_event_count,
            "scored_event_count": evaluation.scored_event_count,
            "failed_event_count": evaluation.failed_event_count,
            "unscorable_event_count": evaluation.unscorable_event_count,
            "completed_at": (
                evaluation.completed_at.isoformat() if evaluation.completed_at is not None else None
            ),
        },
        "truth_included": request.include_truth,
        "metrics": list(metrics),
        "event_results": list(results),
    }
    payload_sha256 = _document_sha256(report)
    metadata = {
        "schema_version": BENCHMARK_EXPORT_SCHEMA_VERSION,
        "format": request.export_format,
        "distribution": request.distribution,
        "payload_sha256": payload_sha256,
        "hash_scope": "canonical report payload excluding this export envelope",
        "license": license_metadata,
    }
    file_stem = f"care-{evaluation.id}-evaluation-report"
    if request.export_format == "json":
        unsigned = {**metadata, "report": report}
        artifact_sha256 = _document_sha256(unsigned)
        content = _canonical_bytes({**unsigned, "artifact_sha256": artifact_sha256}) + b"\n"
        return content, "application/json", f"{file_stem}.json", payload_sha256, license_metadata

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "record_type",
            "name",
            "event_id",
            "farm",
            "source_asset_id",
            "status",
            "value",
            "unit",
            "threshold",
            "passed",
            "failure_code",
            "event_label",
            "event_description",
        ]
    )
    for metric in metrics:
        writer.writerow(
            [
                "metric",
                metric["metric_name"],
                "",
                "",
                "",
                "",
                metric["value"],
                metric["unit"],
                metric["threshold_value"],
                metric["passed"],
                "",
                "",
                "",
            ]
        )
    for result in results:
        truth = result["truth"]
        if not isinstance(truth, Mapping):
            raise BenchmarkArtifactScopeError("benchmark export truth contract is malformed")
        writer.writerow(
            [
                "event_result",
                "care_score",
                result["event_id"],
                result["farm"],
                result["source_asset_id"],
                result["status"],
                result["care_score"],
                "ratio",
                "",
                result["anomaly_detected"],
                _safe_csv_cell(result["failure_code"]),
                _safe_csv_cell(truth["event_label"]),
                _safe_csv_cell(truth["description"]),
            ]
        )
    csv_payload = output.getvalue().encode("utf-8")
    csv_payload_sha256 = hashlib.sha256(csv_payload).hexdigest()
    csv_metadata = {**metadata, "csv_payload_sha256": csv_payload_sha256}
    content = (
        b"# windops-care-export-metadata=" + _canonical_bytes(csv_metadata) + b"\n" + csv_payload
    )
    return content, "text/csv; charset=utf-8", f"{file_stem}.csv", payload_sha256, license_metadata


async def _load_export_source(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    evaluation_run_id: str,
    include_truth: bool,
) -> tuple[
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    list[dict[str, object]],
    list[dict[str, object]],
]:
    row = (
        await session.execute(
            select(BenchmarkDatasetVersion, BenchmarkEvaluationRun)
            .join(
                BenchmarkEvaluationRun,
                BenchmarkEvaluationRun.dataset_version_id == BenchmarkDatasetVersion.id,
            )
            .where(
                BenchmarkEvaluationRun.id == evaluation_run_id,
                benchmark_dataset_scope_clause(policy),
            )
            .execution_options(skip_windops_access_control=True)
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError(f"benchmark evaluation {evaluation_run_id} was not found")
    dataset = cast(BenchmarkDatasetVersion, row[0])
    evaluation = cast(BenchmarkEvaluationRun, row[1])
    if evaluation.status != "completed" or evaluation.invalidated_at is not None:
        raise BenchmarkArtifactScopeError("only completed, non-invalidated evaluations can export")

    safe_columns: list[Any] = [
        BenchmarkEventResult.id,
        BenchmarkEventResult.status,
        BenchmarkEventResult.scorable,
        BenchmarkEventResult.anomaly_detected,
        BenchmarkEventResult.care_score,
        BenchmarkEventResult.coverage_score,
        BenchmarkEventResult.accuracy_score,
        BenchmarkEventResult.reliability_score,
        BenchmarkEventResult.earliness_score,
        BenchmarkEventResult.failure_code,
        BenchmarkEventResult.result_sha256,
        BenchmarkEvent.event_id,
        BenchmarkEvent.farm,
        BenchmarkEvent.source_asset_id,
    ]
    if include_truth:
        safe_columns.extend(
            [
                BenchmarkEvent.event_label,
                BenchmarkEvent.event_interval_start,
                BenchmarkEvent.event_interval_end,
                BenchmarkEvent.truth_metadata,
                BenchmarkEventResult.details,
            ]
        )
    result_rows = (
        await session.execute(
            select(*safe_columns)
            .join(BenchmarkEvent, BenchmarkEvent.id == BenchmarkEventResult.event_id)
            .where(BenchmarkEventResult.evaluation_run_id == evaluation.id)
            .order_by(BenchmarkEvent.event_id.asc())
            .limit(BENCHMARK_EXPORT_RESULT_MAX + 1)
            .execution_options(skip_windops_access_control=True)
        )
    ).all()
    if (
        len(result_rows) > BENCHMARK_EXPORT_RESULT_MAX
        or len(result_rows) != evaluation.requested_event_count
    ):
        raise BenchmarkArtifactScopeError(
            "benchmark export result set is incomplete or exceeds its governed bound"
        )
    results: list[dict[str, object]] = []
    for item in result_rows:
        truth_metadata = item.truth_metadata if include_truth else {}
        details = item.details if include_truth else {}
        results.append(
            {
                "result_id": item.id,
                "event_id": item.event_id,
                "farm": item.farm,
                "source_asset_id": item.source_asset_id,
                "status": item.status,
                "scorable": item.scorable,
                "anomaly_detected": item.anomaly_detected,
                "care_score": item.care_score,
                "coverage_score": item.coverage_score,
                "accuracy_score": item.accuracy_score,
                "reliability_score": item.reliability_score,
                "earliness_score": item.earliness_score,
                "failure_code": item.failure_code,
                "result_sha256": item.result_sha256,
                "truth": {
                    "access": "revealed" if include_truth else "restricted",
                    "event_label": item.event_label if include_truth else None,
                    "event_interval_start": item.event_interval_start if include_truth else None,
                    "event_interval_end": item.event_interval_end if include_truth else None,
                    "failure_type": details.get("failure_type") if include_truth else None,
                    "description": truth_metadata.get("description") if include_truth else None,
                },
            }
        )
    metric_rows = (
        await session.scalars(
            select(BenchmarkMetricSnapshot)
            .where(BenchmarkMetricSnapshot.evaluation_run_id == evaluation.id)
            .order_by(BenchmarkMetricSnapshot.metric_name.asc())
            .limit(BENCHMARK_EXPORT_METRIC_MAX + 1)
            .execution_options(skip_windops_access_control=True)
        )
    ).all()
    if len(metric_rows) > BENCHMARK_EXPORT_METRIC_MAX:
        raise BenchmarkArtifactScopeError("benchmark export metrics exceed their governed bound")
    metrics: list[dict[str, object]] = [
        {
            "metric_name": metric.metric_name,
            "protocol_version": metric.protocol_version,
            "metric_version": metric.metric_version,
            "value": metric.value,
            "unit": metric.unit,
            "is_release_metric": metric.is_release_metric,
            "threshold_value": metric.threshold_value,
            "threshold_direction": metric.threshold_direction,
            "passed": metric.passed,
        }
        for metric in metric_rows
    ]
    return dataset, evaluation, results, metrics


def _export_review_failures(request: BenchmarkArtifactExportRequest) -> list[str]:
    if request.distribution != "external":
        return []
    failures: list[str] = []
    if not request.attribution_confirmed:
        failures.append("ATTRIBUTION_NOT_CONFIRMED")
    if not request.license_link_confirmed:
        failures.append("LICENSE_LINK_NOT_CONFIRMED")
    if not request.share_alike_confirmed:
        failures.append("SHAREALIKE_NOT_CONFIRMED")
    if not request.legal_review_reference:
        failures.append("LEGAL_REVIEW_REFERENCE_REQUIRED")
    return failures


async def build_governed_benchmark_export(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    evaluation_run_id: str,
    request: BenchmarkArtifactExportRequest,
    idempotency_key: str,
    subject: str,
) -> GovernedBenchmarkExport:
    if not benchmark_export_allowed(policy):
        raise BenchmarkExportReviewError(
            "benchmark export requires benchmark, model, and benchmark_export scopes"
        )
    dataset, evaluation, results, metrics = await _load_export_source(
        session,
        policy,
        evaluation_run_id=evaluation_run_id,
        include_truth=request.include_truth,
    )
    request_document = {
        "evaluation_run_id": evaluation_run_id,
        "request": request.model_dump(mode="json"),
        "idempotency_key": idempotency_key,
        "subject": subject,
        "tenant_id": dataset.tenant_id,
    }
    request_sha256 = _document_sha256(request_document)
    export_id = (
        "care-export-" + hashlib.sha256(f"{subject}\0{idempotency_key}".encode()).hexdigest()[:32]
    )
    review_failures = _export_review_failures(request)

    async with _claim_export_identity(session, export_id):
        existing = await session.scalar(
            select(DomainEvent)
            .where(
                DomainEvent.aggregate_type == "benchmark_export",
                DomainEvent.aggregate_id == export_id,
            )
            .order_by(DomainEvent.sequence.asc())
            .limit(1)
            .execution_options(skip_windops_access_control=True)
        )
        if existing is not None:
            if existing.payload.get("request_sha256") != request_sha256:
                raise IdempotencyConflictError(
                    "benchmark export idempotency key was reused with different content"
                )
            if existing.event_type == BENCHMARK_EXPORT_DENIED_EVENT_TYPE:
                raise BenchmarkExportReviewError(
                    "external CARE export review requirements were not satisfied"
                )
            content, content_type, file_name, payload_sha256, license_metadata = _render_export(
                request=request,
                dataset=dataset,
                evaluation=evaluation,
                results=results,
                metrics=metrics,
            )
            artifact_sha256 = hashlib.sha256(content).hexdigest()
            if existing.payload.get("artifact_sha256") != artifact_sha256:
                raise IdempotencyConflictError("governed export content changed after audit")
            return GovernedBenchmarkExport(
                export_id=export_id,
                audit_event_id=existing.id,
                content=content,
                content_type=content_type,
                file_name=file_name,
                artifact_sha256=artifact_sha256,
                payload_sha256=payload_sha256,
                license_metadata=license_metadata,
                replayed=True,
            )

        if review_failures:
            audit = append_domain_event(
                session,
                event_type=BENCHMARK_EXPORT_DENIED_EVENT_TYPE,
                aggregate_type="benchmark_export",
                aggregate_id=export_id,
                payload={
                    "schema_version": BENCHMARK_EXPORT_SCHEMA_VERSION,
                    "request_sha256": request_sha256,
                    "tenant_id": dataset.tenant_id,
                    "dataset_version_id": dataset.id,
                    "evaluation_run_id": evaluation.id,
                    "distribution": request.distribution,
                    "format": request.export_format,
                    "review_status": "denied",
                    "review_failures": review_failures,
                    "requested_by": subject,
                },
            )
            await session.flush()
            await session.commit()
            raise BenchmarkExportReviewError(
                "external CARE export review requirements were not satisfied: "
                + ", ".join(review_failures)
            )

        content, content_type, file_name, payload_sha256, license_metadata = _render_export(
            request=request,
            dataset=dataset,
            evaluation=evaluation,
            results=results,
            metrics=metrics,
        )
        artifact_sha256 = hashlib.sha256(content).hexdigest()
        audit = append_domain_event(
            session,
            event_type=BENCHMARK_EXPORT_EVENT_TYPE,
            aggregate_type="benchmark_export",
            aggregate_id=export_id,
            payload={
                "schema_version": BENCHMARK_EXPORT_SCHEMA_VERSION,
                "request_sha256": request_sha256,
                "tenant_id": dataset.tenant_id,
                "dataset_version_id": dataset.id,
                "evaluation_run_id": evaluation.id,
                "distribution": request.distribution,
                "format": request.export_format,
                "truth_included": request.include_truth,
                "review_status": "approved",
                "review": {
                    "attribution_confirmed": request.attribution_confirmed,
                    "license_link_confirmed": request.license_link_confirmed,
                    "share_alike_confirmed": request.share_alike_confirmed,
                    "legal_review_reference": request.legal_review_reference,
                },
                "artifact_sha256": artifact_sha256,
                "payload_sha256": payload_sha256,
                "license": license_metadata,
                "requested_by": subject,
            },
        )
        await session.flush()
        return GovernedBenchmarkExport(
            export_id=export_id,
            audit_event_id=audit.id,
            content=content,
            content_type=content_type,
            file_name=file_name,
            artifact_sha256=artifact_sha256,
            payload_sha256=payload_sha256,
            license_metadata=license_metadata,
            replayed=False,
        )


CleanupLayer = Literal["standard", "quality", "predictions", "reports"]


@dataclass(frozen=True, slots=True)
class CareArtifactCleanupScope:
    dataset_id: str
    dataset_version: str
    dataset_sha256: str
    layer: CleanupLayer
    farm: str | None = None
    event_id: int | None = None
    model_id: str | None = None
    run_id: str | None = None

    def __post_init__(self) -> None:
        if self.layer not in {"standard", "quality", "predictions", "reports"}:
            raise BenchmarkArtifactScopeError("raw or unknown CARE layers cannot be cleaned")
        if (
            self.dataset_id != DATASET_ID
            or self.dataset_version != DATASET_VERSION
            or not _valid_sha256(self.dataset_sha256)
        ):
            raise BenchmarkArtifactScopeError("cleanup dataset identity is not exact CARE v6")
        if self.layer in {"standard", "quality"}:
            if self.farm not in {"A", "B", "C"} or self.event_id is None:
                raise BenchmarkArtifactScopeError(
                    "dataset artifact cleanup requires farm and event"
                )
            if not 0 <= self.event_id <= 94 or self.model_id is not None or self.run_id is not None:
                raise BenchmarkArtifactScopeError("dataset artifact cleanup scope is inconsistent")
        else:
            if (
                not self.model_id
                or not self.run_id
                or self.farm is not None
                or self.event_id is not None
            ):
                raise BenchmarkArtifactScopeError("run artifact cleanup requires model and run IDs")
            for value in (self.model_id, self.run_id):
                parsed = PurePosixPath(value)
                if (
                    parsed.name != value
                    or value in {"", ".", ".."}
                    or "=" in value
                    or "\\" in value
                    or "//" in value
                ):
                    raise BenchmarkArtifactScopeError("cleanup model/run identity is unsafe")

    def object_prefix(self, layout: CareObjectStorageLayout) -> str:
        if self.layer in {"standard", "quality"}:
            return f"{layout.prefixes()[self.layer]}/farm={self.farm}/event={self.event_id}"
        family = "evaluations/" if self.layer == "reports" else ""
        return f"{layout.prefixes()[self.layer]}/{family}model={self.model_id}/run={self.run_id}"

    def document(self, layout: CareObjectStorageLayout) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": BENCHMARK_CLEANUP_SCHEMA_VERSION,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_sha256": self.dataset_sha256,
            "layer": self.layer,
            "farm": self.farm,
            "event_id": self.event_id,
            "model_id": self.model_id,
            "run_id": self.run_id,
            "bucket": layout.bucket,
            "object_prefix": self.object_prefix(layout),
        }
        return {**payload, "scope_sha256": _document_sha256(payload)}


class CareCleanupObjectClient(Protocol):
    def list_objects(self, bucket: str, *, prefix: str, recursive: bool) -> Iterable[Any]: ...

    def stat_object(self, bucket: str, object_name: str) -> Any: ...

    def remove_object(self, bucket: str, object_name: str) -> None: ...


def _apply_care_artifact_cleanup(
    client: CareCleanupObjectClient,
    layout: CareObjectStorageLayout,
    scope: CareArtifactCleanupScope,
    *,
    expected_objects: Mapping[str, str],
    confirmed_scope_sha256: str,
    subject: str,
    reason: str,
) -> dict[str, object]:
    scope_document = scope.document(layout)
    if confirmed_scope_sha256 != scope_document["scope_sha256"]:
        raise BenchmarkArtifactScopeError("cleanup confirmation does not match exact scope")
    if not subject.strip() or not reason.strip():
        raise BenchmarkArtifactScopeError("cleanup subject and reason are required")
    prefix = str(scope_document["object_prefix"]) + "/"
    if not expected_objects or len(expected_objects) > BENCHMARK_CLEANUP_OBJECT_MAX:
        raise BenchmarkArtifactScopeError("cleanup expected object set is empty or unbounded")
    for key, sha256 in expected_objects.items():
        parsed = PurePosixPath(key)
        if (
            not key.startswith(prefix)
            or parsed.is_absolute()
            or ".." in parsed.parts
            or str(parsed) != key
            or "\\" in key
            or "//" in key
            or not _valid_sha256(sha256)
        ):
            raise BenchmarkArtifactScopeError("cleanup expected object escaped its exact scope")

    listed = list(client.list_objects(layout.bucket, prefix=prefix, recursive=True))
    if len(listed) > BENCHMARK_CLEANUP_OBJECT_MAX:
        raise BenchmarkArtifactScopeError("cleanup object listing exceeded its hard bound")
    listed_names = [str(item.object_name) for item in listed]
    if len(listed_names) != len(set(listed_names)) or set(listed_names) != set(expected_objects):
        raise BenchmarkArtifactScopeError("cleanup listing differs from the confirmed object set")
    for object_name in listed_names:
        stored = client.stat_object(layout.bucket, object_name)
        metadata = {str(key).lower(): str(value) for key, value in dict(stored.metadata).items()}
        stored_sha256 = metadata.get("x-amz-meta-sha256") or metadata.get("sha256")
        if stored_sha256 != expected_objects[object_name]:
            raise BenchmarkArtifactScopeError("cleanup object content hash changed after review")

    deleted: list[str] = []
    try:
        for object_name in sorted(listed_names):
            client.remove_object(layout.bucket, object_name)
            deleted.append(object_name)
    except Exception as exc:
        raise BenchmarkArtifactCleanupError(
            "CARE cleanup stopped after a bounded partial failure; audit deleted object list",
            audit_document={
                "schema_version": BENCHMARK_CLEANUP_SCHEMA_VERSION,
                "status": "failed",
                "scope": scope_document,
                "deleted_objects": deleted,
                "deleted_count": len(deleted),
                "failed_object": object_name,
                "expected_objects_sha256": _document_sha256(dict(sorted(expected_objects.items()))),
                "requested_by": subject,
                "reason": reason,
                "raw_layer_deletion_allowed": False,
            },
        ) from exc
    return {
        "schema_version": BENCHMARK_CLEANUP_SCHEMA_VERSION,
        "status": "completed",
        "scope": scope_document,
        "deleted_objects": deleted,
        "deleted_count": len(deleted),
        "expected_objects_sha256": _document_sha256(dict(sorted(expected_objects.items()))),
        "requested_by": subject,
        "reason": reason,
        "raw_layer_deletion_allowed": False,
    }


def append_care_cleanup_audit(
    session: AsyncSession,
    *,
    cleanup_id: str,
    document: Mapping[str, object],
    failed: bool = False,
) -> DomainEvent:
    if not cleanup_id or PurePosixPath(cleanup_id).name != cleanup_id:
        raise BenchmarkArtifactScopeError("cleanup audit identity is unsafe")
    return append_domain_event(
        session,
        event_type=(
            BENCHMARK_CLEANUP_FAILED_EVENT_TYPE if failed else BENCHMARK_CLEANUP_EVENT_TYPE
        ),
        aggregate_type="benchmark_cleanup",
        aggregate_id=cleanup_id,
        payload=dict(document),
    )


async def execute_care_artifact_cleanup(
    session: AsyncSession,
    client: CareCleanupObjectClient,
    layout: CareObjectStorageLayout,
    scope: CareArtifactCleanupScope,
    *,
    cleanup_id: str,
    expected_objects: Mapping[str, str],
    confirmed_scope_sha256: str,
    subject: str,
    reason: str,
) -> dict[str, object]:
    """Run one exact cleanup with durable intent and outcome audit events.

    A started event is committed before the irreversible object-store operation.
    An interrupted or failed cleanup is never retried automatically under the
    same identity because its exact object set must be reviewed again.
    """

    if (
        not cleanup_id
        or PurePosixPath(cleanup_id).name != cleanup_id
        or "\\" in cleanup_id
        or "//" in cleanup_id
    ):
        raise BenchmarkArtifactScopeError("cleanup audit identity is unsafe")
    scope_document = scope.document(layout)
    request_document = {
        "cleanup_id": cleanup_id,
        "scope": scope_document,
        "expected_objects_sha256": _document_sha256(dict(sorted(expected_objects.items()))),
        "confirmed_scope_sha256": confirmed_scope_sha256,
        "requested_by": subject,
        "reason": reason,
    }
    request_sha256 = _document_sha256(request_document)
    existing = await session.scalar(
        select(DomainEvent)
        .where(
            DomainEvent.aggregate_type == "benchmark_cleanup",
            DomainEvent.aggregate_id == cleanup_id,
        )
        .order_by(DomainEvent.sequence.desc())
        .limit(1)
        .execution_options(skip_windops_access_control=True)
    )
    if existing is not None:
        if existing.payload.get("request_sha256") != request_sha256:
            raise IdempotencyConflictError(
                "CARE cleanup identity was reused with different reviewed content"
            )
        if existing.event_type == BENCHMARK_CLEANUP_EVENT_TYPE:
            return dict(existing.payload)
        raise BenchmarkArtifactCleanupError(
            "CARE cleanup requires human reconciliation before a new reviewed cleanup",
            audit_document=existing.payload,
        )

    append_domain_event(
        session,
        event_type=BENCHMARK_CLEANUP_STARTED_EVENT_TYPE,
        aggregate_type="benchmark_cleanup",
        aggregate_id=cleanup_id,
        payload={
            "schema_version": BENCHMARK_CLEANUP_SCHEMA_VERSION,
            "status": "started",
            "request_sha256": request_sha256,
            **request_document,
            "raw_layer_deletion_allowed": False,
        },
    )
    await session.commit()

    try:
        document = await asyncio.to_thread(
            _apply_care_artifact_cleanup,
            client,
            layout,
            scope,
            expected_objects=expected_objects,
            confirmed_scope_sha256=confirmed_scope_sha256,
            subject=subject,
            reason=reason,
        )
    except BenchmarkArtifactCleanupError as exc:
        failed_document = {**exc.audit_document, "request_sha256": request_sha256}
        append_care_cleanup_audit(
            session,
            cleanup_id=cleanup_id,
            document=failed_document,
            failed=True,
        )
        await session.commit()
        exc.audit_document = failed_document
        raise
    except BenchmarkArtifactScopeError as exc:
        failed_document = {
            "schema_version": BENCHMARK_CLEANUP_SCHEMA_VERSION,
            "status": "rejected",
            "scope": scope_document,
            "deleted_objects": [],
            "deleted_count": 0,
            "request_sha256": request_sha256,
            "failure_code": exc.code,
            "requested_by": subject,
            "reason": reason,
            "raw_layer_deletion_allowed": False,
        }
        append_care_cleanup_audit(
            session,
            cleanup_id=cleanup_id,
            document=failed_document,
            failed=True,
        )
        await session.commit()
        raise
    except Exception as exc:
        failed_document = {
            "schema_version": BENCHMARK_CLEANUP_SCHEMA_VERSION,
            "status": "failed",
            "scope": scope_document,
            "deleted_objects": [],
            "deleted_count": 0,
            "request_sha256": request_sha256,
            "failure_code": "OBJECT_STORE_OPERATION_FAILED",
            "requested_by": subject,
            "reason": reason,
            "raw_layer_deletion_allowed": False,
        }
        append_care_cleanup_audit(
            session,
            cleanup_id=cleanup_id,
            document=failed_document,
            failed=True,
        )
        await session.commit()
        raise BenchmarkArtifactCleanupError(
            "CARE cleanup object-store operation failed; the failure was audited",
            audit_document=failed_document,
        ) from exc

    completed_document = {**document, "request_sha256": request_sha256}
    append_care_cleanup_audit(
        session,
        cleanup_id=cleanup_id,
        document=completed_document,
    )
    await session.commit()
    return completed_document


__all__ = [
    "BENCHMARK_CLEANUP_OBJECT_MAX",
    "BENCHMARK_CLEANUP_SCHEMA_VERSION",
    "BENCHMARK_EXPORT_SCHEMA_VERSION",
    "BenchmarkArtifactCleanupError",
    "BenchmarkArtifactScopeError",
    "BenchmarkExportReviewError",
    "CareArtifactCleanupScope",
    "GovernedBenchmarkExport",
    "benchmark_export_allowed",
    "build_governed_benchmark_export",
    "execute_care_artifact_cleanup",
]
