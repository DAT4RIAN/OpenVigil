from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from windops_backend.benchmarks.care.pipeline import (
    PARQUET_COMPRESSION,
    PARQUET_COMPRESSION_LEVEL,
    PARQUET_ROW_GROUP_SIZE,
    BenchmarkJobCancelled,
    BenchmarkJobState,
    CareObjectStorageLayout,
    CarePipelineError,
    FileBenchmarkJobControl,
    LocalImmutableArtifactStore,
    MinioImmutableArtifactStore,
    ParquetArtifact,
    ParquetCheckpoint,
    RetryableBenchmarkError,
    build_pipeline_contract,
    convert_care_csv_to_parquet,
    probe_care_csv_bounded,
    run_with_bounded_retries,
    verify_parquet_column_projection,
    verify_pipeline_contract,
    write_bounded_probe,
)
from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.operations.backups import governed_buckets

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@pytest.fixture(scope="module")
def wide_csv(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("care-pipeline-source")
    path = root / "event_7.csv"
    sensors = [f"sensor_{index}_Avg" for index in range(48)]
    header = ["time_stamp", "asset_id", "id", "train_test", "status_type_id", *sensors]
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(";".join(header) + "\n")
        for row_id in range(18_000):
            values = [
                f"2024-01-{1 + row_id // 1440:02d} 00:00:00",
                "WT-A01",
                str(row_id),
                "train" if row_id < 17_000 else "prediction",
                "1",
                *(f"{row_id * 0.01 + sensor_index:.4f}" for sensor_index in range(48)),
            ]
            stream.write(";".join(values) + "\n")
    assert path.stat().st_size > 5 * 1024 * 1024
    return path


def test_pipeline_contract_dependency_lock_and_online_import_boundary() -> None:
    first = build_pipeline_contract()
    second = build_pipeline_contract()
    assert first == second
    assert first["execution"]["operations"] == ["import", "quality", "train", "evaluate"]
    assert first["parquet"] == {
        "layout_version": "care-v6-wide-parquet-v2",
        "shape": "one-wide-table-per-dataset-version-farm-event",
        "partition_keys": ["dataset_version", "farm", "event"],
        "compression": "zstd",
        "compression_level": 3,
        "row_group_size": 8192,
        "csv_block_size_bytes": 1048576,
        "column_projection": True,
        "manifest_fields": ["schema_sha256", "row_count", "content_sha256"],
        "object_naming": "content-addressed-data.sha256-<content_sha256>.parquet",
    }
    verify_pipeline_contract(first)
    with pytest.raises(CarePipelineError, match="hash or frozen semantics"):
        verify_pipeline_contract({**first, "contract_sha256": "0" * 64})

    pyproject = tomllib.loads((REPOSITORY_ROOT / "backend/pyproject.toml").read_text())
    assert pyproject["project"]["optional-dependencies"]["benchmark"] == [
        "pyarrow>=23.0.1,<24",
        "scikit-learn>=1.7,<2",
    ]
    assert pyproject["project"]["scripts"]["windops-care-pipeline"].endswith(":main")
    lock = (REPOSITORY_ROOT / "backend/uv.lock").read_text(encoding="utf-8")
    assert 'name = "pyarrow"\nversion = "23.0.1"' in lock
    assert 'name = "scikit-learn"\nversion = "1.9.0"' in lock

    check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import windops_backend.main; "
                "assert not any(n == 'pyarrow' or n.startswith('pyarrow.') for n in sys.modules); "
                "assert not any(n == 'sklearn' or n.startswith('sklearn.') for n in sys.modules)"
            ),
        ],
        cwd=REPOSITORY_ROOT / "backend",
        check=False,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr


