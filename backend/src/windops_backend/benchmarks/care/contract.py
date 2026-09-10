from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from windops_backend.benchmarks.care.artifact_utils import (
    canonical_json_sha256 as _sha256_json,
)

DATASET_ID = "care"
DATASET_VERSION = "v6"
MANIFEST_SCHEMA_VERSION = "care-v6-manifest-v1"
COLUMN_MAPPING_VERSION = "care-v6-column-map-v1"
LICENSE_NAME = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
ZENODO_URL = "https://zenodo.org/records/15846963"
DOI = "10.5281/zenodo.15846963"

METADATA_COLUMNS = (
    "time_stamp",
    "asset_id",
    "id",
    "train_test",
    "status_type_id",
)
FEATURE_METADATA_COLUMNS = (
    "sensor_name",
    "statistics_type",
    "description",
    "unit",
    "is_angle",
    "is_counter",
)
EVENT_METADATA_COMMON_COLUMNS = (
    "event_id",
    "event_label",
    "event_start",
    "event_start_id",
    "event_end",
    "event_end_id",
    "event_description",
)
STATISTIC_SUFFIXES = {
    "average": "avg",
    "maximum": "max",
    "minimum": "min",
    "std_dev": "std",
}
STATISTIC_ORDER = tuple(sorted(STATISTIC_SUFFIXES))
A_BARE_AVERAGE_ALIASES = {
    f"sensor_{index}": (f"sensor_{index}", "average") for index in range(44, 52)
}
DEFAULT_EXPLICIT_ALIASES: Mapping[str, Mapping[str, tuple[str, str]]] = {
    "A": A_BARE_AVERAGE_ALIASES,
    "B": {},
    "C": {},
}


class CareContractError(ValueError):
    """Raised when CARE v6 violates the frozen fail-closed data contract."""


@dataclass(frozen=True)
class CareDatasetExpectations:
    farms: tuple[str, ...]
    csv_count: int
    event_ids: tuple[int, ...]
    signal_counts: tuple[tuple[str, int], ...]
    zip_size_bytes: int | None = None
    zip_md5: str | None = None
    zip_sha256: str | None = None

    def signal_count_for(self, farm: str) -> int:
        counts = dict(self.signal_counts)
        try:
            return counts[farm]
        except KeyError as exc:
            raise CareContractError(f"missing signal-count expectation for farm {farm}") from exc


CARE_V6_EXPECTATIONS = CareDatasetExpectations(
    farms=("A", "B", "C"),
    csv_count=101,
    event_ids=tuple(range(95)),
    signal_counts=(("A", 81), ("B", 252), ("C", 952)),
    zip_size_bytes=5_503_439_673,
    zip_md5="2547b58c21ac8c242d13232860cf500c",
    zip_sha256="ca61379e98956d891041ad45c885109bd8a14199fde0688d0184a11c2d4194f1",
)


@dataclass(frozen=True)
class FeatureDefinition:
    sensor_name: str
    statistics: tuple[str, ...]
    description: str
    unit: str
    is_angle: bool
    is_counter: bool


@dataclass(frozen=True)
class EventDefinition:
    farm: str
    event_id: int
    source_asset_id: str
    event_label: str
    event_start_id: int
    event_end_id: int
    event_start: str
    event_end: str
    event_description: str


@dataclass(frozen=True)
class EventFileScan:
    relative_path: str
    size_bytes: int
    sha256: str
    schema_sha256: str
    header: tuple[str, ...]
    row_count: int
    minimum_source_row_id: int
    maximum_source_row_id: int
    split_counts: tuple[tuple[str, int], ...]
    source_assets: tuple[str, ...]


def verify_care_contract(manifest: Mapping[str, Any]) -> None:
    actual = manifest.get("manifest_sha256")
    if not isinstance(actual, str):
        raise CareContractError("CARE manifest is missing manifest_sha256")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    expected = _sha256_json(unsigned)
    if actual != expected:
        raise CareContractError(f"CARE manifest hash mismatch: expected {expected}, got {actual}")


