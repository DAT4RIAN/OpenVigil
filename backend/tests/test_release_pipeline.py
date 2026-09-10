from __future__ import annotations

import base64
import copy
import json
import os
import re
import zipfile
from pathlib import Path

import pytest
import yaml
from scripts.load_release_environment import main as load_release_environment
from scripts.run_real_release_smoke_server import _gateway_delegation_secret
from scripts.stage_independent_release_evidence import (
    INDEPENDENT_GATES,
    stage_independent_evidence,
)
from scripts.verify_migration_head import DECLARATION_FILES, EXPECTED_HEAD
from scripts.verify_release_checks import REQUIRED_CHECKS, verify_release_checks

from windops_backend.operations.container_artifact import ContainerArtifactError
from windops_backend.operations.release_smoke import _validate_production_environment_file

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
COMPOSE_PATH = REPOSITORY_ROOT / "backend" / "docker-compose.yml"
DOCKERFILE_PATH = REPOSITORY_ROOT / "backend" / "Dockerfile"
ROOT_README_PATH = REPOSITORY_ROOT / "README.md"
REAL_SMOKE_SERVER_PATH = (
    REPOSITORY_ROOT / "backend" / "scripts" / "run_real_release_smoke_server.py"
)
E2E_PRODUCTION_SERVER_PATH = REPOSITORY_ROOT / "scripts" / "e2e-production-server.mjs"
REAL_SMOKE_PREPARE_PATH = REPOSITORY_ROOT / "backend" / "scripts" / "prepare_real_release_smoke.py"


def _assert_real_cross_layer_build_order(job: dict[str, object]) -> None:
    steps = job["steps"]
    assert isinstance(steps, list)
    command_lines = [
        [line.strip() for line in str(step.get("run", "")).splitlines() if line.strip()]
        for step in steps
    ]
    build_indexes = [
        index for index, lines in enumerate(command_lines) if "pnpm run build" in lines
    ]
    artifact_check_indexes = [
        index
        for index, lines in enumerate(command_lines)
        if "test -f dist/server/index.js" in lines
    ]
    real_e2e_indexes = [
        index for index, lines in enumerate(command_lines) if "pnpm test:e2e:real" in lines
    ]

    assert len(build_indexes) == 1, "real cross-layer CI must build exactly one Worker artifact"
    assert len(artifact_check_indexes) == 1, (
        "real cross-layer CI must fail when dist/server/index.js is missing"
    )
    assert len(real_e2e_indexes) == 1, "real cross-layer CI must run exactly one real E2E command"
    build_index = build_indexes[0]
    artifact_check_index = artifact_check_indexes[0]
    real_e2e_index = real_e2e_indexes[0]
    assert artifact_check_index == build_index, "Worker build and artifact check must be atomic"
    assert command_lines[build_index].index("pnpm run build") < command_lines[build_index].index(
        "test -f dist/server/index.js"
    )
    assert build_index + 1 == real_e2e_index, (
        "Worker build must immediately precede real E2E startup"
    )
    assert steps[build_index]["name"] == "Build the real Worker production artifact"
    assert "working-directory" not in steps[build_index]


def test_root_readme_declares_current_migration_head_without_stale_baselines() -> None:
    source = ROOT_README_PATH.read_text(encoding="utf-8")
    assert ROOT_README_PATH in DECLARATION_FILES
    assert EXPECTED_HEAD in source
    stale_baselines = (
        "Python 119/120",
        "0001→0016",
        "十六个连续 Alembic",
        "201 项，189 passed",
        "12 个 `external_release`",
        "11 个 PostgreSQL/TimescaleDB/pgvector",
    )
    for stale_baseline in stale_baselines:
        assert stale_baseline not in source
    assert "pnpm test:e2e" in source
    assert "测试数量以命令和 CI 自动发现结果为准" in source
    assert "这些 skip 不被描述为发布通过" in source
    assert "出现 skip 即失败" in source


