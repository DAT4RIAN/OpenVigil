from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from windops_backend.operations.release_gate import (
    GATE_REPORT_SCHEMA,
    MANIFEST_DIGEST_NAME,
    MANIFEST_FORMAT_VERSION,
    MANIFEST_NAME,
    RELEASE_EVIDENCE_SCHEMA,
    REPORT_FORMAT_VERSION,
    REQUIRED_GATE_CHECKS,
    REQUIRED_RELEASE_GATES,
    _safe_report_path,
)
from windops_backend.operations.report_io import (
    sha256_file as _sha256_file,
)
from windops_backend.operations.report_io import (
    write_atomic_json,
)


class ReleaseEvidenceError(ValueError):
    pass


def release_evidence_set_id(release_id: str, commit_sha: str, image_digest: str) -> str:
    payload = f"{release_id}\n{commit_sha}\n{image_digest}\n".encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    write_atomic_json(
        path,
        payload,
        symlink_error=ReleaseEvidenceError(
            "release evidence output cannot overwrite a symbolic link"
        ),
    )


def _parse_artifact(value: str) -> tuple[str, str]:
    try:
        relative_path, media_type = value.rsplit("=", 1)
    except ValueError as exc:
        raise ReleaseEvidenceError("artifact must use RELATIVE_PATH=MEDIA_TYPE") from exc
    if not relative_path or "/" not in media_type:
        raise ReleaseEvidenceError("artifact must include a relative path and media type")
    return relative_path, media_type


def _parse_check(value: str) -> tuple[str, list[str]]:
    try:
        check_id, paths = value.split("=", 1)
    except ValueError as exc:
        raise ReleaseEvidenceError("check must use CHECK_ID=PATH[,PATH]") from exc
    artifact_paths = [path for path in paths.split(",") if path]
    if not check_id or not artifact_paths:
        raise ReleaseEvidenceError("check must name at least one raw artifact")
    return check_id, artifact_paths


