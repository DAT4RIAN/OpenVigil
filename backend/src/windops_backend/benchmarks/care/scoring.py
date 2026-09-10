from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import windops_backend.benchmarks.care.scoring_prediction as _scoring_prediction

SCORE_PROTOCOL_VERSION = _scoring_prediction.SCORE_PROTOCOL_VERSION
SCORE_PROTOCOL_SCHEMA_VERSION = _scoring_prediction.SCORE_PROTOCOL_SCHEMA_VERSION
PREDICTION_ARTIFACT_SCHEMA_VERSION = _scoring_prediction.PREDICTION_ARTIFACT_SCHEMA_VERSION
EVALUATION_ARTIFACT_SCHEMA_VERSION = _scoring_prediction.EVALUATION_ARTIFACT_SCHEMA_VERSION
THRESHOLD_POLICY_SCHEMA_VERSION = _scoring_prediction.THRESHOLD_POLICY_SCHEMA_VERSION
POINT_BETA = _scoring_prediction.POINT_BETA
EVENT_BETA = _scoring_prediction.EVENT_BETA
CRITICALITY_THRESHOLD = _scoring_prediction.CRITICALITY_THRESHOLD
EARLINESS_START_NUMERATOR = _scoring_prediction.EARLINESS_START_NUMERATOR
EARLINESS_START_DENOMINATOR = _scoring_prediction.EARLINESS_START_DENOMINATOR
COMPONENT_WEIGHTS = _scoring_prediction.COMPONENT_WEIGHTS
RUN_PURPOSES = _scoring_prediction.RUN_PURPOSES
CALIBRATION_SPLITS = _scoring_prediction.CALIBRATION_SPLITS
MODEL_SELECTION_SPLITS = _scoring_prediction.MODEL_SELECTION_SPLITS
GENERALIZATION_PROTOCOLS = _scoring_prediction.GENERALIZATION_PROTOCOLS
DISABLED_GENERALIZATION_PROTOCOL = _scoring_prediction.DISABLED_GENERALIZATION_PROTOCOL
PAPER_URL = _scoring_prediction.PAPER_URL
REFERENCE_RELEASE_URL = _scoring_prediction.REFERENCE_RELEASE_URL
REFERENCE_COMMIT = _scoring_prediction.REFERENCE_COMMIT
REFERENCE_SCORE_SOURCE_URL = _scoring_prediction.REFERENCE_SCORE_SOURCE_URL
REFERENCE_CRITICALITY_SOURCE_URL = _scoring_prediction.REFERENCE_CRITICALITY_SOURCE_URL
REFERENCE_SCORE_SOURCE_SHA256 = _scoring_prediction.REFERENCE_SCORE_SOURCE_SHA256
REFERENCE_CRITICALITY_SOURCE_SHA256 = _scoring_prediction.REFERENCE_CRITICALITY_SOURCE_SHA256
PAPER_PDF_SHA256 = _scoring_prediction.PAPER_PDF_SHA256
CareScoreError = _scoring_prediction.CareScoreError
_canonical_json_bytes = _scoring_prediction._canonical_json_bytes
_canonical_hash = _scoring_prediction._canonical_hash
_require_nonempty = _scoring_prediction._require_nonempty
_require_finite = _scoring_prediction._require_finite
build_score_protocol = _scoring_prediction.build_score_protocol
verify_score_protocol = _scoring_prediction.verify_score_protocol
CalibrationInput = _scoring_prediction.CalibrationInput
ThresholdPolicy = _scoring_prediction.ThresholdPolicy
fixed_threshold_policy = _scoring_prediction.fixed_threshold_policy
ModelSelectionProvenance = _scoring_prediction.ModelSelectionProvenance
PredictionPoint = _scoring_prediction.PredictionPoint
PredictionBatch = _scoring_prediction.PredictionBatch
_verify_threshold_policy = _scoring_prediction._verify_threshold_policy
build_prediction_artifact = _scoring_prediction.build_prediction_artifact
verify_prediction_artifact = _scoring_prediction.verify_prediction_artifact


