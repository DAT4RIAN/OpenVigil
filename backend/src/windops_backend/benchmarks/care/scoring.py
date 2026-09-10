from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from windops_backend.benchmarks.care.contract import DATASET_ID, DATASET_VERSION
from windops_backend.benchmarks.care.quality import (
    FEATURE_SET_VERSION,
    QUALITY_RULE_VERSION,
    STATUS_CORROBORATION_RULE_ID,
    STATUS_RULE_VERSION,
    STATUS_SUSTAINED_DISAGREEMENT_MIN_ROWS,
    evaluate_status_point,
    status_evidence_policy,
)

SCORE_PROTOCOL_VERSION = "care-score-v6"
SCORE_PROTOCOL_SCHEMA_VERSION = "care-score-v6-protocol-v1"
PREDICTION_ARTIFACT_SCHEMA_VERSION = "care-v6-event-prediction-v2"
EVALUATION_ARTIFACT_SCHEMA_VERSION = "care-v6-evaluation-v1"
THRESHOLD_POLICY_SCHEMA_VERSION = "care-v6-threshold-policy-v1"

POINT_BETA = 0.5
EVENT_BETA = 0.5
CRITICALITY_THRESHOLD = 72
EARLINESS_START_NUMERATOR = 1
EARLINESS_START_DENOMINATOR = 4
COMPONENT_WEIGHTS = {
    "coverage": 1.0,
    "accuracy": 2.0,
    "reliability": 1.0,
    "earliness": 1.0,
}
RUN_PURPOSES = ("development", "tuning", "final-holdout")
CALIBRATION_SPLITS = ("train", "train-validation")
MODEL_SELECTION_SPLITS = (*CALIBRATION_SPLITS, "not-used")
GENERALIZATION_PROTOCOLS = (
    "care-event-train-prediction-v6",
    "within-farm-leave-one-turbine-out-v1",
    "cross-farm-ontology-v1",
)
DISABLED_GENERALIZATION_PROTOCOL = "cross-farm-ontology-v1"

PAPER_URL = "https://doi.org/10.3390/data9120138"
REFERENCE_RELEASE_URL = "https://github.com/AEFDI/EnergyFaultDetector/releases/tag/v0.6.2"
REFERENCE_COMMIT = "a338b6efb3a650536930c6e67247694071d2f63e"
REFERENCE_SCORE_SOURCE_URL = (
    "https://github.com/AEFDI/EnergyFaultDetector/blob/"
    f"{REFERENCE_COMMIT}/energy_fault_detector/evaluation/care_score.py"
)
REFERENCE_CRITICALITY_SOURCE_URL = (
    "https://github.com/AEFDI/EnergyFaultDetector/blob/"
    f"{REFERENCE_COMMIT}/energy_fault_detector/utils/analysis.py"
)
REFERENCE_SCORE_SOURCE_SHA256 = "122eaf43c5f6703b78e89a4273ad236ddb7b99f7598dcc44bc808e9476285078"
REFERENCE_CRITICALITY_SOURCE_SHA256 = (
    "2d593ef0474e5d38dd2cbca03fcf1de9f300f764c6305799c48b168481fb558e"
)
PAPER_PDF_SHA256 = "6f90430a4401deb209351988830847ed2324f29b6707c9635ec0fee4fae124d3"


class CareScoreError(ValueError):
    """Raised when a CARE scoring or no-leakage contract is violated."""


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CareScoreError("CARE score artifacts must be finite canonical JSON") from exc


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_nonempty(value: str, *, field: str) -> None:
    if not value.strip():
        raise CareScoreError(f"{field} must not be empty")


def _require_finite(value: float, *, field: str) -> None:
    if not math.isfinite(value):
        raise CareScoreError(f"{field} must be finite")


