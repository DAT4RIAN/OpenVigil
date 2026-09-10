from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest

from windops_backend.benchmarks.care.runtime import CareWorkerSettings
from windops_backend.operations import care_execution_plane as execution_plane
from windops_backend.operations.care_fullscale_acceptance import (
    CareFullScaleAcceptanceError,
    verify_care_fullscale_acceptance,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
COMMIT_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64
RELEASE_ID = "windops-2026.09.04-rc1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _release_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "WINDOPS_CARE_QUEUE": "care-v6-offline",
        "WINDOPS_CARE_MAX_CONCURRENCY": "1",
        "WINDOPS_CARE_MAX_ATTEMPTS": "3",
        "WINDOPS_RELEASE_ID": RELEASE_ID,
        "WINDOPS_RELEASE_COMMIT_SHA": COMMIT_SHA,
        "WINDOPS_RELEASE_IMAGE_DIGEST": IMAGE_DIGEST,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_execution_plane_smoke_resumes_and_replays_the_real_parquet_primitive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release_environment(monkeypatch)
    source = tmp_path / "source" / "smoke.csv"
    source.parent.mkdir()
    source.write_bytes(execution_plane.SMOKE_FIXTURE.read_bytes())
    source.chmod(stat.S_IREAD)
    monkeypatch.setattr(
        execution_plane,
        "verify_benchmark_dependency_closure",
        lambda _path: {"status": "passed"},
    )
    try:
        report = execution_plane.run_execution_plane_smoke(
            tmp_path / "workspace",
            tmp_path / "report.json",
            BACKEND_ROOT / "requirements.container.txt",
            publish_to_configured_minio=False,
            source=source,
        )
    finally:
        source.chmod(stat.S_IREAD | stat.S_IWRITE)

    assert report["status"] == "passed"
    assert report["runtime"]["queue"] == "care-v6-offline"
    assert report["checkpoint_resume"] is True
    assert report["idempotent_replay"] is True
    assert report["row_count"] > 0
    assert report["published_to_care_bucket"] is False


def test_execution_plane_rejects_writable_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release_environment(monkeypatch)
    source = tmp_path / "writable.csv"
    source.write_text("Timestamp,Sensor\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")
    with pytest.raises(execution_plane.CareExecutionPlaneError, match="read-only"):
        execution_plane.run_execution_plane_smoke(
            tmp_path / "workspace",
            tmp_path / "report.json",
            BACKEND_ROOT / "requirements.container.txt",
            publish_to_configured_minio=False,
            source=source,
        )


def test_care_worker_settings_require_tls_and_explicit_denied_buckets() -> None:
    settings = CareWorkerSettings(
        database_url="postgresql+asyncpg://care:strong-database-password@db/care?ssl=require",
        minio_endpoint="minio.internal:9000",
        minio_access_key="care-worker",
        minio_secret_key="x" * 32,
        minio_secure=True,
        minio_bucket="windops-care-benchmarks",
        forbidden_buckets=(
            "windops-field-evidence,windops-knowledge-documents,"
            "windops-model-artifacts,windops-twin-artifacts"
        ),
    )
    assert settings.forbidden_bucket_names == (
        "windops-field-evidence",
        "windops-knowledge-documents",
        "windops-model-artifacts",
        "windops-twin-artifacts",
    )
    with pytest.raises(ValueError, match="TLS endpoint"):
        CareWorkerSettings(
            database_url="postgresql+asyncpg://care:strong-database-password@db/care?ssl=require",
            minio_endpoint="localhost:9000",
            minio_access_key="care-worker",
            minio_secret_key="x" * 32,
            minio_secure=False,
            minio_bucket="windops-care-benchmarks",
            forbidden_buckets=settings.forbidden_buckets,
        )


def _fullscale_evidence(root: Path) -> Path:
    policy = BACKEND_ROOT / "deploy" / "care-minio-worker-policy.json"
    storage = {
        "bucket": "windops-care-benchmarks",
        "tls": True,
        "delete_object_allowed": False,
        "access_denied_buckets": [
            "windops-field-evidence",
            "windops-knowledge-documents",
            "windops-model-artifacts",
            "windops-twin-artifacts",
        ],
        "policy_sha256": _sha256(policy),
    }
    payloads: dict[str, tuple[str, dict[str, object]]] = {
        "dependency_closure": ("dependency-closure.json", {"status": "passed"}),
        "import_manifest": (
            "import-manifest.json",
            {
                "schema_version": "care-v6-full-scale-import-manifest-v1",
                "raw_source_unchanged": True,
                "summary": {"event_count": 95, "farm_namespaced_asset_count": 36},
                "resource_actual": {"limits_passed": True},
            },
        ),
        "evaluation_manifest": (
            "evaluation-manifest.json",
            {
                "schema_version": "care-v6-full-scale-evaluation-manifest-v1",
                "summary": {
                    "event_count": 95,
                    "fold_count": 36,
                    "all_events_accounted_for": True,
                },
                "cross_farm_protocol": {"status": "disabled"},
                "resource_actual": {"limits_passed": True},
            },
        ),
        "import_state": (
            "import-state.json",
            {
                "operation": "import",
                "status": "completed",
                "max_attempts": 3,
                "progress_total": 95,
                "progress_completed": 95,
                "resource_stats": {"limits_passed": True},
            },
        ),
        "evaluation_state": (
            "evaluation-state.json",
            {
                "operation": "evaluate",
                "status": "completed",
                "max_attempts": 3,
                "progress_total": 95,
                "progress_completed": 95,
                "resource_stats": {"limits_passed": True},
            },
        ),
        "registration": (
            "registration.json",
            {"import_created_count": 95, "evaluation_created_count": 36},
        ),
        "registration_replay": (
            "registration-replay.json",
            {
                "import_created_count": 0,
                "evaluation_created_count": 0,
                "import_replayed_count": 95,
                "evaluation_replayed_count": 36,
            },
        ),
        "storage_scope": ("storage-scope.json", storage),
    }
    artifacts_root = root / "artifacts" / "care" / "fullscale"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    for role in ("import_manifest", "evaluation_manifest"):
        name, payload = payloads[role]
        (artifacts_root / name).write_text(json.dumps(payload), encoding="utf-8")
    payloads["import_replay"] = (
        "import-replay.json",
        {
            "replayed": True,
            "manifest_file_sha256": _sha256(artifacts_root / "import-manifest.json"),
        },
    )
    payloads["evaluation_replay"] = (
        "evaluation-replay.json",
        {
            "replayed": True,
            "manifest_file_sha256": _sha256(artifacts_root / "evaluation-manifest.json"),
        },
    )
    artifact_records: list[dict[str, str]] = []
    for role, (name, payload) in payloads.items():
        path = root / "artifacts" / "care" / "fullscale" / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        artifact_records.append(
            {
                "role": role,
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256(path),
                "media_type": "application/json",
            }
        )
    evidence = {
        "format_version": 1,
        "gate": "care_full_scale_acceptance",
        "status": "passed",
        "release": {
            "release_id": RELEASE_ID,
            "commit_sha": COMMIT_SHA,
            "image_digest": IMAGE_DIGEST,
        },
        "workload": {
            "name": "windops-care-full-scale",
            "queue": "care-v6-offline",
            "max_concurrency": 1,
            "max_attempts": 3,
            "active_deadline_seconds": 72000,
        },
        "source": {"approved": True, "read_only": True},
        "dependency_closure": {"status": "passed"},
        "import": {
            "status": "passed",
            "state_status": "completed",
            "limits_passed": True,
            "replayed": True,
        },
        "evaluation": {
            "status": "passed",
            "state_status": "completed",
            "limits_passed": True,
            "replayed": True,
            "fold_count": 36,
            "event_count": 95,
            "cross_farm_status": "disabled",
        },
        "registration": {"status": "passed", "transactional": True, "replayed": True},
        "storage": storage,
        "approval": {
            "approved_by": "independent-release-reviewer",
            "approval_reference": "CHANGE-CARE-1042",
        },
        "artifacts": artifact_records,
    }
    path = root / "artifacts" / "care" / "care-full-scale-release-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return path


def test_fullscale_acceptance_binds_raw_artifacts_and_scoped_credentials(tmp_path: Path) -> None:
    evidence = _fullscale_evidence(tmp_path)
    report = verify_care_fullscale_acceptance(
        evidence,
        tmp_path,
        BACKEND_ROOT / "deploy" / "care-minio-worker-policy.json",
        expected_release_id=RELEASE_ID,
        expected_commit_sha=COMMIT_SHA,
        expected_image_digest=IMAGE_DIGEST,
    )
    assert report["status"] == "passed"
    assert report["artifact_count"] == 10

    document = json.loads(evidence.read_text(encoding="utf-8"))
    document["evaluation"]["fold_count"] = 35
    evidence.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CareFullScaleAcceptanceError, match="evaluation"):
        verify_care_fullscale_acceptance(
            evidence,
            tmp_path,
            BACKEND_ROOT / "deploy" / "care-minio-worker-policy.json",
            expected_release_id=RELEASE_ID,
            expected_commit_sha=COMMIT_SHA,
            expected_image_digest=IMAGE_DIGEST,
        )
