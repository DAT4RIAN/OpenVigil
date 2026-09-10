from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, cast


class CareFullScaleAcceptanceError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CareFullScaleAcceptanceError(f"{field} must be an object")
    return cast(dict[str, Any], value)


def _exact_keys(value: dict[str, Any], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise CareFullScaleAcceptanceError(f"{field} fields do not match the acceptance schema")


def _load_json(path: Path, field: str) -> dict[str, Any]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), field)
    except (OSError, json.JSONDecodeError) as exc:
        raise CareFullScaleAcceptanceError(f"{field} is not valid UTF-8 JSON") from exc


def verify_care_fullscale_acceptance(
    evidence_path: Path,
    evidence_root: Path,
    storage_policy: Path,
    *,
    expected_release_id: str,
    expected_commit_sha: str,
    expected_image_digest: str,
) -> dict[str, Any]:
    if evidence_path.is_symlink() or storage_policy.is_symlink():
        raise CareFullScaleAcceptanceError("CARE acceptance inputs cannot be symbolic links")
    root = evidence_root.resolve()
    expected_evidence_path = root / "artifacts" / "care" / "care-full-scale-release-evidence.json"
    if evidence_path.resolve() != expected_evidence_path:
        raise CareFullScaleAcceptanceError("CARE acceptance evidence path is not canonical")
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected_commit_sha) is None:
        raise CareFullScaleAcceptanceError("expected CARE commit SHA is invalid")
    if (
        re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image_digest) is None
        or expected_image_digest == "sha256:" + "0" * 64
    ):
        raise CareFullScaleAcceptanceError("expected CARE image digest is invalid")
    try:
        document = _load_json(evidence_path, "evidence")
    except (OSError, json.JSONDecodeError) as exc:
        raise CareFullScaleAcceptanceError("CARE acceptance evidence is unreadable") from exc
    _exact_keys(
        document,
        {
            "format_version",
            "gate",
            "status",
            "release",
            "workload",
            "source",
            "dependency_closure",
            "import",
            "evaluation",
            "registration",
            "storage",
            "approval",
            "artifacts",
        },
        "evidence",
    )
    if (
        document["format_version"] != 1
        or document["gate"] != "care_full_scale_acceptance"
        or document["status"] != "passed"
    ):
        raise CareFullScaleAcceptanceError("CARE acceptance did not pass the required gate")
    expected_release = {
        "release_id": expected_release_id,
        "commit_sha": expected_commit_sha,
        "image_digest": expected_image_digest,
    }
    if _mapping(document["release"], "release") != expected_release:
        raise CareFullScaleAcceptanceError("CARE acceptance release identity drifted")
    workload = _mapping(document["workload"], "workload")
    if workload != {
        "name": "windops-care-full-scale",
        "queue": "care-v6-offline",
        "max_concurrency": 1,
        "max_attempts": 3,
        "active_deadline_seconds": 72000,
    }:
        raise CareFullScaleAcceptanceError("CARE execution limits drifted")
    source = _mapping(document["source"], "source")
    if source.get("approved") is not True or source.get("read_only") is not True:
        raise CareFullScaleAcceptanceError("CARE source was not approved and mounted read-only")
    dependency = _mapping(document["dependency_closure"], "dependency_closure")
    if dependency.get("status") != "passed":
        raise CareFullScaleAcceptanceError("CARE dependency closure did not pass")
    imported = _mapping(document["import"], "import")
    if imported != {
        "status": "passed",
        "state_status": "completed",
        "limits_passed": True,
        "replayed": True,
    }:
        raise CareFullScaleAcceptanceError("CARE import checkpoint or replay acceptance failed")
    evaluated = _mapping(document["evaluation"], "evaluation")
    if evaluated != {
        "status": "passed",
        "state_status": "completed",
        "limits_passed": True,
        "replayed": True,
        "fold_count": 36,
        "event_count": 95,
        "cross_farm_status": "disabled",
    }:
        raise CareFullScaleAcceptanceError("CARE full evaluation acceptance failed")
    registration = _mapping(document["registration"], "registration")
    if registration != {"status": "passed", "transactional": True, "replayed": True}:
        raise CareFullScaleAcceptanceError("CARE database registration was not idempotent")
    storage = _mapping(document["storage"], "storage")
    required_denials = {
        "windops-field-evidence",
        "windops-knowledge-documents",
        "windops-model-artifacts",
        "windops-twin-artifacts",
    }
    if (
        storage.get("bucket") != "windops-care-benchmarks"
        or storage.get("tls") is not True
        or storage.get("delete_object_allowed") is not False
        or set(storage.get("access_denied_buckets", [])) != required_denials
        or storage.get("policy_sha256") != _sha256(storage_policy)
    ):
        raise CareFullScaleAcceptanceError("CARE scoped storage acceptance failed")
    approval = _mapping(document["approval"], "approval")
    if (
        not str(approval.get("approved_by", "")).strip()
        or not str(approval.get("approval_reference", "")).strip()
    ):
        raise CareFullScaleAcceptanceError("CARE acceptance lacks independent approval")

    artifacts = document["artifacts"]
    required_roles = {
        "dependency_closure",
        "import_manifest",
        "evaluation_manifest",
        "import_state",
        "evaluation_state",
        "import_replay",
        "evaluation_replay",
        "registration",
        "registration_replay",
        "storage_scope",
    }
    if not isinstance(artifacts, list) or len(artifacts) != len(required_roles):
        raise CareFullScaleAcceptanceError("CARE acceptance requires full raw artifacts")
    observed_paths: set[str] = set()
    observed_roles: dict[str, Path] = {}
    for index, raw_artifact in enumerate(artifacts):
        artifact = _mapping(raw_artifact, f"artifacts[{index}]")
        _exact_keys(artifact, {"role", "path", "sha256", "media_type"}, f"artifacts[{index}]")
        relative = Path(str(artifact["path"]))
        target = (root / relative).resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not target.is_relative_to(root)
            or target.is_symlink()
            or not target.is_file()
            or target.stat().st_size <= 0
        ):
            raise CareFullScaleAcceptanceError("CARE acceptance artifact path is unsafe")
        normalized = relative.as_posix()
        if not normalized.startswith("artifacts/care/fullscale/") or normalized in observed_paths:
            raise CareFullScaleAcceptanceError("CARE acceptance artifact scope is invalid")
        observed_paths.add(normalized)
        role = artifact["role"]
        if not isinstance(role, str) or role in observed_roles:
            raise CareFullScaleAcceptanceError("CARE acceptance artifact role is invalid")
        observed_roles[role] = target
        if artifact["sha256"] != _sha256(target):
            raise CareFullScaleAcceptanceError("CARE acceptance artifact digest mismatch")
    if set(observed_roles) != required_roles:
        raise CareFullScaleAcceptanceError("CARE acceptance artifact roles are incomplete")

    raw_dependency = _load_json(observed_roles["dependency_closure"], "dependency artifact")
    if raw_dependency.get("status") != "passed":
        raise CareFullScaleAcceptanceError("CARE dependency artifact did not pass")
    import_manifest = _load_json(observed_roles["import_manifest"], "import manifest")
    evaluation_manifest = _load_json(observed_roles["evaluation_manifest"], "evaluation manifest")
    import_summary = _mapping(import_manifest.get("summary"), "import summary")
    evaluation_summary = _mapping(evaluation_manifest.get("summary"), "evaluation summary")
    if (
        import_manifest.get("schema_version") != "care-v6-full-scale-import-manifest-v1"
        or import_manifest.get("raw_source_unchanged") is not True
        or import_summary.get("event_count") != 95
        or import_summary.get("farm_namespaced_asset_count") != 36
        or _mapping(import_manifest.get("resource_actual"), "import resources").get("limits_passed")
        is not True
    ):
        raise CareFullScaleAcceptanceError("CARE raw import manifest failed acceptance")
    if (
        evaluation_manifest.get("schema_version") != "care-v6-full-scale-evaluation-manifest-v1"
        or evaluation_summary.get("event_count") != 95
        or evaluation_summary.get("fold_count") != 36
        or evaluation_summary.get("all_events_accounted_for") is not True
        or _mapping(evaluation_manifest.get("cross_farm_protocol"), "cross-farm protocol").get(
            "status"
        )
        != "disabled"
        or _mapping(evaluation_manifest.get("resource_actual"), "evaluation resources").get(
            "limits_passed"
        )
        is not True
    ):
        raise CareFullScaleAcceptanceError("CARE raw evaluation manifest failed acceptance")
    for role, operation in (("import_state", "import"), ("evaluation_state", "evaluate")):
        state = _load_json(observed_roles[role], f"{operation} state")
        if (
            state.get("operation") != operation
            or state.get("status") != "completed"
            or state.get("max_attempts") != 3
            or state.get("progress_total") != 95
            or state.get("progress_completed") != 95
            or _mapping(state.get("resource_stats"), f"{operation} resource stats").get(
                "limits_passed"
            )
            is not True
        ):
            raise CareFullScaleAcceptanceError(f"CARE {operation} checkpoint state failed")
    for role, manifest_role in (
        ("import_replay", "import_manifest"),
        ("evaluation_replay", "evaluation_manifest"),
    ):
        replay = _load_json(observed_roles[role], f"{role} artifact")
        if replay.get("replayed") is not True or replay.get("manifest_file_sha256") != _sha256(
            observed_roles[manifest_role]
        ):
            raise CareFullScaleAcceptanceError(f"CARE {role} did not replay the same manifest")
    registration_result = _load_json(observed_roles["registration"], "registration artifact")
    registration_replay = _load_json(
        observed_roles["registration_replay"], "registration replay artifact"
    )
    if (
        registration_result.get("import_created_count", 0) <= 0
        or registration_result.get("evaluation_created_count", 0) <= 0
        or registration_replay.get("import_created_count") != 0
        or registration_replay.get("evaluation_created_count") != 0
        or registration_replay.get("import_replayed_count", 0) <= 0
        or registration_replay.get("evaluation_replayed_count", 0) <= 0
    ):
        raise CareFullScaleAcceptanceError("CARE registration raw replay evidence failed")
    if _load_json(observed_roles["storage_scope"], "storage scope artifact") != storage:
        raise CareFullScaleAcceptanceError("CARE storage summary drifted from its raw proof")
    return {
        "format_version": 1,
        "gate": "care_full_scale_acceptance",
        "status": "passed",
        "release": expected_release,
        "evidence_sha256": _sha256(evidence_path),
        "storage_policy_sha256": _sha256(storage_policy),
        "artifact_count": len(required_roles),
        "approved_by": approval["approved_by"],
        "approval_reference": approval["approval_reference"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify protected CARE full-scale acceptance")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--storage-policy", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = verify_care_fullscale_acceptance(
        args.evidence,
        args.evidence_root,
        args.storage_policy,
        expected_release_id=args.release_id,
        expected_commit_sha=args.commit_sha,
        expected_image_digest=args.image_digest,
    )
    if args.report.exists() or args.report.is_symlink():
        raise CareFullScaleAcceptanceError("CARE acceptance report must be a new file")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