def record_gate_report(
    evidence_dir: Path,
    *,
    gate: str,
    release_id: str,
    commit_sha: str,
    image_digest: str,
    evidence_set_id: str,
    started_at: str,
    completed_at: str,
    target: str,
    tool_name: str,
    tool_version: str,
    approved_by: str,
    approval_reference: str,
    artifacts: list[tuple[str, str]],
    checks: list[tuple[str, list[str]]],
) -> Path:
    if gate not in REQUIRED_RELEASE_GATES:
        raise ReleaseEvidenceError(f"unknown release gate: {gate}")
    expected_set_id = release_evidence_set_id(release_id, commit_sha, image_digest)
    if evidence_set_id != expected_set_id:
        raise ReleaseEvidenceError("evidence set ID is not derived from the release identity")

    root = evidence_dir.resolve()
    artifact_records: list[dict[str, str]] = []
    observed_artifacts: set[str] = set()
    for relative_path, media_type in artifacts:
        if relative_path in observed_artifacts:
            raise ReleaseEvidenceError(f"duplicate raw artifact: {relative_path}")
        artifact_path = _safe_report_path(root, relative_path)
        if not artifact_path.is_file() or artifact_path.stat().st_size == 0:
            raise ReleaseEvidenceError(f"raw artifact is missing or empty: {relative_path}")
        observed_artifacts.add(relative_path)
        artifact_records.append(
            {
                "path": relative_path,
                "sha256": _sha256_file(artifact_path),
                "media_type": media_type,
            }
        )

    observed_checks: set[str] = set()
    check_records: list[dict[str, Any]] = []
    for check_id, artifact_paths in checks:
        if check_id in observed_checks:
            raise ReleaseEvidenceError(f"duplicate gate check: {check_id}")
        undeclared = set(artifact_paths) - observed_artifacts
        if undeclared:
            raise ReleaseEvidenceError(
                f"gate check {check_id} cites undeclared artifacts: {', '.join(sorted(undeclared))}"
            )
        observed_checks.add(check_id)
        check_records.append(
            {
                "id": check_id,
                "status": "passed",
                "summary": f"{check_id} passed with the cited immutable raw evidence",
                "artifact_paths": artifact_paths,
            }
        )
    if observed_checks != REQUIRED_GATE_CHECKS[gate]:
        missing = REQUIRED_GATE_CHECKS[gate] - observed_checks
        unexpected = observed_checks - REQUIRED_GATE_CHECKS[gate]
        details = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if unexpected:
            details.append(f"unexpected {', '.join(sorted(unexpected))}")
        raise ReleaseEvidenceError(f"{gate} check set is incomplete: {'; '.join(details)}")

    report: dict[str, Any] = {
        "format_version": REPORT_FORMAT_VERSION,
        "gate": gate,
        "status": "passed",
        "release": {
            "release_id": release_id,
            "commit_sha": commit_sha,
            "image_digest": image_digest,
            "evidence_set_id": evidence_set_id,
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "target": target,
        "tool": {"name": tool_name, "version": tool_version},
        "approval": {
            "approved_by": approved_by,
            "approval_reference": approval_reference,
        },
        "checks": check_records,
        "artifacts": artifact_records,
    }
    errors = sorted(Draft202012Validator(GATE_REPORT_SCHEMA).iter_errors(report), key=str)
    if errors:
        raise ReleaseEvidenceError(f"gate report schema violation: {errors[0].message}")
    report_path = root / "reports" / f"{gate}.json"
    _atomic_json(report_path, report)
    return report_path


def assemble_release_manifest(
    evidence_dir: Path,
    *,
    release_id: str,
    commit_sha: str,
    image_digest: str,
    evidence_set_id: str,
    created_at: str,
) -> Path:
    expected_set_id = release_evidence_set_id(release_id, commit_sha, image_digest)
    if evidence_set_id != expected_set_id:
        raise ReleaseEvidenceError("evidence set ID is not derived from the release identity")
    root = evidence_dir.resolve()
    evidence: list[dict[str, str]] = []
    for gate in sorted(REQUIRED_RELEASE_GATES):
        report_path = root / "reports" / f"{gate}.json"
        if not report_path.is_file() or report_path.is_symlink():
            raise ReleaseEvidenceError(f"required gate report is missing or unsafe: {gate}")
        try:
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReleaseEvidenceError(f"required gate report is invalid JSON: {gate}") from exc
        errors = sorted(Draft202012Validator(GATE_REPORT_SCHEMA).iter_errors(loaded), key=str)
        if errors:
            raise ReleaseEvidenceError(f"{gate} gate report schema violation: {errors[0].message}")
        report = cast(dict[str, Any], loaded)
        if report["gate"] != gate:
            raise ReleaseEvidenceError(f"gate report filename does not match its gate: {gate}")
        expected_release = {
            "release_id": release_id,
            "commit_sha": commit_sha,
            "image_digest": image_digest,
            "evidence_set_id": evidence_set_id,
        }
        if report["release"] != expected_release:
            raise ReleaseEvidenceError(f"{gate} gate report belongs to another release identity")
        approval = cast(dict[str, str], report["approval"])
        evidence.append(
            {
                "gate": gate,
                "status": "passed",
                "report_path": report_path.relative_to(root).as_posix(),
                "report_sha256": _sha256_file(report_path),
                "completed_at": cast(str, report["completed_at"]),
                "approved_by": approval["approved_by"],
                "approval_reference": approval["approval_reference"],
            }
        )
    manifest: dict[str, Any] = {
        "format_version": MANIFEST_FORMAT_VERSION,
        "release_id": release_id,
        "commit_sha": commit_sha,
        "image_digest": image_digest,
        "evidence_set_id": evidence_set_id,
        "created_at": created_at,
        "evidence": evidence,
    }
    errors = sorted(Draft202012Validator(RELEASE_EVIDENCE_SCHEMA).iter_errors(manifest), key=str)
    if errors:
        raise ReleaseEvidenceError(f"release manifest schema violation: {errors[0].message}")
    manifest_path = root / MANIFEST_NAME
    _atomic_json(manifest_path, manifest)
    digest_path = root / MANIFEST_DIGEST_NAME
    if digest_path.is_symlink():
        raise ReleaseEvidenceError("release manifest digest cannot overwrite a symbolic link")
    digest_path.write_text(f"{_sha256_file(manifest_path)}  {MANIFEST_NAME}\n", encoding="ascii")
    return manifest_path


def _record_command(args: argparse.Namespace) -> None:
    report = record_gate_report(
        args.evidence_dir,
        gate=args.gate,
        release_id=args.release_id,
        commit_sha=args.commit_sha,
        image_digest=args.image_digest,
        evidence_set_id=args.evidence_set_id,
        started_at=args.started_at,
        completed_at=args.completed_at,
        target=args.target,
        tool_name=args.tool_name,
        tool_version=args.tool_version,
        approved_by=args.approved_by,
        approval_reference=args.approval_reference,
        artifacts=[_parse_artifact(value) for value in args.artifact],
        checks=[_parse_check(value) for value in args.check],
    )
    print(report)


def _assemble_command(args: argparse.Namespace) -> None:
    manifest = assemble_release_manifest(
        args.evidence_dir,
        release_id=args.release_id,
        commit_sha=args.commit_sha,
        image_digest=args.image_digest,
        evidence_set_id=args.evidence_set_id,
        created_at=args.created_at,
    )
    print(manifest)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create standardized, content-addressed OpenVigil release evidence"
    )
    subparsers = parser.add_subparsers(required=True)
    record = subparsers.add_parser("record", help="record one passed gate from raw evidence")
    record.add_argument("--evidence-dir", type=Path, required=True)
    record.add_argument("--gate", choices=sorted(REQUIRED_RELEASE_GATES), required=True)
    record.add_argument("--release-id", required=True)
    record.add_argument("--commit-sha", required=True)
    record.add_argument("--image-digest", required=True)
    record.add_argument("--evidence-set-id", required=True)
    record.add_argument("--started-at", required=True)
    record.add_argument("--completed-at", default=datetime.now(UTC).isoformat())
    record.add_argument("--target", required=True)
    record.add_argument("--tool-name", required=True)
    record.add_argument("--tool-version", required=True)
    record.add_argument("--approved-by", required=True)
    record.add_argument("--approval-reference", required=True)
    record.add_argument("--artifact", action="append", required=True)
    record.add_argument("--check", action="append", required=True)
    record.set_defaults(handler=_record_command)

    assemble = subparsers.add_parser("assemble", help="assemble the exact eleven gate reports")
    assemble.add_argument("--evidence-dir", type=Path, required=True)
    assemble.add_argument("--release-id", required=True)
    assemble.add_argument("--commit-sha", required=True)
    assemble.add_argument("--image-digest", required=True)
    assemble.add_argument("--evidence-set-id", required=True)
    assemble.add_argument("--created-at", default=datetime.now(UTC).isoformat())
    assemble.set_defaults(handler=_assemble_command)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