@dataclass(frozen=True, slots=True)
class CareEventTruth:
    event_id: int
    farm: str
    source_asset_id: str
    event_label: str
    event_start_source_row_id: int
    event_end_source_row_id: int
    failure_type: str | None = None

    def __post_init__(self) -> None:
        if self.event_id < 0:
            raise CareScoreError("truth event_id must be non-negative")
        if self.farm not in {"A", "B", "C"}:
            raise CareScoreError("truth farm must be A, B, or C")
        if self.event_label not in {"anomaly", "normal"}:
            raise CareScoreError("event truth label must be anomaly or normal")
        if self.event_start_source_row_id > self.event_end_source_row_id:
            raise CareScoreError("event truth interval is reversed")
        _require_nonempty(self.source_asset_id, field="truth source asset ID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "farm": self.farm,
            "source_asset_id": self.source_asset_id,
            "event_label": self.event_label,
            "event_start_source_row_id": self.event_start_source_row_id,
            "event_end_source_row_id": self.event_end_source_row_id,
            "failure_type": self.failure_type,
        }


@dataclass(frozen=True, slots=True)
class _FinalEvaluationCapability:
    vault_nonce: object


class PredictionTruthVault:
    """Prediction truth domain; it intentionally exposes no public read API."""

    __slots__ = ("__nonce", "__records")

    def __init__(self, records: Sequence[CareEventTruth]) -> None:
        if not records:
            raise CareScoreError("prediction truth vault must contain at least one event")
        by_id = {record.event_id: record for record in records}
        if len(by_id) != len(records):
            raise CareScoreError("prediction truth vault contains duplicate event IDs")
        self.__records = by_id
        self.__nonce = object()

    def _issue_final_evaluator_capability(self) -> _FinalEvaluationCapability:
        return _FinalEvaluationCapability(self.__nonce)

    def _read_for_final_evaluator(
        self,
        event_id: int,
        capability: _FinalEvaluationCapability,
    ) -> CareEventTruth:
        if capability.vault_nonce is not self.__nonce:
            raise CareScoreError("prediction truth access denied")
        try:
            return self.__records[event_id]
        except KeyError as exc:
            raise CareScoreError(f"prediction truth missing for event {event_id}") from exc


def _f_beta(*, tp: int, fp: int, fn: int, beta: float) -> float:
    beta_squared = beta * beta
    denominator = (1 + beta_squared) * tp + beta_squared * fn + fp
    if denominator == 0:
        return 0.0
    return ((1 + beta_squared) * tp) / denominator


def _reference_earliness_weights(event_length: int) -> list[float]:
    if event_length <= 0:
        raise CareScoreError("earliness requires a non-empty event window")
    scale = EARLINESS_START_DENOMINATOR
    start_of_descend = EARLINESS_START_NUMERATOR / EARLINESS_START_DENOMINATOR
    scaled_event_length = event_length * scale
    change_point = int(scaled_event_length * start_of_descend)
    slope = 1 / (1 - start_of_descend)
    offset = scale / (1 - start_of_descend)
    denominator = scaled_event_length - 1
    weights: list[float] = []
    for index in range(event_length):
        scaled_index = index * scale
        if scaled_index < change_point:
            raw_weight = float(scale)
        else:
            x_value = 0.0 if denominator == 0 else scale * scaled_index / denominator
            raw_weight = offset - slope * x_value
        weights.append(raw_weight / scale)
    return weights