def build_score_protocol() -> dict[str, Any]:
    """Return the immutable, source-pinned care-score-v6 protocol."""

    payload: dict[str, Any] = {
        "score_protocol_version": SCORE_PROTOCOL_VERSION,
        "schema_version": SCORE_PROTOCOL_SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "authority": {
            "paper": {
                "url": PAPER_URL,
                "local_pdf_sha256": PAPER_PDF_SHA256,
                "sections": ["3.2.1", "3.2.2"],
            },
            "reference_implementation": {
                "organization": "Fraunhofer IEE / AEFDI",
                "release": "v0.6.2",
                "release_url": REFERENCE_RELEASE_URL,
                "commit": REFERENCE_COMMIT,
                "care_score_source": REFERENCE_SCORE_SOURCE_URL,
                "care_score_source_sha256": REFERENCE_SCORE_SOURCE_SHA256,
                "criticality_source": REFERENCE_CRITICALITY_SOURCE_URL,
                "criticality_source_sha256": REFERENCE_CRITICALITY_SOURCE_SHA256,
            },
            "conflict_precedence": (
                "the pinned executable reference implementation controls ambiguous paper prose"
            ),
        },
        "point_prediction": {
            "comparison": "anomaly_score > threshold",
            "threshold_equal_is_anomaly": False,
            "threshold_policy_schema_version": THRESHOLD_POLICY_SCHEMA_VERSION,
        },
        "coverage": {
            "metric": "pointwise-f-beta",
            "beta": POINT_BETA,
            "scope": "valid prediction points; anomaly events only",
            "zero_division": 0.0,
        },
        "accuracy": {
            "metric": "pointwise-accuracy",
            "scope": "valid prediction points; normal events only",
        },
        "criticality": {
            "initial": 0,
            "minimum": 0,
            "maximum": 1000,
            "valid_anomaly_delta": 1,
            "valid_normal_delta": -1,
            "invalid_status_delta": 0,
            "event_threshold": CRITICALITY_THRESHOLD,
            "event_comparison": "max_criticality >= 72",
            "threshold_equal_detected": True,
            "evaluation_end": "inclusive event_end",
        },
        "reliability": {
            "metric": "eventwise-f-beta",
            "beta": EVENT_BETA,
            "zero_division": 0.0,
        },
        "earliness": {
            "metric": "reference-weighted-score",
            "start_of_descend": [
                EARLINESS_START_NUMERATOR,
                EARLINESS_START_DENOMINATOR,
            ],
            "scope": "all binary predictions in inclusive anomaly event window",
            "status_filter": "not applied, matching pinned reference implementation",
            "sampling": (
                "reproduce numpy.linspace(0, denominator, event_length * denominator) "
                "then take every denominator-th weight"
            ),
        },
        "aggregation": {
            "event_component_aggregation": "arithmetic mean over scoreable events",
            "weights": dict(COMPONENT_WEIGHTS),
            "order": [
                "no-event-detection => 0",
                "average-normal-accuracy <= 0.5 => accuracy",
                "weighted component mean",
            ],
            "accuracy_boundary": "<= 0.5",
            "rounding": "no intermediate or identity rounding; presentation rounding is external",
        },
        "status_filter": {
            "version": STATUS_RULE_VERSION,
            "corroboration_rule_id": STATUS_CORROBORATION_RULE_ID,
            "minimum_sustained_disagreement_rows": (STATUS_SUSTAINED_DISAGREEMENT_MIN_ROWS),
            "A_prediction": "retain all statuses (CARE v6 exception)",
            "B_C": (
                "retain trusted and short/uncorroborated disagreement; filter sustained "
                "corroborated disagreement"
            ),
            "point_metrics": "use valid points only",
            "criticality": "freeze on invalid points",
        },
        "truth_boundary": {
            "training_and_calibration_splits": list(CALIBRATION_SPLITS),
            "model_selection_fields": [
                "feature_selection_split",
                "early_stopping_split",
                "hyperparameter_selection_split",
            ],
            "not_used_marker": "not-used",
            "prediction_truth_consumer": "FinalCareEvaluator only",
            "prediction_truth_for_threshold_or_tuning": False,
        },
        "run_purposes": list(RUN_PURPOSES),
        "generalization_protocols": {
            "care-event-train-prediction-v6": "enabled; exactly one event",
            "within-farm-leave-one-turbine-out-v1": (
                "enabled; exactly one farm and an explicit held-out asset"
            ),
            DISABLED_GENERALIZATION_PROTOCOL: (
                "disabled until canonical feature ontology and human review are complete"
            ),
        },
        "false_alarm_metrics": {
            "normal_event_false_positive_rate": True,
            "false_alarms_per_1000_valid_normal_hours": True,
            "false_alarms_per_prediction_event_day": True,
            "false_alarms_per_turbine_year": "disabled-no-deduplicated-exposure-proof",
        },
        "golden_vectors": {
            "score_threshold": {
                "threshold": 0.5,
                "scores": [0.49, 0.5, 0.51],
                "binary_predictions": [False, False, True],
            },
            "criticality_boundary": {
                "max_criticality": [71, 72, 73],
                "event_detected": [False, True, True],
            },
            "criticality_status_freeze": {
                "binary_predictions": [True, True, True, True],
                "valid_point_mask": [True, False, False, True],
                "criticality": [1, 1, 1, 2],
            },
            "earliness_four_points": {
                "positive_prediction_indexes": [0, 2, 3],
                "scores": [
                    0.3488372093023256,
                    0.21705426356589147,
                    0.09302325581395347,
                ],
            },
            "special_branches": {
                "no_event_detected": 0.0,
                "normal_accuracy_0_4": 0.4,
                "normal_accuracy_0_5": 0.5,
            },
        },
        "paper_reference_differences": [
            (
                "paper prose says threshold is exceeded; pinned implementation uses inclusive "
                "max_criticality >= threshold"
            ),
            (
                "paper pseudocode status boolean conflicts with its prose; pinned implementation "
                "increments/decrements only during normal operation and freezes otherwise"
            ),
            (
                "paper prose describes a half-event earliness plateau; pinned implementation "
                "defaults to a one-quarter descent start"
            ),
            ("paper equation uses Accuracy < 0.5; pinned implementation uses Accuracy <= 0.5"),
        ],
    }
    return {**payload, "score_protocol_sha256": _canonical_hash(payload)}


