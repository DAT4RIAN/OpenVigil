from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from windops_backend.benchmarks.care.contract import (
    A_BARE_AVERAGE_ALIASES,
    CareContractError,
    CareDatasetExpectations,
    FeatureDefinition,
    build_care_contract,
    build_column_mappings,
    normalize_statistics_types,
    write_care_contract,
)


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _fixture_expectations(zip_path: Path) -> CareDatasetExpectations:
    raw = zip_path.read_bytes()
    return CareDatasetExpectations(
        farms=("A", "B", "C"),
        csv_count=9,
        event_ids=(0, 1, 2),
        signal_counts=(("A", 9), ("B", 4), ("C", 2)),
        zip_size_bytes=len(raw),
        zip_md5=hashlib.md5(raw, usedforsecurity=False).hexdigest(),
        zip_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _create_fixture(tmp_path: Path) -> tuple[Path, Path, CareDatasetExpectations]:
    root = tmp_path / "CARE_To_Compare"
    zip_path = tmp_path / "CARE_To_Compare.zip"
    zip_path.write_bytes(b"fixed-care-v6-contract-fixture")
    feature_rows = {
        "A": [
            ["sensor_0", "average", "Temperature", "�C", "False", "False"],
            *[
                [
                    f"sensor_{index}",
                    "average",
                    "Explicit bare average",
                    "",
                    "False",
                    "False",
                ]
                for index in range(44, 52)
            ],
        ],
        "B": [
            [
                "sensor_0",
                "maximum,minimum,average,std_dev",
                "Counter",
                "kWh",
                "False",
                "True",
            ]
        ],
        "C": [["power_2", "maximum,average", "Scaled power", "kW", "False", "False"]],
    }
    signals = {
        "A": ["sensor_0_avg", *[f"sensor_{index}" for index in range(44, 52)]],
        "B": ["sensor_0_avg", "sensor_0_max", "sensor_0_min", "sensor_0_std"],
        "C": ["power_2_avg", "power_2_max"],
    }
    for event_id, farm in enumerate(("A", "B", "C")):
        farm_root = root / f"Wind Farm {farm}"
        _write_csv(
            farm_root / "feature_description.csv",
            [
                "sensor_name",
                "statistics_type",
                "description",
                "unit",
                "is_angle",
                "is_counter",
            ],
            feature_rows[farm],
        )
        asset_column = "asset" if farm == "A" else "asset_id"
        _write_csv(
            farm_root / "event_info.csv",
            [
                asset_column,
                "event_id",
                "event_label",
                "event_start",
                "event_start_id",
                "event_end",
                "event_end_id",
                "event_description",
            ],
            [
                [
                    str(event_id + 10),
                    event_id,
                    "anomaly" if event_id != 1 else "normal",
                    "t0",
                    1,
                    "t1",
                    2,
                    "fixture",
                ]
            ],
        )
        values = [str(index + 1) for index in range(len(signals[farm]))]
        _write_csv(
            farm_root / "datasets" / f"{event_id}.csv",
            ["time_stamp", "asset_id", "id", "train_test", "status_type_id", *signals[farm]],
            [
                ["2024-01-01 00:00:00", str(event_id + 10), 0, "train", 1, *values],
                ["2024-01-01 00:10:00", str(event_id + 10), 1, "train", 1, *values],
                ["2024-01-01 00:20:00", str(event_id + 10), 2, "prediction", 1, *values],
            ],
        )
    return root, zip_path, _fixture_expectations(zip_path)


def test_statistics_sets_are_deduplicated_and_stably_normalized() -> None:
    assert normalize_statistics_types("maximum,minimum,average,std_dev,average") == (
        "average",
        "maximum",
        "minimum",
        "std_dev",
    )
    with pytest.raises(CareContractError, match="unsupported statistics_type"):
        normalize_statistics_types("average,median")


def test_fixed_a_b_c_fixture_builds_a_deterministic_complete_contract(tmp_path: Path) -> None:
    root, zip_path, expectations = _create_fixture(tmp_path)
    first = build_care_contract(
        root,
        zip_path,
        expectations=expectations,
        tool_git_commit="a" * 40,
        dependency_lock_sha256="b" * 64,
    )
    second = build_care_contract(
        root,
        zip_path,
        expectations=expectations,
        tool_git_commit="a" * 40,
        dependency_lock_sha256="b" * 64,
    )

    assert first == second
    unsigned = {key: value for key, value in first.items() if key != "manifest_sha256"}
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert first["manifest_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert first["summary"] == {
        "csv_file_count": 9,
        "event_count": 3,
        "event_id_min": 0,
        "event_id_max": 2,
        "anomaly_event_count": 2,
        "normal_event_count": 1,
        "source_asset_count": 3,
        "time_point_count": 9,
        "train_time_point_count": 6,
        "prediction_time_point_count": 3,
    }
    farms = {record["farm"]: record for record in first["farms"]}
    assert [farm["signal_column_count"] for farm in farms.values()] == [9, 4, 2]
    a_mapping = {row["source_column"]: row for row in farms["A"]["column_mappings"]}
    assert a_mapping["sensor_44"]["statistic"] == "average"
    assert a_mapping["sensor_44"]["mapping_source"] == "explicit-versioned-alias"
    assert [event["event_id"] for event in first["events"]] == [0, 1, 2]
    assert all(event["source_row_id_min"] == 0 for event in first["events"])
    assert all(event["source_row_id_max"] == 2 for event in first["events"])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda columns: [*columns, "unknown_avg"], "unknown signal columns"),
        (lambda columns: columns[:-1], "missing signal columns"),
        (lambda columns: [columns[0], *columns], "duplicate signal columns"),
    ],
)
def test_mapping_fails_closed_for_unknown_missing_and_duplicate_columns(
    mutate,
    message: str,
) -> None:
    features = [
        FeatureDefinition("sensor_0", ("average",), "Sensor", "1", False, False),
        FeatureDefinition("sensor_44", ("average",), "Bare", "1", False, False),
    ]
    with pytest.raises(CareContractError, match=message):
        build_column_mappings(
            farm="A",
            features=features,
            signal_columns=mutate(["sensor_0_avg", "sensor_44"]),
            explicit_aliases={"sensor_44": A_BARE_AVERAGE_ALIASES["sensor_44"]},
        )


