from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from windops_backend.benchmarks.care.quality import (
    FEATURE_SET_VERSION,
    QUALITY_RULE_VERSION,
)
from windops_backend.benchmarks.care.scoring import (
    CRITICALITY_THRESHOLD,
    REFERENCE_COMMIT,
    SCORE_PROTOCOL_VERSION,
    CalibrationInput,
    CareEventTruth,
    CareScoreError,
    EvaluationFailure,
    EvaluationRunSpec,
    FinalCareEvaluator,
    ModelSelectionProvenance,
    PredictionBatch,
    PredictionPoint,
    PredictionTruthVault,
    ThresholdPolicy,
    build_evaluation_artifact,
    build_prediction_artifact,
    build_score_protocol,
    fixed_threshold_policy,
    recompute_evaluation_artifact,
    verify_evaluation_artifact,
    verify_prediction_artifact,
    verify_score_protocol,
    write_evaluation_artifact,
    write_score_protocol,
)


def _threshold(value: float = 0.5) -> ThresholdPolicy:
    calibration = CalibrationInput(
        anomaly_scores=(0.1, 0.2, 0.3),
        source_split="train-validation",
        source_run_id="train-run-1",
    )
    return fixed_threshold_policy(
        calibration,
        value=value,
        version="threshold-policy-test-v1",
    )


def _prediction(
    event_id: int,
    scores: list[float],
    *,
    farm: str = "B",
    asset: str = "asset-1",
    statuses: list[str] | None = None,
    disagreement_runs: list[int] | None = None,
    corroborated: list[bool] | None = None,
    threshold: float = 0.5,
) -> dict[str, Any]:
    statuses = statuses or ["0"] * len(scores)
    disagreement_runs = disagreement_runs or [1] * len(scores)
    corroborated = corroborated or [False] * len(scores)
    points = tuple(
        PredictionPoint(
            source_row_id=index,
            source_timestamp=f"source-{index:04d}",
            anonymous_time=f"2022-01-01T{index // 6:02d}:{(index % 6) * 10:02d}:00",
            anomaly_score=score,
            status_id=statuses[index],
            disagreement_run_length=disagreement_runs[index],
            corroborated_by_signal=corroborated[index],
            corroboration_signal_count=1 if farm in {"B", "C"} else 0,
            corroboration_finite_signal_count=1 if farm in {"B", "C"} else 0,
            corroboration_inactive_or_invalid_signal_count=(
                1 if farm in {"B", "C"} and corroborated[index] else 0
            ),
        )
        for index, score in enumerate(scores)
    )
    batch = PredictionBatch(
        event_id=event_id,
        farm=farm,
        source_asset_id=asset,
        points=points,
        model_id="model-care-test",
        model_version="1",
        deployment_id=None,
        feature_set_version=FEATURE_SET_VERSION,
        feature_set_sha256="feature-set-test-sha",
        quality_rule_version=QUALITY_RULE_VERSION,
        quality_contract_sha256="quality-contract-test-sha",
        model_selection_provenance=ModelSelectionProvenance(
            training_run_id="train-run-1",
            feature_selection_split="train",
            early_stopping_split="train-validation",
            hyperparameter_selection_split="train-validation",
        ),
    )
    return build_prediction_artifact(
        batch,
        _threshold(threshold),
        trusted_status_ids=("0", "2"),
        status_signal_columns=(("fixture_scaled_power_avg",) if farm in {"B", "C"} else ()),
    )


def _truth(
    event_id: int,
    label: str,
    length: int,
    *,
    farm: str = "B",
    asset: str = "asset-1",
) -> CareEventTruth:
    return CareEventTruth(
        event_id=event_id,
        farm=farm,
        source_asset_id=asset,
        event_label=label,
        event_start_source_row_id=0,
        event_end_source_row_id=length - 1,
        failure_type="fixture-failure" if label == "anomaly" else None,
    )