def test_object_layout_settings_lifecycle_policy_and_backup_scope() -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url="sqlite+aiosqlite:///:memory:",
        schema_bootstrap=True,
        knowledge_graph_backend="memory",
    )
    layout = CareObjectStorageLayout.from_settings(settings)
    assert layout.bucket == "windops-care-benchmarks"
    assert layout.event_key("standard", farm="C", event_id=94, file_name="data.parquet") == (
        "care/v6/standard/farm=C/event=94/data.parquet"
    )
    assert layout.contract_document()["public_access"] is False
    assert layout.contract_document()["lifecycle"]["temporary"]["expire_after_days"] == 7
    assert settings.minio_care_bucket in governed_buckets(settings)

    lifecycle = json.loads(
        (REPOSITORY_ROOT / "backend/deploy/care-minio-lifecycle.json").read_text()
    )
    rules = {item["Filter"]["Prefix"]: item["Expiration"]["Days"] for item in lifecycle["Rules"]}
    assert rules == {
        "care/v6/_tmp/": 7,
        "care/v6/raw/": 3650,
        "care/v6/standard/": 3650,
        "care/v6/quality/": 3650,
        "care/v6/predictions/": 1825,
        "care/v6/reports/": 3650,
    }
    compose = (REPOSITORY_ROOT / "backend/docker-compose.yml").read_text()
    assert "mc version enable local/windops-care-benchmarks" in compose
    assert "mc ilm import local/windops-care-benchmarks" in compose
    policy = json.loads(
        (REPOSITORY_ROOT / "backend/deploy/care-minio-worker-policy.json").read_text()
    )
    serialized_policy = json.dumps(policy, sort_keys=True)
    assert "s3:DeleteObject" not in serialized_policy
    assert "windops-care-benchmarks/care/v6/*" in serialized_policy
    worker_location = next(
        statement
        for statement in policy["Statement"]
        if statement["Action"] == ["s3:GetBucketLocation"]
    )
    worker_list = next(
        statement for statement in policy["Statement"] if statement["Action"] == ["s3:ListBucket"]
    )
    assert "Condition" not in worker_location
    assert worker_list["Condition"]["StringLike"]["s3:prefix"] == ["care/v6/*"]
    cleanup_policy = json.loads(
        (REPOSITORY_ROOT / "backend/deploy/care-minio-cleanup-policy.json").read_text()
    )
    cleanup_serialized = json.dumps(cleanup_policy, sort_keys=True)
    assert "s3:DeleteObject" in cleanup_serialized
    assert "care/v6/raw" not in cleanup_serialized
    cleanup_location = next(
        statement
        for statement in cleanup_policy["Statement"]
        if statement["Action"] == ["s3:GetBucketLocation"]
    )
    assert "Condition" not in cleanup_location
    for layer in ("standard", "quality", "predictions", "reports"):
        assert f"windops-care-benchmarks/care/v6/{layer}/*" in cleanup_serialized

    with pytest.raises(ValueError, match="prefixes must be distinct and safe"):
        Settings(
            environment=Environment.TEST,
            database_url="sqlite+aiosqlite:///:memory:",
            knowledge_graph_backend="memory",
            minio_care_raw_prefix="../raw",
        )
    with pytest.raises(ValueError, match="prefixes must be distinct and safe"):
        Settings(
            environment=Environment.TEST,
            database_url="sqlite+aiosqlite:///:memory:",
            knowledge_graph_backend="memory",
            minio_care_raw_prefix="care/v6/raw\\escape",
        )
    with pytest.raises(ValueError, match="operationally isolated"):
        Settings(
            environment=Environment.TEST,
            database_url="sqlite+aiosqlite:///:memory:",
            knowledge_graph_backend="memory",
            minio_care_bucket="windops-model-artifacts",
        )
    with pytest.raises(CarePipelineError, match="prefixes must be distinct"):
        CareObjectStorageLayout(quality_prefix="care/v6/raw")