def test_release_workflow_is_protected_pinned_and_complete() -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    job = workflow["jobs"]["build-and-qualify"]
    assert job["environment"] == "production-release"
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["permissions"] == {
        "contents": "read",
        "packages": "write",
        "id-token": "write",
        "attestations": "write",
        "checks": "read",
    }
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert "python_base_image" in source
    assert "PYTHON_BASE_IMAGE=${{ steps.policy.outputs.base_image }}" in source
    assert "postgres_client_image" in source
    assert "POSTGRES_CLIENT_IMAGE=${{ steps.policy.outputs.postgres_client_image }}" in source
    assert "POSTGRES_CLIENT_MAJOR=${{ steps.policy.outputs.postgres_client_major }}" in source
    assert "provenance: mode=max" in source
    assert "sbom: true" in source
    assert "cosign sign --yes" in source
    assert "cosign verify-attestation" in source
    assert "severity: CRITICAL,HIGH" in source
    assert 'exit-code: "1"' in source
    assert "windops-container-artifact" in source
    assert "windops-release-smoke" in source
    assert "windops-deployment-policy" in source
    assert "test_release_environment.py" in source
    assert 'WINDOPS_FAIL_ON_SKIPPED: "1"' in source
    assert "windops-backup" in source
    assert "release-qualification.json" in source
    assert "windops-release-evidence" in source
    assert "windops-release-gate" in source
    assert "stage_independent_release_evidence.py" in source
    assert "WINDOPS_INDEPENDENT_EVIDENCE_SHA256" in source
    assert '--environment-file "${RUNNER_TEMP}/windops-release.env"' in source
    assert "--qualification-output release-evidence/release-qualification.json" in source
    assert 'status:"qualified"' not in source
    assert "status: qualified" not in source
    assert "sites-release-bindings.env" in source
    assert '"WINDOPS_BACKEND_EXPECTED_RELEASE_ID=${RELEASE_ID}"' in source
    assert '"WINDOPS_BACKEND_EXPECTED_COMMIT_SHA=${GITHUB_SHA}"' in source
    assert '"WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST=${IMAGE_DIGEST}"' in source
    assert REQUIRED_CHECKS == {
        "frontend",
        "backend",
        "postgres-contract",
        "care-postgres-contract",
        "browser-e2e",
        "real-cross-layer-e2e",
    }
    assert "verify_release_checks.py" in source
    uses = re.findall(r"^\s*uses:\s*([^\s#]+)", source, flags=re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses)
    assert not re.search(r"uses:\s*[^\s]+@(main|master|v\d+)(?:\s|$)", source)