def _average_precision(pairs: Sequence[tuple[float, bool]]) -> float | None:
    positive_count = sum(label for _, label in pairs)
    if positive_count == 0:
        return None
    ordered = sorted(pairs, key=lambda pair: pair[0], reverse=True)
    true_positives = 0
    false_positives = 0
    previous_recall = 0.0
    average_precision = 0.0
    cursor = 0
    while cursor < len(ordered):
        score = ordered[cursor][0]
        group_true = 0
        group_false = 0
        while cursor < len(ordered) and ordered[cursor][0] == score:
            if ordered[cursor][1]:
                group_true += 1
            else:
                group_false += 1
            cursor += 1
        true_positives += group_true
        false_positives += group_false
        recall = true_positives / positive_count
        precision = true_positives / (true_positives + false_positives)
        average_precision += (recall - previous_recall) * precision
        previous_recall = recall
    return average_precision


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


class FinalCareEvaluator:
    """The only component granted access to prediction truth."""

    __slots__ = ("_capability", "_truth_vault")

    def __init__(self, truth_vault: PredictionTruthVault) -> None:
        self._truth_vault = truth_vault
        self._capability = truth_vault._issue_final_evaluator_capability()

    def evaluate_event(self, prediction_artifact: Mapping[str, Any]) -> dict[str, Any]:
        verify_prediction_artifact(prediction_artifact)
        event_id = int(prediction_artifact["event_id"])
        truth = self._truth_vault._read_for_final_evaluator(event_id, self._capability)
        if (
            truth.farm != prediction_artifact["farm"]
            or truth.source_asset_id != prediction_artifact["source_asset_id"]
        ):
            raise CareScoreError("prediction artifact identity does not match event truth")

        common_result: dict[str, Any] = {
            "event_id": event_id,
            "farm": truth.farm,
            "source_asset_id": truth.source_asset_id,
            "event_label": truth.event_label,
            "failure_type": truth.failure_type,
            "event_start_source_row_id": truth.event_start_source_row_id,
            "event_end_source_row_id": truth.event_end_source_row_id,
            "prediction_artifact_sha256": prediction_artifact["prediction_artifact_sha256"],
        }

        points = prediction_artifact["points"]
        row_positions = {int(point["source_row_id"]): index for index, point in enumerate(points)}
        if (
            truth.event_start_source_row_id not in row_positions
            or truth.event_end_source_row_id not in row_positions
        ):
            return {
                **common_result,
                "status": "unscorable",
                "unscorable_reason": "truth-interval-boundary-not-in-prediction",
            }

        valid_points = [point for point in points if bool(point["valid_point_mask"])]
        if not valid_points:
            return {
                **common_result,
                "status": "unscorable",
                "unscorable_reason": "no-valid-prediction-points",
            }

        tp = fp = tn = fn = 0
        scored_points: list[dict[str, Any]] = []
        for point in valid_points:
            row_id = int(point["source_row_id"])
            is_true_anomaly = truth.event_label == "anomaly" and (
                truth.event_start_source_row_id <= row_id <= truth.event_end_source_row_id
            )
            predicted = bool(point["binary_prediction"])
            if is_true_anomaly and predicted:
                tp += 1
            elif is_true_anomaly:
                fn += 1
            elif predicted:
                fp += 1
            else:
                tn += 1
            scored_points.append(
                {
                    "source_row_id": row_id,
                    "ground_truth": is_true_anomaly,
                    "binary_prediction": predicted,
                    "anomaly_score": point["anomaly_score"],
                }
            )

        event_end_position = row_positions[truth.event_end_source_row_id]
        criticality_points = points[: event_end_position + 1]
        max_criticality = max(int(point["criticality"]) for point in criticality_points)
        event_detected = max_criticality >= CRITICALITY_THRESHOLD
        first_detected = next(
            (
                point
                for point in criticality_points
                if int(point["criticality"]) >= CRITICALITY_THRESHOLD
            ),
            None,
        )
        first_detected_row_id = (
            int(first_detected["source_row_id"]) if first_detected is not None else None
        )
        early_detection_seconds = (
            (event_end_position - row_positions[first_detected_row_id])
            * int(prediction_artifact["sample_period_seconds"])
            if first_detected_row_id is not None
            else None
        )

        earliness: float | None = None
        earliness_intermediate: list[dict[str, Any]] = []
        coverage: float | None = None
        if truth.event_label == "anomaly":
            start_position = row_positions[truth.event_start_source_row_id]
            event_points = points[start_position : event_end_position + 1]
            weights = _reference_earliness_weights(len(event_points))
            total_weight = sum(weights)
            contribution = 0.0
            for point, weight in zip(event_points, weights, strict=True):
                weighted_prediction = weight * int(bool(point["binary_prediction"]))
                contribution += weighted_prediction
                earliness_intermediate.append(
                    {
                        "source_row_id": point["source_row_id"],
                        "weight": weight,
                        "binary_prediction": point["binary_prediction"],
                        "weighted_prediction": weighted_prediction,
                    }
                )
            earliness = contribution / total_weight
            coverage = _f_beta(tp=tp, fp=fp, fn=fn, beta=POINT_BETA)

        accuracy = (tp + tn) / (tp + fp + tn + fn)
        result: dict[str, Any] = {
            **common_result,
            "status": "scored",
            "unscorable_reason": None,
            "valid_point_count": len(valid_points),
            "filtered_point_count": len(points) - len(valid_points),
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "coverage_f0_5": coverage,
            "point_accuracy": accuracy,
            "earliness": earliness,
            "earliness_intermediate": earliness_intermediate,
            "max_criticality": max_criticality,
            "criticality_threshold": CRITICALITY_THRESHOLD,
            "criticality_comparison": "greater-than-or-equal",
            "event_detected": event_detected,
            "first_detected_source_row_id": first_detected_row_id,
            "early_detection_seconds": early_detection_seconds,
            "sample_period_seconds": prediction_artifact["sample_period_seconds"],
            "scored_points": scored_points,
        }
        result["event_result_sha256"] = _canonical_hash(result)
        return result


