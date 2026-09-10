import json
from pathlib import Path

import pytest

from windops_backend.operations.container_artifact import (
    ContainerArtifactError,
    load_release_policy,
    verify_image_inspect,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = BACKEND_ROOT / "deploy" / "release-policy.json"
IMAGE_DIGEST = "sha256:" + "b" * 64
IMAGE = f"ghcr.io/windops/windops-backend@{IMAGE_DIGEST}"
RELEASE_ID = "windops-2026.08.19-rc1"
COMMIT_SHA = "a" * 40
SOURCE_URL = "https://github.com/windops/wind-agent"


def _inspect(policy: dict[str, object]) -> dict[str, object]:
    return {
        "RepoDigests": [IMAGE],
        "Config": {
            "User": "10001:10001",
            "Cmd": ["windops-api"],
            "Labels": {
                "org.opencontainers.image.version": RELEASE_ID,
                "org.opencontainers.image.revision": COMMIT_SHA,
                "org.opencontainers.image.source": SOURCE_URL,
                "org.opencontainers.image.base.name": policy["python_base_image"],
                "org.windops.postgresql-client.image": policy["postgres_client_image"],
                "org.windops.postgresql-client.major": str(policy["postgres_client_major"]),
            },
            "Healthcheck": {
                "Test": [
                    "CMD",
                    "python",
                    "-c",
                    "open('http://127.0.0.1:8000/api/v1/healthz')",
                ]
            },
        },
    }


def test_release_policy_and_image_identity_are_digest_bound() -> None:
    policy = load_release_policy(POLICY_PATH)
    assert "windops-care-full-scale" in policy["required_entrypoints"]
    assert "windops-care-dependency-closure" in policy["required_entrypoints"]
    assert "windops-care-workload-smoke" in policy["required_entrypoints"]
    assert "windops-care-fullscale-acceptance" in policy["required_entrypoints"]
    report = verify_image_inspect(
        _inspect(policy),
        image=IMAGE,
        release_id=RELEASE_ID,
        commit_sha=COMMIT_SHA,
        source_url=SOURCE_URL,
        policy=policy,
    )
    assert report == {
        "image": IMAGE,
        "image_digest": IMAGE_DIGEST,
        "release_id": RELEASE_ID,
        "commit_sha": COMMIT_SHA,
        "source_url": SOURCE_URL,
        "user": "10001:10001",
        "command": ["windops-api"],
        "base_image": policy["python_base_image"],
        "postgres_client_image": policy["postgres_client_image"],
        "postgres_client_major": policy["postgres_client_major"],
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("User", "0:0", "UID/GID"),
        ("Cmd", ["sh"], "default command"),
        ("Healthcheck", None, "health check"),
    ],
)
def test_image_identity_rejects_runtime_drift(
    field: str,
    value: object,
    message: str,
) -> None:
    policy = load_release_policy(POLICY_PATH)
    inspect = _inspect(policy)
    inspect["Config"][field] = value  # type: ignore[index]
    with pytest.raises(ContainerArtifactError, match=message):
        verify_image_inspect(
            inspect,
            image=IMAGE,
            release_id=RELEASE_ID,
            commit_sha=COMMIT_SHA,
            source_url=SOURCE_URL,
            policy=policy,
        )


def test_release_policy_rejects_floating_base_image(tmp_path: Path) -> None:
    policy = load_release_policy(POLICY_PATH)
    policy["python_base_image"] = "python:3.12-slim"
    path = tmp_path / "release-policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ContainerArtifactError, match="non-placeholder digest"):
        load_release_policy(path)


def test_release_policy_rejects_postgresql_client_drift(tmp_path: Path) -> None:
    policy = load_release_policy(POLICY_PATH)
    policy["postgres_client_image"] = "timescale/timescaledb-ha:latest"
    path = tmp_path / "release-policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ContainerArtifactError, match="PostgreSQL client image"):
        load_release_policy(path)

    policy = load_release_policy(POLICY_PATH)
    policy["postgres_client_major"] = 17
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ContainerArtifactError, match="production major 16"):
        load_release_policy(path)


def test_image_identity_rejects_unpushed_or_mislabeled_image() -> None:
    policy = load_release_policy(POLICY_PATH)
    inspect = _inspect(policy)
    inspect["RepoDigests"] = []
    with pytest.raises(ContainerArtifactError, match="not bound"):
        verify_image_inspect(
            inspect,
            image=IMAGE,
            release_id=RELEASE_ID,
            commit_sha=COMMIT_SHA,
            source_url=SOURCE_URL,
            policy=policy,
        )

    inspect = _inspect(policy)
    inspect["Config"]["Labels"]["org.opencontainers.image.revision"] = "c" * 40  # type: ignore[index]
    with pytest.raises(ContainerArtifactError, match="revision"):
        verify_image_inspect(
            inspect,
            image=IMAGE,
            release_id=RELEASE_ID,
            commit_sha=COMMIT_SHA,
            source_url=SOURCE_URL,
            policy=policy,
        )
