from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from windops_backend.config import Settings, get_settings
from windops_backend.operations.backups import (
    MANIFEST_NAME,
    create_backup,
    database_connection,
    governed_buckets,
    restore_backup,
    sha256_file,
    verify_backup_bundle,
)


def validate_drill_targets(source: Settings, target: Settings) -> str:
    _, _, source_database = database_connection(source.database_url)
    _, _, target_database = database_connection(target.database_url)
    if source_database == target_database:
        raise ValueError("disaster-recovery drill database must be isolated from the source")
    overlapping_buckets = set(governed_buckets(source)).intersection(governed_buckets(target))
    if overlapping_buckets:
        raise ValueError(
            "disaster-recovery drill buckets must be isolated from the source: "
            f"{', '.join(sorted(overlapping_buckets))}"
        )
    return target_database


def target_settings_from_environment(source: Settings) -> Settings:
    required = {
        "database_url": "WINDOPS_DR_TARGET_DATABASE_URL",
        "minio_endpoint": "WINDOPS_DR_TARGET_MINIO_ENDPOINT",
        "minio_access_key": "WINDOPS_DR_TARGET_MINIO_ACCESS_KEY",
        "minio_secret_key": "WINDOPS_DR_TARGET_MINIO_SECRET_KEY",  # nosec B105 - env name
        "minio_field_evidence_bucket": "WINDOPS_DR_TARGET_FIELD_EVIDENCE_BUCKET",
        "minio_knowledge_bucket": "WINDOPS_DR_TARGET_KNOWLEDGE_BUCKET",
        "minio_model_bucket": "WINDOPS_DR_TARGET_MODEL_BUCKET",
        "minio_twin_bucket": "WINDOPS_DR_TARGET_TWIN_BUCKET",
        "minio_care_bucket": "WINDOPS_DR_TARGET_CARE_BUCKET",
    }
    missing = [
        environment_name
        for environment_name in required.values()
        if not os.getenv(environment_name)
    ]
    if missing:
        raise ValueError(f"missing disaster-recovery target settings: {', '.join(missing)}")
    values = source.model_dump()
    for setting_name, environment_name in required.items():
        values[setting_name] = os.environ[environment_name]
    secure = os.getenv("WINDOPS_DR_TARGET_MINIO_SECURE", "true").strip().lower()
    if secure not in {"true", "false"}:
        raise ValueError("WINDOPS_DR_TARGET_MINIO_SECURE must be true or false")
    values["minio_secure"] = secure == "true"
    return Settings(**values)


def run_disaster_recovery_drill(
    source: Settings,
    target: Settings,
    output_dir: Path,
    *,
    confirmed_target: str,
) -> Path:
    target_database = validate_drill_targets(source, target)
    if confirmed_target != target_database:
        raise ValueError("drill confirmation must exactly match the isolated target database")
    started_at = datetime.now(UTC)
    started = time.monotonic()
    backup_path = create_backup(source, output_dir)
    manifest = verify_backup_bundle(backup_path)
    restore_backup(
        target,
        backup_path,
        confirmed_target=confirmed_target,
        allow_object_overwrite=False,
        allow_database_rename=True,
    )
    completed_at = datetime.now(UTC)
    evidence: dict[str, Any] = {
        "status": "verified",
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "recovery_time_seconds": round(time.monotonic() - started, 3),
        "recovery_point": manifest["created_at"],
        "source_database": manifest["database_name"],
        "target_database": target_database,
        "schema_revision": manifest["schema_revision"],
        "database_invariants": manifest["database_invariants"],
        "artifact_count": len(manifest["artifacts"]),
        "manifest_sha256": sha256_file(backup_path / MANIFEST_NAME),
        "object_overwrite_allowed": False,
        "source_target_isolation_verified": True,
    }
    evidence_path = output_dir.resolve() / (
        f"dr-drill-evidence-{completed_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return evidence_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Back up WindOps and restore it into an explicitly isolated drill target"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--confirm-target", required=True)
    args = parser.parse_args()
    source = get_settings()
    target = target_settings_from_environment(source)
    evidence_path = run_disaster_recovery_drill(
        source,
        target,
        args.output_dir,
        confirmed_target=args.confirm_target,
    )
    print(evidence_path)