def normalize_statistics_types(raw_value: str) -> tuple[str, ...]:
    values = {part.strip() for part in raw_value.split(",") if part.strip()}
    if not values:
        raise CareContractError("statistics_type must contain at least one statistic")
    unsupported = sorted(values.difference(STATISTIC_SUFFIXES))
    if unsupported:
        raise CareContractError(f"unsupported statistics_type values: {unsupported}")
    return tuple(statistic for statistic in STATISTIC_ORDER if statistic in values)


def _parse_boolean(raw_value: str, *, field: str) -> bool:
    if raw_value == "True":
        return True
    if raw_value == "False":
        return False
    raise CareContractError(f"{field} must be exactly True or False, got {raw_value!r}")


def _read_small_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]], dict[str, Any]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CareContractError(f"{path.name} is not valid UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=";")
    if reader.fieldnames is None:
        raise CareContractError(f"{path.name} has no header")
    header = tuple(reader.fieldnames)
    if len(header) != len(set(header)):
        raise CareContractError(f"{path.name} has duplicate header columns")
    rows: list[dict[str, str]] = []
    for line_number, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise CareContractError(f"{path.name}:{line_number} has a malformed row")
        rows.append(
            {key: value for key, value in row.items() if key is not None and value is not None}
        )
    record = {
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "row_count": len(rows),
        "schema_sha256": _sha256_json(list(header)),
    }
    return header, rows, record


def _require_exact_header(path: Path, actual: Sequence[str], expected: Sequence[str]) -> None:
    if tuple(actual) != tuple(expected):
        raise CareContractError(
            f"{path.name} header mismatch: expected {list(expected)!r}, got {list(actual)!r}"
        )


def _parse_feature_definitions(path: Path) -> tuple[list[FeatureDefinition], dict[str, Any]]:
    header, rows, record = _read_small_csv(path)
    _require_exact_header(path, header, FEATURE_METADATA_COLUMNS)
    features: list[FeatureDefinition] = []
    seen: set[str] = set()
    for row in rows:
        sensor_name = row["sensor_name"].strip()
        if not sensor_name:
            raise CareContractError(f"{path.name} contains an empty sensor_name")
        if sensor_name in seen:
            raise CareContractError(f"duplicate feature metadata sensor: {sensor_name}")
        seen.add(sensor_name)
        features.append(
            FeatureDefinition(
                sensor_name=sensor_name,
                statistics=normalize_statistics_types(row["statistics_type"]),
                description=row["description"],
                unit=row["unit"],
                is_angle=_parse_boolean(row["is_angle"], field="is_angle"),
                is_counter=_parse_boolean(row["is_counter"], field="is_counter"),
            )
        )
    return features, record


def _parse_event_definitions(
    path: Path,
    farm: str,
) -> tuple[list[EventDefinition], dict[str, Any]]:
    header, rows, record = _read_small_csv(path)
    asset_column = "asset" if farm == "A" else "asset_id"
    _require_exact_header(path, header, (asset_column, *EVENT_METADATA_COMMON_COLUMNS))
    events: list[EventDefinition] = []
    seen: set[int] = set()
    for row in rows:
        try:
            event_id = int(row["event_id"])
            event_start_id = int(row["event_start_id"])
            event_end_id = int(row["event_end_id"])
        except ValueError as exc:
            raise CareContractError(f"{path.name} contains a non-integer event or row ID") from exc
        if event_id in seen:
            raise CareContractError(f"duplicate event metadata ID: {event_id}")
        seen.add(event_id)
        source_asset_id = row[asset_column].strip()
        if not source_asset_id:
            raise CareContractError(f"event {event_id} has an empty source asset")
        event_label = row["event_label"].strip()
        if event_label not in {"anomaly", "normal"}:
            raise CareContractError(f"event {event_id} has invalid label {event_label!r}")
        if event_start_id > event_end_id:
            raise CareContractError(f"event {event_id} has a reversed event interval")
        events.append(
            EventDefinition(
                farm=farm,
                event_id=event_id,
                source_asset_id=source_asset_id,
                event_label=event_label,
                event_start_id=event_start_id,
                event_end_id=event_end_id,
                event_start=row["event_start"],
                event_end=row["event_end"],
                event_description=row["event_description"],
            )
        )
    return events, record


def build_column_mappings(
    *,
    farm: str,
    features: Sequence[FeatureDefinition],
    signal_columns: Sequence[str],
    explicit_aliases: Mapping[str, tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    aliases = dict(explicit_aliases or {})
    if len(signal_columns) != len(set(signal_columns)):
        raise CareContractError(f"farm {farm} has duplicate signal columns")

    definitions = {
        (feature.sensor_name, statistic): feature
        for feature in features
        for statistic in feature.statistics
    }
    if len(definitions) != sum(len(feature.statistics) for feature in features):
        raise CareContractError(f"farm {farm} has duplicate feature/statistic definitions")

    alias_targets: dict[tuple[str, str], str] = {}
    for source_column, target in aliases.items():
        if target not in definitions:
            raise CareContractError(
                f"farm {farm} alias {source_column!r} targets unknown feature/statistic {target!r}"
            )
        if target in alias_targets:
            raise CareContractError(
                f"farm {farm} has duplicate aliases for feature/statistic {target!r}"
            )
        alias_targets[target] = source_column

    candidates: dict[str, list[tuple[str, str]]] = {}
    for sensor_name, statistic in definitions:
        source_column = alias_targets.get(
            (sensor_name, statistic),
            f"{sensor_name}_{STATISTIC_SUFFIXES[statistic]}",
        )
        candidates.setdefault(source_column, []).append((sensor_name, statistic))

    ambiguous = {source: targets for source, targets in candidates.items() if len(targets) != 1}
    if ambiguous:
        raise CareContractError(f"farm {farm} has ambiguous column mappings: {ambiguous!r}")

    actual = set(signal_columns)
    expected = set(candidates)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown:
        raise CareContractError(f"farm {farm} has unknown signal columns: {unknown}")
    if missing:
        raise CareContractError(f"farm {farm} is missing signal columns: {missing}")

    mappings: list[dict[str, Any]] = []
    for source_column in signal_columns:
        sensor_name, statistic = candidates[source_column][0]
        feature = definitions[(sensor_name, statistic)]
        mappings.append(
            {
                "source_column": source_column,
                "base_sensor": sensor_name,
                "statistic": statistic,
                "mapping_source": "explicit-versioned-alias"
                if source_column in aliases
                else "feature-metadata-and-statistic-suffix",
                "description": feature.description,
                "source_unit": feature.unit,
                "is_angle": feature.is_angle,
                "is_counter": feature.is_counter,
            }
        )
    return mappings


def _decode_required(raw: bytes, *, path: Path, row_number: int, field: str) -> str:
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CareContractError(f"{path.name}:{row_number} has invalid UTF-8 in {field}") from exc
    if not value:
        raise CareContractError(f"{path.name}:{row_number} has an empty {field}")
    return value


def _scan_event_file(path: Path, relative_path: str) -> EventFileScan:
    digest = hashlib.sha256()
    row_count = 0
    minimum_id: int | None = None
    maximum_id: int | None = None
    split_counts: Counter[str] = Counter()
    source_assets: set[str] = set()
    with path.open("rb") as handle:
        raw_header = handle.readline()
        if not raw_header:
            raise CareContractError(f"{relative_path} is empty")
        digest.update(raw_header)
        try:
            header = tuple(
                next(csv.reader([raw_header.decode("utf-8-sig").rstrip("\r\n")], delimiter=";"))
            )
        except (UnicodeDecodeError, csv.Error) as exc:
            raise CareContractError(f"{relative_path} has an invalid header") from exc
        if len(header) != len(set(header)):
            raise CareContractError(f"{relative_path} has duplicate header columns")
        if header[: len(METADATA_COLUMNS)] != METADATA_COLUMNS:
            raise CareContractError(
                f"{relative_path} metadata columns must be {list(METADATA_COLUMNS)!r}"
            )
        expected_delimiters = len(header) - 1
        for row_number, raw_line in enumerate(handle, start=2):
            digest.update(raw_line)
            if not raw_line.strip(b"\r\n"):
                raise CareContractError(f"{relative_path}:{row_number} is blank")
            if raw_line.count(b";") != expected_delimiters:
                raise CareContractError(
                    f"{relative_path}:{row_number} does not match the frozen schema width"
                )
            first_fields = raw_line.rstrip(b"\r\n").split(b";", 5)
            if len(first_fields) != 6:
                raise CareContractError(f"{relative_path}:{row_number} is malformed")
            source_asset = _decode_required(
                first_fields[1], path=path, row_number=row_number, field="asset_id"
            )
            raw_source_id = _decode_required(
                first_fields[2], path=path, row_number=row_number, field="id"
            )
            split = _decode_required(
                first_fields[3], path=path, row_number=row_number, field="train_test"
            )
            if split not in {"train", "prediction"}:
                raise CareContractError(
                    f"{relative_path}:{row_number} has invalid train_test value {split!r}"
                )
            try:
                source_id = int(raw_source_id)
            except ValueError as exc:
                raise CareContractError(
                    f"{relative_path}:{row_number} has non-integer id {raw_source_id!r}"
                ) from exc
            minimum_id = source_id if minimum_id is None else min(minimum_id, source_id)
            maximum_id = source_id if maximum_id is None else max(maximum_id, source_id)
            source_assets.add(source_asset)
            split_counts[split] += 1
            row_count += 1
    if row_count == 0 or minimum_id is None or maximum_id is None:
        raise CareContractError(f"{relative_path} has no data rows")
    return EventFileScan(
        relative_path=relative_path,
        size_bytes=path.stat().st_size,
        sha256=digest.hexdigest(),
        schema_sha256=_sha256_json(list(header)),
        header=header,
        row_count=row_count,
        minimum_source_row_id=minimum_id,
        maximum_source_row_id=maximum_id,
        split_counts=tuple(sorted(split_counts.items())),
        source_assets=tuple(sorted(source_assets)),
    )


def _hash_zip(path: Path) -> dict[str, Any]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            md5.update(chunk)
            sha256.update(chunk)
            size += len(chunk)
    return {
        "filename": path.name,
        "size_bytes": size,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def _validate_zip(zip_record: Mapping[str, Any], expected: CareDatasetExpectations) -> None:
    checks = (
        ("size_bytes", expected.zip_size_bytes),
        ("md5", expected.zip_md5),
        ("sha256", expected.zip_sha256),
    )
    for field, expected_value in checks:
        if expected_value is not None and zip_record[field] != expected_value:
            raise CareContractError(
                f"CARE ZIP {field} mismatch: expected {expected_value!r}, got {zip_record[field]!r}"
            )


def _file_record(
    *,
    relative_path: str,
    kind: str,
    farm: str,
    record: Mapping[str, Any],
    event_id: int | None = None,
) -> dict[str, Any]:
    result = {
        "relative_path": relative_path,
        "kind": kind,
        "farm": farm,
        "size_bytes": record["size_bytes"],
        "sha256": record["sha256"],
        "row_count": record["row_count"],
        "schema_sha256": record["schema_sha256"],
    }
    if event_id is not None:
        result["event_id"] = event_id
    return result


def _ensure_read_only_source_output(dataset_root: Path, zip_path: Path, output_path: Path) -> None:
    root = dataset_root.resolve()
    output = output_path.resolve()
    if output == zip_path.resolve() or output.is_relative_to(root):
        raise CareContractError("contract output must not modify the read-only CARE source")


def build_care_contract(
    dataset_root: Path,
    zip_path: Path,
    *,
    expectations: CareDatasetExpectations = CARE_V6_EXPECTATIONS,
    explicit_aliases: Mapping[str, Mapping[str, tuple[str, str]]] = DEFAULT_EXPLICIT_ALIASES,
    tool_git_commit: str = "unknown",
    dependency_lock_sha256: str = "unknown",
) -> dict[str, Any]:
    dataset_root = dataset_root.resolve()
    zip_path = zip_path.resolve()
    if not dataset_root.is_dir():
        raise CareContractError(f"CARE dataset root does not exist: {dataset_root}")
    if not zip_path.is_file():
        raise CareContractError(f"CARE ZIP does not exist: {zip_path}")

    zip_record = _hash_zip(zip_path)
    _validate_zip(zip_record, expectations)
    csv_paths = sorted(
        (path for path in dataset_root.rglob("*.csv") if path.is_file()),
        key=lambda path: path.relative_to(dataset_root).as_posix(),
    )
    if len(csv_paths) != expectations.csv_count:
        raise CareContractError(
            f"CARE CSV count mismatch: expected {expectations.csv_count}, got {len(csv_paths)}"
        )

    csv_files: list[dict[str, Any]] = []
    farm_records: list[dict[str, Any]] = []
    event_records: list[dict[str, Any]] = []
    all_event_ids: set[int] = set()

    for farm in expectations.farms:
        farm_directory = dataset_root / f"Wind Farm {farm}"
        feature_path = farm_directory / "feature_description.csv"
        event_info_path = farm_directory / "event_info.csv"
        dataset_directory = farm_directory / "datasets"
        if (
            not feature_path.is_file()
            or not event_info_path.is_file()
            or not dataset_directory.is_dir()
        ):
            raise CareContractError(f"farm {farm} is missing its required CARE directory structure")

        features, feature_file_record = _parse_feature_definitions(feature_path)
        events, event_info_file_record = _parse_event_definitions(event_info_path, farm)
        relative_feature = feature_path.relative_to(dataset_root).as_posix()
        relative_event_info = event_info_path.relative_to(dataset_root).as_posix()
        csv_files.append(
            _file_record(
                relative_path=relative_feature,
                kind="feature-metadata",
                farm=farm,
                record=feature_file_record,
            )
        )
        csv_files.append(
            _file_record(
                relative_path=relative_event_info,
                kind="event-metadata",
                farm=farm,
                record=event_info_file_record,
            )
        )

        event_by_id = {event.event_id: event for event in events}
        dataset_files = sorted(dataset_directory.glob("*.csv"), key=lambda path: int(path.stem))
        dataset_ids: set[int] = set()
        canonical_signal_header: tuple[str, ...] | None = None
        farm_mapping: list[dict[str, Any]] | None = None
        for dataset_file in dataset_files:
            try:
                event_id = int(dataset_file.stem)
            except ValueError as exc:
                raise CareContractError(
                    f"farm {farm} has a non-numeric event filename: {dataset_file.name}"
                ) from exc
            if event_id in dataset_ids:
                raise CareContractError(f"farm {farm} has duplicate event file ID {event_id}")
            dataset_ids.add(event_id)
            relative_dataset = dataset_file.relative_to(dataset_root).as_posix()
            scan = _scan_event_file(dataset_file, relative_dataset)
            signal_header = scan.header[len(METADATA_COLUMNS) :]
            if canonical_signal_header is None:
                canonical_signal_header = signal_header
                farm_mapping = build_column_mappings(
                    farm=farm,
                    features=features,
                    signal_columns=signal_header,
                    explicit_aliases=explicit_aliases.get(farm, {}),
                )
            elif signal_header != canonical_signal_header:
                raise CareContractError(
                    f"farm {farm} event {event_id} schema differs from the farm contract"
                )
            if len(signal_header) != expectations.signal_count_for(farm):
                raise CareContractError(
                    f"farm {farm} signal count mismatch: expected "
                    f"{expectations.signal_count_for(farm)}, got {len(signal_header)}"
                )
            metadata = event_by_id.get(event_id)
            if metadata is None:
                raise CareContractError(
                    f"farm {farm} event file {event_id}.csv has no event_info.csv row"
                )
            if scan.source_assets != (metadata.source_asset_id,):
                raise CareContractError(
                    f"farm {farm} event {event_id} asset mismatch: metadata "
                    f"{metadata.source_asset_id!r}, data {scan.source_assets!r}"
                )
            if not (
                scan.minimum_source_row_id
                <= metadata.event_start_id
                <= metadata.event_end_id
                <= scan.maximum_source_row_id
            ):
                raise CareContractError(
                    f"farm {farm} event {event_id} truth interval is outside the file ID range"
                )
            scan_record = {
                "size_bytes": scan.size_bytes,
                "sha256": scan.sha256,
                "row_count": scan.row_count,
                "schema_sha256": scan.schema_sha256,
            }
            csv_files.append(
                _file_record(
                    relative_path=relative_dataset,
                    kind="event-data",
                    farm=farm,
                    event_id=event_id,
                    record=scan_record,
                )
            )
            event_records.append(
                {
                    "farm": farm,
                    "event_id": event_id,
                    "relative_path": relative_dataset,
                    "source_asset_id": metadata.source_asset_id,
                    "event_label": metadata.event_label,
                    "event_start_id": metadata.event_start_id,
                    "event_end_id": metadata.event_end_id,
                    "event_start": metadata.event_start,
                    "event_end": metadata.event_end,
                    "event_description": metadata.event_description,
                    "row_count": scan.row_count,
                    "source_row_id_min": scan.minimum_source_row_id,
                    "source_row_id_max": scan.maximum_source_row_id,
                    "split_counts": dict(scan.split_counts),
                    "schema_sha256": scan.schema_sha256,
                    "file_sha256": scan.sha256,
                }
            )
            all_event_ids.add(event_id)

        metadata_ids = set(event_by_id)
        if dataset_ids != metadata_ids:
            missing_files = sorted(metadata_ids - dataset_ids)
            orphan_files = sorted(dataset_ids - metadata_ids)
            raise CareContractError(
                f"farm {farm} event ID mismatch: missing files {missing_files}, "
                f"orphan files {orphan_files}"
            )
        if canonical_signal_header is None or farm_mapping is None:
            raise CareContractError(f"farm {farm} has no event data files")
        farm_records.append(
            {
                "farm": farm,
                "event_count": len(events),
                "event_ids": sorted(metadata_ids),
                "signal_column_count": len(canonical_signal_header),
                "signal_schema_sha256": _sha256_json(list(canonical_signal_header)),
                "feature_count": len(features),
                "column_mapping_version": COLUMN_MAPPING_VERSION,
                "column_mapping_sha256": _sha256_json(farm_mapping),
                "column_mappings": farm_mapping,
            }
        )

    expected_event_ids = set(expectations.event_ids)
    if all_event_ids != expected_event_ids:
        raise CareContractError(
            "CARE event ID coverage mismatch: "
            f"missing {sorted(expected_event_ids - all_event_ids)}, "
            f"unexpected {sorted(all_event_ids - expected_event_ids)}"
        )
    if len(csv_files) != expectations.csv_count:
        raise CareContractError(
            f"manifest CSV record count mismatch: expected {expectations.csv_count}, "
            f"got {len(csv_files)}"
        )

    csv_files.sort(key=lambda record: str(record["relative_path"]))
    event_records.sort(key=lambda record: int(record["event_id"]))
    farm_records.sort(key=lambda record: str(record["farm"]))
    anomaly_count = sum(event["event_label"] == "anomaly" for event in event_records)
    normal_count = sum(event["event_label"] == "normal" for event in event_records)
    source_assets = {(str(event["farm"]), str(event["source_asset_id"])) for event in event_records}
    payload: dict[str, Any] = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "source": {
            "zenodo_url": ZENODO_URL,
            "doi": DOI,
            "zip": zip_record,
            "read_only": True,
        },
        "license": {
            "name": LICENSE_NAME,
            "url": LICENSE_URL,
            "changes_made": (
                "No changes to source ZIP/CSV; manifest and mappings are derived artifacts."
            ),
            "artifact_license": LICENSE_NAME,
        },
        "generator": {
            "version": MANIFEST_SCHEMA_VERSION,
            "git_commit": tool_git_commit,
            "dependency_lock_sha256": dependency_lock_sha256,
        },
        "mapping_contract": {
            "statistics_field": "statistics_type",
            "statistics_set_order": list(STATISTIC_ORDER),
            "metadata_columns": list(METADATA_COLUMNS),
            "a_bare_average_columns": sorted(A_BARE_AVERAGE_ALIASES),
            "unknown_missing_duplicate_ambiguous_policy": "fail-closed",
        },
        "summary": {
            "csv_file_count": len(csv_files),
            "event_count": len(event_records),
            "event_id_min": min(all_event_ids),
            "event_id_max": max(all_event_ids),
            "anomaly_event_count": anomaly_count,
            "normal_event_count": normal_count,
            "source_asset_count": len(source_assets),
            "time_point_count": sum(int(event["row_count"]) for event in event_records),
            "train_time_point_count": sum(
                int(event["split_counts"].get("train", 0)) for event in event_records
            ),
            "prediction_time_point_count": sum(
                int(event["split_counts"].get("prediction", 0)) for event in event_records
            ),
        },
        "csv_files": csv_files,
        "farms": farm_records,
        "events": event_records,
    }
    manifest_sha256 = _sha256_json(payload)
    return {**payload, "manifest_sha256": manifest_sha256}


def _git_commit(repository_root: Path) -> str:
    git_marker = repository_root / ".git"
    if git_marker.is_dir():
        git_dir = git_marker
    elif git_marker.is_file():
        marker = git_marker.read_text(encoding="utf-8").strip()
        if not marker.startswith("gitdir: "):
            raise CareContractError("repository .git file has an invalid gitdir marker")
        candidate = Path(marker.removeprefix("gitdir: ").strip())
        git_dir = candidate if candidate.is_absolute() else (repository_root / candidate).resolve()
    else:
        raise CareContractError("repository has no .git metadata")

    head = (git_dir / "HEAD").read_text(encoding="ascii").strip()
    if not head.startswith("ref: "):
        return _validated_git_object_id(head)

    ref_name = head.removeprefix("ref: ").strip()
    ref_path = Path(*ref_name.split("/"))
    if not ref_name.startswith("refs/") or ".." in ref_path.parts:
        raise CareContractError("repository HEAD contains an invalid ref")

    lookup_roots = [git_dir]
    common_dir_marker = git_dir / "commondir"
    if common_dir_marker.is_file():
        common_candidate = Path(common_dir_marker.read_text(encoding="utf-8").strip())
        common_dir = (
            common_candidate
            if common_candidate.is_absolute()
            else (git_dir / common_candidate).resolve()
        )
        lookup_roots.append(common_dir)

    for lookup_root in lookup_roots:
        loose_ref = lookup_root / ref_path
        if loose_ref.is_file():
            return _validated_git_object_id(loose_ref.read_text(encoding="ascii").strip())
        packed_refs = lookup_root / "packed-refs"
        if packed_refs.is_file():
            for line in packed_refs.read_text(encoding="ascii").splitlines():
                if not line or line.startswith(("#", "^")):
                    continue
                object_id, separator, packed_ref_name = line.partition(" ")
                if separator and packed_ref_name == ref_name:
                    return _validated_git_object_id(object_id)
    raise CareContractError(f"repository HEAD ref is unresolved: {ref_name}")


def _validated_git_object_id(value: str) -> str:
    if len(value) not in {40, 64} or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise CareContractError("repository HEAD is not a valid Git object ID")
    return value


def _write_manifest(output_path: Path, manifest: Mapping[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


def write_care_contract(
    dataset_root: Path,
    zip_path: Path,
    output_path: Path,
    *,
    expectations: CareDatasetExpectations = CARE_V6_EXPECTATIONS,
    explicit_aliases: Mapping[str, Mapping[str, tuple[str, str]]] = DEFAULT_EXPLICIT_ALIASES,
    tool_git_commit: str = "unknown",
    dependency_lock_sha256: str = "unknown",
) -> dict[str, Any]:
    _ensure_read_only_source_output(dataset_root, zip_path, output_path)
    manifest = build_care_contract(
        dataset_root,
        zip_path,
        expectations=expectations,
        explicit_aliases=explicit_aliases,
        tool_git_commit=tool_git_commit,
        dependency_lock_sha256=dependency_lock_sha256,
    )
    _write_manifest(output_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the fail-closed CARE v6 data contract")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--zip-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[5]
    lock_path = repository_root / "backend" / "uv.lock"
    manifest = write_care_contract(
        args.dataset_root,
        args.zip_path,
        args.output,
        tool_git_commit=_git_commit(repository_root),
        dependency_lock_sha256=hashlib.sha256(lock_path.read_bytes()).hexdigest(),
    )
    summary = manifest["summary"]
    print(
        "CARE v6 contract generated: "
        f"{summary['csv_file_count']} CSV, {summary['event_count']} events, "
        f"{summary['time_point_count']} time points, sha256={manifest['manifest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
