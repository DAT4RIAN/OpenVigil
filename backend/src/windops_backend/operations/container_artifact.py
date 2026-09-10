from __future__ import annotations

import argparse
import json
import re
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any, cast

from windops_backend.operations.report_io import write_atomic_json


class ContainerArtifactError(ValueError):
    """Raised when a built image is not the approved release artifact."""


def _run(command: list[str]) -> str:
    completed = subprocess.run(  # nosec B603
        command, check=True, capture_output=True, text=True
    )
    return completed.stdout


def load_release_policy(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContainerArtifactError("release policy must be valid UTF-8 JSON") from exc
    if not isinstance(loaded, dict) or set(loaded) != {
        "format_version",
        "python_base_image",
        "postgres_client_image",
        "postgres_client_major",
        "platform",
        "approved_backup_storage_class",
        "required_workloads",
        "required_entrypoints",
    }:
        raise ContainerArtifactError("release policy fields do not match the supported format")
    if loaded["format_version"] != 1 or loaded["platform"] != "linux/amd64":
        raise ContainerArtifactError("release policy version or platform is unsupported")
    for field, label in (
        ("python_base_image", "Python base image"),
        ("postgres_client_image", "PostgreSQL client image"),
    ):
        image = loaded[field]
        if (
            not isinstance(image, str)
            or re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image) is None
            or image.endswith("sha256:" + "0" * 64)
        ):
            raise ContainerArtifactError(f"approved {label} must use a non-placeholder digest")
    if loaded["postgres_client_major"] != 16:
        raise ContainerArtifactError("PostgreSQL client major must match the production major 16")
    for field in ("required_workloads", "required_entrypoints"):
        values = loaded[field]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value for value in values)
            or len(values) != len(set(values))
        ):
            raise ContainerArtifactError(f"release policy {field} must be unique non-empty strings")
    return cast(dict[str, Any], loaded)


def _release_digest(image: str) -> str:
    match = re.fullmatch(r"([^\s@]+)@(sha256:[0-9a-f]{64})", image)
    if match is None:
        raise ContainerArtifactError("release image must be addressed by one immutable digest")
    repository, digest = match.groups()
    if repository.startswith("registry.invalid/") or digest == "sha256:" + "0" * 64:
        raise ContainerArtifactError("release image cannot use a placeholder")
    return digest


def verify_image_inspect(
    inspect: dict[str, Any],
    *,
    image: str,
    release_id: str,
    commit_sha: str,
    source_url: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    digest = _release_digest(image)
    if re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", release_id
    ) is None or release_id.lower() in {"development", "unknown", "unreleased"}:
        raise ContainerArtifactError("release ID is invalid or a placeholder")
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit_sha) is None:
        raise ContainerArtifactError("commit SHA must be a full lowercase Git SHA")
    repo_digests = inspect.get("RepoDigests")
    if not isinstance(repo_digests, list) or image not in repo_digests:
        raise ContainerArtifactError("local image metadata is not bound to the requested digest")
    config = inspect.get("Config")
    if not isinstance(config, dict):
        raise ContainerArtifactError("Docker inspect output is missing image configuration")
    if config.get("User") != "10001:10001":
        raise ContainerArtifactError("release image must run as UID/GID 10001")
    if config.get("Cmd") != ["windops-api"]:
        raise ContainerArtifactError("release image default command must be windops-api")
    labels = config.get("Labels")
    if not isinstance(labels, dict):
        raise ContainerArtifactError("release image is missing OCI labels")
    expected_labels = {
        "org.opencontainers.image.version": release_id,
        "org.opencontainers.image.revision": commit_sha,
        "org.opencontainers.image.source": source_url,
        "org.opencontainers.image.base.name": policy["python_base_image"],
        "org.windops.postgresql-client.image": policy["postgres_client_image"],
        "org.windops.postgresql-client.major": str(policy["postgres_client_major"]),
    }
    for name, value in expected_labels.items():
        if labels.get(name) != value:
            raise ContainerArtifactError(f"release image label {name} does not match")
    healthcheck = config.get("Healthcheck")
    test = healthcheck.get("Test") if isinstance(healthcheck, dict) else None
    if not isinstance(test, list) or not any("/api/v1/healthz" in str(value) for value in test):
        raise ContainerArtifactError("release image must define the API health check")
    return {
        "image": image,
        "image_digest": digest,
        "release_id": release_id,
        "commit_sha": commit_sha,
        "source_url": source_url,
        "user": config["User"],
        "command": config["Cmd"],
        "base_image": policy["python_base_image"],
        "postgres_client_image": policy["postgres_client_image"],
        "postgres_client_major": policy["postgres_client_major"],
    }