def verify_score_protocol(protocol: Mapping[str, Any]) -> None:
    actual = protocol.get("score_protocol_sha256")
    if not isinstance(actual, str):
        raise CareScoreError("CARE score protocol is missing score_protocol_sha256")
    unsigned = {key: value for key, value in protocol.items() if key != "score_protocol_sha256"}
    expected = _canonical_hash(unsigned)
    if actual != expected:
        raise CareScoreError(
            f"CARE score protocol hash mismatch: expected {expected}, got {actual}"
        )
    if protocol.get("score_protocol_version") != SCORE_PROTOCOL_VERSION:
        raise CareScoreError("unsupported CARE score protocol version")
    frozen_hash = build_score_protocol()["score_protocol_sha256"]
    if actual != frozen_hash:
        raise CareScoreError(
            f"CARE score protocol does not match frozen {SCORE_PROTOCOL_VERSION} identity"
        )


@dataclass(frozen=True, slots=True)
class CalibrationInput:
    """Label-free calibration input that cannot carry prediction truth."""

    anomaly_scores: tuple[float, ...]
    source_split: str
    source_run_id: str

    def __post_init__(self) -> None:
        if self.source_split not in CALIBRATION_SPLITS:
            raise CareScoreError(
                "threshold calibration may only read train or train-validation scores"
            )
        _require_nonempty(self.source_run_id, field="source_run_id")
        if not self.anomaly_scores:
            raise CareScoreError("calibration input must contain at least one score")
        for score in self.anomaly_scores:
            _require_finite(score, field="calibration anomaly score")