def test_wide_parquet_is_bounded_projectable_and_immutable(wide_csv: Path, tmp_path: Path) -> None:
    output_root = tmp_path / "pipeline-output"
    store_root = tmp_path / "object-store"
    source_sha = _sha256(wide_csv)
    artifact = convert_care_csv_to_parquet(
        wide_csv,
        output_root,
        job_id="fixture-import-1",
        farm="A",
        event_id=7,
        artifact_store=LocalImmutableArtifactStore(store_root),
        expected_source_sha256=source_sha,
    )
    assert artifact.row_count == 18_000
    assert (
        artifact.local_path
        == (output_root / "care/v6/standard/farm=A/event=7/data.parquet").resolve()
    )
    assert artifact.peak_record_batch_bytes < wide_csv.stat().st_size
    assert artifact.row_group_count == 3
    assert artifact.content_sha256 in artifact.artifact_uri

    manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_sha256"] == source_sha
    assert manifest["object_key"].endswith(f"data.sha256-{artifact.content_sha256}.parquet")
    assert manifest["compression"] == PARQUET_COMPRESSION
    assert manifest["compression_level"] == PARQUET_COMPRESSION_LEVEL
    assert manifest["row_group_size"] == PARQUET_ROW_GROUP_SIZE

    parquet = __import__("pyarrow.parquet", fromlist=["ParquetFile"])
    parquet_file = parquet.ParquetFile(artifact.local_path)
    assert parquet_file.metadata.num_columns == 53
    for index in range(parquet_file.num_row_groups):
        expected_rows = (
            PARQUET_ROW_GROUP_SIZE
            if index < parquet_file.num_row_groups - 1
            else artifact.row_count - PARQUET_ROW_GROUP_SIZE * (artifact.row_group_count - 1)
        )
        assert parquet_file.metadata.row_group(index).num_rows == expected_rows
        for column in range(parquet_file.metadata.row_group(index).num_columns):
            assert parquet_file.metadata.row_group(index).column(column).compression == "ZSTD"
    metadata = parquet_file.schema_arrow.metadata or {}
    assert metadata[b"care.dataset_version"] == b"v6"
    assert metadata[b"care.schema_sha256"] == artifact.schema_sha256.encode()
    assert metadata[b"care.license_url"] == (b"https://creativecommons.org/licenses/by-sa/4.0/")
    assert metadata[b"care.doi"] == b"10.5281/zenodo.15846963"
    assert metadata[b"care.content_sha256_location"] == (
        b"immutable sidecar manifest and object key"
    )
    embedded_license = json.loads(metadata[b"care.artifact_license_json"].decode("utf-8"))
    assert embedded_license == manifest["license"]
    assert embedded_license["code_license_is_separate"] is True

    projection = verify_parquet_column_projection(artifact.local_path, ["id", "sensor_0_Avg"])
    assert projection.row_count == artifact.row_count
    assert projection.selected_columns == ("id", "sensor_0_Avg")
    assert projection.total_column_count == 53
    assert projection.peak_selected_batch_bytes < artifact.peak_record_batch_bytes
    with pytest.raises(CarePipelineError, match="unknown columns"):
        verify_parquet_column_projection(artifact.local_path, ["ground_truth"])

    retry = convert_care_csv_to_parquet(
        wide_csv,
        output_root,
        job_id="fixture-import-1",
        farm="A",
        event_id=7,
        artifact_store=LocalImmutableArtifactStore(store_root),
        expected_source_sha256=source_sha,
    )
    assert retry == artifact
    assert len(list(store_root.rglob("*.parquet"))) == 1

    changed_source = tmp_path / "changed.csv"
    shutil.copyfile(wide_csv, changed_source)
    with changed_source.open("a", encoding="utf-8") as stream:
        stream.write("changed-source\n")
    with pytest.raises(CarePipelineError, match="belongs to another source"):
        convert_care_csv_to_parquet(
            changed_source,
            output_root,
            job_id="fixture-import-2",
            farm="A",
            event_id=7,
        )


