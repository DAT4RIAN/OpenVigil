from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from care_trust import make_test_trust_anchor
from windops_backend.benchmarks.care.importer import (
    MINIMAL_IMPORT_SCHEMA_VERSION,
    TRUTH_ACCESS_SCOPE,
    CareMinimalImportError,
    build_a_minimal_import,
    register_a_minimal_import,
    verify_minimal_import_manifest,
)
from windops_backend.benchmarks.care.pipeline import (
    BenchmarkJobCancelled,
    LocalImmutableArtifactStore,
    RetryableBenchmarkError,
)
from windops_backend.benchmarks.care.quality import build_quality_contract
from windops_backend.benchmarks.care.trust import CareTrustAnchor
from windops_backend.models import (
    BenchmarkDatasetVersion,
    BenchmarkEvent,
    BenchmarkFeatureMap,
    BenchmarkFile,
    BenchmarkQualityReport,
)


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(column: str, base: str, statistic: str) -> dict[str, Any]:
    return {
        "source_column": column,
        "base_sensor": base,
        "statistic": statistic,
        "description": f"Fixture {base} {statistic}",
        "source_unit": "deg" if base == "sensor_1" else "1",
        "is_angle": base == "sensor_1",
        "is_counter": False,
        "mapping_source": "feature-metadata-and-statistic-suffix",
    }


def _write_event(path: Path, mappings: list[dict[str, Any]], row_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "time_stamp",
        "asset_id",
        "id",
        "train_test",
        "status_type_id",
        *[str(mapping["source_column"]) for mapping in mappings],
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter=";", lineterminator="\n")
        writer.writerow(header)
        for row_id in range(row_count):
            writer.writerow(
                [
                    f"2024-01-{1 + row_id // 144:02d} 00:{(row_id % 6) * 10:02d}:00",
                    "0",
                    row_id,
                    "train" if row_id < row_count - 400 else "prediction",
                    "0",
                    *(
                        f"{row_id * 0.01 + column_index:.5f}"
                        for column_index in range(len(mappings))
                    ),
                ]
            )


def _fixture(
    tmp_path: Path,
    *,
    row_count: int = 4_200,
) -> tuple[Path, Path, dict, dict, CareTrustAnchor]:
    root = tmp_path / "CARE_To_Compare"
    archive = tmp_path / "CARE_To_Compare.zip"
    archive.write_bytes(b"immutable-care-v6-minimal-import-fixture")
    mappings = [
        *[_mapping(f"sensor_{index}_avg", f"sensor_{index}", "average") for index in range(54)],
        *[
            _mapping(f"sensor_{index}_{suffix}", f"sensor_{index}", statistic)
            for index in range(9)
            for suffix, statistic in (
                ("max", "maximum"),
                ("min", "minimum"),
                ("std", "std_dev"),
            )
        ],
    ]
    assert len(mappings) == 81
    events: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for event_id, label in ((0, "anomaly"), (24, "normal")):
        relative_path = f"Wind Farm A/datasets/{event_id}.csv"
        path = root / relative_path
        _write_event(path, mappings, row_count)
        source_sha = _sha256(path)
        schema_sha = _canonical_hash([mapping["source_column"] for mapping in mappings])
        events.append(
            {
                "event_description": "fixture fault" if label == "anomaly" else "",
                "event_end": "2024-01-30 00:00:00",
                "event_end_id": row_count - 1,
                "event_id": event_id,
                "event_label": label,
                "event_start": "2024-01-27 00:00:00",
                "event_start_id": row_count - 400,
                "farm": "A",
                "file_sha256": source_sha,
                "relative_path": relative_path,
                "row_count": row_count,
                "schema_sha256": schema_sha,
                "source_asset_id": "0",
                "source_row_id_max": row_count - 1,
                "source_row_id_min": 0,
                "split_counts": {"prediction": 400, "train": row_count - 400},
            }
        )
        files.append(
            {
                "event_id": event_id,
                "farm": "A",
                "kind": "event-data",
                "relative_path": relative_path,
                "row_count": row_count,
                "schema_sha256": schema_sha,
                "sha256": source_sha,
                "size_bytes": path.stat().st_size,
            }
        )
    archive_bytes = archive.read_bytes()
    unsigned = {
        "manifest_schema_version": "care-v6-manifest-v1",
        "dataset_id": "care",
        "dataset_version": "v6",
        "source": {
            "doi": "10.5281/zenodo.15846963",
            "read_only": True,
            "zenodo_url": "https://zenodo.org/records/15846963",
            "zip": {
                "filename": archive.name,
                "md5": hashlib.md5(archive_bytes, usedforsecurity=False).hexdigest(),
                "sha256": hashlib.sha256(archive_bytes).hexdigest(),
                "size_bytes": len(archive_bytes),
            },
        },
        "license": {
            "artifact_license": "CC BY-SA 4.0",
            "changes_made": "fixture source is unchanged",
            "name": "CC BY-SA 4.0",
            "url": "https://creativecommons.org/licenses/by-sa/4.0/",
        },
        "summary": {
            "csv_file_count": 2,
            "event_count": 2,
            "anomaly_event_count": 1,
            "normal_event_count": 1,
            "time_point_count": row_count * 2,
        },
        "mapping_contract": {
            "metadata_columns": [
                "time_stamp",
                "asset_id",
                "id",
                "train_test",
                "status_type_id",
            ]
        },
        "farms": [
            {
                "farm": "A",
                "column_mapping_version": "care-v6-column-map-v1",
                "column_mapping_sha256": _canonical_hash(mappings),
                "column_mappings": mappings,
                "event_count": 2,
                "event_ids": [0, 24],
                "feature_count": 54,
                "signal_column_count": 81,
                "signal_schema_sha256": events[0]["schema_sha256"],
            }
        ],
        "events": events,
        "csv_files": files,
    }
    manifest = {**unsigned, "manifest_sha256": _canonical_hash(unsigned)}
    quality = build_quality_contract(manifest)
    return root, archive, manifest, quality, make_test_trust_anchor(manifest, quality)


