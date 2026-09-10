from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from care_trust import make_test_trust_anchor
from windops_backend.benchmarks.care import fullscale as fullscale_module
from windops_backend.benchmarks.care.contract import (
    CareDatasetExpectations,
    build_care_contract,
)
from windops_backend.benchmarks.care.fullscale import (
    CareFullScaleError,
    FullScaleExpectedCounts,
    FullScaleResourceLimits,
    build_full_scale_evaluation,
    build_full_scale_import,
    build_full_scale_plan,
    register_full_scale_evaluation,
    register_full_scale_import,
    verify_full_scale_evaluation_manifest,
    verify_full_scale_import_manifest,
)
from windops_backend.benchmarks.care.fullscale import (
    main as full_scale_main,
)
from windops_backend.benchmarks.care.pipeline import (
    BenchmarkJobCancelled,
    BenchmarkJobState,
    FileBenchmarkJobControl,
    LocalImmutableArtifactStore,
)
from windops_backend.benchmarks.care.quality import build_quality_contract
from windops_backend.benchmarks.care.resources import (
    peak_process_resident_bytes,
    trim_process_resident_memory,
)
from windops_backend.benchmarks.care.trust import CareTrustAnchor
from windops_backend.models import (
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkEvent,
    BenchmarkEventResult,
    BenchmarkFeatureMap,
    BenchmarkFile,
    BenchmarkMetricSnapshot,
    BenchmarkQualityReport,
    RegisteredModel,
)


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter=";", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _fixture(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any], CareTrustAnchor]:
    root = tmp_path / "CARE_To_Compare"
    archive = tmp_path / "CARE_To_Compare.zip"
    archive.write_bytes(b"care-v6-full-scale-fixture")
    event_farms = ((0, "A"), (1, "A"), (2, "C"), (3, "C"), (4, "B"), (5, "B"))
    by_farm: dict[str, list[list[object]]] = {"A": [], "B": [], "C": []}
    for event_id, farm in event_farms:
        asset = str(event_id + 10)
        label = "anomaly" if event_id % 2 == 0 else "normal"
        by_farm[farm].append(
            [
                asset,
                event_id,
                label,
                "t8",
                8,
                "t10",
                10,
                "fixture fault" if label == "anomaly" else "",
            ]
        )
        offset = float(event_id * 10)
        train_statuses = {
            3: [0, 0, 0, 0, 0, 9, 9, 9],
            5: [9, 9, 9, 9, 9, 9, 0, 0],
        }.get(event_id, [0, 0, 0, 0, 0, 0, 0, 0])
        prediction_statuses = {
            2: [9, 9, 0],
            3: [9, 9, 9],
            4: [9, 9, 9],
            5: [9, 0, 9],
        }.get(event_id, [0, 0, 0])
        rows: list[list[object]] = []
        for row_id, (split, status) in enumerate(
            [
                *(("train", status) for status in train_statuses),
                *(("prediction", status) for status in prediction_statuses),
            ]
        ):
            signal = 0.0 if status == 9 else offset + row_id
            rows.append(
                [
                    f"2024-01-01 {row_id // 6:02d}:{(row_id % 6) * 10:02d}:00",
                    asset,
                    row_id,
                    split,
                    status,
                    signal,
                    signal + 1,
                ]
            )
        _write_csv(
            root / f"Wind Farm {farm}" / "datasets" / f"{event_id}.csv",
            [
                "time_stamp",
                "asset_id",
                "id",
                "train_test",
                "status_type_id",
                "sensor_0_avg",
                "sensor_0_max",
            ],
            rows,
        )
    for farm in ("A", "B", "C"):
        farm_root = root / f"Wind Farm {farm}"
        _write_csv(
            farm_root / "feature_description.csv",
            [
                "sensor_name",
                "statistics_type",
                "description",
                "unit",
                "is_angle",
                "is_counter",
            ],
            [["sensor_0", "average,maximum", "Active power", "kW", "False", "False"]],
        )
        _write_csv(
            farm_root / "event_info.csv",
            [
                "asset" if farm == "A" else "asset_id",
                "event_id",
                "event_label",
                "event_start",
                "event_start_id",
                "event_end",
                "event_end_id",
                "event_description",
            ],
            by_farm[farm],
        )
    archive_bytes = archive.read_bytes()
    expectations = CareDatasetExpectations(
        farms=("A", "B", "C"),
        csv_count=12,
        event_ids=tuple(range(6)),
        signal_counts=(("A", 2), ("B", 2), ("C", 2)),
        zip_size_bytes=len(archive_bytes),
        zip_md5=hashlib.md5(archive_bytes, usedforsecurity=False).hexdigest(),
        zip_sha256=hashlib.sha256(archive_bytes).hexdigest(),
    )
    manifest = build_care_contract(
        root,
        archive,
        expectations=expectations,
        explicit_aliases={},
        tool_git_commit="a" * 40,
        dependency_lock_sha256="b" * 64,
    )
    quality = build_quality_contract(manifest)
    return root, archive, manifest, quality, make_test_trust_anchor(manifest, quality)


