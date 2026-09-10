from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess  # nosec B404 - fixed PostgreSQL client commands, never a shell
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from hmac import compare_digest
from pathlib import Path
from typing import Any, cast
from urllib.parse import SplitResult, quote, unquote, urlsplit, urlunsplit

from minio import Minio
from minio.error import S3Error

from windops_backend.config import Settings, get_settings
from windops_backend.operations.report_io import sha256_file as sha256_file

BACKUP_FORMAT_VERSION = 2
LEGACY_BACKUP_FORMAT_VERSION = 1
GOVERNED_BUCKET_ROLES = (
    "field_evidence",
    "knowledge",
    "model",
    "twin",
    "care",
)
CARE_BACKUP_PREFIXES = (
    "care/v6/raw/",
    "care/v6/standard/",
    "care/v6/quality/",
    "care/v6/predictions/",
    "care/v6/reports/",
)
CARE_TEMPORARY_PREFIX = "care/v6/_tmp/"
DATABASE_INVARIANT_TABLES = (
    ("wind_farms", "wind_farms"),
    ("turbines", "turbines"),
    ("scada_samples", "scada_samples"),
    ("missions", "missions"),
    ("decisions", "decisions"),
    ("work_orders", "work_orders"),
    ("evidence", "evidence"),
    ("generated_reports", "generated_reports"),
    ("knowledge_documents", "knowledge_documents"),
    ("registered_models", "registered_models"),
    ("domain_events", "domain_events"),
    ("read_access_audits", "read_access_audits"),
    ("read_access_audit_archives", "read_access_audit_archives"),
    ("benchmark_dataset_versions", "benchmark_dataset_versions"),
    ("benchmark_files", "benchmark_files"),
    ("benchmark_events", "benchmark_events"),
    ("benchmark_feature_maps", "benchmark_feature_maps"),
    ("benchmark_quality_reports", "benchmark_quality_reports"),
    ("benchmark_evaluation_runs", "benchmark_evaluation_runs"),
    ("benchmark_event_results", "benchmark_event_results"),
    ("benchmark_metric_snapshots", "benchmark_metric_snapshots"),
    ("benchmark_replay_runs", "benchmark_replay_runs"),
    ("anomaly_alert_policy_states", "anomaly_alert_policy_states"),
)
DATABASE_INVARIANT_QUERY = """
SELECT json_build_object(
    'wind_farms', (SELECT count(*) FROM wind_farms),
    'turbines', (SELECT count(*) FROM turbines),
    'scada_samples', (SELECT count(*) FROM scada_samples),
    'missions', (SELECT count(*) FROM missions),
    'decisions', (SELECT count(*) FROM decisions),
    'work_orders', (SELECT count(*) FROM work_orders),
    'evidence', (SELECT count(*) FROM evidence),
    'generated_reports', (SELECT count(*) FROM generated_reports),
    'knowledge_documents', (SELECT count(*) FROM knowledge_documents),
    'registered_models', (SELECT count(*) FROM registered_models),
    'domain_events', (SELECT count(*) FROM domain_events),
    'read_access_audits', (SELECT count(*) FROM read_access_audits),
    'read_access_audit_archives', (SELECT count(*) FROM read_access_audit_archives),
    'benchmark_dataset_versions', (SELECT count(*) FROM benchmark_dataset_versions),
    'benchmark_files', (SELECT count(*) FROM benchmark_files),
    'benchmark_events', (SELECT count(*) FROM benchmark_events),
    'benchmark_feature_maps', (SELECT count(*) FROM benchmark_feature_maps),
    'benchmark_quality_reports', (SELECT count(*) FROM benchmark_quality_reports),
    'benchmark_evaluation_runs', (SELECT count(*) FROM benchmark_evaluation_runs),
    'benchmark_event_results', (SELECT count(*) FROM benchmark_event_results),
    'benchmark_metric_snapshots', (SELECT count(*) FROM benchmark_metric_snapshots),
    'benchmark_replay_runs', (SELECT count(*) FROM benchmark_replay_runs),
    'anomaly_alert_policy_states', (SELECT count(*) FROM anomaly_alert_policy_states)
)::text
""".strip()
MANIFEST_NAME = "manifest.json"
MANIFEST_DIGEST_NAME = "manifest.sha256"


