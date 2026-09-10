from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from minio.error import S3Error

from windops_backend.benchmarks.care.dependency_closure import (
    verify_benchmark_dependency_closure,
)
from windops_backend.benchmarks.care.pipeline import (
    BenchmarkJobCancelled,
    MinioImmutableArtifactStore,
    convert_care_csv_to_parquet,
)
from windops_backend.benchmarks.care.runtime import (
    care_minio_client,
    get_care_worker_settings,
)

CARE_QUEUE = "care-v6-offline"
CARE_MAX_CONCURRENCY = 1
CARE_MAX_ATTEMPTS = 3
SMOKE_FIXTURE = Path(__file__).parents[1] / "benchmarks" / "care" / "smoke_fixture.csv"
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class CareExecutionPlaneError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise CareExecutionPlaneError(f"CARE execution plane requires {name}")
    return value


def verify_execution_contract() -> dict[str, str | int]:
    queue = _required_environment("WINDOPS_CARE_QUEUE")
    if queue != CARE_QUEUE:
        raise CareExecutionPlaneError(f"CARE work must use the isolated {CARE_QUEUE} queue")
    try:
        concurrency = int(_required_environment("WINDOPS_CARE_MAX_CONCURRENCY"))
        max_attempts = int(_required_environment("WINDOPS_CARE_MAX_ATTEMPTS"))
    except ValueError as exc:
        raise CareExecutionPlaneError("CARE concurrency and attempts must be integers") from exc
    if concurrency != CARE_MAX_CONCURRENCY:
        raise CareExecutionPlaneError("CARE execution concurrency must be exactly one")
    if max_attempts != CARE_MAX_ATTEMPTS:
        raise CareExecutionPlaneError("CARE retry attempts must be exactly three")
    release_id = _required_environment("WINDOPS_RELEASE_ID")
    commit_sha = _required_environment("WINDOPS_RELEASE_COMMIT_SHA")
    image_digest = _required_environment("WINDOPS_RELEASE_IMAGE_DIGEST")
    if _COMMIT_SHA.fullmatch(commit_sha) is None or _IMAGE_DIGEST.fullmatch(image_digest) is None:
        raise CareExecutionPlaneError(
            "CARE workload requires immutable commit and image identities"
        )
    return {
        "queue": queue,
        "max_concurrency": concurrency,
        "max_attempts": max_attempts,
        "release_id": release_id,
        "commit_sha": commit_sha,
        "image_digest": image_digest,
    }


def _verify_source_is_read_only(source: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise CareExecutionPlaneError("CARE smoke source is missing or unsafe")
    filesystem_read_only = hasattr(os, "statvfs") and bool(
        os.statvfs(source).f_flag & getattr(os, "ST_RDONLY", 1)
    )
    writable_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    mode_read_only = not bool(source.stat().st_mode & writable_bits)
    if not filesystem_read_only and not mode_read_only:
        raise CareExecutionPlaneError("CARE execution source must be mounted read-only")


def _minio_store() -> tuple[MinioImmutableArtifactStore, list[str]]:
    settings = get_care_worker_settings()
    bucket = settings.minio_bucket
    client = care_minio_client(settings)
    try:
        if not client.bucket_exists(bucket):
            raise CareExecutionPlaneError("the isolated CARE bucket does not exist")
    except S3Error as exc:
        raise CareExecutionPlaneError("the isolated CARE bucket is not accessible") from exc
    forbidden = list(settings.forbidden_bucket_names)
    for forbidden_bucket in forbidden:
        try:
            client.bucket_exists(forbidden_bucket)
        except S3Error as exc:
            if exc.code == "AccessDenied":
                continue
            raise CareExecutionPlaneError(
                f"unexpected CARE storage denial for {forbidden_bucket}"
            ) from exc
        raise CareExecutionPlaneError(
            f"CARE worker credentials can access forbidden bucket {forbidden_bucket}"
        )
    return MinioImmutableArtifactStore(client, bucket), forbidden


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    if path.is_symlink():
        raise CareExecutionPlaneError("CARE smoke report cannot overwrite a symbolic link")
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def run_execution_plane_smoke(
    workspace: Path,
    report_path: Path,
    requirements_lock: Path,
    *,
    publish_to_configured_minio: bool,
    source: Path = SMOKE_FIXTURE,
) -> dict[str, Any]:
    contract = verify_execution_contract()
    _verify_source_is_read_only(source)
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if source.resolve().is_relative_to(workspace):
        raise CareExecutionPlaneError("CARE source cannot be inside the writable workspace")
    dependency = verify_benchmark_dependency_closure(requirements_lock)
    output_root = workspace / "pipeline"
    job_id = f"execution-plane-smoke-{str(contract['commit_sha'])[:12]}"
    try:
        convert_care_csv_to_parquet(
            source,
            output_root,
            job_id=job_id,
            farm="A",
            event_id=94,
            stop_after_chunks=1,
            csv_block_size_bytes=64 * 1024,
        )
    except BenchmarkJobCancelled:
        pass
    else:
        raise CareExecutionPlaneError("CARE smoke did not stop at its durable checkpoint")
    artifact = convert_care_csv_to_parquet(
        source,
        output_root,
        job_id=job_id,
        farm="A",
        event_id=94,
        csv_block_size_bytes=64 * 1024,
    )
    replayed = convert_care_csv_to_parquet(
        source,
        output_root,
        job_id=job_id,
        farm="A",
        event_id=94,
        csv_block_size_bytes=64 * 1024,
    )
    if replayed != artifact:
        raise CareExecutionPlaneError("CARE smoke idempotent replay changed the artifact")

    proof: dict[str, Any] = {
        "format_version": 1,
        "gate": "care_execution_plane_smoke",
        "status": "passed",
        "runtime": contract,
        "dependency_closure": dependency,
        "source": {"kind": "synthetic-smoke-only", "sha256": _sha256(source)},
        "checkpoint_resume": True,
        "idempotent_replay": True,
        "row_count": artifact.row_count,
        "parquet_sha256": artifact.content_sha256,
        "published_to_care_bucket": False,
    }
    if publish_to_configured_minio:
        store, forbidden = _minio_store()
        proof_path = workspace / "execution-plane-proof.json"
        _atomic_json(proof_path, proof)
        proof_sha256 = _sha256(proof_path)
        uri = store.put_immutable(
            f"care/v6/reports/execution-plane-smoke/proof.sha256-{proof_sha256}.json",
            proof_path,
            proof_sha256,
            content_type="application/json",
        )
        proof.update(
            {
                "published_to_care_bucket": True,
                "storage_scope_denied_buckets": forbidden,
                "storage_proof_uri": uri,
                "storage_proof_sha256": proof_sha256,
            }
        )
    _atomic_json(report_path, proof)
    return proof


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise the isolated, checkpointed CARE production execution plane"
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--requirements-lock", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=SMOKE_FIXTURE)
    parser.add_argument("--publish-to-configured-minio", action="store_true")
    args = parser.parse_args()
    report = run_execution_plane_smoke(
        args.workspace,
        args.report,
        args.requirements_lock,
        publish_to_configured_minio=args.publish_to_configured_minio,
        source=args.source,
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
