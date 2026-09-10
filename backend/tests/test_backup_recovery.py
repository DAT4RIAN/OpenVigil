import json
from contextlib import contextmanager
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.operations import backups
from windops_backend.operations.backups import (
    MANIFEST_DIGEST_NAME,
    MANIFEST_NAME,
    database_connection,
    safe_configuration_snapshot,
    sha256_file,
    validate_confirmed_target,
    verify_backup_bundle,
)


def _bundle(root: Path) -> Path:
    root.mkdir()
    database_dump = root / "postgresql.dump"
    database_dump.write_bytes(b"verified-postgresql-dump")
    safe_config = root / "safe-config.json"
    safe_config.write_text("{}", encoding="utf-8")
    manifest = {
        "format_version": 2,
        "complete": True,
        "created_at": "2026-08-14T12:00:00+00:00",
        "database_name": "windops_restore_drill",
        "schema_revision": "0014_reasoning_evaluations",
        "database_invariants": {
            "wind_farms": 1,
            "turbines": 64,
            "missions": 3,
        },
        "buckets": [
            "windops-field-evidence",
            "windops-knowledge-documents",
            "windops-model-artifacts",
            "windops-twin-artifacts",
            "windops-care-benchmarks",
        ],
        "bucket_bindings": {
            "field_evidence": "windops-field-evidence",
            "knowledge": "windops-knowledge-documents",
            "model": "windops-model-artifacts",
            "twin": "windops-twin-artifacts",
            "care": "windops-care-benchmarks",
        },
        "artifacts": [
            {
                "kind": "postgresql",
                "path": database_dump.name,
                "bytes": database_dump.stat().st_size,
                "sha256": sha256_file(database_dump),
                "database_name": "windops_restore_drill",
            },
            {
                "kind": "configuration",
                "path": safe_config.name,
                "bytes": safe_config.stat().st_size,
                "sha256": sha256_file(safe_config),
            },
        ],
    }
    manifest_path = root / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    (root / MANIFEST_DIGEST_NAME).write_text(
        f"{sha256_file(manifest_path)}  {MANIFEST_NAME}\n",
        encoding="ascii",
    )
    return root


def test_database_connection_removes_password_and_requires_exact_confirmation() -> None:
    safe_url, password, database_name = database_connection(
        "postgresql+asyncpg://windops:p%40ssword@db.internal:5432/"
        "windops_restore_drill?sslmode=verify-full"
    )
    assert safe_url == (
        "postgresql://windops@db.internal:5432/windops_restore_drill?sslmode=verify-full"
    )
    assert password == "p@ssword"
    assert database_name == "windops_restore_drill"
    assert (
        validate_confirmed_target(
            "postgresql+asyncpg://windops:secret@db/windops_restore_drill",
            "windops_restore_drill",
        )
        == "windops_restore_drill"
    )
    with pytest.raises(ValueError, match="exactly match"):
        validate_confirmed_target(
            "postgresql+asyncpg://windops:secret@db/windops_restore_drill",
            "windops",
        )


def test_snapshot_query_suppresses_transaction_command_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    def run_postgres_command(command: tuple[str, ...], _password: str) -> CompletedProcess[str]:
        commands.append(command)
        return CompletedProcess(command, 0, "0028_read_audit_pipeline\n", "")

    monkeypatch.setattr(backups, "_run_postgres_command", run_postgres_command)
    result = backups._snapshot_query(
        "postgresql://backup@db/windops",
        "secret",
        "snapshot-42",
        "SELECT version_num FROM alembic_version",
    )

    assert result.stdout == "0028_read_audit_pipeline\n"
    assert commands[0][:5] == (
        "psql",
        "--dbname=postgresql://backup@db/windops",
        "--quiet",
        "--tuples-only",
        "--no-align",
    )


def test_backup_bundle_is_verified_before_restore(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "backup")
    manifest = verify_backup_bundle(bundle)
    assert manifest["complete"] is True
    assert manifest["database_name"] == "windops_restore_drill"

    (bundle / "postgresql.dump").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="size mismatch|digest mismatch"):
        verify_backup_bundle(bundle)