def database_connection(database_url: str) -> tuple[str, str, str]:
    """Return a password-free libpq URL, password, and decoded database name."""

    normalized = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlsplit(normalized)
    if parsed.scheme != "postgresql" or not parsed.hostname:
        raise ValueError("backup and restore require a PostgreSQL URL")
    database_name = unquote(parsed.path.lstrip("/"))
    if not database_name or "/" in database_name or "\\" in database_name:
        raise ValueError("PostgreSQL URL must identify exactly one database")
    username = quote(unquote(parsed.username or ""), safe="")
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    authority = f"{username}@{host}" if username else host
    if parsed.port is not None:
        authority = f"{authority}:{parsed.port}"
    safe_url = urlunsplit(
        SplitResult("postgresql", authority, parsed.path, parsed.query, parsed.fragment)
    )
    return safe_url, unquote(parsed.password or ""), database_name


def validate_confirmed_target(database_url: str, confirmed_target: str) -> str:
    _, _, database_name = database_connection(database_url)
    if not confirmed_target or not compare_digest(database_name, confirmed_target):
        raise ValueError(
            "restore target confirmation must exactly match the database name in the URL"
        )
    return database_name


def _subprocess_environment(password: str) -> dict[str, str]:
    environment = os.environ.copy()
    if password:
        environment["PGPASSWORD"] = password
    else:
        environment.pop("PGPASSWORD", None)
    return environment


def _run_postgres_command(
    command: Sequence[str],
    password: str,
) -> subprocess.CompletedProcess[str]:
    if not command or command[0] not in {"pg_dump", "pg_restore", "psql"}:
        raise ValueError("unsupported PostgreSQL client command")
    return subprocess.run(  # nosec B603 - argv list, shell disabled, executable allowlisted
        list(command),
        check=True,
        capture_output=True,
        text=True,
        env=_subprocess_environment(password),
    )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@contextmanager