@dataclass(frozen=True, slots=True)
class ThresholdPolicy:
    value: float
    version: str
    calibration_split: str
    calibration_run_id: str
    strategy: str

    def __post_init__(self) -> None:
        _require_finite(self.value, field="threshold")
        _require_nonempty(self.version, field="threshold policy version")
        _require_nonempty(self.calibration_run_id, field="calibration run ID")
        _require_nonempty(self.strategy, field="threshold strategy")
        if self.calibration_split not in CALIBRATION_SPLITS:
            raise CareScoreError(
                "threshold policy provenance may not reference prediction or prediction truth"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": THRESHOLD_POLICY_SCHEMA_VERSION,
            "value": self.value,
            "version": self.version,
            "comparison": "strict-greater-than",
            "calibration_split": self.calibration_split,
            "calibration_run_id": self.calibration_run_id,
            "strategy": self.strategy,
            "prediction_truth_used": False,
        }
        return {**payload, "threshold_policy_sha256": _canonical_hash(payload)}


def fixed_threshold_policy(
    calibration: CalibrationInput,
    *,
    value: float,
    version: str,
    strategy: str = "fixed-from-train-calibration",
) -> ThresholdPolicy:
    """Create a policy without accepting any prediction labels or event truth."""

    return ThresholdPolicy(
        value=value,
        version=version,
        calibration_split=calibration.source_split,
        calibration_run_id=calibration.source_run_id,
        strategy=strategy,
    )


@dataclass(frozen=True, slots=True)
class ModelSelectionProvenance:
    training_run_id: str
    feature_selection_split: str
    early_stopping_split: str
    hyperparameter_selection_split: str

    def __post_init__(self) -> None:
        _require_nonempty(self.training_run_id, field="model-selection training run ID")
        for field_name, value in (
            ("feature_selection_split", self.feature_selection_split),
            ("early_stopping_split", self.early_stopping_split),
            ("hyperparameter_selection_split", self.hyperparameter_selection_split),
        ):
            if value not in MODEL_SELECTION_SPLITS:
                raise CareScoreError(
                    f"{field_name} may only use train, train-validation, or not-used"
                )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "training_run_id": self.training_run_id,
            "feature_selection_split": self.feature_selection_split,
            "early_stopping_split": self.early_stopping_split,
            "hyperparameter_selection_split": self.hyperparameter_selection_split,
            "prediction_truth_used": False,
        }
        return {**payload, "model_selection_sha256": _canonical_hash(payload)}


@dataclass(frozen=True, slots=True)
class PredictionPoint:
    source_row_id: int
    source_timestamp: str
    anonymous_time: str
    anomaly_score: float
    status_id: str
    disagreement_run_length: int = 1
    corroborated_by_signal: bool = False
    corroboration_signal_count: int = 0
    corroboration_finite_signal_count: int = 0
    corroboration_inactive_or_invalid_signal_count: int = 0

    def __post_init__(self) -> None:
        if self.source_row_id < 0:
            raise CareScoreError("source_row_id must be non-negative")
        _require_nonempty(self.source_timestamp, field="source timestamp")
        _require_nonempty(self.anonymous_time, field="anonymous time")
        _require_finite(self.anomaly_score, field="anomaly score")
        _require_nonempty(self.status_id, field="status ID")
        if self.disagreement_run_length < 1:
            raise CareScoreError("disagreement_run_length must be positive")
        counts = (
            self.corroboration_signal_count,
            self.corroboration_finite_signal_count,
            self.corroboration_inactive_or_invalid_signal_count,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts
        ):
            raise CareScoreError("status corroboration counts must be non-negative integers")
        if (
            self.corroboration_finite_signal_count > self.corroboration_signal_count
            or self.corroboration_inactive_or_invalid_signal_count > self.corroboration_signal_count
        ):
            raise CareScoreError("status corroboration counts are inconsistent")


