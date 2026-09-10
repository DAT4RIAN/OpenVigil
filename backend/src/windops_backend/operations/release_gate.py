from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

MANIFEST_NAME = "release-evidence.json"
MANIFEST_DIGEST_NAME = "release-evidence.sha256"
REQUIRED_RELEASE_GATES = frozenset(
    {
        "image_scan",
        "sbom",
        "signature_verification",
        "deployment_policy",
        "migration",
        "external_release",
        "dr_drill",
        "dast",
        "accessibility_visual",
        "slo_exercise",
        "sites_postdeploy",
    }
)

REPORT_FORMAT_VERSION = 1
REQUIRED_GATE_CHECKS: dict[str, frozenset[str]] = {
    "image_scan": frozenset(
        {"immutable_digest_scanned", "critical_findings_zero", "high_findings_zero"}
    ),
    "sbom": frozenset({"immutable_digest_bound", "components_present", "format_validated"}),
    "signature_verification": frozenset(
        {"digest_verified", "signer_identity_verified", "signature_policy_verified"}
    ),
    "deployment_policy": frozenset(
        {
            "rendered_manifests_validated",
            "immutable_digest_bound",
            "pod_security_validated",
            "network_policy_validated",
            "encrypted_backup_storage_validated",
        }
    ),
    "migration": frozenset(
        {
            "backup_recorded",
            "unique_head_verified",
            "candidate_upgrade_completed",
            "post_upgrade_head_verified",
            "rollback_rehearsed",
        }
    ),
    "external_release": frozenset(
        {
            "dependency_readiness",
            "protected_metrics",
            "object_roundtrip",
            "embedding_provider",
            "reasoning_provider",
            "active_model_inference",
        }
    ),
    "dr_drill": frozenset(
        {
            "source_target_isolated",
            "restore_completed",
            "schema_verified",
            "row_counts_verified",
            "objects_verified",
            "rto_met",
            "rpo_met",
        }
    ),
    "dast": frozenset(
        {
            "sites_entry_scanned",
            "api_entry_scanned",
            "role_boundaries_tested",
            "critical_findings_zero",
            "high_findings_zero",
        }
    ),
    "accessibility_visual": frozenset(
        {
            "automated_scan",
            "critical_violations_zero",
            "keyboard_navigation",
            "screen_reader",
            "zoom_200_percent",
            "responsive_layout",
            "reduced_motion",
            "visual_regression",
        }
    ),
    "slo_exercise": frozenset(
        {
            "load_test",
            "latency_target_met",
            "error_budget_met",
            "telemetry_freshness_met",
            "agent_success_target_met",
            "alert_routed",
            "trace_correlated",
        }
    ),
    "sites_postdeploy": frozenset(
        {
            "runtime_release_identity",
            "production_workspaces",
            "fixture_leakage_zero",
            "sse_resume",
            "alarm_write",
            "approval_work_order",
            "evidence_upload",
            "report_export",
            "knowledge_retrieval",
            "knowledge_graph_scope_boundary",
            "model_inference",
            "metrics",
            "trace_correlation",
            "rollback_verified",
        }
    ),
}

GATE_REPORT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "format_version",
        "gate",
        "status",
        "release",
        "started_at",
        "completed_at",
        "target",
        "tool",
        "checks",
        "artifacts",
    ],
    "properties": {
        "format_version": {"const": REPORT_FORMAT_VERSION},
        "gate": {"enum": sorted(REQUIRED_RELEASE_GATES)},
        "status": {"const": "passed"},
        "release": {
            "type": "object",
            "additionalProperties": False,
            "required": ["release_id", "commit_sha", "image_digest"],
            "properties": {
                "release_id": {"type": "string", "minLength": 3, "maxLength": 128},
                "commit_sha": {"type": "string", "pattern": "^(?:[0-9a-f]{40}|[0-9a-f]{64})$"},
                "image_digest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            },
        },
        "started_at": {"type": "string", "format": "date-time"},
        "completed_at": {"type": "string", "format": "date-time"},
        "target": {"type": "string", "minLength": 3, "maxLength": 512},
        "tool": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "version"],
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 160},
                "version": {"type": "string", "minLength": 1, "maxLength": 160},
            },
        },
        "checks": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "status", "summary", "artifact_paths"],
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{2,95}$"},
                    "status": {"const": "passed"},
                    "summary": {"type": "string", "minLength": 3, "maxLength": 2000},
                    "artifact_paths": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1, "maxLength": 1024},
                    },
                },
            },
        },
        "artifacts": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "sha256", "media_type"],
                "properties": {
                    "path": {"type": "string", "minLength": 1, "maxLength": 1024},
                    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "media_type": {"type": "string", "minLength": 3, "maxLength": 160},
                },
            },
        },
    },
}