def test_legacy_v1_bundle_remains_verifiable_but_cannot_remap_buckets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = _bundle(tmp_path / "legacy-backup")
    manifest_path = bundle / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["format_version"] = 1
    manifest.pop("bucket_bindings")
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    (bundle / MANIFEST_DIGEST_NAME).write_text(
        f"{sha256_file(manifest_path)}  {MANIFEST_NAME}\n",
        encoding="ascii",
    )
    assert verify_backup_bundle(bundle)["format_version"] == 1

    settings = Settings(
        environment=Environment.TEST,
        database_url=("postgresql+asyncpg://windops:secret@db/windops_restore_isolated"),
        minio_field_evidence_bucket="restore-field-evidence",
        minio_knowledge_bucket="restore-knowledge",
        minio_model_bucket="restore-model",
        minio_twin_bucket="restore-twin",
        minio_care_bucket="restore-care",
    )
    monkeypatch.setattr(backups, "minio_client", lambda _settings: object())
    with pytest.raises(ValueError, match="legacy backup bucket identities"):
        backups.restore_backup(
            settings,
            bundle,
            confirmed_target="windops_restore_isolated",
            allow_object_overwrite=False,
            allow_database_rename=True,
        )


def test_manifest_cannot_escape_bundle(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "backup")
    manifest_path = bundle / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["path"] = "../outside.dump"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    (bundle / MANIFEST_DIGEST_NAME).write_text(
        f"{sha256_file(manifest_path)}  {MANIFEST_NAME}\n",
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="escapes"):
        verify_backup_bundle(bundle)


def test_safe_configuration_snapshot_never_contains_credentials() -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url="sqlite+aiosqlite:///:memory:",
        knowledge_graph_backend="memory",
        minio_access_key="high-value-access-key",
        minio_secret_key="high-value-secret-key",
        gateway_delegation_secret="high-value-delegation-secret",
        metrics_bearer_token="high-value-metrics-token",
    )
    serialized = json.dumps(safe_configuration_snapshot(settings), sort_keys=True)
    assert "high-value" not in serialized
    assert "database_url" not in serialized
    assert "redis_url" not in serialized
    snapshot = safe_configuration_snapshot(settings)
    assert snapshot["docs_enabled"] is True
    assert snapshot["trusted_hosts"] == ["localhost", "127.0.0.1", "test", "testserver"]
    assert snapshot["rate_limit"] == {
        "enabled": False,
        "principal_requests_per_minute": 600,
        "client_requests_per_minute": 10_000,
    }
    assert snapshot["release"] == {
        "release_id": "development",
        "commit_sha": "",
        "image_digest": "",
    }


def test_database_invariants_cover_every_care_authoritative_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {label: 0 for label, _table in backups.DATABASE_INVARIANT_TABLES}
    commands: list[tuple[str, ...]] = []

    def run_postgres_command(command: tuple[str, ...], _password: str) -> CompletedProcess[str]:
        commands.append(command)
        return CompletedProcess(command, 0, json.dumps(expected), "")

    monkeypatch.setattr(backups, "_run_postgres_command", run_postgres_command)
    assert (
        backups.current_database_invariants("postgresql+asyncpg://windops:secret@db/windops")
        == expected
    )
    query_argument = next(argument for argument in commands[0] if argument.startswith("--command="))
    assert query_argument == f"--command={backups.DATABASE_INVARIANT_QUERY}"
    for label, table in backups.DATABASE_INVARIANT_TABLES:
        assert f"'{label}'" in query_argument
        assert f"FROM {table}" in query_argument
    assert {
        "benchmark_dataset_versions",
        "benchmark_files",
        "benchmark_events",
        "benchmark_feature_maps",
        "benchmark_quality_reports",
        "benchmark_evaluation_runs",
        "benchmark_event_results",
        "benchmark_metric_snapshots",
        "benchmark_replay_runs",
        "anomaly_alert_policy_states",
        "read_access_audits",
        "read_access_audit_archives",
    }.issubset(expected)


