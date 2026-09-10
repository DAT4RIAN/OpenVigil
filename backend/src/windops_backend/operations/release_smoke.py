from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import subprocess  # nosec B404
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, cast

from windops_backend.operations.container_artifact import ContainerArtifactError


def _run(command: list[str], *, capture: bool = True) -> str:
    completed = subprocess.run(  # nosec B603
        command, check=True, capture_output=capture, text=True
    )
    return completed.stdout if capture else ""


def _runtime_environment(
    *,
    database_url: str,
    neo4j_uri: str,
    neo4j_password: str,
    release_id: str,
    commit_sha: str,
    image_digest: str,
) -> list[str]:
    values = {
        "WINDOPS_ENVIRONMENT": "development",
        "WINDOPS_DATABASE_URL": database_url,
        "WINDOPS_NEO4J_URI": neo4j_uri,
        "WINDOPS_NEO4J_USER": "neo4j",
        "WINDOPS_NEO4J_PASSWORD": neo4j_password,
        "WINDOPS_BIND_HOST": "0.0.0.0",  # nosec B104
        "WINDOPS_RELEASE_ID": release_id,
        "WINDOPS_RELEASE_COMMIT_SHA": commit_sha,
        "WINDOPS_RELEASE_IMAGE_DIGEST": image_digest,
    }
    return [argument for name, value in values.items() for argument in ("--env", f"{name}={value}")]


def _request(path: str, port: int) -> tuple[dict[str, Any], dict[str, str]]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        if response.status != 200:
            raise OSError(f"release smoke endpoint returned HTTP {response.status}")
        payload = cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
        headers = {name.lower(): value for name, value in response.getheaders()}
        return payload, headers
    finally:
        connection.close()


def smoke_release_image(
    *,
    image: str,
    network: str,
    database_url: str,
    neo4j_uri: str,
    neo4j_password: str,
    release_id: str,
    commit_sha: str,
    image_digest: str,
    port: int,
) -> dict[str, Any]:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None:
        raise ContainerArtifactError("release smoke requires a SHA-256 image digest")
    container_name = "windops-release-image-smoke"
    if _run(
        ["docker", "ps", "-a", "--filter", f"name=^{container_name}$", "--format", "{{.Names}}"]
    ):
        raise ContainerArtifactError(f"refusing to replace existing container {container_name}")
    environment = _runtime_environment(
        database_url=database_url,
        neo4j_uri=neo4j_uri,
        neo4j_password=neo4j_password,
        release_id=release_id,
        commit_sha=commit_sha,
        image_digest=image_digest,
    )
    hardened = [
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=128m",  # nosec B108
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "10001:10001",
    ]
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            network,
            *hardened,
            *environment,
            image,
            "alembic",
            "upgrade",
            "head",
        ],
        capture=False,
    )
    try:
        _run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                container_name,
                "--network",
                network,
                "--publish",
                f"127.0.0.1:{port}:8000",
                *hardened,
                *environment,
                image,
            ]
        )
        deadline = time.monotonic() + 120
        last_error = "API did not answer"
        while time.monotonic() < deadline:
            try:
                health, _ = _request("/api/v1/healthz", port)
                ready, _ = _request("/api/v1/readyz", port)
                break
            except (OSError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                time.sleep(1)
        else:
            logs = _run(["docker", "logs", container_name])
            raise ContainerArtifactError(
                f"release image did not become ready: {last_error}\n{logs}"
            )
        if health != {"status": "ok"} or ready.get("status") != "ready":
            raise ContainerArtifactError("release image health or readiness response is invalid")
        health_deadline = time.monotonic() + 45
        while time.monotonic() < health_deadline:
            health_state = json.loads(
                _run(["docker", "inspect", container_name, "--format", "{{json .State.Health}}"])
            )
            if health_state.get("Status") == "healthy":
                break
            if health_state.get("Status") == "unhealthy":
                raise ContainerArtifactError("Docker health check became unhealthy")
            time.sleep(1)
        else:
            raise ContainerArtifactError("Docker health check did not become healthy")
        return {
            "format_version": 1,
            "gate": "release_image_smoke",
            "status": "passed",
            "image": image,
            "release_id": release_id,
            "commit_sha": commit_sha,
            "image_digest": image_digest,
            "checks": [
                "migration_from_image",
                "read_only_non_root_runtime",
                "health_endpoint",
                "readiness_endpoint",
                "docker_healthcheck",
                "release_configuration_injected",
            ],
        }
    finally:
        subprocess.run(  # nosec B603 B607
            ["docker", "rm", "--force", container_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _write_report(path: Path, report: dict[str, Any]) -> None:
    if path.is_symlink():
        raise ContainerArtifactError("smoke report cannot overwrite a symbolic link")
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run migration and API smoke from a release image")
    parser.add_argument("--image", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--neo4j-uri", required=True)
    parser.add_argument("--neo4j-password", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--port", type=int, default=18000)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = smoke_release_image(
            image=args.image,
            network=args.network,
            database_url=args.database_url,
            neo4j_uri=args.neo4j_uri,
            neo4j_password=args.neo4j_password,
            release_id=args.release_id,
            commit_sha=args.commit_sha,
            image_digest=args.image_digest,
            port=args.port,
        )
        _write_report(args.report, report)
    except (ContainerArtifactError, OSError, subprocess.SubprocessError) as exc:
        print(
            json.dumps({"gate": "release_image_smoke", "status": "failed", "error": str(exc)}),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
