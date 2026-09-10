from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXPECTED_MIGRATION_HEAD = "0028_read_audit_pipeline"
MIN_REPLAY_ROWS_PER_SECOND = 50.0
MAX_QUERY_P95_MS = 500.0
MAX_REPLAY_SQL_STATEMENTS_PER_BATCH = 40
MAX_CATALOG_SQL_STATEMENTS_PER_REQUEST = 12
CATALOG_PROFILE_PATH_COUNT = 5
EXPECTED_TESTS = {
    "offline": {
        "test_postgres_offline_evaluation_registration_is_exactly_idempotent",
    },
    "full_scale": {
        "test_real_postgres_full_scale_registration_catalog_and_query_budget",
    },
    "vertical": {
        "test_real_postgres_care_replay_alert_mission_diagnosis_vertical_slice",
        "test_same_database_stage_upgrade_is_append_only_and_concurrently_idempotent",
    },
}


class CarePostgresEvidenceError(RuntimeError):
    """Raised when CARE PostgreSQL release evidence is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class JunitEvidence:
    path: Path
    tests: int
    properties: dict[str, str]
    sha256: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CarePostgresEvidenceError(f"evidence JSON is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise CarePostgresEvidenceError(f"evidence JSON must be an object: {path}")
    return value


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def read_junit(path: Path, *, expected_tests: set[str]) -> JunitEvidence:
    path = path.resolve(strict=True)
    try:
        root = ET.parse(path).getroot()  # nosec B314
    except (OSError, ET.ParseError) as exc:
        raise CarePostgresEvidenceError(f"JUnit is unreadable: {path}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise CarePostgresEvidenceError(f"JUnit has no testsuite: {path}")
    counts = {
        name: sum(int(suite.get(name, "0")) for suite in suites)
        for name in ("tests", "failures", "errors", "skipped")
    }
    test_names = {case.get("name", "") for case in root.iter("testcase")}
    if counts["tests"] != len(expected_tests) or test_names != expected_tests:
        raise CarePostgresEvidenceError(
            f"JUnit collected unexpected tests: expected {sorted(expected_tests)}, "
            f"got {sorted(test_names)}"
        )
    if any(counts[name] for name in ("failures", "errors", "skipped")):
        raise CarePostgresEvidenceError(
            "JUnit must have zero failures, errors, and skips: "
            f"failures={counts['failures']} errors={counts['errors']} "
            f"skipped={counts['skipped']}"
        )
    properties: dict[str, str] = {}
    for item in root.iter("property"):
        name = item.get("name")
        value = item.get("value")
        if not name or value is None or name in properties:
            raise CarePostgresEvidenceError("JUnit properties must have unique names and values")
        properties[name] = value
    return JunitEvidence(path, counts["tests"], properties, _sha256(path))


def _required(properties: dict[str, str], name: str) -> str:
    value = properties.get(name)
    if value is None or value == "":
        raise CarePostgresEvidenceError(f"required JUnit property is missing: {name}")
    return value


def _metric(properties: dict[str, str], name: str) -> float:
    try:
        value = float(_required(properties, name))
    except ValueError as exc:
        raise CarePostgresEvidenceError(f"JUnit property is not numeric: {name}") from exc
    if not math.isfinite(value):
        raise CarePostgresEvidenceError(f"JUnit property is not finite: {name}")
    return value


def _integer_metric(properties: dict[str, str], name: str) -> int:
    raw = _required(properties, name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise CarePostgresEvidenceError(f"JUnit property is not an integer: {name}") from exc
    if value < 0:
        raise CarePostgresEvidenceError(f"JUnit property cannot be negative: {name}")
    return value


def _metric_series(properties: dict[str, str], name: str, *, expected: int) -> list[float]:
    raw_values = _required(properties, name).split(",")
    if len(raw_values) != expected:
        raise CarePostgresEvidenceError(
            f"JUnit property must contain {expected} measurements: {name}"
        )
    try:
        values = [float(value) for value in raw_values]
    except ValueError as exc:
        raise CarePostgresEvidenceError(
            f"JUnit property contains a non-numeric value: {name}"
        ) from exc
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise CarePostgresEvidenceError(f"JUnit property contains an invalid measurement: {name}")
    return values


def _integer_series(properties: dict[str, str], name: str, *, expected: int) -> list[int]:
    raw_values = _required(properties, name).split(",")
    if len(raw_values) != expected:
        raise CarePostgresEvidenceError(
            f"JUnit property must contain {expected} measurements: {name}"
        )
    try:
        values = [int(value) for value in raw_values]
    except ValueError as exc:
        raise CarePostgresEvidenceError(f"JUnit property contains a non-integer: {name}") from exc
    if any(value < 0 for value in values):
        raise CarePostgresEvidenceError(f"JUnit property contains an invalid measurement: {name}")
    return values


def verify_care_postgres_evidence(
    *,
    offline_junit: Path,
    full_scale_junit: Path,
    vertical_junit: Path,
    dependency_closure: Path,
    expected_commit_sha: str,
    postgres_image: str,
    migration_head: str,
) -> dict[str, Any]:
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected_commit_sha) is None:
        raise CarePostgresEvidenceError("expected commit must be a full lowercase Git SHA")
    if re.fullmatch(
        r"[^\s@]+@sha256:[0-9a-f]{64}", postgres_image
    ) is None or postgres_image.endswith("sha256:" + "0" * 64):
        raise CarePostgresEvidenceError("PostgreSQL test image must use a real immutable digest")
    if migration_head != EXPECTED_MIGRATION_HEAD:
        raise CarePostgresEvidenceError(
            f"migration head is {migration_head}, expected {EXPECTED_MIGRATION_HEAD}"
        )

    offline = read_junit(offline_junit, expected_tests=EXPECTED_TESTS["offline"])
    full_scale = read_junit(full_scale_junit, expected_tests=EXPECTED_TESTS["full_scale"])
    vertical = read_junit(vertical_junit, expected_tests=EXPECTED_TESTS["vertical"])
    properties = {
        "offline": offline.properties,
        "full_scale": full_scale.properties,
        "vertical": vertical.properties,
    }

    identity_groups = {
        "source_manifest_sha256": (
            _required(offline.properties, "care.offline.source_manifest_sha256"),
            _required(full_scale.properties, "care.full_scale.source_manifest_sha256"),
            _required(vertical.properties, "care.contract_sha256"),
        ),
        "quality_contract_sha256": (
            _required(offline.properties, "care.offline.quality_contract_sha256"),
            _required(full_scale.properties, "care.full_scale.quality_contract_sha256"),
        ),
        "minimal_import_identity_sha256": (
            _required(offline.properties, "care.offline.import_identity_sha256"),
            _required(vertical.properties, "care.import_identity_sha256"),
        ),
        "offline_evaluation_identity_sha256": (
            _required(offline.properties, "care.offline.evaluation_identity_sha256"),
            _required(vertical.properties, "care.evaluation_identity_sha256"),
        ),
        "full_import_manifest_sha256": (
            _required(full_scale.properties, "care.full_scale.import_manifest_sha256"),
            _required(vertical.properties, "care.stage_upgrade.full_import_manifest_sha256"),
        ),
        "full_evaluation_manifest_sha256": (
            _required(full_scale.properties, "care.full_scale.evaluation_manifest_sha256"),
            _required(vertical.properties, "care.stage_upgrade.full_evaluation_manifest_sha256"),
        ),
        "approved_root_sha256": (
            _required(offline.properties, "care.offline.approved_root_sha256"),
            _required(full_scale.properties, "care.full_scale.approved_root_sha256"),
            _required(vertical.properties, "care.stage_upgrade.approved_root_sha256"),
        ),
    }
    identities: dict[str, str] = {}
    for name, values in identity_groups.items():
        if len(set(values)) != 1 or not _is_sha256(values[0]):
            raise CarePostgresEvidenceError(f"CARE evidence identity mismatch: {name}")
        identities[name] = values[0]

    replay_rows_per_second = _metric(vertical.properties, "care.replay_write_rows_per_second")
    query_p95_ms = _metric(full_scale.properties, "care.full_scale.query_p95_ms")
    replay_sql_counts = _integer_series(
        vertical.properties,
        "care.replay_write_sql_statements",
        expected=7,
    )
    replay_sql_seconds = _metric_series(
        vertical.properties,
        "care.replay_write_sql_seconds",
        expected=7,
    )
    replay_max_sql_count = _integer_metric(
        vertical.properties,
        "care.replay_write_max_batch_sql_statements",
    )
    replay_db_elapsed_seconds = _metric(
        vertical.properties,
        "care.replay_write_db_elapsed_seconds",
    )
    catalog_sql_count_max = _integer_metric(
        full_scale.properties,
        "care.full_scale.query_sql_count_max",
    )
    catalog_sql_p95_ms = _metric(
        full_scale.properties,
        "care.full_scale.query_sql_p95_ms",
    )
    catalog_paths: list[str] = []
    catalog_path_sql_counts: list[int] = []
    catalog_path_sql_p95_ms: list[float] = []
    for index in range(CATALOG_PROFILE_PATH_COUNT):
        catalog_paths.append(
            _required(full_scale.properties, f"care.full_scale.query_{index}_path")
        )
        catalog_path_sql_counts.append(
            _integer_metric(
                full_scale.properties,
                f"care.full_scale.query_{index}_sql_count_max",
            )
        )
        catalog_path_sql_p95_ms.append(
            _metric(
                full_scale.properties,
                f"care.full_scale.query_{index}_sql_p95_ms",
            )
        )
    if replay_rows_per_second < MIN_REPLAY_ROWS_PER_SECOND:
        raise CarePostgresEvidenceError(
            f"CARE replay throughput {replay_rows_per_second:.3f} is below "
            f"{MIN_REPLAY_ROWS_PER_SECOND:.3f} rows/s"
        )
    if query_p95_ms > MAX_QUERY_P95_MS:
        raise CarePostgresEvidenceError(
            f"CARE catalog p95 {query_p95_ms:.3f} ms exceeds {MAX_QUERY_P95_MS:.3f} ms"
        )
    if len(set(catalog_paths)) != CATALOG_PROFILE_PATH_COUNT:
        raise CarePostgresEvidenceError("CARE catalog SQL profile paths must be unique")
    if any(count > MAX_CATALOG_SQL_STATEMENTS_PER_REQUEST for count in catalog_path_sql_counts):
        raise CarePostgresEvidenceError("CARE catalog SQL statement budget was exceeded")
    if catalog_sql_count_max != max(catalog_path_sql_counts):
        raise CarePostgresEvidenceError("CARE catalog SQL count aggregate is inconsistent")
    if not math.isclose(catalog_sql_p95_ms, max(catalog_path_sql_p95_ms), abs_tol=0.001):
        raise CarePostgresEvidenceError("CARE catalog SQL p95 aggregate is inconsistent")
    if catalog_sql_p95_ms > query_p95_ms:
        raise CarePostgresEvidenceError("CARE catalog SQL p95 exceeds end-to-end p95")
    if any(value > query_p95_ms for value in catalog_path_sql_p95_ms):
        raise CarePostgresEvidenceError("CARE catalog path SQL p95 exceeds end-to-end p95")
    if replay_max_sql_count != max(replay_sql_counts):
        raise CarePostgresEvidenceError("CARE replay SQL count aggregate is inconsistent")
    if replay_max_sql_count > MAX_REPLAY_SQL_STATEMENTS_PER_BATCH:
        raise CarePostgresEvidenceError("CARE replay SQL statement budget was exceeded")
    if not math.isclose(
        replay_db_elapsed_seconds,
        sum(replay_sql_seconds),
        abs_tol=0.00001,
    ):
        raise CarePostgresEvidenceError("CARE replay SQL elapsed aggregate is inconsistent")
    exact_stage_properties = {
        "care.stage_upgrade.quality_parent_count": "95",
        "care.stage_upgrade.quality_artifact_count": "97",
        "care.stage_upgrade.concurrent_create_exact": "true",
        "care.stage_upgrade.concurrent_replay_exact": "true",
    }
    for name, expected in exact_stage_properties.items():
        if _required(vertical.properties, name) != expected:
            raise CarePostgresEvidenceError(f"same-database stage property is invalid: {name}")

    closure = _read_json(dependency_closure.resolve(strict=True))
    if closure.get("status") != "passed" or closure.get("gate") != (
        "care_benchmark_dependency_closure"
    ):
        raise CarePostgresEvidenceError("CARE dependency closure did not pass")
    for name in ("uv_lock_sha256", "requirements_lock_sha256"):
        if not _is_sha256(closure.get(name)):
            raise CarePostgresEvidenceError(f"CARE dependency closure is missing {name}")

    junit = {"offline": offline, "full_scale": full_scale, "vertical": vertical}
    report: dict[str, Any] = {
        "format_version": 1,
        "gate": "care_postgres_release_acceptance",
        "status": "passed",
        "identity": {
            "commit_sha": expected_commit_sha,
            "postgres_image": postgres_image,
            "migration_head": migration_head,
            "uv_lock_sha256": closure["uv_lock_sha256"],
            "requirements_lock_sha256": closure["requirements_lock_sha256"],
            **identities,
        },
        "tests": {
            "expected": sum(len(value) for value in EXPECTED_TESTS.values()),
            "actual": sum(value.tests for value in junit.values()),
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "junit_sha256": {name: value.sha256 for name, value in junit.items()},
        },
        "performance": {
            "replay_rows_per_second": replay_rows_per_second,
            "minimum_replay_rows_per_second": MIN_REPLAY_ROWS_PER_SECOND,
            "catalog_query_p95_ms": query_p95_ms,
            "maximum_catalog_query_p95_ms": MAX_QUERY_P95_MS,
            "replay_sql_statements_per_batch": replay_sql_counts,
            "maximum_replay_sql_statements_per_batch": MAX_REPLAY_SQL_STATEMENTS_PER_BATCH,
            "replay_database_elapsed_seconds": replay_db_elapsed_seconds,
            "catalog_sql_statement_count_max": catalog_sql_count_max,
            "maximum_catalog_sql_statements_per_request": (MAX_CATALOG_SQL_STATEMENTS_PER_REQUEST),
            "catalog_sql_p95_ms": catalog_sql_p95_ms,
            "catalog_paths": catalog_paths,
        },
        "same_database_stage_sequence": {
            name.removeprefix("care.stage_upgrade."): value
            for name, value in exact_stage_properties.items()
        },
        "junit_properties": properties,
    }
    report["evidence_root_sha256"] = _canonical_hash(report)
    return report


def _write_report(path: Path, report: dict[str, Any]) -> None:
    if path.is_symlink():
        raise CarePostgresEvidenceError("CARE PostgreSQL report cannot overwrite a symlink")
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify exact, identity-bound CARE PostgreSQL JUnit evidence"
    )
    parser.add_argument("--offline-junit", type=Path, required=True)
    parser.add_argument("--full-scale-junit", type=Path, required=True)
    parser.add_argument("--vertical-junit", type=Path, required=True)
    parser.add_argument("--dependency-closure", type=Path, required=True)
    parser.add_argument("--expected-commit-sha", required=True)
    parser.add_argument("--postgres-image", required=True)
    parser.add_argument("--migration-head", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify_care_postgres_evidence(
            offline_junit=args.offline_junit,
            full_scale_junit=args.full_scale_junit,
            vertical_junit=args.vertical_junit,
            dependency_closure=args.dependency_closure,
            expected_commit_sha=args.expected_commit_sha,
            postgres_image=args.postgres_image,
            migration_head=args.migration_head,
        )
        _write_report(args.report, report)
    except (CarePostgresEvidenceError, OSError) as exc:
        print(
            json.dumps(
                {
                    "gate": "care_postgres_release_acceptance",
                    "status": "failed",
                    "error": str(exc),
                }
            ),
            file=__import__("sys").stderr,
        )
        raise SystemExit(2) from exc
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
