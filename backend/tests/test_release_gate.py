import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from release_scan_fixtures import trivy_image_scan
from windops_backend.operations.release_evidence import release_evidence_set_id
from windops_backend.operations.release_gate import (
    MANIFEST_DIGEST_NAME,
    MANIFEST_NAME,
    REQUIRED_GATE_CHECKS,
    REQUIRED_RELEASE_GATES,
    verify_release_evidence,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(root: Path) -> Path:
    root.mkdir()
    now = datetime.now(UTC).isoformat()
    release = {
        "release_id": "windops-2026.08.14-rc1",
        "commit_sha": "a" * 40,
        "image_digest": "sha256:" + "b" * 64,
    }
    release["evidence_set_id"] = release_evidence_set_id(
        release["release_id"], release["commit_sha"], release["image_digest"]
    )
    evidence = []
    for gate in sorted(REQUIRED_RELEASE_GATES):
        artifact = root / "artifacts" / f"{gate}.json"
        artifact.parent.mkdir(exist_ok=True)
        artifact.write_text(
            json.dumps(
                trivy_image_scan(
                    release["release_id"], release["commit_sha"], release["image_digest"]
                )
                if gate == "image_scan"
                else {"gate": gate, "raw_result": "passed"}
            ),
            encoding="utf-8",
        )
        artifact_path = artifact.relative_to(root).as_posix()
        report = root / "reports" / f"{gate}.json"
        report.parent.mkdir(exist_ok=True)
        report.write_text(
            json.dumps(
                {
                    "format_version": 2,
                    "gate": gate,
                    "status": "passed",
                    "release": release,
                    "started_at": now,
                    "completed_at": now,
                    "target": "isolated-production-candidate",
                    "tool": {"name": "release-test-harness", "version": "1.0"},
                    "approval": {
                        "approved_by": "independent-release-reviewer",
                        "approval_reference": f"CHANGE-{gate.upper()}",
                    },
                    "checks": [
                        {
                            "id": check_id,
                            "status": "passed",
                            "summary": f"{check_id} was verified against raw evidence",
                            "artifact_paths": [artifact_path],
                        }
                        for check_id in sorted(REQUIRED_GATE_CHECKS[gate])
                    ],
                    "artifacts": [
                        {
                            "path": artifact_path,
                            "sha256": _sha256(artifact),
                            "media_type": "application/json",
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        evidence.append(
            {
                "gate": gate,
                "status": "passed",
                "report_path": report.relative_to(root).as_posix(),
                "report_sha256": _sha256(report),
                "completed_at": now,
                "approved_by": "independent-release-reviewer",
                "approval_reference": f"CHANGE-{gate.upper()}",
            }
        )
    manifest = {
        "format_version": 2,
        **release,
        "created_at": now,
        "evidence": evidence,
    }
    manifest_path = root / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    (root / MANIFEST_DIGEST_NAME).write_text(
        f"{_sha256(manifest_path)}  {MANIFEST_NAME}\n", encoding="ascii"
    )
    return root


def _resign(root: Path) -> None:
    manifest_path = root / MANIFEST_NAME
    (root / MANIFEST_DIGEST_NAME).write_text(
        f"{_sha256(manifest_path)}  {MANIFEST_NAME}\n", encoding="ascii"
    )


def _refresh_report_digest(root: Path, gate: str) -> None:
    manifest_path = root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report_path = root / "reports" / f"{gate}.json"
    for item in manifest["evidence"]:
        if item["gate"] == gate:
            item["report_sha256"] = _sha256(report_path)
            break
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _resign(root)


def _refresh_image_scan_artifact(root: Path) -> None:
    report_path = root / "reports" / "image_scan.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["artifacts"][0]["sha256"] = _sha256(root / "artifacts" / "image_scan.json")
    report_path.write_text(json.dumps(report), encoding="utf-8")
    _refresh_report_digest(root, "image_scan")


@pytest.mark.parametrize("finding_type", ["Vulnerabilities", "Secrets"])
@pytest.mark.parametrize("severity", ["CRITICAL", "HIGH"])
def test_verifier_rejects_failed_raw_scan_even_when_hashes_and_approvals_match(
    tmp_path: Path, finding_type: str, severity: str
) -> None:
    root = _bundle(tmp_path / "contradictory-scan")
    path = root / "artifacts" / "image_scan.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["Results"][0][finding_type] = [{"Severity": severity}]
    path.write_text(json.dumps(raw), encoding="utf-8")
    _refresh_image_scan_artifact(root)
    with pytest.raises(ValueError, match="raw image scan contains"):
        verify_release_evidence(root)
    assert not (root / "release-qualification.json").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "invalid_json",
        "invalid_utf8",
        "not_object",
        "unsupported_schema",
        "wrong_artifact_type",
        "scanner_error",
        "empty_results",
        "invalid_result",
        "empty_target",
        "no_os_scan",
        "empty_findings_object",
        "false_findings",
        "missing_severity",
        "invalid_severity",
        "severity_array",
        "missing_metadata",
        "invalid_labels",
        "invalid_repo_digests",
        "different_digest",
        "different_commit",
        "different_release",
    ],
)
def test_verifier_rejects_malformed_or_unbound_raw_image_scans(
    tmp_path: Path, mutation: str
) -> None:
    root = _bundle(tmp_path / "invalid-raw-scan")
    path = root / "artifacts" / "image_scan.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "invalid_json":
        path.write_text("not JSON", encoding="utf-8")
    elif mutation == "invalid_utf8":
        path.write_bytes(b"\xff")
    else:
        if mutation == "not_object":
            raw = []
        elif mutation == "unsupported_schema":
            raw["SchemaVersion"] = 1
        elif mutation == "wrong_artifact_type":
            raw["ArtifactType"] = "filesystem"
        elif mutation == "scanner_error":
            raw["Errors"] = ["scan incomplete"]
        elif mutation == "empty_results":
            raw["Results"] = []
        elif mutation == "invalid_result":
            raw["Results"] = [None]
        elif mutation == "empty_target":
            raw["Results"][0]["Target"] = ""
        elif mutation == "no_os_scan":
            raw["Results"][0]["Class"] = "lang-pkgs"
        elif mutation == "empty_findings_object":
            raw["Results"][0]["Vulnerabilities"] = {}
        elif mutation == "false_findings":
            raw["Results"][0]["Secrets"] = False
        elif mutation == "missing_severity":
            raw["Results"][0]["Vulnerabilities"] = [{}]
        elif mutation == "invalid_severity":
            raw["Results"][0]["Vulnerabilities"] = [{"Severity": "unrated"}]
        elif mutation == "severity_array":
            raw["Results"][0]["Vulnerabilities"] = [{"Severity": []}]
        elif mutation == "missing_metadata":
            raw.pop("Metadata")
        elif mutation == "invalid_labels":
            raw["Metadata"]["ImageConfig"]["config"]["Labels"] = []
        elif mutation == "invalid_repo_digests":
            raw["Metadata"]["RepoDigests"] = [False]
        elif mutation == "different_digest":
            raw["ArtifactName"] = "registry.example/openvigil@sha256:" + "c" * 64
        elif mutation == "different_commit":
            raw["Metadata"]["ImageConfig"]["config"]["Labels"][
                "org.opencontainers.image.revision"
            ] = "c" * 40
        elif mutation == "different_release":
            raw["Metadata"]["ImageConfig"]["config"]["Labels"][
                "org.opencontainers.image.version"
            ] = "another-release"
        path.write_text(json.dumps(raw), encoding="utf-8")
    _refresh_image_scan_artifact(root)
    with pytest.raises(ValueError, match="raw image scan"):
        verify_release_evidence(root)


@pytest.mark.parametrize("scan_variant", ["lower_severity", "nullable_findings", "repo_digest"])
def test_raw_scan_accepts_valid_zero_critical_high_results(
    tmp_path: Path, scan_variant: str
) -> None:
    root = _bundle(tmp_path / "valid-scan")
    path = root / "artifacts" / "image_scan.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if scan_variant == "lower_severity":
        raw["Results"][0]["Vulnerabilities"] = [
            {"Severity": severity} for severity in ("LOW", "MEDIUM", "UNKNOWN")
        ]
    elif scan_variant == "nullable_findings":
        raw["Results"][0].update(Vulnerabilities=None, Secrets=None)
        raw["Metadata"]["RepoDigests"] = None
    elif scan_variant == "repo_digest":
        raw["Metadata"]["RepoDigests"] = [raw["ArtifactName"]]
        raw["ArtifactName"] = "local-tag"
    path.write_text(json.dumps(raw), encoding="utf-8")
    _refresh_image_scan_artifact(root)
    assert verify_release_evidence(root)["status"] == "verified"


def test_complete_release_evidence_bundle_is_verified(tmp_path: Path) -> None:
    result = verify_release_evidence(_bundle(tmp_path / "release"))
    assert result["status"] == "verified"
    assert result["gate_count"] == len(REQUIRED_RELEASE_GATES)
    assert result["image_digest"] == "sha256:" + "b" * 64
    assert result["evidence_set_id"] == release_evidence_set_id(
        "windops-2026.08.14-rc1", "a" * 40, "sha256:" + "b" * 64
    )


def test_release_gate_rejects_missing_or_tampered_reports(tmp_path: Path) -> None:
    root = _bundle(tmp_path / "release")
    manifest_path = root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence"] = manifest["evidence"][1:]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _resign(root)
    with pytest.raises(ValueError, match="schema violation|required release evidence"):
        verify_release_evidence(root)

    root = _bundle(tmp_path / "tampered")
    (root / "reports" / "dast.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="report digest mismatch"):
        verify_release_evidence(root)


def test_release_gate_rejects_placeholder_digest_and_path_escape(tmp_path: Path) -> None:
    root = _bundle(tmp_path / "release")
    manifest_path = root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["image_digest"] = "sha256:" + "0" * 64
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _resign(root)
    with pytest.raises(ValueError, match="placeholder"):
        verify_release_evidence(root)

    root = _bundle(tmp_path / "escape")
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    manifest_path = root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence"][0]["report_path"] = "../../outside.json"
    manifest["evidence"][0]["report_sha256"] = _sha256(outside)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _resign(root)
    with pytest.raises(ValueError, match="escapes"):
        verify_release_evidence(root)


def test_release_gate_rejects_unbound_or_incomplete_gate_reports(tmp_path: Path) -> None:
    root = _bundle(tmp_path / "unbound")
    report_path = root / "reports" / "sites_postdeploy.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["release"]["commit_sha"] = "c" * 40
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    _refresh_report_digest(root, "sites_postdeploy")
    with pytest.raises(ValueError, match="not bound to manifest commit_sha"):
        verify_release_evidence(root)

    root = _bundle(tmp_path / "incomplete")
    report_path = root / "reports" / "dast.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["checks"] = [
        check for check in report["checks"] if check["id"] != "role_boundaries_tested"
    ]
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    _refresh_report_digest(root, "dast")
    with pytest.raises(ValueError, match="missing required checks: role_boundaries_tested"):
        verify_release_evidence(root)


def test_release_gate_rejects_tampered_or_undeclared_raw_artifacts(tmp_path: Path) -> None:
    root = _bundle(tmp_path / "tampered-artifact")
    (root / "artifacts" / "slo_exercise.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        verify_release_evidence(root)

    root = _bundle(tmp_path / "undeclared-artifact")
    report_path = root / "reports" / "migration.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["checks"][0]["artifact_paths"] = ["artifacts/not-declared.json"]
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    _refresh_report_digest(root, "migration")
    with pytest.raises(ValueError, match="cites undeclared artifacts"):
        verify_release_evidence(root)


def test_release_gate_rejects_stale_or_cross_run_reports(tmp_path: Path) -> None:
    root = _bundle(tmp_path / "stale")
    manifest_path = root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stale_time = (datetime.now(UTC) - timedelta(days=4)).isoformat()
    for gate in REQUIRED_RELEASE_GATES:
        report_path = root / "reports" / f"{gate}.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["started_at"] = stale_time
        report["completed_at"] = stale_time
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        for item in manifest["evidence"]:
            if item["gate"] == gate:
                item["completed_at"] = stale_time
                item["report_sha256"] = _sha256(report_path)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _resign(root)
    with pytest.raises(ValueError, match="stale gate reports"):
        verify_release_evidence(root)

    root = _bundle(tmp_path / "cross-run")
    report_path = root / "reports" / "dast.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["release"]["evidence_set_id"] = "sha256:" + "c" * 64
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    _refresh_report_digest(root, "dast")
    with pytest.raises(ValueError, match="evidence_set_id"):
        verify_release_evidence(root)
