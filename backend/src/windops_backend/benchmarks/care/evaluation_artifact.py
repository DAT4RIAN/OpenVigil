from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from windops_backend.benchmarks.care.licensing import verify_care_artifact_license
from windops_backend.benchmarks.care.quality import FEATURE_SET_VERSION, QUALITY_RULE_VERSION
from windops_backend.benchmarks.care.scoring import (
    SCORE_PROTOCOL_VERSION,
    CareEventTruth,
    EvaluationFailure,
    FinalCareEvaluator,
    PredictionTruthVault,
    aggregate_evaluation_results,
    build_score_protocol,
    verify_prediction_artifact,
    verify_score_protocol,
)

OFFLINE_EVALUATION_VERSION = "care-v6-offline-evaluation-v1"
EVALUATION_SUITE_SCHEMA_VERSION = "care-v6-evaluation-suite-v1"
EVALUATION_SUITE_PROTOCOL = "care-event-train-prediction-v6-suite-v1"
COMPONENT_GENERALIZATION_PROTOCOL = "care-event-train-prediction-v6"


class CareOfflineEvaluationError(ValueError):
    """Raised when the offline evaluation boundary fails closed."""


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CareOfflineEvaluationError(
            "offline evaluation artifacts must be finite canonical JSON"
        ) from exc


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class EvaluationSuiteSpec:
    run_id: str
    purpose: str
    event_ids: tuple[int, ...]
    model_id: str
    model_version: str
    created_at: str
    farm: str = "A"
    suite_protocol: str = EVALUATION_SUITE_PROTOCOL
    component_protocol: str = COMPONENT_GENERALIZATION_PROTOCOL

    def __post_init__(self) -> None:
        if self.purpose not in {"development", "tuning", "final-holdout"}:
            raise CareOfflineEvaluationError("unknown evaluation suite purpose")
        if self.farm not in {"A", "B", "C"}:
            raise CareOfflineEvaluationError("evaluation suite farm is invalid")
        if self.suite_protocol != EVALUATION_SUITE_PROTOCOL:
            raise CareOfflineEvaluationError("evaluation suite protocol is not supported")
        if self.component_protocol != COMPONENT_GENERALIZATION_PROTOCOL:
            raise CareOfflineEvaluationError("evaluation suite component protocol is invalid")
        if len(self.event_ids) < 2 or len(self.event_ids) != len(set(self.event_ids)):
            raise CareOfflineEvaluationError(
                "evaluation suite requires at least two unique event IDs"
            )
        if not self.run_id or not self.model_id or not self.model_version:
            raise CareOfflineEvaluationError("evaluation suite identity is incomplete")
        try:
            created_at = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CareOfflineEvaluationError("evaluation suite created_at is invalid") from exc
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise CareOfflineEvaluationError("evaluation suite created_at needs a timezone")

    def to_document(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "purpose": self.purpose,
            "generalization_protocol": self.suite_protocol,
            "component_generalization_protocol": self.component_protocol,
            "event_ids": list(self.event_ids),
            "model_id": self.model_id,
            "model_version": self.model_version,
            "created_at": self.created_at,
            "farm": self.farm,
            "prediction_truth_available_to_training_or_calibration": False,
            "generalization_claim": "none-minimal-fixed-event-suite",
        }


def build_evaluation_suite_artifact(
    spec: EvaluationSuiteSpec,
    predictions: Sequence[Mapping[str, Any]],
    truths: Sequence[CareEventTruth],
    *,
    source_dataset_sha256: str,
    source_import_manifest_sha256: str,
    license_metadata: Mapping[str, Any],
    protocol: Mapping[str, Any] | None = None,
    failures: Sequence[EvaluationFailure] = (),
    approval_lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    protocol_value = dict(protocol or build_score_protocol())
    verify_score_protocol(protocol_value)
    by_event: dict[int, Mapping[str, Any]] = {}
    for prediction in predictions:
        verify_prediction_artifact(prediction)
        event_id = int(prediction["event_id"])
        if event_id in by_event:
            raise CareOfflineEvaluationError("evaluation suite has duplicate predictions")
        if (
            prediction["model_id"] != spec.model_id
            or prediction["model_version"] != spec.model_version
            or prediction["farm"] != spec.farm
        ):
            raise CareOfflineEvaluationError("evaluation suite prediction identity mismatch")
        by_event[event_id] = prediction
    failures_by_event = {failure.event_id: failure for failure in failures}
    if len(failures_by_event) != len(failures) or set(by_event).intersection(failures_by_event):
        raise CareOfflineEvaluationError("evaluation suite has duplicate event outcomes")
    if set(by_event).union(failures_by_event) != set(spec.event_ids):
        raise CareOfflineEvaluationError("evaluation suite does not account for every event")
    truth_by_event = {truth.event_id: truth for truth in truths}
    if set(truth_by_event) != set(by_event):
        raise CareOfflineEvaluationError(
            "restricted truth must exist exactly for events with predictions"
        )
    evaluator = FinalCareEvaluator(PredictionTruthVault(tuple(truths)))
    results = [
        (
            evaluator.evaluate_event(by_event[event_id])
            if event_id in by_event
            else failures_by_event[event_id].to_result()
        )
        for event_id in spec.event_ids
    ]
    ordered_predictions = [
        by_event[event_id] for event_id in spec.event_ids if event_id in by_event
    ]
    payload: dict[str, Any] = {
        "schema_version": EVALUATION_SUITE_SCHEMA_VERSION,
        "score_protocol": protocol_value,
        "run": spec.to_document(),
        "provenance": {
            "source_dataset_sha256": source_dataset_sha256,
            "source_import_manifest_sha256": source_import_manifest_sha256,
            "prediction_truth_read_after_predictions_completed": True,
            "care_approval": dict(approval_lineage) if approval_lineage is not None else None,
        },
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
            "records": [
                truth_by_event[event_id].to_dict()
                for event_id in spec.event_ids
                if event_id in truth_by_event
            ],
        },
        "event_results": results,
        "summary": aggregate_evaluation_results(results, ordered_predictions),
        "license": dict(license_metadata),
    }
    return {**payload, "evaluation_artifact_sha256": _canonical_hash(payload)}


