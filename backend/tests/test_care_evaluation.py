from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from test_care_importer import _build as build_minimal_import_fixture
from windops_backend.benchmarks.care.anomaly import (
    ActivationGateEvidence,
    ActivationGatePolicy,
    evaluate_activation_gate,
)
from windops_backend.benchmarks.care.anomaly import (
    BenchmarkMetricSnapshot as ActivationMetricSnapshot,
)
from windops_backend.benchmarks.care.evaluation import (
    COMPONENT_GENERALIZATION_PROTOCOL,
    EVALUATION_SUITE_PROTOCOL,
    CareOfflineEvaluationError,
    EvaluationSuiteSpec,
    build_evaluation_suite_artifact,
    build_offline_evaluations,
    register_offline_evaluations,
    verify_evaluation_suite_artifact,
)
from windops_backend.benchmarks.care.importer import register_a_minimal_import
from windops_backend.benchmarks.care.scoring import CareEventTruth, EvaluationFailure
from windops_backend.errors import ConflictError
from windops_backend.models import (
    BenchmarkEvaluationRun,
    BenchmarkEventResult,
    BenchmarkMetricSnapshot,
    RegisteredModel,
)

CREATED_AT = "2026-08-26T08:00:00+00:00"


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _build_evaluations(tmp_path: Path):
    (
        _,
        _,
        source_manifest,
        quality,
        import_root,
        _,
        imported,
        trust_anchor,
    ) = build_minimal_import_fixture(tmp_path)
    output_root = tmp_path / "evaluation-output"
    result = build_offline_evaluations(
        imported.manifest,
        quality,
        import_root,
        output_root,
        created_at=CREATED_AT,
        trust_anchor=trust_anchor,
    )
    return source_manifest, quality, imported, import_root, output_root, result, trust_anchor


