from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import windops_backend.benchmarks.care.pipeline_runtime as _pipeline_runtime
from windops_backend.benchmarks.care.artifact_utils import (
    canonical_json_sha256 as _sha256_json,
)
from windops_backend.benchmarks.care.artifact_utils import (
    sha256_file as _sha256_file,
)
from windops_backend.benchmarks.care.contract import (
    COLUMN_MAPPING_VERSION,
    DATASET_ID,
    DATASET_VERSION,
    DOI,
    LICENSE_NAME,
    LICENSE_URL,
    METADATA_COLUMNS,
)
from windops_backend.benchmarks.care.licensing import (
    build_care_artifact_license,
    verify_care_artifact_license,
)

PIPELINE_CONTRACT_VERSION = _pipeline_runtime.PIPELINE_CONTRACT_VERSION
PARQUET_LAYOUT_VERSION = _pipeline_runtime.PARQUET_LAYOUT_VERSION
JOB_STATE_SCHEMA_VERSION = _pipeline_runtime.JOB_STATE_SCHEMA_VERSION
CHECKPOINT_SCHEMA_VERSION = _pipeline_runtime.CHECKPOINT_SCHEMA_VERSION
PARQUET_COMPRESSION = _pipeline_runtime.PARQUET_COMPRESSION
PARQUET_COMPRESSION_LEVEL = _pipeline_runtime.PARQUET_COMPRESSION_LEVEL
PARQUET_ROW_GROUP_SIZE = _pipeline_runtime.PARQUET_ROW_GROUP_SIZE
CSV_BLOCK_SIZE_BYTES = _pipeline_runtime.CSV_BLOCK_SIZE_BYTES
COPY_BUFFER_BYTES = _pipeline_runtime.COPY_BUFFER_BYTES
MAX_JOB_ATTEMPTS = _pipeline_runtime.MAX_JOB_ATTEMPTS
QUALITY_RULE_VERSION = _pipeline_runtime.QUALITY_RULE_VERSION
FEATURE_SET_VERSION = _pipeline_runtime.FEATURE_SET_VERSION
CarePipelineError = _pipeline_runtime.CarePipelineError
BenchmarkJobCancelled = _pipeline_runtime.BenchmarkJobCancelled
RetryableBenchmarkError = _pipeline_runtime.RetryableBenchmarkError
_is_sha256 = _pipeline_runtime._is_sha256
_normalize_column_selection = _pipeline_runtime._normalize_column_selection
_validate_job_id = _pipeline_runtime._validate_job_id
_atomic_json = _pipeline_runtime._atomic_json
_project_local_output = _pipeline_runtime._project_local_output
BenchmarkDependencyVersions = _pipeline_runtime.BenchmarkDependencyVersions
load_benchmark_dependencies = _pipeline_runtime.load_benchmark_dependencies
benchmark_dependency_versions = _pipeline_runtime.benchmark_dependency_versions
CareObjectStorageLayout = _pipeline_runtime.CareObjectStorageLayout
ImmutableArtifactStore = _pipeline_runtime.ImmutableArtifactStore
_safe_object_key = _pipeline_runtime._safe_object_key
LocalImmutableArtifactStore = _pipeline_runtime.LocalImmutableArtifactStore
MinioImmutableArtifactStore = _pipeline_runtime.MinioImmutableArtifactStore
BenchmarkJobState = _pipeline_runtime.BenchmarkJobState
FileBenchmarkJobControl = _pipeline_runtime.FileBenchmarkJobControl


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    index: int
    relative_path: str
    row_count: int
    sha256: str

    def to_document(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "relative_path": self.relative_path,
            "row_count": self.row_count,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class ParquetCheckpoint:
    job_id: str
    source_sha256: str
    farm: str
    event_id: int
    schema_sha256: str
    processed_rows: int
    chunks: tuple[ChunkRecord, ...]

    def to_document(self) -> dict[str, Any]:
        payload = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "job_id": self.job_id,
            "source_sha256": self.source_sha256,
            "farm": self.farm,
            "event_id": self.event_id,
            "schema_sha256": self.schema_sha256,
            "processed_rows": self.processed_rows,
            "chunks": [item.to_document() for item in self.chunks],
        }
        return {**payload, "checkpoint_sha256": _sha256_json(payload)}

    @classmethod
    def from_path(cls, path: Path) -> ParquetCheckpoint:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise CarePipelineError("Parquet checkpoint root must be an object")
        actual = raw.get("checkpoint_sha256")
        unsigned = {key: item for key, item in raw.items() if key != "checkpoint_sha256"}
        if (
            not isinstance(actual, str)
            or _sha256_json(unsigned) != actual
            or raw.get("schema_version") != CHECKPOINT_SCHEMA_VERSION
        ):
            raise CarePipelineError("Parquet checkpoint hash or schema is invalid")
        chunks_raw = raw.get("chunks")
        if not isinstance(chunks_raw, list):
            raise CarePipelineError("Parquet checkpoint chunks are malformed")
        try:
            chunks = tuple(
                ChunkRecord(
                    int(item["index"]),
                    str(item["relative_path"]),
                    int(item["row_count"]),
                    str(item["sha256"]),
                )
                for item in chunks_raw
                if isinstance(item, Mapping)
            )
            if len(chunks) != len(chunks_raw):
                raise CarePipelineError("Parquet checkpoint contains a malformed chunk")
            checkpoint = cls(
                str(raw["job_id"]),
                str(raw["source_sha256"]),
                str(raw["farm"]),
                int(raw["event_id"]),
                str(raw["schema_sha256"]),
                int(raw["processed_rows"]),
                chunks,
            )
            if (
                not checkpoint.job_id.strip()
                or not _is_sha256(checkpoint.source_sha256)
                or not _is_sha256(checkpoint.schema_sha256)
                or checkpoint.farm not in {"A", "B", "C"}
                or not 0 <= checkpoint.event_id <= 94
                or checkpoint.processed_rows < 1
                or [chunk.index for chunk in chunks] != list(range(len(chunks)))
                or sum(chunk.row_count for chunk in chunks) != checkpoint.processed_rows
            ):
                raise CarePipelineError("Parquet checkpoint semantics are invalid")
            for chunk in chunks:
                relative = PurePosixPath(chunk.relative_path)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or not relative.parts
                    or relative.parts[0] != "chunks"
                    or chunk.row_count < 1
                    or not _is_sha256(chunk.sha256)
                ):
                    raise CarePipelineError("Parquet checkpoint chunk semantics are invalid")
            return checkpoint
        except (KeyError, TypeError, ValueError) as exc:
            raise CarePipelineError("Parquet checkpoint is malformed") from exc