def verify_evaluation_suite_artifact(artifact: Mapping[str, Any]) -> None:
    actual = artifact.get("evaluation_artifact_sha256")
    unsigned = {
        key: value for key, value in artifact.items() if key != "evaluation_artifact_sha256"
    }
    if (
        not isinstance(actual, str)
        or _canonical_hash(unsigned) != actual
        or artifact.get("schema_version") != EVALUATION_SUITE_SCHEMA_VERSION
    ):
        raise CareOfflineEvaluationError("evaluation suite hash or schema is invalid")
    run = artifact.get("run")
    provenance = artifact.get("provenance")
    predictions = artifact.get("predictions")
    failures_raw = artifact.get("failures")
    truth_domain = artifact.get("truth_domain")
    license_metadata = artifact.get("license")
    protocol = artifact.get("score_protocol")
    if (
        not isinstance(run, Mapping)
        or not isinstance(provenance, Mapping)
        or not isinstance(truth_domain, Mapping)
        or not isinstance(license_metadata, Mapping)
        or not isinstance(protocol, Mapping)
        or not isinstance(predictions, list)
        or not isinstance(failures_raw, list)
    ):
        raise CareOfflineEvaluationError("evaluation suite structure is malformed")
    spec = EvaluationSuiteSpec(
        run_id=str(run["run_id"]),
        purpose=str(run["purpose"]),
        event_ids=tuple(int(event_id) for event_id in run["event_ids"]),
        model_id=str(run["model_id"]),
        model_version=str(run["model_version"]),
        created_at=str(run["created_at"]),
        farm=str(run["farm"]),
        suite_protocol=str(run["generalization_protocol"]),
        component_protocol=str(run["component_generalization_protocol"]),
    )
    if (
        run.get("prediction_truth_available_to_training_or_calibration") is not False
        or run.get("generalization_claim") != "none-minimal-fixed-event-suite"
        or provenance.get("prediction_truth_read_after_predictions_completed") is not True
        or truth_domain.get("accessed_by") != "FinalCareEvaluator"
        or truth_domain.get("available_to_training_or_calibration") is not False
    ):
        raise CareOfflineEvaluationError("evaluation suite leakage boundary is invalid")
    source_dataset_sha256 = str(provenance["source_dataset_sha256"])
    source_import_manifest_sha256 = str(provenance["source_import_manifest_sha256"])
    verify_care_artifact_license(
        license_metadata,
        artifact_type="offline-evaluation-suite",
        source_dataset_sha256=source_dataset_sha256,
        source_artifact_sha256=source_import_manifest_sha256,
        transformation_versions={
            "evaluation": OFFLINE_EVALUATION_VERSION,
            "feature_set": FEATURE_SET_VERSION,
            "quality_rules": QUALITY_RULE_VERSION,
            "score_protocol": SCORE_PROTOCOL_VERSION,
        },
    )
    records = truth_domain.get("records")
    if not isinstance(records, list):
        raise CareOfflineEvaluationError("evaluation suite truth records are malformed")
    truths = [
        CareEventTruth(
            event_id=int(record["event_id"]),
            farm=str(record["farm"]),
            source_asset_id=str(record["source_asset_id"]),
            event_label=str(record["event_label"]),
            event_start_source_row_id=int(record["event_start_source_row_id"]),
            event_end_source_row_id=int(record["event_end_source_row_id"]),
            failure_type=(str(record["failure_type"]) if record.get("failure_type") else None),
        )
        for record in records
        if isinstance(record, Mapping)
    ]
    failures = [
        EvaluationFailure(
            event_id=int(failure["event_id"]),
            category=str(failure["category"]),
            reason=str(failure["reason"]),
        )
        for failure in failures_raw
        if isinstance(failure, Mapping)
    ]
    if len(truths) != len(records) or len(failures) != len(failures_raw):
        raise CareOfflineEvaluationError("evaluation suite outcome is malformed")
    rebuilt = build_evaluation_suite_artifact(
        spec,
        predictions,
        truths,
        source_dataset_sha256=source_dataset_sha256,
        source_import_manifest_sha256=source_import_manifest_sha256,
        license_metadata=license_metadata,
        protocol=protocol,
        failures=failures,
        approval_lineage=(
            provenance.get("care_approval")
            if isinstance(provenance.get("care_approval"), Mapping)
            else None
        ),
    )
    if _canonical_bytes(rebuilt) != _canonical_bytes(artifact):
        raise CareOfflineEvaluationError("evaluation suite cannot be reproduced")