def _build(tmp_path: Path):
    root, archive, manifest, quality, trust_anchor = _fixture(tmp_path)
    output = tmp_path / "derived"
    store = tmp_path / "object-store"
    result = build_a_minimal_import(
        manifest,
        quality,
        root,
        output,
        source_archive_path=archive,
        artifact_store=LocalImmutableArtifactStore(store),
        trust_anchor=trust_anchor,
    )
    return root, archive, manifest, quality, output, store, result, trust_anchor


def test_a_minimal_import_is_wide_licensed_truth_isolated_and_deterministic(
    tmp_path: Path,
) -> None:
    root, archive, manifest, quality, output, store, first, trust_anchor = _build(tmp_path)
    verify_minimal_import_manifest(first.manifest)
    assert first.replayed is False
    assert first.manifest["schema_version"] == MINIMAL_IMPORT_SCHEMA_VERSION
    assert first.manifest["summary"]["row_count"] == 8_400
    assert first.manifest["summary"]["train_row_count"] == 7_600
    assert first.manifest["summary"]["prediction_row_count"] == 800
    assert first.manifest["mapping_count"] == 81
    assert first.manifest["model_input_count"] == 54
    assert not set(first.manifest["model_input_columns"]).intersection(
        first.manifest["truth_fields_forbidden_from_model_input"]
    )
    assert not any(
        truth_field in event
        for event in first.manifest["events"]
        for truth_field in first.manifest["truth_fields_forbidden_from_model_input"]
    )

    parquet = __import__("pyarrow.parquet", fromlist=["ParquetFile"])
    for event in first.manifest["events"]:
        parquet_path = output / Path(event["parquet"]["data"]["local_relative_path"])
        parquet_file = parquet.ParquetFile(parquet_path)
        try:
            assert parquet_file.metadata.num_rows == 4_200
            assert parquet_file.metadata.num_columns == 59
            assert parquet_file.schema_arrow.names[:5] == [
                "time_stamp",
                "asset_id",
                "id",
                "train_test",
                "status_type_id",
            ]
            assert not set(parquet_file.schema_arrow.names).intersection(
                first.manifest["truth_fields_forbidden_from_model_input"]
            )
        finally:
            parquet_file.close()
        report = json.loads(
            (output / Path(event["quality"]["report"]["local_relative_path"])).read_text(
                encoding="utf-8"
            )
        )
        mask = json.loads(
            (output / Path(event["quality"]["mask"]["local_relative_path"])).read_text(
                encoding="utf-8"
            )
        )
        truth = json.loads(
            (output / Path(event["restricted_truth"]["artifact"]["local_relative_path"])).read_text(
                encoding="utf-8"
            )
        )
        assert "quality_mask_ranges" not in report
        assert len(report["feature_summaries"]) == 81
        assert mask["raw_values_modified"] is False
        assert truth["access_scope"] == TRUTH_ACCESS_SCOPE
        assert truth["model_input_allowed"] is False
        assert truth["event_label"] in {"anomaly", "normal"}
        for document in (report, mask, truth):
            assert document["license"]["artifact_license"] == "CC BY-SA 4.0"
            assert document["license"]["share_alike_required"] is True

    mapping = json.loads(
        (output / Path(first.manifest["mapping_artifact"]["local_relative_path"])).read_text(
            encoding="utf-8"
        )
    )
    assert mapping["mapping_count"] == 81
    assert mapping["approved_model_input_count"] == 54
    source_hashes = {
        event_id: _sha256(root / f"Wind Farm A/datasets/{event_id}.csv") for event_id in (0, 24)
    }
    object_count = len([path for path in store.rglob("*") if path.is_file()])

    second = build_a_minimal_import(
        manifest,
        quality,
        root,
        output,
        source_archive_path=archive,
        artifact_store=LocalImmutableArtifactStore(store),
        trust_anchor=trust_anchor,
    )
    assert second.replayed is True
    assert second.manifest == first.manifest
    assert second.manifest_file_sha256 == first.manifest_file_sha256
    assert len([path for path in store.rglob("*") if path.is_file()]) == object_count
    assert source_hashes == {
        event_id: _sha256(root / f"Wind Farm A/datasets/{event_id}.csv") for event_id in (0, 24)
    }


