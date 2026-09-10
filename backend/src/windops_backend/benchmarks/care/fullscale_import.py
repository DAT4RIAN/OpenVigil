from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

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
    convert_care_csv_to_parquet,
)
from windops_backend.benchmarks.care.quality import (
    audit_event_quality,
    verify_quality_contract,
)
from windops_backend.benchmarks.care.resources import (
    peak_process_resident_bytes,
    trim_process_resident_memory,
)
from windops_backend.benchmarks.care.trust import (
    CareTrustAnchor,
    verify_care_approval_lineage,
    verify_care_source_rebuild,
)
from windops_backend.schemas import (
    BenchmarkDatasetVersionCreateRequest,
    BenchmarkEventCreateRequest,
    BenchmarkFeatureMapCreateRequest,
    BenchmarkFileCreateRequest,
    BenchmarkQualityReportCreateRequest,
)
from windops_backend.services.benchmark_metadata import (
    register_benchmark_event,
    register_benchmark_file,
    register_dataset_version,
    register_feature_map,
    register_quality_report,
)

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