def _load_artifact(output_root: Path, reference: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(
        (output_root / Path(reference["local_relative_path"])).read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return value


def _truths(artifact: dict[str, Any]) -> list[CareEventTruth]:
    return [CareEventTruth(**record) for record in artifact["truth_domain"]["records"]]


def test_offline_baselines_freeze_truth_free_predictions_and_reproduce(
    tmp_path: Path,
) -> None:
    _, quality, imported, import_root, output_root, first, trust_anchor = _build_evaluations(
        tmp_path
    )
    assert first.replayed is False
    assert first.manifest["suite_protocol"] == EVALUATION_SUITE_PROTOCOL
    assert first.manifest["component_generalization_protocol"] == (
        COMPONENT_GENERALIZATION_PROTOCOL
    )
    assert first.manifest["prediction_truth_available_to_training_or_calibration"] is False
    assert len(first.manifest["models"]) == 2

    deterministic_identities: list[tuple[str, tuple[str, ...], str]] = []
    for model in first.manifest["models"]:
        assert model["random_seed"] == 20_260_826
        assert model["summary"]["requested_event_count"] == 2
        assert model["summary"]["scored_event_count"] == 2
        assert {result["event_label"] for result in model["event_results"]} == {
            "anomaly",
            "normal",
        }
        package = _load_artifact(output_root, model["package"])
        assert package["prediction_truth_used"] is False
        assert package["training_split"] == "train"
        assert package["trusted_train_status_ids"] == ["0"]
        assert package["feature_set_sha256"] == quality["feature_set_sha256"]
        assert package["dependency_identity"]["implementation"]
        prediction_hashes: list[str] = []
        for reference in model["prediction_artifacts"]:
            prediction = _load_artifact(output_root, reference)
            prediction_text = json.dumps(prediction, sort_keys=True)
            assert prediction["prediction_truth_present"] is False
            assert prediction["source_split"] == "prediction"
            assert prediction["threshold_policy"]["calibration_split"] == "train"
            assert prediction["model_selection_provenance"]["prediction_truth_used"] is False
            assert "event_label" not in prediction_text
            assert "event_description" not in prediction_text
            assert all(
                {"anomaly_score", "binary_prediction", "valid_point_mask"}.issubset(point)
                for point in prediction["points"]
            )
            prediction_hashes.append(prediction["prediction_artifact_sha256"])
        evaluation = _load_artifact(output_root, model["evaluation_artifact"])
        verify_evaluation_suite_artifact(evaluation)
        assert evaluation["run"]["generalization_claim"] == ("none-minimal-fixed-event-suite")
        deterministic_identities.append(
            (
                package["model_package_sha256"],
                tuple(prediction_hashes),
                evaluation["evaluation_artifact_sha256"],
            )
        )

    object_count = len(
        [path for path in (output_root / "immutable-object-store").rglob("*") if path.is_file()]
    )
    replay = build_offline_evaluations(
        imported.manifest,
        quality,
        import_root,
        output_root,
        created_at=CREATED_AT,
        trust_anchor=trust_anchor,
    )
    assert replay.replayed is True
    assert replay.manifest == first.manifest
    assert replay.manifest_file_sha256 == first.manifest_file_sha256
    assert object_count == len(
        [path for path in (output_root / "immutable-object-store").rglob("*") if path.is_file()]
    )

    fresh_output = tmp_path / "fresh-evaluation-output"
    fresh = build_offline_evaluations(
        imported.manifest,
        quality,
        import_root,
        fresh_output,
        created_at=CREATED_AT,
        trust_anchor=trust_anchor,
    )
    fresh_identities = []
    for model in fresh.manifest["models"]:
        package = _load_artifact(fresh_output, model["package"])
        predictions = [
            _load_artifact(fresh_output, reference)["prediction_artifact_sha256"]
            for reference in model["prediction_artifacts"]
        ]
        evaluation = _load_artifact(fresh_output, model["evaluation_artifact"])
        fresh_identities.append(
            (
                package["model_package_sha256"],
                tuple(predictions),
                evaluation["evaluation_artifact_sha256"],
            )
        )
    assert fresh_identities == deterministic_identities
    assert fresh.manifest["result_identity_sha256"] == first.manifest["result_identity_sha256"]

    tampered_package = fresh_output / Path(
        fresh.manifest["models"][0]["package"]["local_relative_path"]
    )
    tampered_package.write_bytes(tampered_package.read_bytes() + b"tamper")
    with pytest.raises(CareOfflineEvaluationError, match="content drifted"):
        build_offline_evaluations(
            imported.manifest,
            quality,
            import_root,
            fresh_output,
            created_at=CREATED_AT,
            trust_anchor=trust_anchor,
        )


def test_suite_counts_failures_and_unscorable_events_and_rejects_omission(
    tmp_path: Path,
) -> None:
    _, _, _, _, output_root, built, _ = _build_evaluations(tmp_path)
    model = built.manifest["models"][0]
    evaluation = _load_artifact(output_root, model["evaluation_artifact"])
    predictions = evaluation["predictions"]
    truths = _truths(evaluation)
    base_spec = {
        "purpose": "development",
        "event_ids": (0, 24),
        "model_id": model["model_id"],
        "model_version": model["model_version"],
        "created_at": CREATED_AT,
    }

    failed = build_evaluation_suite_artifact(
        EvaluationSuiteSpec(run_id="failure-accounting", **base_spec),
        predictions[:1],
        truths[:1],
        source_dataset_sha256=evaluation["provenance"]["source_dataset_sha256"],
        source_import_manifest_sha256=evaluation["provenance"]["source_import_manifest_sha256"],
        license_metadata=evaluation["license"],
        failures=(EvaluationFailure(24, "model", "fixture-model-failure"),),
    )
    verify_evaluation_suite_artifact(failed)
    assert failed["summary"]["requested_event_count"] == 2
    assert failed["summary"]["model_failure_event_count"] == 1
    assert failed["summary"]["scored_event_count"] == 1
    assert failed["summary"]["status"] == "unscorable"

    unscorable_truths = [
        truths[0],
        CareEventTruth(
            event_id=24,
            farm="A",
            source_asset_id=truths[1].source_asset_id,
            event_label="normal",
            event_start_source_row_id=99_998,
            event_end_source_row_id=99_999,
        ),
    ]
    unscorable = build_evaluation_suite_artifact(
        EvaluationSuiteSpec(run_id="unscorable-accounting", **base_spec),
        predictions,
        unscorable_truths,
        source_dataset_sha256=evaluation["provenance"]["source_dataset_sha256"],
        source_import_manifest_sha256=evaluation["provenance"]["source_import_manifest_sha256"],
        license_metadata=evaluation["license"],
    )
    verify_evaluation_suite_artifact(unscorable)
    assert unscorable["summary"]["unscorable_event_count"] == 1
    assert unscorable["summary"]["unscorable_events"] == [
        {"event_id": 24, "reason": "truth-interval-boundary-not-in-prediction"}
    ]
    with pytest.raises(CareOfflineEvaluationError, match="account for every event"):
        build_evaluation_suite_artifact(
            EvaluationSuiteSpec(run_id="silently-omitted", **base_spec),
            predictions[:1],
            truths[:1],
            source_dataset_sha256=evaluation["provenance"]["source_dataset_sha256"],
            source_import_manifest_sha256=evaluation["provenance"]["source_import_manifest_sha256"],
            license_metadata=evaluation["license"],
        )


def test_offline_suite_is_accepted_only_by_structured_server_activation_gate(
    tmp_path: Path,
) -> None:
    _, _, _, _, output_root, built, _ = _build_evaluations(tmp_path)
    model = built.manifest["models"][0]
    artifact = _load_artifact(output_root, model["evaluation_artifact"])
    prediction = artifact["predictions"][0]
    snapshot = ActivationMetricSnapshot.from_evaluation_artifact(artifact)
    policy = ActivationGatePolicy(
        policy_version="care-h004-activation-v1",
        minimum_care_score=0.0,
        minimum_event_detection_rate=0.0,
        maximum_normal_event_false_positive_rate=1.0,
        required_farms=("A",),
        required_generalization_protocols=(EVALUATION_SUITE_PROTOCOL,),
        required_feature_set_version=prediction["feature_set_version"],
        required_feature_set_sha256=prediction["feature_set_sha256"],
        required_quality_rule_version=prediction["quality_rule_version"],
        required_quality_contract_sha256=prediction["quality_contract_sha256"],
        required_threshold_policy_version=prediction["threshold_policy"]["version"],
        required_threshold_policy_sha256=prediction["threshold_policy"]["threshold_policy_sha256"],
    )
    evidence = ActivationGateEvidence(
        evaluation_run_id=model["evaluation_run_id"],
        evaluation_status="completed",
        invalidated=False,
        evaluation_artifact=artifact,
        metric_snapshot=snapshot,
        model_id=model["model_id"],
        model_version=model["model_version"],
        model_artifact_sha256=model["package"]["file_sha256"],
        deployment_id="care-h004-deployment",
        deployment_version="care-h004-deployment",
        approval_ids=("approval-h004",),
        audit_event_ids=("audit-h004",),
    )
    authorization = evaluate_activation_gate(
        policy,
        evidence,
        authorized_at=datetime(2026, 8, 26, 8, tzinfo=UTC),
    )
    assert authorization.evaluation_run_id == model["evaluation_run_id"]

    tampered = copy.deepcopy(artifact)
    tampered["summary"]["care_score"] = 1.0
    with pytest.raises(ValueError, match="hash or schema"):
        ActivationMetricSnapshot.from_evaluation_artifact(tampered)


@pytest.mark.asyncio
async def test_offline_registration_is_atomic_complete_and_exactly_idempotent(
    app: FastAPI,
    tmp_path: Path,
) -> None:
    source_manifest, quality, imported, _, _, built, trust_anchor = _build_evaluations(tmp_path)
    async with app.state.session_factory() as session, session.begin():
        await register_a_minimal_import(
            session,
            imported.manifest,
            source_manifest,
            quality,
            tenant_id="tenant-east-china",
            subject="care-worker",
            trust_anchor=trust_anchor,
        )
        first = await register_offline_evaluations(
            session,
            built.manifest,
            artifact_root=built.manifest_path.parents[4],
            subject="care-worker",
            trust_anchor=trust_anchor,
        )
    expected_records = sum(2 + 2 + len(model["metrics"]) for model in built.manifest["models"])
    assert first.created_count == expected_records
    assert first.replayed_count == 0

    async with app.state.session_factory() as session, session.begin():
        replay = await register_offline_evaluations(
            session,
            built.manifest,
            artifact_root=built.manifest_path.parents[4],
            subject="care-worker",
            trust_anchor=trust_anchor,
        )
    assert replay.created_count == 0
    assert replay.replayed_count == expected_records

    async with app.state.session_factory() as session:
        assert (
            int(
                await session.scalar(
                    select(func.count(RegisteredModel.id)).where(
                        RegisteredModel.id.in_(first.model_ids)
                    )
                )
                or 0
            )
            == 2
        )
        assert (
            int(
                await session.scalar(
                    select(func.count(BenchmarkEvaluationRun.id)).where(
                        BenchmarkEvaluationRun.id.in_(first.evaluation_run_ids)
                    )
                )
                or 0
            )
            == 2
        )
        assert (
            int(
                await session.scalar(
                    select(func.count(BenchmarkEventResult.id)).where(
                        BenchmarkEventResult.evaluation_run_id.in_(first.evaluation_run_ids)
                    )
                )
                or 0
            )
            == 4
        )
        assert int(
            await session.scalar(
                select(func.count(BenchmarkMetricSnapshot.id)).where(
                    BenchmarkMetricSnapshot.evaluation_run_id.in_(first.evaluation_run_ids)
                )
            )
            or 0
        ) == sum(len(model["metrics"]) for model in built.manifest["models"])
        statuses = (
            (
                await session.execute(
                    select(BenchmarkEvaluationRun.status).where(
                        BenchmarkEvaluationRun.id.in_(first.evaluation_run_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert statuses == ["completed", "completed"]

    conflicting = copy.deepcopy(built.manifest)
    conflicting["models"][0]["model_name"] = "resigned conflicting identity"
    unsigned = {key: value for key, value in conflicting.items() if key != "manifest_sha256"}
    conflicting["manifest_sha256"] = _canonical_hash(unsigned)
    async with app.state.session_factory() as session:
        with pytest.raises(ConflictError, match="different content"):
            async with session.begin():
                await register_offline_evaluations(
                    session,
                    conflicting,
                    artifact_root=built.manifest_path.parents[4],
                    subject="care-worker",
                    trust_anchor=trust_anchor,
                )
