from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from windops_backend.operations.care_postgres_evidence import (
    EXPECTED_MIGRATION_HEAD,
    EXPECTED_TESTS,
    CarePostgresEvidenceError,
    verify_care_postgres_evidence,
)


def _write_junit(
    path: Path,
    tests: set[str],
    properties: dict[str, str],
    *,
    skipped: int = 0,
) -> None:
    suites = ET.Element("testsuites", {"name": "pytest tests"})
    suite = ET.SubElement(
        suites,
        "testsuite",
        {
            "name": "pytest",
            "tests": str(len(tests)),
            "failures": "0",
            "errors": "0",
            "skipped": str(skipped),
        },
    )
    property_nodes = ET.SubElement(suite, "properties")
    for name, value in properties.items():
        ET.SubElement(property_nodes, "property", {"name": name, "value": value})
    for name in sorted(tests):
        ET.SubElement(suite, "testcase", {"name": name})
    ET.ElementTree(suites).write(path, encoding="utf-8", xml_declaration=True)


def _valid_evidence(tmp_path: Path) -> dict[str, Path]:
    source = "a" * 64
    quality = "b" * 64
    minimal = "c" * 64
    offline_identity = "d" * 64
    full_import = "e" * 64
    full_evaluation = "f" * 64
    approved = "1" * 64
    offline = tmp_path / "offline.xml"
    full_scale = tmp_path / "full-scale.xml"
    vertical = tmp_path / "vertical.xml"
    closure = tmp_path / "closure.json"
    _write_junit(
        offline,
        EXPECTED_TESTS["offline"],
        {
            "care.offline.source_manifest_sha256": source,
            "care.offline.quality_contract_sha256": quality,
            "care.offline.import_identity_sha256": minimal,
            "care.offline.evaluation_identity_sha256": offline_identity,
            "care.offline.approved_root_sha256": approved,
        },
    )
    _write_junit(
        full_scale,
        EXPECTED_TESTS["full_scale"],
        {
            "care.full_scale.query_p95_ms": "499.999",
            "care.full_scale.query_sql_count_max": "10",
            "care.full_scale.query_sql_p95_ms": "9.000",
            **{
                f"care.full_scale.query_{index}_path": f"/benchmark-path-{index}"
                for index in range(5)
            },
            **{
                f"care.full_scale.query_{index}_sql_count_max": str(10 - index)
                for index in range(5)
            },
            **{f"care.full_scale.query_{index}_sql_p95_ms": str(9 - index) for index in range(5)},
            "care.full_scale.source_manifest_sha256": source,
            "care.full_scale.quality_contract_sha256": quality,
            "care.full_scale.import_manifest_sha256": full_import,
            "care.full_scale.evaluation_manifest_sha256": full_evaluation,
            "care.full_scale.approved_root_sha256": approved,
        },
    )
    _write_junit(
        vertical,
        EXPECTED_TESTS["vertical"],
        {
            "care.contract_sha256": source,
            "care.import_identity_sha256": minimal,
            "care.evaluation_identity_sha256": offline_identity,
            "care.replay_write_rows_per_second": "50.001",
            "care.replay_write_sql_statements": "14,13,13,13,13,13,13",
            "care.replay_write_sql_seconds": ",".join(["0.010000"] * 7),
            "care.replay_write_max_batch_sql_statements": "14",
            "care.replay_write_db_elapsed_seconds": "0.070000",
            "care.stage_upgrade.full_import_manifest_sha256": full_import,
            "care.stage_upgrade.full_evaluation_manifest_sha256": full_evaluation,
            "care.stage_upgrade.approved_root_sha256": approved,
            "care.stage_upgrade.quality_parent_count": "95",
            "care.stage_upgrade.quality_artifact_count": "97",
            "care.stage_upgrade.concurrent_create_exact": "true",
            "care.stage_upgrade.concurrent_replay_exact": "true",
        },
    )
    closure.write_text(
        json.dumps(
            {
                "gate": "care_benchmark_dependency_closure",
                "status": "passed",
                "uv_lock_sha256": "2" * 64,
                "requirements_lock_sha256": "3" * 64,
            }
        ),
        encoding="utf-8",
    )
    return {
        "offline_junit": offline,
        "full_scale_junit": full_scale,
        "vertical_junit": vertical,
        "dependency_closure": closure,
    }


def test_care_postgres_evidence_binds_exact_tests_roots_performance_and_runtime(
    tmp_path: Path,
) -> None:
    report = verify_care_postgres_evidence(
        **_valid_evidence(tmp_path),
        expected_commit_sha="4" * 40,
        postgres_image=f"timescale/test@sha256:{'5' * 64}",
        migration_head=EXPECTED_MIGRATION_HEAD,
    )

    assert report["status"] == "passed"
    assert report["tests"] | {"junit_sha256": None} == {
        "expected": 4,
        "actual": 4,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "junit_sha256": None,
    }
    assert report["performance"] == {
        "replay_rows_per_second": 50.001,
        "minimum_replay_rows_per_second": 50.0,
        "catalog_query_p95_ms": 499.999,
        "maximum_catalog_query_p95_ms": 500.0,
        "replay_sql_statements_per_batch": [14, 13, 13, 13, 13, 13, 13],
        "maximum_replay_sql_statements_per_batch": 40,
        "replay_database_elapsed_seconds": 0.07,
        "catalog_sql_statement_count_max": 10,
        "maximum_catalog_sql_statements_per_request": 12,
        "catalog_sql_p95_ms": 9.0,
        "catalog_paths": [f"/benchmark-path-{index}" for index in range(5)],
    }
    assert len(report["evidence_root_sha256"]) == 64


def test_care_postgres_evidence_rejects_skip_and_performance_regression(
    tmp_path: Path,
) -> None:
    paths = _valid_evidence(tmp_path)
    _write_junit(paths["offline_junit"], EXPECTED_TESTS["offline"], {}, skipped=1)
    with pytest.raises(CarePostgresEvidenceError, match="zero failures, errors, and skips"):
        verify_care_postgres_evidence(
            **paths,
            expected_commit_sha="4" * 40,
            postgres_image=f"timescale/test@sha256:{'5' * 64}",
            migration_head=EXPECTED_MIGRATION_HEAD,
        )

    paths = _valid_evidence(tmp_path)
    full_scale = paths["full_scale_junit"]
    text = full_scale.read_text(encoding="utf-8").replace("499.999", "500.001")
    full_scale.write_text(text, encoding="utf-8")
    with pytest.raises(CarePostgresEvidenceError, match="exceeds"):
        verify_care_postgres_evidence(
            **paths,
            expected_commit_sha="4" * 40,
            postgres_image=f"timescale/test@sha256:{'5' * 64}",
            migration_head=EXPECTED_MIGRATION_HEAD,
        )

    paths = _valid_evidence(tmp_path)
    vertical = paths["vertical_junit"]
    text = vertical.read_text(encoding="utf-8").replace(
        'name="care.replay_write_max_batch_sql_statements" value="14"',
        'name="care.replay_write_max_batch_sql_statements" value="41"',
    )
    vertical.write_text(text, encoding="utf-8")
    with pytest.raises(CarePostgresEvidenceError, match="aggregate is inconsistent"):
        verify_care_postgres_evidence(
            **paths,
            expected_commit_sha="4" * 40,
            postgres_image=f"timescale/test@sha256:{'5' * 64}",
            migration_head=EXPECTED_MIGRATION_HEAD,
        )