def test_csv_fragments_coalesce_to_fixed_parquet_row_groups(wide_csv: Path, tmp_path: Path) -> None:
    artifact = convert_care_csv_to_parquet(
        wide_csv,
        tmp_path / "fragmented-output",
        job_id="fragmented-import",
        farm="C",
        event_id=10,
        csv_block_size_bytes=64 * 1024,
    )
    manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
    assert manifest["csv_block_size_bytes"] == 64 * 1024
    assert artifact.row_group_count == 3

    parquet = __import__("pyarrow.parquet", fromlist=["ParquetFile"])
    parquet_file = parquet.ParquetFile(artifact.local_path)
    assert [
        parquet_file.metadata.row_group(index).num_rows
        for index in range(parquet_file.num_row_groups)
    ] == [8192, 8192, 1616]


def test_parquet_projection_freezes_model_inputs_and_license(
    wide_csv: Path, tmp_path: Path
) -> None:
    selected = (
        "time_stamp",
        "asset_id",
        "id",
        "train_test",
        "status_type_id",
        "sensor_0_Avg",
        "sensor_1_Avg",
    )
    model_inputs = ("sensor_0_Avg", "sensor_1_Avg")
    artifact = convert_care_csv_to_parquet(
        wide_csv,
        tmp_path / "projected-output",
        job_id="projected-import",
        farm="A",
        event_id=12,
        selected_columns=selected,
        model_input_columns=model_inputs,
    )
    manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
    assert manifest["columns"] == list(selected)
    assert manifest["model_input_columns"] == list(model_inputs)
    assert manifest["metadata_columns"] == list(selected[:5])
    assert manifest["source_dataset_sha256"] == _sha256(wide_csv)
    assert manifest["license"]["creators"] == [
        "Christian G" + chr(0xFC) + "ck",
        "Cyriana M. A. Roelofs",
    ]
    assert manifest["license"]["creator_affiliation"].startswith("Fraunhofer Institute")
    assert manifest["license"]["artifact_license"] == "CC BY-SA 4.0"
    assert manifest["license"]["share_alike_required"] is True
    assert manifest["license"]["external_distribution_review"] == "required"
    assert "projected" in manifest["license"]["changes_made"]
    assert manifest["license"]["transformation_versions"] == {
        "column_mapping": "care-v6-column-map-v1",
        "feature_set": "care-v6-avg-feature-set-v1",
        "pipeline": "care-v6-benchmark-pipeline-v2",
        "quality_rules": "care-v6-quality-rules-v1",
    }
    projection = verify_parquet_column_projection(artifact.local_path, model_inputs)
    assert projection.total_column_count == len(selected)

    retry = convert_care_csv_to_parquet(
        wide_csv,
        tmp_path / "projected-output",
        job_id="projected-import",
        farm="A",
        event_id=12,
        selected_columns=selected,
        model_input_columns=model_inputs,
    )
    assert retry == artifact
    with pytest.raises(CarePipelineError, match="absent from source"):
        convert_care_csv_to_parquet(
            wide_csv,
            tmp_path / "invalid-projection",
            job_id="invalid-projection",
            farm="A",
            event_id=12,
            selected_columns=(*selected, "event_label"),
            model_input_columns=model_inputs,
        )
    with pytest.raises(CarePipelineError, match="preserve immutable source order"):
        convert_care_csv_to_parquet(
            wide_csv,
            tmp_path / "invalid-order",
            job_id="invalid-order",
            farm="A",
            event_id=12,
            selected_columns=(*selected[:5], "sensor_1_Avg", "sensor_0_Avg"),
            model_input_columns=model_inputs,
        )