@pytest.mark.asyncio
async def test_a_minimal_import_registration_is_atomic_and_idempotent(
    app: FastAPI,
    tmp_path: Path,
) -> None:
    _, _, manifest, quality, _, _, bundle, trust_anchor = _build(tmp_path)
    async with app.state.session_factory() as session, session.begin():
        first = await register_a_minimal_import(
            session,
            bundle.manifest,
            manifest,
            quality,
            tenant_id="tenant-east-china",
            subject="care-worker",
            trust_anchor=trust_anchor,
        )
        assert first.created_count == 88
        assert first.replayed_count == 0
    async with app.state.session_factory() as session, session.begin():
        second = await register_a_minimal_import(
            session,
            bundle.manifest,
            manifest,
            quality,
            tenant_id="tenant-east-china",
            subject="care-worker",
            trust_anchor=trust_anchor,
        )
        assert second.created_count == 0
        assert second.replayed_count == 88
        assert second.event_ids == ("care-v6-event-a-0", "care-v6-event-a-24")
    async with app.state.session_factory() as session:
        assert int(await session.scalar(select(func.count(BenchmarkDatasetVersion.id))) or 0) == 1
        assert int(await session.scalar(select(func.count(BenchmarkFile.id))) or 0) == 2
        assert int(await session.scalar(select(func.count(BenchmarkEvent.id))) or 0) == 2
        assert int(await session.scalar(select(func.count(BenchmarkFeatureMap.id))) or 0) == 81
        assert int(await session.scalar(select(func.count(BenchmarkQualityReport.id))) or 0) == 2
        truth = (
            (await session.execute(select(BenchmarkEvent).order_by(BenchmarkEvent.event_id)))
            .scalars()
            .all()
        )
        assert {row.event_label for row in truth} == {"anomaly", "normal"}
        assert all(row.truth_metadata["access_scope"] == TRUTH_ACCESS_SCOPE for row in truth)
        assert all("event_description" not in row.truth_metadata for row in truth)


def test_cancelled_minimal_import_resumes_from_durable_chunk_without_final_manifest(
    tmp_path: Path,
) -> None:
    root, archive, manifest, quality, trust_anchor = _fixture(tmp_path)
    output = tmp_path / "cancel-output"
    with pytest.raises(BenchmarkJobCancelled, match="durable chunk"):
        build_a_minimal_import(
            manifest,
            quality,
            root,
            output,
            source_archive_path=archive,
            stop_after_chunks_by_event={0: 1},
            trust_anchor=trust_anchor,
        )
    checkpoint = output / ".work/care-v6-a-event-0-import/checkpoint.json"
    final_manifest = output / "care/v6/reports/a-minimal-import/manifest.json"
    assert checkpoint.is_file()
    assert not final_manifest.exists()
    assert not list(output.rglob("*.partial"))

    resumed = build_a_minimal_import(
        manifest,
        quality,
        root,
        output,
        source_archive_path=archive,
        trust_anchor=trust_anchor,
    )
    assert resumed.manifest["summary"]["event_count"] == 2
    assert not checkpoint.exists()
    assert not list(output.rglob("*.partial"))


