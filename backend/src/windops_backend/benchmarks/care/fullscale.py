from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.metadata
import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from windops_backend.benchmarks.care.anomaly import (
    canonical_anomaly_input_schema,
    canonical_anomaly_output_schema,
)
from windops_backend.benchmarks.care.contract import (
    COLUMN_MAPPING_VERSION,
    DATASET_ID,
    DATASET_VERSION,
    DOI,
    LICENSE_NAME,
    LICENSE_URL,
    METADATA_COLUMNS,
    ZENODO_URL,
    CareContractError,
    verify_care_contract,
)
from windops_backend.benchmarks.care.importer import (
    SOURCE_CONTRACT_URI,
    TRUTH_ACCESS_SCOPE,
    _artifact_reference,
    _publish_json,
    _sha256_file,
    _source_file_record,
    _verify_archive,
    _verify_reference,
    _write_immutable_bytes,
)
from windops_backend.benchmarks.care.licensing import (
    CARE_CREATOR_AFFILIATION,
    CARE_DATASET_CREATORS,
    CARE_RECOMMENDED_CITATION,
    build_care_artifact_license,
    verify_care_artifact_license,
)
from windops_backend.benchmarks.care.pipeline import (
    FEATURE_SET_VERSION,
    PIPELINE_CONTRACT_VERSION,
    QUALITY_RULE_VERSION,
    BenchmarkJobCancelled,
    BenchmarkJobState,
    CareObjectStorageLayout,
    CarePipelineError,
    FileBenchmarkJobControl,
    ImmutableArtifactStore,
    LocalImmutableArtifactStore,
    MinioImmutableArtifactStore,
    convert_care_csv_to_parquet,
)
from windops_backend.benchmarks.care.quality import (
    STATUS_CORROBORATION_RULE_ID,
    ZERO_RUN_RULE_ID,
    StatusPointEvidence,
    StatusSequenceState,
    audit_event_quality,
    evaluate_status_point,
    status_evidence_policy,
    verify_quality_contract,
)
from windops_backend.benchmarks.care.resources import (
    peak_process_resident_bytes,
    trim_process_resident_memory,
)
from windops_backend.benchmarks.care.runtime import (
    care_minio_client,
    get_care_worker_settings,
)
from windops_backend.benchmarks.care.scoring import (
    SCORE_PROTOCOL_VERSION,
    CareEventTruth,
    EvaluationRunSpec,
    FinalCareEvaluator,
    ModelSelectionProvenance,
    PredictionBatch,
    PredictionPoint,
    PredictionTruthVault,
    ThresholdPolicy,
    build_evaluation_artifact,
    build_prediction_artifact,
    verify_prediction_artifact,
)
from windops_backend.benchmarks.care.trust import (
    CareTrustAnchor,
    verify_care_approval_lineage,
    verify_care_source_rebuild,
    verify_embedded_care_approval,
)
from windops_backend.config import get_settings
from windops_backend.db import create_engine, create_session_factory
from windops_backend.operations.backups import minio_client
from windops_backend.schemas import (
    BenchmarkDatasetVersionCreateRequest,
    BenchmarkEvaluationRunCreateRequest,
    BenchmarkEventCreateRequest,
    BenchmarkEventResultCreateRequest,
    BenchmarkFeatureMapCreateRequest,
    BenchmarkFileCreateRequest,
    BenchmarkMetricSnapshotCreateRequest,
    BenchmarkQualityReportCreateRequest,
    ModelRegisterRequest,
)
from windops_backend.services.benchmark_metadata import (
    complete_evaluation_run,
    get_or_create_evaluation_run,
    record_event_result,
    record_metric_snapshot,
    register_benchmark_event,
    register_benchmark_file,
    register_dataset_version,
    register_feature_map,
    register_quality_report,
)
from windops_backend.services.models import register_model

FULL_SCALE_IMPORT_VERSION = "care-v6-full-scale-import-v5"
FULL_SCALE_IMPORT_SCHEMA_VERSION = "care-v6-full-scale-import-manifest-v1"
FULL_SCALE_EVENT_SCHEMA_VERSION = "care-v6-full-scale-event-v1"
FULL_SCALE_EVALUATION_VERSION = "care-v6-within-farm-loao-v7"
FULL_SCALE_EVALUATION_SCHEMA_VERSION = "care-v6-full-scale-evaluation-manifest-v1"
FULL_SCALE_FOLD_SCHEMA_VERSION = "care-v6-within-farm-fold-v1"
FULL_SCALE_MODEL_SCHEMA_VERSION = "care-v6-within-farm-zscore-model-v3"
FULL_SCALE_PREDICTION_FREEZE_SCHEMA_VERSION = "care-v6-prediction-freeze-v1"
FULL_SCALE_RESOURCE_POLICY_VERSION = "care-v6-full-scale-resource-policy-v5"
FULL_SCALE_OPERATIONAL_POLICY_VERSION = "care-v6-full-scale-operational-policy-v4"
FULL_SCALE_PROTOCOL_FROZEN_AT = "2026-08-27T00:00:00+00:00"
FULL_SCALE_THRESHOLD = 4.506536091667749
FULL_SCALE_THRESHOLD_VERSION = "care-v6-within-farm-loao-threshold-v1"
FULL_SCALE_THRESHOLD_RUN_ID = "care-a-minimal-zscore-train-calibration"
FULL_SCALE_MODEL_VERSION = "1.2.0"
FULL_SCALE_QUALITY_MASK_POLICY_VERSION = "care-v6-model-quality-mask-apply-v1"
FULL_SCALE_TRAIN_STATUS_IDS = ("0",)
FULL_SCALE_STAGE_ORDER = ("A", "C", "B")
MIN_REPLAY_WRITE_ROWS_PER_SECOND = 50.0


class CareFullScaleError(CarePipelineError):
    """Raised when the CARE full-scale release boundary fails closed."""


class CareFullScaleResourceError(CareFullScaleError):
    """Raised when measured work exceeds a preregistered resource limit."""


@dataclass(frozen=True, slots=True)
class FullScaleExpectedCounts:
    event_count: int
    farm_event_counts: tuple[tuple[str, int], ...]
    farm_signal_counts: tuple[tuple[str, int], ...]
    asset_count: int
    anomaly_count: int
    normal_count: int
    row_count: int

    def __post_init__(self) -> None:
        if self.event_count < 1 or self.asset_count < 1 or self.row_count < 1:
            raise CareFullScaleError("full-scale expected counts must be positive")
        if self.anomaly_count + self.normal_count != self.event_count:
            raise CareFullScaleError("full-scale expected labels do not total the events")
        if tuple(farm for farm, _ in self.farm_event_counts) != FULL_SCALE_STAGE_ORDER:
            raise CareFullScaleError("full-scale expected farm counts must follow A, C, B")
        if {farm for farm, _ in self.farm_signal_counts} != {"A", "B", "C"}:
            raise CareFullScaleError("full-scale signal expectations must cover A, B, and C")

    def to_document(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "farm_event_counts": dict(self.farm_event_counts),
            "farm_signal_counts": dict(self.farm_signal_counts),
            "farm_namespaced_asset_count": self.asset_count,
            "anomaly_event_count": self.anomaly_count,
            "normal_event_count": self.normal_count,
            "row_count": self.row_count,
        }


CARE_V6_FULL_SCALE_COUNTS = FullScaleExpectedCounts(
    event_count=95,
    farm_event_counts=(("A", 22), ("C", 58), ("B", 15)),
    farm_signal_counts=(("A", 81), ("B", 252), ("C", 952)),
    asset_count=36,
    anomaly_count=45,
    normal_count=50,
    row_count=5_242_948,
)


@dataclass(frozen=True, slots=True)
class FullScaleResourceLimits:
    max_import_runtime_seconds: float = 43_200.0
    max_evaluation_runtime_seconds: float = 21_600.0
    max_peak_record_batch_bytes: int = 16 * 1024 * 1024
    max_peak_arrow_allocated_bytes: int = 512 * 1024 * 1024
    max_peak_process_resident_bytes: int = 1024 * 1024 * 1024
    csv_block_size_bytes: int = 1024 * 1024
    max_import_storage_bytes: int = 64 * 1024 * 1024 * 1024
    max_evaluation_storage_bytes: int = 8 * 1024 * 1024 * 1024
    min_import_rows_per_second: float = 100.0
    max_prediction_points: int = 281_249
    parquet_row_group_size: int = 8192
    replay_batch_rows: int = 1000
    catalog_event_page_rows: int = 64
    curve_response_points: int = 512
    frontend_api_response_bytes: int = 512 * 1024
    query_p95_milliseconds: float = 500.0

    def __post_init__(self) -> None:
        for name, value in self.to_document().items():
            if name == "policy_version":
                continue
            if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
                raise CareFullScaleError(f"full-scale resource limit {name} must be positive")

    def to_document(self) -> dict[str, Any]:
        return {
            "policy_version": FULL_SCALE_RESOURCE_POLICY_VERSION,
            "max_import_runtime_seconds": self.max_import_runtime_seconds,
            "max_evaluation_runtime_seconds": self.max_evaluation_runtime_seconds,
            "max_peak_record_batch_bytes": self.max_peak_record_batch_bytes,
            "max_peak_arrow_allocated_bytes": self.max_peak_arrow_allocated_bytes,
            "max_peak_process_resident_bytes": self.max_peak_process_resident_bytes,
            "csv_block_size_bytes": self.csv_block_size_bytes,
            "max_import_storage_bytes": self.max_import_storage_bytes,
            "max_evaluation_storage_bytes": self.max_evaluation_storage_bytes,
            "min_import_rows_per_second": self.min_import_rows_per_second,
            "max_prediction_points": self.max_prediction_points,
            "parquet_row_group_size": self.parquet_row_group_size,
            "replay_batch_rows": self.replay_batch_rows,
            "catalog_event_page_rows": self.catalog_event_page_rows,
            "curve_response_points": self.curve_response_points,
            "frontend_api_response_bytes": self.frontend_api_response_bytes,
            "query_p95_milliseconds": self.query_p95_milliseconds,
        }


DEFAULT_FULL_SCALE_RESOURCE_LIMITS = FullScaleResourceLimits()


@dataclass(frozen=True, slots=True)
class _FarmContract:
    farm: str
    events: tuple[Mapping[str, Any], ...]
    mappings: tuple[Mapping[str, Any], ...]
    semantics: tuple[Mapping[str, Any], ...]
    selected_columns: tuple[str, ...]
    model_input_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _FullScaleContract:
    farms: tuple[_FarmContract, ...]
    events: tuple[Mapping[str, Any], ...]
    source_dataset_sha256: str
    expected_counts: FullScaleExpectedCounts


@dataclass(frozen=True, slots=True)
class FullScaleImportResult:
    manifest_path: Path
    manifest: Mapping[str, Any]
    manifest_file_sha256: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class FullScaleEvaluationResult:
    manifest_path: Path
    manifest: Mapping[str, Any]
    manifest_file_sha256: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class FullScaleImportRegistration:
    created_count: int
    replayed_count: int
    dataset_version_id: str
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FullScaleEvaluationRegistration:
    created_count: int
    replayed_count: int
    model_ids: tuple[str, ...]
    evaluation_run_ids: tuple[str, ...]


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CareFullScaleError("full-scale artifacts must be finite canonical JSON") from exc


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _resolved_artifact_root(path: Path) -> Path:
    return path.resolve()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not token or len(token) > 48:
        raise CareFullScaleError("full-scale asset identity is not a portable token")
    return token


