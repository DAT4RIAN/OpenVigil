from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import tracemalloc
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import uuid4

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
    verify_care_contract,
)
from windops_backend.benchmarks.care.licensing import (
    CARE_CREATOR_AFFILIATION,
    CARE_DATASET_CREATORS,
    CARE_RECOMMENDED_CITATION,
    build_care_artifact_license,
    verify_care_artifact_license,
)
from windops_backend.benchmarks.care.pipeline import (
    PIPELINE_CONTRACT_VERSION,
    CareObjectStorageLayout,
    CarePipelineError,
    ImmutableArtifactStore,
    LocalImmutableArtifactStore,
    convert_care_csv_to_parquet,
)
from windops_backend.benchmarks.care.quality import (
    FEATURE_SET_VERSION,
    QUALITY_RULE_VERSION,
    audit_event_quality,
    verify_quality_contract,
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

MINIMAL_IMPORT_SCHEMA_VERSION = "care-v6-a-minimal-import-v1"
MINIMAL_EVENT_IDS = (0, 24)
MINIMAL_FARM = "A"
EXPECTED_MAPPING_COUNT = 81
EXPECTED_MODEL_INPUT_COUNT = 54
TRUTH_ACCESS_SCOPE = "benchmark-evaluation-truth"
IMPORT_BUNDLE_URI = "care://v6/reports/a-minimal-import/manifest.json"
SOURCE_CONTRACT_URI = "care://v6/reports/source-contract/manifest.json"

_TRUTH_FIELD_NAMES = frozenset(
    {
        "event_label",
        "event_start",
        "event_end",
        "event_start_id",
        "event_end_id",
        "event_description",
    }
)


class CareMinimalImportError(CarePipelineError):
    """Raised when the A-farm minimal import fails a closed contract boundary."""


@dataclass(frozen=True, slots=True)
class MinimalImportResult:
    manifest_path: Path
    manifest: Mapping[str, Any]
    manifest_file_sha256: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class MinimalImportRegistration:
    created_count: int
    replayed_count: int
    dataset_version_id: str
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ImportContract:
    events: tuple[Mapping[str, Any], ...]
    mappings: tuple[Mapping[str, Any], ...]
    semantics: tuple[Mapping[str, Any], ...]
    selected_columns: tuple[str, ...]
    model_input_columns: tuple[str, ...]
    source_dataset_sha256: str


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: Path, *, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_archive(path: Path) -> dict[str, int | str]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    size_bytes = 0
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            size_bytes += len(chunk)
            sha256.update(chunk)
            md5.update(chunk)
    return {
        "size_bytes": size_bytes,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _json_document_bytes(payload: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    document = {**payload, "document_sha256": _canonical_hash(payload)}
    content = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    return document, content


def _write_immutable_bytes(path: Path, content: bytes) -> bool:
    """Write once; return True when identical content already existed."""

    if path.exists():
        if not path.is_file() or path.read_bytes() != content:
            raise CareMinimalImportError(f"immutable artifact conflicts with existing path: {path}")
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise CareMinimalImportError(
                    f"immutable artifact concurrently received different content: {path}"
                ) from None
    finally:
        temporary.unlink(missing_ok=True)
    return False


def _relative_path(root: Path, path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise CareMinimalImportError("derived artifact escaped the configured output root")
    return str(resolved.relative_to(root)).replace("\\", "/")


def _artifact_reference(
    *,
    output_root: Path,
    path: Path,
    artifact_uri: str,
    file_sha256: str,
    document_sha256: str | None = None,
) -> dict[str, Any]:
    reference: dict[str, Any] = {
        "local_relative_path": _relative_path(output_root, path),
        "artifact_uri": artifact_uri,
        "file_sha256": file_sha256,
        "size_bytes": path.stat().st_size,
    }
    if document_sha256 is not None:
        reference["document_sha256"] = document_sha256
    return reference


def _publish_json(
    *,
    output_root: Path,
    local_path: Path,
    payload: Mapping[str, Any],
    object_key_prefix: str,
    artifact_store: ImmutableArtifactStore | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    document, content = _json_document_bytes(payload)
    _write_immutable_bytes(local_path, content)
    file_sha256 = hashlib.sha256(content).hexdigest()
    object_key = f"{object_key_prefix}.sha256-{file_sha256}.json"
    artifact_uri = (
        artifact_store.put_immutable(
            object_key,
            local_path,
            file_sha256,
            content_type="application/json",
        )
        if artifact_store is not None
        else local_path.resolve().as_uri()
    )
    return document, _artifact_reference(
        output_root=output_root,
        path=local_path,
        artifact_uri=artifact_uri,
        file_sha256=file_sha256,
        document_sha256=str(document["document_sha256"]),
    )


def _license(
    contract: _ImportContract,
    *,
    artifact_type: str,
    changes_made: str,
    source_artifact_sha256: str,
) -> dict[str, Any]:
    return build_care_artifact_license(
        artifact_type=artifact_type,
        changes_made=changes_made,
        source_dataset_sha256=contract.source_dataset_sha256,
        source_artifact_sha256=source_artifact_sha256,
        transformation_versions={
            "column_mapping": COLUMN_MAPPING_VERSION,
            "feature_set": FEATURE_SET_VERSION,
            "minimal_import": MINIMAL_IMPORT_SCHEMA_VERSION,
            "pipeline": PIPELINE_CONTRACT_VERSION,
            "quality_rules": QUALITY_RULE_VERSION,
        },
    )


def _validate_control_inputs(
    manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
) -> _ImportContract:
    verify_care_contract(manifest)
    verify_quality_contract(quality_contract)
    if quality_contract.get("source_manifest_sha256") != manifest["manifest_sha256"]:
        raise CareMinimalImportError("quality contract does not belong to the source manifest")
    if (
        manifest.get("dataset_id") != DATASET_ID
        or manifest.get("dataset_version") != DATASET_VERSION
    ):
        raise CareMinimalImportError("minimal importer only accepts CARE v6")
    source = manifest.get("source")
    license_metadata = manifest.get("license")
    if not isinstance(source, Mapping) or not isinstance(license_metadata, Mapping):
        raise CareMinimalImportError("source manifest provenance is incomplete")
    zip_record = source.get("zip")
    if (
        not isinstance(zip_record, Mapping)
        or not _is_sha256(zip_record.get("sha256"))
        or source.get("doi") != DOI
        or source.get("zenodo_url") != ZENODO_URL
        or source.get("read_only") is not True
        or license_metadata.get("name") != LICENSE_NAME
        or license_metadata.get("url") != LICENSE_URL
    ):
        raise CareMinimalImportError(
            "source manifest license or immutable archive identity is invalid"
        )

    events = tuple(
        event
        for event in manifest.get("events", [])
        if event.get("farm") == MINIMAL_FARM and int(event.get("event_id", -1)) in MINIMAL_EVENT_IDS
    )
    if tuple(int(event["event_id"]) for event in events) != MINIMAL_EVENT_IDS:
        raise CareMinimalImportError("source manifest must contain ordered A events 0 and 24")
    if {str(event.get("event_label")) for event in events} != {"anomaly", "normal"}:
        raise CareMinimalImportError("minimal events must contain one anomaly and one normal truth")
    if len({str(event.get("source_asset_id")) for event in events}) != 1:
        raise CareMinimalImportError("minimal events must use the same logical source asset")

    farm_rows = [item for item in manifest.get("farms", []) if item.get("farm") == MINIMAL_FARM]
    quality_farms = [
        item for item in quality_contract.get("farms", []) if item.get("farm") == MINIMAL_FARM
    ]
    if len(farm_rows) != 1 or len(quality_farms) != 1:
        raise CareMinimalImportError("A-farm mapping or quality semantics are missing")
    mappings = tuple(farm_rows[0].get("column_mappings", []))
    semantics = tuple(quality_farms[0].get("features", []))
    if len(mappings) != EXPECTED_MAPPING_COUNT or len(semantics) != EXPECTED_MAPPING_COUNT:
        raise CareMinimalImportError("A-farm minimal import requires all 81 mapped signals")
    mapping_columns = tuple(str(item.get("source_column", "")) for item in mappings)
    semantic_columns = tuple(str(item.get("source_column", "")) for item in semantics)
    if mapping_columns != semantic_columns or len(set(mapping_columns)) != EXPECTED_MAPPING_COUNT:
        raise CareMinimalImportError("A-farm mapping and quality semantics are not one-to-one")
    model_inputs = tuple(
        str(item["source_column"]) for item in semantics if item.get("enabled_by_default") is True
    )
    if (
        len(model_inputs) != EXPECTED_MODEL_INPUT_COUNT
        or any(
            item.get("statistic") != "average"
            for item in semantics
            if item.get("enabled_by_default")
        )
        or any(column in _TRUTH_FIELD_NAMES for column in model_inputs)
    ):
        raise CareMinimalImportError(
            "A-farm model inputs must be exactly the 54 approved Avg signals"
        )
    selected = (*METADATA_COLUMNS, *model_inputs)
    return _ImportContract(
        events,
        mappings,
        semantics,
        selected,
        model_inputs,
        str(zip_record["sha256"]),
    )


def _verify_archive(source_archive_path: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    expected = manifest["source"]["zip"]
    actual = _hash_archive(source_archive_path.resolve(strict=True))
    if (
        actual["size_bytes"] != int(expected["size_bytes"])
        or actual["md5"] != expected["md5"]
        or actual["sha256"] != expected["sha256"]
    ):
        raise CareMinimalImportError("source archive differs from the immutable CARE manifest")
    return actual


def _verify_embedded_license(value: Mapping[str, Any]) -> None:
    license_metadata = value.get("license")
    if not isinstance(license_metadata, Mapping):
        raise CareMinimalImportError("derived JSON artifact is missing license metadata")
    versions = license_metadata.get("transformation_versions")
    if not isinstance(versions, Mapping):
        raise CareMinimalImportError("derived JSON artifact transformation versions are invalid")
    try:
        verify_care_artifact_license(
            license_metadata,
            artifact_type=str(license_metadata["artifact_type"]),
            source_dataset_sha256=str(license_metadata["source_dataset_sha256"]),
            source_artifact_sha256=str(license_metadata["source_artifact_sha256"]),
            transformation_versions={str(key): str(item) for key, item in versions.items()},
        )
    except (KeyError, ValueError) as exc:
        raise CareMinimalImportError("derived JSON artifact license is invalid") from exc


def verify_minimal_import_manifest(value: Mapping[str, Any]) -> None:
    actual = value.get("manifest_sha256")
    unsigned = {key: item for key, item in value.items() if key != "manifest_sha256"}
    if not _is_sha256(actual) or _canonical_hash(unsigned) != actual:
        raise CareMinimalImportError("minimal import manifest hash is invalid")
    events = value.get("events")
    model_inputs = value.get("model_input_columns")
    if (
        value.get("schema_version") != MINIMAL_IMPORT_SCHEMA_VERSION
        or value.get("dataset_id") != DATASET_ID
        or value.get("dataset_version") != DATASET_VERSION
        or value.get("farm") != MINIMAL_FARM
        or value.get("event_ids") != list(MINIMAL_EVENT_IDS)
        or value.get("mapping_count") != EXPECTED_MAPPING_COUNT
        or value.get("model_input_count") != EXPECTED_MODEL_INPUT_COUNT
        or not isinstance(model_inputs, list)
        or len(model_inputs) != EXPECTED_MODEL_INPUT_COUNT
        or len(set(model_inputs)) != EXPECTED_MODEL_INPUT_COUNT
        or any(column in _TRUTH_FIELD_NAMES for column in model_inputs)
        or not isinstance(events, list)
        or [event.get("event_id") for event in events] != list(MINIMAL_EVENT_IDS)
        or value.get("raw_source_unchanged") is not True
    ):
        raise CareMinimalImportError("minimal import manifest semantics are invalid")
    forbidden = set(_TRUTH_FIELD_NAMES)
    for event in events:
        if forbidden.intersection(event):
            raise CareMinimalImportError("event truth leaked into the truth-free import manifest")
        truth = event.get("restricted_truth")
        if not isinstance(truth, Mapping) or truth.get("access_scope") != TRUTH_ACCESS_SCOPE:
            raise CareMinimalImportError("event truth reference is not access-isolated")
    _verify_embedded_license(value)


def _verify_reference(output_root: Path, reference: Mapping[str, Any]) -> None:
    relative = reference.get("local_relative_path")
    if (
        not isinstance(relative, str)
        or PurePosixPath(relative).is_absolute()
        or ".." in PurePosixPath(relative).parts
    ):
        raise CareMinimalImportError("derived artifact reference path is unsafe")
    path = (output_root / Path(*PurePosixPath(relative).parts)).resolve()
    if not path.is_relative_to(output_root) or not path.is_file():
        raise CareMinimalImportError("derived artifact reference is missing")
    if _sha256_file(path) != reference.get("file_sha256") or path.stat().st_size != int(
        reference.get("size_bytes", -1)
    ):
        raise CareMinimalImportError("derived artifact reference content changed")


def _verify_existing_bundle(
    *,
    manifest_path: Path,
    output_root: Path,
    source_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    contract: _ImportContract,
    dataset_root: Path,
    source_archive_path: Path | None,
) -> MinimalImportResult:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise CareMinimalImportError("minimal import manifest root must be an object")
    verify_minimal_import_manifest(raw)
    if (
        raw.get("source_manifest_sha256") != source_manifest["manifest_sha256"]
        or raw.get("quality_contract_sha256") != quality_contract["quality_contract_sha256"]
        or tuple(raw.get("model_input_columns", [])) != contract.model_input_columns
    ):
        raise CareMinimalImportError("existing minimal import belongs to another control contract")
    _verify_reference(output_root, raw["mapping_artifact"])
    for event_summary, source_event in zip(raw["events"], contract.events, strict=True):
        source_path = (dataset_root / str(source_event["relative_path"])).resolve(strict=True)
        if (
            not source_path.is_relative_to(dataset_root)
            or _sha256_file(source_path) != source_event["file_sha256"]
        ):
            raise CareMinimalImportError("source event changed after the minimal import")
        _verify_reference(output_root, event_summary["parquet"]["data"])
        _verify_reference(output_root, event_summary["parquet"]["manifest"])
        _verify_reference(output_root, event_summary["quality"]["report"])
        _verify_reference(output_root, event_summary["quality"]["mask"])
        _verify_reference(output_root, event_summary["restricted_truth"]["artifact"])
    if source_archive_path is not None:
        _verify_archive(source_archive_path, source_manifest)
    return MinimalImportResult(
        manifest_path,
        raw,
        _sha256_file(manifest_path),
        True,
    )


def _audit_with_resources(
    source_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    dataset_root: Path,
    event_id: int,
) -> tuple[dict[str, Any], dict[str, int | float]]:
    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()
    baseline_current, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    started = time.perf_counter()
    try:
        report = audit_event_quality(source_manifest, quality_contract, dataset_root, event_id)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        if not was_tracing:
            tracemalloc.stop()
    resources: dict[str, int | float] = {
        "elapsed_seconds": elapsed,
        "peak_python_traced_bytes": max(0, peak - baseline_current),
        "rows_per_second": float(report["row_count"]) / elapsed if elapsed > 0 else 0.0,
    }
    return report, resources


def _source_file_record(manifest: Mapping[str, Any], relative_path: str) -> Mapping[str, Any]:
    matches = [
        item for item in manifest.get("csv_files", []) if item.get("relative_path") == relative_path
    ]
    if len(matches) != 1:
        raise CareMinimalImportError(f"source file inventory is missing {relative_path}")
    if not isinstance(matches[0], Mapping):
        raise CareMinimalImportError(f"source file inventory is malformed for {relative_path}")
    return cast(Mapping[str, Any], matches[0])


def build_a_minimal_import(
    source_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    dataset_root: Path,
    output_root: Path,
    *,
    source_archive_path: Path | None = None,
    artifact_store: ImmutableArtifactStore | None = None,
    stop_after_chunks_by_event: Mapping[int, int] | None = None,
) -> MinimalImportResult:
    """Build the immutable A0/A24 bundle without exposing event truth to model inputs."""

    contract = _validate_control_inputs(source_manifest, quality_contract)
    dataset_root = dataset_root.resolve(strict=True)
    output_root = output_root.resolve()
    if output_root == dataset_root or output_root.is_relative_to(dataset_root):
        raise CareMinimalImportError("minimal import output must be outside the read-only dataset")
    if source_archive_path is not None:
        source_archive_path = source_archive_path.resolve(strict=True)
        if output_root == source_archive_path or output_root.is_relative_to(source_archive_path):
            raise CareMinimalImportError("minimal import output must be outside the source archive")
    manifest_path = (
        output_root
        / DATASET_ID
        / DATASET_VERSION
        / "reports"
        / "a-minimal-import"
        / "manifest.json"
    )
    if manifest_path.exists():
        return _verify_existing_bundle(
            manifest_path=manifest_path,
            output_root=output_root,
            source_manifest=source_manifest,
            quality_contract=quality_contract,
            contract=contract,
            dataset_root=dataset_root,
            source_archive_path=source_archive_path,
        )

    archive_before = (
        _verify_archive(source_archive_path, source_manifest)
        if source_archive_path is not None
        else None
    )
    layout = CareObjectStorageLayout()
    semantic_by_column = {str(item["source_column"]): item for item in contract.semantics}
    mapping_payload: dict[str, Any] = {
        "schema_version": "care-v6-column-mapping-artifact-v1",
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "farm": MINIMAL_FARM,
        "mapping_version": COLUMN_MAPPING_VERSION,
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "mapping_count": len(contract.mappings),
        "approved_model_input_count": len(contract.model_input_columns),
        "approved_model_input_columns": list(contract.model_input_columns),
        "mappings": [
            {
                **dict(mapping),
                "quality_semantics": dict(semantic_by_column[str(mapping["source_column"])]),
            }
            for mapping in contract.mappings
        ],
        "license": _license(
            contract,
            artifact_type="column-mapping",
            changes_made=(
                "Combined the immutable source column map with normalized unit, quality, and "
                "default-enabled semantics; no source values were copied or modified."
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
            / "farm=A"
            / "column-mapping.json"
        ),
        payload=mapping_payload,
        object_key_prefix=f"{layout.quality_prefix}/mappings/farm=A/column-mapping",
        artifact_store=artifact_store,
    )

    event_summaries: list[dict[str, Any]] = []
    total_rows = 0
    total_elapsed = 0.0
    peak_memory = 0
    for event in contract.events:
        event_id = int(event["event_id"])
        source_path = (dataset_root / str(event["relative_path"])).resolve(strict=True)
        if not source_path.is_relative_to(dataset_root):
            raise CareMinimalImportError("event path escaped the read-only dataset root")
        source_before = _sha256_file(source_path)
        if source_before != event["file_sha256"]:
            raise CareMinimalImportError(f"event {event_id} differs from the source manifest")
        parquet = convert_care_csv_to_parquet(
            source_path,
            output_root,
            job_id=f"care-v6-a-event-{event_id}-import",
            farm=MINIMAL_FARM,
            event_id=event_id,
            artifact_store=artifact_store,
            object_layout=layout,
            expected_source_sha256=source_before,
            source_dataset_sha256=contract.source_dataset_sha256,
            stop_after_chunks=(stop_after_chunks_by_event or {}).get(event_id),
            selected_columns=contract.selected_columns,
            model_input_columns=contract.model_input_columns,
        )
        parquet_manifest = json.loads(parquet.manifest_path.read_text(encoding="utf-8"))
        if (
            parquet.row_count != int(event["row_count"])
            or tuple(parquet_manifest["columns"]) != contract.selected_columns
            or tuple(parquet_manifest["model_input_columns"]) != contract.model_input_columns
        ):
            raise CareMinimalImportError(f"event {event_id} Parquet identity is inconsistent")

        audit, quality_resources = _audit_with_resources(
            source_manifest,
            quality_contract,
            dataset_root,
            event_id,
        )
        if (
            int(audit["row_count"]) != int(event["row_count"])
            or audit["split_counts"] != event["split_counts"]
            or len(audit["feature_summaries"]) != EXPECTED_MAPPING_COUNT
        ):
            raise CareMinimalImportError(f"event {event_id} quality audit identity is inconsistent")
        event_dir = (
            output_root / DATASET_ID / DATASET_VERSION / "quality" / "farm=A" / f"event={event_id}"
        )
        source_quality_hash = str(audit["quality_report_sha256"])
        mask_payload: dict[str, Any] = {
            "schema_version": "care-v6-quality-mask-artifact-v1",
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "farm": MINIMAL_FARM,
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
                    "Extracted sparse quality findings into a separate mask; source values "
                    "remain unchanged in the standard artifact."
                ),
                source_artifact_sha256=source_before,
            ),
        }
        _, mask_reference = _publish_json(
            output_root=output_root,
            local_path=event_dir / "quality-mask.json",
            payload=mask_payload,
            object_key_prefix=(f"{layout.quality_prefix}/farm=A/event={event_id}/quality-mask"),
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
                        "Computed deterministic feature and event quality summaries and moved "
                        "sparse mask ranges to a separately licensed artifact."
                    ),
                    source_artifact_sha256=source_before,
                ),
            }
        )
        _, report_reference = _publish_json(
            output_root=output_root,
            local_path=event_dir / "quality-report.json",
            payload=report_payload,
            object_key_prefix=(f"{layout.quality_prefix}/farm=A/event={event_id}/quality-report"),
            artifact_store=artifact_store,
        )
        truth_payload: dict[str, Any] = {
            "schema_version": "care-v6-restricted-event-truth-v1",
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "farm": MINIMAL_FARM,
            "event_id": event_id,
            "access_scope": TRUTH_ACCESS_SCOPE,
            "model_input_allowed": False,
            "event_label": event["event_label"],
            "event_start": event["event_start"],
            "event_end": event["event_end"],
            "event_start_id": event["event_start_id"],
            "event_end_id": event["event_end_id"],
            "event_description": event["event_description"],
            "source_event_file_sha256": source_before,
            "license": _license(
                contract,
                artifact_type="restricted-evaluation-truth",
                changes_made=(
                    "Copied event truth metadata into an evaluation-only artifact separated "
                    "from standard Parquet and model-input manifests."
                ),
                source_artifact_sha256=source_before,
            ),
        }
        _, truth_reference = _publish_json(
            output_root=output_root,
            local_path=event_dir / "restricted-truth.json",
            payload=truth_payload,
            object_key_prefix=(
                f"{layout.quality_prefix}/restricted-truth/farm=A/event={event_id}/truth"
            ),
            artifact_store=artifact_store,
        )
        source_after = _sha256_file(source_path)
        if source_after != source_before:
            raise CareMinimalImportError(f"event {event_id} source changed during import")
        source_file = _source_file_record(source_manifest, str(event["relative_path"]))
        parquet_manifest_hash = _sha256_file(parquet.manifest_path)
        parquet_reference = {
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
            "column_count": len(contract.selected_columns),
        }
        event_summaries.append(
            {
                "event_id": event_id,
                "source_asset_id": event["source_asset_id"],
                "source_relative_path": event["relative_path"],
                "source_size_bytes": source_file["size_bytes"],
                "source_file_sha256": source_before,
                "source_schema_sha256": event["schema_sha256"],
                "row_count": event["row_count"],
                "source_row_id_min": event["source_row_id_min"],
                "source_row_id_max": event["source_row_id_max"],
                "split_counts": event["split_counts"],
                "parquet": parquet_reference,
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
            }
        )
        total_rows += parquet.row_count
        total_elapsed += parquet.elapsed_seconds + float(quality_resources["elapsed_seconds"])
        peak_memory = max(
            peak_memory,
            parquet.peak_record_batch_bytes,
            parquet.peak_arrow_allocated_bytes,
            int(quality_resources["peak_python_traced_bytes"]),
        )

    archive_after = (
        _verify_archive(source_archive_path, source_manifest)
        if source_archive_path is not None
        else None
    )
    if archive_before != archive_after:
        raise CareMinimalImportError("source archive changed during minimal import")
    identity_payload = {
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "quality_contract_sha256": quality_contract["quality_contract_sha256"],
        "event_ids": list(MINIMAL_EVENT_IDS),
        "mapping_artifact_sha256": mapping_reference["file_sha256"],
        "model_input_columns": list(contract.model_input_columns),
        "events": [
            {
                "event_id": event["event_id"],
                "source_file_sha256": event["source_file_sha256"],
                "parquet_sha256": event["parquet"]["data"]["file_sha256"],
                "quality_report_sha256": event["quality"]["report"]["file_sha256"],
                "quality_mask_sha256": event["quality"]["mask"]["file_sha256"],
                "restricted_truth_sha256": event["restricted_truth"]["artifact"]["file_sha256"],
            }
            for event in event_summaries
        ],
    }
    import_identity = _canonical_hash(identity_payload)
    payload: dict[str, Any] = {
        "schema_version": MINIMAL_IMPORT_SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "farm": MINIMAL_FARM,
        "event_ids": list(MINIMAL_EVENT_IDS),
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "source_dataset_sha256": contract.source_dataset_sha256,
        "quality_contract_sha256": quality_contract["quality_contract_sha256"],
        "mapping_version": COLUMN_MAPPING_VERSION,
        "mapping_count": EXPECTED_MAPPING_COUNT,
        "mapping_artifact": mapping_reference,
        "feature_set_version": FEATURE_SET_VERSION,
        "quality_rule_version": QUALITY_RULE_VERSION,
        "model_input_count": EXPECTED_MODEL_INPUT_COUNT,
        "model_input_columns": list(contract.model_input_columns),
        "metadata_columns": list(METADATA_COLUMNS),
        "truth_fields_forbidden_from_model_input": sorted(_TRUTH_FIELD_NAMES),
        "truth_access_scope": TRUTH_ACCESS_SCOPE,
        "events": event_summaries,
        "summary": {
            "event_count": len(event_summaries),
            "row_count": total_rows,
            "train_row_count": sum(
                int(event["split_counts"]["train"]) for event in event_summaries
            ),
            "prediction_row_count": sum(
                int(event["split_counts"]["prediction"]) for event in event_summaries
            ),
            "elapsed_seconds": total_elapsed,
            "rows_per_second": total_rows / total_elapsed if total_elapsed > 0 else 0.0,
            "peak_measured_bytes": peak_memory,
        },
        "source_archive_verification": archive_after,
        "raw_source_unchanged": True,
        "immutable_registration_identity": import_identity,
        "bundle_uri": IMPORT_BUNDLE_URI,
        "license": _license(
            contract,
            artifact_type="minimal-import-manifest",
            changes_made=(
                "Selected A-farm events 0 and 24, projected approved Avg features, generated "
                "wide Parquet and separate quality/truth artifacts; source files were unchanged."
            ),
            source_artifact_sha256=str(source_manifest["manifest_sha256"]),
        ),
    }
    manifest = {**payload, "manifest_sha256": _canonical_hash(payload)}
    manifest_content = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_immutable_bytes(manifest_path, manifest_content)
    verify_minimal_import_manifest(manifest)
    if any(
        not math.isfinite(float(value))
        for value in payload["summary"].values()
        if isinstance(value, float)
    ):
        raise CareMinimalImportError("minimal import resource telemetry is non-finite")
    return MinimalImportResult(
        manifest_path,
        manifest,
        hashlib.sha256(manifest_content).hexdigest(),
        False,
    )


async def register_a_minimal_import(
    session: AsyncSession,
    import_manifest: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    *,
    tenant_id: str,
    subject: str,
) -> MinimalImportRegistration:
    """Register the immutable bundle in the caller's transaction, without committing it."""

    contract = _validate_control_inputs(source_manifest, quality_contract)
    verify_minimal_import_manifest(import_manifest)
    if (
        import_manifest.get("source_manifest_sha256") != source_manifest["manifest_sha256"]
        or import_manifest.get("quality_contract_sha256")
        != quality_contract["quality_contract_sha256"]
        or tuple(import_manifest.get("model_input_columns", [])) != contract.model_input_columns
    ):
        raise CareMinimalImportError("minimal import registration controls do not match")
    dataset_version_id = "care-v6"
    license_metadata = import_manifest["license"]
    source_zip = source_manifest["source"]["zip"]
    dataset, dataset_replayed = await register_dataset_version(
        session,
        BenchmarkDatasetVersionCreateRequest(
            dataset_version_id=dataset_version_id,
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
            },
        ),
        subject=subject,
    )
    created = 0 if dataset_replayed else 1
    replayed = 1 if dataset_replayed else 0
    event_database_ids: list[str] = []
    import_events = {int(event["event_id"]): event for event in import_manifest["events"]}
    for source_event in contract.events:
        event_number = int(source_event["event_id"])
        imported = import_events[event_number]
        file_id = f"care-v6-file-a-{event_number}"
        _, was_replayed = await register_benchmark_file(
            session,
            BenchmarkFileCreateRequest(
                file_id=file_id,
                dataset_version_id=dataset.id,
                file_kind="event",
                relative_path=str(source_event["relative_path"]),
                farm=MINIMAL_FARM,
                event_id=event_number,
                size_bytes=int(imported["source_size_bytes"]),
                row_count=int(source_event["row_count"]),
                schema_sha256=str(source_event["schema_sha256"]),
                content_sha256=str(source_event["file_sha256"]),
                metadata={
                    "standard_parquet": imported["parquet"]["data"],
                    "source_read_only": True,
                    "split_counts": source_event["split_counts"],
                },
            ),
        )
        created += 0 if was_replayed else 1
        replayed += 1 if was_replayed else 0
        event_database_id = f"care-v6-event-a-{event_number}"
        event_database_ids.append(event_database_id)
        _, was_replayed = await register_benchmark_event(
            session,
            BenchmarkEventCreateRequest(
                benchmark_event_id=event_database_id,
                dataset_version_id=dataset.id,
                source_file_id=file_id,
                event_id=event_number,
                farm=MINIMAL_FARM,
                source_asset_id=str(source_event["source_asset_id"]),
                logical_asset_id=f"CARE-A-{source_event['source_asset_id']}",
                event_label=str(source_event["event_label"]),
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

    for index, (mapping, semantics) in enumerate(
        zip(contract.mappings, contract.semantics, strict=True)
    ):
        _, was_replayed = await register_feature_map(
            session,
            BenchmarkFeatureMapCreateRequest(
                feature_map_id=f"care-v6-feature-a-{index:03d}",
                dataset_version_id=dataset.id,
                mapping_version=COLUMN_MAPPING_VERSION,
                farm=MINIMAL_FARM,
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
                quality_report_id=f"care-v6-quality-a-{imported['event_id']}",
                event_id=event_database_id,
                quality_rule_version=QUALITY_RULE_VERSION,
                feature_set_version=FEATURE_SET_VERSION,
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
    return MinimalImportRegistration(
        created,
        replayed,
        dataset.id,
        tuple(event_database_ids),
    )


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise CareMinimalImportError(f"JSON root must be an object: {path}")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the CARE v6 A0/A24 minimal import bundle")
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--quality-contract", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--object-store-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    object_store_root = args.object_store_root or (args.output_root / "immutable-object-store")
    result = build_a_minimal_import(
        _load_json(args.source_manifest),
        _load_json(args.quality_contract),
        args.dataset_root,
        args.output_root,
        source_archive_path=args.source_archive,
        artifact_store=LocalImmutableArtifactStore(object_store_root),
    )
    print(
        json.dumps(
            {
                "manifest": str(result.manifest_path),
                "manifest_file_sha256": result.manifest_file_sha256,
                "import_identity_sha256": result.manifest["immutable_registration_identity"],
                "replayed": result.replayed,
                "summary": result.manifest["summary"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


__all__ = [
    "MINIMAL_EVENT_IDS",
    "MINIMAL_IMPORT_SCHEMA_VERSION",
    "SOURCE_CONTRACT_URI",
    "TRUTH_ACCESS_SCOPE",
    "CareMinimalImportError",
    "MinimalImportRegistration",
    "MinimalImportResult",
    "build_a_minimal_import",
    "register_a_minimal_import",
    "verify_minimal_import_manifest",
]