def test_create_backup_captures_manifest_metadata_from_exported_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url="postgresql+asyncpg://windops:secret@db/windops",
    )
    commands: list[tuple[str, ...]] = []
    captured_snapshot_ids: list[str | None] = []

    @contextmanager
    def exported_snapshot(_safe_url: str, _password: str):
        yield "snapshot-42"

    def run_postgres_command(command: tuple[str, ...], _password: str) -> CompletedProcess[str]:
        commands.append(command)
        dump_argument = next(
            (argument for argument in command if argument.startswith("--file=")), None
        )
        if dump_argument is not None:
            Path(dump_argument.removeprefix("--file=")).write_bytes(b"postgresql-dump")
        return CompletedProcess(command, 0, "", "")

    def schema_revision(_database_url: str, *, snapshot_id: str | None = None) -> str:
        captured_snapshot_ids.append(snapshot_id)
        return "0028_read_audit_pipeline"

    def invariants(_database_url: str, *, snapshot_id: str | None = None) -> dict[str, int]:
        captured_snapshot_ids.append(snapshot_id)
        return {"wind_farms": 1, "turbines": 1}

    class ScopedMinio:
        def bucket_exists(self, _bucket: str) -> bool:
            return True

        def list_objects(self, bucket: str, *, recursive: bool):
            del recursive
            if bucket != settings.minio_care_bucket:
                return iter(())
            return iter(
                (
                    type("Object", (), {"object_name": "care/v6/_tmp/upload.partial"})(),
                    type(
                        "Object",
                        (),
                        {"object_name": "care/v6/reports/verified-report.json"},
                    )(),
                )
            )

        def stat_object(self, _bucket: str, object_name: str):
            assert object_name == "care/v6/reports/verified-report.json"
            return type("ObjectStat", (), {"content_type": "application/json"})()

        def fget_object(self, _bucket: str, object_name: str, destination: str) -> None:
            assert object_name == "care/v6/reports/verified-report.json"
            Path(destination).write_bytes(b"verified CARE report")

    monkeypatch.setattr(backups, "_export_postgres_snapshot", exported_snapshot)
    monkeypatch.setattr(backups, "_run_postgres_command", run_postgres_command)
    monkeypatch.setattr(backups, "current_schema_revision", schema_revision)
    monkeypatch.setattr(backups, "current_database_invariants", invariants)
    monkeypatch.setattr(backups, "minio_client", lambda _settings: ScopedMinio())

    bundle = backups.create_backup(settings, tmp_path)
    manifest = json.loads((bundle / MANIFEST_NAME).read_text(encoding="utf-8"))

    dump_command = next(command for command in commands if command[0] == "pg_dump")
    assert "--snapshot=snapshot-42" in dump_command
    assert captured_snapshot_ids == ["snapshot-42", "snapshot-42"]
    assert manifest["schema_revision"] == "0028_read_audit_pipeline"
    assert manifest["database_invariants"] == {"wind_farms": 1, "turbines": 1}
    assert len(manifest["buckets"]) == 5
    assert settings.minio_care_bucket in manifest["buckets"]
    assert manifest["bucket_bindings"]["care"] == settings.minio_care_bucket
    minio_artifacts = [
        artifact for artifact in manifest["artifacts"] if artifact["kind"] == "minio"
    ]
    assert [artifact["object_name"] for artifact in minio_artifacts] == [
        "care/v6/reports/verified-report.json"
    ]
    assert (
        backups.object_is_in_governed_backup_scope("care", "care/v6/_tmp/upload.partial") is False
    )
    with pytest.raises(RuntimeError, match="outside the governed backup prefixes"):
        backups.object_is_in_governed_backup_scope("care", "care/v6/unknown/object")