def test_object_store_failure_does_not_publish_bundle_or_leave_partial_files(
    tmp_path: Path,
) -> None:
    class UnavailableStore:
        def put_immutable(
            self,
            object_key: str,
            source: Path,
            sha256: str,
            *,
            content_type: str = "application/octet-stream",
        ) -> str:
            del object_key, source, sha256, content_type
            raise RetryableBenchmarkError("fixture object store unavailable")

    root, archive, manifest, quality, trust_anchor = _fixture(tmp_path, row_count=24)
    output = tmp_path / "failure-output"
    with pytest.raises(RetryableBenchmarkError, match="unavailable"):
        build_a_minimal_import(
            manifest,
            quality,
            root,
            output,
            source_archive_path=archive,
            artifact_store=UnavailableStore(),
            trust_anchor=trust_anchor,
        )
    assert not (output / "care/v6/reports/a-minimal-import/manifest.json").exists()
    assert not list(output.rglob("*.partial"))


def test_minimal_import_rejects_resigned_truth_policy_mapping_and_source_tampering(
    tmp_path: Path,
) -> None:
    root, archive, manifest, _, trust_anchor = _fixture(tmp_path, row_count=24)
    wrong_truth = copy.deepcopy(manifest)
    wrong_truth["events"][1]["event_label"] = "anomaly"
    unsigned = {key: item for key, item in wrong_truth.items() if key != "manifest_sha256"}
    wrong_truth["manifest_sha256"] = _canonical_hash(unsigned)
    with pytest.raises(CareMinimalImportError, match="signed approved root"):
        build_a_minimal_import(
            wrong_truth,
            build_quality_contract(wrong_truth),
            root,
            tmp_path / "wrong-truth",
            source_archive_path=archive,
            trust_anchor=trust_anchor,
        )

    bad_mapping = copy.deepcopy(manifest)
    bad_mapping["farms"][0]["column_mappings"].pop()
    unsigned = {key: item for key, item in bad_mapping.items() if key != "manifest_sha256"}
    bad_mapping["manifest_sha256"] = _canonical_hash(unsigned)
    with pytest.raises(CareMinimalImportError, match="signed approved root"):
        build_a_minimal_import(
            bad_mapping,
            build_quality_contract(bad_mapping),
            root,
            tmp_path / "bad-mapping",
            source_archive_path=archive,
            trust_anchor=trust_anchor,
        )

    wrong_policy = build_quality_contract(manifest)
    wrong_policy["zero_value_policy"]["global_zero_to_null"] = True
    unsigned_quality = {
        key: item for key, item in wrong_policy.items() if key != "quality_contract_sha256"
    }
    wrong_policy["quality_contract_sha256"] = _canonical_hash(unsigned_quality)
    with pytest.raises(CareMinimalImportError, match="signed approved root"):
        build_a_minimal_import(
            manifest,
            wrong_policy,
            root,
            tmp_path / "wrong-policy",
            source_archive_path=archive,
            trust_anchor=trust_anchor,
        )

    wrong_source = copy.deepcopy(manifest)
    wrong_source["source"]["zip"]["sha256"] = "0" * 64
    unsigned_source = {key: item for key, item in wrong_source.items() if key != "manifest_sha256"}
    wrong_source["manifest_sha256"] = _canonical_hash(unsigned_source)
    with pytest.raises(CareMinimalImportError, match="signed approved root"):
        build_a_minimal_import(
            wrong_source,
            build_quality_contract(wrong_source),
            root,
            tmp_path / "wrong-source",
            source_archive_path=archive,
            trust_anchor=trust_anchor,
        )

    tampered_bundle = {
        "schema_version": MINIMAL_IMPORT_SCHEMA_VERSION,
        "manifest_sha256": "0" * 64,
    }
    with pytest.raises(CareMinimalImportError, match="manifest hash"):
        verify_minimal_import_manifest(tampered_bundle)