@dataclass(frozen=True, slots=True)
class EvaluationRunSpec:
    run_id: str
    purpose: str
    generalization_protocol: str
    event_ids: tuple[int, ...]
    model_id: str
    model_version: str
    created_at: str
    farm: str | None = None
    held_out_asset_id: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("run_id", self.run_id),
            ("model_id", self.model_id),
            ("model_version", self.model_version),
            ("created_at", self.created_at),
        ):
            _require_nonempty(value, field=field_name)
        if self.purpose not in RUN_PURPOSES:
            raise CareScoreError(f"unknown evaluation run purpose: {self.purpose}")
        if self.generalization_protocol not in GENERALIZATION_PROTOCOLS:
            raise CareScoreError(f"unknown generalization protocol: {self.generalization_protocol}")
        if self.generalization_protocol == DISABLED_GENERALIZATION_PROTOCOL:
            raise CareScoreError(
                "cross-farm evaluation is disabled until the canonical ontology is complete"
            )
        if not self.event_ids or len(self.event_ids) != len(set(self.event_ids)):
            raise CareScoreError("evaluation run event IDs must be non-empty and unique")
        if self.generalization_protocol == "care-event-train-prediction-v6":
            if len(self.event_ids) != 1:
                raise CareScoreError("single-event protocol requires exactly one event")
            if self.held_out_asset_id is not None:
                raise CareScoreError("single-event protocol cannot declare a held-out asset")
        if self.generalization_protocol == "within-farm-leave-one-turbine-out-v1":
            if self.farm not in {"A", "B", "C"} or not self.held_out_asset_id:
                raise CareScoreError(
                    "within-farm leave-one-turbine-out requires one farm and held-out asset"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "purpose": self.purpose,
            "generalization_protocol": self.generalization_protocol,
            "event_ids": list(self.event_ids),
            "model_id": self.model_id,
            "model_version": self.model_version,
            "created_at": self.created_at,
            "farm": self.farm,
            "held_out_asset_id": self.held_out_asset_id,
            "prediction_truth_available_to_training_or_calibration": False,
        }