@dataclass(frozen=True, slots=True)
class ParquetArtifact:
    local_path: Path
    manifest_path: Path
    artifact_uri: str
    content_sha256: str
    schema_sha256: str
    row_count: int
    row_group_count: int
    source_sha256: str
    source_dataset_sha256: str
    peak_record_batch_bytes: int
    peak_arrow_allocated_bytes: int
    elapsed_seconds: float


def _schema_hash(schema: Any) -> str:
    return hashlib.sha256(schema.remove_metadata().serialize().to_pybytes()).hexdigest()


def _canonical_parquet_schema(arrow: Any, source_schema: Any) -> Any:
    """Freeze timestamp precision so chunk readback cannot drift across Parquet boundaries."""

    fields = [
        field.with_type(arrow.timestamp("ms")) if arrow.types.is_timestamp(field.type) else field
        for field in source_schema
    ]
    return arrow.schema(fields)


def _validate_existing_artifact(
    final_path: Path,
    manifest_path: Path,
    *,
    farm: str | None = None,
    event_id: int | None = None,
    parquet_module: Any | None = None,
    selected_columns: Sequence[str] | None = None,
    model_input_columns: Sequence[str] | None = None,
    csv_block_size_bytes: int = CSV_BLOCK_SIZE_BYTES,
) -> ParquetArtifact | None:
    if not final_path.exists() and not manifest_path.exists():
        return None
    if not final_path.is_file() or not manifest_path.is_file():
        raise CarePipelineError("partial final Parquet artifact exists without its manifest")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise CarePipelineError("Parquet manifest root must be an object")
    manifest_hash = raw.get("manifest_sha256")
    unsigned = {key: item for key, item in raw.items() if key != "manifest_sha256"}
    if not isinstance(manifest_hash, str) or _sha256_json(unsigned) != manifest_hash:
        raise CarePipelineError("Parquet manifest hash mismatch")
    try:
        content_hash = str(raw.get("content_sha256", ""))
        schema_sha256 = str(raw.get("schema_sha256", ""))
        source_sha256 = str(raw.get("source_sha256", ""))
        row_count = int(raw.get("row_count", 0))
        row_group_count = int(raw.get("row_group_count", 0))
        manifest_columns = raw["columns"]
        manifest_model_inputs = raw["model_input_columns"]
        manifest_metadata_columns = raw["metadata_columns"]
        license_metadata = raw["license"]
        resource_stats = raw["resource_stats"]
        if (
            not isinstance(resource_stats, Mapping)
            or not isinstance(manifest_columns, list)
            or not all(isinstance(item, str) for item in manifest_columns)
            or not isinstance(manifest_model_inputs, list)
            or not all(isinstance(item, str) for item in manifest_model_inputs)
            or not isinstance(manifest_metadata_columns, list)
            or not all(isinstance(item, str) for item in manifest_metadata_columns)
            or not isinstance(license_metadata, Mapping)
        ):
            raise TypeError
        if (
            raw.get("schema_version") != PIPELINE_CONTRACT_VERSION
            or raw.get("layout_version") != PARQUET_LAYOUT_VERSION
            or raw.get("dataset_id") != DATASET_ID
            or raw.get("dataset_version") != DATASET_VERSION
            or raw.get("compression") != PARQUET_COMPRESSION
            or raw.get("compression_level") != PARQUET_COMPRESSION_LEVEL
            or raw.get("row_group_size") != PARQUET_ROW_GROUP_SIZE
            or int(raw.get("csv_block_size_bytes", CSV_BLOCK_SIZE_BYTES)) != csv_block_size_bytes
            or not _is_sha256(content_hash)
            or not _is_sha256(schema_sha256)
            or not _is_sha256(source_sha256)
            or not _is_sha256(str(raw.get("source_dataset_sha256", "")))
            or row_count < 1
            or row_group_count != (row_count + PARQUET_ROW_GROUP_SIZE - 1) // PARQUET_ROW_GROUP_SIZE
            or int(raw.get("column_count", 0)) != len(manifest_columns)
            or len(manifest_columns) != len(set(manifest_columns))
            or (farm is not None and raw.get("farm") != farm)
            or (event_id is not None and raw.get("event_id") != event_id)
            or (selected_columns is not None and tuple(manifest_columns) != tuple(selected_columns))
            or tuple(manifest_model_inputs) != tuple(model_input_columns or ())
            or not set(manifest_model_inputs).issubset(manifest_columns)
            or manifest_metadata_columns
            != [column for column in manifest_columns if column not in manifest_model_inputs]
            or raw.get("column_selection_sha256")
            != _sha256_json(
                {
                    "columns": manifest_columns,
                    "model_input_columns": manifest_model_inputs,
                }
            )
        ):
            raise CarePipelineError("Parquet manifest semantics are invalid")
        try:
            verify_care_artifact_license(
                license_metadata,
                artifact_type="wide-standard-parquet",
                source_dataset_sha256=str(raw["source_dataset_sha256"]),
                source_artifact_sha256=source_sha256,
                transformation_versions={
                    "column_mapping": COLUMN_MAPPING_VERSION,
                    "feature_set": FEATURE_SET_VERSION,
                    "pipeline": PIPELINE_CONTRACT_VERSION,
                    "quality_rules": QUALITY_RULE_VERSION,
                },
            )
        except (KeyError, ValueError) as exc:
            raise CarePipelineError("Parquet artifact license metadata is invalid") from exc
        peak_record_batch_bytes = int(resource_stats["peak_record_batch_bytes"])
        peak_arrow_allocated_bytes = int(resource_stats["peak_arrow_allocated_bytes"])
        elapsed_seconds = float(resource_stats["elapsed_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CarePipelineError("Parquet manifest semantics are invalid") from exc
    if _sha256_file(final_path) != content_hash:
        raise CarePipelineError("existing Parquet artifact content hash mismatch")
    if parquet_module is not None:
        parquet_file = parquet_module.ParquetFile(final_path)
        try:
            parquet_metadata = parquet_file.schema_arrow.metadata or {}
            try:
                embedded_license = json.loads(
                    parquet_metadata[b"care.artifact_license_json"].decode("utf-8")
                )
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CarePipelineError(
                    "Parquet artifact is missing embedded CARE license metadata"
                ) from exc
            if (
                int(parquet_file.metadata.num_rows) != row_count
                or int(parquet_file.num_row_groups) != row_group_count
                or _schema_hash(parquet_file.schema_arrow) != schema_sha256
                or list(parquet_file.schema_arrow.names) != manifest_columns
                or embedded_license != dict(license_metadata)
                or parquet_metadata.get(b"care.license_url") != LICENSE_URL.encode()
                or parquet_metadata.get(b"care.doi") != DOI.encode()
                or parquet_metadata.get(b"care.content_sha256_location")
                != b"immutable sidecar manifest and object key"
                or any(
                    parquet_file.metadata.row_group(group_index).num_rows
                    != (
                        PARQUET_ROW_GROUP_SIZE
                        if group_index < parquet_file.num_row_groups - 1
                        else row_count - PARQUET_ROW_GROUP_SIZE * (parquet_file.num_row_groups - 1)
                    )
                    or any(
                        parquet_file.metadata.row_group(group_index)
                        .column(column_index)
                        .compression.lower()
                        != PARQUET_COMPRESSION
                        for column_index in range(
                            parquet_file.metadata.row_group(group_index).num_columns
                        )
                    )
                    for group_index in range(parquet_file.num_row_groups)
                )
            ):
                raise CarePipelineError("Parquet physical metadata differs from its manifest")
        finally:
            parquet_file.close()
    return ParquetArtifact(
        final_path,
        manifest_path,
        str(raw["artifact_uri"]),
        content_hash,
        schema_sha256,
        row_count,
        row_group_count,
        source_sha256,
        str(raw["source_dataset_sha256"]),
        peak_record_batch_bytes,
        peak_arrow_allocated_bytes,
        elapsed_seconds,
    )


def convert_care_csv_to_parquet(
    source_path: Path,
    output_root: Path,
    *,
    job_id: str,
    farm: str,
    event_id: int,
    artifact_store: ImmutableArtifactStore | None = None,
    object_layout: CareObjectStorageLayout | None = None,
    job_control: FileBenchmarkJobControl | None = None,
    expected_source_sha256: str | None = None,
    source_dataset_sha256: str | None = None,
    stop_after_chunks: int | None = None,
    selected_columns: Sequence[str] | None = None,
    model_input_columns: Sequence[str] | None = None,
    csv_block_size_bytes: int = CSV_BLOCK_SIZE_BYTES,
) -> ParquetArtifact:
    """Convert a semicolon CARE event in bounded batches with durable chunk checkpoints."""

    if farm not in {"A", "B", "C"} or not 0 <= event_id <= 94:
        raise CarePipelineError("Parquet import has an invalid CARE event identity")
    if not 64 * 1024 <= csv_block_size_bytes <= 16 * 1024 * 1024:
        raise CarePipelineError("CSV block size must be between 64 KiB and 16 MiB")
    _validate_job_id(job_id)
    source_path, output_root = _project_local_output(source_path, output_root)
    selected, model_inputs = _normalize_column_selection(
        source_path,
        selected_columns,
        model_input_columns,
    )
    arrow, csv_module, parquet_module = load_benchmark_dependencies()
    destination_dir = (
        output_root
        / DATASET_ID
        / DATASET_VERSION
        / "standard"
        / f"farm={farm}"
        / f"event={event_id}"
    )
    final_path = destination_dir / "data.parquet"
    manifest_path = destination_dir / "manifest.json"
    source_sha256 = _sha256_file(source_path)
    if expected_source_sha256 and source_sha256 != expected_source_sha256.lower():
        raise CarePipelineError("source file SHA-256 differs from the immutable manifest")
    dataset_sha256 = source_dataset_sha256 or source_sha256
    if not _is_sha256(dataset_sha256):
        raise CarePipelineError("source dataset SHA-256 is invalid")
    projected_model_only = selected is not None and set(selected) == {
        *model_inputs,
        *METADATA_COLUMNS,
    }
    artifact_license = build_care_artifact_license(
        artifact_type="wide-standard-parquet",
        changes_made=(
            (
                "Converted the immutable semicolon CSV to projected, ZSTD-compressed wide "
                "Parquet; source values were preserved and non-approved statistics were omitted."
            )
            if projected_model_only
            else (
                "Converted the immutable semicolon CSV to ZSTD-compressed wide Parquet; "
                "all mapped signal columns and source values were preserved, while only "
                "metadata-approved Avg columns were designated as model inputs."
            )
        ),
        source_dataset_sha256=dataset_sha256,
        source_artifact_sha256=source_sha256,
        transformation_versions={
            "column_mapping": COLUMN_MAPPING_VERSION,
            "feature_set": FEATURE_SET_VERSION,
            "pipeline": PIPELINE_CONTRACT_VERSION,
            "quality_rules": QUALITY_RULE_VERSION,
        },
    )
    existing = _validate_existing_artifact(
        final_path,
        manifest_path,
        farm=farm,
        event_id=event_id,
        parquet_module=parquet_module,
        selected_columns=selected,
        model_input_columns=model_inputs,
        csv_block_size_bytes=csv_block_size_bytes,
    )
    if existing is not None:
        if existing.source_sha256 != source_sha256:
            raise CarePipelineError("existing immutable artifact belongs to another source")
        if existing.source_dataset_sha256 != dataset_sha256:
            raise CarePipelineError("existing immutable artifact belongs to another dataset")
        return existing

    started = time.perf_counter()
    work_dir = output_root / ".work" / job_id
    chunks_dir = work_dir / "chunks"
    checkpoint_path = work_dir / "checkpoint.json"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    checkpoint: ParquetCheckpoint | None = None
    if checkpoint_path.is_file():
        checkpoint = ParquetCheckpoint.from_path(checkpoint_path)
        if (
            checkpoint.job_id != job_id
            or checkpoint.source_sha256 != source_sha256
            or checkpoint.farm != farm
            or checkpoint.event_id != event_id
        ):
            raise CarePipelineError("checkpoint identity differs from the requested import")
        for chunk in checkpoint.chunks:
            chunk_path = work_dir / chunk.relative_path
            if not chunk_path.is_file() or _sha256_file(chunk_path) != chunk.sha256:
                raise CarePipelineError("checkpoint chunk is absent or corrupted")

    try:
        reader = csv_module.open_csv(
            str(source_path),
            read_options=csv_module.ReadOptions(
                block_size=csv_block_size_bytes,
                use_threads=False,
            ),
            parse_options=csv_module.ParseOptions(delimiter=";"),
            convert_options=csv_module.ConvertOptions(
                strings_can_be_null=False,
                include_columns=list(selected) if selected is not None else None,
            ),
        )
    except Exception as exc:
        raise CarePipelineError("selected CARE columns could not be read") from exc
    if selected is not None and tuple(reader.schema.names) != selected:
        raise CarePipelineError("selected CARE columns changed order during CSV projection")
    schema = _canonical_parquet_schema(arrow, reader.schema)
    schema_sha256 = _schema_hash(schema)
    arrow_allocation_baseline = int(arrow.total_allocated_bytes())
    if checkpoint is not None and checkpoint.schema_sha256 != schema_sha256:
        raise CarePipelineError("checkpoint schema differs from the current source")
    chunks = list(checkpoint.chunks if checkpoint else ())
    processed_rows = checkpoint.processed_rows if checkpoint else 0
    peak_batch_bytes = 0
    peak_arrow_bytes = 0
    try:
        for batch_index, batch in enumerate(reader):
            peak_batch_bytes = max(peak_batch_bytes, int(batch.nbytes))
            peak_arrow_bytes = max(
                peak_arrow_bytes,
                max(0, int(arrow.total_allocated_bytes()) - arrow_allocation_baseline),
            )
            if batch_index < len(chunks):
                if int(batch.num_rows) != chunks[batch_index].row_count:
                    raise CarePipelineError("resumed CSV batch no longer matches its checkpoint")
                continue
            if job_control is not None:
                job_control.cancellation_point()
            chunk_path = chunks_dir / f"chunk-{batch_index:08d}.parquet"
            partial = chunk_path.with_suffix(".parquet.partial")
            try:
                table = arrow.Table.from_batches([batch])
                if not table.schema.equals(schema, check_metadata=False):
                    table = table.cast(schema, safe=True)
                parquet_module.write_table(
                    table,
                    partial,
                    compression=PARQUET_COMPRESSION,
                    compression_level=PARQUET_COMPRESSION_LEVEL,
                    row_group_size=PARQUET_ROW_GROUP_SIZE,
                    write_statistics=True,
                )
                os.replace(partial, chunk_path)
            finally:
                partial.unlink(missing_ok=True)
            chunk = ChunkRecord(
                batch_index,
                str(chunk_path.relative_to(work_dir)).replace("\\", "/"),
                int(batch.num_rows),
                _sha256_file(chunk_path),
            )
            chunks.append(chunk)
            processed_rows += chunk.row_count
            checkpoint = ParquetCheckpoint(
                job_id,
                source_sha256,
                farm,
                event_id,
                schema_sha256,
                processed_rows,
                tuple(chunks),
            )
            _atomic_json(checkpoint_path, checkpoint.to_document())
            if job_control is not None:
                job_control.heartbeat(
                    completed=processed_rows,
                    total=None,
                    current_file=str(source_path),
                    checkpoint_path=str(checkpoint_path),
                    resource_stats={
                        "peak_record_batch_bytes": peak_batch_bytes,
                        "peak_arrow_allocated_bytes": peak_arrow_bytes,
                    },
                )
            if stop_after_chunks is not None and len(chunks) >= stop_after_chunks:
                raise BenchmarkJobCancelled("test stop after durable chunk boundary")

        if not chunks:
            raise CarePipelineError("CARE event CSV contains no data rows")
        destination_dir.mkdir(parents=True, exist_ok=True)
        final_partial = final_path.with_suffix(".parquet.partial")
        metadata = {
            b"care.pipeline_contract_version": PIPELINE_CONTRACT_VERSION.encode(),
            b"care.layout_version": PARQUET_LAYOUT_VERSION.encode(),
            b"care.dataset_id": DATASET_ID.encode(),
            b"care.dataset_version": DATASET_VERSION.encode(),
            b"care.farm": farm.encode(),
            b"care.event_id": str(event_id).encode(),
            b"care.source_sha256": source_sha256.encode(),
            b"care.schema_sha256": schema_sha256.encode(),
            b"care.row_count": str(processed_rows).encode(),
            b"care.csv_block_size_bytes": str(csv_block_size_bytes).encode(),
            b"care.license": LICENSE_NAME.encode(),
            b"care.license_url": artifact_license["license_url"].encode(),
            b"care.doi": artifact_license["doi"].encode(),
            b"care.recommended_citation": artifact_license["recommended_citation"].encode(),
            b"care.changes_made": artifact_license["changes_made"].encode(),
            b"care.artifact_license_json": json.dumps(
                artifact_license,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
            b"care.content_sha256_location": b"immutable sidecar manifest and object key",
            b"care.selected_columns_sha256": _sha256_json(list(schema.names)).encode(),
            b"care.model_input_columns_sha256": _sha256_json(list(model_inputs)).encode(),
        }
        writer = parquet_module.ParquetWriter(
            final_partial,
            schema.with_metadata(metadata),
            compression=PARQUET_COMPRESSION,
            compression_level=PARQUET_COMPRESSION_LEVEL,
            write_statistics=True,
        )
        pending_batches: list[Any] = []
        pending_rows = 0
        merged_rows = 0
        try:
            for chunk in chunks:
                chunk_file = parquet_module.ParquetFile(work_dir / chunk.relative_path)
                try:
                    for row_group_index in range(chunk_file.num_row_groups):
                        table = chunk_file.read_row_group(row_group_index)
                        for source_batch in table.to_batches(max_chunksize=PARQUET_ROW_GROUP_SIZE):
                            batch_offset = 0
                            while batch_offset < source_batch.num_rows:
                                take = min(
                                    PARQUET_ROW_GROUP_SIZE - pending_rows,
                                    source_batch.num_rows - batch_offset,
                                )
                                pending_batches.append(source_batch.slice(batch_offset, take))
                                pending_rows += take
                                batch_offset += take
                                if pending_rows == PARQUET_ROW_GROUP_SIZE:
                                    row_group = arrow.Table.from_batches(pending_batches)
                                    writer.write_table(
                                        row_group,
                                        row_group_size=PARQUET_ROW_GROUP_SIZE,
                                    )
                                    del row_group
                                    merged_rows += pending_rows
                                    pending_batches.clear()
                                    pending_rows = 0
                                    peak_arrow_bytes = max(
                                        peak_arrow_bytes,
                                        max(
                                            0,
                                            int(arrow.total_allocated_bytes())
                                            - arrow_allocation_baseline,
                                        ),
                                    )
                finally:
                    chunk_file.close()
            if pending_batches:
                row_group = arrow.Table.from_batches(pending_batches)
                writer.write_table(row_group, row_group_size=PARQUET_ROW_GROUP_SIZE)
                del row_group
                merged_rows += pending_rows
                pending_batches.clear()
                pending_rows = 0
                peak_arrow_bytes = max(
                    peak_arrow_bytes,
                    max(
                        0,
                        int(arrow.total_allocated_bytes()) - arrow_allocation_baseline,
                    ),
                )
            if merged_rows != processed_rows:
                raise CarePipelineError("coalesced Parquet row count differs from checkpoint")
        finally:
            writer.close()
        os.replace(final_partial, final_path)
    except (BenchmarkJobCancelled, CarePipelineError):
        (destination_dir / "data.parquet.partial").unlink(missing_ok=True)
        raise
    except Exception as exc:
        (destination_dir / "data.parquet.partial").unlink(missing_ok=True)
        raise CarePipelineError(f"CARE Parquet conversion failed: {type(exc).__name__}") from exc

    content_sha256 = _sha256_file(final_path)
    parquet_file = parquet_module.ParquetFile(final_path)
    try:
        row_group_count = int(parquet_file.num_row_groups)
        if row_group_count != (processed_rows + PARQUET_ROW_GROUP_SIZE - 1) // (
            PARQUET_ROW_GROUP_SIZE
        ):
            raise CarePipelineError("Parquet row groups are not fixed at the governed size")
    finally:
        parquet_file.close()
    layout = object_layout or CareObjectStorageLayout()
    object_key = layout.event_key(
        "standard",
        farm=farm,
        event_id=event_id,
        file_name=f"data.sha256-{content_sha256}.parquet",
    )
    try:
        artifact_uri = (
            artifact_store.put_immutable(
                object_key,
                final_path,
                content_sha256,
                content_type="application/vnd.apache.parquet",
            )
            if artifact_store is not None
            else final_path.resolve().as_uri()
        )
    except Exception:
        final_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise
    elapsed = time.perf_counter() - started
    dependencies = benchmark_dependency_versions().to_document()
    manifest: dict[str, Any] = {
        "schema_version": PIPELINE_CONTRACT_VERSION,
        "layout_version": PARQUET_LAYOUT_VERSION,
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "farm": farm,
        "event_id": event_id,
        "source_path": source_path.name,
        "source_sha256": source_sha256,
        "source_dataset_sha256": dataset_sha256,
        "schema_sha256": schema_sha256,
        "row_count": processed_rows,
        "row_group_count": row_group_count,
        "column_count": len(schema.names),
        "columns": list(schema.names),
        "model_input_columns": list(model_inputs),
        "metadata_columns": [column for column in schema.names if column not in model_inputs],
        "column_selection_sha256": _sha256_json(
            {"columns": list(schema.names), "model_input_columns": list(model_inputs)}
        ),
        "content_sha256": content_sha256,
        "artifact_uri": artifact_uri,
        "object_key": object_key,
        "compression": PARQUET_COMPRESSION,
        "compression_level": PARQUET_COMPRESSION_LEVEL,
        "row_group_size": PARQUET_ROW_GROUP_SIZE,
        "csv_block_size_bytes": csv_block_size_bytes,
        "dependencies": dependencies,
        "license": artifact_license,
        "resource_stats": {
            "peak_record_batch_bytes": peak_batch_bytes,
            "peak_arrow_allocated_bytes": peak_arrow_bytes,
            "elapsed_seconds": elapsed,
        },
    }
    manifest["manifest_sha256"] = _sha256_json(manifest)
    try:
        _atomic_json(manifest_path, manifest)
    except Exception:
        final_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise
    shutil.rmtree(work_dir)
    artifact = _validate_existing_artifact(
        final_path,
        manifest_path,
        farm=farm,
        event_id=event_id,
        parquet_module=parquet_module,
        selected_columns=selected,
        model_input_columns=model_inputs,
        csv_block_size_bytes=csv_block_size_bytes,
    )
    if artifact is None:  # pragma: no cover - both files were just atomically created
        raise CarePipelineError("final Parquet artifact disappeared after publication")
    if job_control is not None:
        job_control.complete(artifact.artifact_uri, manifest["resource_stats"])
    return artifact


@dataclass(frozen=True, slots=True)
class BoundedScanResult:
    row_count: int
    batch_count: int
    column_count: int
    source_size_bytes: int
    peak_record_batch_bytes: int
    peak_arrow_allocated_bytes: int
    elapsed_seconds: float

    def to_document(self) -> dict[str, int | float]:
        return {
            "row_count": self.row_count,
            "batch_count": self.batch_count,
            "column_count": self.column_count,
            "source_size_bytes": self.source_size_bytes,
            "peak_record_batch_bytes": self.peak_record_batch_bytes,
            "peak_arrow_allocated_bytes": self.peak_arrow_allocated_bytes,
            "elapsed_seconds": self.elapsed_seconds,
        }


def probe_care_csv_bounded(
    source_path: Path,
    *,
    maximum_batches: int | None = None,
) -> BoundedScanResult:
    arrow, csv_module, _parquet = load_benchmark_dependencies()
    source_path = source_path.resolve(strict=True)
    started = time.perf_counter()
    reader = csv_module.open_csv(
        str(source_path),
        read_options=csv_module.ReadOptions(block_size=CSV_BLOCK_SIZE_BYTES, use_threads=False),
        parse_options=csv_module.ParseOptions(delimiter=";"),
        convert_options=csv_module.ConvertOptions(strings_can_be_null=False),
    )
    arrow_allocation_baseline = int(arrow.total_allocated_bytes())
    row_count = 0
    batch_count = 0
    peak_batch_bytes = 0
    peak_arrow_bytes = 0
    for batch in reader:
        row_count += int(batch.num_rows)
        batch_count += 1
        peak_batch_bytes = max(peak_batch_bytes, int(batch.nbytes))
        peak_arrow_bytes = max(
            peak_arrow_bytes,
            max(0, int(arrow.total_allocated_bytes()) - arrow_allocation_baseline),
        )
        if maximum_batches is not None and batch_count >= maximum_batches:
            break
    return BoundedScanResult(
        row_count,
        batch_count,
        len(reader.schema.names),
        source_path.stat().st_size,
        peak_batch_bytes,
        peak_arrow_bytes,
        time.perf_counter() - started,
    )


@dataclass(frozen=True, slots=True)
class ColumnProjectionResult:
    row_count: int
    selected_columns: tuple[str, ...]
    total_column_count: int
    row_group_count: int
    peak_selected_batch_bytes: int


def verify_parquet_column_projection(
    path: Path,
    columns: Sequence[str],
) -> ColumnProjectionResult:
    _arrow, _csv, parquet_module = load_benchmark_dependencies()
    parquet_file = parquet_module.ParquetFile(path)
    available = tuple(parquet_file.schema_arrow.names)
    selected = tuple(columns)
    if not selected or len(selected) != len(set(selected)):
        raise CarePipelineError("Parquet column projection must be non-empty and unique")
    missing = sorted(set(selected).difference(available))
    if missing:
        raise CarePipelineError(f"Parquet projection requested unknown columns: {missing}")
    rows = 0
    peak_bytes = 0
    for index in range(parquet_file.num_row_groups):
        table = parquet_file.read_row_group(index, columns=list(selected))
        rows += int(table.num_rows)
        peak_bytes = max(peak_bytes, int(table.nbytes))
    return ColumnProjectionResult(
        rows, selected, len(available), parquet_file.num_row_groups, peak_bytes
    )


def run_with_bounded_retries(
    control: FileBenchmarkJobControl,
    operation: Callable[[], ParquetArtifact],
) -> ParquetArtifact:
    while True:
        state = control.start_attempt()
        if state.status == "cancelled":
            raise BenchmarkJobCancelled("benchmark job was cancelled before execution")
        try:
            artifact = operation()
            if control.read().status != "completed":
                control.complete(
                    artifact.artifact_uri,
                    {
                        "peak_record_batch_bytes": artifact.peak_record_batch_bytes,
                        "peak_arrow_allocated_bytes": artifact.peak_arrow_allocated_bytes,
                        "elapsed_seconds": artifact.elapsed_seconds,
                    },
                )
            return artifact
        except BenchmarkJobCancelled:
            raise
        except RetryableBenchmarkError as exc:
            updated = control.fail(exc)
            if updated.status == "failed":
                raise
            continue
        except Exception as exc:
            control.fail(exc, retryable=False)
            raise


def write_bounded_probe(
    source_path: Path,
    output_path: Path,
    *,
    maximum_batches: int | None = None,
) -> dict[str, Any]:
    source_path = source_path.resolve(strict=True)
    output_path = output_path.resolve()
    if output_path == source_path or output_path.is_relative_to(source_path):
        raise CarePipelineError("bounded probe output cannot overwrite its source")
    result = probe_care_csv_bounded(source_path, maximum_batches=maximum_batches)
    payload: dict[str, Any] = {
        "schema_version": PIPELINE_CONTRACT_VERSION,
        "source_path": source_path.name,
        "source_sha256": _sha256_file(source_path),
        "maximum_batches": maximum_batches,
        "dependencies": benchmark_dependency_versions().to_document(),
        "result": result.to_document(),
    }
    payload["probe_sha256"] = _sha256_json(payload)
    _atomic_json(output_path, payload)
    return payload


def build_pipeline_contract() -> dict[str, Any]:
    layout = CareObjectStorageLayout()
    contract: dict[str, Any] = {
        "schema_version": PIPELINE_CONTRACT_VERSION,
        "execution": {
            "process": "independent-cli-or-dramatiq-worker",
            "http_request_does_heavy_work": False,
            "operations": ["import", "quality", "train", "evaluate"],
            "heartbeat": True,
            "bounded_attempts": MAX_JOB_ATTEMPTS,
            "cancellation_boundary": "after-each-confirmed-record-batch",
            "resume": "content-verified-chunk-checkpoint",
        },
        "dependencies": {
            "optional_extra": "benchmark",
            "columnar_engine": "pyarrow",
            "baseline_engine": "scikit-learn",
            "loaded_by_online_api": False,
        },
        "parquet": {
            "layout_version": PARQUET_LAYOUT_VERSION,
            "shape": "one-wide-table-per-dataset-version-farm-event",
            "partition_keys": ["dataset_version", "farm", "event"],
            "compression": PARQUET_COMPRESSION,
            "compression_level": PARQUET_COMPRESSION_LEVEL,
            "row_group_size": PARQUET_ROW_GROUP_SIZE,
            "csv_block_size_bytes": CSV_BLOCK_SIZE_BYTES,
            "column_projection": True,
            "manifest_fields": ["schema_sha256", "row_count", "content_sha256"],
            "object_naming": "content-addressed-data.sha256-<content_sha256>.parquet",
        },
        "object_storage": layout.contract_document(),
        "immutability": {
            "same_key_same_content": "idempotent-success",
            "same_key_different_content": "fail-closed",
            "temporary_publish_cleanup": True,
            "final_metric_owner": "CARE-H002/H004",
        },
    }
    contract["contract_sha256"] = _sha256_json(contract)
    return contract


def verify_pipeline_contract(contract: Mapping[str, Any]) -> None:
    actual = contract.get("contract_sha256")
    if not isinstance(actual, str):
        raise CarePipelineError("pipeline contract is missing contract_sha256")
    unsigned = {key: value for key, value in contract.items() if key != "contract_sha256"}
    if _sha256_json(unsigned) != actual or dict(contract) != build_pipeline_contract():
        raise CarePipelineError("pipeline contract hash or frozen semantics differ")


def write_pipeline_contract(path: Path) -> None:
    contract = build_pipeline_contract()
    verify_pipeline_contract(contract)
    _atomic_json(path, contract)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Independent CARE v6 benchmark pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    contract = subparsers.add_parser("contract")
    contract.add_argument("output", type=Path)
    convert = subparsers.add_parser("parquet")
    convert.add_argument("source", type=Path)
    convert.add_argument("output_root", type=Path)
    convert.add_argument("--job-id", required=True)
    convert.add_argument("--farm", choices=("A", "B", "C"), required=True)
    convert.add_argument("--event", type=int, required=True)
    probe = subparsers.add_parser("probe")
    probe.add_argument("source", type=Path)
    probe.add_argument("output", type=Path)
    probe.add_argument("--maximum-batches", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "contract":
        write_pipeline_contract(args.output)
        return 0
    if args.command == "parquet":
        artifact = convert_care_csv_to_parquet(
            args.source,
            args.output_root,
            job_id=args.job_id,
            farm=args.farm,
            event_id=args.event,
        )
        print(artifact.manifest_path)
        return 0
    if args.command == "probe":
        write_bounded_probe(
            args.source,
            args.output,
            maximum_batches=args.maximum_batches,
        )
        print(args.output)
        return 0
    raise CarePipelineError(f"unsupported command {args.command}")