def _evaluate(prediction: dict[str, Any], truth: CareEventTruth) -> dict[str, Any]:
    return FinalCareEvaluator(PredictionTruthVault((truth,))).evaluate_event(prediction)


def _two_event_artifact(
    anomaly_scores: list[float],
    normal_scores: list[float],
    *,
    purpose: str = "development",
) -> dict[str, Any]:
    predictions = [_prediction(10, anomaly_scores), _prediction(11, normal_scores)]
    truths = [
        _truth(10, "anomaly", len(anomaly_scores)),
        _truth(11, "normal", len(normal_scores)),
    ]
    run = EvaluationRunSpec(
        run_id=f"run-{purpose}",
        purpose=purpose,
        generalization_protocol="within-farm-leave-one-turbine-out-v1",
        event_ids=(10, 11),
        model_id="model-care-test",
        model_version="1",
        created_at="2026-08-26T18:42:00+08:00",
        farm="B",
        held_out_asset_id="asset-1",
    )
    return build_evaluation_artifact(
        run,
        FinalCareEvaluator(PredictionTruthVault(truths)),
        predictions,
    )


def _rehash(payload: dict[str, Any], hash_field: str) -> None:
    unsigned = {key: value for key, value in payload.items() if key != hash_field}
    encoded = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    payload[hash_field] = hashlib.sha256(encoded).hexdigest()


def test_protocol_freezes_authoritative_constants_boundaries_and_sources() -> None:
    first = build_score_protocol()
    second = build_score_protocol()

    assert first == second
    verify_score_protocol(first)
    assert first["score_protocol_version"] == SCORE_PROTOCOL_VERSION
    assert first["authority"]["reference_implementation"]["commit"] == REFERENCE_COMMIT
    assert first["coverage"]["beta"] == 0.5
    assert first["reliability"]["beta"] == 0.5
    assert first["criticality"]["event_threshold"] == 72
    assert first["criticality"]["threshold_equal_detected"] is True
    assert first["point_prediction"]["threshold_equal_is_anomaly"] is False
    assert first["earliness"]["start_of_descend"] == [1, 4]
    assert first["aggregation"]["weights"] == {
        "coverage": 1.0,
        "accuracy": 2.0,
        "reliability": 1.0,
        "earliness": 1.0,
    }
    assert first["aggregation"]["rounding"].startswith("no intermediate")
    assert first["golden_vectors"]["criticality_boundary"] == {
        "max_criticality": [71, 72, 73],
        "event_detected": [False, True, True],
    }
    assert first["golden_vectors"]["earliness_four_points"]["scores"] == [
        0.3488372093023256,
        0.21705426356589147,
        0.09302325581395347,
    ]


def test_threshold_equality_is_normal_and_prediction_artifact_is_complete() -> None:
    artifact = _prediction(1, [0.49, 0.5, 0.51])

    verify_prediction_artifact(artifact)
    assert [point["binary_prediction"] for point in artifact["points"]] == [False, False, True]
    assert [point["criticality"] for point in artifact["points"]] == [0, 0, 1]
    assert artifact["threshold_policy"]["value"] == 0.5
    assert artifact["prediction_truth_present"] is False
    assert {
        "anomaly_score",
        "binary_prediction",
        "valid_point_mask",
        "criticality",
        "source_timestamp",
        "anonymous_time",
    }.issubset(artifact["points"][0])


@pytest.mark.parametrize(
    ("length", "detected"),
    [(71, False), (72, True), (73, True)],
)
def test_criticality_71_72_73_inclusive_boundary(length: int, detected: bool) -> None:
    prediction = _prediction(length, [1.0] * length)
    result = _evaluate(prediction, _truth(length, "anomaly", length))

    assert result["max_criticality"] == length
    assert result["criticality_threshold"] == CRITICALITY_THRESHOLD
    assert result["event_detected"] is detected