def test_release_image_smoke_requires_exact_production_identity_and_dependencies(
    tmp_path: Path,
) -> None:
    environment = tmp_path / "release.env"
    release_id = "windops-2026.09.04-rc1"
    commit_sha = "a" * 40
    image_digest = "sha256:" + "b" * 64
    values = {
        "WINDOPS_ENVIRONMENT": "production",
        "WINDOPS_RELEASE_ID": release_id,
        "WINDOPS_RELEASE_COMMIT_SHA": commit_sha,
        "WINDOPS_RELEASE_IMAGE_DIGEST": image_digest,
        "WINDOPS_DATABASE_URL": "postgresql+asyncpg://release@db/windops?ssl=require",
        "WINDOPS_REDIS_URL": "rediss://redis/0",
        "WINDOPS_MINIO_ENDPOINT": "minio.internal:9000",
        "WINDOPS_NEO4J_URI": "neo4j+s://neo4j.internal:7687",
        "WINDOPS_TRUSTED_HOSTS": '["release-api.internal"]',
    }
    environment.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()), encoding="utf-8"
    )
    assert (
        _validate_production_environment_file(
            environment,
            release_id=release_id,
            commit_sha=commit_sha,
            image_digest=image_digest,
        )
        == "release-api.internal"
    )

    development = tmp_path / "development.env"
    development.write_text(
        environment.read_text(encoding="utf-8").replace(
            "WINDOPS_ENVIRONMENT=production", "WINDOPS_ENVIRONMENT=development"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ContainerArtifactError, match="wrong WINDOPS_ENVIRONMENT"):
        _validate_production_environment_file(
            development,
            release_id=release_id,
            commit_sha=commit_sha,
            image_digest=image_digest,
        )


def test_independent_release_evidence_staging_is_bounded_and_requires_every_gate(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "independent.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for gate in INDEPENDENT_GATES:
            bundle.writestr(f"reports/{gate}.json", '{"status":"passed"}')
            bundle.writestr(f"artifacts/{gate}/raw.json", '{"result":"passed"}')
    destination = tmp_path / "release-evidence"
    stage_independent_evidence(archive, destination)
    assert {path.stem for path in (destination / "reports").glob("*.json")} == set(
        INDEPENDENT_GATES
    )

    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as bundle:
        bundle.writestr("../outside.json", "{}")
    with pytest.raises(ValueError, match="unsafe path"):
        stage_independent_evidence(unsafe, tmp_path / "unsafe-output")


@pytest.mark.parametrize(
    ("name", "status", "conclusion", "head_sha", "expected_pass"),
    [
        ("browser-e2e", "completed", "success", "target", True),
        ("browser-e2e", "completed", None, "target", False),
        ("browser-e2e", "completed", "failure", "target", False),
        ("browser-e2e", "completed", "cancelled", "target", False),
        ("browser-e2e", "in_progress", None, "target", False),
        ("browser-e2e", "completed", "success", "other", False),
    ],
)
def test_release_check_gate_requires_successful_same_sha_for_browser_e2e(
    name: str,
    status: str,
    conclusion: str | None,
    head_sha: str,
    expected_pass: bool,
) -> None:
    checks = [
        {
            "name": check_name,
            "status": "completed",
            "conclusion": "success",
            "head_sha": "target",
        }
        for check_name in REQUIRED_CHECKS
        if check_name != "browser-e2e"
    ]
    checks.append(
        {
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "head_sha": head_sha,
        }
    )
    assert (not verify_release_checks(checks, "target")) is expected_pass


def test_release_check_gate_rejects_missing_browser_e2e() -> None:
    checks = [
        {
            "name": check_name,
            "status": "completed",
            "conclusion": "success",
            "head_sha": "target",
        }
        for check_name in REQUIRED_CHECKS
        if check_name != "browser-e2e"
    ]
    assert verify_release_checks(checks, "target")


@pytest.mark.parametrize(
    ("status", "conclusion", "head_sha", "expected_pass"),
    [
        ("completed", "success", "target", True),
        ("in_progress", "success", "target", False),
        ("completed", "failure", "target", False),
        ("completed", "cancelled", "target", False),
        ("completed", "success", "other", False),
    ],
)
def test_release_gate_requires_completed_successful_real_cross_layer_check(
    status: str,
    conclusion: str,
    head_sha: str,
    expected_pass: bool,
) -> None:
    checks = [
        {
            "name": check_name,
            "status": "completed",
            "conclusion": "success",
            "head_sha": "target",
        }
        for check_name in REQUIRED_CHECKS
        if check_name != "real-cross-layer-e2e"
    ]
    checks.append(
        {
            "name": "real-cross-layer-e2e",
            "status": status,
            "conclusion": conclusion,
            "head_sha": head_sha,
        }
    )
    assert (not verify_release_checks(checks, "target")) is expected_pass


def test_release_gate_rejects_missing_real_cross_layer_check() -> None:
    checks = [
        {
            "name": check_name,
            "status": "completed",
            "conclusion": "success",
            "head_sha": "target",
        }
        for check_name in REQUIRED_CHECKS
        if check_name != "real-cross-layer-e2e"
    ]
    assert verify_release_checks(checks, "target")


def test_ci_workflow_enforces_immutable_quality_and_postgres_gates() -> None:
    source = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    uses = re.findall(r"^\s*uses:\s*([^\s#]+)", source, flags=re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses)
    assert "pnpm test:coverage" in source
    assert "pnpm test:e2e" in source
    assert "pnpm test:e2e:real" in source
    assert "real-cross-layer-e2e" in source
    assert 'WINDOPS_E2E_REAL_BACKEND: "1"' in source
    assert "playwright install --with-deps chromium" in source
    assert "tests/e2e/__screenshots__" in source
    assert "check_coverage_budget.py" in source
    assert "--cov-fail-under=68" in source
    assert "--diff-file coverage.diff" in source
    backend_job = workflow["jobs"]["backend"]
    backend_commands = "\n".join(
        str(step.get("run", "")) for step in backend_job["steps"] if isinstance(step, dict)
    )
    assert "--junitxml=backend-tests-junit.xml" in backend_commands
    assert any(
        "backend/backend-tests-junit.xml" in str(step.get("with", {}).get("path", ""))
        for step in backend_job["steps"]
        if isinstance(step, dict)
    )
    assert 'WINDOPS_FAIL_ON_SKIPPED: "1"' in source
    assert "timescale/timescaledb-ha@sha256:" in source
    assert "tests/external/test_postgres_migrations.py" in source
    assert "tests/external/test_postgres_concurrency.py" in source
    assert "tests/external/test_postgres_service_resilience.py" in source
    assert "tests/external/test_postgres_prediction_lock.py" in source
    care_job = workflow["jobs"]["care-postgres-contract"]
    assert care_job["if"] == "github.event_name != 'pull_request'"
    assert care_job["runs-on"] == ["self-hosted", "linux", "x64", "windops-care-v6"]
    care_commands = "\n".join(
        str(step.get("run", "")) for step in care_job["steps"] if isinstance(step, dict)
    )
    assert "test_postgres_care_offline_evaluation.py" in care_commands
    assert "test_postgres_care_fullscale.py" in care_commands
    assert "test_postgres_care_vertical_slice.py" in care_commands
    assert "windops-care-postgres-evidence" in care_commands
    assert "0028_read_audit_pipeline" in care_commands
    assert "WINDOPS_CARE_REAL_ARTIFACT_ROOT" in care_commands
    assert "WINDOPS_CARE_FULL_SCALE_ROOT" in care_commands
    assert "care-postgres-evidence/vertical-junit.xml" in care_commands


def test_real_cross_layer_job_builds_worker_artifact_before_startup() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    _assert_real_cross_layer_build_order(workflow["jobs"]["real-cross-layer-e2e"])

    worker_source = E2E_PRODUCTION_SERVER_PATH.read_text(encoding="utf-8")
    assert 'new URL("../dist/server/index.js", import.meta.url)' in worker_source
    assert "await import(workerUrl.href)" in worker_source


def test_real_cross_layer_build_contract_rejects_a_missing_artifact_step() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = copy.deepcopy(workflow["jobs"]["real-cross-layer-e2e"])
    job["steps"] = [
        step
        for step in job["steps"]
        if step.get("name") != "Build the real Worker production artifact"
    ]

    with pytest.raises(AssertionError, match="must build exactly one Worker artifact"):
        _assert_real_cross_layer_build_order(job)


def test_real_cross_layer_build_contract_rejects_a_missing_dist_check() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = copy.deepcopy(workflow["jobs"]["real-cross-layer-e2e"])
    build_step = next(
        step
        for step in job["steps"]
        if step.get("name") == "Build the real Worker production artifact"
    )
    build_step["run"] = "pnpm run build"

    with pytest.raises(AssertionError, match="must fail when dist/server/index.js is missing"):
        _assert_real_cross_layer_build_order(job)


def test_real_cross_layer_delegation_secret_has_one_workflow_to_script_source() -> None:
    workflow_source = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_source)
    job = workflow["jobs"]["real-cross-layer-e2e"]
    job_environment = job["env"]
    backend_source = REAL_SMOKE_SERVER_PATH.read_text(encoding="utf-8")
    worker_source = E2E_PRODUCTION_SERVER_PATH.read_text(encoding="utf-8")

    assert job_environment["WINDOPS_GATEWAY_DELEGATION_SECRET"]
    assert "WINDOPS_E2E_DELEGATION_SECRET" not in job_environment
    assert "WINDOPS_GATEWAY_DELEGATION_SECRET" in backend_source
    assert "WINDOPS_GATEWAY_DELEGATION_SECRET" in worker_source
    assert "WINDOPS_E2E_DELEGATION_SECRET" not in backend_source
    assert "WINDOPS_E2E_DELEGATION_SECRET" not in worker_source
    assert "WINDOPS_E2E_DELEGATION_SECRET" not in workflow_source
    assert "is required for the real cross-layer smoke" in backend_source
    assert "is required when WINDOPS_E2E_REAL_BACKEND=1" in worker_source
    assert "real-worker-release-smoke-delegation-secret" not in backend_source
    assert "real-worker-release-smoke-delegation-secret" not in worker_source


def test_real_cross_layer_backend_requires_the_shared_delegation_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WINDOPS_GATEWAY_DELEGATION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="WINDOPS_GATEWAY_DELEGATION_SECRET is required"):
        _gateway_delegation_secret()

    shared_secret = "test-shared-delegation-secret-with-at-least-forty-eight-characters"
    monkeypatch.setenv("WINDOPS_GATEWAY_DELEGATION_SECRET", f"  {shared_secret}  ")
    assert _gateway_delegation_secret() == shared_secret


