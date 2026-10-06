"""Qualify both runtimes only after the legacy eleven gates and structural gates."""

from __future__ import annotations

import argparse
import base64
import copy
import json
import subprocess  # nosec B404
import xml.etree.ElementTree as ET  # nosec B405
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from windops_backend.operations.deployment_policy import verify_deployment_policy
from windops_backend.operations.hybrid_identity import hybrid_bundle_id
from windops_backend.operations.release_gate import (
    GATE_REPORT_SCHEMA,
    MANIFEST_NAME,
    MAX_EVIDENCE_SPAN_SECONDS,
    MAX_REPORT_DURATION_SECONDS,
    _aware_datetime,
    _safe_report_path,
    _verify_image_scan_raw,
    verify_release_evidence,
)
from windops_backend.operations.report_io import sha256_file, write_atomic_json
from windops_backend.operations.structural_artifact import verify_structural_artifact

STRUCTURAL_CHECKS = frozenset(
    {
        "two_image_runtime_identity",
        "dedicated_queue_recovery",
        "modal_and_prestress_closures",
        "scope_and_source_revalidation",
        "raw_object_sha_roundtrip",
        "numeric_method_failure_cases",
        "read_audit_fail_closed",
        "sql_outbox_projection_consistency",
    }
)
STRUCTURAL_ACCEPTANCE_SCHEMA = copy.deepcopy(GATE_REPORT_SCHEMA)
STRUCTURAL_ACCEPTANCE_SCHEMA["properties"]["gate"] = {"const": "structural_runtime"}
_identity_schema = STRUCTURAL_ACCEPTANCE_SCHEMA["properties"]["release"]
_identity_schema["required"] += ["api_image_digest", "bundle_id"]
_identity_schema["properties"].update(
    {
        name: {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
        for name in ("api_image_digest", "bundle_id")
    }
)


def verify_structural_acceptance(root: Path, identity: dict[str, str]) -> dict[str, Any]:
    path = _safe_report_path(root, "reports/structural_runtime.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(STRUCTURAL_ACCEPTANCE_SCHEMA).iter_errors(report), key=str)
    if errors:
        raise ValueError(f"structural acceptance schema violation: {errors[0].message}")
    if report["release"] != identity:
        raise ValueError("structural acceptance is not bound to both release images")
    started = _aware_datetime(report["started_at"], "structural.started_at")
    completed = _aware_datetime(report["completed_at"], "structural.completed_at")
    now = datetime.now(UTC)
    if not 0 <= (completed - started).total_seconds() <= MAX_REPORT_DURATION_SECONDS:
        raise ValueError("structural acceptance has an invalid execution duration")
    if not 0 <= (now - completed).total_seconds() <= MAX_EVIDENCE_SPAN_SECONDS:
        raise ValueError("structural acceptance is stale or from the future")
    artifacts: dict[str, Path] = {}
    for artifact in report["artifacts"]:
        relative = artifact["path"]
        candidate = _safe_report_path(root, relative)
        if (
            relative in artifacts
            or candidate == path
            or not candidate.is_file()
            or not candidate.stat().st_size
        ):
            raise ValueError(
                "structural acceptance artifact is duplicate, empty or self-referential"
            )
        if sha256_file(candidate) != artifact["sha256"]:
            raise ValueError("structural acceptance artifact SHA-256 mismatch")
        artifacts[relative] = candidate
    checks = report["checks"]
    observed = [check["id"] for check in checks]
    if len(observed) != len(set(observed)) or set(observed) != STRUCTURAL_CHECKS:
        raise ValueError("structural acceptance must include every required check exactly once")
    for check in checks:
        if not set(check["artifact_paths"]).issubset(artifacts):
            raise ValueError("structural acceptance check cites an undeclared artifact")
        if check["id"] in {"modal_and_prestress_closures", "scope_and_source_revalidation"}:
            cases: set[tuple[str, str]] = set()
            for relative in check["artifact_paths"]:
                candidate = artifacts[relative]
                if candidate.suffix != ".xml":
                    continue
                data = candidate.read_bytes()
                if len(data) > 8 * 1024 * 1024 or b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                    raise ValueError("structural JUnit input is unsafe or unbounded")
                junit = ET.fromstring(data)  # nosec B314
                if any(junit.findall(".//" + tag) for tag in ("failure", "error", "skipped")):
                    raise ValueError("structural acceptance contains failed or skipped cases")
                for case in junit.findall(".//testcase"):
                    if not case.get("name"):
                        raise ValueError("structural acceptance JUnit case has no identity")
                    cases.add((case.get("classname", ""), case.attrib["name"]))
            minimum = 2 if check["id"] == "modal_and_prestress_closures" else 1
            if len(cases) < minimum:
                raise ValueError("structural acceptance lacks real non-skipped scenario results")
    return cast(dict[str, Any], report)


def _verify_structural_scan(root: Path, identity: dict[str, str]) -> None:
    relative = "structural/image-scan.json"
    _verify_image_scan_raw(
        root,
        identity,
        [
            {"id": name, "artifact_paths": [relative]}
            for name in (
                "immutable_digest_scanned",
                "critical_findings_zero",
                "high_findings_zero",
            )
        ],
    )


def verify_attested_sbom(output: str, sbom: dict[str, Any], image: str) -> None:
    digest = image.rsplit("@sha256:", 1)[-1]
    decoder = json.JSONDecoder()
    remaining = output.strip()
    while remaining:
        loaded, consumed = decoder.raw_decode(remaining)
        remaining = remaining[consumed:].lstrip()
        for item in loaded if isinstance(loaded, list) else [loaded]:
            envelope = item.get("dsseEnvelope", item)
            payload = envelope.get("payload")
            if not isinstance(payload, str):
                continue
            statement = json.loads(base64.b64decode(payload, validate=True))
            if statement.get("predicateType") != "https://spdx.dev/Document":
                continue
            if statement.get("predicate") != sbom:
                continue
            if any(
                subject.get("digest", {}).get("sha256") == digest
                for subject in statement.get("subject", [])
            ):
                return
    raise ValueError("verified SPDX attestation does not bind this SBOM to the structural digest")


def _verify_structural_supply_chain(root: Path, image: str, source_url: str) -> None:
    # Re-execute signature policy at qualification; a saved 'passed' JSON is insufficient.
    common = [
        "--certificate-identity",
        source_url + "/.github/workflows/release.yml@refs/heads/main",
        "--certificate-oidc-issuer",
        "https://token.actions.githubusercontent.com",
    ]
    outputs = []
    for command in (
        ["cosign", "verify", *common, image],
        ["cosign", "verify-attestation", "--type", "spdxjson", *common, image],
    ):
        result = subprocess.run(  # nosec B603
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if not result.stdout.strip():
            raise ValueError("structural signature or SBOM verification returned no evidence")
        outputs.append(result.stdout)
    sbom_path = _safe_report_path(root, "structural/sbom.spdx.json")
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    if (
        not isinstance(sbom.get("spdxVersion"), str)
        or not sbom["spdxVersion"].startswith("SPDX-2.")
        or not sbom.get("packages")
    ):
        raise ValueError("structural SBOM must contain a validated SPDX package inventory")
    verify_attested_sbom(outputs[1], sbom, image)


def verify_hybrid_release(
    *,
    evidence_dir: Path,
    release_id: str,
    commit_sha: str,
    api_image: str,
    structural_image: str,
    source_url: str,
    policy: Path,
    lock: Path,
) -> dict[str, Any]:
    root = evidence_dir.resolve()
    api = verify_release_evidence(root)
    api_digest, structural_digest = (
        api_image.rsplit("@", 1)[-1],
        structural_image.rsplit("@", 1)[-1],
    )
    bundle_id = hybrid_bundle_id(release_id, commit_sha, api_digest, structural_digest)
    if any(
        api[key] != value
        for key, value in {
            "release_id": release_id,
            "commit_sha": commit_sha,
            "image_digest": api_digest,
        }.items()
    ):
        raise ValueError("hybrid bundle does not match the verified eleven-gate API release")
    identity = {
        "release_id": release_id,
        "commit_sha": commit_sha,
        "api_image_digest": api_digest,
        "image_digest": structural_digest,
        "bundle_id": bundle_id,
        "evidence_set_id": bundle_id,
    }
    acceptance = verify_structural_acceptance(root, identity)
    api_manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    completions = [
        _aware_datetime(item["completed_at"], "api.completed_at")
        for item in api_manifest["evidence"]
    ] + [_aware_datetime(acceptance["completed_at"], "structural.completed_at")]
    if (max(completions) - min(completions)).total_seconds() > MAX_EVIDENCE_SPAN_SECONDS:
        raise ValueError("two-image reports span different release windows")
    manifests = _safe_report_path(root, "structural/rendered-manifests.yaml")
    deployment = verify_deployment_policy(
        manifests,
        expected_release_id=release_id,
        expected_commit_sha=commit_sha,
        expected_image_digest=api_digest,
        expected_structural_image_digest=structural_digest,
        approved_backup_storage_class=json.loads(policy.read_text())[
            "approved_backup_storage_class"
        ],
    )
    _verify_structural_scan(root, identity)
    _verify_structural_supply_chain(root, structural_image, source_url)
    artifact = verify_structural_artifact(
        image=structural_image,
        api_image=api_image,
        release_id=release_id,
        commit_sha=commit_sha,
        source_url=source_url,
        policy_path=policy,
        lock_path=lock,
    )
    paths = {
        "release-evidence.json",
        "release-evidence.sha256",
        "reports/structural_runtime.json",
        "structural/image-scan.json",
        "structural/sbom.spdx.json",
        "structural/rendered-manifests.yaml",
    }
    paths.update(item["path"] for item in acceptance["artifacts"])
    return {
        "format_version": 1,
        "status": "qualified",
        "release_id": release_id,
        "commit_sha": commit_sha,
        "api_image": api_image,
        "structural_image": structural_image,
        "api_image_digest": api_digest,
        "structural_image_digest": structural_digest,
        "bundle_id": bundle_id,
        "verified_at": datetime.now(UTC).isoformat(),
        "api_gate_count": api["gate_count"],
        "api_manifest_sha256": api["manifest_sha256"],
        "structural_acceptance": acceptance,
        "structural_artifact": artifact,
        "deployment": deployment,
        "artifacts_sha256": {
            relative: sha256_file(_safe_report_path(root, relative)) for relative in sorted(paths)
        },
        "field_qualification": "unverified",
        "verifier": "windops-hybrid-release-gate.v1",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("release-id", "commit-sha", "api-image", "structural-image", "source-url"):
        parser.add_argument("--" + name, required=True)
    for name in ("evidence-dir", "policy", "lock", "qualification-output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.qualification_output.exists() or args.qualification_output.is_symlink():
        raise ValueError("hybrid qualification output already exists or is unsafe")
    report = verify_hybrid_release(
        evidence_dir=args.evidence_dir,
        release_id=args.release_id,
        commit_sha=args.commit_sha,
        api_image=args.api_image,
        structural_image=args.structural_image,
        source_url=args.source_url,
        policy=args.policy,
        lock=args.lock,
    )
    write_atomic_json(
        args.qualification_output, report, symlink_error=ValueError("unsafe qualification path")
    )
    print(json.dumps({key: report[key] for key in ("status", "bundle_id", "api_gate_count")}))


if __name__ == "__main__":
    main()
