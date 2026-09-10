from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path

import pytest

from windops_backend.benchmarks.care.contract import CareContractError
from windops_backend.benchmarks.care.quality import (
    QUALITY_RULE_VERSION,
    audit_event_quality,
    build_quality_contract,
    evaluate_status_point,
    is_anonymized_scaled_power,
    normalize_unit,
)


def _signed_manifest(event_path: Path, mappings: list[dict]) -> dict:
    raw = event_path.read_bytes()
    row_count = len(raw.splitlines()) - 1
    unsigned = {
        "manifest_schema_version": "care-v6-manifest-v1",
        "dataset_id": "care",
        "dataset_version": "v6",
        "farms": [
            {
                "farm": "B",
                "column_mappings": mappings,
            }
        ],
        "events": [
            {
                "farm": "B",
                "event_id": 7,
                "source_asset_id": "14",
                "relative_path": "Wind Farm B/datasets/7.csv",
                "row_count": row_count,
                "file_sha256": hashlib.sha256(raw).hexdigest(),
            }
        ],
    }
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return {**unsigned, "manifest_sha256": hashlib.sha256(canonical).hexdigest()}


def _mapping(
    column: str,
    base: str,
    statistic: str,
    *,
    description: str = "Signal",
    unit: str = "1",
    is_angle: bool = False,
    is_counter: bool = False,
) -> dict:
    return {
        "source_column": column,
        "base_sensor": base,
        "statistic": statistic,
        "description": description,
        "source_unit": unit,
        "is_angle": is_angle,
        "is_counter": is_counter,
    }