def test_restore_validates_dump_before_destructive_restore(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = _bundle(tmp_path / "backup")
    settings = Settings(
        environment=Environment.TEST,
        database_url="postgresql+asyncpg://windops:secret@db/windops_restore_drill",
    )
    commands: list[tuple[str, ...]] = []

    class EmptyMinio:
        def bucket_exists(self, _bucket: str) -> bool:
            return True

    def run_postgres_command(command: tuple[str, ...], _password: str) -> CompletedProcess[str]:
        commands.append(command)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backups, "minio_client", lambda _settings: EmptyMinio())
    monkeypatch.setattr(backups, "_run_postgres_command", run_postgres_command)
    monkeypatch.setattr(
        backups,
        "current_schema_revision",
        lambda _database_url: "0014_reasoning_evaluations",
    )
    monkeypatch.setattr(
        backups,
        "current_database_invariants",
        lambda _database_url: {"wind_farms": 1, "turbines": 64, "missions": 3},
    )

    backups.restore_backup(
        settings,
        bundle,
        confirmed_target="windops_restore_drill",
        allow_object_overwrite=False,
    )

    assert commands[0][:2] == ("pg_restore", "--list")
    assert commands[1][0] == "pg_restore"
    assert "--clean" in commands[1]
    assert "--single-transaction" in commands[1]


def test_restore_maps_v2_bucket_roles_to_isolated_dr_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = _bundle(tmp_path / "backup")
    care_object = bundle / "objects" / "care-object"
    care_object.parent.mkdir()
    care_object.write_bytes(b"verified-care-artifact")
    manifest_path = bundle / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].append(
        {
            "kind": "minio",
            "path": care_object.relative_to(bundle).as_posix(),
            "bytes": care_object.stat().st_size,
            "sha256": sha256_file(care_object),
            "bucket": "windops-care-benchmarks",
            "bucket_role": "care",
            "object_name": "care/v6/reports/manifest.json",
            "content_type": "application/json",
        }
    )
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    (bundle / MANIFEST_DIGEST_NAME).write_text(
        f"{sha256_file(manifest_path)}  {MANIFEST_NAME}\n",
        encoding="ascii",
    )

    settings = Settings(
        environment=Environment.TEST,
        database_url=("postgresql+asyncpg://windops:secret@db/windops_restore_isolated"),
        minio_field_evidence_bucket="restore-field-evidence",
        minio_knowledge_bucket="restore-knowledge",
        minio_model_bucket="restore-model",
        minio_twin_bucket="restore-twin",
        minio_care_bucket="restore-care",
    )
    stored: dict[tuple[str, str], bytes] = {}
    stored_metadata: dict[tuple[str, str], dict[str, str]] = {}

    class IsolatedMinio:
        def bucket_exists(self, bucket: str) -> bool:
            return bucket.startswith("restore-")

        def fput_object(
            self,
            bucket: str,
            object_name: str,
            path: str,
            *,
            content_type: str,
            metadata: dict[str, str],
        ) -> None:
            assert content_type == "application/json"
            stored[(bucket, object_name)] = Path(path).read_bytes()
            stored_metadata[(bucket, object_name)] = metadata

        def fget_object(self, bucket: str, object_name: str, path: str) -> None:
            Path(path).write_bytes(stored[(bucket, object_name)])

    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(backups, "minio_client", lambda _settings: IsolatedMinio())
    monkeypatch.setattr(
        backups,
        "_run_postgres_command",
        lambda command, _password: commands.append(command),
    )
    monkeypatch.setattr(
        backups,
        "current_schema_revision",
        lambda _database_url: "0014_reasoning_evaluations",
    )
    monkeypatch.setattr(
        backups,
        "current_database_invariants",
        lambda _database_url: {"wind_farms": 1, "turbines": 64, "missions": 3},
    )

    backups.restore_backup(
        settings,
        bundle,
        confirmed_target="windops_restore_isolated",
        allow_object_overwrite=True,
        allow_database_rename=True,
    )

    assert commands[0][:2] == ("pg_restore", "--list")
    assert stored == {("restore-care", "care/v6/reports/manifest.json"): b"verified-care-artifact"}
    assert stored_metadata == {
        ("restore-care", "care/v6/reports/manifest.json"): {"sha256": sha256_file(care_object)}
    }
