from __future__ import annotations

import base64
import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from test_release_gate import _bundle
from windops_backend.operations.hybrid_identity import hybrid_bundle_id
from windops_backend.operations.hybrid_release_gate import (
    STRUCTURAL_CHECKS,
    verify_attested_sbom,
    verify_hybrid_release,
    verify_structural_acceptance,
)
from windops_backend.operations.report_io import sha256_file

API = "sha256:" + "b" * 64
STRUCTURAL = "sha256:" + "c" * 64
RELEASE = "windops-2026.08.14-rc1"
COMMIT = "a" * 40
IMAGE = "ghcr.io/example/structural@" + STRUCTURAL


def _identity():
    bundle_id = hybrid_bundle_id(RELEASE, COMMIT, API, STRUCTURAL)
    return {
        "release_id": RELEASE,
        "commit_sha": COMMIT,
        "api_image_digest": API,
        "image_digest": STRUCTURAL,
        "bundle_id": bundle_id,
        "evidence_set_id": bundle_id,
    }


def _acceptance(root: Path):
    artifact = root / "artifacts/structural/cases.xml"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        '<testsuites><testsuite><testcase name="prestress"/><testcase name="modal"/>'
        '<testcase name="scope_and_recovery"/></testsuite></testsuites>'
    )
    relative = artifact.relative_to(root).as_posix()
    now = datetime.now(UTC) - timedelta(seconds=1)
    report = {
        "format_version": 2,
        "gate": "structural_runtime",
        "status": "passed",
        "release": _identity(),
        "started_at": now.isoformat(),
        "completed_at": now.isoformat(),
        "target": "unit-schema-fixture",
        "tool": {"name": "unit-schema-fixture", "version": "1"},
        "approval": {"approved_by": "unit-reviewer", "approval_reference": "UNIT-ONLY"},
        "checks": [
            {
                "id": check,
                "status": "passed",
                "summary": "Unit contract fixture only",
                "artifact_paths": [relative],
            }
            for check in sorted(STRUCTURAL_CHECKS)
        ],
        "artifacts": [
            {"path": relative, "sha256": sha256_file(artifact), "media_type": "application/xml"}
        ],
    }
    path = root / "reports/structural_runtime.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report))
    return report, path, artifact


def test_acceptance_schema_and_content_identity_are_verified_without_qualifying_images(
    tmp_path: Path,
):
    report, _, _ = _acceptance(tmp_path)
    assert verify_structural_acceptance(tmp_path, _identity()) == report
    assert not (tmp_path / "hybrid-release-qualification.json").exists()


@pytest.mark.parametrize(
    "violation",
    [
        "api_digest",
        "structural_digest",
        "bundle",
        "missing_check",
        "duplicate_check",
        "tampered",
        "failure",
        "error",
        "skipped",
        "insufficient_cases",
        "future",
        "stale",
        "duration",
        "outside",
        "undeclared",
        "report_status",
    ],
)
def test_structural_acceptance_rejects_incomplete_drifted_and_failed_evidence(
    tmp_path: Path, violation
):
    report, path, artifact = _acceptance(tmp_path)
    if violation in {"api_digest", "structural_digest", "bundle"}:
        key = {
            "api_digest": "api_image_digest",
            "structural_digest": "image_digest",
            "bundle": "bundle_id",
        }[violation]
        report["release"][key] = "sha256:" + "d" * 64
    elif violation == "missing_check":
        report["checks"].pop()
    elif violation == "duplicate_check":
        report["checks"].append(copy.deepcopy(report["checks"][0]))
    elif violation == "tampered":
        artifact.write_text("changed")
    elif violation in {"failure", "error", "skipped", "insufficient_cases"}:
        artifact.write_text(
            '<testsuites><testsuite><testcase name="only">'
            + (f"<{violation}/>" if violation != "insufficient_cases" else "")
            + "</testcase></testsuite></testsuites>"
        )
        report["artifacts"][0]["sha256"] = sha256_file(artifact)
    elif violation in {"future", "stale", "duration"}:
        report["completed_at"] = (
            datetime.now(UTC)
            + timedelta(days=1 if violation == "future" else -4 if violation == "stale" else 0)
        ).isoformat()
        report["started_at"] = (
            datetime.fromisoformat(report["completed_at"])
            - timedelta(days=2 if violation == "duration" else 0)
        ).isoformat()
    elif violation == "outside":
        report["artifacts"][0]["path"] = "../outside.xml"
    elif violation == "undeclared":
        report["checks"][0]["artifact_paths"] = ["artifacts/missing.xml"]
    else:
        report["status"] = "unverified"
    path.write_text(json.dumps(report))
    with pytest.raises((ValueError, OSError)):
        verify_structural_acceptance(tmp_path, _identity())


def test_eleven_api_gates_alone_cannot_qualify_the_structural_runtime(tmp_path: Path):
    root = _bundle(tmp_path / "api-only")
    with pytest.raises(FileNotFoundError, match="structural_runtime"):
        verify_hybrid_release(
            evidence_dir=root,
            release_id=RELEASE,
            commit_sha=COMMIT,
            api_image="ghcr.io/example/api@" + API,
            structural_image=IMAGE,
            source_url="https://github.com/example/repo",
            policy=Path("unused"),
            lock=Path("unused"),
        )
    assert not (root / "hybrid-release-qualification.json").exists()


@pytest.mark.parametrize("changed", [None, "sbom", "image", "predicate"])
def test_verified_attestation_payload_must_bind_the_same_spdx_and_digest(changed):
    sbom = {"spdxVersion": "SPDX-2.3", "packages": [{"name": "unit-package"}]}
    statement = {
        "predicateType": "https://spdx.dev/Document",
        "predicate": copy.deepcopy(sbom),
        "subject": [{"digest": {"sha256": STRUCTURAL.split(":")[1]}}],
    }
    if changed == "sbom":
        statement["predicate"]["packages"][0]["name"] = "other"
    elif changed == "image":
        statement["subject"][0]["digest"]["sha256"] = "d" * 64
    elif changed == "predicate":
        statement["predicateType"] = "unknown"
    output = json.dumps({"payload": base64.b64encode(json.dumps(statement).encode()).decode()})
    if changed is None:
        verify_attested_sbom(output, sbom, IMAGE)
    else:
        with pytest.raises(ValueError, match="does not bind"):
            verify_attested_sbom(output, sbom, IMAGE)


def test_two_image_identity_changes_when_either_image_changes():
    original = hybrid_bundle_id(RELEASE, COMMIT, API, STRUCTURAL)
    assert original != hybrid_bundle_id(RELEASE, COMMIT, API, "sha256:" + "d" * 64)
    assert original != hybrid_bundle_id(RELEASE, COMMIT, "sha256:" + "d" * 64, STRUCTURAL)
    with pytest.raises(ValueError, match="separate"):
        hybrid_bundle_id(RELEASE, COMMIT, API, API)