def test_repeatable_real_cross_layer_fixture_resets_its_owned_idempotency_result() -> None:
    source = REAL_SMOKE_PREPARE_PATH.read_text(encoding="utf-8")
    assert "delete(CommandReceipt)" in source
    assert "CommandReceipt.command_type == ROTATION_CONFIRMATION_COMMAND" in source
    assert "CommandReceipt.target == audit_id" in source


def test_release_dependency_stack_and_dockerfile_are_digest_pinned() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    assert all(
        re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", service["image"])
        for service in compose["services"].values()
    )
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert dockerfile.startswith("# syntax=docker/dockerfile:1.7@sha256:")
    assert "slim-trixie@sha256:" + "0" * 64 in dockerfile
    assert 'org.opencontainers.image.base.name="${PYTHON_BASE_IMAGE}"' in dockerfile
    assert "COPY alembic.ini requirements.container.txt ./" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "/api/v1/healthz" in dockerfile
    kustomization = yaml.safe_load(
        (REPOSITORY_ROOT / "backend" / "deploy" / "kubernetes" / "kustomization.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert kustomization["labels"] == [
        {
            "pairs": {"app.kubernetes.io/part-of": "windops-backend"},
            "includeSelectors": False,
            "includeTemplates": True,
        }
    ]


def test_protected_release_environment_loader_is_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "WINDOPS_ENVIRONMENT": "production",
        "WINDOPS_DATABASE_URL": "postgresql+asyncpg://release@db/windops",
        "WINDOPS_REDIS_URL": "rediss://redis/0",
        "WINDOPS_MINIO_ENDPOINT": "minio.internal:9000",
        "WINDOPS_NEO4J_URI": "neo4j+s://neo4j.internal:7687",
        "WINDOPS_LITELLM_MODEL": "openai/release-model",
        "WINDOPS_EMBEDDING_MODEL": "release-embedding",
    }
    encoded = base64.b64encode(
        "".join(f"{name}={value}\n" for name, value in values.items()).encode()
    ).decode()
    github_env = tmp_path / "github-env"
    release_env = tmp_path / "release.env"
    monkeypatch.setenv("WINDOPS_ISOLATED_RELEASE_ENV_B64", encoded)
    monkeypatch.setenv("GITHUB_ENV", str(github_env))
    monkeypatch.setenv("WINDOPS_RELEASE_ENV_PATH", str(release_env))

    assert load_release_environment() == 0
    assert github_env.read_text(encoding="utf-8") == release_env.read_text(encoding="utf-8")
    if os.name != "nt":
        assert release_env.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "payload",
    [
        "WINDOPS_ENVIRONMENT=development\n",
        "WINDOPS_ENVIRONMENT=production\nGITHUB_TOKEN=forbidden\n",
        "WINDOPS_ENVIRONMENT=production\nWINDOPS_ENVIRONMENT=production\n",
    ],
)
def test_protected_release_environment_loader_rejects_incomplete_or_unsafe_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
) -> None:
    monkeypatch.setenv(
        "WINDOPS_ISOLATED_RELEASE_ENV_B64",
        base64.b64encode(payload.encode()).decode(),
    )
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "github-env"))
    monkeypatch.setenv("WINDOPS_RELEASE_ENV_PATH", str(tmp_path / "release.env"))
    with pytest.raises(SystemExit):
        load_release_environment()