@dataclass(frozen=True, slots=True)
class PredictionBatch:
    event_id: int
    farm: str
    source_asset_id: str
    points: tuple[PredictionPoint, ...]
    model_id: str
    model_version: str
    deployment_id: str | None
    feature_set_version: str
    feature_set_sha256: str
    quality_rule_version: str
    quality_contract_sha256: str
    model_selection_provenance: ModelSelectionProvenance
    sample_period_seconds: int = 600
    dataset_version: str = DATASET_VERSION
    source_split: str = "prediction"

    def __post_init__(self) -> None:
        if self.event_id < 0:
            raise CareScoreError("event_id must be non-negative")
        if self.farm not in {"A", "B", "C"}:
            raise CareScoreError(f"unknown CARE farm: {self.farm}")
        if self.dataset_version != DATASET_VERSION:
            raise CareScoreError(f"expected CARE {DATASET_VERSION}, got {self.dataset_version}")
        if self.source_split != "prediction":
            raise CareScoreError("prediction batches must come only from the prediction split")
        if not self.points:
            raise CareScoreError("prediction batch must contain at least one point")
        if self.sample_period_seconds <= 0:
            raise CareScoreError("sample_period_seconds must be positive")
        for field_name, value in (
            ("source_asset_id", self.source_asset_id),
            ("model_id", self.model_id),
            ("model_version", self.model_version),
            ("feature_set_version", self.feature_set_version),
            ("feature_set_sha256", self.feature_set_sha256),
            ("quality_rule_version", self.quality_rule_version),
            ("quality_contract_sha256", self.quality_contract_sha256),
        ):
            _require_nonempty(value, field=field_name)
        row_ids = [point.source_row_id for point in self.points]
        if row_ids != sorted(row_ids) or len(row_ids) != len(set(row_ids)):
            raise CareScoreError(
                "prediction points must have unique increasing source_row_id values"
            )


def _verify_threshold_policy(policy: Mapping[str, Any]) -> None:
    actual = policy.get("threshold_policy_sha256")
    if not isinstance(actual, str):
        raise CareScoreError("threshold policy is missing threshold_policy_sha256")
    unsigned = {key: value for key, value in policy.items() if key != "threshold_policy_sha256"}
    if _canonical_hash(unsigned) != actual:
        raise CareScoreError("threshold policy hash mismatch")
    if policy.get("schema_version") != THRESHOLD_POLICY_SCHEMA_VERSION:
        raise CareScoreError("unsupported threshold policy schema")
    if policy.get("comparison") != "strict-greater-than":
        raise CareScoreError("care-score-v6 requires strict score > threshold comparison")
    if policy.get("calibration_split") not in CALIBRATION_SPLITS:
        raise CareScoreError("threshold policy has forbidden prediction provenance")
    if policy.get("prediction_truth_used") is not False:
        raise CareScoreError("threshold policy must prove prediction truth was not used")
    for field_name in ("version", "calibration_run_id", "strategy"):
        value = policy.get(field_name)
        if not isinstance(value, str):
            raise CareScoreError(f"threshold policy {field_name} must be a string")
        _require_nonempty(value, field=f"threshold policy {field_name}")
    value = policy.get("value")
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise CareScoreError("threshold policy value must be numeric")
    _require_finite(float(value), field="threshold")