def test_all_normal_and_all_anomaly_predictions_hit_official_special_branches() -> None:
    all_normal = _two_event_artifact([0.0] * 73, [0.0] * 73)
    assert all_normal["summary"]["care_score"] == 0.0
    assert all_normal["summary"]["special_branch"] == "no-event-detected"

    all_anomaly = _two_event_artifact([1.0] * 73, [1.0] * 73)
    assert all_anomaly["summary"]["care_score"] == 0.0
    assert all_anomaly["summary"]["special_branch"] == "normal-accuracy-at-or-below-0.5"


def test_no_alarm_and_sustained_normal_false_alarm_metrics() -> None:
    no_alarm = _two_event_artifact([1.0, 0.0] * 40, [0.0] * 80)
    assert no_alarm["summary"]["special_branch"] == "no-event-detected"

    sustained = _two_event_artifact([1.0] * 72, [1.0] * 72)
    metrics = sustained["summary"]["event_metrics"]
    assert metrics["false_alarm_normal_event_count"] == 1
    assert metrics["normal_event_false_positive_rate"] == 1.0
    assert metrics["valid_normal_hours"] == 12.0
    assert metrics["false_alarms_per_1000_valid_normal_hours"] == pytest.approx(1000 / 12)
    assert metrics["normal_prediction_event_days"] == 0.5
    assert metrics["false_alarms_per_prediction_event_day"] == 2.0
    assert metrics["false_alarms_per_turbine_year"] is None
    assert metrics["turbine_year_metric_status"].startswith("disabled")


def test_a_prediction_status_exception_and_bc_filter_freeze() -> None:
    a_prediction = _prediction(
        1,
        [1.0, 1.0, 1.0],
        farm="A",
        statuses=["4", "4", "4"],
        disagreement_runs=[10, 10, 10],
        corroborated=[False, False, False],
    )
    assert a_prediction["valid_point_count"] == 3
    assert [point["criticality"] for point in a_prediction["points"]] == [1, 2, 3]
    assert {point["status_reason"] for point in a_prediction["points"]} == {
        "care-v6-a-prediction-status-exception"
    }

    bc_prediction = _prediction(
        2,
        [1.0, 1.0, 1.0, 1.0],
        statuses=["0", "5", "5", "0"],
        disagreement_runs=[1, 3, 4, 1],
        corroborated=[False, True, True, False],
    )
    assert [point["valid_point_mask"] for point in bc_prediction["points"]] == [
        True,
        False,
        False,
        True,
    ]
    assert [point["criticality"] for point in bc_prediction["points"]] == [1, 1, 1, 2]


def test_earliness_reference_weights_reward_front_half_over_back_and_endpoint() -> None:
    scores = {
        "front": [1.0, 0.0, 0.0, 0.0],
        "back": [0.0, 0.0, 1.0, 0.0],
        "end": [0.0, 0.0, 0.0, 1.0],
    }
    results = {
        name: _evaluate(_prediction(index, values), _truth(index, "anomaly", 4))
        for index, (name, values) in enumerate(scores.items(), start=20)
    }

    assert results["front"]["earliness"] == pytest.approx(15 / 43)
    assert results["back"]["earliness"] == pytest.approx(28 / 129)
    assert results["end"]["earliness"] == pytest.approx(4 / 43)
    assert results["front"]["earliness"] > results["back"]["earliness"]
    assert results["back"]["earliness"] > results["end"]["earliness"]
    assert results["end"]["earliness_intermediate"][-1]["source_row_id"] == 3


@pytest.mark.parametrize(
    ("normal_scores", "expected_accuracy"),
    [([1.0] * 6 + [0.0] * 4, 0.4), ([1.0] * 5 + [0.0] * 5, 0.5)],
)
def test_accuracy_low_and_equal_boundary_use_reference_special_branch(
    normal_scores: list[float], expected_accuracy: float
) -> None:
    artifact = _two_event_artifact([1.0] * 72, normal_scores)

    assert artifact["summary"]["components"]["average_normal_accuracy"] == expected_accuracy
    assert artifact["summary"]["special_branch"] == "normal-accuracy-at-or-below-0.5"
    assert artifact["summary"]["care_score"] == expected_accuracy