def _export_postgres_snapshot(safe_url: str, password: str) -> Iterator[str]:
    """Keep an exported REPEATABLE READ snapshot alive for dump metadata queries."""

    process = subprocess.Popen(  # nosec B603 - fixed psql executable, shell disabled
        (
            "psql",
            f"--dbname={safe_url}",
            "--no-psqlrc",
            "--quiet",
            "--tuples-only",
            "--no-align",
            "--set=ON_ERROR_STOP=1",
        ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=_subprocess_environment(password),
    )
    try:
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("failed to open the PostgreSQL snapshot session")
        process.stdin.write("BEGIN ISOLATION LEVEL REPEATABLE READ;\n")
        process.stdin.write("SELECT pg_export_snapshot();\n")
        process.stdin.flush()
        snapshot_id = process.stdout.readline().strip()
        if not snapshot_id:
            stderr = process.stderr.read().strip() if process.stderr is not None else ""
            raise RuntimeError(
                "PostgreSQL did not return an exported snapshot" + (f": {stderr}" if stderr else "")
            )
        yield snapshot_id
    finally:
        if process.poll() is None:
            try:
                process.communicate(input="ROLLBACK;\n\\q\n", timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def _snapshot_query(
    safe_url: str,
    password: str,
    snapshot_id: str,
    query: str,
) -> subprocess.CompletedProcess[str]:
    command = (
        "BEGIN ISOLATION LEVEL REPEATABLE READ; "
        f"SET TRANSACTION SNAPSHOT {_sql_literal(snapshot_id)}; "
        f"{query};"
    )
    return _run_postgres_command(
        (
            "psql",
            f"--dbname={safe_url}",
            "--quiet",
            "--tuples-only",
            "--no-align",
            "--set=ON_ERROR_STOP=1",
            f"--command={command}",
        ),
        password,
    )


def current_schema_revision(database_url: str, *, snapshot_id: str | None = None) -> str:
    safe_url, password, _ = database_connection(database_url)
    result = (
        _snapshot_query(
            safe_url,
            password,
            snapshot_id,
            "SELECT version_num FROM alembic_version",
        )
        if snapshot_id is not None
        else _run_postgres_command(
            (
                "psql",
                f"--dbname={safe_url}",
                "--tuples-only",
                "--no-align",
                "--command=SELECT version_num FROM alembic_version",
            ),
            password,
        )
    )
    revisions = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(revisions) != 1:
        raise RuntimeError("database must contain exactly one Alembic head revision")
    return revisions[0]


def current_database_invariants(
    database_url: str, *, snapshot_id: str | None = None
) -> dict[str, int]:
    safe_url, password, _ = database_connection(database_url)
    query = DATABASE_INVARIANT_QUERY
    result = (
        _snapshot_query(safe_url, password, snapshot_id, query)
        if snapshot_id is not None
        else _run_postgres_command(
            (
                "psql",
                f"--dbname={safe_url}",
                "--tuples-only",
                "--no-align",
                f"--command={query}",
            ),
            password,
        )
    )
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(rows) != 1:
        raise RuntimeError("database invariant query did not return exactly one row")
    loaded = json.loads(rows[0])
    if not isinstance(loaded, dict) or any(
        not isinstance(key, str) or not isinstance(value, int) for key, value in loaded.items()
    ):
        raise RuntimeError("database invariant query returned an invalid payload")
    return cast(dict[str, int], loaded)


def minio_client(settings: Settings) -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key.get_secret_value(),
        secure=settings.minio_secure,
    )


def governed_bucket_bindings(settings: Settings) -> dict[str, str]:
    return {
        "field_evidence": settings.minio_field_evidence_bucket,
        "knowledge": settings.minio_knowledge_bucket,
        "model": settings.minio_model_bucket,
        "twin": settings.minio_twin_bucket,
        "care": settings.minio_care_bucket,
    }


def governed_buckets(settings: Settings) -> tuple[str, ...]:
    return tuple(governed_bucket_bindings(settings).values())


def object_is_in_governed_backup_scope(bucket_role: str, object_name: str) -> bool:
    if bucket_role != "care":
        return True
    if object_name.startswith(CARE_TEMPORARY_PREFIX):
        return False
    if not any(object_name.startswith(prefix) for prefix in CARE_BACKUP_PREFIXES):
        raise RuntimeError(f"CARE object is outside the governed backup prefixes: {object_name}")
    return True


def safe_configuration_snapshot(settings: Settings) -> dict[str, Any]:
    return {
        "environment": settings.environment.value,
        "api_prefix": settings.api_prefix,
        "release": {
            "release_id": settings.release_id,
            "commit_sha": settings.release_commit_sha,
            "image_digest": settings.release_image_digest,
        },
        "docs_enabled": settings.docs_enabled,
        "trusted_hosts": list(settings.trusted_hosts),
        "rate_limit": {
            "enabled": settings.rate_limit_enabled,
            "principal_requests_per_minute": settings.rate_limit_requests_per_minute,
            "client_requests_per_minute": settings.rate_limit_client_requests_per_minute,
        },
        "auth_mode": settings.auth_mode,
        "agent_mode": settings.agent_mode,
        "litellm_model": settings.litellm_model,
        "embedding_model": settings.embedding_model,
        "knowledge_graph_backend": settings.knowledge_graph_backend,
        "neo4j_database": settings.neo4j_database,
        "minio_endpoint": settings.minio_endpoint,
        "minio_secure": settings.minio_secure,
        "governed_buckets": governed_bucket_bindings(settings),
        "otel_enabled": settings.otel_enabled,
        "otel_service_name": settings.otel_service_name,
        "slo": {
            "http_availability": settings.slo_http_availability_target,
            "http_p95_latency_seconds": settings.slo_http_p95_latency_seconds,
            "agent_success": settings.slo_agent_success_target,
            "telemetry_freshness_seconds": settings.slo_telemetry_freshness_seconds,
        },
    }


def _artifact_entry(
    *,
    kind: str,
    path: Path,
    root: Path,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "kind": kind,
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if extra:
        entry.update(extra)
    return entry


def create_backup(settings: Settings, output_dir: Path) -> Path:
    output_root = output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final_path = output_root / f"windops-backup-{stamp}"
    incomplete_path = output_root / f".windops-backup-{stamp}.incomplete"
    if final_path.exists() or incomplete_path.exists():
        raise FileExistsError("backup target already exists; retry with a new timestamp")
    incomplete_path.mkdir()

    safe_url, password, database_name = database_connection(settings.database_url)
    database_dump = incomplete_path / "postgresql.dump"
    with _export_postgres_snapshot(safe_url, password) as snapshot_id:
        _run_postgres_command(
            (
                "pg_dump",
                f"--dbname={safe_url}",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                f"--snapshot={snapshot_id}",
                f"--file={database_dump}",
            ),
            password,
        )
        # Capture all PostgreSQL metadata through the exact snapshot used by
        # pg_dump. Object-store downloads happen after this transaction closes.
        schema_revision = current_schema_revision(settings.database_url, snapshot_id=snapshot_id)
        database_invariants = current_database_invariants(
            settings.database_url, snapshot_id=snapshot_id
        )
    artifacts = [
        _artifact_entry(
            kind="postgresql",
            path=database_dump,
            root=incomplete_path,
            extra={"database_name": database_name},
        )
    ]

    configuration_path = incomplete_path / "safe-config.json"
    configuration_path.write_text(
        json.dumps(safe_configuration_snapshot(settings), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifacts.append(
        _artifact_entry(kind="configuration", path=configuration_path, root=incomplete_path)
    )

    client = minio_client(settings)
    bucket_bindings = governed_bucket_bindings(settings)
    for bucket_role, bucket in bucket_bindings.items():
        if not client.bucket_exists(bucket):
            raise RuntimeError(f"required bucket is missing: {bucket}")
        for object_info in client.list_objects(bucket, recursive=True):
            object_name = object_info.object_name
            if not object_is_in_governed_backup_scope(bucket_role, object_name):
                continue
            object_id = hashlib.sha256(object_name.encode()).hexdigest()
            object_path = incomplete_path / "objects" / bucket / object_id
            object_path.parent.mkdir(parents=True, exist_ok=True)
            object_stat = client.stat_object(bucket, object_name)
            client.fget_object(bucket, object_name, str(object_path))
            artifacts.append(
                _artifact_entry(
                    kind="minio",
                    path=object_path,
                    root=incomplete_path,
                    extra={
                        "bucket": bucket,
                        "bucket_role": bucket_role,
                        "object_name": object_name,
                        "content_type": object_stat.content_type,
                    },
                )
            )

    manifest = {
        "format_version": BACKUP_FORMAT_VERSION,
        "complete": True,
        "created_at": datetime.now(UTC).isoformat(),
        "database_name": database_name,
        "schema_revision": schema_revision,
        "database_invariants": database_invariants,
        "buckets": list(governed_buckets(settings)),
        "bucket_bindings": bucket_bindings,
        "artifacts": artifacts,
    }
    manifest_path = incomplete_path / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (incomplete_path / MANIFEST_DIGEST_NAME).write_text(
        f"{sha256_file(manifest_path)}  {MANIFEST_NAME}\n",
        encoding="ascii",
    )
    incomplete_path.replace(final_path)
    return final_path


def _safe_bundle_path(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError("manifest artifact path must be relative")
    unresolved = root / relative_path
    cursor = root
    for part in Path(relative_path).parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("backup artifacts cannot contain symbolic links")
    candidate = unresolved.resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("manifest artifact path escapes the backup bundle")
    return candidate


def verify_backup_bundle(bundle: Path) -> dict[str, Any]:
    root = bundle.resolve()
    manifest_path = root / MANIFEST_NAME
    digest_path = root / MANIFEST_DIGEST_NAME
    if not manifest_path.is_file() or not digest_path.is_file():
        raise ValueError("backup manifest or digest sidecar is missing")
    digest_tokens = digest_path.read_text(encoding="ascii").split()
    if not digest_tokens:
        raise ValueError("backup manifest digest sidecar is empty")
    expected_manifest_digest = digest_tokens[0]
    if (
        len(expected_manifest_digest) != 64
        or sha256_file(manifest_path) != expected_manifest_digest
    ):
        raise ValueError("backup manifest digest mismatch")
    loaded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(loaded_manifest, dict):
        raise ValueError("backup manifest root must be an object")
    manifest = cast(dict[str, Any], loaded_manifest)
    if (
        manifest.get("format_version") not in {LEGACY_BACKUP_FORMAT_VERSION, BACKUP_FORMAT_VERSION}
        or manifest.get("complete") is not True
    ):
        raise ValueError("unsupported or incomplete backup bundle")
    if not isinstance(manifest.get("database_name"), str) or not manifest["database_name"]:
        raise ValueError("backup manifest database identity is missing")
    if not isinstance(manifest.get("schema_revision"), str) or not manifest["schema_revision"]:
        raise ValueError("backup manifest schema revision is missing")
    invariants = manifest.get("database_invariants")
    if not isinstance(invariants, dict) or any(
        not isinstance(key, str) or not isinstance(value, int) or value < 0
        for key, value in invariants.items()
    ):
        raise ValueError("backup manifest database invariants are invalid")
    buckets = manifest.get("buckets")
    if (
        not isinstance(buckets, list)
        or not buckets
        or any(not isinstance(bucket, str) or not bucket for bucket in buckets)
        or len(buckets) != len(set(buckets))
    ):
        raise ValueError("backup manifest bucket identities are invalid")
    bucket_bindings = manifest.get("bucket_bindings")
    if manifest["format_version"] == BACKUP_FORMAT_VERSION:
        if (
            not isinstance(bucket_bindings, dict)
            or set(bucket_bindings) != set(GOVERNED_BUCKET_ROLES)
            or any(
                not isinstance(role, str) or not isinstance(bucket, str) or not bucket
                for role, bucket in bucket_bindings.items()
            )
            or len(set(bucket_bindings.values())) != len(GOVERNED_BUCKET_ROLES)
            or set(bucket_bindings.values()) != set(buckets)
        ):
            raise ValueError("backup manifest bucket role bindings are invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("backup manifest contains no artifacts")
    postgres_count = 0
    seen_paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("invalid backup artifact record")
        relative_path = artifact.get("path")
        if not isinstance(relative_path, str) or relative_path in seen_paths:
            raise ValueError("backup artifact paths must be unique strings")
        seen_paths.add(relative_path)
        artifact_path = _safe_bundle_path(root, relative_path)
        if not artifact_path.is_file():
            raise ValueError(f"backup artifact is missing: {relative_path}")
        if artifact_path.stat().st_size != artifact.get("bytes"):
            raise ValueError(f"backup artifact size mismatch: {relative_path}")
        if sha256_file(artifact_path) != artifact.get("sha256"):
            raise ValueError(f"backup artifact digest mismatch: {relative_path}")
        if artifact.get("kind") == "postgresql":
            postgres_count += 1
        elif artifact.get("kind") == "minio":
            if not artifact.get("bucket") or not artifact.get("object_name"):
                raise ValueError("MinIO artifact is missing its object identity")
            if artifact["bucket"] not in buckets:
                raise ValueError("MinIO artifact references an undeclared bucket")
            if manifest["format_version"] == BACKUP_FORMAT_VERSION and (
                artifact.get("bucket_role") not in GOVERNED_BUCKET_ROLES
                or cast(dict[str, str], bucket_bindings)[str(artifact["bucket_role"])]
                != artifact["bucket"]
            ):
                raise ValueError("MinIO artifact bucket role is invalid")
        elif artifact.get("kind") != "configuration":
            raise ValueError("backup manifest contains an unsupported artifact kind")
    if postgres_count != 1:
        raise ValueError("backup bundle must contain exactly one PostgreSQL dump")
    return manifest


def _minio_artifacts(manifest: dict[str, Any]) -> Iterable[dict[str, Any]]:
    return (artifact for artifact in manifest["artifacts"] if artifact["kind"] == "minio")


def _restore_bucket(
    manifest: dict[str, Any],
    target_bindings: dict[str, str],
    artifact: dict[str, Any],
) -> str:
    if manifest["format_version"] == LEGACY_BACKUP_FORMAT_VERSION:
        return str(artifact["bucket"])
    return target_bindings[str(artifact["bucket_role"])]


def restore_backup(
    settings: Settings,
    bundle: Path,
    *,
    confirmed_target: str,
    allow_object_overwrite: bool,
    allow_database_rename: bool = False,
) -> None:
    manifest = verify_backup_bundle(bundle)
    database_name = validate_confirmed_target(settings.database_url, confirmed_target)
    if database_name != manifest.get("database_name") and not allow_database_rename:
        raise ValueError("backup database identity does not match the restore target")
    target_bindings = governed_bucket_bindings(settings)
    if manifest["format_version"] == LEGACY_BACKUP_FORMAT_VERSION:
        if set(manifest["buckets"]) != set(target_bindings.values()):
            raise ValueError("legacy backup bucket identities do not match the restore environment")
    elif set(manifest["bucket_bindings"]) != set(target_bindings):
        raise ValueError("backup bucket roles do not match the restore environment")
    root = bundle.resolve()
    client = minio_client(settings)
    for bucket in target_bindings.values():
        if not client.bucket_exists(bucket):
            raise RuntimeError(f"restore target bucket is missing: {bucket}")
    if not allow_object_overwrite:
        for artifact in _minio_artifacts(manifest):
            target_bucket = _restore_bucket(manifest, target_bindings, artifact)
            try:
                client.stat_object(target_bucket, artifact["object_name"])
            except S3Error as exc:
                if exc.code not in {"NoSuchKey", "NoSuchObject", "NoSuchVersion"}:
                    raise
            else:
                raise FileExistsError(
                    "restore target object already exists: "
                    f"{target_bucket}/{artifact['object_name']}"
                )

    database_artifact = next(
        artifact for artifact in manifest["artifacts"] if artifact["kind"] == "postgresql"
    )
    safe_url, password, _ = database_connection(settings.database_url)
    database_dump_path = _safe_bundle_path(root, database_artifact["path"])
    # Validate the custom dump before any destructive target operation.
    _run_postgres_command(("pg_restore", "--list", str(database_dump_path)), password)
    _run_postgres_command(
        (
            "pg_restore",
            f"--dbname={safe_url}",
            "--clean",
            "--if-exists",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-acl",
            str(database_dump_path),
        ),
        password,
    )
    for artifact in _minio_artifacts(manifest):
        target_bucket = _restore_bucket(manifest, target_bindings, artifact)
        client.fput_object(
            target_bucket,
            artifact["object_name"],
            str(_safe_bundle_path(root, artifact["path"])),
            content_type=artifact.get("content_type") or "application/octet-stream",
            metadata={"sha256": artifact["sha256"]},
        )
    if current_schema_revision(settings.database_url) != manifest["schema_revision"]:
        raise RuntimeError("restored database schema revision does not match the backup")
    if current_database_invariants(settings.database_url) != manifest["database_invariants"]:
        raise RuntimeError("restored database row-count invariants do not match the backup")
    with tempfile.TemporaryDirectory(prefix="windops-restore-verify-") as temporary:
        for index, artifact in enumerate(_minio_artifacts(manifest)):
            target_bucket = _restore_bucket(manifest, target_bindings, artifact)
            verification_path = Path(temporary) / str(index)
            client.fget_object(target_bucket, artifact["object_name"], str(verification_path))
            if sha256_file(verification_path) != artifact["sha256"]:
                raise RuntimeError(
                    f"restored object digest mismatch: {target_bucket}/{artifact['object_name']}"
                )


def backup_main() -> None:
    parser = argparse.ArgumentParser(description="Create a verified OpenVigil recovery bundle")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    backup_path = create_backup(get_settings(), args.output_dir)
    print(backup_path)


def restore_main() -> None:
    parser = argparse.ArgumentParser(description="Restore a verified OpenVigil recovery bundle")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--confirm-target", required=True)
    parser.add_argument("--allow-object-overwrite", action="store_true")
    parser.add_argument("--allow-database-rename", action="store_true")
    args = parser.parse_args()
    restore_backup(
        get_settings(),
        args.bundle,
        confirmed_target=args.confirm_target,
        allow_object_overwrite=args.allow_object_overwrite,
        allow_database_rename=args.allow_database_rename,
    )