def test_mapping_fails_closed_for_ambiguous_and_duplicate_metadata() -> None:
    features = [
        FeatureDefinition("sensor_0", ("average",), "Sensor", "1", False, False),
        FeatureDefinition("sensor_44", ("average",), "Bare", "1", False, False),
    ]
    aliases = {"sensor_0_avg": ("sensor_44", "average")}
    with pytest.raises(CareContractError, match="ambiguous column mappings"):
        build_column_mappings(
            farm="A",
            features=features,
            signal_columns=["sensor_0_avg"],
            explicit_aliases=aliases,
        )

    duplicate = [features[0], features[0]]
    with pytest.raises(CareContractError, match="duplicate feature/statistic"):
        build_column_mappings(
            farm="A",
            features=duplicate,
            signal_columns=["sensor_0_avg"],
        )


def test_event_filename_and_metadata_are_bidirectionally_validated(tmp_path: Path) -> None:
    root, zip_path, expectations = _create_fixture(tmp_path)
    (root / "Wind Farm B" / "datasets" / "1.csv").rename(
        root / "Wind Farm B" / "datasets" / "9.csv"
    )
    with pytest.raises(CareContractError, match="has no event_info.csv row"):
        build_care_contract(root, zip_path, expectations=expectations)


def test_event_interval_and_asset_must_match_the_real_file(tmp_path: Path) -> None:
    root, zip_path, expectations = _create_fixture(tmp_path)
    event_info = root / "Wind Farm C" / "event_info.csv"
    text = event_info.read_text(encoding="utf-8")
    event_info.write_text(text.replace(";1;t1;2;", ";1;t1;99;"), encoding="utf-8")
    with pytest.raises(CareContractError, match="truth interval is outside"):
        build_care_contract(root, zip_path, expectations=expectations)


def test_zip_identity_and_read_only_output_boundary_fail_closed(tmp_path: Path) -> None:
    root, zip_path, expectations = _create_fixture(tmp_path)
    mismatched = CareDatasetExpectations(
        farms=expectations.farms,
        csv_count=expectations.csv_count,
        event_ids=expectations.event_ids,
        signal_counts=expectations.signal_counts,
        zip_sha256="0" * 64,
    )
    with pytest.raises(CareContractError, match="CARE ZIP sha256 mismatch"):
        build_care_contract(root, zip_path, expectations=mismatched)

    with pytest.raises(CareContractError, match="must not modify the read-only CARE source"):
        write_care_contract(
            root,
            zip_path,
            root / "derived-manifest.json",
            expectations=expectations,
        )
