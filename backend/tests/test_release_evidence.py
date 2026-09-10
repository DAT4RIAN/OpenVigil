from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from windops_backend.operations.release_evidence import (
    ReleaseEvidenceError,
    assemble_release_manifest,
    record_gate_report,
    release_evidence_set_id,
)
from windops_backend.operations.release_gate import (
    QUALIFICATION_NAME,
    REQUIRED_GATE_CHECKS,
    REQUIRED_RELEASE_GATES,
    _write_qualification,
    verify_release_evidence,
)


def _record_all(root: Path) -> tuple[str, str, str, str]:
    release_id = "windops-2026.09.04-rc1"
    commit_sha = "a" * 40
    image_digest = "sha256:" + "b" * 64
    evidence_set_id = release_evidence_set_id(release_id, commit_sha, image_digest)
    now = datetime.now(UTC).isoformat()
    for gate in REQUIRED_RELEASE_GATES:
        artifact = root / "artifacts" / f"{gate}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({"gate": gate, "result": "passed"}), encoding="utf-8")
        relative = artifact.relative_to(root).as_posix()
        record_gate_report(
            root,
            gate=gate,
            release_id=release_id,
            commit_sha=commit_sha,
            image_digest=image_digest,
            evidence_set_id=evidence_set_id,
            started_at=now,
            completed_at=now,
            target="isolated-production-candidate",
            tool_name=f"{gate}-verifier",
            tool_version="1.0",
            approved_by="release-reviewer",
            approval_reference=f"APPROVAL-{gate.upper()}",
            artifacts=[(relative, "application/json")],
            checks=[(check, [relative]) for check in REQUIRED_GATE_CHECKS[gate]],
        )
    return release_id, commit_sha, image_digest, evidence_set_id


def test_evidence_builder_assembles_then_only_gate_writes_qualification(tmp_path: Path) -> None:
    root = tmp_path / "release-evidence"
    release_id, commit_sha, image_digest, evidence_set_id = _record_all(root)
    assemble_release_manifest(
        root,
        release_id=release_id,
        commit_sha=commit_sha,
        image_digest=image_digest,
        evidence_set_id=evidence_set_id,
        created_at=datetime.now(UTC).isoformat(),
    )
    assert not (root / QUALIFICATION_NAME).exists()
    result = verify_release_evidence(root)
    _write_qualification(root / QUALIFICATION_NAME, result)
    qualification = json.loads((root / QUALIFICATION_NAME).read_text(encoding="utf-8"))
    assert qualification["status"] == "qualified"
    assert qualification["manifest_sha256"] == result["manifest_sha256"]
    assert qualification["evidence_set_id"] == evidence_set_id
    with pytest.raises(ValueError, match="already exists"):
        _write_qualification(root / QUALIFICATION_NAME, result)


def test_evidence_builder_rejects_missing_checks_and_wrong_identity(tmp_path: Path) -> None:
    root = tmp_path / "release-evidence"
    artifact = root / "artifacts" / "scan.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    release_id = "windops-2026.09.04-rc1"
    commit_sha = "a" * 40
    image_digest = "sha256:" + "b" * 64
    evidence_set_id = release_evidence_set_id(release_id, commit_sha, image_digest)
    now = datetime.now(UTC).isoformat()
    common = {
        "evidence_dir": root,
        "gate": "image_scan",
        "release_id": release_id,
        "commit_sha": commit_sha,
        "image_digest": image_digest,
        "started_at": now,
        "completed_at": now,
        "target": "candidate-image",
        "tool_name": "trivy",
        "tool_version": "0.68.2",
        "approved_by": "release-reviewer",
        "approval_reference": "APPROVAL-IMAGE-SCAN",
        "artifacts": [("artifacts/scan.json", "application/json")],
    }
    with pytest.raises(ReleaseEvidenceError, match="check set is incomplete"):
        record_gate_report(
            **common,
            evidence_set_id=evidence_set_id,
            checks=[("immutable_digest_scanned", ["artifacts/scan.json"])],
        )
    with pytest.raises(ReleaseEvidenceError, match="not derived"):
        record_gate_report(
            **common,
            evidence_set_id="sha256:" + "c" * 64,
            checks=[
                (check, ["artifacts/scan.json"]) for check in REQUIRED_GATE_CHECKS["image_scan"]
            ],
        )