def _runtime_probe(
    image: str, required_entrypoints: list[str], postgres_client_major: int
) -> dict[str, Any]:
    program = r"""
import importlib.util
import json
import pathlib
import re
import shutil
import subprocess

entrypoints = json.loads(__import__('os').environ['WINDOPS_REQUIRED_ENTRYPOINTS'])
missing = [name for name in entrypoints if shutil.which(name) is None]
if missing:
    raise SystemExit(f"missing entrypoints: {', '.join(missing)}")
required = [
    pathlib.Path('/app/alembic.ini'),
    pathlib.Path('/app/alembic/versions'),
    pathlib.Path('/app/requirements.container.txt'),
    pathlib.Path('/app/care-benchmark-dependency-closure.json'),
]
if any(not path.exists() for path in required):
    raise SystemExit('migration payload or dependency lock is missing')
requirements_lock = required[2]
lock = requirements_lock.read_text(encoding='utf-8')
if '--hash=sha256:' not in lock:
    raise SystemExit('container dependency lock is not hash locked')
persisted_closure = json.loads(required[3].read_text(encoding='utf-8'))
closure_output = subprocess.run(
    [
        'windops-care-dependency-closure',
        '--requirements-lock',
        str(requirements_lock),
    ],
    check=True,
    capture_output=True,
    text=True,
).stdout
runtime_closure = json.loads(closure_output.splitlines()[-1])
if persisted_closure != runtime_closure:
    raise SystemExit('CARE benchmark dependency closure drifted after image build')
if importlib.util.find_spec('pytest') is not None:
    raise SystemExit('test dependencies must not be installed in the runtime image')
subprocess.run([shutil.which('python'), '-m', 'pip', 'check'], check=True)
expected_postgres_major = int(__import__('os').environ['WINDOPS_POSTGRES_CLIENT_MAJOR'])
postgres_clients = {}
for executable in ('pg_dump', 'pg_restore', 'psql'):
    version = subprocess.run(
        [executable, '--version'], check=True, capture_output=True, text=True
    ).stdout.strip()
    match = re.search(r'(\d+)\.', version)
    if match is None or int(match.group(1)) != expected_postgres_major:
        raise SystemExit(
            f'{executable} must exactly match PostgreSQL major {expected_postgres_major}'
        )
    postgres_clients[executable] = version
print(json.dumps({
    'entrypoints': entrypoints,
    'dependency_lock': 'hash-locked',
    'care_benchmark_dependency_closure': runtime_closure,
    'pip_check': 'passed',
    'postgres_clients': postgres_clients,
}))
"""
    output = _run(
        [
            "docker",
            "run",
            "--rm",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",  # nosec B108
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "10001:10001",
            "--env",
            f"WINDOPS_REQUIRED_ENTRYPOINTS={json.dumps(required_entrypoints)}",
            "--env",
            f"WINDOPS_POSTGRES_CLIENT_MAJOR={postgres_client_major}",
            "--entrypoint",
            "python",
            image,
            "-c",
            program,
        ]
    )
    return cast(dict[str, Any], json.loads(output.splitlines()[-1]))


def verify_container_artifact(
    *,
    image: str,
    release_id: str,
    commit_sha: str,
    source_url: str,
    policy_path: Path,
) -> dict[str, Any]:
    policy = load_release_policy(policy_path)
    _release_digest(image)
    _run(["docker", "pull", image])
    inspected = json.loads(_run(["docker", "image", "inspect", image]))
    if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(inspected[0], dict):
        raise ContainerArtifactError("Docker inspect returned an unexpected image result")
    identity = verify_image_inspect(
        inspected[0],
        image=image,
        release_id=release_id,
        commit_sha=commit_sha,
        source_url=source_url,
        policy=policy,
    )
    runtime = _runtime_probe(
        image,
        cast(list[str], policy["required_entrypoints"]),
        cast(int, policy["postgres_client_major"]),
    )
    return {
        "format_version": 1,
        "gate": "container_artifact",
        "status": "passed",
        "identity": identity,
        "runtime": runtime,
        "checks": [
            "approved_base_digest",
            "approved_postgresql_client_digest",
            "immutable_release_digest",
            "release_labels",
            "non_root_user",
            "healthcheck",
            "entrypoints",
            "migration_payload",
            "hash_locked_dependencies",
            "runtime_dependency_check",
            "care_benchmark_dependency_closure",
            "postgresql_client_major_exact",
            "no_test_dependencies",
        ],
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    write_atomic_json(
        path,
        report,
        symlink_error=ContainerArtifactError("container report cannot overwrite a symbolic link"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a pushed OpenVigil release image")
    parser.add_argument("--image", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify_container_artifact(
            image=args.image,
            release_id=args.release_id,
            commit_sha=args.commit_sha,
            source_url=args.source_url,
            policy_path=args.policy,
        )
        _write_report(args.report, report)
    except (ContainerArtifactError, OSError, subprocess.SubprocessError) as exc:
        print(
            json.dumps({"gate": "container_artifact", "status": "failed", "error": str(exc)}),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