def test_no_valid_points_are_explicitly_unscorable() -> None:
    prediction = _prediction(
        30,
        [1.0, 1.0, 1.0],
        statuses=["5", "5", "5"],
        disagreement_runs=[3, 3, 3],
        corroborated=[True, True, True],
    )
    result = _evaluate(prediction, _truth(30, "anomaly", 3))

    assert prediction["valid_point_count"] == 0
    assert result["status"] == "unscorable"
    assert result["unscorable_reason"] == "no-valid-prediction-points"


def test_training_and_calibration_types_cannot_read_prediction_truth() -> None:
    calibration = CalibrationInput((0.1, 0.2), "train", "train-only")
    assert not hasattr(calibration, "prediction_truth")
    assert not hasattr(calibration, "event_label")
    with pytest.raises(CareScoreError, match="train or train-validation"):
        CalibrationInput((0.1,), "prediction", "forbidden")
    with pytest.raises(CareScoreError, match="prediction truth"):
        ThresholdPolicy(0.5, "v1", "prediction", "forbidden", "best-on-truth")
    for field_name in (
        "feature_selection_split",
        "early_stopping_split",
        "hyperparameter_selection_split",
    ):
        values = {
            "feature_selection_split": "train",
            "early_stopping_split": "train-validation",
            "hyperparameter_selection_split": "not-used",
        }
        values[field_name] = "prediction"
        with pytest.raises(CareScoreError, match=field_name):
            ModelSelectionProvenance(training_run_id="train-only", **values)

    prediction = _prediction(31, [0.1, 0.9])
    serialized = json.dumps(prediction, sort_keys=True)
    assert "event_label" not in serialized
    assert "ground_truth" not in serialized
    assert prediction["model_selection_provenance"]["prediction_truth_used"] is False
    vault = PredictionTruthVault((_truth(31, "anomaly", 2),))
    assert not hasattr(vault, "read")


def test_single_event_and_within_farm_protocols_are_distinct_and_cross_farm_fails() -> None:
    single = EvaluationRunSpec(
        run_id="single",
        purpose="development",
        generalization_protocol="care-event-train-prediction-v6",
        event_ids=(1,),
        model_id="m",
        model_version="1",
        created_at="2026-08-26T00:00:00Z",
    )
    within = EvaluationRunSpec(
        run_id="within",
        purpose="tuning",
        generalization_protocol="within-farm-leave-one-turbine-out-v1",
        event_ids=(1, 2),
        model_id="m",
        model_version="1",
        created_at="2026-08-26T00:00:00Z",
        farm="C",
        held_out_asset_id="asset-c",
    )
    assert single.generalization_protocol != within.generalization_protocol
    with pytest.raises(CareScoreError, match="cross-farm evaluation is disabled"):
        EvaluationRunSpec(
            run_id="cross",
            purpose="development",
            generalization_protocol="cross-farm-ontology-v1",
            event_ids=(1, 2),
            model_id="m",
            model_version="1",
            created_at="2026-08-26T00:00:00Z",
        )
    with pytest.raises(CareScoreError, match="exactly one event"):
        EvaluationRunSpec(
            run_id="bad-single",
            purpose="development",
            generalization_protocol="care-event-train-prediction-v6",
            event_ids=(1, 2),
            model_id="m",
            model_version="1",
            created_at="2026-08-26T00:00:00Z",
        )