def test_protected_release_environment_cannot_override_candidate_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "WINDOPS_ENVIRONMENT": "production",
        "WINDOPS_DATABASE_URL": "postgresql+asyncpg://release@db/windops",
        "WINDOPS_REDIS_URL": "rediss://redis/0",
        "WINDOPS_MINIO_ENDPOINT": "minio.internal:9000",
        "WINDOPS_NEO4J_URI": "neo4j+s://neo4j.internal:7687",
        "WINDOPS_LITELLM_MODEL": "openai/release-model",
        "WINDOPS_EMBEDDING_MODEL": "release-embedding",
        "WINDOPS_RELEASE_ID": "wrong-candidate",
    }
    payload = "".join(f"{name}={value}\n" for name, value in values.items())
    monkeypatch.setenv(
        "WINDOPS_ISOLATED_RELEASE_ENV_B64", base64.b64encode(payload.encode()).decode()
    )
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "github-env"))
    monkeypatch.setenv("WINDOPS_RELEASE_ENV_PATH", str(tmp_path / "release.env"))
    with pytest.raises(SystemExit, match="cannot override candidate identity"):
        load_release_environment()


def test_release_policy_has_only_reviewed_fields() -> None:
    policy = json.loads(
        (REPOSITORY_ROOT / "backend" / "deploy" / "release-policy.json").read_text(encoding="utf-8")
    )
    assert policy["format_version"] == 1
    assert policy["platform"] == "linux/amd64"
    assert policy["python_base_image"].endswith(
        "@sha256:47ae396f09c1303b8653019811a8498470603d7ffefc29cb07c88f1f8cb3d19f"
    )
    assert policy["postgres_client_image"].endswith(
        "@sha256:df8eaa04de65fbe238df8dbc356e79108bcb8166d3458833536a3ff745abb2be"
    )
    assert policy["postgres_client_major"] == 16
    assert set(policy["required_workloads"]) == {
        "windops-api",
        "windops-worker",
        "windops-outbox-relay",
        "windops-read-audit-worker",
        "windops-migrate-release",
        "windops-backup",
        "windops-read-audit-maintenance",
        "windops-care-full-scale",
    }