def _license(
    contract: _FullScaleContract,
    *,
    artifact_type: str,
    changes_made: str,
    source_artifact_sha256: str,
    extra_versions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    versions = {
        "column_mapping": COLUMN_MAPPING_VERSION,
        "feature_set": FEATURE_SET_VERSION,
        "full_scale": FULL_SCALE_IMPORT_VERSION,
        "pipeline": PIPELINE_CONTRACT_VERSION,
        "quality_rules": QUALITY_RULE_VERSION,
    }
    versions.update(extra_versions or {})
    return build_care_artifact_license(
        artifact_type=artifact_type,
        changes_made=changes_made,
        source_dataset_sha256=contract.source_dataset_sha256,
        source_artifact_sha256=source_artifact_sha256,
        transformation_versions=versions,
    )


def _verify_license(value: Mapping[str, Any]) -> None:
    metadata = value.get("license")
    if not isinstance(metadata, Mapping):
        raise CareFullScaleError("full-scale artifact is missing license metadata")
    versions = metadata.get("transformation_versions")
    if not isinstance(versions, Mapping):
        raise CareFullScaleError("full-scale license transformation versions are malformed")
    verify_care_artifact_license(
        metadata,
        artifact_type=str(metadata.get("artifact_type", "")),
        source_dataset_sha256=str(metadata.get("source_dataset_sha256", "")),
        source_artifact_sha256=str(metadata.get("source_artifact_sha256", "")),
        transformation_versions={str(key): str(item) for key, item in versions.items()},
    )


def _build_contract(
    source_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    *,
    expected_counts: FullScaleExpectedCounts,
) -> _FullScaleContract:
    verify_care_contract(source_manifest)
    verify_quality_contract(quality_contract)
    if quality_contract.get("source_manifest_sha256") != source_manifest["manifest_sha256"]:
        raise CareFullScaleError("quality contract does not belong to the source manifest")
    if (
        source_manifest.get("dataset_id") != DATASET_ID
        or source_manifest.get("dataset_version") != DATASET_VERSION
    ):
        raise CareFullScaleError("full-scale execution only accepts CARE v6")
    source = source_manifest.get("source")
    if not isinstance(source, Mapping) or not isinstance(source.get("zip"), Mapping):
        raise CareFullScaleError("full-scale source archive identity is missing")
    source_dataset_sha256 = source["zip"].get("sha256")
    if not _is_sha256(source_dataset_sha256) or source.get("read_only") is not True:
        raise CareFullScaleError("full-scale source must be immutable and read-only")

    events_raw = source_manifest.get("events")
    source_farms = source_manifest.get("farms")
    quality_farms = quality_contract.get("farms")
    if (
        not isinstance(events_raw, list)
        or not isinstance(source_farms, list)
        or not isinstance(quality_farms, list)
    ):
        raise CareFullScaleError("full-scale control contracts are malformed")
    source_farm_by_id = {
        str(item.get("farm")): item for item in source_farms if isinstance(item, Mapping)
    }
    quality_farm_by_id = {
        str(item.get("farm")): item for item in quality_farms if isinstance(item, Mapping)
    }
    expected_farm_events = dict(expected_counts.farm_event_counts)
    expected_signals = dict(expected_counts.farm_signal_counts)
    farm_contracts: list[_FarmContract] = []
    ordered_events: list[Mapping[str, Any]] = []
    for farm in FULL_SCALE_STAGE_ORDER:
        source_farm = source_farm_by_id.get(farm)
        quality_farm = quality_farm_by_id.get(farm)
        if not isinstance(source_farm, Mapping) or not isinstance(quality_farm, Mapping):
            raise CareFullScaleError(f"full-scale farm {farm} mapping is missing")
        mappings = tuple(
            item for item in source_farm.get("column_mappings", []) if isinstance(item, Mapping)
        )
        semantics = tuple(
            item for item in quality_farm.get("features", []) if isinstance(item, Mapping)
        )
        if len(mappings) != expected_signals[farm] or len(semantics) != len(mappings):
            raise CareFullScaleError(f"full-scale farm {farm} signal count is inconsistent")
        mapping_columns = tuple(str(item.get("source_column", "")) for item in mappings)
        semantic_columns = tuple(str(item.get("source_column", "")) for item in semantics)
        if mapping_columns != semantic_columns or len(set(mapping_columns)) != len(mappings):
            raise CareFullScaleError(f"full-scale farm {farm} mappings are not one-to-one")
        model_inputs = tuple(
            str(item["source_column"])
            for item in semantics
            if item.get("enabled_by_default") is True
        )
        if not model_inputs or any(
            item.get("statistic") != "average"
            for item in semantics
            if item.get("enabled_by_default") is True
        ):
            raise CareFullScaleError(f"full-scale farm {farm} model inputs are not approved Avg")
        farm_events = tuple(
            sorted(
                (
                    item
                    for item in events_raw
                    if isinstance(item, Mapping) and item.get("farm") == farm
                ),
                key=lambda item: int(item["event_id"]),
            )
        )
        if len(farm_events) != expected_farm_events[farm]:
            raise CareFullScaleError(f"full-scale farm {farm} event count is inconsistent")
        ordered_events.extend(farm_events)
        farm_contracts.append(
            _FarmContract(
                farm=farm,
                events=farm_events,
                mappings=mappings,
                semantics=semantics,
                selected_columns=(*METADATA_COLUMNS, *mapping_columns),
                model_input_columns=model_inputs,
            )
        )

    event_ids = [int(item["event_id"]) for item in ordered_events]
    labels = [str(item["event_label"]) for item in ordered_events]
    assets = {(str(item["farm"]), str(item["source_asset_id"])) for item in ordered_events}
    actual = {
        "event_count": len(ordered_events),
        "farm_namespaced_asset_count": len(assets),
        "anomaly_event_count": labels.count("anomaly"),
        "normal_event_count": labels.count("normal"),
        "row_count": sum(int(item["row_count"]) for item in ordered_events),
    }
    expected = expected_counts.to_document()
    for key in (
        "event_count",
        "farm_namespaced_asset_count",
        "anomaly_event_count",
        "normal_event_count",
        "row_count",
    ):
        if actual[key] != expected[key]:
            raise CareFullScaleError(f"full-scale {key} differs from the frozen count")
    if len(event_ids) != len(set(event_ids)):
        raise CareFullScaleError("full-scale event IDs are not globally unique")
    return _FullScaleContract(
        farms=tuple(farm_contracts),
        events=tuple(ordered_events),
        source_dataset_sha256=str(source_dataset_sha256),
        expected_counts=expected_counts,
    )


def build_full_scale_plan(
    source_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    *,
    expected_counts: FullScaleExpectedCounts = CARE_V6_FULL_SCALE_COUNTS,
) -> dict[str, Any]:
    """Freeze A -> C -> B execution before any derived value is written."""

    contract = _build_contract(
        source_manifest,
        quality_contract,
        expected_counts=expected_counts,
    )
    payload = {
        "schema_version": "care-v6-full-scale-plan-v1",
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "quality_contract_sha256": quality_contract["quality_contract_sha256"],
        "stage_order": list(FULL_SCALE_STAGE_ORDER),
        "expected_counts": expected_counts.to_document(),
        "stages": [
            {
                "stage_index": index,
                "farm": farm.farm,
                "event_ids": [int(event["event_id"]) for event in farm.events],
                "event_count": len(farm.events),
                "signal_column_count": len(farm.mappings),
                "model_input_count": len(farm.model_input_columns),
                "farm_namespaced_assets": sorted(
                    {f"{farm.farm}:{event['source_asset_id']}" for event in farm.events}
                ),
                "row_count": sum(int(event["row_count"]) for event in farm.events),
            }
            for index, farm in enumerate(contract.farms)
        ],
        "full_wide_parquet_required": True,
        "timescaledb_full_signal_expansion_allowed": False,
        "cross_farm_protocol": {
            "status": "disabled",
            "reason": "canonical ontology and recorded human review are not complete",
            "human_review_ids": [],
        },
    }
    return {**payload, "plan_sha256": _canonical_hash(payload)}


def _event_summary_path(output_root: Path, *, farm: str, event_id: int) -> Path:
    return (
        output_root
        / DATASET_ID
        / DATASET_VERSION
        / "reports"
        / "full-import"
        / "events"
        / f"farm={farm}"
        / f"event={event_id}.json"
    )


def _verify_event_summary(
    value: Mapping[str, Any],
    *,
    output_root: Path,
    source_event: Mapping[str, Any],
    farm_contract: _FarmContract,
) -> None:
    actual = value.get("document_sha256")
    unsigned = {key: item for key, item in value.items() if key != "document_sha256"}
    if not _is_sha256(actual) or _canonical_hash(unsigned) != actual:
        raise CareFullScaleError("full-scale event summary hash is invalid")
    if (
        value.get("schema_version") != FULL_SCALE_EVENT_SCHEMA_VERSION
        or value.get("farm") != farm_contract.farm
        or value.get("event_id") != source_event["event_id"]
        or value.get("source_asset_id") != source_event["source_asset_id"]
        or value.get("source_file_sha256") != source_event["file_sha256"]
        or value.get("row_count") != source_event["row_count"]
        or value.get("signal_column_count") != len(farm_contract.mappings)
        or value.get("model_input_count") != len(farm_contract.model_input_columns)
        or value.get("source_unchanged") is not True
    ):
        raise CareFullScaleError("full-scale event summary identity is inconsistent")
    parquet = value.get("parquet")
    quality = value.get("quality")
    truth = value.get("restricted_truth")
    if (
        not isinstance(parquet, Mapping)
        or not isinstance(quality, Mapping)
        or not isinstance(truth, Mapping)
    ):
        raise CareFullScaleError("full-scale event references are malformed")
    for reference in (
        parquet.get("data"),
        parquet.get("manifest"),
        quality.get("report"),
        quality.get("mask"),
        truth.get("artifact"),
    ):
        if not isinstance(reference, Mapping):
            raise CareFullScaleError("full-scale event artifact reference is malformed")
        _verify_reference(output_root, reference)
    _verify_license(value)


def _load_existing_event_summary(
    path: Path,
    *,
    output_root: Path,
    source_event: Mapping[str, Any],
    farm_contract: _FarmContract,
) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise CareFullScaleError("full-scale event summary root must be an object")
    _verify_event_summary(
        raw,
        output_root=output_root,
        source_event=source_event,
        farm_contract=farm_contract,
    )
    return raw


def _resource_max(event_summaries: Sequence[Mapping[str, Any]], path: Sequence[str]) -> float:
    values: list[float] = []
    for event in event_summaries:
        current: Any = event
        for part in path:
            current = current[part]
        values.append(float(current))
    return max(values, default=0.0)


def _audit_with_process_resources(
    source_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    dataset_root: Path,
    event_id: int,
) -> tuple[dict[str, Any], dict[str, int | float]]:
    started = time.perf_counter()
    report = audit_event_quality(source_manifest, quality_contract, dataset_root, event_id)
    elapsed = time.perf_counter() - started
    return report, {
        "elapsed_seconds": elapsed,
        "peak_process_resident_bytes": peak_process_resident_bytes(),
        "rows_per_second": float(report["row_count"]) / elapsed if elapsed > 0 else 0.0,
    }


def _enforce_import_resources(
    *,
    event_summaries: Sequence[Mapping[str, Any]],
    elapsed_seconds: float,
    storage_bytes: int,
    row_count: int,
    limits: FullScaleResourceLimits,
) -> dict[str, Any]:
    peak_batch = int(
        _resource_max(event_summaries, ("resource_stats", "parquet", "peak_record_batch_bytes"))
    )
    peak_arrow = int(
        _resource_max(
            event_summaries,
            ("resource_stats", "parquet", "peak_arrow_allocated_bytes"),
        )
    )
    peak_resident = int(
        _resource_max(
            event_summaries,
            ("resource_stats", "quality", "peak_process_resident_bytes"),
        )
    )
    throughput = row_count / elapsed_seconds if elapsed_seconds > 0 else 0.0
    actual = {
        "elapsed_seconds": elapsed_seconds,
        "storage_bytes": storage_bytes,
        "row_count": row_count,
        "rows_per_second": throughput,
        "peak_record_batch_bytes": peak_batch,
        "peak_arrow_allocated_bytes": peak_arrow,
        "peak_process_resident_bytes": peak_resident,
    }
    violations = []
    if elapsed_seconds > limits.max_import_runtime_seconds:
        violations.append("max_import_runtime_seconds")
    if storage_bytes > limits.max_import_storage_bytes:
        violations.append("max_import_storage_bytes")
    if peak_batch > limits.max_peak_record_batch_bytes:
        violations.append("max_peak_record_batch_bytes")
    if peak_arrow > limits.max_peak_arrow_allocated_bytes:
        violations.append("max_peak_arrow_allocated_bytes")
    if peak_resident > limits.max_peak_process_resident_bytes:
        violations.append("max_peak_process_resident_bytes")
    if throughput < limits.min_import_rows_per_second:
        violations.append("min_import_rows_per_second")
    if violations:
        raise CareFullScaleResourceError(
            f"full-scale import exceeded preregistered resources: {', '.join(violations)}"
        )
    return {**actual, "limits_passed": True, "violations": []}


def build_full_scale_import(
    source_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    dataset_root: Path,
    output_root: Path,
    *,
    source_archive_path: Path | None = None,
    artifact_store: ImmutableArtifactStore | None = None,
    job_id: str = "care-v6-full-import",
    state_path: Path | None = None,
    stop_after_events: int | None = None,
    expected_counts: FullScaleExpectedCounts = CARE_V6_FULL_SCALE_COUNTS,
    resource_limits: FullScaleResourceLimits = DEFAULT_FULL_SCALE_RESOURCE_LIMITS,
    trust_anchor: CareTrustAnchor | None = None,
) -> FullScaleImportResult:
    """Create recoverable full-signal artifacts in the mandatory A -> C -> B order."""

    dataset_root = dataset_root.resolve(strict=True)
    try:
        approved_lineage = verify_care_source_rebuild(
            source_manifest,
            quality_contract,
            dataset_root,
            source_archive_path,
            trust_anchor=trust_anchor,
        )
    except CareContractError as exc:
        raise CareFullScaleError(str(exc)) from exc
    contract = _build_contract(
        source_manifest,
        quality_contract,
        expected_counts=expected_counts,
    )
    plan = build_full_scale_plan(
        source_manifest,
        quality_contract,
        expected_counts=expected_counts,
    )
    output_root = output_root.resolve()
    if output_root == dataset_root or output_root.is_relative_to(dataset_root):
        raise CareFullScaleError("full-scale output must be outside the read-only dataset")
    if source_archive_path is not None:
        source_archive_path = source_archive_path.resolve(strict=True)
        if output_root == source_archive_path or output_root.is_relative_to(source_archive_path):
            raise CareFullScaleError("full-scale output must be outside the source archive")
    manifest_path = (
        output_root / DATASET_ID / DATASET_VERSION / "reports" / "full-import" / "manifest.json"
    )
    if manifest_path.exists():
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise CareFullScaleError("full-scale import manifest root must be an object")
        verify_full_scale_import_manifest(
            raw,
            output_root=output_root,
            source_manifest=source_manifest,
            quality_contract=quality_contract,
            expected_counts=expected_counts,
            resource_limits=resource_limits,
            trust_anchor=trust_anchor,
        )
        return FullScaleImportResult(manifest_path, raw, _sha256_file(manifest_path), True)

    state_file = state_path or output_root / ".state" / f"{job_id}.json"
    job_control = FileBenchmarkJobControl(
        state_file,
        BenchmarkJobState.pending(job_id, "import"),
    )
    state = job_control.start_attempt()
    if state.status == "cancelled":
        raise BenchmarkJobCancelled("full-scale import was cancelled before restart")
    archive_before = (
        _verify_archive(source_archive_path, source_manifest)
        if source_archive_path is not None
        else None
    )
    layout = CareObjectStorageLayout()
    started = time.perf_counter()
    event_summaries: list[Mapping[str, Any]] = []
    mapping_references: dict[str, Mapping[str, Any]] = {}
    newly_completed = 0
    try:
        for farm_contract in contract.farms:
            semantic_by_column = {
                str(item["source_column"]): item for item in farm_contract.semantics
            }
            mapping_payload = {
                "schema_version": "care-v6-full-column-mapping-artifact-v1",
                "dataset_id": DATASET_ID,
                "dataset_version": DATASET_VERSION,
                "farm": farm_contract.farm,
                "mapping_version": COLUMN_MAPPING_VERSION,
                "source_manifest_sha256": source_manifest["manifest_sha256"],
                "mapping_count": len(farm_contract.mappings),
                "approved_model_input_count": len(farm_contract.model_input_columns),
                "approved_model_input_columns": list(farm_contract.model_input_columns),
                "mappings": [
                    {
                        **dict(mapping),
                        "quality_semantics": dict(
                            semantic_by_column[str(mapping["source_column"])]
                        ),
                    }
                    for mapping in farm_contract.mappings
                ],
                "license": _license(
                    contract,
                    artifact_type="full-column-mapping",
                    changes_made=(
                        "Combined every mapped signal with normalized quality and unit "
                        "semantics; no source values were copied or modified."
                    ),
                    source_artifact_sha256=str(source_manifest["manifest_sha256"]),
                ),
            }
            _, mapping_reference = _publish_json(
                output_root=output_root,
                local_path=(
                    output_root
                    / DATASET_ID
                    / DATASET_VERSION
                    / "quality"
                    / "mappings"
                    / f"farm={farm_contract.farm}"
                    / "full-column-mapping.json"
                ),
                payload=mapping_payload,
                object_key_prefix=(
                    f"{layout.quality_prefix}/mappings/farm={farm_contract.farm}/full-column-mapping"
                ),
                artifact_store=artifact_store,
            )
            mapping_references[farm_contract.farm] = mapping_reference

            for source_event in farm_contract.events:
                job_control.cancellation_point()
                event_id = int(source_event["event_id"])
                summary_path = _event_summary_path(
                    output_root,
                    farm=farm_contract.farm,
                    event_id=event_id,
                )
                existing = _load_existing_event_summary(
                    summary_path,
                    output_root=output_root,
                    source_event=source_event,
                    farm_contract=farm_contract,
                )
                if existing is not None:
                    event_summaries.append(existing)
                    job_control.heartbeat(
                        completed=len(event_summaries),
                        total=len(contract.events),
                        current_file=str(source_event["relative_path"]),
                        checkpoint_path=str(summary_path),
                        resource_stats={"resumed_event_count": len(event_summaries)},
                    )
                    continue

                source_path = (dataset_root / str(source_event["relative_path"])).resolve(
                    strict=True
                )
                if not source_path.is_relative_to(dataset_root):
                    raise CareFullScaleError("full-scale event escaped the dataset root")
                source_before = _sha256_file(source_path)
                if source_before != source_event["file_sha256"]:
                    raise CareFullScaleError(f"event {event_id} differs from the manifest")
                parquet = convert_care_csv_to_parquet(
                    source_path,
                    output_root,
                    job_id=f"care-v6-{farm_contract.farm.lower()}-{event_id}-full",
                    farm=farm_contract.farm,
                    event_id=event_id,
                    artifact_store=artifact_store,
                    object_layout=layout,
                    expected_source_sha256=source_before,
                    source_dataset_sha256=contract.source_dataset_sha256,
                    selected_columns=farm_contract.selected_columns,
                    model_input_columns=farm_contract.model_input_columns,
                    csv_block_size_bytes=resource_limits.csv_block_size_bytes,
                )
                parquet_manifest = json.loads(parquet.manifest_path.read_text(encoding="utf-8"))
                if (
                    parquet.row_count != int(source_event["row_count"])
                    or tuple(parquet_manifest["columns"]) != farm_contract.selected_columns
                    or tuple(parquet_manifest["model_input_columns"])
                    != farm_contract.model_input_columns
                ):
                    raise CareFullScaleError(f"event {event_id} Parquet identity is inconsistent")

                if not trim_process_resident_memory():
                    raise CareFullScaleError(
                        "full-scale worker could not trim released resident memory"
                    )

                audit, quality_resources = _audit_with_process_resources(
                    source_manifest,
                    quality_contract,
                    dataset_root,
                    event_id,
                )
                if (
                    int(audit["row_count"]) != int(source_event["row_count"])
                    or audit["split_counts"] != source_event["split_counts"]
                    or len(audit["feature_summaries"]) != len(farm_contract.mappings)
                ):
                    raise CareFullScaleError(f"event {event_id} quality identity is inconsistent")
                event_dir = (
                    output_root
                    / DATASET_ID
                    / DATASET_VERSION
                    / "quality"
                    / f"farm={farm_contract.farm}"
                    / f"event={event_id}"
                )
                source_quality_hash = str(audit["quality_report_sha256"])
                mask_payload = {
                    "schema_version": "care-v6-quality-mask-artifact-v1",
                    "dataset_id": DATASET_ID,
                    "dataset_version": DATASET_VERSION,
                    "farm": farm_contract.farm,
                    "event_id": event_id,
                    "source_event_file_sha256": source_before,
                    "source_quality_report_sha256": source_quality_hash,
                    "quality_rule_version": QUALITY_RULE_VERSION,
                    "raw_values_modified": False,
                    "mask_count": len(audit["quality_mask_ranges"]),
                    "quality_mask_ranges": audit["quality_mask_ranges"],
                    "license": _license(
                        contract,
                        artifact_type="quality-mask",
                        changes_made=(
                            "Extracted sparse quality findings into a separate mask; all "
                            "source values remain unchanged in the full standard artifact."
                        ),
                        source_artifact_sha256=source_before,
                    ),
                }
                _, mask_reference = _publish_json(
                    output_root=output_root,
                    local_path=event_dir / "quality-mask.json",
                    payload=mask_payload,
                    object_key_prefix=(
                        f"{layout.quality_prefix}/farm={farm_contract.farm}/event={event_id}/quality-mask"
                    ),
                    artifact_store=artifact_store,
                )
                report_payload = {
                    key: item
                    for key, item in audit.items()
                    if key not in {"quality_mask_ranges", "quality_report_sha256"}
                }
                report_payload.update(
                    {
                        "schema_version": "care-v6-quality-report-artifact-v1",
                        "source_quality_report_sha256": source_quality_hash,
                        "quality_mask_reference": mask_reference,
                        "license": _license(
                            contract,
                            artifact_type="quality-report",
                            changes_made=(
                                "Computed deterministic full-signal quality summaries and "
                                "published sparse findings as a separate mask."
                            ),
                            source_artifact_sha256=source_before,
                        ),
                    }
                )
                _, report_reference = _publish_json(
                    output_root=output_root,
                    local_path=event_dir / "quality-report.json",
                    payload=report_payload,
                    object_key_prefix=(
                        f"{layout.quality_prefix}/farm={farm_contract.farm}/event={event_id}/quality-report"
                    ),
                    artifact_store=artifact_store,
                )
                truth_payload = {
                    "schema_version": "care-v6-restricted-event-truth-v1",
                    "dataset_id": DATASET_ID,
                    "dataset_version": DATASET_VERSION,
                    "farm": farm_contract.farm,
                    "event_id": event_id,
                    "source_asset_id": source_event["source_asset_id"],
                    "access_scope": TRUTH_ACCESS_SCOPE,
                    "model_input_allowed": False,
                    "event_label": source_event["event_label"],
                    "event_start": source_event["event_start"],
                    "event_end": source_event["event_end"],
                    "event_start_id": source_event["event_start_id"],
                    "event_end_id": source_event["event_end_id"],
                    "event_description": source_event["event_description"],
                    "source_event_file_sha256": source_before,
                    "license": _license(
                        contract,
                        artifact_type="restricted-evaluation-truth",
                        changes_made=(
                            "Copied event truth into an evaluation-only artifact kept apart "
                            "from full Parquet, training, calibration, and predictions."
                        ),
                        source_artifact_sha256=source_before,
                    ),
                }
                _, truth_reference = _publish_json(
                    output_root=output_root,
                    local_path=event_dir / "restricted-truth.json",
                    payload=truth_payload,
                    object_key_prefix=(
                        f"{layout.quality_prefix}/restricted-truth/farm={farm_contract.farm}/event={event_id}/truth"
                    ),
                    artifact_store=artifact_store,
                )
                if _sha256_file(source_path) != source_before:
                    raise CareFullScaleError(f"event {event_id} source changed during import")
                source_file = _source_file_record(
                    source_manifest,
                    str(source_event["relative_path"]),
                )
                parquet_manifest_hash = _sha256_file(parquet.manifest_path)
                event_payload = {
                    "schema_version": FULL_SCALE_EVENT_SCHEMA_VERSION,
                    "dataset_id": DATASET_ID,
                    "dataset_version": DATASET_VERSION,
                    "farm": farm_contract.farm,
                    "event_id": event_id,
                    "source_asset_id": source_event["source_asset_id"],
                    "logical_asset_id": (
                        f"CARE-{farm_contract.farm}-{source_event['source_asset_id']}"
                    ),
                    "source_relative_path": source_event["relative_path"],
                    "source_size_bytes": source_file["size_bytes"],
                    "source_file_sha256": source_before,
                    "source_schema_sha256": source_event["schema_sha256"],
                    "row_count": source_event["row_count"],
                    "source_row_id_min": source_event["source_row_id_min"],
                    "source_row_id_max": source_event["source_row_id_max"],
                    "split_counts": source_event["split_counts"],
                    "signal_column_count": len(farm_contract.mappings),
                    "model_input_count": len(farm_contract.model_input_columns),
                    "parquet": {
                        "data": _artifact_reference(
                            output_root=output_root,
                            path=parquet.local_path,
                            artifact_uri=parquet.artifact_uri,
                            file_sha256=parquet.content_sha256,
                        ),
                        "manifest": _artifact_reference(
                            output_root=output_root,
                            path=parquet.manifest_path,
                            artifact_uri=parquet.manifest_path.resolve().as_uri(),
                            file_sha256=parquet_manifest_hash,
                            document_sha256=str(parquet_manifest["manifest_sha256"]),
                        ),
                        "schema_sha256": parquet.schema_sha256,
                        "row_group_count": parquet.row_group_count,
                        "column_count": len(farm_contract.selected_columns),
                    },
                    "quality": {
                        "source_quality_report_sha256": source_quality_hash,
                        "feature_summary_count": len(audit["feature_summaries"]),
                        "mask_count": len(audit["quality_mask_ranges"]),
                        "report": report_reference,
                        "mask": mask_reference,
                    },
                    "restricted_truth": {
                        "access_scope": TRUTH_ACCESS_SCOPE,
                        "artifact": truth_reference,
                    },
                    "resource_stats": {
                        "parquet": {
                            "elapsed_seconds": parquet.elapsed_seconds,
                            "peak_record_batch_bytes": parquet.peak_record_batch_bytes,
                            "peak_arrow_allocated_bytes": parquet.peak_arrow_allocated_bytes,
                            "rows_per_second": (
                                parquet.row_count / parquet.elapsed_seconds
                                if parquet.elapsed_seconds > 0
                                else 0.0
                            ),
                        },
                        "quality": quality_resources,
                    },
                    "source_unchanged": True,
                    "license": _license(
                        contract,
                        artifact_type="full-scale-event-summary",
                        changes_made=(
                            "Recorded immutable full-signal Parquet, quality, and isolated "
                            "truth references for one event without modifying the source."
                        ),
                        source_artifact_sha256=source_before,
                    ),
                }
                event_document = {
                    **event_payload,
                    "document_sha256": _canonical_hash(event_payload),
                }
                content = (
                    json.dumps(event_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8")
                _write_immutable_bytes(summary_path, content)
                _verify_event_summary(
                    event_document,
                    output_root=output_root,
                    source_event=source_event,
                    farm_contract=farm_contract,
                )
                event_summaries.append(event_document)
                newly_completed += 1
                if not trim_process_resident_memory():
                    raise CareFullScaleError(
                        "full-scale worker could not trim completed event memory"
                    )
                job_control.heartbeat(
                    completed=len(event_summaries),
                    total=len(contract.events),
                    current_file=str(source_event["relative_path"]),
                    checkpoint_path=str(summary_path),
                    resource_stats={
                        "completed_event_count": len(event_summaries),
                        "last_peak_record_batch_bytes": parquet.peak_record_batch_bytes,
                        "last_peak_arrow_allocated_bytes": parquet.peak_arrow_allocated_bytes,
                    },
                )
                if stop_after_events is not None and newly_completed >= stop_after_events:
                    job_control.request_cancel()
                    job_control.cancellation_point()

        archive_after = (
            _verify_archive(source_archive_path, source_manifest)
            if source_archive_path is not None
            else None
        )
        if archive_before != archive_after:
            raise CareFullScaleError("source archive changed during full-scale import")
        elapsed_seconds = sum(
            float(event["resource_stats"]["parquet"]["elapsed_seconds"])
            + float(event["resource_stats"]["quality"]["elapsed_seconds"])
            for event in event_summaries
        )
        storage_bytes = sum(
            int(reference["size_bytes"])
            for event in event_summaries
            for reference in (
                event["parquet"]["data"],
                event["parquet"]["manifest"],
                event["quality"]["report"],
                event["quality"]["mask"],
                event["restricted_truth"]["artifact"],
            )
        ) + sum(int(reference["size_bytes"]) for reference in mapping_references.values())
        resource_actual = _enforce_import_resources(
            event_summaries=event_summaries,
            elapsed_seconds=elapsed_seconds,
            storage_bytes=storage_bytes,
            row_count=sum(int(event["row_count"]) for event in event_summaries),
            limits=resource_limits,
        )
        payload = {
            "schema_version": FULL_SCALE_IMPORT_SCHEMA_VERSION,
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "source_manifest_sha256": source_manifest["manifest_sha256"],
            "source_dataset_sha256": contract.source_dataset_sha256,
            "quality_contract_sha256": quality_contract["quality_contract_sha256"],
            "care_approval": approved_lineage,
            "plan": plan,
            "stage_order": list(FULL_SCALE_STAGE_ORDER),
            "mapping_artifacts": mapping_references,
            "events": list(event_summaries),
            "summary": expected_counts.to_document(),
            "resource_policy": resource_limits.to_document(),
            "resource_actual": resource_actual,
            "execution": {
                "independent_worker_required": True,
                "job_id": job_id,
                "job_state_path": str(state_file.resolve()),
                "event_checkpoint_count": len(event_summaries),
                "event_boundary_cancel_and_new-job-resume": True,
                "bounded_attempts": 3,
                "wall_clock_elapsed_seconds": time.perf_counter() - started,
            },
            "storage_boundary": {
                "full_standard_format": "wide-parquet",
                "full_timescaledb_expanded_row_count": 0,
                "full_timescaledb_expansion_allowed": False,
                "selected_replay_only": True,
            },
            "cross_farm_protocol": plan["cross_farm_protocol"],
            "source_archive_verification": archive_after,
            "raw_source_unchanged": True,
            "license": _license(
                contract,
                artifact_type="full-scale-import-manifest",
                changes_made=(
                    "Expanded the verified two-event slice to A, C, then B and all expected "
                    "events; retained every mapped signal in wide Parquet and kept truth isolated."
                ),
                source_artifact_sha256=str(source_manifest["manifest_sha256"]),
            ),
        }
        manifest = {**payload, "manifest_sha256": _canonical_hash(payload)}
        content = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _write_immutable_bytes(manifest_path, content)
        verify_full_scale_import_manifest(
            manifest,
            output_root=output_root,
            source_manifest=source_manifest,
            quality_contract=quality_contract,
            expected_counts=expected_counts,
            resource_limits=resource_limits,
            trust_anchor=trust_anchor,
        )
        job_control.complete(manifest_path.resolve().as_uri(), resource_actual)
        return FullScaleImportResult(
            manifest_path,
            manifest,
            hashlib.sha256(content).hexdigest(),
            False,
        )
    except BenchmarkJobCancelled:
        raise
    except Exception as exc:
        job_control.fail(exc, retryable=not isinstance(exc, CareFullScaleResourceError))
        raise


def verify_full_scale_import_manifest(
    value: Mapping[str, Any],
    *,
    output_root: Path,
    source_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    expected_counts: FullScaleExpectedCounts = CARE_V6_FULL_SCALE_COUNTS,
    resource_limits: FullScaleResourceLimits = DEFAULT_FULL_SCALE_RESOURCE_LIMITS,
    trust_anchor: CareTrustAnchor | None = None,
) -> None:
    contract = _build_contract(
        source_manifest,
        quality_contract,
        expected_counts=expected_counts,
    )
    actual_hash = value.get("manifest_sha256")
    unsigned = {key: item for key, item in value.items() if key != "manifest_sha256"}
    if not _is_sha256(actual_hash) or _canonical_hash(unsigned) != actual_hash:
        raise CareFullScaleError("full-scale import manifest hash is invalid")
    approval = value.get("care_approval")
    if not isinstance(approval, Mapping):
        raise CareFullScaleError("full-scale import is missing CARE approved-root lineage")
    try:
        verify_care_approval_lineage(
            approval,
            source_manifest,
            quality_contract,
            trust_anchor=trust_anchor,
        )
    except CareContractError as exc:
        raise CareFullScaleError(str(exc)) from exc
    events = value.get("events")
    mappings = value.get("mapping_artifacts")
    if (
        value.get("schema_version") != FULL_SCALE_IMPORT_SCHEMA_VERSION
        or value.get("dataset_id") != DATASET_ID
        or value.get("dataset_version") != DATASET_VERSION
        or value.get("source_manifest_sha256") != source_manifest["manifest_sha256"]
        or value.get("quality_contract_sha256") != quality_contract["quality_contract_sha256"]
        or value.get("stage_order") != list(FULL_SCALE_STAGE_ORDER)
        or value.get("summary") != expected_counts.to_document()
        or value.get("raw_source_unchanged") is not True
        or not isinstance(events, list)
        or not isinstance(mappings, Mapping)
        or len(events) != expected_counts.event_count
    ):
        raise CareFullScaleError("full-scale import manifest semantics are invalid")
    source_by_event = {int(event["event_id"]): event for event in contract.events}
    farm_by_id = {farm.farm: farm for farm in contract.farms}
    expected_order = [int(event["event_id"]) for event in contract.events]
    if [int(event.get("event_id", -1)) for event in events if isinstance(event, Mapping)] != (
        expected_order
    ):
        raise CareFullScaleError("full-scale event order is not A, C, B")
    for farm, reference in mappings.items():
        if farm not in farm_by_id or not isinstance(reference, Mapping):
            raise CareFullScaleError("full-scale mapping reference is malformed")
        _verify_reference(output_root, reference)
    if set(mappings) != set(farm_by_id):
        raise CareFullScaleError("full-scale mapping references are incomplete")
    for event in events:
        if not isinstance(event, Mapping):
            raise CareFullScaleError("full-scale event summary is malformed")
        event_id = int(event["event_id"])
        source_event = source_by_event.get(event_id)
        if source_event is None:
            raise CareFullScaleError("full-scale event is absent from the source contract")
        farm_contract = farm_by_id[str(event["farm"])]
        _verify_event_summary(
            event,
            output_root=output_root,
            source_event=source_event,
            farm_contract=farm_contract,
        )
    storage = value.get("storage_boundary")
    cross_farm = value.get("cross_farm_protocol")
    resource_actual = value.get("resource_actual")
    execution = value.get("execution")
    archive_verification = value.get("source_archive_verification")
    source_archive = source_manifest["source"]["zip"]
    expected_archive_verification = {
        "size_bytes": int(source_archive["size_bytes"]),
        "md5": str(source_archive["md5"]),
        "sha256": str(source_archive["sha256"]),
    }
    expected_resource_actual = _enforce_import_resources(
        event_summaries=cast(Sequence[Mapping[str, Any]], events),
        elapsed_seconds=sum(
            float(event["resource_stats"][operation]["elapsed_seconds"])
            for event in events
            for operation in ("parquet", "quality")
        ),
        storage_bytes=sum(
            int(reference["size_bytes"])
            for event in events
            for reference in (
                event["parquet"]["data"],
                event["parquet"]["manifest"],
                event["quality"]["report"],
                event["quality"]["mask"],
                event["restricted_truth"]["artifact"],
            )
        )
        + sum(int(reference["size_bytes"]) for reference in mappings.values()),
        row_count=sum(int(event["row_count"]) for event in events),
        limits=resource_limits,
    )
    wall_clock_elapsed = (
        execution.get("wall_clock_elapsed_seconds") if isinstance(execution, Mapping) else None
    )
    if (
        not isinstance(storage, Mapping)
        or storage.get("full_timescaledb_expanded_row_count") != 0
        or storage.get("full_timescaledb_expansion_allowed") is not False
        or not isinstance(cross_farm, Mapping)
        or cross_farm.get("status") != "disabled"
        or cross_farm.get("human_review_ids") != []
        or not isinstance(resource_actual, Mapping)
        or dict(resource_actual) != expected_resource_actual
        or value.get("resource_policy") != resource_limits.to_document()
        or not isinstance(execution, Mapping)
        or execution.get("independent_worker_required") is not True
        or execution.get("event_checkpoint_count") != expected_counts.event_count
        or execution.get("event_boundary_cancel_and_new-job-resume") is not True
        or execution.get("bounded_attempts") != 3
        or (
            archive_verification is not None
            and archive_verification != expected_archive_verification
        )
        or (
            expected_counts == CARE_V6_FULL_SCALE_COUNTS
            and archive_verification != expected_archive_verification
        )
        or not isinstance(wall_clock_elapsed, int | float)
        or isinstance(wall_clock_elapsed, bool)
        or not math.isfinite(float(wall_clock_elapsed))
        or float(wall_clock_elapsed) <= 0
        or float(wall_clock_elapsed) > resource_limits.max_import_runtime_seconds
    ):
        raise CareFullScaleError("full-scale storage, ontology, or resource gate is invalid")
    _verify_license(value)


async def register_full_scale_import(
    session: AsyncSession,
    import_manifest: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    *,
    artifact_root: Path,
    tenant_id: str,
    subject: str,
    expected_counts: FullScaleExpectedCounts = CARE_V6_FULL_SCALE_COUNTS,
    resource_limits: FullScaleResourceLimits = DEFAULT_FULL_SCALE_RESOURCE_LIMITS,
    trust_anchor: CareTrustAnchor | None = None,
) -> FullScaleImportRegistration:
    """Idempotently extend the phased CARE registration to all verified events."""

    contract = _build_contract(
        source_manifest,
        quality_contract,
        expected_counts=expected_counts,
    )
    verify_full_scale_import_manifest(
        import_manifest,
        output_root=_resolved_artifact_root(artifact_root),
        source_manifest=source_manifest,
        quality_contract=quality_contract,
        expected_counts=expected_counts,
        resource_limits=resource_limits,
        trust_anchor=trust_anchor,
    )
    source_zip = source_manifest["source"]["zip"]
    license_metadata = import_manifest["license"]
    dataset, dataset_replayed = await register_dataset_version(
        session,
        BenchmarkDatasetVersionCreateRequest(
            dataset_version_id="care-v6",
            tenant_id=tenant_id,
            dataset_id=DATASET_ID,
            version=DATASET_VERSION,
            status="ready",
            source_uri=ZENODO_URL,
            manifest_uri=SOURCE_CONTRACT_URI,
            manifest_sha256=str(source_manifest["manifest_sha256"]),
            content_sha256=str(source_zip["sha256"]),
            source_archive_md5=str(source_zip["md5"]),
            source_archive_sha256=str(source_zip["sha256"]),
            size_bytes=int(source_zip["size_bytes"]),
            file_count=int(source_manifest["summary"]["csv_file_count"]),
            license_name=LICENSE_NAME,
            license_url=LICENSE_URL,
            doi=DOI,
            citation=CARE_RECOMMENDED_CITATION,
            attribution={
                "creators": list(CARE_DATASET_CREATORS),
                "affiliation": CARE_CREATOR_AFFILIATION,
                "artifact_license": license_metadata["artifact_license"],
                "changes_made": license_metadata["changes_made"],
                "share_alike_required": True,
                "full_import_manifest_sha256": import_manifest["manifest_sha256"],
                "care_approval": dict(import_manifest["care_approval"]),
            },
        ),
        subject=subject,
    )
    created = 0 if dataset_replayed else 1
    replayed = 1 if dataset_replayed else 0
    source_by_event = {int(event["event_id"]): event for event in contract.events}
    event_database_ids: list[str] = []
    for imported in import_manifest["events"]:
        event_id = int(imported["event_id"])
        farm = str(imported["farm"])
        source_event = source_by_event[event_id]
        file_id = f"care-v6-file-{farm.lower()}-{event_id}"
        _, was_replayed = await register_benchmark_file(
            session,
            BenchmarkFileCreateRequest(
                file_id=file_id,
                dataset_version_id=dataset.id,
                file_kind="event",
                relative_path=str(source_event["relative_path"]),
                farm=cast(Any, farm),
                event_id=event_id,
                size_bytes=int(imported["source_size_bytes"]),
                row_count=int(source_event["row_count"]),
                schema_sha256=str(source_event["schema_sha256"]),
                content_sha256=str(source_event["file_sha256"]),
                metadata={
                    "standard_parquet": imported["parquet"]["data"],
                    "standard_parquet_manifest": imported["parquet"]["manifest"],
                    "source_read_only": True,
                    "split_counts": source_event["split_counts"],
                    "full_signal_column_count": imported["signal_column_count"],
                    "model_input_count": imported["model_input_count"],
                },
            ),
        )
        created += 0 if was_replayed else 1
        replayed += 1 if was_replayed else 0
        event_database_id = f"care-v6-event-{farm.lower()}-{event_id}"
        event_database_ids.append(event_database_id)
        _, was_replayed = await register_benchmark_event(
            session,
            BenchmarkEventCreateRequest(
                benchmark_event_id=event_database_id,
                dataset_version_id=dataset.id,
                source_file_id=file_id,
                event_id=event_id,
                farm=cast(Any, farm),
                source_asset_id=str(source_event["source_asset_id"]),
                logical_asset_id=str(imported["logical_asset_id"]),
                event_label=cast(Literal["anomaly", "normal"], str(source_event["event_label"])),
                first_source_row_id=int(source_event["source_row_id_min"]),
                last_source_row_id=int(source_event["source_row_id_max"]),
                train_row_count=int(source_event["split_counts"]["train"]),
                prediction_row_count=int(source_event["split_counts"]["prediction"]),
                event_interval_start=int(source_event["event_start_id"]),
                event_interval_end=int(source_event["event_end_id"]),
                truth_metadata={
                    "access_scope": TRUTH_ACCESS_SCOPE,
                    "artifact": imported["restricted_truth"]["artifact"],
                    "description_available_after_authorization": bool(
                        source_event["event_description"]
                    ),
                    "model_input_allowed": False,
                },
            ),
        )
        created += 0 if was_replayed else 1
        replayed += 1 if was_replayed else 0

    for farm_contract in contract.farms:
        for index, (mapping, semantics) in enumerate(
            zip(farm_contract.mappings, farm_contract.semantics, strict=True)
        ):
            _, was_replayed = await register_feature_map(
                session,
                BenchmarkFeatureMapCreateRequest(
                    feature_map_id=(f"care-v6-feature-{farm_contract.farm.lower()}-{index:03d}"),
                    dataset_version_id=dataset.id,
                    mapping_version=COLUMN_MAPPING_VERSION,
                    farm=cast(Any, farm_contract.farm),
                    source_column=str(mapping["source_column"]),
                    canonical_feature=str(mapping["base_sensor"]),
                    statistic=str(mapping["statistic"]),
                    unit=str(semantics["normalized_unit"]),
                    enabled=bool(semantics["enabled_by_default"]),
                    semantics={
                        "mapping_source": mapping["mapping_source"],
                        "source_unit": mapping["source_unit"],
                        "unit_rule_id": semantics["unit_rule_id"],
                        "value_domain": semantics["value_domain"],
                        "value_semantics": semantics["value_semantics"],
                        "absolute_power_interpretation_allowed": semantics[
                            "absolute_power_interpretation_allowed"
                        ],
                    },
                ),
            )
            created += 0 if was_replayed else 1
            replayed += 1 if was_replayed else 0

    for event_database_id, imported in zip(
        event_database_ids, import_manifest["events"], strict=True
    ):
        quality = imported["quality"]
        _, was_replayed = await register_quality_report(
            session,
            BenchmarkQualityReportCreateRequest(
                quality_report_id=(
                    f"care-v6-quality-{str(imported['farm']).lower()}-{imported['event_id']}"
                ),
                event_id=event_database_id,
                quality_rule_version=QUALITY_RULE_VERSION,
                feature_set_version=FEATURE_SET_VERSION,
                canonical_content_sha256=str(quality["source_quality_report_sha256"]),
                artifact_stage="full-scale-import",
                status="completed",
                artifact_uri=str(quality["report"]["artifact_uri"]),
                artifact_sha256=str(quality["report"]["file_sha256"]),
                mask_uri=str(quality["mask"]["artifact_uri"]),
                mask_sha256=str(quality["mask"]["file_sha256"]),
                summary={
                    "row_count": imported["row_count"],
                    "feature_summary_count": quality["feature_summary_count"],
                    "mask_count": quality["mask_count"],
                    "raw_values_modified": False,
                },
            ),
            subject=subject,
        )
        created += 0 if was_replayed else 1
        replayed += 1 if was_replayed else 0
    return FullScaleImportRegistration(
        created,
        replayed,
        dataset.id,
        tuple(event_database_ids),
    )


@dataclass(slots=True)
class _Moments:
    counts: Any
    sums: Any
    sum_squares: Any
    quality_mask_counts: Any
    status_usable_train_rows: int = 0
    trusted_train_rows: int = 0
    retained_disagreement_train_rows: int = 0
    masked_status_train_rows: int = 0
    quality_masked_train_rows: int = 0


def _new_moments(np: Any, feature_count: int) -> _Moments:
    return _Moments(
        counts=np.zeros(feature_count, dtype=np.int64),
        sums=np.zeros(feature_count, dtype=np.float64),
        sum_squares=np.zeros(feature_count, dtype=np.float64),
        quality_mask_counts=np.zeros(feature_count, dtype=np.int64),
    )


def _normalise_status(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _timestamp_text(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    text = str(value)
    if not text:
        raise CareFullScaleError("prediction timestamp must not be empty")
    return text


def _resolve_reference(output_root: Path, reference: Mapping[str, Any]) -> Path:
    relative = reference.get("local_relative_path")
    if not isinstance(relative, str):
        raise CareFullScaleError("full-scale local artifact reference is missing")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise CareFullScaleError("full-scale local artifact path is unsafe")
    path = output_root.joinpath(*pure.parts).resolve(strict=True)
    if not path.is_relative_to(output_root) or _sha256_file(path) != reference.get("file_sha256"):
        raise CareFullScaleError("full-scale local artifact content changed")
    return path


def _publish_self_hashed_json(
    *,
    output_root: Path,
    path: Path,
    document: Mapping[str, Any],
    document_sha256: str,
    object_key_prefix: str,
    artifact_store: ImmutableArtifactStore | None,
) -> dict[str, Any]:
    content = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _write_immutable_bytes(path, content)
    file_sha256 = hashlib.sha256(content).hexdigest()
    object_key = f"{object_key_prefix}.sha256-{file_sha256}.json"
    artifact_uri = (
        artifact_store.put_immutable(
            object_key,
            path,
            file_sha256,
            content_type="application/json",
        )
        if artifact_store is not None
        else path.resolve().as_uri()
    )
    return _artifact_reference(
        output_root=output_root,
        path=path,
        artifact_uri=artifact_uri,
        file_sha256=file_sha256,
        document_sha256=document_sha256,
    )


def _load_json_reference(output_root: Path, reference: Mapping[str, Any]) -> Mapping[str, Any]:
    path = _resolve_reference(output_root, reference)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise CareFullScaleError("full-scale JSON artifact root must be an object")
    return raw


def _quality_mask_policy(feature_columns: Sequence[str]) -> dict[str, Any]:
    payload = {
        "policy_version": FULL_SCALE_QUALITY_MASK_POLICY_VERSION,
        "decision": "apply",
        "feature_columns_sha256": _canonical_hash(list(feature_columns)),
        "range_coordinate": "inclusive-source-row-id",
        "training_action": "exclude-masked-feature-values-from-fold-moments",
        "prediction_action": "impute-masked-feature-values-with-fold-training-mean",
        "nonfinite_prediction_action": "impute-with-fold-training-mean",
        "score_stage": "after-mask-and-imputation",
        "ignored_mask_requires_sensitivity_approval": True,
    }
    return {**payload, "policy_sha256": _canonical_hash(payload)}


def _quality_mask_impact_summary(
    training_resources: Mapping[str, Any],
    predictions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    prediction_point_count = sum(int(item["point_count"]) for item in predictions)
    absolute_delta_sum = sum(
        float(item["quality_mask_mean_absolute_score_delta"]) * int(item["point_count"])
        for item in predictions
    )
    payload = {
        "policy_version": FULL_SCALE_QUALITY_MASK_POLICY_VERSION,
        "decision": "apply",
        "quality_masked_train_row_count": int(training_resources["quality_masked_train_row_count"]),
        "quality_masked_train_feature_value_count": int(
            training_resources["quality_masked_train_feature_value_count"]
        ),
        "quality_masked_prediction_point_count": sum(
            int(item["quality_masked_prediction_point_count"]) for item in predictions
        ),
        "quality_masked_prediction_feature_value_count": sum(
            int(item["quality_masked_prediction_feature_value_count"]) for item in predictions
        ),
        "quality_mask_score_changed_prediction_point_count": sum(
            int(item["quality_mask_score_changed_prediction_point_count"]) for item in predictions
        ),
        "quality_mask_binary_decision_changed_point_count": sum(
            int(item["quality_mask_binary_decision_changed_point_count"]) for item in predictions
        ),
        "quality_mask_max_absolute_score_delta": max(
            (float(item["quality_mask_max_absolute_score_delta"]) for item in predictions),
            default=0.0,
        ),
        "quality_mask_mean_absolute_score_delta": (
            absolute_delta_sum / prediction_point_count if prediction_point_count else 0.0
        ),
        "actual_fold_metrics_use_masked_predictions": True,
        "counterfactual_scope": (
            "prediction-time masks ignored with the same mask-trained fold profile"
        ),
        "metric_change_explanation": (
            "fold metrics are recomputed from mask-applied scores; score and binary-decision "
            "delta counts quantify prediction-time impact, while verifier-recomputed fold "
            "moments prove training-time impact"
        ),
    }
    return {**payload, "impact_sha256": _canonical_hash(payload)}


def _quality_mask_lineage(
    import_manifest: Mapping[str, Any],
    farm: str,
    *,
    excluded_asset_id: str | None = None,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for event in import_manifest["events"]:
        if str(event["farm"]) != farm or (
            excluded_asset_id is not None and str(event["source_asset_id"]) == excluded_asset_id
        ):
            continue
        quality = event.get("quality")
        reference = quality.get("mask") if isinstance(quality, Mapping) else None
        if not isinstance(reference, Mapping):
            raise CareFullScaleError("full-scale event quality mask reference is missing")
        file_sha256 = reference.get("file_sha256")
        source_quality_sha256 = quality.get("source_quality_report_sha256")
        mask_count = quality.get("mask_count")
        if (
            not _is_sha256(file_sha256)
            or not _is_sha256(source_quality_sha256)
            or not isinstance(mask_count, int)
            or isinstance(mask_count, bool)
            or mask_count < 0
        ):
            raise CareFullScaleError("full-scale event quality mask lineage is malformed")
        events.append(
            {
                "event_id": int(event["event_id"]),
                "source_asset_id": str(event["source_asset_id"]),
                "quality_mask_file_sha256": file_sha256,
                "source_quality_report_sha256": source_quality_sha256,
                "mask_range_count": mask_count,
            }
        )
    events.sort(key=lambda item: int(item["event_id"]))
    payload = {
        "farm": farm,
        "excluded_asset_id": excluded_asset_id,
        "event_count": len(events),
        "events": events,
    }
    return {**payload, "lineage_sha256": _canonical_hash(payload)}


def _load_quality_mask_artifact(
    output_root: Path,
    event: Mapping[str, Any],
) -> Mapping[str, Any]:
    quality = event.get("quality")
    reference = quality.get("mask") if isinstance(quality, Mapping) else None
    if not isinstance(reference, Mapping):
        raise CareFullScaleError("full-scale event quality mask reference is missing")
    if not isinstance(quality, Mapping):
        raise CareFullScaleError("full-scale event quality evidence is missing")
    raw = _load_json_reference(output_root, reference)
    ranges = raw.get("quality_mask_ranges")
    if (
        raw.get("schema_version") != "care-v6-quality-mask-artifact-v1"
        or raw.get("dataset_id") != DATASET_ID
        or raw.get("dataset_version") != DATASET_VERSION
        or raw.get("farm") != event.get("farm")
        or raw.get("event_id") != event.get("event_id")
        or raw.get("source_event_file_sha256") != event.get("source_file_sha256")
        or raw.get("source_quality_report_sha256") != quality.get("source_quality_report_sha256")
        or raw.get("quality_rule_version") != QUALITY_RULE_VERSION
        or raw.get("raw_values_modified") is not False
        or not isinstance(ranges, list)
        or raw.get("mask_count") != len(ranges)
        or raw.get("mask_count") != quality.get("mask_count")
    ):
        raise CareFullScaleError("full-scale quality mask artifact identity is invalid")
    previous_end_by_column: dict[str, int] = {}
    for item in ranges:
        if not isinstance(item, Mapping):
            raise CareFullScaleError("full-scale quality mask range is malformed")
        column = item.get("source_column")
        start = item.get("source_row_id_start")
        end = item.get("source_row_id_end")
        length = item.get("length")
        if (
            not isinstance(column, str)
            or not column
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or end < start
            or not isinstance(length, int)
            or isinstance(length, bool)
            or length != end - start + 1
            or item.get("rule_id") != ZERO_RUN_RULE_ID
            or item.get("rule_version") != QUALITY_RULE_VERSION
            or item.get("raw_value_preserved") is not True
            or start <= previous_end_by_column.get(column, -1)
        ):
            raise CareFullScaleError("full-scale quality mask range is invalid")
        previous_end_by_column[column] = end
    return raw


def _quality_mask_index(
    mask_artifact: Mapping[str, Any],
    feature_columns: Sequence[str],
) -> dict[str, tuple[tuple[int, int], ...]]:
    selected = set(feature_columns)
    by_column: dict[str, list[tuple[int, int]]] = {}
    for item in mask_artifact["quality_mask_ranges"]:
        column = str(item["source_column"])
        if column in selected:
            by_column.setdefault(column, []).append(
                (int(item["source_row_id_start"]), int(item["source_row_id_end"]))
            )
    return {column: tuple(ranges) for column, ranges in by_column.items()}


def _quality_mask_matrix(
    *,
    row_ids: Sequence[Any],
    feature_columns: Sequence[str],
    mask_index: Mapping[str, tuple[tuple[int, int], ...]],
    np: Any,
) -> Any:
    rows = np.asarray([int(value) for value in row_ids], dtype=np.int64)
    if len(rows) > 1 and bool((np.diff(rows) <= 0).any()):
        raise CareFullScaleError("full-scale Parquet source row IDs are not strictly increasing")
    result = np.zeros((len(rows), len(feature_columns)), dtype=bool)
    for feature_index, column in enumerate(feature_columns):
        ranges = mask_index.get(column, ())
        if not ranges or not len(rows):
            continue
        starts = np.asarray([start for start, _ in ranges], dtype=np.int64)
        ends = np.asarray([end for _, end in ranges], dtype=np.int64)
        positions = np.searchsorted(starts, rows, side="right") - 1
        has_candidate = positions >= 0
        safe_positions = np.where(has_candidate, positions, 0)
        result[:, feature_index] = has_candidate & (rows <= ends[safe_positions])
    return result


def _feature_matrix(batch: Any, columns: Sequence[str], np: Any) -> Any:
    arrays = []
    for column in columns:
        index = batch.schema.get_field_index(column)
        if index < 0:
            raise CareFullScaleError(f"full-scale Parquet is missing feature {column}")
        arrow_column = batch.column(index)
        try:
            values = np.asarray(arrow_column.to_numpy(zero_copy_only=False), dtype=np.float64)
        except (TypeError, ValueError):
            values = np.asarray(arrow_column.to_pylist(), dtype=np.float64)
        arrays.append(values)
    return np.column_stack(arrays)


def _batch_values(batch: Any, name: str) -> list[Any]:
    index = batch.schema.get_field_index(name)
    if index < 0:
        raise CareFullScaleError(f"full-scale Parquet is missing metadata column {name}")
    return cast(list[Any], batch.column(index).to_pylist())


def _evaluation_column_contracts(
    output_root: Path,
    import_manifest: Mapping[str, Any],
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    features_by_farm: dict[str, tuple[str, ...]] = {}
    status_signals_by_farm: dict[str, tuple[str, ...]] = {}
    mapping_references = import_manifest.get("mapping_artifacts")
    if not isinstance(mapping_references, Mapping):
        raise CareFullScaleError("full-scale mapping references are malformed")
    for farm in FULL_SCALE_STAGE_ORDER:
        reference = mapping_references.get(farm)
        if not isinstance(reference, Mapping):
            raise CareFullScaleError(f"full-scale farm {farm} mapping reference is missing")
        mapping = _load_json_reference(output_root, reference)
        features = tuple(str(item) for item in mapping.get("approved_model_input_columns", []))
        if not features or len(features) != int(mapping.get("approved_model_input_count", -1)):
            raise CareFullScaleError(f"full-scale farm {farm} feature mapping is invalid")
        raw_mappings = mapping.get("mappings")
        if not isinstance(raw_mappings, list):
            raise CareFullScaleError(f"full-scale farm {farm} mapping rows are invalid")
        semantics_by_column = {
            str(item.get("source_column")): item.get("quality_semantics")
            for item in raw_mappings
            if isinstance(item, Mapping)
        }
        status_signal_values: list[str] = []
        for column in features:
            semantics = semantics_by_column.get(column)
            if (
                isinstance(semantics, Mapping)
                and semantics.get("value_semantics") == "anonymized-rated-power-scaled"
            ):
                status_signal_values.append(column)
        status_signals = tuple(status_signal_values)
        try:
            status_evidence_policy(farm, status_signals)
        except CareContractError as exc:
            raise CareFullScaleError(str(exc)) from exc
        features_by_farm[farm] = features
        status_signals_by_farm[farm] = status_signals
    return features_by_farm, status_signals_by_farm


def _batch_status_evidence(
    *,
    state: StatusSequenceState,
    row_ids: Sequence[Any],
    splits: Sequence[Any],
    statuses: Sequence[Any],
    feature_values: Any,
    feature_columns: Sequence[str],
    status_signal_columns: Sequence[str],
) -> tuple[StatusPointEvidence, ...]:
    signal_indexes = tuple(feature_columns.index(column) for column in status_signal_columns)
    return tuple(
        state.observe(
            source_row_id=int(row_id),
            split=str(split),
            status_id=_normalise_status(status),
            corroboration_signal_values=tuple(
                feature_values[index, position] for position in signal_indexes
            ),
        )
        for index, (row_id, split, status) in enumerate(zip(row_ids, splits, statuses, strict=True))
    )


def _iter_event_batches(
    output_root: Path,
    event: Mapping[str, Any],
    columns: Sequence[str],
    *,
    batch_size: int = 8192,
) -> Any:
    parquet_module = importlib.import_module("pyarrow.parquet")
    path = _resolve_reference(output_root, event["parquet"]["data"])
    parquet_file = parquet_module.ParquetFile(path)
    try:
        yield from parquet_file.iter_batches(batch_size=batch_size, columns=list(columns))
    finally:
        parquet_file.close()


def _accumulate_moments(
    *,
    import_manifest: Mapping[str, Any],
    output_root: Path,
    features_by_farm: Mapping[str, tuple[str, ...]],
    status_signals_by_farm: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, _Moments], dict[tuple[str, str], _Moments], dict[str, Any]]:
    np = importlib.import_module("numpy")
    arrow = importlib.import_module("pyarrow")
    totals = {farm: _new_moments(np, len(features)) for farm, features in features_by_farm.items()}
    assets: dict[tuple[str, str], _Moments] = {}
    baseline_arrow = int(arrow.total_allocated_bytes())
    peak_batch = 0
    peak_arrow = 0
    scanned_rows = 0
    status_usable_rows = 0
    trusted_rows = 0
    retained_disagreement_rows = 0
    masked_status_rows = 0
    quality_masked_rows = 0
    quality_masked_values = 0
    started = time.perf_counter()
    for event in import_manifest["events"]:
        farm = str(event["farm"])
        asset = str(event["source_asset_id"])
        features = features_by_farm[farm]
        status_signals = status_signals_by_farm[farm]
        mask_artifact = _load_quality_mask_artifact(output_root, event)
        mask_index = _quality_mask_index(mask_artifact, features)
        asset_moments = assets.setdefault((farm, asset), _new_moments(np, len(features)))
        status_state = StatusSequenceState(farm, FULL_SCALE_TRAIN_STATUS_IDS)
        columns = ("asset_id", "id", "train_test", "status_type_id", *features)
        for batch in _iter_event_batches(output_root, event, columns):
            peak_batch = max(peak_batch, int(batch.nbytes))
            peak_arrow = max(
                peak_arrow,
                max(0, int(arrow.total_allocated_bytes()) - baseline_arrow),
            )
            batch_assets = {_normalise_status(value) for value in _batch_values(batch, "asset_id")}
            if batch_assets != {asset}:
                raise CareFullScaleError("Parquet asset identity differs from the event manifest")
            split = _batch_values(batch, "train_test")
            status = [_normalise_status(value) for value in _batch_values(batch, "status_type_id")]
            row_ids = _batch_values(batch, "id")
            all_values = _feature_matrix(batch, features, np)
            all_quality_masks = _quality_mask_matrix(
                row_ids=row_ids,
                feature_columns=features,
                mask_index=mask_index,
                np=np,
            )
            evidence = _batch_status_evidence(
                state=status_state,
                row_ids=row_ids,
                splits=split,
                statuses=status,
                feature_values=all_values,
                feature_columns=features,
                status_signal_columns=status_signals,
            )
            decisions = tuple(
                evaluate_status_point(
                    farm=farm,
                    split=str(split_value),
                    status_id=status_value,
                    trusted_status_ids=FULL_SCALE_TRAIN_STATUS_IDS,
                    disagreement_run_length=item.disagreement_run_length,
                    corroborated_by_signal=item.corroborated_by_signal,
                )
                for split_value, status_value, item in zip(
                    split,
                    status,
                    evidence,
                    strict=True,
                )
            )
            train_mask = np.asarray(
                [
                    str(split_value) == "train" and decision.model_usable
                    for split_value, decision in zip(split, decisions, strict=True)
                ],
                dtype=bool,
            )
            scanned_rows += len(split)
            batch_trusted_rows = sum(
                str(split_value) == "train" and status_value in FULL_SCALE_TRAIN_STATUS_IDS
                for split_value, status_value in zip(split, status, strict=True)
            )
            batch_retained_rows = sum(
                str(split_value) == "train"
                and status_value not in FULL_SCALE_TRAIN_STATUS_IDS
                and decision.model_usable
                for split_value, status_value, decision in zip(
                    split,
                    status,
                    decisions,
                    strict=True,
                )
            )
            batch_masked_rows = sum(
                str(split_value) == "train" and not decision.model_usable
                for split_value, decision in zip(split, decisions, strict=True)
            )
            if not bool(train_mask.any()):
                for moments in (totals[farm], asset_moments):
                    moments.trusted_train_rows += batch_trusted_rows
                    moments.retained_disagreement_train_rows += batch_retained_rows
                    moments.masked_status_train_rows += batch_masked_rows
                trusted_rows += batch_trusted_rows
                retained_disagreement_rows += batch_retained_rows
                masked_status_rows += batch_masked_rows
                continue
            values = all_values[train_mask]
            quality_masks = all_quality_masks[train_mask]
            finite = np.isfinite(values) & ~quality_masks
            safe = np.where(finite, values, 0.0)
            counts = finite.sum(axis=0, dtype=np.int64)
            sums = safe.sum(axis=0, dtype=np.float64)
            sum_squares = np.square(safe).sum(axis=0, dtype=np.float64)
            quality_counts = quality_masks.sum(axis=0, dtype=np.int64)
            batch_quality_masked_rows = int(quality_masks.any(axis=1).sum())
            batch_quality_masked_values = int(quality_counts.sum())
            selected_rows = int(train_mask.sum())
            for moments in (totals[farm], asset_moments):
                moments.counts += counts
                moments.sums += sums
                moments.sum_squares += sum_squares
                moments.quality_mask_counts += quality_counts
                moments.status_usable_train_rows += selected_rows
                moments.trusted_train_rows += batch_trusted_rows
                moments.retained_disagreement_train_rows += batch_retained_rows
                moments.masked_status_train_rows += batch_masked_rows
                moments.quality_masked_train_rows += batch_quality_masked_rows
            status_usable_rows += selected_rows
            trusted_rows += batch_trusted_rows
            retained_disagreement_rows += batch_retained_rows
            masked_status_rows += batch_masked_rows
            quality_masked_rows += batch_quality_masked_rows
            quality_masked_values += batch_quality_masked_values
        if not trim_process_resident_memory():
            raise CareFullScaleError(
                "full-scale evaluator could not trim training-pass resident memory"
            )
    return (
        totals,
        assets,
        {
            "elapsed_seconds": time.perf_counter() - started,
            "scanned_row_count": scanned_rows,
            "status_usable_train_row_count": status_usable_rows,
            "trusted_train_row_count": trusted_rows,
            "retained_disagreement_train_row_count": retained_disagreement_rows,
            "masked_status_train_row_count": masked_status_rows,
            "quality_masked_train_row_count": quality_masked_rows,
            "quality_masked_train_feature_value_count": quality_masked_values,
            "peak_record_batch_bytes": peak_batch,
            "peak_arrow_allocated_bytes": peak_arrow,
        },
    )


def _build_fold_profiles(
    *,
    totals: Mapping[str, _Moments],
    assets: Mapping[tuple[str, str], _Moments],
    features_by_farm: Mapping[str, tuple[str, ...]],
    import_manifest: Mapping[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    np = importlib.import_module("numpy")
    profiles: dict[tuple[str, str], dict[str, Any]] = {}
    for (farm, asset), own in sorted(assets.items()):
        total = totals[farm]
        counts = total.counts - own.counts
        if bool((counts <= 0).any()):
            missing = [
                feature
                for feature, count in zip(features_by_farm[farm], counts.tolist(), strict=True)
                if int(count) <= 0
            ]
            raise CareFullScaleError(
                f"held-out {farm}:{asset} leaves features without finite train data: {missing[:5]}"
            )
        sums = total.sums - own.sums
        sum_squares = total.sum_squares - own.sum_squares
        quality_mask_counts = total.quality_mask_counts - own.quality_mask_counts
        means = sums / counts
        variances = np.maximum(0.0, (sum_squares / counts) - np.square(means))
        standard_deviations = np.sqrt(variances)
        standard_deviations = np.where(standard_deviations > 1e-12, standard_deviations, 1.0)
        if not bool(np.isfinite(means).all()) or not bool(np.isfinite(standard_deviations).all()):
            raise CareFullScaleError("full-scale fold profile is non-finite")
        quality_mask_lineage = _quality_mask_lineage(
            import_manifest,
            farm,
            excluded_asset_id=asset,
        )
        quality_mask_policy = _quality_mask_policy(features_by_farm[farm])
        profiles[(farm, asset)] = {
            "farm": farm,
            "held_out_asset_id": asset,
            "training_asset_ids": sorted(
                item_asset
                for item_farm, item_asset in assets
                if item_farm == farm and item_asset != asset
            ),
            "status_usable_train_row_count": (
                total.status_usable_train_rows - own.status_usable_train_rows
            ),
            "trusted_train_row_count": total.trusted_train_rows - own.trusted_train_rows,
            "retained_disagreement_train_row_count": (
                total.retained_disagreement_train_rows - own.retained_disagreement_train_rows
            ),
            "masked_status_train_row_count": (
                total.masked_status_train_rows - own.masked_status_train_rows
            ),
            "quality_masked_train_row_count": (
                total.quality_masked_train_rows - own.quality_masked_train_rows
            ),
            "quality_masked_train_feature_value_count": int(quality_mask_counts.sum()),
            "quality_masked_train_feature_counts": quality_mask_counts.tolist(),
            "quality_mask_policy_sha256": quality_mask_policy["policy_sha256"],
            "training_quality_mask_lineage_sha256": quality_mask_lineage["lineage_sha256"],
            "training_quality_mask_event_count": quality_mask_lineage["event_count"],
            "finite_counts": counts.tolist(),
            "means": means.tolist(),
            "standard_deviations": standard_deviations.tolist(),
            "imputation": "leave-one-asset-out-feature-mean-for-nonfinite-or-quality-masked-v2",
            "prediction_truth_used": False,
        }
    return profiles


def _model_id(farm: str) -> str:
    return f"care-{farm.lower()}-within-farm-loao-zscore-v1"


def _threshold_policy() -> ThresholdPolicy:
    return ThresholdPolicy(
        value=FULL_SCALE_THRESHOLD,
        version=FULL_SCALE_THRESHOLD_VERSION,
        calibration_split="train",
        calibration_run_id=FULL_SCALE_THRESHOLD_RUN_ID,
        strategy="preregistered-from-a-minimal-train-only-before-full-scale",
    )


def _model_selection(farm: str, asset: str) -> ModelSelectionProvenance:
    return ModelSelectionProvenance(
        training_run_id=f"care-v6-{farm.lower()}-loao-{_safe_token(asset)}-train-v2",
        feature_selection_split="not-used",
        early_stopping_split="not-used",
        hyperparameter_selection_split="not-used",
    )


def _build_prediction(
    *,
    event: Mapping[str, Any],
    output_root: Path,
    features: tuple[str, ...],
    status_signal_columns: tuple[str, ...],
    profile: Mapping[str, Any],
    feature_set_sha256: str,
    quality_contract_sha256: str,
    license_metadata: Mapping[str, Any],
    approval_lineage: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    np = importlib.import_module("numpy")
    arrow = importlib.import_module("pyarrow")
    farm = str(event["farm"])
    asset = str(event["source_asset_id"])
    means = np.asarray(profile["means"], dtype=np.float64)
    standard_deviations = np.asarray(profile["standard_deviations"], dtype=np.float64)
    points: list[PredictionPoint] = []
    point_input_evidence: list[tuple[int, int, int, float]] = []
    quality_mask_artifact = _load_quality_mask_artifact(output_root, event)
    quality_mask_index = _quality_mask_index(quality_mask_artifact, features)
    baseline_arrow = int(arrow.total_allocated_bytes())
    peak_batch = 0
    peak_arrow = 0
    started = time.perf_counter()
    status_state = StatusSequenceState(farm, FULL_SCALE_TRAIN_STATUS_IDS)
    columns = ("time_stamp", "id", "train_test", "status_type_id", *features)
    for batch in _iter_event_batches(output_root, event, columns):
        peak_batch = max(peak_batch, int(batch.nbytes))
        peak_arrow = max(
            peak_arrow,
            max(0, int(arrow.total_allocated_bytes()) - baseline_arrow),
        )
        split = _batch_values(batch, "train_test")
        row_ids = _batch_values(batch, "id")
        statuses = _batch_values(batch, "status_type_id")
        all_values = _feature_matrix(batch, features, np)
        all_quality_masks = _quality_mask_matrix(
            row_ids=row_ids,
            feature_columns=features,
            mask_index=quality_mask_index,
            np=np,
        )
        status_evidence = _batch_status_evidence(
            state=status_state,
            row_ids=row_ids,
            splits=split,
            statuses=statuses,
            feature_values=all_values,
            feature_columns=features,
            status_signal_columns=status_signal_columns,
        )
        prediction_positions = [
            index for index, value in enumerate(split) if str(value) == "prediction"
        ]
        if not prediction_positions:
            continue
        values = all_values[prediction_positions]
        quality_masks = all_quality_masks[prediction_positions]
        finite = np.isfinite(values)
        usable = finite & ~quality_masks
        imputed = np.where(usable, values, means)
        scores = np.max(np.abs((imputed - means) / standard_deviations), axis=1)
        ignored_mask_values = np.where(finite, values, means)
        ignored_mask_scores = np.max(
            np.abs((ignored_mask_values - means) / standard_deviations),
            axis=1,
        )
        if not bool(np.isfinite(scores).all()):
            raise CareFullScaleError("full-scale model emitted a non-finite score")
        timestamps = _batch_values(batch, "time_stamp")
        for score_index, batch_index in enumerate(prediction_positions):
            timestamp = _timestamp_text(timestamps[batch_index])
            evidence = status_evidence[batch_index]
            points.append(
                PredictionPoint(
                    source_row_id=int(row_ids[batch_index]),
                    source_timestamp=timestamp,
                    anonymous_time=timestamp,
                    anomaly_score=float(scores[score_index]),
                    status_id=_normalise_status(statuses[batch_index]),
                    disagreement_run_length=evidence.disagreement_run_length,
                    corroborated_by_signal=evidence.corroborated_by_signal,
                    corroboration_signal_count=evidence.corroboration_signal_count,
                    corroboration_finite_signal_count=(evidence.corroboration_finite_signal_count),
                    corroboration_inactive_or_invalid_signal_count=(
                        evidence.corroboration_inactive_or_invalid_signal_count
                    ),
                )
            )
            quality_masked_count = int(quality_masks[score_index].sum())
            nonfinite_count = int((~finite[score_index]).sum())
            point_input_evidence.append(
                (
                    quality_masked_count,
                    nonfinite_count,
                    int((~usable[score_index]).sum()),
                    float(ignored_mask_scores[score_index]),
                )
            )
    if len(points) != int(event["split_counts"]["prediction"]):
        raise CareFullScaleError("full-scale prediction count differs from the import manifest")
    artifact = build_prediction_artifact(
        PredictionBatch(
            event_id=int(event["event_id"]),
            farm=farm,
            source_asset_id=asset,
            points=tuple(points),
            model_id=_model_id(farm),
            model_version=FULL_SCALE_MODEL_VERSION,
            deployment_id=None,
            feature_set_version=FEATURE_SET_VERSION,
            feature_set_sha256=feature_set_sha256,
            quality_rule_version=QUALITY_RULE_VERSION,
            quality_contract_sha256=quality_contract_sha256,
            model_selection_provenance=_model_selection(farm, asset),
        ),
        _threshold_policy(),
        trusted_status_ids=FULL_SCALE_TRAIN_STATUS_IDS,
        status_signal_columns=status_signal_columns,
        license_metadata=license_metadata,
        approval_lineage=approval_lineage,
    )
    artifact_payload = {
        key: value for key, value in artifact.items() if key != "prediction_artifact_sha256"
    }
    artifact_points = artifact_payload.get("points")
    if not isinstance(artifact_points, list) or len(artifact_points) != len(point_input_evidence):
        raise CareFullScaleError("full-scale prediction input evidence shape is invalid")
    for raw_point, input_evidence in zip(artifact_points, point_input_evidence, strict=True):
        if not isinstance(raw_point, dict):
            raise CareFullScaleError("full-scale prediction point is not mutable")
        raw_point.update(
            {
                "quality_masked_feature_count": input_evidence[0],
                "nonfinite_feature_count": input_evidence[1],
                "imputed_feature_count": input_evidence[2],
                "quality_mask_ignored_anomaly_score": input_evidence[3],
                "quality_mask_score_delta": (float(raw_point["anomaly_score"]) - input_evidence[3]),
                "quality_mask_changed_binary_prediction": (
                    (float(raw_point["anomaly_score"]) > FULL_SCALE_THRESHOLD)
                    != (input_evidence[3] > FULL_SCALE_THRESHOLD)
                ),
            }
        )
    event_quality = event["quality"]
    mask_reference = event_quality["mask"]
    selected_feature_columns = set(features)
    selected_mask_range_count = sum(
        1
        for item in quality_mask_artifact["quality_mask_ranges"]
        if str(item["source_column"]) in selected_feature_columns
    )
    artifact_payload.update(
        {
            "quality_mask_policy": _quality_mask_policy(features),
            "quality_mask_reference": dict(mask_reference),
            "quality_mask_range_count": int(quality_mask_artifact["mask_count"]),
            "selected_quality_mask_range_count": selected_mask_range_count,
            "quality_masked_prediction_feature_value_count": sum(
                evidence[0] for evidence in point_input_evidence
            ),
            "quality_masked_prediction_point_count": sum(
                evidence[0] > 0 for evidence in point_input_evidence
            ),
            "nonfinite_prediction_feature_value_count": sum(
                evidence[1] for evidence in point_input_evidence
            ),
            "imputed_prediction_feature_value_count": sum(
                evidence[2] for evidence in point_input_evidence
            ),
            "quality_mask_score_changed_prediction_point_count": sum(
                float(point["quality_mask_score_delta"]) != 0.0 for point in artifact_points
            ),
            "quality_mask_binary_decision_changed_point_count": sum(
                bool(point["quality_mask_changed_binary_prediction"]) for point in artifact_points
            ),
            "quality_mask_max_absolute_score_delta": max(
                (abs(float(point["quality_mask_score_delta"])) for point in artifact_points),
                default=0.0,
            ),
            "quality_mask_mean_absolute_score_delta": (
                sum(abs(float(point["quality_mask_score_delta"])) for point in artifact_points)
                / len(artifact_points)
            ),
            "quality_mask_impact_interpretation": (
                "counterfactual ignores prediction-time masks while retaining the same "
                "mask-trained fold; training-profile changes are proven separately by "
                "raw fold recomputation"
            ),
        }
    )
    artifact = {
        **artifact_payload,
        "prediction_artifact_sha256": _canonical_hash(artifact_payload),
    }
    verify_prediction_artifact(artifact)
    if not trim_process_resident_memory():
        raise CareFullScaleError(
            "full-scale evaluator could not trim prediction-pass resident memory"
        )
    return artifact, {
        "elapsed_seconds": time.perf_counter() - started,
        "prediction_point_count": len(points),
        "peak_record_batch_bytes": peak_batch,
        "peak_arrow_allocated_bytes": peak_arrow,
    }


def _truth_from_event(output_root: Path, event: Mapping[str, Any]) -> CareEventTruth:
    raw = _load_json_reference(output_root, event["restricted_truth"]["artifact"])
    if (
        raw.get("access_scope") != TRUTH_ACCESS_SCOPE
        or raw.get("model_input_allowed") is not False
        or raw.get("event_id") != event["event_id"]
        or raw.get("farm") != event["farm"]
        or str(raw.get("source_asset_id")) != str(event["source_asset_id"])
    ):
        raise CareFullScaleError("restricted truth identity or access contract is invalid")
    description = str(raw.get("event_description", "")).strip()
    return CareEventTruth(
        event_id=int(raw["event_id"]),
        farm=str(raw["farm"]),
        source_asset_id=str(raw["source_asset_id"]),
        event_label=str(raw["event_label"]),
        event_start_source_row_id=int(raw["event_start_id"]),
        event_end_source_row_id=int(raw["event_end_id"]),
        failure_type=description or None,
    )


def verify_full_scale_prediction_status_evidence(
    prediction: Mapping[str, Any],
    *,
    output_root: Path,
    event: Mapping[str, Any],
    status_signal_columns: Sequence[str],
) -> dict[str, int]:
    """Recompute caller-supplied status fields from immutable Parquet rows and signals."""

    verify_prediction_artifact(prediction)
    farm = str(event["farm"])
    expected_policy = status_evidence_policy(farm, status_signal_columns)
    if prediction.get("status_evidence_policy") != expected_policy:
        raise CareFullScaleError("full-scale prediction status evidence policy is invalid")
    points = prediction.get("points")
    if not isinstance(points, list):
        raise CareFullScaleError("full-scale prediction points are missing")
    np = importlib.import_module("numpy")
    state = StatusSequenceState(farm, FULL_SCALE_TRAIN_STATUS_IDS)
    point_index = 0
    training_counts = {
        "status_usable_train_row_count": 0,
        "trusted_train_row_count": 0,
        "retained_disagreement_train_row_count": 0,
        "masked_status_train_row_count": 0,
    }
    columns = ("id", "train_test", "status_type_id", *status_signal_columns)
    for batch in _iter_event_batches(output_root, event, columns):
        row_ids = _batch_values(batch, "id")
        splits = _batch_values(batch, "train_test")
        statuses = _batch_values(batch, "status_type_id")
        signal_values = (
            _feature_matrix(batch, status_signal_columns, np)
            if status_signal_columns
            else np.empty((len(row_ids), 0), dtype=np.float64)
        )
        evidence = _batch_status_evidence(
            state=state,
            row_ids=row_ids,
            splits=splits,
            statuses=statuses,
            feature_values=signal_values,
            feature_columns=status_signal_columns,
            status_signal_columns=status_signal_columns,
        )
        for batch_index, split in enumerate(splits):
            status_id = _normalise_status(statuses[batch_index])
            if str(split) == "train":
                decision = evaluate_status_point(
                    farm=farm,
                    split="train",
                    status_id=status_id,
                    trusted_status_ids=FULL_SCALE_TRAIN_STATUS_IDS,
                    disagreement_run_length=evidence[batch_index].disagreement_run_length,
                    corroborated_by_signal=evidence[batch_index].corroborated_by_signal,
                )
                if decision.model_usable:
                    training_counts["status_usable_train_row_count"] += 1
                    if status_id in FULL_SCALE_TRAIN_STATUS_IDS:
                        training_counts["trusted_train_row_count"] += 1
                    else:
                        training_counts["retained_disagreement_train_row_count"] += 1
                else:
                    training_counts["masked_status_train_row_count"] += 1
            if str(split) != "prediction":
                continue
            if point_index >= len(points) or not isinstance(points[point_index], Mapping):
                raise CareFullScaleError("full-scale prediction status evidence is incomplete")
            point = points[point_index]
            expected = {
                "source_row_id": int(row_ids[batch_index]),
                "status_id": status_id,
                "disagreement_run_length": evidence[batch_index].disagreement_run_length,
                "corroborated_by_signal": evidence[batch_index].corroborated_by_signal,
                "corroboration_signal_count": evidence[batch_index].corroboration_signal_count,
                "corroboration_finite_signal_count": evidence[
                    batch_index
                ].corroboration_finite_signal_count,
                "corroboration_inactive_or_invalid_signal_count": evidence[
                    batch_index
                ].corroboration_inactive_or_invalid_signal_count,
                "corroboration_rule_id": STATUS_CORROBORATION_RULE_ID,
            }
            if any(point.get(key) != value for key, value in expected.items()):
                raise CareFullScaleError(
                    "full-scale prediction status evidence differs from raw status and signals"
                )
            point_index += 1
    if point_index != len(points):
        raise CareFullScaleError("full-scale prediction status evidence has extra points")
    return training_counts


def verify_full_scale_prediction_model_inputs(
    prediction: Mapping[str, Any],
    *,
    output_root: Path,
    event: Mapping[str, Any],
    features: Sequence[str],
    status_signal_columns: Sequence[str],
    profile: Mapping[str, Any],
) -> dict[str, int]:
    """Recompute quality-mask application and scores from immutable model inputs."""

    training_counts = verify_full_scale_prediction_status_evidence(
        prediction,
        output_root=output_root,
        event=event,
        status_signal_columns=status_signal_columns,
    )
    expected_policy = _quality_mask_policy(features)
    event_quality = event.get("quality")
    mask_reference = event_quality.get("mask") if isinstance(event_quality, Mapping) else None
    if (
        prediction.get("quality_mask_policy") != expected_policy
        or not isinstance(mask_reference, Mapping)
        or prediction.get("quality_mask_reference") != dict(mask_reference)
    ):
        raise CareFullScaleError("full-scale prediction quality mask lineage is invalid")
    mask_artifact = _load_quality_mask_artifact(output_root, event)
    mask_index = _quality_mask_index(mask_artifact, features)
    selected_columns = set(features)
    selected_range_count = sum(
        1
        for item in mask_artifact["quality_mask_ranges"]
        if str(item["source_column"]) in selected_columns
    )
    if (
        prediction.get("quality_mask_range_count") != mask_artifact.get("mask_count")
        or prediction.get("selected_quality_mask_range_count") != selected_range_count
    ):
        raise CareFullScaleError("full-scale prediction quality mask counts are invalid")

    points = prediction.get("points")
    if not isinstance(points, list):
        raise CareFullScaleError("full-scale prediction points are missing")
    np = importlib.import_module("numpy")
    means = np.asarray(profile["means"], dtype=np.float64)
    standard_deviations = np.asarray(profile["standard_deviations"], dtype=np.float64)
    point_index = 0
    masked_value_count = 0
    masked_point_count = 0
    nonfinite_value_count = 0
    imputed_value_count = 0
    score_changed_count = 0
    binary_changed_count = 0
    absolute_score_deltas: list[float] = []
    columns = ("id", "train_test", *features)
    for batch in _iter_event_batches(output_root, event, columns):
        row_ids = _batch_values(batch, "id")
        splits = _batch_values(batch, "train_test")
        all_values = _feature_matrix(batch, features, np)
        all_masks = _quality_mask_matrix(
            row_ids=row_ids,
            feature_columns=features,
            mask_index=mask_index,
            np=np,
        )
        prediction_positions = [
            index for index, value in enumerate(splits) if str(value) == "prediction"
        ]
        if not prediction_positions:
            continue
        values = all_values[prediction_positions]
        quality_masks = all_masks[prediction_positions]
        finite = np.isfinite(values)
        usable = finite & ~quality_masks
        imputed = np.where(usable, values, means)
        scores = np.max(np.abs((imputed - means) / standard_deviations), axis=1)
        ignored_mask_values = np.where(finite, values, means)
        ignored_mask_scores = np.max(
            np.abs((ignored_mask_values - means) / standard_deviations),
            axis=1,
        )
        for score_index, batch_index in enumerate(prediction_positions):
            if point_index >= len(points) or not isinstance(points[point_index], Mapping):
                raise CareFullScaleError("full-scale prediction model-input evidence is incomplete")
            point = points[point_index]
            quality_count = int(quality_masks[score_index].sum())
            nonfinite_count = int((~finite[score_index]).sum())
            imputed_count = int((~usable[score_index]).sum())
            score = float(scores[score_index])
            ignored_score = float(ignored_mask_scores[score_index])
            score_delta = score - ignored_score
            binary_changed = (score > FULL_SCALE_THRESHOLD) != (
                ignored_score > FULL_SCALE_THRESHOLD
            )
            if (
                point.get("source_row_id") != int(row_ids[batch_index])
                or point.get("quality_masked_feature_count") != quality_count
                or point.get("nonfinite_feature_count") != nonfinite_count
                or point.get("imputed_feature_count") != imputed_count
                or point.get("anomaly_score") != score
                or point.get("quality_mask_ignored_anomaly_score") != ignored_score
                or point.get("quality_mask_score_delta") != score_delta
                or point.get("quality_mask_changed_binary_prediction") is not binary_changed
            ):
                raise CareFullScaleError(
                    "full-scale prediction differs from raw values, quality mask, and fold"
                )
            masked_value_count += quality_count
            masked_point_count += int(quality_count > 0)
            nonfinite_value_count += nonfinite_count
            imputed_value_count += imputed_count
            score_changed_count += int(score_delta != 0.0)
            binary_changed_count += int(binary_changed)
            absolute_score_deltas.append(abs(score_delta))
            point_index += 1
    if point_index != len(points):
        raise CareFullScaleError("full-scale prediction model-input evidence has extra points")
    expected_counts = {
        "quality_masked_prediction_feature_value_count": masked_value_count,
        "quality_masked_prediction_point_count": masked_point_count,
        "nonfinite_prediction_feature_value_count": nonfinite_value_count,
        "imputed_prediction_feature_value_count": imputed_value_count,
        "quality_mask_score_changed_prediction_point_count": score_changed_count,
        "quality_mask_binary_decision_changed_point_count": binary_changed_count,
        "quality_mask_max_absolute_score_delta": max(absolute_score_deltas, default=0.0),
        "quality_mask_mean_absolute_score_delta": (
            sum(absolute_score_deltas) / len(absolute_score_deltas)
        ),
    }
    if any(prediction.get(name) != count for name, count in expected_counts.items()):
        raise CareFullScaleError("full-scale prediction model-input totals are invalid")
    if prediction.get("quality_mask_impact_interpretation") != (
        "counterfactual ignores prediction-time masks while retaining the same "
        "mask-trained fold; training-profile changes are proven separately by "
        "raw fold recomputation"
    ):
        raise CareFullScaleError("full-scale prediction mask impact interpretation is invalid")
    return training_counts


def _operational_policy(resource_limits: FullScaleResourceLimits) -> dict[str, Any]:
    payload = {
        "policy_version": FULL_SCALE_OPERATIONAL_POLICY_VERSION,
        "permissions": {
            "catalog": ["benchmark"],
            "truth": ["benchmark", "benchmark_truth"],
            "export": ["benchmark", "model", "benchmark_export"],
            "external_export_review": "required",
            "normal_worker_delete_allowed": False,
            "raw_cleanup_allowed": False,
        },
        "backup_recovery": {
            "bucket": CareObjectStorageLayout().bucket,
            "required_layers": ["raw", "standard", "quality", "predictions", "reports"],
            "versioning_required": True,
            "restore_requires_hash_verification": True,
            "restore_requires_sha256_object_metadata": True,
            "care_authoritative_table_invariants_required": True,
            "temporary_prefix_backed_up": False,
            "database_contains_full_signal_expansion": False,
        },
        "fault_recovery": {
            "storage_unavailable_state": "pending-or-failed-observable",
            "corrupt_checkpoint_state": "failed-closed",
            "cancel_state": "cancelled",
            "resume_mechanism": "new-job-id-reuses-verified-event-checkpoints",
            "maximum_attempts_per_job": 3,
            "partial_final_manifest_allowed": False,
        },
        "serving_limits": {
            "catalog_event_page_rows": resource_limits.catalog_event_page_rows,
            "curve_response_points": resource_limits.curve_response_points,
            "frontend_api_response_bytes": resource_limits.frontend_api_response_bytes,
            "query_p95_milliseconds": resource_limits.query_p95_milliseconds,
            "replay_batch_rows": resource_limits.replay_batch_rows,
            "min_replay_write_rows_per_second": MIN_REPLAY_WRITE_ROWS_PER_SECOND,
        },
    }
    return {**payload, "policy_sha256": _canonical_hash(payload)}


def _verify_operational_policy(value: Mapping[str, Any]) -> None:
    actual = value.get("policy_sha256")
    unsigned = {key: item for key, item in value.items() if key != "policy_sha256"}
    permissions = value.get("permissions")
    backup = value.get("backup_recovery")
    fault = value.get("fault_recovery")
    serving = value.get("serving_limits")
    if (
        not _is_sha256(actual)
        or _canonical_hash(unsigned) != actual
        or value.get("policy_version") != FULL_SCALE_OPERATIONAL_POLICY_VERSION
        or not isinstance(permissions, Mapping)
        or permissions.get("normal_worker_delete_allowed") is not False
        or permissions.get("raw_cleanup_allowed") is not False
        or not isinstance(backup, Mapping)
        or backup.get("required_layers") != ["raw", "standard", "quality", "predictions", "reports"]
        or backup.get("restore_requires_sha256_object_metadata") is not True
        or backup.get("care_authoritative_table_invariants_required") is not True
        or backup.get("temporary_prefix_backed_up") is not False
        or backup.get("database_contains_full_signal_expansion") is not False
        or not isinstance(fault, Mapping)
        or fault.get("partial_final_manifest_allowed") is not False
        or not isinstance(serving, Mapping)
        or serving.get("min_replay_write_rows_per_second") != MIN_REPLAY_WRITE_ROWS_PER_SECOND
    ):
        raise CareFullScaleError("full-scale operational policy is invalid")


def _verify_model_package(value: Mapping[str, Any]) -> None:
    actual = value.get("model_package_sha256")
    unsigned = {key: item for key, item in value.items() if key != "model_package_sha256"}
    profiles = value.get("fold_profiles")
    features = value.get("feature_columns")
    farm = value.get("farm")
    status_policy = value.get("status_evidence_policy")
    quality_mask_policy = value.get("quality_mask_policy")
    quality_mask_lineage = value.get("quality_mask_lineage")
    if (
        not _is_sha256(actual)
        or _canonical_hash(unsigned) != actual
        or value.get("schema_version") != FULL_SCALE_MODEL_SCHEMA_VERSION
        or value.get("model_kind") != "anomaly"
        or value.get("model_version") != FULL_SCALE_MODEL_VERSION
        or value.get("generalization_protocol") != "within-farm-leave-one-turbine-out-v1"
        or value.get("prediction_truth_used") is not False
        or not isinstance(features, list)
        or not features
        or not isinstance(profiles, list)
        or not profiles
        or farm not in FULL_SCALE_STAGE_ORDER
        or not isinstance(status_policy, Mapping)
        or not isinstance(quality_mask_policy, Mapping)
        or not isinstance(quality_mask_lineage, Mapping)
    ):
        raise CareFullScaleError("full-scale model package identity is invalid")
    expected_quality_mask_policy = _quality_mask_policy([str(item) for item in features])
    if dict(quality_mask_policy) != expected_quality_mask_policy:
        raise CareFullScaleError("full-scale model quality mask policy drifted")
    lineage_hash = quality_mask_lineage.get("lineage_sha256")
    lineage_unsigned = {
        key: item for key, item in quality_mask_lineage.items() if key != "lineage_sha256"
    }
    lineage_events = quality_mask_lineage.get("events")
    if (
        not _is_sha256(lineage_hash)
        or _canonical_hash(lineage_unsigned) != lineage_hash
        or quality_mask_lineage.get("farm") != farm
        or quality_mask_lineage.get("excluded_asset_id") is not None
        or not isinstance(lineage_events, list)
        or quality_mask_lineage.get("event_count") != len(lineage_events)
        or not lineage_events
    ):
        raise CareFullScaleError("full-scale model quality mask lineage is invalid")
    seen_mask_events: set[int] = set()
    for lineage_event in lineage_events:
        if not isinstance(lineage_event, Mapping):
            raise CareFullScaleError("full-scale model quality mask event is malformed")
        event_id = lineage_event.get("event_id")
        mask_count = lineage_event.get("mask_range_count")
        if (
            not isinstance(event_id, int)
            or isinstance(event_id, bool)
            or event_id in seen_mask_events
            or not isinstance(lineage_event.get("source_asset_id"), str)
            or not _is_sha256(lineage_event.get("quality_mask_file_sha256"))
            or not _is_sha256(lineage_event.get("source_quality_report_sha256"))
            or not isinstance(mask_count, int)
            or isinstance(mask_count, bool)
            or mask_count < 0
        ):
            raise CareFullScaleError("full-scale model quality mask event is invalid")
        seen_mask_events.add(event_id)
    status_signal_columns = status_policy.get("corroboration_signal_columns")
    if (
        not isinstance(status_signal_columns, list)
        or any(not isinstance(item, str) for item in status_signal_columns)
        or any(item not in features for item in status_signal_columns)
    ):
        raise CareFullScaleError("full-scale model status evidence policy is malformed")
    try:
        expected_status_policy = status_evidence_policy(str(farm), status_signal_columns)
    except CareContractError as exc:
        raise CareFullScaleError(str(exc)) from exc
    if dict(status_policy) != expected_status_policy:
        raise CareFullScaleError("full-scale model status evidence policy drifted")
    expected_length = len(features)
    held_out: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, Mapping):
            raise CareFullScaleError("full-scale model fold profile is malformed")
        asset = str(profile.get("held_out_asset_id", ""))
        if not asset or asset in held_out:
            raise CareFullScaleError("full-scale model fold identity is duplicated")
        held_out.add(asset)
        usable_rows = profile.get("status_usable_train_row_count")
        trusted_rows = profile.get("trusted_train_row_count")
        retained_rows = profile.get("retained_disagreement_train_row_count")
        masked_rows = profile.get("masked_status_train_row_count")
        quality_masked_rows = profile.get("quality_masked_train_row_count")
        quality_masked_values = profile.get("quality_masked_train_feature_value_count")
        quality_mask_counts = profile.get("quality_masked_train_feature_counts")
        quality_mask_event_count = profile.get("training_quality_mask_event_count")
        if (
            not isinstance(usable_rows, int)
            or isinstance(usable_rows, bool)
            or usable_rows < 0
            or not isinstance(trusted_rows, int)
            or isinstance(trusted_rows, bool)
            or trusted_rows < 0
            or not isinstance(retained_rows, int)
            or isinstance(retained_rows, bool)
            or retained_rows < 0
            or not isinstance(masked_rows, int)
            or isinstance(masked_rows, bool)
            or masked_rows < 0
            or not isinstance(quality_masked_rows, int)
            or isinstance(quality_masked_rows, bool)
            or quality_masked_rows < 0
            or quality_masked_rows > usable_rows
            or not isinstance(quality_masked_values, int)
            or isinstance(quality_masked_values, bool)
            or quality_masked_values < 0
            or not isinstance(quality_mask_counts, list)
            or len(quality_mask_counts) != expected_length
            or any(
                not isinstance(item, int) or isinstance(item, bool) or item < 0
                for item in quality_mask_counts
            )
            or sum(quality_mask_counts) != quality_masked_values
            or profile.get("quality_mask_policy_sha256") != quality_mask_policy["policy_sha256"]
            or not _is_sha256(profile.get("training_quality_mask_lineage_sha256"))
            or not isinstance(quality_mask_event_count, int)
            or isinstance(quality_mask_event_count, bool)
            or quality_mask_event_count < 1
            or profile.get("imputation")
            != "leave-one-asset-out-feature-mean-for-nonfinite-or-quality-masked-v2"
            or usable_rows != trusted_rows + retained_rows
        ):
            raise CareFullScaleError(f"full-scale fold {asset} status counts are invalid")
        for name in ("finite_counts", "means", "standard_deviations"):
            values = profile.get(name)
            if not isinstance(values, list) or len(values) != expected_length:
                raise CareFullScaleError(f"full-scale fold {asset} {name} shape is invalid")
            if any(
                isinstance(item, bool)
                or not isinstance(item, int | float)
                or not math.isfinite(float(item))
                for item in values
            ):
                raise CareFullScaleError(f"full-scale fold {asset} {name} is non-finite")
    _verify_license(value)


def _evaluate_resource_gate(
    *,
    elapsed_seconds: float,
    storage_bytes: int,
    prediction_count: int,
    peak_batch: int,
    peak_arrow: int,
    peak_resident: int,
    limits: FullScaleResourceLimits,
) -> dict[str, Any]:
    violations = []
    if elapsed_seconds > limits.max_evaluation_runtime_seconds:
        violations.append("max_evaluation_runtime_seconds")
    if storage_bytes > limits.max_evaluation_storage_bytes:
        violations.append("max_evaluation_storage_bytes")
    if prediction_count > limits.max_prediction_points:
        violations.append("max_prediction_points")
    if peak_batch > limits.max_peak_record_batch_bytes:
        violations.append("max_peak_record_batch_bytes")
    if peak_arrow > limits.max_peak_arrow_allocated_bytes:
        violations.append("max_peak_arrow_allocated_bytes")
    if peak_resident > limits.max_peak_process_resident_bytes:
        violations.append("max_peak_process_resident_bytes")
    if violations:
        raise CareFullScaleResourceError(
            f"full-scale evaluation exceeded preregistered resources: {', '.join(violations)}"
        )
    return {
        "elapsed_seconds": elapsed_seconds,
        "storage_bytes": storage_bytes,
        "prediction_point_count": prediction_count,
        "peak_record_batch_bytes": peak_batch,
        "peak_arrow_allocated_bytes": peak_arrow,
        "peak_process_resident_bytes": peak_resident,
        "limits_passed": True,
        "violations": [],
    }


def build_full_scale_evaluation(
    import_manifest: Mapping[str, Any],
    output_root: Path,
    *,
    artifact_store: ImmutableArtifactStore | None = None,
    job_id: str = "care-v6-full-evaluation",
    state_path: Path | None = None,
    stop_after_predictions: int | None = None,
    expected_counts: FullScaleExpectedCounts = CARE_V6_FULL_SCALE_COUNTS,
    resource_limits: FullScaleResourceLimits = DEFAULT_FULL_SCALE_RESOURCE_LIMITS,
    trust_anchor: CareTrustAnchor | None = None,
) -> FullScaleEvaluationResult:
    """Run two bounded passes and evaluate one held-out-asset fold per farm asset."""

    approval = import_manifest.get("care_approval")
    if not isinstance(approval, Mapping):
        raise CareFullScaleError("full-scale import is missing CARE approved-root lineage")
    try:
        verify_embedded_care_approval(approval, trust_anchor=trust_anchor)
    except CareContractError as exc:
        raise CareFullScaleError(str(exc)) from exc
    if approval.get("source_manifest_sha256") != import_manifest.get(
        "source_manifest_sha256"
    ) or approval.get("quality_contract_sha256") != import_manifest.get("quality_contract_sha256"):
        raise CareFullScaleError("full-scale import approved-root lineage hashes drifted")

    output_root = output_root.resolve()
    manifest_path = (
        output_root / DATASET_ID / DATASET_VERSION / "reports" / "full-evaluation" / "manifest.json"
    )
    if manifest_path.exists():
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise CareFullScaleError("full-scale evaluation manifest root must be an object")
        verify_full_scale_evaluation_manifest(
            raw,
            output_root=output_root,
            import_manifest=import_manifest,
            expected_counts=expected_counts,
            resource_limits=resource_limits,
            trust_anchor=trust_anchor,
        )
        return FullScaleEvaluationResult(manifest_path, raw, _sha256_file(manifest_path), True)
    if (
        import_manifest.get("schema_version") != FULL_SCALE_IMPORT_SCHEMA_VERSION
        or import_manifest.get("summary") != expected_counts.to_document()
        or import_manifest.get("raw_source_unchanged") is not True
    ):
        raise CareFullScaleError("full-scale evaluation requires a verified import manifest")
    source_dataset_sha256 = str(import_manifest["source_dataset_sha256"])
    quality_contract_sha256 = str(import_manifest["quality_contract_sha256"])
    if not _is_sha256(source_dataset_sha256) or not _is_sha256(quality_contract_sha256):
        raise CareFullScaleError("full-scale evaluation control hashes are invalid")
    features_by_farm, status_signals_by_farm = _evaluation_column_contracts(
        output_root,
        import_manifest,
    )

    state_file = state_path or output_root / ".state" / f"{job_id}.json"
    job_control = FileBenchmarkJobControl(
        state_file,
        BenchmarkJobState.pending(job_id, "evaluate"),
    )
    state = job_control.start_attempt()
    if state.status == "cancelled":
        raise BenchmarkJobCancelled("full-scale evaluation was cancelled before restart")
    layout = CareObjectStorageLayout()
    started = time.perf_counter()
    try:
        totals, asset_moments, training_resources = _accumulate_moments(
            import_manifest=import_manifest,
            output_root=output_root,
            features_by_farm=features_by_farm,
            status_signals_by_farm=status_signals_by_farm,
        )
        profiles = _build_fold_profiles(
            totals=totals,
            assets=asset_moments,
            features_by_farm=features_by_farm,
            import_manifest=import_manifest,
        )
        if len(profiles) != expected_counts.asset_count:
            raise CareFullScaleError("full-scale fold count differs from farm-namespaced assets")

        model_references: dict[str, Mapping[str, Any]] = {}
        for farm in FULL_SCALE_STAGE_ORDER:
            farm_profiles = [
                profiles[(profile_farm, asset)]
                for profile_farm, asset in sorted(profiles)
                if profile_farm == farm
            ]
            quality_mask_policy = _quality_mask_policy(features_by_farm[farm])
            quality_mask_lineage = _quality_mask_lineage(import_manifest, farm)
            model_payload = {
                "schema_version": FULL_SCALE_MODEL_SCHEMA_VERSION,
                "dataset_id": DATASET_ID,
                "dataset_version": DATASET_VERSION,
                "farm": farm,
                "model_id": _model_id(farm),
                "model_version": FULL_SCALE_MODEL_VERSION,
                "model_kind": "anomaly",
                "algorithm": "maximum-absolute-leave-one-asset-standard-score",
                "generalization_protocol": "within-farm-leave-one-turbine-out-v1",
                "feature_set_version": FEATURE_SET_VERSION,
                "feature_set_sha256": _canonical_hash(list(features_by_farm[farm])),
                "feature_columns": list(features_by_farm[farm]),
                "quality_rule_version": QUALITY_RULE_VERSION,
                "quality_contract_sha256": quality_contract_sha256,
                "quality_mask_policy": quality_mask_policy,
                "quality_mask_lineage": quality_mask_lineage,
                "care_approval": dict(approval),
                "threshold_policy": _threshold_policy().to_dict(),
                "fold_profiles": farm_profiles,
                "dependency_identity": {
                    "implementation": FULL_SCALE_EVALUATION_VERSION,
                    "numpy": importlib.metadata.version("numpy"),
                    "pyarrow": importlib.metadata.version("pyarrow"),
                    "python_numeric_contract": "float64-streaming-sum-sumsq-v1",
                },
                "training_split": "train",
                "trusted_train_status_ids": list(FULL_SCALE_TRAIN_STATUS_IDS),
                "status_evidence_policy": status_evidence_policy(
                    farm,
                    status_signals_by_farm[farm],
                ),
                "prediction_truth_used": False,
                "cross_farm_ontology_used": False,
                "license": build_care_artifact_license(
                    artifact_type="full-scale-anomaly-model-package",
                    changes_made=(
                        "Computed per-farm leave-one-asset-out means and standard deviations "
                        "from status-usable train rows after applying immutable feature masks; "
                        "no prediction truth was read."
                    ),
                    source_dataset_sha256=source_dataset_sha256,
                    source_artifact_sha256=str(import_manifest["manifest_sha256"]),
                    transformation_versions={
                        "evaluation": FULL_SCALE_EVALUATION_VERSION,
                        "feature_set": FEATURE_SET_VERSION,
                        "quality_rules": QUALITY_RULE_VERSION,
                        "score_protocol": SCORE_PROTOCOL_VERSION,
                    },
                ),
            }
            model = {**model_payload, "model_package_sha256": _canonical_hash(model_payload)}
            _verify_model_package(model)
            model_path = (
                output_root
                / DATASET_ID
                / DATASET_VERSION
                / "reports"
                / "full-evaluation"
                / "models"
                / f"farm={farm}"
                / "model.json"
            )
            model_references[farm] = _publish_self_hashed_json(
                output_root=output_root,
                path=model_path,
                document=model,
                document_sha256=str(model["model_package_sha256"]),
                object_key_prefix=(
                    f"{layout.reports_prefix}/full-evaluation/models/farm={farm}/model"
                ),
                artifact_store=artifact_store,
            )

        prediction_references: dict[str, Mapping[str, Any]] = {}
        prediction_resources: list[Mapping[str, Any]] = []
        completed_predictions = 0
        for event in import_manifest["events"]:
            job_control.cancellation_point()
            farm = str(event["farm"])
            asset = str(event["source_asset_id"])
            event_id = int(event["event_id"])
            prediction_path = (
                output_root
                / DATASET_ID
                / DATASET_VERSION
                / "predictions"
                / "full-evaluation"
                / f"model={_model_id(farm)}"
                / f"farm={farm}"
                / f"event={event_id}.json"
            )
            existing_reference: Mapping[str, Any] | None = None
            if prediction_path.exists():
                raw_prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
                if not isinstance(raw_prediction, Mapping):
                    raise CareFullScaleError("full-scale prediction root must be an object")
                verify_full_scale_prediction_model_inputs(
                    raw_prediction,
                    output_root=output_root,
                    event=event,
                    features=features_by_farm[farm],
                    status_signal_columns=status_signals_by_farm[farm],
                    profile=profiles[(farm, asset)],
                )
                if (
                    raw_prediction.get("event_id") != event_id
                    or raw_prediction.get("farm") != farm
                    or str(raw_prediction.get("source_asset_id")) != asset
                    or raw_prediction.get("model_id") != _model_id(farm)
                ):
                    raise CareFullScaleError("existing full-scale prediction identity drifted")
                existing_reference = _artifact_reference(
                    output_root=output_root,
                    path=prediction_path,
                    artifact_uri=prediction_path.resolve().as_uri(),
                    file_sha256=_sha256_file(prediction_path),
                    document_sha256=str(raw_prediction["prediction_artifact_sha256"]),
                )
                resources = {
                    "elapsed_seconds": 0.0,
                    "prediction_point_count": int(raw_prediction["point_count"]),
                    "peak_record_batch_bytes": 0,
                    "peak_arrow_allocated_bytes": 0,
                    "resumed": True,
                }
            else:
                prediction, resources = _build_prediction(
                    event=event,
                    output_root=output_root,
                    features=features_by_farm[farm],
                    status_signal_columns=status_signals_by_farm[farm],
                    profile=profiles[(farm, asset)],
                    feature_set_sha256=_canonical_hash(list(features_by_farm[farm])),
                    quality_contract_sha256=quality_contract_sha256,
                    approval_lineage=approval,
                    license_metadata=build_care_artifact_license(
                        artifact_type="full-scale-event-prediction",
                        changes_made=(
                            "Applied the held-out-asset farm profile to prediction rows and "
                            "saved scores, binary decisions, status masks, and criticality."
                        ),
                        source_dataset_sha256=source_dataset_sha256,
                        source_artifact_sha256=str(event["parquet"]["data"]["file_sha256"]),
                        transformation_versions={
                            "evaluation": FULL_SCALE_EVALUATION_VERSION,
                            "feature_set": FEATURE_SET_VERSION,
                            "quality_rules": QUALITY_RULE_VERSION,
                            "score_protocol": SCORE_PROTOCOL_VERSION,
                        },
                    ),
                )
                existing_reference = _publish_self_hashed_json(
                    output_root=output_root,
                    path=prediction_path,
                    document=prediction,
                    document_sha256=str(prediction["prediction_artifact_sha256"]),
                    object_key_prefix=(
                        f"{layout.predictions_prefix}/full-evaluation/model={_model_id(farm)}/farm={farm}/event={event_id}/prediction"
                    ),
                    artifact_store=artifact_store,
                )
                completed_predictions += 1
            prediction_references[str(event_id)] = existing_reference
            prediction_resources.append({"event_id": event_id, **resources})
            job_control.heartbeat(
                completed=len(prediction_references),
                total=len(import_manifest["events"]),
                current_file=str(prediction_path),
                checkpoint_path=str(prediction_path),
                resource_stats={
                    "prediction_event_count": len(prediction_references),
                    "prediction_point_count": sum(
                        int(item["prediction_point_count"]) for item in prediction_resources
                    ),
                },
            )
            if (
                stop_after_predictions is not None
                and completed_predictions >= stop_after_predictions
            ):
                job_control.request_cancel()
                job_control.cancellation_point()

        freeze_payload = {
            "schema_version": FULL_SCALE_PREDICTION_FREEZE_SCHEMA_VERSION,
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "source_import_manifest_sha256": import_manifest["manifest_sha256"],
            "care_approval": dict(approval),
            "prediction_truth_present": False,
            "prediction_truth_read": False,
            "quality_mask_policy_version": FULL_SCALE_QUALITY_MASK_POLICY_VERSION,
            "quality_masks_applied": True,
            "event_ids": [int(event["event_id"]) for event in import_manifest["events"]],
            "prediction_artifacts": prediction_references,
            "prediction_event_count": len(prediction_references),
            "prediction_point_count": sum(
                int(item["prediction_point_count"]) for item in prediction_resources
            ),
        }
        freeze = {**freeze_payload, "freeze_sha256": _canonical_hash(freeze_payload)}
        freeze_path = (
            output_root
            / DATASET_ID
            / DATASET_VERSION
            / "reports"
            / "full-evaluation"
            / "prediction-freeze.json"
        )
        freeze_reference = _publish_self_hashed_json(
            output_root=output_root,
            path=freeze_path,
            document=freeze,
            document_sha256=str(freeze["freeze_sha256"]),
            object_key_prefix=f"{layout.reports_prefix}/full-evaluation/prediction-freeze",
            artifact_store=artifact_store,
        )

        # Truth is intentionally opened only after all truth-free predictions are frozen.
        truths = {
            int(event["event_id"]): _truth_from_event(output_root, event)
            for event in import_manifest["events"]
        }
        fold_references: list[Mapping[str, Any]] = []
        fold_summaries: list[Mapping[str, Any]] = []
        accounted_events: set[int] = set()
        for farm, asset in sorted(profiles):
            fold_events = [
                event
                for event in import_manifest["events"]
                if event["farm"] == farm and str(event["source_asset_id"]) == asset
            ]
            event_ids = tuple(int(event["event_id"]) for event in fold_events)
            predictions = [
                _load_json_reference(output_root, prediction_references[str(event_id)])
                for event_id in event_ids
            ]
            evaluator = FinalCareEvaluator(
                PredictionTruthVault(tuple(truths[event_id] for event_id in event_ids))
            )
            run = EvaluationRunSpec(
                run_id=(f"care-v6-{farm.lower()}-loao-{_safe_token(asset)}-final-v2"),
                purpose="final-holdout",
                generalization_protocol="within-farm-leave-one-turbine-out-v1",
                event_ids=event_ids,
                model_id=_model_id(farm),
                model_version=FULL_SCALE_MODEL_VERSION,
                created_at=FULL_SCALE_PROTOCOL_FROZEN_AT,
                farm=farm,
                held_out_asset_id=asset,
            )
            evaluation = build_evaluation_artifact(
                run,
                evaluator,
                predictions,
                approval_lineage=approval,
            )
            fold_profile = profiles[(farm, asset)]
            prediction_quality_masks = [
                {
                    "event_id": int(prediction["event_id"]),
                    "quality_mask_file_sha256": prediction["quality_mask_reference"]["file_sha256"],
                    "quality_mask_range_count": prediction["quality_mask_range_count"],
                    "quality_masked_prediction_feature_value_count": prediction[
                        "quality_masked_prediction_feature_value_count"
                    ],
                    "quality_masked_prediction_point_count": prediction[
                        "quality_masked_prediction_point_count"
                    ],
                }
                for prediction in predictions
            ]
            fold_payload = {
                "schema_version": FULL_SCALE_FOLD_SCHEMA_VERSION,
                "dataset_id": DATASET_ID,
                "dataset_version": DATASET_VERSION,
                "farm": farm,
                "held_out_asset_id": asset,
                "generalization_protocol": "within-farm-leave-one-turbine-out-v1",
                "prediction_freeze_sha256": freeze["freeze_sha256"],
                "truth_read_after_prediction_freeze": True,
                "model_package_sha256": model_references[farm]["document_sha256"],
                "quality_mask_policy": _quality_mask_policy(features_by_farm[farm]),
                "fold_profile": dict(fold_profile),
                "prediction_quality_masks": prediction_quality_masks,
                "evaluation": evaluation,
                "care_approval": dict(approval),
                "license": build_care_artifact_license(
                    artifact_type="within-farm-evaluation-fold",
                    changes_made=(
                        "Evaluated one farm-namespaced held-out asset after every prediction "
                        "artifact was frozen; training and prediction mask lineage was retained, "
                        "and truth was unavailable to training and calibration."
                    ),
                    source_dataset_sha256=source_dataset_sha256,
                    source_artifact_sha256=str(freeze["freeze_sha256"]),
                    transformation_versions={
                        "evaluation": FULL_SCALE_EVALUATION_VERSION,
                        "feature_set": FEATURE_SET_VERSION,
                        "quality_rules": QUALITY_RULE_VERSION,
                        "score_protocol": SCORE_PROTOCOL_VERSION,
                    },
                ),
            }
            fold = {**fold_payload, "document_sha256": _canonical_hash(fold_payload)}
            fold_path = (
                output_root
                / DATASET_ID
                / DATASET_VERSION
                / "reports"
                / "full-evaluation"
                / "folds"
                / f"farm={farm}"
                / f"held-out-asset={_safe_token(asset)}.json"
            )
            fold_reference = _publish_self_hashed_json(
                output_root=output_root,
                path=fold_path,
                document=fold,
                document_sha256=str(fold["document_sha256"]),
                object_key_prefix=(
                    f"{layout.reports_prefix}/full-evaluation/folds/farm={farm}/held-out-asset={_safe_token(asset)}"
                ),
                artifact_store=artifact_store,
            )
            fold_references.append(fold_reference)
            summary = evaluation["summary"]
            fold_summaries.append(
                {
                    "farm": farm,
                    "held_out_asset_id": asset,
                    "run_id": run.run_id,
                    "event_ids": list(event_ids),
                    "requested_event_count": summary["requested_event_count"],
                    "scored_event_count": summary["scored_event_count"],
                    "unscorable_event_count": summary["unscorable_event_count"],
                    "data_failure_event_count": summary["data_failure_event_count"],
                    "model_failure_event_count": summary["model_failure_event_count"],
                    "care_score": summary.get("care_score"),
                    "normal_event_false_positive_rate": summary.get("event_metrics", {}).get(
                        "normal_event_false_positive_rate"
                    ),
                    "event_detection_rate": summary.get("event_metrics", {}).get(
                        "event_detection_rate"
                    ),
                    "release_candidate_passed": (
                        summary.get("status") == "scored"
                        and float(summary.get("care_score", 0.0)) >= 0.5
                        and int(summary.get("unscorable_event_count", 0)) == 0
                        and int(summary.get("data_failure_event_count", 0)) == 0
                        and int(summary.get("model_failure_event_count", 0)) == 0
                    ),
                }
            )
            if accounted_events.intersection(event_ids):
                raise CareFullScaleError("full-scale event was evaluated in more than one fold")
            accounted_events.update(event_ids)
        expected_event_ids = {int(event["event_id"]) for event in import_manifest["events"]}
        if accounted_events != expected_event_ids:
            raise CareFullScaleError("full-scale folds do not account for every event")

        peak_resident = peak_process_resident_bytes()
        evaluation_elapsed = time.perf_counter() - started
        storage_bytes = sum(
            int(reference["size_bytes"])
            for reference in [
                *model_references.values(),
                *prediction_references.values(),
                freeze_reference,
                *fold_references,
            ]
        )
        prediction_count = int(freeze["prediction_point_count"])
        peak_batch = max(
            int(training_resources["peak_record_batch_bytes"]),
            max(
                (int(item["peak_record_batch_bytes"]) for item in prediction_resources),
                default=0,
            ),
        )
        peak_arrow = max(
            int(training_resources["peak_arrow_allocated_bytes"]),
            max(
                (int(item["peak_arrow_allocated_bytes"]) for item in prediction_resources),
                default=0,
            ),
        )
        resource_actual = _evaluate_resource_gate(
            elapsed_seconds=evaluation_elapsed,
            storage_bytes=storage_bytes,
            prediction_count=prediction_count,
            peak_batch=peak_batch,
            peak_arrow=peak_arrow,
            peak_resident=peak_resident,
            limits=resource_limits,
        )
        candidate_pass_count = sum(
            bool(summary["release_candidate_passed"]) for summary in fold_summaries
        )
        quality_mask_impact = _quality_mask_impact_summary(
            training_resources,
            [
                _load_json_reference(output_root, prediction_references[str(event["event_id"])])
                for event in import_manifest["events"]
            ],
        )
        payload = {
            "schema_version": FULL_SCALE_EVALUATION_SCHEMA_VERSION,
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "source_import_manifest_sha256": import_manifest["manifest_sha256"],
            "source_dataset_sha256": source_dataset_sha256,
            "quality_contract_sha256": quality_contract_sha256,
            "care_approval": dict(approval),
            "generalization_protocol": "within-farm-leave-one-turbine-out-v1",
            "farm_namespaced_fold_count": len(profiles),
            "model_packages": model_references,
            "prediction_freeze": freeze_reference,
            "fold_artifacts": fold_references,
            "fold_summaries": fold_summaries,
            "summary": {
                **expected_counts.to_document(),
                "prediction_event_count": len(prediction_references),
                "prediction_point_count": prediction_count,
                "fold_count": len(profiles),
                "candidate_release_pass_count": candidate_pass_count,
                "candidate_release_fail_count": len(profiles) - candidate_pass_count,
                "all_events_accounted_for": True,
            },
            "resource_policy": resource_limits.to_document(),
            "resource_actual": resource_actual,
            "training_resources": training_resources,
            "prediction_resources": prediction_resources,
            "quality_mask_impact": quality_mask_impact,
            "operational_policy": _operational_policy(resource_limits),
            "server_release_gate": {
                "authority": "immutable-evaluation-run-and-metric-snapshot-only",
                "frontend_or_json_override_allowed": False,
                "failed_or_unscorable_events_may_be_omitted": False,
                "candidate_results_are_recorded_even_when_gate_fails": True,
            },
            "cross_farm_protocol": {
                "status": "disabled",
                "reason": "canonical ontology and recorded human review are not complete",
                "human_review_ids": [],
            },
            "truth_boundary": {
                "prediction_freeze_completed_before_truth_read": True,
                "prediction_truth_available_to_training_or_calibration": False,
            },
            "license": build_care_artifact_license(
                artifact_type="full-scale-evaluation-manifest",
                changes_made=(
                    "Ran streaming within-farm leave-one-asset-out evaluation for every "
                    "farm-namespaced asset and retained all scored, failed, and unscorable "
                    "outcomes."
                ),
                source_dataset_sha256=source_dataset_sha256,
                source_artifact_sha256=str(import_manifest["manifest_sha256"]),
                transformation_versions={
                    "evaluation": FULL_SCALE_EVALUATION_VERSION,
                    "feature_set": FEATURE_SET_VERSION,
                    "quality_rules": QUALITY_RULE_VERSION,
                    "score_protocol": SCORE_PROTOCOL_VERSION,
                },
            ),
        }
        manifest = {**payload, "manifest_sha256": _canonical_hash(payload)}
        content = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _write_immutable_bytes(manifest_path, content)
        verify_full_scale_evaluation_manifest(
            manifest,
            output_root=output_root,
            import_manifest=import_manifest,
            expected_counts=expected_counts,
            resource_limits=resource_limits,
            trust_anchor=trust_anchor,
        )
        job_control.complete(manifest_path.resolve().as_uri(), resource_actual)
        return FullScaleEvaluationResult(
            manifest_path,
            manifest,
            hashlib.sha256(content).hexdigest(),
            False,
        )
    except BenchmarkJobCancelled:
        raise
    except Exception as exc:
        job_control.fail(exc, retryable=not isinstance(exc, CareFullScaleResourceError))
        raise


def verify_full_scale_evaluation_manifest(
    value: Mapping[str, Any],
    *,
    output_root: Path,
    import_manifest: Mapping[str, Any],
    expected_counts: FullScaleExpectedCounts = CARE_V6_FULL_SCALE_COUNTS,
    resource_limits: FullScaleResourceLimits = DEFAULT_FULL_SCALE_RESOURCE_LIMITS,
    trust_anchor: CareTrustAnchor | None = None,
) -> None:
    actual = value.get("manifest_sha256")
    unsigned = {key: item for key, item in value.items() if key != "manifest_sha256"}
    summary = value.get("summary")
    model_packages = value.get("model_packages")
    prediction_freeze = value.get("prediction_freeze")
    fold_artifacts = value.get("fold_artifacts")
    fold_summaries = value.get("fold_summaries")
    if (
        not _is_sha256(actual)
        or _canonical_hash(unsigned) != actual
        or value.get("schema_version") != FULL_SCALE_EVALUATION_SCHEMA_VERSION
        or value.get("source_import_manifest_sha256") != import_manifest["manifest_sha256"]
        or value.get("generalization_protocol") != "within-farm-leave-one-turbine-out-v1"
        or value.get("farm_namespaced_fold_count") != expected_counts.asset_count
        or not isinstance(summary, Mapping)
        or not isinstance(model_packages, Mapping)
        or not isinstance(prediction_freeze, Mapping)
        or not isinstance(fold_artifacts, list)
        or not isinstance(fold_summaries, list)
        or len(fold_artifacts) != expected_counts.asset_count
        or len(fold_summaries) != expected_counts.asset_count
    ):
        raise CareFullScaleError("full-scale evaluation manifest identity is invalid")
    approval = value.get("care_approval")
    if not isinstance(approval, Mapping) or approval != import_manifest.get("care_approval"):
        raise CareFullScaleError("full-scale evaluation approved-root lineage is invalid")
    try:
        verify_embedded_care_approval(approval, trust_anchor=trust_anchor)
    except CareContractError as exc:
        raise CareFullScaleError(str(exc)) from exc
    for key, expected in expected_counts.to_document().items():
        if summary.get(key) != expected:
            raise CareFullScaleError(f"full-scale evaluation summary {key} is invalid")
    if (
        summary.get("prediction_event_count") != expected_counts.event_count
        or summary.get("fold_count") != expected_counts.asset_count
        or summary.get("all_events_accounted_for") is not True
    ):
        raise CareFullScaleError("full-scale evaluation outcome coverage is incomplete")
    if (
        expected_counts == CARE_V6_FULL_SCALE_COUNTS
        and summary.get("prediction_point_count") != resource_prediction_count()
    ):
        raise CareFullScaleError("CARE v6 prediction point count is inconsistent")
    features_by_farm, status_signals_by_farm = _evaluation_column_contracts(
        output_root,
        import_manifest,
    )
    loaded_model_packages: dict[str, Mapping[str, Any]] = {}
    for farm, reference in model_packages.items():
        if farm not in FULL_SCALE_STAGE_ORDER or not isinstance(reference, Mapping):
            raise CareFullScaleError("full-scale model reference is malformed")
        model_package = _load_json_reference(output_root, reference)
        _verify_model_package(model_package)
        if (
            model_package.get("feature_columns") != list(features_by_farm[farm])
            or model_package.get("status_evidence_policy")
            != status_evidence_policy(farm, status_signals_by_farm[farm])
            or model_package.get("quality_mask_policy")
            != _quality_mask_policy(features_by_farm[farm])
            or model_package.get("quality_mask_lineage")
            != _quality_mask_lineage(import_manifest, farm)
        ):
            raise CareFullScaleError(
                "full-scale model inputs differ from the approved import mapping or masks"
            )
        loaded_model_packages[farm] = model_package
    if set(model_packages) != set(FULL_SCALE_STAGE_ORDER):
        raise CareFullScaleError("full-scale model packages do not cover every farm")
    freeze = _load_json_reference(output_root, prediction_freeze)
    freeze_unsigned = {key: item for key, item in freeze.items() if key != "freeze_sha256"}
    if (
        freeze.get("schema_version") != FULL_SCALE_PREDICTION_FREEZE_SCHEMA_VERSION
        or _canonical_hash(freeze_unsigned) != freeze.get("freeze_sha256")
        or freeze.get("prediction_truth_present") is not False
        or freeze.get("prediction_truth_read") is not False
        or freeze.get("quality_mask_policy_version") != FULL_SCALE_QUALITY_MASK_POLICY_VERSION
        or freeze.get("quality_masks_applied") is not True
        or freeze.get("prediction_event_count") != expected_counts.event_count
    ):
        raise CareFullScaleError("full-scale prediction freeze is invalid")
    prediction_references = freeze.get("prediction_artifacts")
    training_resources = value.get("training_resources")
    prediction_resources = value.get("prediction_resources")
    resource_actual = value.get("resource_actual")
    if (
        not isinstance(prediction_references, Mapping)
        or not isinstance(training_resources, Mapping)
        or not isinstance(prediction_resources, list)
        or len(prediction_resources) != expected_counts.event_count
        or any(not isinstance(item, Mapping) for item in prediction_resources)
        or any(not isinstance(item, Mapping) for item in fold_artifacts)
        or not isinstance(resource_actual, Mapping)
    ):
        raise CareFullScaleError("full-scale evaluation resource evidence is malformed")
    verification_totals, verification_assets, verification_training = _accumulate_moments(
        import_manifest=import_manifest,
        output_root=output_root,
        features_by_farm=features_by_farm,
        status_signals_by_farm=status_signals_by_farm,
    )
    expected_profiles = _build_fold_profiles(
        totals=verification_totals,
        assets=verification_assets,
        features_by_farm=features_by_farm,
        import_manifest=import_manifest,
    )
    verified_training_count_fields = (
        "scanned_row_count",
        "status_usable_train_row_count",
        "trusted_train_row_count",
        "retained_disagreement_train_row_count",
        "masked_status_train_row_count",
        "quality_masked_train_row_count",
        "quality_masked_train_feature_value_count",
    )
    if any(
        training_resources.get(name) != verification_training.get(name)
        for name in verified_training_count_fields
    ):
        raise CareFullScaleError(
            "full-scale training totals differ from raw rows and quality masks"
        )
    for farm, model_package in loaded_model_packages.items():
        for profile in model_package["fold_profiles"]:
            profile_key = (farm, str(profile["held_out_asset_id"]))
            if (
                profile_key not in expected_profiles
                or dict(profile) != expected_profiles[profile_key]
            ):
                raise CareFullScaleError(
                    "full-scale fold moments differ from raw rows and quality masks"
                )
    expected_events = {str(int(event["event_id"])): event for event in import_manifest["events"]}
    if set(prediction_references) != set(expected_events):
        raise CareFullScaleError("full-scale prediction references are incomplete")
    prediction_point_count = 0
    verified_predictions: list[Mapping[str, Any]] = []
    verified_prediction_by_event: dict[int, Mapping[str, Any]] = {}
    raw_training_counts_by_asset: dict[tuple[str, str], dict[str, int]] = {}
    for event_id, event in expected_events.items():
        reference = prediction_references[event_id]
        if not isinstance(reference, Mapping):
            raise CareFullScaleError("full-scale prediction reference is malformed")
        prediction = _load_json_reference(output_root, reference)
        verified_predictions.append(prediction)
        verified_prediction_by_event[int(event_id)] = prediction
        profile = expected_profiles[(str(event["farm"]), str(event["source_asset_id"]))]
        event_training_counts = verify_full_scale_prediction_model_inputs(
            prediction,
            output_root=output_root,
            event=event,
            features=features_by_farm[str(event["farm"])],
            status_signal_columns=status_signals_by_farm[str(event["farm"])],
            profile=profile,
        )
        asset_key = (str(event["farm"]), str(event["source_asset_id"]))
        asset_counts = raw_training_counts_by_asset.setdefault(
            asset_key,
            {name: 0 for name in event_training_counts},
        )
        for name, count in event_training_counts.items():
            asset_counts[name] += count
        if (
            prediction.get("event_id") != int(event_id)
            or prediction.get("farm") != event["farm"]
            or str(prediction.get("source_asset_id")) != str(event["source_asset_id"])
            or prediction.get("model_id") != _model_id(str(event["farm"]))
            or prediction.get("point_count") != int(event["split_counts"]["prediction"])
        ):
            raise CareFullScaleError("full-scale prediction identity is invalid")
        prediction_point_count += int(prediction["point_count"])
    if (
        prediction_point_count != int(summary["prediction_point_count"])
        or sum(int(item["prediction_point_count"]) for item in prediction_resources)
        != prediction_point_count
    ):
        raise CareFullScaleError("full-scale prediction resource count is invalid")
    if value.get("quality_mask_impact") != _quality_mask_impact_summary(
        training_resources,
        verified_predictions,
    ):
        raise CareFullScaleError("full-scale quality mask impact summary is invalid")
    raw_training_totals = {
        name: sum(counts[name] for counts in raw_training_counts_by_asset.values())
        for name in (
            "status_usable_train_row_count",
            "trusted_train_row_count",
            "retained_disagreement_train_row_count",
            "masked_status_train_row_count",
        )
    }
    if any(training_resources.get(name) != count for name, count in raw_training_totals.items()):
        raise CareFullScaleError("full-scale training status totals differ from raw rows")
    for farm, model_package in loaded_model_packages.items():
        for profile in model_package["fold_profiles"]:
            held_out_asset = str(profile["held_out_asset_id"])
            expected_profile_counts = {
                name: sum(
                    counts[name]
                    for (item_farm, item_asset), counts in raw_training_counts_by_asset.items()
                    if item_farm == farm and item_asset != held_out_asset
                )
                for name in raw_training_totals
            }
            if any(profile.get(name) != count for name, count in expected_profile_counts.items()):
                raise CareFullScaleError(
                    "full-scale fold status counts differ from raw status and signals"
                )
    actual_elapsed = resource_actual.get("elapsed_seconds")
    actual_peak_resident = resource_actual.get("peak_process_resident_bytes")
    if (
        not isinstance(actual_elapsed, int | float)
        or isinstance(actual_elapsed, bool)
        or not math.isfinite(float(actual_elapsed))
        or float(actual_elapsed) <= 0
        or not isinstance(actual_peak_resident, int)
        or isinstance(actual_peak_resident, bool)
        or actual_peak_resident <= 0
    ):
        raise CareFullScaleError("full-scale evaluation resource actual is malformed")
    expected_resource_actual = _evaluate_resource_gate(
        elapsed_seconds=float(actual_elapsed),
        storage_bytes=sum(
            int(reference["size_bytes"])
            for reference in [
                *model_packages.values(),
                *prediction_references.values(),
                prediction_freeze,
                *fold_artifacts,
            ]
        ),
        prediction_count=prediction_point_count,
        peak_batch=max(
            int(training_resources["peak_record_batch_bytes"]),
            max(
                (int(item["peak_record_batch_bytes"]) for item in prediction_resources),
                default=0,
            ),
        ),
        peak_arrow=max(
            int(training_resources["peak_arrow_allocated_bytes"]),
            max(
                (int(item["peak_arrow_allocated_bytes"]) for item in prediction_resources),
                default=0,
            ),
        ),
        peak_resident=actual_peak_resident,
        limits=resource_limits,
    )
    if dict(resource_actual) != expected_resource_actual:
        raise CareFullScaleError("full-scale evaluation resource actual is invalid")
    accounted: set[int] = set()
    freeze_hash = freeze["freeze_sha256"]
    for reference, summary_item in zip(fold_artifacts, fold_summaries, strict=True):
        if not isinstance(reference, Mapping) or not isinstance(summary_item, Mapping):
            raise CareFullScaleError("full-scale fold reference is malformed")
        fold = _load_json_reference(output_root, reference)
        fold_hash = fold.get("document_sha256")
        fold_unsigned = {key: item for key, item in fold.items() if key != "document_sha256"}
        evaluation = fold.get("evaluation")
        farm = str(fold.get("farm", ""))
        held_out_asset = str(fold.get("held_out_asset_id", ""))
        if (
            fold.get("schema_version") != FULL_SCALE_FOLD_SCHEMA_VERSION
            or _canonical_hash(fold_unsigned) != fold_hash
            or fold.get("prediction_freeze_sha256") != freeze_hash
            or fold.get("truth_read_after_prediction_freeze") is not True
            or not isinstance(evaluation, Mapping)
            or evaluation.get("run", {}).get("generalization_protocol")
            != "within-farm-leave-one-turbine-out-v1"
            or farm not in loaded_model_packages
            or fold.get("model_package_sha256")
            != loaded_model_packages[farm]["model_package_sha256"]
            or fold.get("quality_mask_policy") != _quality_mask_policy(features_by_farm[farm])
            or fold.get("fold_profile") != expected_profiles.get((farm, held_out_asset))
        ):
            raise CareFullScaleError("full-scale fold artifact identity is invalid")
        event_ids = {int(item) for item in summary_item.get("event_ids", [])}
        if not event_ids.issubset(verified_prediction_by_event):
            raise CareFullScaleError("full-scale fold prediction mask coverage is incomplete")
        expected_prediction_quality_masks = [
            {
                "event_id": event_id,
                "quality_mask_file_sha256": verified_prediction_by_event[event_id][
                    "quality_mask_reference"
                ]["file_sha256"],
                "quality_mask_range_count": verified_prediction_by_event[event_id][
                    "quality_mask_range_count"
                ],
                "quality_masked_prediction_feature_value_count": verified_prediction_by_event[
                    event_id
                ]["quality_masked_prediction_feature_value_count"],
                "quality_masked_prediction_point_count": verified_prediction_by_event[event_id][
                    "quality_masked_prediction_point_count"
                ],
            }
            for event_id in sorted(event_ids)
        ]
        if fold.get("prediction_quality_masks") != expected_prediction_quality_masks:
            raise CareFullScaleError("full-scale fold prediction mask lineage is invalid")
        if accounted.intersection(event_ids):
            raise CareFullScaleError("full-scale fold event coverage overlaps")
        accounted.update(event_ids)
        _verify_license(fold)
    expected_event_ids = {int(event["event_id"]) for event in import_manifest["events"]}
    if accounted != expected_event_ids:
        raise CareFullScaleError("full-scale fold artifacts do not cover every event")
    cross_farm = value.get("cross_farm_protocol")
    release_gate = value.get("server_release_gate")
    truth_boundary = value.get("truth_boundary")
    operational = value.get("operational_policy")
    if (
        not isinstance(cross_farm, Mapping)
        or cross_farm.get("status") != "disabled"
        or cross_farm.get("human_review_ids") != []
        or not isinstance(release_gate, Mapping)
        or release_gate.get("frontend_or_json_override_allowed") is not False
        or value.get("resource_policy") != resource_limits.to_document()
        or not isinstance(truth_boundary, Mapping)
        or truth_boundary.get("prediction_freeze_completed_before_truth_read") is not True
        or truth_boundary.get("prediction_truth_available_to_training_or_calibration") is not False
        or not isinstance(operational, Mapping)
        or dict(operational) != _operational_policy(resource_limits)
    ):
        raise CareFullScaleError("full-scale release, resource, truth, or ontology gate is invalid")
    _verify_operational_policy(operational)
    _verify_license(value)


async def register_full_scale_evaluation(
    session: AsyncSession,
    evaluation_manifest: Mapping[str, Any],
    import_manifest: Mapping[str, Any],
    *,
    artifact_root: Path,
    subject: str,
    expected_counts: FullScaleExpectedCounts = CARE_V6_FULL_SCALE_COUNTS,
    resource_limits: FullScaleResourceLimits = DEFAULT_FULL_SCALE_RESOURCE_LIMITS,
    trust_anchor: CareTrustAnchor | None = None,
) -> FullScaleEvaluationRegistration:
    """Register three farm models, every held-out fold, and every event outcome."""

    artifact_root = _resolved_artifact_root(artifact_root)
    verify_full_scale_evaluation_manifest(
        evaluation_manifest,
        output_root=artifact_root,
        import_manifest=import_manifest,
        expected_counts=expected_counts,
        resource_limits=resource_limits,
        trust_anchor=trust_anchor,
    )
    created = replayed = 0
    model_ids: list[str] = []
    evaluation_run_ids: list[str] = []
    model_rows: dict[str, Any] = {}
    model_packages: dict[str, Mapping[str, Any]] = {}
    for farm in FULL_SCALE_STAGE_ORDER:
        reference = evaluation_manifest["model_packages"][farm]
        package = _load_json_reference(artifact_root, reference)
        model_id = str(package["model_id"])
        model_ids.append(model_id)
        model, was_replayed = await register_model(
            session,
            ModelRegisterRequest(
                model_id=model_id,
                name=f"CARE {farm} within-farm LOAO z-score",
                version=str(package["model_version"]),
                kind="anomaly",
                description=(
                    "Deterministic CARE v6 within-farm leave-one-asset-out anomaly model; "
                    "prediction truth is excluded from training and threshold calibration."
                ),
                artifact_uri=str(reference["artifact_uri"]),
                artifact_sha256=str(reference["file_sha256"]),
                content_type="application/json",
                input_schema=canonical_anomaly_input_schema(),
                output_schema=canonical_anomaly_output_schema(),
                metrics={
                    "algorithm": package["algorithm"],
                    "evaluation_role": "full-scale-within-farm",
                    "generalization_protocol": package["generalization_protocol"],
                    "dependency_identity": package["dependency_identity"],
                    "feature_set_version": package["feature_set_version"],
                    "quality_rule_version": package["quality_rule_version"],
                    "quality_mask_policy": package["quality_mask_policy"],
                    "quality_mask_lineage_sha256": package["quality_mask_lineage"][
                        "lineage_sha256"
                    ],
                    "model_package_sha256": package["model_package_sha256"],
                    "prediction_truth_used": False,
                    "care_approval": dict(evaluation_manifest["care_approval"]),
                },
            ),
            content_size_bytes=int(reference["size_bytes"]),
            subject=subject,
        )
        created += 0 if was_replayed else 1
        replayed += 1 if was_replayed else 0
        model_rows[farm] = model
        model_packages[farm] = package

    freeze = _load_json_reference(artifact_root, evaluation_manifest["prediction_freeze"])
    prediction_references = freeze["prediction_artifacts"]
    summaries = {
        str(summary["run_id"]): summary for summary in evaluation_manifest["fold_summaries"]
    }
    completed_at = datetime.fromisoformat(FULL_SCALE_PROTOCOL_FROZEN_AT)
    for fold_reference in evaluation_manifest["fold_artifacts"]:
        fold = _load_json_reference(artifact_root, fold_reference)
        evaluation = fold["evaluation"]
        run_document = evaluation["run"]
        run_id = str(run_document["run_id"])
        farm = str(fold["farm"])
        summary = summaries[run_id]
        package = model_packages[farm]
        threshold = package["threshold_policy"]
        evaluation_run_ids.append(run_id)
        input_identity = _canonical_hash(
            {
                "source_import_manifest_sha256": import_manifest["manifest_sha256"],
                "prediction_freeze_sha256": freeze["freeze_sha256"],
                "model_package_sha256": package["model_package_sha256"],
                "farm": farm,
                "held_out_asset_id": fold["held_out_asset_id"],
                "event_ids": run_document["event_ids"],
                "care_approved_root_sha256": evaluation_manifest["care_approval"][
                    "approved_root_sha256"
                ],
            }
        )
        run, was_replayed = await get_or_create_evaluation_run(
            session,
            BenchmarkEvaluationRunCreateRequest(
                evaluation_run_id=run_id,
                dataset_version_id="care-v6",
                model_id=model_rows[farm].id,
                model_version=model_rows[farm].version,
                run_kind="final-holdout",
                protocol_version="within-farm-leave-one-turbine-out-v1",
                farm=cast(Any, farm),
                feature_set_version=str(package["feature_set_version"]),
                quality_rule_version=str(package["quality_rule_version"]),
                threshold_policy_version=str(threshold["version"]),
                threshold_policy_sha256=str(threshold["threshold_policy_sha256"]),
                random_seed=0,
                input_identity_sha256=input_identity,
                requested_event_count=int(summary["requested_event_count"]),
                extension_data={
                    "held_out_asset_id": fold["held_out_asset_id"],
                    "fold_artifact": fold_reference,
                    "model_package": evaluation_manifest["model_packages"][farm],
                    "prediction_freeze_sha256": freeze["freeze_sha256"],
                    "prediction_truth_used": False,
                    "quality_mask_policy": package["quality_mask_policy"],
                    "quality_mask_lineage_sha256": package["quality_mask_lineage"][
                        "lineage_sha256"
                    ],
                    "release_candidate_passed": summary["release_candidate_passed"],
                    "care_approval": dict(evaluation_manifest["care_approval"]),
                },
            ),
            subject=subject,
        )
        created += 0 if was_replayed else 1
        replayed += 1 if was_replayed else 0
        components = evaluation["summary"].get("components", {})
        if not isinstance(components, Mapping):
            components = {}
        for result in evaluation["event_results"]:
            event_id = int(result["event_id"])
            result_status = str(result["status"])
            scored = result_status == "scored"
            prediction = prediction_references.get(str(event_id))
            database_status = (
                "scored" if scored else "unscorable" if result_status == "unscorable" else "failed"
            )
            _, was_replayed = await record_event_result(
                session,
                BenchmarkEventResultCreateRequest(
                    event_result_id=f"{run_id}-e-{event_id}",
                    evaluation_run_id=run.id,
                    event_id=f"care-v6-event-{farm.lower()}-{event_id}",
                    status=cast(Any, database_status),
                    scorable=scored,
                    anomaly_detected=(bool(result["event_detected"]) if scored else None),
                    care_score=(
                        float(summary["care_score"])
                        if scored and summary.get("care_score") is not None
                        else None
                    ),
                    coverage_score=(
                        float(result["coverage_f0_5"])
                        if scored and result.get("coverage_f0_5") is not None
                        else None
                    ),
                    accuracy_score=(
                        float(result["point_accuracy"])
                        if scored and result.get("point_accuracy") is not None
                        else None
                    ),
                    reliability_score=(
                        float(components["reliability_event_f0_5"])
                        if scored and components.get("reliability_event_f0_5") is not None
                        else None
                    ),
                    earliness_score=(
                        float(result["earliness"])
                        if scored and result.get("earliness") is not None
                        else None
                    ),
                    prediction_artifact_uri=(
                        str(prediction["artifact_uri"]) if prediction is not None else None
                    ),
                    prediction_artifact_sha256=(
                        str(prediction["file_sha256"]) if prediction is not None else None
                    ),
                    failure_code=(
                        str(result.get("unscorable_reason") or result.get("failure_reason"))
                        if not scored
                        else None
                    ),
                    result_sha256=str(result["event_result_sha256"]),
                    details={
                        "event_label": result.get("event_label"),
                        "failure_type": result.get("failure_type"),
                        "care_score_scope": "fold-aggregate-or-null-for-single-class-fold",
                        "fold_artifact_uri": fold_reference["artifact_uri"],
                        "fold_artifact_sha256": fold_reference["file_sha256"],
                        "point_confusion": {
                            key: result.get(key) for key in ("tp", "fp", "tn", "fn")
                        },
                    },
                ),
            )
            created += 0 if was_replayed else 1
            replayed += 1 if was_replayed else 0

        metric_values: list[dict[str, Any]] = [
            {
                "name": "scored_event_count",
                "value": float(summary["scored_event_count"]),
                "unit": "events",
                "release": False,
            },
            *[
                {
                    "name": name,
                    "value": float(summary[name]),
                    "unit": "events",
                    "release": True,
                    "threshold": 0.0,
                    "direction": "eq",
                    "passed": int(summary[name]) == 0,
                }
                for name in (
                    "unscorable_event_count",
                    "data_failure_event_count",
                    "model_failure_event_count",
                )
            ],
            {
                "name": "release_candidate_pass",
                "value": float(bool(summary["release_candidate_passed"])),
                "unit": "boolean",
                "release": True,
                "threshold": 1.0,
                "direction": "eq",
                "passed": bool(summary["release_candidate_passed"]),
            },
        ]
        for name in (
            "care_score",
            "normal_event_false_positive_rate",
            "event_detection_rate",
        ):
            if summary.get(name) is not None:
                metric_values.append(
                    {
                        "name": name,
                        "value": float(summary[name]),
                        "unit": "ratio",
                        "release": name == "care_score",
                        "threshold": 0.5 if name == "care_score" else None,
                        "direction": "gte" if name == "care_score" else None,
                        "passed": (float(summary[name]) >= 0.5 if name == "care_score" else None),
                    }
                )
        for metric_index, metric in enumerate(metric_values):
            _, was_replayed = await record_metric_snapshot(
                session,
                BenchmarkMetricSnapshotCreateRequest(
                    metric_snapshot_id=f"{run_id}-m-{metric_index:02d}",
                    evaluation_run_id=run.id,
                    metric_name=str(metric["name"]),
                    protocol_version=SCORE_PROTOCOL_VERSION,
                    metric_version="care-v6-full-scale-fold-v1",
                    value=float(metric["value"]),
                    unit=str(metric["unit"]),
                    is_release_metric=bool(metric["release"]),
                    threshold_value=metric.get("threshold"),
                    threshold_direction=cast(Any, metric.get("direction")),
                    passed=metric.get("passed"),
                    details={
                        "fold_artifact_sha256": fold_reference["file_sha256"],
                        "held_out_asset_id": fold["held_out_asset_id"],
                    },
                ),
            )
            created += 0 if was_replayed else 1
            replayed += 1 if was_replayed else 0
        await complete_evaluation_run(
            session,
            evaluation_run_id=run.id,
            artifact_uri=str(fold_reference["artifact_uri"]),
            artifact_sha256=str(fold_reference["file_sha256"]),
            completed_at=completed_at,
            subject=subject,
        )
    return FullScaleEvaluationRegistration(
        created,
        replayed,
        tuple(model_ids),
        tuple(evaluation_run_ids),
    )


def resource_prediction_count() -> int:
    """Frozen CARE v6 prediction split count used by release verification."""

    return 281_249


def _read_json(path: Path) -> Mapping[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise CareFullScaleError(f"JSON root must be an object: {path}")
    return raw


async def _register_from_settings(args: argparse.Namespace) -> dict[str, Any]:
    if args.use_care_worker_runtime:
        care_settings = get_care_worker_settings()
        engine = create_async_engine(
            care_settings.database_url.get_secret_value(),
            pool_pre_ping=True,
        )
    else:
        settings = get_settings()
        engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        source_manifest = _read_json(args.source_manifest)
        quality_contract = _read_json(args.quality_contract)
        import_manifest = _read_json(args.import_manifest)
        evaluation_manifest = _read_json(args.evaluation_manifest)
        async with session_factory() as session, session.begin():
            imported = await register_full_scale_import(
                session,
                import_manifest,
                source_manifest,
                quality_contract,
                artifact_root=args.artifact_root,
                tenant_id=args.tenant_id,
                subject=args.subject,
            )
            evaluated = await register_full_scale_evaluation(
                session,
                evaluation_manifest,
                import_manifest,
                artifact_root=args.artifact_root,
                subject=args.subject,
            )
        return {
            "import_created_count": imported.created_count,
            "import_replayed_count": imported.replayed_count,
            "evaluation_created_count": evaluated.created_count,
            "evaluation_replayed_count": evaluated.replayed_count,
            "dataset_version_id": imported.dataset_version_id,
            "event_database_ids": list(imported.event_ids),
            "model_ids": list(evaluated.model_ids),
            "evaluation_run_ids": list(evaluated.evaluation_run_ids),
        }
    finally:
        await engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded CARE v6 full-scale import/evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    import_parser = subparsers.add_parser("import", help="build A -> C -> B full artifacts")
    import_parser.add_argument("--manifest", type=Path, required=True)
    import_parser.add_argument("--quality-contract", type=Path, required=True)
    import_parser.add_argument("--dataset-root", type=Path, required=True)
    import_parser.add_argument("--output-root", type=Path, required=True)
    import_parser.add_argument("--archive", type=Path)
    import_store = import_parser.add_mutually_exclusive_group()
    import_store.add_argument("--object-store-root", type=Path)
    import_store.add_argument("--use-configured-minio", action="store_true")
    import_store.add_argument("--use-care-worker-runtime", action="store_true")
    import_parser.add_argument("--job-id", default="care-v6-full-import")
    import_parser.add_argument("--state-path", type=Path)
    evaluate_parser = subparsers.add_parser("evaluate", help="run within-farm LOAO evaluation")
    evaluate_parser.add_argument("--import-manifest", type=Path, required=True)
    evaluate_parser.add_argument("--output-root", type=Path, required=True)
    evaluation_store = evaluate_parser.add_mutually_exclusive_group()
    evaluation_store.add_argument("--object-store-root", type=Path)
    evaluation_store.add_argument("--use-configured-minio", action="store_true")
    evaluation_store.add_argument("--use-care-worker-runtime", action="store_true")
    evaluate_parser.add_argument("--job-id", default="care-v6-full-evaluation")
    evaluate_parser.add_argument("--state-path", type=Path)
    register_parser = subparsers.add_parser(
        "register", help="atomically register verified import and evaluation manifests"
    )
    register_parser.add_argument("--source-manifest", type=Path, required=True)
    register_parser.add_argument("--quality-contract", type=Path, required=True)
    register_parser.add_argument("--import-manifest", type=Path, required=True)
    register_parser.add_argument("--evaluation-manifest", type=Path, required=True)
    register_parser.add_argument("--artifact-root", type=Path, required=True)
    register_parser.add_argument("--tenant-id", default="tenant-east-china")
    register_parser.add_argument("--subject", default="care-full-scale-worker")
    register_parser.add_argument("--use-care-worker-runtime", action="store_true")
    status_parser = subparsers.add_parser("status", help="verify and print a job state")
    status_parser.add_argument("--state-path", type=Path, required=True)
    cancel_parser = subparsers.add_parser(
        "cancel", help="request cancellation at the next durable event boundary"
    )
    cancel_parser.add_argument("--state-path", type=Path, required=True)
    return parser


def _artifact_store_from_args(args: argparse.Namespace) -> ImmutableArtifactStore | None:
    if args.use_care_worker_runtime:
        care_settings = get_care_worker_settings()
        return MinioImmutableArtifactStore(
            care_minio_client(care_settings),
            care_settings.minio_bucket,
        )
    if args.use_configured_minio:
        settings = get_settings()
        return MinioImmutableArtifactStore(
            minio_client(settings),
            settings.minio_care_bucket,
        )
    return (
        LocalImmutableArtifactStore(args.object_store_root)
        if args.object_store_root is not None
        else None
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in {"status", "cancel"}:
        control = FileBenchmarkJobControl(args.state_path)
        state = control.request_cancel() if args.command == "cancel" else control.read()
        print(json.dumps(state.to_document(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "register":
        print(
            json.dumps(
                asyncio.run(_register_from_settings(args)),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    store = _artifact_store_from_args(args)
    result: FullScaleImportResult | FullScaleEvaluationResult
    if args.command == "import":
        result = build_full_scale_import(
            _read_json(args.manifest),
            _read_json(args.quality_contract),
            args.dataset_root,
            args.output_root,
            source_archive_path=args.archive,
            artifact_store=store,
            job_id=args.job_id,
            state_path=args.state_path,
        )
    else:
        result = build_full_scale_evaluation(
            _read_json(args.import_manifest),
            args.output_root,
            artifact_store=store,
            job_id=args.job_id,
            state_path=args.state_path,
        )
    print(
        json.dumps(
            {
                "manifest_path": str(result.manifest_path),
                "manifest_file_sha256": result.manifest_file_sha256,
                "replayed": result.replayed,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