@dataclass(frozen=True, slots=True)
class EvaluationFailure:
    event_id: int
    category: str
    reason: str

    def __post_init__(self) -> None:
        if self.event_id < 0:
            raise CareScoreError("failed evaluation event_id must be non-negative")
        if self.category not in {"data", "model"}:
            raise CareScoreError("evaluation failure category must be data or model")
        _require_nonempty(self.reason, field="evaluation failure reason")

    def to_result(self) -> dict[str, Any]:
        payload = {
            "event_id": self.event_id,
            "status": f"{self.category}-failure",
            "failure_reason": self.reason,
        }
        return {**payload, "event_result_sha256": _canonical_hash(payload)}


def _aggregate_results(
    results: Sequence[Mapping[str, Any]],
    predictions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    scored = [result for result in results if result["status"] == "scored"]
    unscorable = [result for result in results if result["status"] == "unscorable"]
    data_failures = [result for result in results if result["status"] == "data-failure"]
    model_failures = [result for result in results if result["status"] == "model-failure"]
    anomaly_results = [result for result in scored if result["event_label"] == "anomaly"]
    normal_results = [result for result in scored if result["event_label"] == "normal"]
    base: dict[str, Any] = {
        "requested_event_count": len(results),
        "scored_event_count": len(scored),
        "unscorable_event_count": len(unscorable),
        "data_failure_event_count": len(data_failures),
        "model_failure_event_count": len(model_failures),
        "unscorable_events": [
            {"event_id": item["event_id"], "reason": item["unscorable_reason"]}
            for item in unscorable
        ],
        "failed_events": [
            {
                "event_id": item["event_id"],
                "category": str(item["status"]).removesuffix("-failure"),
                "reason": item["failure_reason"],
            }
            for item in [*data_failures, *model_failures]
        ],
    }
    if not anomaly_results or not normal_results:
        return {
            **base,
            "status": "unscorable",
            "unscorable_reason": "requires-at-least-one-scoreable-anomaly-and-normal-event",
            "care_score": None,
        }

    average_coverage = sum(float(item["coverage_f0_5"]) for item in anomaly_results) / len(
        anomaly_results
    )
    average_accuracy = sum(float(item["point_accuracy"]) for item in normal_results) / len(
        normal_results
    )
    average_earliness = sum(float(item["earliness"]) for item in anomaly_results) / len(
        anomaly_results
    )
    event_tp = sum(bool(item["event_detected"]) for item in anomaly_results)
    event_fn = len(anomaly_results) - event_tp
    event_fp = sum(bool(item["event_detected"]) for item in normal_results)
    reliability = _f_beta(tp=event_tp, fp=event_fp, fn=event_fn, beta=EVENT_BETA)
    any_event_detected = any(bool(item["event_detected"]) for item in scored)
    if not any_event_detected:
        special_branch = "no-event-detected"
        care_score = 0.0
    elif average_accuracy <= 0.5:
        special_branch = "normal-accuracy-at-or-below-0.5"
        care_score = average_accuracy
    else:
        special_branch = "weighted-components"
        care_score = (
            average_coverage * COMPONENT_WEIGHTS["coverage"]
            + average_accuracy * COMPONENT_WEIGHTS["accuracy"]
            + reliability * COMPONENT_WEIGHTS["reliability"]
            + average_earliness * COMPONENT_WEIGHTS["earliness"]
        ) / sum(COMPONENT_WEIGHTS.values())

    valid_normal_hours = sum(
        int(item["valid_point_count"]) * int(item["sample_period_seconds"]) / 3600
        for item in normal_results
    )
    predictions_by_event = {int(item["event_id"]): item for item in predictions}
    prediction_event_days = sum(
        int(predictions_by_event[int(item["event_id"])]["point_count"])
        * int(item["sample_period_seconds"])
        / 86400
        for item in normal_results
    )
    false_alarm_events = event_fp
    point_tp = sum(int(item["tp"]) for item in scored)
    point_fp = sum(int(item["fp"]) for item in scored)
    point_fn = sum(int(item["fn"]) for item in scored)
    point_precision = point_tp / (point_tp + point_fp) if point_tp + point_fp else 0.0
    point_recall = point_tp / (point_tp + point_fn) if point_tp + point_fn else 0.0
    score_truth_pairs = [
        (float(point["anomaly_score"]), bool(point["ground_truth"]))
        for item in scored
        for point in item["scored_points"]
    ]
    early_detection_values = [
        float(item["early_detection_seconds"])
        for item in anomaly_results
        if item["early_detection_seconds"] is not None
    ]
    return {
        **base,
        "status": "scored",
        "unscorable_reason": None,
        "care_score": care_score,
        "special_branch": special_branch,
        "components": {
            "average_coverage_f0_5": average_coverage,
            "average_normal_accuracy": average_accuracy,
            "reliability_event_f0_5": reliability,
            "average_earliness": average_earliness,
            "weights": dict(COMPONENT_WEIGHTS),
        },
        "event_metrics": {
            "anomaly_event_count": len(anomaly_results),
            "normal_event_count": len(normal_results),
            "detected_anomaly_event_count": event_tp,
            "false_alarm_normal_event_count": false_alarm_events,
            "event_detection_rate": event_tp / len(anomaly_results),
            "normal_event_false_positive_rate": false_alarm_events / len(normal_results),
            "valid_normal_hours": valid_normal_hours,
            "false_alarms_per_1000_valid_normal_hours": (
                false_alarm_events / valid_normal_hours * 1000 if valid_normal_hours else None
            ),
            "normal_prediction_event_days": prediction_event_days,
            "false_alarms_per_prediction_event_day": (
                false_alarm_events / prediction_event_days if prediction_event_days else None
            ),
            "false_alarms_per_turbine_year": None,
            "turbine_year_metric_status": "disabled-no-deduplicated-exposure-proof",
        },
        "point_metrics": {
            "precision": point_precision,
            "recall": point_recall,
            "f0_5": _f_beta(tp=point_tp, fp=point_fp, fn=point_fn, beta=POINT_BETA),
            "pr_auc_average_precision": _average_precision(score_truth_pairs),
        },
        "early_detection_seconds": {
            "median": _quantile(early_detection_values, 0.5),
            "p25": _quantile(early_detection_values, 0.25),
            "p75": _quantile(early_detection_values, 0.75),
        },
        "rounding": "none",
    }


def aggregate_evaluation_results(
    results: Sequence[Mapping[str, Any]],
    predictions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate already evaluated events using the frozen CARE v6 formula."""

    return _aggregate_results(results, predictions)


def build_evaluation_artifact(
    run: EvaluationRunSpec,
    evaluator: FinalCareEvaluator,
    predictions: Sequence[Mapping[str, Any]],
    *,
    protocol: Mapping[str, Any] | None = None,
    failures: Sequence[EvaluationFailure] = (),
    approval_lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    protocol_value = dict(protocol or build_score_protocol())
    verify_score_protocol(protocol_value)
    if len(predictions) + len(failures) != len(run.event_ids):
        raise CareScoreError("evaluation run outcomes do not match event IDs")
    by_event: dict[int, Mapping[str, Any]] = {}
    for prediction in predictions:
        verify_prediction_artifact(prediction)
        event_id = int(prediction["event_id"])
        if event_id in by_event:
            raise CareScoreError("evaluation run contains duplicate prediction events")
        by_event[event_id] = prediction
        if (
            prediction["model_id"] != run.model_id
            or prediction["model_version"] != run.model_version
        ):
            raise CareScoreError("evaluation run model identity does not match prediction artifact")
        if run.generalization_protocol == "within-farm-leave-one-turbine-out-v1":
            if prediction["farm"] != run.farm:
                raise CareScoreError("within-farm run contains a cross-farm prediction")
            if prediction["source_asset_id"] != run.held_out_asset_id:
                raise CareScoreError("within-farm run contains a non-held-out asset prediction")
    failures_by_event = {failure.event_id: failure for failure in failures}
    if len(failures_by_event) != len(failures) or set(by_event).intersection(failures_by_event):
        raise CareScoreError("evaluation run contains duplicate event outcomes")
    if set(by_event).union(failures_by_event) != set(run.event_ids):
        raise CareScoreError("evaluation run event IDs do not match event outcomes")

    ordered_predictions = [by_event[event_id] for event_id in run.event_ids if event_id in by_event]
    results = [
        (
            evaluator.evaluate_event(by_event[event_id])
            if event_id in by_event
            else failures_by_event[event_id].to_result()
        )
        for event_id in run.event_ids
    ]
    truth_records = [
        {
            "event_id": result["event_id"],
            "farm": result["farm"],
            "source_asset_id": result["source_asset_id"],
            "event_label": result["event_label"],
            "event_start_source_row_id": result.get("event_start_source_row_id"),
            "event_end_source_row_id": result.get("event_end_source_row_id"),
            "failure_type": result.get("failure_type"),
        }
        for result in results
        if result["status"] in {"scored", "unscorable"}
    ]
    payload: dict[str, Any] = {
        "schema_version": EVALUATION_ARTIFACT_SCHEMA_VERSION,
        "score_protocol": protocol_value,
        "run": run.to_dict(),
        "predictions": ordered_predictions,
        "failures": [
            {
                "event_id": failure.event_id,
                "category": failure.category,
                "reason": failure.reason,
            }
            for failure in failures
        ],
        "truth_domain": {
            "accessed_by": "FinalCareEvaluator",
            "available_to_training_or_calibration": False,
            "records": truth_records,
        },
        "event_results": results,
        "summary": _aggregate_results(results, ordered_predictions),
    }
    if approval_lineage is not None:
        payload["care_approval"] = dict(approval_lineage)
    return {**payload, "evaluation_artifact_sha256": _canonical_hash(payload)}


def _verify_evaluation_artifact_envelope(artifact: Mapping[str, Any]) -> None:
    actual = artifact.get("evaluation_artifact_sha256")
    if not isinstance(actual, str):
        raise CareScoreError("evaluation artifact is missing evaluation_artifact_sha256")
    unsigned = {
        key: value for key, value in artifact.items() if key != "evaluation_artifact_sha256"
    }
    if _canonical_hash(unsigned) != actual:
        raise CareScoreError("evaluation artifact hash mismatch")
    if artifact.get("schema_version") != EVALUATION_ARTIFACT_SCHEMA_VERSION:
        raise CareScoreError("unsupported evaluation artifact schema")
    protocol = artifact.get("score_protocol")
    if not isinstance(protocol, Mapping):
        raise CareScoreError("evaluation artifact protocol is malformed")
    verify_score_protocol(protocol)
    predictions = artifact.get("predictions")
    if not isinstance(predictions, list):
        raise CareScoreError("evaluation artifact predictions are malformed")
    for prediction in predictions:
        if not isinstance(prediction, Mapping):
            raise CareScoreError("evaluation artifact prediction is malformed")
        verify_prediction_artifact(prediction)


def verify_evaluation_artifact(artifact: Mapping[str, Any]) -> None:
    """Verify both the immutable envelope and complete score recomputation."""

    _verify_evaluation_artifact_envelope(artifact)
    recompute_evaluation_artifact(artifact)


def recompute_evaluation_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute every event and aggregate from the immutable saved artifact."""

    _verify_evaluation_artifact_envelope(artifact)
    truth_domain = artifact.get("truth_domain")
    run_raw = artifact.get("run")
    predictions = artifact.get("predictions")
    protocol = artifact.get("score_protocol")
    if (
        not isinstance(truth_domain, Mapping)
        or not isinstance(run_raw, Mapping)
        or not isinstance(predictions, list)
        or not isinstance(protocol, Mapping)
    ):
        raise CareScoreError("evaluation artifact recomputation inputs are malformed")
    if (
        truth_domain.get("accessed_by") != "FinalCareEvaluator"
        or truth_domain.get("available_to_training_or_calibration") is not False
    ):
        raise CareScoreError("evaluation artifact truth-domain boundary is invalid")
    records = truth_domain.get("records")
    if not isinstance(records, list):
        raise CareScoreError("evaluation artifact truth records are malformed")
    truths = [
        CareEventTruth(
            event_id=int(record["event_id"]),
            farm=str(record["farm"]),
            source_asset_id=str(record["source_asset_id"]),
            event_label=str(record["event_label"]),
            event_start_source_row_id=int(record["event_start_source_row_id"]),
            event_end_source_row_id=int(record["event_end_source_row_id"]),
            failure_type=(
                str(record["failure_type"]) if record.get("failure_type") is not None else None
            ),
        )
        for record in records
        if isinstance(record, Mapping)
    ]
    if len(truths) != len(records):
        raise CareScoreError("evaluation artifact contains a malformed truth record")
    run = EvaluationRunSpec(
        run_id=str(run_raw["run_id"]),
        purpose=str(run_raw["purpose"]),
        generalization_protocol=str(run_raw["generalization_protocol"]),
        event_ids=tuple(int(event_id) for event_id in run_raw["event_ids"]),
        model_id=str(run_raw["model_id"]),
        model_version=str(run_raw["model_version"]),
        created_at=str(run_raw["created_at"]),
        farm=str(run_raw["farm"]) if run_raw.get("farm") is not None else None,
        held_out_asset_id=(
            str(run_raw["held_out_asset_id"])
            if run_raw.get("held_out_asset_id") is not None
            else None
        ),
    )
    failures_raw = artifact.get("failures")
    if not isinstance(failures_raw, list):
        raise CareScoreError("evaluation artifact failures are malformed")
    failures = [
        EvaluationFailure(
            event_id=int(failure["event_id"]),
            category=str(failure["category"]),
            reason=str(failure["reason"]),
        )
        for failure in failures_raw
        if isinstance(failure, Mapping)
    ]
    if len(failures) != len(failures_raw):
        raise CareScoreError("evaluation artifact contains a malformed failure")
    rebuilt = build_evaluation_artifact(
        run,
        FinalCareEvaluator(PredictionTruthVault(truths)),
        predictions,
        protocol=protocol,
        failures=failures,
        approval_lineage=(
            artifact.get("care_approval")
            if isinstance(artifact.get("care_approval"), Mapping)
            else None
        ),
    )
    if _canonical_json_bytes(rebuilt) != _canonical_json_bytes(artifact):
        raise CareScoreError("evaluation artifact cannot be reproduced from its saved inputs")
    return rebuilt


def write_score_protocol(path: Path, protocol: Mapping[str, Any] | None = None) -> None:
    value = dict(protocol or build_score_protocol())
    verify_score_protocol(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )


def write_evaluation_artifact(path: Path, artifact: Mapping[str, Any]) -> None:
    verify_evaluation_artifact(artifact)
    run = artifact.get("run")
    if not isinstance(run, Mapping):
        raise CareScoreError("evaluation artifact run is malformed")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    if run.get("purpose") == "final-holdout":
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        except FileExistsError as exc:
            raise CareScoreError(
                "final-holdout evaluation artifacts cannot be overwritten"
            ) from exc
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        return
    path.write_bytes(payload)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write the immutable care-score-v6 protocol")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    write_score_protocol(args.output)
    print(json.dumps({"output": str(args.output), **build_score_protocol()["authority"]}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
