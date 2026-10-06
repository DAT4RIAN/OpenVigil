"""Verify the dedicated Linux scientific image against its exact API parent."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

from windops_backend.operations.container_artifact import (
    ContainerArtifactError,
    _release_digest,
    load_release_policy,
    verify_image_inspect,
)
from windops_backend.operations.report_io import sha256_file, write_atomic_json

STRUCTURAL_COMMAND = [
    "dramatiq",
    "windops_backend.structural_tasks",
    "--queues",
    "structural-analysis",
    "--processes",
    "1",
    "--threads",
    "1",
]


def _run(command: list[str]) -> str:
    return subprocess.run(  # nosec B603
        command, check=True, capture_output=True, text=True, timeout=300
    ).stdout


def verify_structural_inspect(
    inspected: dict[str, Any],
    api_inspected: dict[str, Any],
    *,
    image: str,
    api_image: str,
    release_id: str,
    commit_sha: str,
    source_url: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    api = verify_image_inspect(
        api_inspected,
        image=api_image,
        release_id=release_id,
        commit_sha=commit_sha,
        source_url=source_url,
        policy=policy,
    )
    digest = _release_digest(image)
    if digest == api["image_digest"]:
        raise ContainerArtifactError("structural and API images must have separate digests")
    if image not in inspected.get("RepoDigests", []):
        raise ContainerArtifactError("structural image is not bound to the requested digest")
    if inspected.get("Os") != "linux" or inspected.get("Architecture") != "amd64":
        raise ContainerArtifactError("structural image requires linux/amd64")
    config = inspected.get("Config", {})
    if (
        config.get("User") != "10001:10001"
        or config.get("Cmd") != STRUCTURAL_COMMAND
        or config.get("Entrypoint") not in (None, [])
        or config.get("Healthcheck", {}).get("Test") != ["NONE"]
    ):
        raise ContainerArtifactError(
            "structural image requires the isolated non-root queue command"
        )
    labels = config.get("Labels", {})
    expected = {
        "org.opencontainers.image.version": release_id,
        "org.opencontainers.image.revision": commit_sha,
        "org.opencontainers.image.source": source_url,
        "org.opencontainers.image.base.name": api_image,
        "org.windops.postgresql-client.image": policy["postgres_client_image"],
        "org.windops.postgresql-client.major": str(policy["postgres_client_major"]),
    }
    if any(labels.get(name) != value for name, value in expected.items()):
        raise ContainerArtifactError("structural image labels differ from the approved API parent")
    environment = config.get("Env", [])
    for name, value in {
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "MPLBACKEND": "Agg",
    }.items():
        if sum(item == f"{name}={value}" for item in environment) != 1:
            raise ContainerArtifactError(
                "structural image requires bounded numeric thread settings"
            )
    api_layers = api_inspected.get("RootFS", {}).get("Layers", [])
    layers = inspected.get("RootFS", {}).get("Layers", [])
    if not api_layers or len(layers) <= len(api_layers) or layers[: len(api_layers)] != api_layers:
        raise ContainerArtifactError("structural layers do not extend the exact API image")
    return {
        "image": image,
        "image_digest": digest,
        "api_image": api_image,
        "api_image_digest": api["image_digest"],
        "release_id": release_id,
        "commit_sha": commit_sha,
        "source_url": source_url,
        "platform": "linux/amd64",
    }


def verify_structural_artifact(
    *,
    image: str,
    api_image: str,
    release_id: str,
    commit_sha: str,
    source_url: str,
    policy_path: Path,
    lock_path: Path,
) -> dict[str, Any]:
    for reference in (api_image, image):
        _release_digest(reference)
        _run(["docker", "pull", reference])
    api = json.loads(_run(["docker", "image", "inspect", api_image]))[0]
    structural = json.loads(_run(["docker", "image", "inspect", image]))[0]
    identity = verify_structural_inspect(
        structural,
        api,
        image=image,
        api_image=api_image,
        release_id=release_id,
        commit_sha=commit_sha,
        source_url=source_url,
        policy=load_release_policy(policy_path),
    )
    output = _run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--user",
            "10001:10001",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m",  # nosec B108
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--entrypoint",
            "python",
            image,
            "-m",
            "windops_backend.operations.structural_smoke",
        ]
    )
    runtime = json.loads(output.splitlines()[-1])
    if runtime["dependency_closure"]["requirements_lock_sha256"] != sha256_file(lock_path):
        raise ContainerArtifactError("structural runtime lock differs from the build source")
    return {
        "format_version": 1,
        "gate": "structural_container",
        "status": "passed",
        "identity": identity,
        "runtime": runtime,
        "api_inspect": api,
        "structural_inspect": structural,
        "policy_sha256": sha256_file(policy_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("image", "api-image", "release-id", "commit-sha", "source-url"):
        parser.add_argument("--" + name, required=True)
    for name in ("policy", "lock", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = verify_structural_artifact(
        image=args.image,
        api_image=args.api_image,
        release_id=args.release_id,
        commit_sha=args.commit_sha,
        source_url=args.source_url,
        policy_path=args.policy,
        lock_path=args.lock,
    )
    write_atomic_json(
        args.report, report, symlink_error=ContainerArtifactError("unsafe report path")
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"structural image verification failed: {type(exc).__name__}") from exc
