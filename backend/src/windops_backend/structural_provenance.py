"""Keep deployment declarations separate from observed calculation versions."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal, Protocol

from windops_backend.operations.hybrid_identity import hybrid_bundle_id


class HybridDeploymentSettings(Protocol):
    """Only the declared deployment identity fields consumed by this verifier."""

    release_id: str
    release_commit_sha: str
    release_image_digest: str
    api_image_digest: str
    structural_image_digest: str
    release_bundle_id: str


RuntimeRole = Literal["api", "structural-worker"]


def execution_code_identity() -> dict[str, str]:
    package = Path(__file__).parent
    return {
        name: hashlib.sha256((package / name).read_bytes()).hexdigest()
        for name in (
            "structural_worker.py",
            "structural_process.py",
            "structural_compute.py",
            "structural_provenance.py",
            "structural_result_identity.py",
        )
    }


def deployment_identity(
    settings: HybridDeploymentSettings, role: RuntimeRole | None = None
) -> dict[str, str] | None:
    """Validate trusted configuration; this does not observe the running OCI image."""
    if not any(
        (settings.api_image_digest, settings.structural_image_digest, settings.release_bundle_id)
    ):
        return None
    bundle = hybrid_bundle_id(
        settings.release_id,
        settings.release_commit_sha,
        settings.api_image_digest,
        settings.structural_image_digest,
    )
    if settings.release_bundle_id != bundle:
        raise ValueError("hybrid runtime bundle identity does not match its two image digests")
    allowed = {
        "api": settings.api_image_digest,
        "structural-worker": settings.structural_image_digest,
    }
    if settings.release_image_digest not in (
        {allowed[role]} if role is not None else set(allowed.values())
    ):
        raise ValueError("hybrid runtime image declaration does not match its process role")
    return {
        "release_id": settings.release_id,
        "commit_sha": settings.release_commit_sha,
        "api_image_digest": settings.api_image_digest,
        "structural_image_digest": settings.structural_image_digest,
        "bundle_id": bundle,
    }


def execution_provenance(
    declared: dict[str, str] | None, actual_algorithm: dict[str, Any]
) -> dict[str, object]:
    return {
        "contract": "openvigil.structural-execution.v1",
        "deployment_declared": declared,
        "runtime_role": "structural-worker",
        "runtime_image_digest_declared": declared["structural_image_digest"] if declared else None,
        "image_identity_assurance": "deployment_declared" if declared else "unbound",
        "algorithm_observed": dict(actual_algorithm),
        "execution_code_sha256": execution_code_identity(),
    }
