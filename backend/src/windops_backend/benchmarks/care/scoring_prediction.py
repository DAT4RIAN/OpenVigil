from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