def test_bounded_probe_and_probe_artifact(wide_csv: Path, tmp_path: Path) -> None:
    scan = probe_care_csv_bounded(wide_csv)
    assert scan.row_count == 18_000
    assert scan.batch_count > 4
    assert scan.column_count == 53
    assert scan.peak_record_batch_bytes < scan.source_size_bytes // 2
    output = tmp_path / "probe.json"
    payload = write_bounded_probe(wide_csv, output, maximum_batches=2)
    assert payload["result"]["batch_count"] == 2
    assert payload["source_sha256"] == _sha256(wide_csv)
    assert payload["probe_sha256"] == _canonical_hash(
        {key: value for key, value in payload.items() if key != "probe_sha256"}
    )


def test_checkpoint_resume_and_semantic_tamper_rejection(wide_csv: Path, tmp_path: Path) -> None:
    output_root = tmp_path / "resume-output"
    with pytest.raises(BenchmarkJobCancelled, match="durable chunk"):
        convert_care_csv_to_parquet(
            wide_csv,
            output_root,
            job_id="resume-job",
            farm="B",
            event_id=8,
            stop_after_chunks=1,
        )
    checkpoint_path = output_root / ".work/resume-job/checkpoint.json"
    checkpoint = ParquetCheckpoint.from_path(checkpoint_path)
    assert checkpoint.processed_rows > 0
    assert len(checkpoint.chunks) == 1
    assert not (output_root / "care/v6/standard/farm=B/event=8/data.parquet").exists()

    artifact = convert_care_csv_to_parquet(
        wide_csv,
        output_root,
        job_id="resume-job",
        farm="B",
        event_id=8,
    )
    assert artifact.row_count == 18_000
    assert not checkpoint_path.exists()

    tamper_root = tmp_path / "tamper-output"
    with pytest.raises(BenchmarkJobCancelled):
        convert_care_csv_to_parquet(
            wide_csv,
            tamper_root,
            job_id="tamper-job",
            farm="B",
            event_id=9,
            stop_after_chunks=1,
        )
    tamper_path = tamper_root / ".work/tamper-job/checkpoint.json"
    raw = json.loads(tamper_path.read_text())
    raw["chunks"][0]["relative_path"] = "../escaped.parquet"
    unsigned = {key: value for key, value in raw.items() if key != "checkpoint_sha256"}
    raw["checkpoint_sha256"] = _canonical_hash(unsigned)
    tamper_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CarePipelineError, match="chunk semantics"):
        ParquetCheckpoint.from_path(tamper_path)
    with pytest.raises(CarePipelineError, match="portable identifier"):
        convert_care_csv_to_parquet(
            wide_csv,
            tmp_path / "escape-output",
            job_id="../escape",
            farm="A",
            event_id=1,
        )


def test_job_heartbeat_cancel_retry_and_terminal_failure(tmp_path: Path) -> None:
    state_path = tmp_path / "job.json"
    control = FileBenchmarkJobControl(
        state_path,
        BenchmarkJobState.pending("retry-job", "import", max_attempts=3),
    )
    attempts = 0
    expected = ParquetArtifact(
        tmp_path / "data.parquet",
        tmp_path / "manifest.json",
        "file:///immutable/data.parquet",
        "a" * 64,
        "b" * 64,
        3,
        1,
        "c" * 64,
        "d" * 64,
        100,
        200,
        0.25,
    )

    def operation() -> ParquetArtifact:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RetryableBenchmarkError("temporary store outage")
        return expected

    assert run_with_bounded_retries(control, operation) == expected
    completed = control.read()
    assert completed.status == "completed"
    assert completed.attempt == 3
    assert completed.artifact_uri == expected.artifact_uri
    assert completed.heartbeat_at is not None
    completed_revision = completed.revision
    control.complete(expected.artifact_uri, {})
    assert control.read().revision == completed_revision
    with pytest.raises(CarePipelineError, match="artifact is immutable"):
        control.complete("file:///different.parquet", {})
    with pytest.raises(CarePipelineError, match="cannot be executed again"):
        control.start_attempt()

    cancel_control = FileBenchmarkJobControl(
        tmp_path / "cancel.json", BenchmarkJobState.pending("cancel-job", "quality")
    )
    cancel_control.request_cancel()
    with pytest.raises(BenchmarkJobCancelled, match="before execution"):
        run_with_bounded_retries(cancel_control, lambda: expected)
    assert cancel_control.read().status == "cancelled"

    fail_control = FileBenchmarkJobControl(
        tmp_path / "fail.json", BenchmarkJobState.pending("fail-job", "train")
    )
    with pytest.raises(CarePipelineError, match="invalid model input"):
        run_with_bounded_retries(
            fail_control,
            lambda: (_ for _ in ()).throw(CarePipelineError("invalid model input")),
        )
    assert fail_control.read().status == "failed"
    assert fail_control.read().attempt == 1
    assert fail_control.read().error == "invalid model input"

    raw = json.loads(state_path.read_text())
    raw["cancel_requested"] = "false"
    unsigned = {key: value for key, value in raw.items() if key != "state_sha256"}
    raw["state_sha256"] = _canonical_hash(unsigned)
    state_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CarePipelineError, match="must be boolean"):
        control.read()