RELEASE_EVIDENCE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "format_version",
        "release_id",
        "commit_sha",
        "image_digest",
        "created_at",
        "evidence",
    ],
    "properties": {
        "format_version": {"const": 1},
        "release_id": {"type": "string", "minLength": 3, "maxLength": 128},
        "commit_sha": {"type": "string", "pattern": "^(?:[0-9a-f]{40}|[0-9a-f]{64})$"},
        "image_digest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "created_at": {"type": "string", "format": "date-time"},
        "evidence": {
            "type": "array",
            "minItems": len(REQUIRED_RELEASE_GATES),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "gate",
                    "status",
                    "report_path",
                    "report_sha256",
                    "completed_at",
                    "approved_by",
                    "approval_reference",
                ],
                "properties": {
                    "gate": {"enum": sorted(REQUIRED_RELEASE_GATES)},
                    "status": {"const": "passed"},
                    "report_path": {"type": "string", "minLength": 1, "maxLength": 1024},
                    "report_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "completed_at": {"type": "string", "format": "date-time"},
                    "approved_by": {"type": "string", "minLength": 2, "maxLength": 160},
                    "approval_reference": {
                        "type": "string",
                        "minLength": 3,
                        "maxLength": 512,
                    },
                },
            },
        },
    },
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _aware_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _safe_report_path(root: Path, relative_path: str) -> Path:
    candidate_relative = Path(relative_path)
    if candidate_relative.is_absolute() or not relative_path:
        raise ValueError("release evidence report paths must be relative")
    cursor = root
    for part in candidate_relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("release evidence reports cannot be symbolic links")
    candidate = (root / candidate_relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("release evidence report path escapes the evidence directory")
    return candidate


def _verify_gate_report(
    root: Path,
    report_path: Path,
    manifest: dict[str, Any],
    evidence_item: dict[str, Any],
) -> None:
    gate = cast(str, evidence_item["gate"])
    try:
        loaded = json.loads(report_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{gate} gate report must be valid UTF-8 JSON") from exc
    errors = sorted(Draft202012Validator(GATE_REPORT_SCHEMA).iter_errors(loaded), key=str)
    if errors:
        raise ValueError(f"{gate} gate report schema violation: {errors[0].message}")
    report = cast(dict[str, Any], loaded)
    if report["gate"] != gate:
        raise ValueError(f"{gate} gate report declares a different gate")
    release = cast(dict[str, Any], report["release"])
    for field in ("release_id", "commit_sha", "image_digest"):
        if release[field] != manifest[field]:
            raise ValueError(f"{gate} gate report is not bound to manifest {field}")

    started_at = _aware_datetime(cast(str, report["started_at"]), f"{gate}.started_at")
    completed_at = _aware_datetime(cast(str, report["completed_at"]), f"{gate}.completed_at")
    manifest_completed_at = _aware_datetime(
        cast(str, evidence_item["completed_at"]), f"{gate}.manifest_completed_at"
    )
    if completed_at < started_at:
        raise ValueError(f"{gate} gate report completed before it started")
    if completed_at != manifest_completed_at:
        raise ValueError(f"{gate} gate report completion time does not match the manifest")

    artifact_paths: set[str] = set()
    for artifact in cast(list[dict[str, Any]], report["artifacts"]):
        relative_path = cast(str, artifact["path"])
        if relative_path in artifact_paths:
            raise ValueError(f"{gate} gate report duplicates artifact path: {relative_path}")
        artifact_paths.add(relative_path)
        artifact_path = _safe_report_path(root, relative_path)
        if artifact_path == report_path:
            raise ValueError(f"{gate} gate report cannot cite itself as raw evidence")
        if not artifact_path.is_file() or artifact_path.stat().st_size == 0:
            raise ValueError(f"{gate} gate artifact is missing or empty: {relative_path}")
        if _sha256_file(artifact_path) != artifact["sha256"]:
            raise ValueError(f"{gate} gate artifact digest mismatch: {relative_path}")

    observed_checks: set[str] = set()
    for check in cast(list[dict[str, Any]], report["checks"]):
        check_id = cast(str, check["id"])
        if check_id in observed_checks:
            raise ValueError(f"{gate} gate report duplicates check: {check_id}")
        observed_checks.add(check_id)
        undeclared = set(cast(list[str], check["artifact_paths"])) - artifact_paths
        if undeclared:
            raise ValueError(
                f"{gate} gate check {check_id} cites undeclared artifacts: "
                f"{', '.join(sorted(undeclared))}"
            )
    missing_checks = REQUIRED_GATE_CHECKS[gate] - observed_checks
    if missing_checks:
        raise ValueError(
            f"{gate} gate report is missing required checks: {', '.join(sorted(missing_checks))}"
        )


def verify_release_evidence(evidence_dir: Path) -> dict[str, Any]:
    root = evidence_dir.resolve()
    manifest_path = root / MANIFEST_NAME
    digest_path = root / MANIFEST_DIGEST_NAME
    if not manifest_path.is_file() or not digest_path.is_file():
        raise ValueError("release evidence manifest or digest sidecar is missing")
    digest_tokens = digest_path.read_text(encoding="ascii").split()
    if len(digest_tokens) != 2 or digest_tokens[1] != MANIFEST_NAME:
        raise ValueError("release evidence manifest digest sidecar is invalid")
    manifest_sha256 = _sha256_file(manifest_path)
    if digest_tokens[0] != manifest_sha256:
        raise ValueError("release evidence manifest digest mismatch")

    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(RELEASE_EVIDENCE_SCHEMA).iter_errors(loaded), key=str)
    if errors:
        raise ValueError(f"release evidence manifest schema violation: {errors[0].message}")
    manifest = cast(dict[str, Any], loaded)
    if manifest["image_digest"] == "sha256:" + "0" * 64:
        raise ValueError("release image digest is still the non-deployable placeholder")
    _aware_datetime(manifest["created_at"], "created_at")

    observed_gates: set[str] = set()
    observed_paths: set[str] = set()
    for item in manifest["evidence"]:
        gate = cast(str, item["gate"])
        relative_path = cast(str, item["report_path"])
        if gate in observed_gates:
            raise ValueError(f"release evidence gate is duplicated: {gate}")
        if relative_path in observed_paths:
            raise ValueError(f"release evidence report path is reused: {relative_path}")
        observed_gates.add(gate)
        observed_paths.add(relative_path)
        _aware_datetime(item["completed_at"], f"{gate}.completed_at")
        report_path = _safe_report_path(root, relative_path)
        if not report_path.is_file() or report_path.stat().st_size == 0:
            raise ValueError(f"release evidence report is missing or empty: {relative_path}")
        if _sha256_file(report_path) != item["report_sha256"]:
            raise ValueError(f"release evidence report digest mismatch: {relative_path}")
        _verify_gate_report(root, report_path, manifest, cast(dict[str, Any], item))

    missing = REQUIRED_RELEASE_GATES - observed_gates
    if missing:
        raise ValueError(
            f"required release evidence gates are missing: {', '.join(sorted(missing))}"
        )
    return {
        "status": "verified",
        "release_id": manifest["release_id"],
        "commit_sha": manifest["commit_sha"],
        "image_digest": manifest["image_digest"],
        "gate_count": len(observed_gates),
        "manifest_sha256": manifest_sha256,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the complete, content-addressed WindOps release evidence bundle"
    )
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_release_evidence(args.evidence_dir), sort_keys=True))