def build_prediction_artifact(
    batch: PredictionBatch,
    threshold_policy: ThresholdPolicy,
    *,
    trusted_status_ids: Sequence[str],
    status_signal_columns: Sequence[str] = (),
    license_metadata: Mapping[str, Any] | None = None,
    approval_lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a truth-free prediction artifact with replayable point intermediates."""

    if batch.feature_set_version != FEATURE_SET_VERSION:
        raise CareScoreError("prediction batch feature-set version does not match CARE v6")
    if batch.quality_rule_version != QUALITY_RULE_VERSION:
        raise CareScoreError("prediction batch quality-rule version does not match CARE v6")
    trusted = tuple(sorted(set(trusted_status_ids)))
    if not trusted:
        raise CareScoreError("prediction scoring requires an explicit trusted-status allowlist")
    try:
        status_policy = status_evidence_policy(batch.farm, status_signal_columns)
    except ValueError as exc:
        raise CareScoreError(str(exc)) from exc

    criticality = 0
    points: list[dict[str, Any]] = []
    for point in batch.points:
        if point.corroboration_signal_count != len(status_signal_columns):
            raise CareScoreError(
                "status corroboration count does not match the frozen signal columns"
            )
        expected_corroborated = (
            batch.farm in {"B", "C"}
            and point.status_id not in trusted
            and point.corroboration_signal_count > 0
            and point.corroboration_inactive_or_invalid_signal_count
            == point.corroboration_signal_count
        )
        if point.corroborated_by_signal is not expected_corroborated:
            raise CareScoreError("status corroboration flag does not match its evidence counts")
        decision = evaluate_status_point(
            farm=batch.farm,
            split="prediction",
            status_id=point.status_id,
            trusted_status_ids=trusted,
            disagreement_run_length=point.disagreement_run_length,
            corroborated_by_signal=point.corroborated_by_signal,
        )
        binary_prediction = point.anomaly_score > threshold_policy.value
        if decision.model_usable:
            criticality = (
                min(1000, criticality + 1) if binary_prediction else max(0, criticality - 1)
            )
        points.append(
            {
                "source_row_id": point.source_row_id,
                "source_timestamp": point.source_timestamp,
                "anonymous_time": point.anonymous_time,
                "anomaly_score": point.anomaly_score,
                "binary_prediction": binary_prediction,
                "valid_point_mask": decision.model_usable,
                "status_id": point.status_id,
                "status_rule_version": decision.rule_version,
                "status_reason": decision.reason,
                "status_confidence": decision.confidence,
                "disagreement_run_length": point.disagreement_run_length,
                "corroborated_by_signal": point.corroborated_by_signal,
                "corroboration_signal_count": point.corroboration_signal_count,
                "corroboration_finite_signal_count": (point.corroboration_finite_signal_count),
                "corroboration_inactive_or_invalid_signal_count": (
                    point.corroboration_inactive_or_invalid_signal_count
                ),
                "corroboration_rule_id": STATUS_CORROBORATION_RULE_ID,
                "criticality": criticality,
            }
        )

    payload: dict[str, Any] = {
        "schema_version": PREDICTION_ARTIFACT_SCHEMA_VERSION,
        "score_protocol_version": SCORE_PROTOCOL_VERSION,
        "dataset_id": DATASET_ID,
        "dataset_version": batch.dataset_version,
        "event_id": batch.event_id,
        "farm": batch.farm,
        "source_asset_id": batch.source_asset_id,
        "source_split": batch.source_split,
        "sample_period_seconds": batch.sample_period_seconds,
        "model_id": batch.model_id,
        "model_version": batch.model_version,
        "deployment_id": batch.deployment_id,
        "feature_set_version": batch.feature_set_version,
        "feature_set_sha256": batch.feature_set_sha256,
        "quality_rule_version": batch.quality_rule_version,
        "quality_contract_sha256": batch.quality_contract_sha256,
        "model_selection_provenance": batch.model_selection_provenance.to_dict(),
        "status_rule_version": STATUS_RULE_VERSION,
        "status_evidence_policy": status_policy,
        "trusted_status_ids": list(trusted),
        "threshold_policy": threshold_policy.to_dict(),
        "point_count": len(points),
        "valid_point_count": sum(bool(point["valid_point_mask"]) for point in points),
        "points": points,
        "prediction_truth_present": False,
    }
    if license_metadata is not None:
        payload["license"] = dict(license_metadata)
    if approval_lineage is not None:
        payload["care_approval"] = dict(approval_lineage)
    return {**payload, "prediction_artifact_sha256": _canonical_hash(payload)}


def verify_prediction_artifact(artifact: Mapping[str, Any]) -> None:
    actual = artifact.get("prediction_artifact_sha256")
    if not isinstance(actual, str):
        raise CareScoreError("prediction artifact is missing prediction_artifact_sha256")
    unsigned = {
        key: value for key, value in artifact.items() if key != "prediction_artifact_sha256"
    }
    if _canonical_hash(unsigned) != actual:
        raise CareScoreError("prediction artifact hash mismatch")
    if artifact.get("schema_version") != PREDICTION_ARTIFACT_SCHEMA_VERSION:
        raise CareScoreError("unsupported prediction artifact schema")
    if artifact.get("score_protocol_version") != SCORE_PROTOCOL_VERSION:
        raise CareScoreError("prediction artifact has the wrong score protocol")
    if (
        artifact.get("dataset_id") != DATASET_ID
        or artifact.get("dataset_version") != DATASET_VERSION
    ):
        raise CareScoreError("prediction artifact has the wrong CARE dataset identity")
    if artifact.get("source_split") != "prediction":
        raise CareScoreError("prediction artifact has a non-prediction source split")
    if artifact.get("prediction_truth_present") is not False:
        raise CareScoreError("prediction artifacts must not contain prediction truth")
    forbidden_truth_fields = {"ground_truth", "event_label", "event_description", "failure_type"}
    if forbidden_truth_fields.intersection(artifact):
        raise CareScoreError("prediction artifact contains a forbidden truth field")

    policy = artifact.get("threshold_policy")
    if not isinstance(policy, Mapping):
        raise CareScoreError("prediction artifact threshold policy is malformed")
    _verify_threshold_policy(policy)
    threshold = float(policy["value"])
    model_selection = artifact.get("model_selection_provenance")
    if not isinstance(model_selection, Mapping):
        raise CareScoreError("prediction artifact model-selection provenance is malformed")
    model_selection_hash = model_selection.get("model_selection_sha256")
    if not isinstance(model_selection_hash, str):
        raise CareScoreError("model-selection provenance hash is missing")
    unsigned_model_selection = {
        key: value for key, value in model_selection.items() if key != "model_selection_sha256"
    }
    if _canonical_hash(unsigned_model_selection) != model_selection_hash:
        raise CareScoreError("model-selection provenance hash mismatch")
    for field_name in (
        "feature_selection_split",
        "early_stopping_split",
        "hyperparameter_selection_split",
    ):
        if model_selection.get(field_name) not in MODEL_SELECTION_SPLITS:
            raise CareScoreError(f"model-selection provenance has forbidden {field_name}")
    if model_selection.get("prediction_truth_used") is not False:
        raise CareScoreError("model selection must prove prediction truth was not used")
    training_run_id = model_selection.get("training_run_id")
    if not isinstance(training_run_id, str):
        raise CareScoreError("model-selection training run ID must be a string")
    _require_nonempty(training_run_id, field="model-selection training run ID")
    for field_name, expected_value in (
        ("feature_set_version", FEATURE_SET_VERSION),
        ("quality_rule_version", QUALITY_RULE_VERSION),
        ("status_rule_version", STATUS_RULE_VERSION),
    ):
        if artifact.get(field_name) != expected_value:
            raise CareScoreError(f"prediction artifact has the wrong {field_name}")
    for field_name in (
        "source_asset_id",
        "model_id",
        "model_version",
        "feature_set_sha256",
        "quality_contract_sha256",
    ):
        value = artifact.get(field_name)
        if not isinstance(value, str):
            raise CareScoreError(f"prediction artifact {field_name} must be a string")
        _require_nonempty(value, field=f"prediction artifact {field_name}")
    sample_period = artifact.get("sample_period_seconds")
    if not isinstance(sample_period, int) or isinstance(sample_period, bool) or sample_period <= 0:
        raise CareScoreError("prediction artifact sample period must be positive")
    farm = artifact.get("farm")
    trusted_raw = artifact.get("trusted_status_ids")
    if farm not in {"A", "B", "C"} or not isinstance(trusted_raw, list):
        raise CareScoreError("prediction artifact status contract is malformed")
    trusted = tuple(str(item) for item in trusted_raw)
    if not trusted:
        raise CareScoreError("prediction artifact trusted-status allowlist is empty")
    evidence_policy = artifact.get("status_evidence_policy")
    if not isinstance(evidence_policy, Mapping):
        raise CareScoreError("prediction artifact status evidence policy is missing")
    signal_columns = evidence_policy.get("corroboration_signal_columns")
    if not isinstance(signal_columns, list) or any(
        not isinstance(value, str) for value in signal_columns
    ):
        raise CareScoreError("prediction artifact status signal columns are malformed")
    try:
        expected_evidence_policy = status_evidence_policy(str(farm), signal_columns)
    except ValueError as exc:
        raise CareScoreError(str(exc)) from exc
    if dict(evidence_policy) != expected_evidence_policy:
        raise CareScoreError("prediction artifact status evidence policy drifted")

    points = artifact.get("points")
    if not isinstance(points, list) or not points:
        raise CareScoreError("prediction artifact points are missing")
    if artifact.get("point_count") != len(points):
        raise CareScoreError("prediction artifact point_count mismatch")

    criticality = 0
    previous_row_id = -1
    valid_count = 0
    for raw_point in points:
        if not isinstance(raw_point, Mapping):
            raise CareScoreError("prediction artifact point is malformed")
        if forbidden_truth_fields.intersection(raw_point):
            raise CareScoreError("prediction artifact point contains a forbidden truth field")
        row_id = raw_point.get("source_row_id")
        score = raw_point.get("anomaly_score")
        if (
            not isinstance(row_id, int)
            or isinstance(row_id, bool)
            or row_id <= previous_row_id
            or not isinstance(score, int | float)
            or isinstance(score, bool)
        ):
            raise CareScoreError("prediction artifact rows or scores are invalid")
        previous_row_id = row_id
        _require_finite(float(score), field="artifact anomaly score")
        expected_binary = float(score) > threshold
        if raw_point.get("binary_prediction") is not expected_binary:
            raise CareScoreError("prediction artifact binary threshold result mismatch")

        disagreement_run_length = raw_point.get("disagreement_run_length")
        if (
            not isinstance(disagreement_run_length, int)
            or isinstance(disagreement_run_length, bool)
            or disagreement_run_length < 1
        ):
            raise CareScoreError("prediction artifact disagreement run length is invalid")
        corroborated = raw_point.get("corroborated_by_signal")
        signal_count = raw_point.get("corroboration_signal_count")
        finite_signal_count = raw_point.get("corroboration_finite_signal_count")
        inactive_signal_count = raw_point.get("corroboration_inactive_or_invalid_signal_count")
        if (
            not isinstance(corroborated, bool)
            or not isinstance(signal_count, int)
            or isinstance(signal_count, bool)
            or signal_count < 0
            or not isinstance(finite_signal_count, int)
            or isinstance(finite_signal_count, bool)
            or finite_signal_count < 0
            or not isinstance(inactive_signal_count, int)
            or isinstance(inactive_signal_count, bool)
            or inactive_signal_count < 0
            or finite_signal_count > signal_count
            or inactive_signal_count > signal_count
            or signal_count != len(signal_columns)
            or raw_point.get("corroboration_rule_id") != STATUS_CORROBORATION_RULE_ID
        ):
            raise CareScoreError("prediction artifact status corroboration evidence is invalid")
        expected_corroborated = (
            farm in {"B", "C"}
            and str(raw_point.get("status_id", "")) not in trusted
            and signal_count > 0
            and inactive_signal_count == signal_count
        )
        if corroborated is not expected_corroborated:
            raise CareScoreError("prediction artifact status corroboration flag is invalid")
        decision = evaluate_status_point(
            farm=str(farm),
            split="prediction",
            status_id=str(raw_point.get("status_id", "")),
            trusted_status_ids=trusted,
            disagreement_run_length=disagreement_run_length,
            corroborated_by_signal=corroborated,
        )
        if (
            raw_point.get("valid_point_mask") is not decision.model_usable
            or raw_point.get("status_rule_version") != decision.rule_version
            or raw_point.get("status_reason") != decision.reason
            or raw_point.get("status_confidence") != decision.confidence
        ):
            raise CareScoreError("prediction artifact status decision mismatch")
        if decision.model_usable:
            valid_count += 1
            criticality = min(1000, criticality + 1) if expected_binary else max(0, criticality - 1)
        if raw_point.get("criticality") != criticality:
            raise CareScoreError("prediction artifact criticality mismatch")
    if artifact.get("valid_point_count") != valid_count:
        raise CareScoreError("prediction artifact valid_point_count mismatch")


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