EXPECTED = FullScaleExpectedCounts(
    event_count=6,
    farm_event_counts=(("A", 2), ("C", 2), ("B", 2)),
    farm_signal_counts=(("A", 2), ("B", 2), ("C", 2)),
    asset_count=6,
    anomaly_count=3,
    normal_count=3,
    row_count=66,
)

LIMITS = FullScaleResourceLimits(
    max_import_runtime_seconds=600,
    max_evaluation_runtime_seconds=600,
    max_peak_record_batch_bytes=16 * 1024 * 1024,
    max_peak_arrow_allocated_bytes=512 * 1024 * 1024,
    max_peak_process_resident_bytes=1024 * 1024 * 1024,
    max_import_storage_bytes=1024 * 1024 * 1024,
    max_evaluation_storage_bytes=1024 * 1024 * 1024,
    min_import_rows_per_second=0.001,
    max_prediction_points=18,
)


class _UnavailableArtifactStore:
    def put_immutable(
        self,
        object_key: str,
        source: Path,
        sha256: str,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        del object_key, source, sha256, content_type
        raise RuntimeError("injected object store outage")


def test_full_scale_plan_and_import_are_ordered_recoverable_and_fully_licensed(
    tmp_path: Path,
) -> None:
    assert peak_process_resident_bytes() > 0
    assert trim_process_resident_memory() is True
    root, archive, manifest, quality, trust_anchor = _fixture(tmp_path)
    output = tmp_path / "derived"
    store = LocalImmutableArtifactStore(tmp_path / "objects")
    plan = build_full_scale_plan(manifest, quality, expected_counts=EXPECTED)
    assert plan["stage_order"] == ["A", "C", "B"]
    assert [(stage["farm"], stage["event_ids"]) for stage in plan["stages"]] == [
        ("A", [0, 1]),
        ("C", [2, 3]),
        ("B", [4, 5]),
    ]
    assert plan["cross_farm_protocol"]["status"] == "disabled"

    with pytest.raises(BenchmarkJobCancelled):
        build_full_scale_import(
            manifest,
            quality,
            root,
            output,
            source_archive_path=archive,
            artifact_store=store,
            job_id="fixture-full-import-cancelled",
            stop_after_events=1,
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )
    cancelled_state = json.loads(
        (output / ".state" / "fixture-full-import-cancelled.json").read_text(encoding="utf-8")
    )
    assert cancelled_state["status"] == "cancelled"
    assert not (output / "care" / "v6" / "reports" / "full-import" / "manifest.json").exists()

    completed = build_full_scale_import(
        manifest,
        quality,
        root,
        output,
        source_archive_path=archive,
        artifact_store=store,
        job_id="fixture-full-import-resumed",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )
    assert completed.replayed is False
    assert [event["farm"] for event in completed.manifest["events"]] == [
        "A",
        "A",
        "C",
        "C",
        "B",
        "B",
    ]
    assert completed.manifest["summary"] == EXPECTED.to_document()
    assert completed.manifest["storage_boundary"]["full_timescaledb_expanded_row_count"] == 0
    assert completed.manifest["resource_actual"]["limits_passed"] is True
    assert completed.manifest["resource_policy"]["csv_block_size_bytes"] == 1024 * 1024
    first_parquet_manifest = json.loads(
        (
            output / completed.manifest["events"][0]["parquet"]["manifest"]["local_relative_path"]
        ).read_text(encoding="utf-8")
    )
    assert first_parquet_manifest["column_count"] == 7
    assert first_parquet_manifest["model_input_columns"] == ["sensor_0_avg"]
    assert "all mapped signal columns" in first_parquet_manifest["license"]["changes_made"]
    replay = build_full_scale_import(
        manifest,
        quality,
        root,
        output,
        source_archive_path=archive,
        artifact_store=store,
        job_id="ignored-after-completion",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )
    assert replay.replayed is True
    assert replay.manifest_file_sha256 == completed.manifest_file_sha256


def test_full_scale_cli_reports_and_requests_durable_cancellation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = tmp_path / "operator-state.json"
    FileBenchmarkJobControl(
        state_path,
        BenchmarkJobState.pending("operator-cancel", "import"),
    )

    assert full_scale_main(["status", "--state-path", str(state_path)]) == 0
    reported = json.loads(capsys.readouterr().out)
    assert reported["status"] == "pending"
    assert reported["cancel_requested"] is False

    assert full_scale_main(["cancel", "--state-path", str(state_path)]) == 0
    cancelling = json.loads(capsys.readouterr().out)
    assert cancelling["status"] == "pending"
    assert cancelling["cancel_requested"] is True
    assert FileBenchmarkJobControl(state_path).read().cancel_requested is True


def test_full_scale_cli_routes_atomic_database_registration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_register(args: Any) -> dict[str, Any]:
        assert args.artifact_root == tmp_path
        assert args.tenant_id == "tenant-east-china"
        return {
            "import_created_count": 1571,
            "evaluation_created_count": 324,
        }

    monkeypatch.setattr(fullscale_module, "_register_from_settings", fake_register)
    placeholder = tmp_path / "placeholder.json"
    assert (
        full_scale_main(
            [
                "register",
                "--source-manifest",
                str(placeholder),
                "--quality-contract",
                str(placeholder),
                "--import-manifest",
                str(placeholder),
                "--evaluation-manifest",
                str(placeholder),
                "--artifact-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {
        "evaluation_created_count": 324,
        "import_created_count": 1571,
    }


def test_full_scale_cli_can_use_only_the_configured_care_minio_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(minio_care_bucket="windops-care-benchmarks")
    client = object()
    monkeypatch.setattr(fullscale_module, "get_settings", lambda: settings)
    monkeypatch.setattr(fullscale_module, "minio_client", lambda value: client)

    args = fullscale_module._parser().parse_args(
        [
            "import",
            "--manifest",
            "manifest.json",
            "--quality-contract",
            "quality.json",
            "--dataset-root",
            "dataset",
            "--output-root",
            "output",
            "--use-configured-minio",
        ]
    )
    store = fullscale_module._artifact_store_from_args(args)
    assert store is not None
    assert store.client is client
    assert store.bucket == "windops-care-benchmarks"

    with pytest.raises(SystemExit):
        fullscale_module._parser().parse_args(
            [
                "evaluate",
                "--import-manifest",
                "import.json",
                "--output-root",
                "output",
                "--object-store-root",
                "local-store",
                "--use-configured-minio",
            ]
        )


def test_full_scale_evaluation_freezes_predictions_before_truth_and_accounts_every_fold(
    tmp_path: Path,
) -> None:
    root, archive, manifest, quality, trust_anchor = _fixture(tmp_path)
    output = tmp_path / "derived"
    store = LocalImmutableArtifactStore(tmp_path / "objects")
    imported = build_full_scale_import(
        manifest,
        quality,
        root,
        output,
        source_archive_path=archive,
        artifact_store=store,
        job_id="fixture-full-import",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )
    with pytest.raises(BenchmarkJobCancelled):
        build_full_scale_evaluation(
            imported.manifest,
            output,
            artifact_store=store,
            job_id="fixture-full-evaluation-cancelled",
            stop_after_predictions=1,
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )
    completed = build_full_scale_evaluation(
        imported.manifest,
        output,
        artifact_store=store,
        job_id="fixture-full-evaluation-resumed",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )
    assert completed.manifest["farm_namespaced_fold_count"] == 6
    assert completed.manifest["summary"]["prediction_event_count"] == 6
    assert completed.manifest["summary"]["prediction_point_count"] == 18
    assert completed.manifest["summary"]["all_events_accounted_for"] is True
    assert completed.manifest["truth_boundary"] == {
        "prediction_freeze_completed_before_truth_read": True,
        "prediction_truth_available_to_training_or_calibration": False,
    }
    assert completed.manifest["cross_farm_protocol"]["status"] == "disabled"
    assert all(fold["requested_event_count"] == 1 for fold in completed.manifest["fold_summaries"])
    assert completed.manifest["operational_policy"]["permissions"]["raw_cleanup_allowed"] is False
    assert (
        completed.manifest["operational_policy"]["backup_recovery"][
            "care_authoritative_table_invariants_required"
        ]
        is True
    )
    assert (
        completed.manifest["operational_policy"]["backup_recovery"]["temporary_prefix_backed_up"]
        is False
    )
    assert (
        completed.manifest["operational_policy"]["serving_limits"][
            "min_replay_write_rows_per_second"
        ]
        == fullscale_module.MIN_REPLAY_WRITE_ROWS_PER_SECOND
    )
    assert (
        completed.manifest["operational_policy"]["fault_recovery"]["resume_mechanism"]
        == "new-job-id-reuses-verified-event-checkpoints"
    )
    freeze_reference = completed.manifest["prediction_freeze"]
    freeze = json.loads(
        (output / freeze_reference["local_relative_path"]).read_text(encoding="utf-8")
    )
    short_prediction = json.loads(
        (output / freeze["prediction_artifacts"]["2"]["local_relative_path"]).read_text(
            encoding="utf-8"
        )
    )
    sustained_prediction = json.loads(
        (output / freeze["prediction_artifacts"]["3"]["local_relative_path"]).read_text(
            encoding="utf-8"
        )
    )
    assert [point["disagreement_run_length"] for point in short_prediction["points"]] == [
        1,
        2,
        1,
    ]
    assert [point["valid_point_mask"] for point in short_prediction["points"]] == [
        True,
        True,
        True,
    ]
    assert [point["disagreement_run_length"] for point in sustained_prediction["points"]] == [
        1,
        2,
        3,
    ]
    assert [point["corroborated_by_signal"] for point in sustained_prediction["points"]] == [
        True,
        True,
        True,
    ]
    assert [point["valid_point_mask"] for point in sustained_prediction["points"]] == [
        True,
        True,
        False,
    ]

    b_model_reference = completed.manifest["model_packages"]["B"]
    b_model = json.loads(
        (output / b_model_reference["local_relative_path"]).read_text(encoding="utf-8")
    )
    held_out_14 = next(
        profile for profile in b_model["fold_profiles"] if profile["held_out_asset_id"] == "14"
    )
    assert held_out_14["status_usable_train_row_count"] == 4
    assert held_out_14["trusted_train_row_count"] == 2
    assert held_out_14["retained_disagreement_train_row_count"] == 2
    assert held_out_14["masked_status_train_row_count"] == 4
    assert held_out_14["quality_masked_train_row_count"] == 2
    assert held_out_14["quality_masked_train_feature_value_count"] == 2
    assert held_out_14["quality_masked_train_feature_counts"] == [2]
    assert b_model["quality_mask_policy"]["decision"] == "apply"

    assert [point["quality_masked_feature_count"] for point in sustained_prediction["points"]] == [
        1,
        1,
        1,
    ]
    assert sustained_prediction["quality_masked_prediction_feature_value_count"] == 3
    assert sustained_prediction["quality_masked_prediction_point_count"] == 3
    assert sustained_prediction["quality_mask_score_changed_prediction_point_count"] == 3
    assert completed.manifest["quality_mask_impact"]["decision"] == "apply"
    assert completed.manifest["quality_mask_impact"]["quality_masked_train_row_count"] > 0
    assert (
        completed.manifest["quality_mask_impact"][
            "quality_mask_score_changed_prediction_point_count"
        ]
        > 0
    )

    tampered = copy.deepcopy(sustained_prediction)
    tampered["points"][0]["corroboration_finite_signal_count"] = 0
    unsigned_tampered = {
        key: item for key, item in tampered.items() if key != "prediction_artifact_sha256"
    }
    tampered["prediction_artifact_sha256"] = fullscale_module._canonical_hash(unsigned_tampered)
    with pytest.raises(CareFullScaleError, match="differs from raw status and signals"):
        fullscale_module.verify_full_scale_prediction_status_evidence(
            tampered,
            output_root=output,
            event=next(event for event in imported.manifest["events"] if event["event_id"] == 3),
            status_signal_columns=tuple(
                sustained_prediction["status_evidence_policy"]["corroboration_signal_columns"]
            ),
        )

    mask_ignored = copy.deepcopy(sustained_prediction)
    for point in mask_ignored["points"]:
        point["quality_masked_feature_count"] = 0
    mask_ignored["quality_masked_prediction_feature_value_count"] = 0
    mask_ignored["quality_masked_prediction_point_count"] = 0
    mask_ignored_unsigned = {
        key: item for key, item in mask_ignored.items() if key != "prediction_artifact_sha256"
    }
    mask_ignored["prediction_artifact_sha256"] = fullscale_module._canonical_hash(
        mask_ignored_unsigned
    )
    event_3 = next(event for event in imported.manifest["events"] if event["event_id"] == 3)
    c_model = json.loads(
        (output / completed.manifest["model_packages"]["C"]["local_relative_path"]).read_text(
            encoding="utf-8"
        )
    )
    c_profile = next(
        profile for profile in c_model["fold_profiles"] if profile["held_out_asset_id"] == "13"
    )
    with pytest.raises(CareFullScaleError, match="quality mask|raw values"):
        fullscale_module.verify_full_scale_prediction_model_inputs(
            mask_ignored,
            output_root=output,
            event=event_3,
            features=tuple(c_model["feature_columns"]),
            status_signal_columns=tuple(
                sustained_prediction["status_evidence_policy"]["corroboration_signal_columns"]
            ),
            profile=c_profile,
        )
    replay = build_full_scale_evaluation(
        imported.manifest,
        output,
        artifact_store=store,
        job_id="ignored-after-evaluation-completion",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )
    assert replay.replayed is True
    assert replay.manifest_file_sha256 == completed.manifest_file_sha256


@pytest.mark.asyncio
async def test_full_scale_registration_is_complete_idempotent_and_preserves_score_scope(
    app: FastAPI, tmp_path: Path
) -> None:
    root, archive, manifest, quality, trust_anchor = _fixture(tmp_path)
    output = tmp_path / "registered-derived"
    imported = build_full_scale_import(
        manifest,
        quality,
        root,
        output,
        source_archive_path=archive,
        job_id="fixture-registered-import",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )
    evaluated = build_full_scale_evaluation(
        imported.manifest,
        output,
        job_id="fixture-registered-evaluation",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )

    async with app.state.session_factory() as session, session.begin():
        imported_first = await register_full_scale_import(
            session,
            imported.manifest,
            manifest,
            quality,
            artifact_root=output,
            tenant_id="tenant-east-china",
            subject="care-worker",
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )
        evaluated_first = await register_full_scale_evaluation(
            session,
            evaluated.manifest,
            imported.manifest,
            artifact_root=output,
            subject="care-worker",
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )
    assert imported_first.created_count == 25
    assert imported_first.replayed_count == 0
    assert evaluated_first.created_count == 45
    assert evaluated_first.replayed_count == 0

    async with app.state.session_factory() as session, session.begin():
        imported_replay = await register_full_scale_import(
            session,
            imported.manifest,
            manifest,
            quality,
            artifact_root=output,
            tenant_id="tenant-east-china",
            subject="care-worker",
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )
        evaluated_replay = await register_full_scale_evaluation(
            session,
            evaluated.manifest,
            imported.manifest,
            artifact_root=output,
            subject="care-worker",
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )
    assert imported_replay.created_count == 0
    assert imported_replay.replayed_count == 25
    assert evaluated_replay.created_count == 0
    assert evaluated_replay.replayed_count == 45

    async with app.state.session_factory() as session:
        expected_table_counts = {
            BenchmarkDatasetVersion: 1,
            BenchmarkFile: 6,
            BenchmarkEvent: 6,
            BenchmarkFeatureMap: 6,
            BenchmarkQualityReport: 6,
            RegisteredModel: 3,
            BenchmarkEvaluationRun: 6,
            BenchmarkEventResult: 6,
            BenchmarkMetricSnapshot: 30,
        }
        for model, count in expected_table_counts.items():
            assert int(await session.scalar(select(func.count()).select_from(model)) or 0) == count
        dataset = await session.get(BenchmarkDatasetVersion, "care-v6")
        assert dataset is not None
        assert dataset.manifest_sha256 == manifest["manifest_sha256"]
        results = (await session.scalars(select(BenchmarkEventResult))).all()
        assert all(result.status == "scored" and result.scorable for result in results)
        assert all(result.care_score is None for result in results)


def test_full_scale_verifiers_reject_corruption_partial_coverage_and_cross_farm_claims(
    tmp_path: Path,
) -> None:
    def rehash(document: dict[str, Any]) -> None:
        unsigned = {key: value for key, value in document.items() if key != "manifest_sha256"}
        document["manifest_sha256"] = hashlib.sha256(
            json.dumps(
                unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    root, archive, manifest, quality, trust_anchor = _fixture(tmp_path)
    output = tmp_path / "derived"
    imported = build_full_scale_import(
        manifest,
        quality,
        root,
        output,
        source_archive_path=archive,
        job_id="fixture-verify-import",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )
    bad_import = copy.deepcopy(imported.manifest)
    bad_import["events"] = bad_import["events"][:-1]
    rehash(bad_import)
    with pytest.raises(CareFullScaleError, match="semantics|order"):
        verify_full_scale_import_manifest(
            bad_import,
            output_root=output,
            source_manifest=manifest,
            quality_contract=quality,
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )

    raised_policy = copy.deepcopy(imported.manifest)
    raised_policy["resource_policy"]["max_import_runtime_seconds"] += 1
    rehash(raised_policy)
    with pytest.raises(CareFullScaleError, match="resource"):
        verify_full_scale_import_manifest(
            raised_policy,
            output_root=output,
            source_manifest=manifest,
            quality_contract=quality,
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )

    understated_wall_clock = copy.deepcopy(imported.manifest)
    understated_wall_clock["execution"]["wall_clock_elapsed_seconds"] = 0.0
    rehash(understated_wall_clock)
    with pytest.raises(CareFullScaleError, match="resource"):
        verify_full_scale_import_manifest(
            understated_wall_clock,
            output_root=output,
            source_manifest=manifest,
            quality_contract=quality,
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )

    changed_archive = copy.deepcopy(imported.manifest)
    changed_archive["source_archive_verification"]["sha256"] = "0" * 64
    rehash(changed_archive)
    with pytest.raises(CareFullScaleError, match="resource"):
        verify_full_scale_import_manifest(
            changed_archive,
            output_root=output,
            source_manifest=manifest,
            quality_contract=quality,
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )

    evaluated = build_full_scale_evaluation(
        imported.manifest,
        output,
        job_id="fixture-verify-evaluation",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )
    bad_evaluation = copy.deepcopy(evaluated.manifest)
    bad_evaluation["cross_farm_protocol"] = {
        "status": "enabled",
        "human_review_ids": [],
    }
    rehash(bad_evaluation)
    with pytest.raises(CareFullScaleError, match="ontology"):
        verify_full_scale_evaluation_manifest(
            bad_evaluation,
            output_root=output,
            import_manifest=imported.manifest,
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )

    raised_evaluation_policy = copy.deepcopy(evaluated.manifest)
    raised_evaluation_policy["resource_policy"]["max_evaluation_runtime_seconds"] += 1
    rehash(raised_evaluation_policy)
    with pytest.raises(CareFullScaleError, match="resource"):
        verify_full_scale_evaluation_manifest(
            raised_evaluation_policy,
            output_root=output,
            import_manifest=imported.manifest,
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )

    weakened_operational_policy = copy.deepcopy(evaluated.manifest)
    weakened_operational_policy["operational_policy"]["serving_limits"][
        "query_p95_milliseconds"
    ] += 1
    operational_unsigned = {
        key: value
        for key, value in weakened_operational_policy["operational_policy"].items()
        if key != "policy_sha256"
    }
    weakened_operational_policy["operational_policy"]["policy_sha256"] = hashlib.sha256(
        json.dumps(
            operational_unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    rehash(weakened_operational_policy)
    with pytest.raises(CareFullScaleError, match="release|resource"):
        verify_full_scale_evaluation_manifest(
            weakened_operational_policy,
            output_root=output,
            import_manifest=imported.manifest,
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )

    understated_evaluation_storage = copy.deepcopy(evaluated.manifest)
    understated_evaluation_storage["resource_actual"]["storage_bytes"] -= 1
    rehash(understated_evaluation_storage)
    with pytest.raises(CareFullScaleError, match="resource"):
        verify_full_scale_evaluation_manifest(
            understated_evaluation_storage,
            output_root=output,
            import_manifest=imported.manifest,
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )


def test_full_scale_import_exposes_storage_failure_and_recovers_without_partial_publish(
    tmp_path: Path,
) -> None:
    root, archive, manifest, quality, trust_anchor = _fixture(tmp_path)
    output = tmp_path / "storage-failure-derived"
    state_path = output / ".state" / "fixture-storage-recovery.json"

    with pytest.raises(RuntimeError, match="injected object store outage"):
        build_full_scale_import(
            manifest,
            quality,
            root,
            output,
            source_archive_path=archive,
            artifact_store=_UnavailableArtifactStore(),
            job_id="fixture-storage-recovery",
            expected_counts=EXPECTED,
            resource_limits=LIMITS,
            trust_anchor=trust_anchor,
        )

    failed_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert failed_state["status"] == "pending"
    assert failed_state["attempt"] == 1
    assert not (output / "care" / "v6" / "reports" / "full-import" / "manifest.json").exists()
    assert not list(output.rglob("*.partial"))

    completed = build_full_scale_import(
        manifest,
        quality,
        root,
        output,
        source_archive_path=archive,
        artifact_store=LocalImmutableArtifactStore(tmp_path / "recovered-objects"),
        job_id="fixture-storage-recovery",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )
    recovered_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert completed.manifest["summary"] == EXPECTED.to_document()
    assert recovered_state["status"] == "completed"
    assert recovered_state["attempt"] == 2


def test_full_scale_resource_violation_is_terminal_and_new_job_can_recover(
    tmp_path: Path,
) -> None:
    root, archive, manifest, quality, trust_anchor = _fixture(tmp_path)
    output = tmp_path / "resource-failure-derived"
    strict_limits = FullScaleResourceLimits(
        max_import_runtime_seconds=600,
        max_evaluation_runtime_seconds=600,
        max_peak_record_batch_bytes=16 * 1024 * 1024,
        max_peak_arrow_allocated_bytes=512 * 1024 * 1024,
        max_peak_process_resident_bytes=1024 * 1024 * 1024,
        max_import_storage_bytes=1,
        max_evaluation_storage_bytes=1024 * 1024 * 1024,
        min_import_rows_per_second=0.001,
        max_prediction_points=18,
    )

    with pytest.raises(CareFullScaleError, match="max_import_storage_bytes"):
        build_full_scale_import(
            manifest,
            quality,
            root,
            output,
            source_archive_path=archive,
            job_id="fixture-resource-limit",
            expected_counts=EXPECTED,
            resource_limits=strict_limits,
            trust_anchor=trust_anchor,
        )

    state = json.loads(
        (output / ".state" / "fixture-resource-limit.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "failed"
    assert "max_import_storage_bytes" in state["error"]
    assert not (output / "care" / "v6" / "reports" / "full-import" / "manifest.json").exists()

    completed = build_full_scale_import(
        manifest,
        quality,
        root,
        output,
        source_archive_path=archive,
        job_id="fixture-resource-limit-recovery",
        expected_counts=EXPECTED,
        resource_limits=LIMITS,
        trust_anchor=trust_anchor,
    )
    assert completed.manifest["resource_actual"]["limits_passed"] is True