def test_event_prediction_artifact_fully_recomputes_score_and_rejects_semantic_tamper() -> None:
    artifact = _two_event_artifact([1.0] * 72, [0.0] * 72)

    verify_evaluation_artifact(artifact)
    assert recompute_evaluation_artifact(artifact) == artifact
    assert artifact["summary"]["status"] == "scored"
    components = artifact["summary"]["components"]
    assert components["average_coverage_f0_5"] == 1.0
    assert components["average_normal_accuracy"] == 1.0
    assert components["reliability_event_f0_5"] == 1.0
    assert components["average_earliness"] == 0.9999999999999996
    assert components["weights"] == {
        "coverage": 1.0,
        "accuracy": 2.0,
        "reliability": 1.0,
        "earliness": 1.0,
    }
    assert artifact["summary"]["care_score"] == 1.0

    prediction = dict(artifact["predictions"][0])
    prediction["points"] = [dict(point) for point in prediction["points"]]
    prediction["points"][0]["binary_prediction"] = False
    _rehash(prediction, "prediction_artifact_sha256")
    with pytest.raises(CareScoreError, match="binary threshold result mismatch"):
        verify_prediction_artifact(prediction)


def test_protocol_and_artifacts_are_deterministic_and_final_holdout_is_write_once(
    tmp_path: Path,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    write_score_protocol(protocol_path)
    first_protocol = protocol_path.read_bytes()
    write_score_protocol(protocol_path)
    assert protocol_path.read_bytes() == first_protocol

    artifact = _two_event_artifact([1.0] * 72, [0.0] * 72, purpose="final-holdout")
    artifact_path = tmp_path / "final-evaluation.json"
    write_evaluation_artifact(artifact_path, artifact)
    first_artifact = artifact_path.read_bytes()
    with pytest.raises(CareScoreError, match="cannot be overwritten"):
        write_evaluation_artifact(artifact_path, artifact)
    assert artifact_path.read_bytes() == first_artifact


def test_tampered_protocol_and_artifact_hashes_fail_closed() -> None:
    protocol = build_score_protocol()
    protocol["criticality"]["event_threshold"] = 71
    with pytest.raises(CareScoreError, match="protocol hash mismatch"):
        verify_score_protocol(protocol)

    artifact = _two_event_artifact([1.0] * 72, [0.0] * 72)
    artifact["summary"]["care_score"] = 0.99
    with pytest.raises(CareScoreError, match="artifact hash mismatch"):
        verify_evaluation_artifact(artifact)
    _rehash(artifact, "evaluation_artifact_sha256")
    with pytest.raises(CareScoreError, match="cannot be reproduced"):
        verify_evaluation_artifact(artifact)


def test_data_and_model_failures_are_counted_and_never_silently_dropped() -> None:
    predictions = [_prediction(40, [1.0] * 72), _prediction(41, [0.0] * 72)]
    truths = [_truth(40, "anomaly", 72), _truth(41, "normal", 72)]
    run = EvaluationRunSpec(
        run_id="run-with-failures",
        purpose="development",
        generalization_protocol="within-farm-leave-one-turbine-out-v1",
        event_ids=(40, 41, 42, 43),
        model_id="model-care-test",
        model_version="1",
        created_at="2026-08-26T18:42:00+08:00",
        farm="B",
        held_out_asset_id="asset-1",
    )
    artifact = build_evaluation_artifact(
        run,
        FinalCareEvaluator(PredictionTruthVault(truths)),
        predictions,
        failures=(
            EvaluationFailure(42, "data", "source checksum mismatch"),
            EvaluationFailure(43, "model", "inference failed"),
        ),
    )

    assert artifact["summary"]["requested_event_count"] == 4
    assert artifact["summary"]["scored_event_count"] == 2
    assert artifact["summary"]["data_failure_event_count"] == 1
    assert artifact["summary"]["model_failure_event_count"] == 1
    assert artifact["summary"]["failed_events"] == [
        {"event_id": 42, "category": "data", "reason": "source checksum mismatch"},
        {"event_id": 43, "category": "model", "reason": "inference failed"},
    ]
    assert recompute_evaluation_artifact(artifact) == artifact