def test_unavailable_store_exhausts_retries_without_final_or_partial(
    wide_csv: Path, tmp_path: Path
) -> None:
    class UnavailableStore:
        def __init__(self) -> None:
            self.calls = 0

        def put_immutable(
            self,
            object_key: str,
            source: Path,
            sha256: str,
            *,
            content_type: str = "application/octet-stream",
        ) -> str:
            del object_key, source, sha256, content_type
            self.calls += 1
            raise RetryableBenchmarkError("object storage unavailable")

    output_root = tmp_path / "unavailable-output"
    store = UnavailableStore()
    control = FileBenchmarkJobControl(
        tmp_path / "unavailable-job.json",
        BenchmarkJobState.pending("unavailable-job", "import", max_attempts=3),
    )

    def operation() -> ParquetArtifact:
        return convert_care_csv_to_parquet(
            wide_csv,
            output_root,
            job_id="unavailable-job",
            farm="C",
            event_id=10,
            artifact_store=store,
            job_control=control,
        )

    with pytest.raises(RetryableBenchmarkError, match="unavailable"):
        run_with_bounded_retries(control, operation)
    assert store.calls == 3
    failed = control.read()
    assert failed.status == "failed"
    assert failed.attempt == 3
    destination = output_root / "care/v6/standard/farm=C/event=10"
    assert not (destination / "data.parquet").exists()
    assert not (destination / "manifest.json").exists()
    assert not list(output_root.rglob("*.partial"))
    assert (output_root / ".work/unavailable-job/checkpoint.json").is_file()


