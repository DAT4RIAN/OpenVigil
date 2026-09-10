import re
import tomllib
from pathlib import Path
from typing import Any, cast

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ROOT = BACKEND_ROOT / "deploy" / "kubernetes"
PLACEHOLDER_DIGEST = "sha256:" + "0" * 64


def _documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in sorted(DEPLOY_ROOT.glob("*.yaml")):
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if isinstance(document, dict) and "kind" in document:
                documents.append(cast(dict[str, Any], document))
    return documents


def _named(kind: str, name: str) -> dict[str, Any]:
    return next(
        document
        for document in _documents()
        if document["kind"] == kind and document["metadata"]["name"] == name
    )


def _container(workload: dict[str, Any]) -> dict[str, Any]:
    pod_spec = (
        workload["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        if workload["kind"] == "CronJob"
        else workload["spec"]["template"]["spec"]
    )
    return cast(dict[str, Any], pod_spec["containers"][0])


def test_runtime_image_is_non_root_and_excludes_development_context() -> None:
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "PYTHON_BASE_IMAGE=python:3.12.11-slim-trixie@sha256:" in dockerfile
    assert "POSTGRES_CLIENT_IMAGE=timescale/timescaledb-ha@sha256:" in dockerfile
    assert "FROM ${POSTGRES_CLIENT_IMAGE} AS postgres-client" in dockerfile
    assert "FROM ${PYTHON_BASE_IMAGE} AS builder" in dockerfile
    assert "FROM ${PYTHON_BASE_IMAGE} AS runtime" in dockerfile
    for executable in ("pg_dump", "pg_restore", "psql"):
        assert (
            f"COPY --from=postgres-client /usr/lib/postgresql/16/bin/{executable} "
            f"/usr/local/bin/{executable}"
        ) in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert 'CMD ["windops-api"]' in dockerfile
    assert 'org.opencontainers.image.revision="${WINDOPS_COMMIT_SHA}"' in dockerfile
    assert "--require-hashes --wheel-dir /wheels -r requirements.container.txt" in dockerfile
    assert "--no-index --find-links=/wheels --require-hashes" in dockerfile
    for excluded in (".venv", "tests", ".test-tmp", "docker-compose.yml"):
        assert excluded in dockerignore


def test_container_requirements_are_hash_locked_to_uv_versions() -> None:
    requirements = (BACKEND_ROOT / "requirements.container.txt").read_text(encoding="utf-8")
    headers = re.findall(r"(?m)^([a-z0-9][a-z0-9._-]*)==([^ ;\\]+).*$", requirements)
    assert headers
    blocks = re.split(r"(?m)(?=^[a-z0-9][a-z0-9._-]*==)", requirements)
    assert all("--hash=sha256:" in block for block in blocks if block.strip())
    assert not re.search(r"(?m)^(?:pytest|mypy|ruff|bandit|pip-audit)==", requirements)

    lock = tomllib.loads((BACKEND_ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = {(package["name"], package["version"]) for package in lock["package"]}
    for name, version in headers:
        assert (name.replace("_", "-"), version) in locked
    project = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert any(
        dependency.lower().startswith("pyyaml") for dependency in project["project"]["dependencies"]
    )
    assert project["project"]["scripts"]["windops-deployment-policy"] == (
        "windops_backend.operations.deployment_policy:main"
    )


def test_workloads_are_digest_pinned_hardened_and_resource_bounded() -> None:
    workloads = [
        document
        for document in _documents()
        if document["kind"] in {"Deployment", "Job", "CronJob"}
    ]
    assert {document["metadata"]["name"] for document in workloads} == {
        "windops-api",
        "windops-worker",
        "windops-outbox-relay",
        "windops-migrate-release",
        "windops-backup",
    }
    for workload in workloads:
        container = _container(workload)
        assert "@sha256:" in container["image"]
        assert container["image"].endswith(PLACEHOLDER_DIGEST)
        assert ":latest" not in container["image"]
        assert container["envFrom"] == [{"secretRef": {"name": "windops-runtime"}}]
        assert set(container["resources"]) == {"requests", "limits"}
        assert set(container["resources"]["requests"]) == {
            "cpu",
            "memory",
            "ephemeral-storage",
        }
        assert set(container["resources"]["limits"]) == {
            "cpu",
            "memory",
            "ephemeral-storage",
        }
        assert container["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        }


def test_api_rollout_probes_availability_and_scaling_are_fail_closed() -> None:
    api = _named("Deployment", "windops-api")
    assert api["spec"]["replicas"] == 3
    assert api["spec"]["strategy"]["rollingUpdate"] == {
        "maxUnavailable": 0,
        "maxSurge": 1,
    }
    container = _container(api)
    assert container["startupProbe"]["httpGet"]["path"] == "/api/v1/healthz"
    assert container["livenessProbe"]["httpGet"]["path"] == "/api/v1/healthz"
    assert container["readinessProbe"]["httpGet"]["path"] == "/api/v1/readyz"
    for probe in ("startupProbe", "livenessProbe", "readinessProbe"):
        assert container[probe]["httpGet"]["httpHeaders"] == [
            {"name": "Host", "value": "windops-api.windops.svc"}
        ]
    assert _named("PodDisruptionBudget", "windops-api")["spec"]["minAvailable"] == 2
    hpa = _named("HorizontalPodAutoscaler", "windops-api")
    assert hpa["spec"]["minReplicas"] == 3
    assert hpa["spec"]["maxReplicas"] >= 6


def test_migration_backup_and_network_boundaries_are_explicit() -> None:
    migration = _named("Job", "windops-migrate-release")
    assert _container(migration)["command"] == ["alembic", "upgrade", "head"]
    assert migration["spec"]["backoffLimit"] == 1
    backup = _named("CronJob", "windops-backup")
    assert backup["spec"]["concurrencyPolicy"] == "Forbid"
    assert _container(backup)["command"] == [
        "windops-backup",
        "--output-dir",
        "/backups",
    ]
    backup_claim = _named("PersistentVolumeClaim", "windops-backups")
    assert backup_claim["spec"]["storageClassName"] == "windops-encrypted-backup"
    default_deny = _named("NetworkPolicy", "windops-default-deny")
    assert default_deny["spec"]["podSelector"] == {}
    assert set(default_deny["spec"]["policyTypes"]) == {"Ingress", "Egress"}
    ingress = _named("NetworkPolicy", "windops-api-ingress")
    selector = ingress["spec"]["ingress"][0]["from"][0]["namespaceSelector"]["matchLabels"]
    assert selector == {"windops.openai.com/gateway-access": "true"}
    egress = _named("NetworkPolicy", "windops-runtime-egress")
    assert all(rule.get("to") for rule in egress["spec"]["egress"])
    dependency_peer = egress["spec"]["egress"][1]["to"][0]
    assert dependency_peer == {
        "namespaceSelector": {
            "matchLabels": {"windops.openai.com/runtime-dependency-access": "true"}
        },
        "podSelector": {"matchLabels": {"windops.openai.com/runtime-dependency-access": "true"}},
    }
    assert not any(document["kind"] == "Secret" for document in _documents())