def _write_quality_fixture(root: Path) -> tuple[Path, list[dict]]:
    path = root / "Wind Farm B" / "datasets" / "7.csv"
    path.parent.mkdir(parents=True)
    mappings = [
        _mapping("sensor_0_avg", "sensor_0", "average", unit="�C"),
        _mapping(
            "power_1_avg",
            "power_1",
            "average",
            description="Active power",
            unit="kW",
        ),
        _mapping("sensor_2_avg", "sensor_2", "average", unit="deg", is_angle=True),
        _mapping("sensor_3_avg", "sensor_3", "average", is_counter=True),
        _mapping("sensor_4_min", "sensor_4", "minimum"),
        _mapping("sensor_4_avg", "sensor_4", "average"),
        _mapping("sensor_4_max", "sensor_4", "maximum"),
        _mapping("sensor_4_std", "sensor_4", "std_dev"),
    ]
    header = [
        "time_stamp",
        "asset_id",
        "id",
        "train_test",
        "status_type_id",
        *[mapping["source_column"] for mapping in mappings],
    ]
    rows = [
        ["2024-01-01 00:00:00", 14, 0, "train", 1, 0, 10, 0, 10, 1, 2, 3, 1],
        ["2024-01-01 00:10:00", 14, 1, "train", 9, 0, 10, 0, 11, 1, 2, 3, 1],
        ["2024-01-01 00:20:00", 14, 2, "prediction", 9, 0, 10, 0, 1, 3, 2, 1, -1],
        ["2024-01-01 00:30:00", 14, 3, "prediction", 1, "", 0, "nan", 2, 1, 2, 3, 1],
        ["2024-01-01 00:40:00", 14, 4, "prediction", 1, "inf", 0, "bad", 3, 1, 2, 3, 1],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path, mappings


def test_unit_repairs_empty_units_and_scaled_power_are_explicit() -> None:
    assert normalize_unit("�C").normalized_unit == "°C"
    assert normalize_unit("�").normalized_unit == "°"
    assert normalize_unit("Celsius").normalized_unit == "°C"
    assert normalize_unit("deg").normalized_unit == "°"
    assert normalize_unit("").normalized_unit == "unknown"
    assert normalize_unit("", dimensionless_confirmed=True).normalized_unit == "1"
    assert is_anonymized_scaled_power(
        _mapping("power_1_avg", "power_1", "average", description="Active power", unit="kW")
    )
    assert not is_anonymized_scaled_power(
        _mapping(
            "sensor_1_avg",
            "sensor_1",
            "average",
            description="Total active power",
            unit="kWh",
            is_counter=True,
        )
    )
    assert not is_anonymized_scaled_power(
        _mapping(
            "sensor_2_avg",
            "sensor_2",
            "average",
            description="24VDC power pack",
            unit="V",
        )
    )


def test_status_rules_preserve_a_prediction_and_short_bc_disagreements() -> None:
    trusted = ["1"]
    assert evaluate_status_point(
        farm="A", split="prediction", status_id="9", trusted_status_ids=trusted
    ).model_usable
    assert not evaluate_status_point(
        farm="A", split="train", status_id="9", trusted_status_ids=trusted
    ).model_usable
    assert evaluate_status_point(
        farm="B",
        split="prediction",
        status_id="9",
        trusted_status_ids=trusted,
        disagreement_run_length=2,
        corroborated_by_signal=True,
    ).model_usable
    assert not evaluate_status_point(
        farm="C",
        split="prediction",
        status_id="9",
        trusted_status_ids=trusted,
        disagreement_run_length=3,
        corroborated_by_signal=True,
    ).model_usable
    with pytest.raises(CareContractError, match="explicit trusted-status allowlist"):
        evaluate_status_point(farm="B", split="train", status_id="1", trusted_status_ids=[])


def test_quality_contract_and_event_audit_preserve_raw_values_and_masks(tmp_path: Path) -> None:
    root = tmp_path / "CARE_To_Compare"
    event_path, mappings = _write_quality_fixture(root)
    manifest = _signed_manifest(event_path, mappings)
    contract = build_quality_contract(manifest)

    assert contract["raw_value_policy"].startswith("preserve")
    assert contract["zero_value_policy"]["global_zero_to_null"] is False
    assert contract["time_semantics"]["cross_event_ordering_allowed"] is False
    assert contract["summary"]["default_enabled_avg_count"] == 5
    assert contract["summary"]["default_disabled_non_avg_count"] == 3
    assert contract == build_quality_contract(manifest)
    features = {item["source_column"]: item for item in contract["farms"][0]["features"]}
    assert features["sensor_2_avg"]["normalized_unit"] == "°"
    assert features["sensor_2_avg"]["value_domain"] == "circular"
    assert features["sensor_3_avg"]["counter_policy"] == "detect-regression-reset-and-wrap"
    before = event_path.read_bytes()
    first = audit_event_quality(
        manifest,
        contract,
        root,
        7,
        zero_run_min_length=3,
    )
    second = audit_event_quality(
        manifest,
        contract,
        root,
        7,
        zero_run_min_length=3,
    )
    assert first == second
    assert event_path.read_bytes() == before
    assert first["raw_values_modified"] is False
    assert first["timestamp_semantics"] == "independently-shifted-anonymized"
    assert first["split_counts"] == {"prediction": 3, "train": 2}
    summaries = {item["source_column"]: item for item in first["feature_summaries"]}
    temperature = summaries["sensor_0_avg"]
    assert temperature["zero_count"] == 3
    assert temperature["longest_consecutive_zero_run"] == 3
    assert temperature["null_count"] == 1
    assert temperature["positive_infinity_count"] == 1
    assert summaries["sensor_2_avg"]["nan_count"] == 1
    assert summaries["sensor_2_avg"]["parse_failure_count"] == 1
    assert summaries["sensor_3_avg"]["counter_regression_or_reset_count"] == 1
    assert summaries["sensor_4_std"]["std_negative_count"] == 1
    assert summaries["sensor_4_avg"]["min_avg_max_violation_count"] == 1
    mask = next(
        item for item in first["quality_mask_ranges"] if item["source_column"] == "sensor_0_avg"
    )
    assert mask["source_row_id_start"] == 0
    assert mask["source_row_id_end"] == 2
    assert mask["confidence"] == 0.95
    assert mask["raw_value_preserved"] is True
    assert mask["rule_version"] == QUALITY_RULE_VERSION

    tampered = copy.deepcopy(contract)
    tampered["zero_value_policy"]["global_zero_to_null"] = True
    with pytest.raises(CareContractError, match="quality contract hash mismatch"):
        audit_event_quality(manifest, tampered, root, 7, zero_run_min_length=3)


def test_a_farm_zero_runs_are_summarized_without_bc_missing_mask(tmp_path: Path) -> None:
    root = tmp_path / "CARE_To_Compare"
    event_path, mappings = _write_quality_fixture(root)
    manifest = _signed_manifest(event_path, mappings)
    manifest["events"][0]["farm"] = "A"
    manifest["farms"][0]["farm"] = "A"
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    manifest["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    a_path = root / "Wind Farm A" / "datasets" / "7.csv"
    a_path.parent.mkdir(parents=True)
    a_path.write_bytes(event_path.read_bytes())
    manifest["events"][0]["relative_path"] = "Wind Farm A/datasets/7.csv"
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    contract = build_quality_contract(manifest)
    report = audit_event_quality(manifest, contract, root, 7, zero_run_min_length=3)
    assert report["quality_mask_ranges"] == []
    summaries = {item["source_column"]: item for item in report["feature_summaries"]}
    assert summaries["sensor_0_avg"]["longest_consecutive_zero_run"] == 3