def test_local_and_minio_immutable_store_failure_boundaries(tmp_path: Path) -> None:
    first = tmp_path / "first.parquet"
    second = tmp_path / "second.parquet"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    local = LocalImmutableArtifactStore(tmp_path / "store")
    key = "care/v6/standard/data.parquet"
    first_uri = local.put_immutable(key, first, _sha256(first))
    assert local.put_immutable(key, first, _sha256(first)) == first_uri
    with pytest.raises(CarePipelineError, match="different content"):
        local.put_immutable(key, second, _sha256(second))

    class AccessDenied(Exception):
        code = "AccessDenied"

    class DeniedMinio:
        def stat_object(self, bucket: str, object_key: str) -> Any:
            del bucket, object_key
            raise AccessDenied("denied")

    minio = MinioImmutableArtifactStore(DeniedMinio(), "windops-care-benchmarks")
    with pytest.raises(CarePipelineError, match="must contain"):
        minio.put_immutable(key, first, _sha256(first))
    addressed_key = f"care/v6/standard/data.sha256-{_sha256(first)}.parquet"
    with pytest.raises(RetryableBenchmarkError, match="unavailable"):
        minio.put_immutable(addressed_key, first, _sha256(first))

    class MissingObject(Exception):
        code = "NoSuchKey"

    class PublishingMinio:
        def __init__(self) -> None:
            self.published = False
            self.removed: list[str] = []

        def stat_object(self, bucket: str, object_key: str) -> Any:
            del bucket, object_key
            if not self.published:
                raise MissingObject("missing")
            return type(
                "StoredObject",
                (),
                {
                    "size": first.stat().st_size,
                    "metadata": {"x-amz-meta-sha256": _sha256(first)},
                },
            )()

        def fput_object(self, bucket: str, object_key: str, path: str, **kwargs: Any) -> None:
            del bucket, path
            assert object_key.startswith("care/v6/_tmp/")
            assert kwargs["metadata"] == {"sha256": _sha256(first)}

        def copy_object(self, bucket: str, object_key: str, source: Any, **kwargs: Any) -> None:
            del bucket, source
            assert object_key == addressed_key
            assert kwargs["metadata_directive"] == "REPLACE"
            self.published = True

        def remove_object(self, bucket: str, object_key: str) -> None:
            del bucket
            self.removed.append(object_key)

    publishing_client = PublishingMinio()
    publishing_store = MinioImmutableArtifactStore(publishing_client, "windops-care-benchmarks")
    assert publishing_store.put_immutable(addressed_key, first, _sha256(first)) == (
        f"minio://windops-care-benchmarks/{addressed_key}"
    )
    assert len(publishing_client.removed) == 1
    assert publishing_client.removed[0].startswith("care/v6/_tmp/")
    assert publishing_store.put_immutable(addressed_key, first, _sha256(first)).startswith(
        "minio://"
    )

    class LifecycleDeferredCleanupMinio(PublishingMinio):
        def remove_object(self, bucket: str, object_key: str) -> None:
            super().remove_object(bucket, object_key)
            raise AccessDenied("normal CARE worker cannot delete temporary objects")

    lifecycle_client = LifecycleDeferredCleanupMinio()
    lifecycle_store = MinioImmutableArtifactStore(lifecycle_client, "windops-care-benchmarks")
    assert lifecycle_store.put_immutable(addressed_key, first, _sha256(first)) == (
        f"minio://windops-care-benchmarks/{addressed_key}"
    )
    assert len(lifecycle_client.removed) == 1

    class BrokenCleanupMinio(PublishingMinio):
        def remove_object(self, bucket: str, object_key: str) -> None:
            super().remove_object(bucket, object_key)
            raise OSError("cleanup transport failed")

    with pytest.raises(RetryableBenchmarkError, match="temporary object cleanup failed"):
        MinioImmutableArtifactStore(BrokenCleanupMinio(), "windops-care-benchmarks").put_immutable(
            addressed_key, first, _sha256(first)
        )


def test_existing_manifest_semantics_fail_closed(wide_csv: Path, tmp_path: Path) -> None:
    output_root = tmp_path / "manifest-output"
    artifact = convert_care_csv_to_parquet(
        wide_csv,
        output_root,
        job_id="manifest-job",
        farm="A",
        event_id=11,
    )
    raw = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
    original = dict(raw)
    raw["row_count"] += 1
    unsigned = {key: value for key, value in raw.items() if key != "manifest_sha256"}
    raw["manifest_sha256"] = _canonical_hash(unsigned)
    artifact.manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CarePipelineError, match="physical metadata"):
        convert_care_csv_to_parquet(
            wide_csv,
            output_root,
            job_id="manifest-job",
            farm="A",
            event_id=11,
        )

    raw = original
    raw["compression"] = "snappy"
    unsigned = {key: value for key, value in raw.items() if key != "manifest_sha256"}
    raw["manifest_sha256"] = _canonical_hash(unsigned)
    artifact.manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CarePipelineError, match="semantics"):
        convert_care_csv_to_parquet(
            wide_csv,
            output_root,
            job_id="manifest-job",
            farm="A",
            event_id=11,
        )
