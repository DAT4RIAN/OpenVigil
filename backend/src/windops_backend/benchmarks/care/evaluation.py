from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import time
import tracemalloc
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.benchmarks.care.anomaly import (
    canonical_anomaly_input_schema,
    canonical_anomaly_output_schema,
)
from windops_backend.benchmarks.care.contract import (
    DATASET_ID,
    DATASET_VERSION,
    CareContractError,
)
from windops_backend.benchmarks.care.importer import verify_minimal_import_manifest
from windops_backend.benchmarks.care.licensing import (
    build_care_artifact_license,
    verify_care_artifact_license,
)
from windops_backend.benchmarks.care.pipeline import (
    ImmutableArtifactStore,
    LocalImmutableArtifactStore,
)
from windops_backend.benchmarks.care.quality import (
    FEATURE_SET_VERSION,
    QUALITY_RULE_VERSION,
    StatusPointEvidence,
    StatusSequenceState,
    evaluate_status_point,
    verify_quality_contract,
)
from windops_backend.benchmarks.care.scoring import (
    SCORE_PROTOCOL_VERSION,
    CalibrationInput,
    CareEventTruth,
    EvaluationFailure,
    FinalCareEvaluator,
    ModelSelectionProvenance,
    PredictionBatch,
    PredictionPoint,
    PredictionTruthVault,
    aggregate_evaluation_results,
    build_prediction_artifact,
    build_score_protocol,
    fixed_threshold_policy,
    verify_prediction_artifact,
    verify_score_protocol,
)
from windops_backend.benchmarks.care.trust import (
    CareTrustAnchor,
    verify_embedded_care_approval,
)
from windops_backend.schemas import (
    BenchmarkEvaluationRunCreateRequest,
    BenchmarkEventResultCreateRequest,
    BenchmarkMetricSnapshotCreateRequest,
    ModelRegisterRequest,
)
from windops_backend.services.benchmark_metadata import (
    complete_evaluation_run,
    get_or_create_evaluation_run,
    record_event_result,
    record_metric_snapshot,
)
from windops_backend.services.models import register_model

parquet: Any = importlib.import_module("pyarrow.parquet")

OFFLINE_EVALUATION_VERSION = "care-v6-offline-evaluation-v1"
OFFLINE_EVALUATION_SCHEMA_VERSION = "care-v6-offline-evaluation-manifest-v1"
EVALUATION_SUITE_SCHEMA_VERSION = "care-v6-evaluation-suite-v1"
EVALUATION_SUITE_PROTOCOL = "care-event-train-prediction-v6-suite-v1"
COMPONENT_GENERALIZATION_PROTOCOL = "care-event-train-prediction-v6"
MODEL_PACKAGE_SCHEMA_VERSION = "care-v6-offline-anomaly-model-v1"
METRIC_VERSION = "care-v6-metric-snapshot-v1"
TRAIN_TRUSTED_STATUS_IDS = ("0",)
DEFAULT_RANDOM_SEED = 20_260_826

SIMPLE_ALGORITHM = "care-zscore-max-v1"
TARGET_ALGORITHM = "care-random-projection-ensemble-v1"
_ALGORITHMS = (
    {
        "algorithm": SIMPLE_ALGORITHM,
        "model_id": "care-a-minimal-zscore-v1",
        "model_name": "CARE A minimal z-score baseline",
        "model_version": "1.0.0",
        "threshold_quantile": 0.95,
        "projection_count": 0,
    },
    {
        "algorithm": TARGET_ALGORITHM,
        "model_id": "care-a-minimal-rp-ensemble-v1",
        "model_name": "CARE A minimal random-projection anomaly ensemble",
        "model_version": "1.0.0",
        "threshold_quantile": 0.975,
        "projection_count": 32,
    },
)


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


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_file_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _write_immutable_json(path: Path, value: Mapping[str, Any]) -> tuple[str, int]:
    content = _json_file_bytes(value)
    if path.exists():
        if not path.is_file() or path.read_bytes() != content:
            raise CareOfflineEvaluationError(
                f"immutable evaluation artifact already exists with different content: {path}"
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return hashlib.sha256(content).hexdigest(), len(content)


def _artifact_reference(
    *,
    output_root: Path,
    path: Path,
    document_sha256: str,
    object_key_prefix: str,
    artifact_store: ImmutableArtifactStore,
) -> dict[str, Any]:
    file_sha256 = _file_hash(path)
    key = f"{object_key_prefix}/{path.stem}.sha256-{file_sha256}{path.suffix}"
    uri = artifact_store.put_immutable(
        key,
        path,
        file_sha256,
        content_type="application/json",
    )
    return {
        "artifact_uri": uri,
        "local_relative_path": path.relative_to(output_root).as_posix(),
        "document_sha256": document_sha256,
        "file_sha256": file_sha256,
        "size_bytes": path.stat().st_size,
    }


def _dependency_identity() -> dict[str, str]:
    return {
        "implementation": OFFLINE_EVALUATION_VERSION,
        "numpy": importlib.metadata.version("numpy"),
        "pyarrow": importlib.metadata.version("pyarrow"),
        "python_numeric_contract": "float64-pcg64-linear-quantile-v1",
    }


def _normalise_status(value: Any) -> str:
    if isinstance(value, int | np.integer):
        return str(int(value))
    if isinstance(value, float | np.floating) and float(value).is_integer():
        return str(int(value))
    return str(value)


def _timestamp_text(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    text = str(value)
    if not text:
        raise CareOfflineEvaluationError("prediction timestamp must not be empty")
    return text


@dataclass(frozen=True, slots=True)
class _LoadedEvent:
    event_id: int
    source_asset_id: str
    parquet_sha256: str
    source_row_ids: np.ndarray[Any, Any]
    source_timestamps: tuple[str, ...]
    split: np.ndarray[Any, Any]
    status_ids: tuple[str, ...]
    status_evidence: tuple[StatusPointEvidence, ...]
    values: np.ndarray[Any, Any]


@dataclass(frozen=True, slots=True)
class _EventModelOutput:
    profile: dict[str, Any]
    train_scores: np.ndarray[Any, Any]
    prediction_scores: np.ndarray[Any, Any]


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


@dataclass(frozen=True, slots=True)
class OfflineEvaluationResult:
    manifest_path: Path
    manifest: dict[str, Any]
    manifest_file_sha256: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class OfflineEvaluationRegistration:
    created_count: int
    replayed_count: int
    model_ids: tuple[str, ...]
    evaluation_run_ids: tuple[str, ...]


def _load_event(
    import_root: Path,
    event: Mapping[str, Any],
    feature_columns: Sequence[str],
) -> _LoadedEvent:
    parquet_data = event.get("parquet", {}).get("data", {})
    relative = parquet_data.get("local_relative_path")
    if not isinstance(relative, str):
        raise CareOfflineEvaluationError("minimal import has no local Parquet reference")
    relative_path = PurePosixPath(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise CareOfflineEvaluationError("minimal import Parquet path is unsafe")
    path = import_root.joinpath(*relative_path.parts).resolve(strict=True)
    expected_hash = str(parquet_data.get("file_sha256", ""))
    if _file_hash(path) != expected_hash:
        raise CareOfflineEvaluationError("minimal import Parquet content hash mismatch")
    columns = ["time_stamp", "id", "train_test", "status_type_id", *feature_columns]
    table = parquet.read_table(path, columns=columns)
    if table.column_names != columns:
        raise CareOfflineEvaluationError("offline evaluation Parquet projection drifted")
    split = np.asarray(table["train_test"].to_pylist(), dtype=object)
    source_row_ids = np.asarray(table["id"].to_numpy(zero_copy_only=False), dtype=np.int64)
    if len(source_row_ids) < 1 or not np.all(source_row_ids[1:] > source_row_ids[:-1]):
        raise CareOfflineEvaluationError("offline evaluation source rows are not increasing")
    values = np.column_stack(
        [
            np.asarray(table[column].to_numpy(zero_copy_only=False), dtype=np.float64)
            for column in feature_columns
        ]
    )
    status_ids = tuple(_normalise_status(value) for value in table["status_type_id"].to_pylist())
    status_state = StatusSequenceState("A", TRAIN_TRUSTED_STATUS_IDS)
    status_evidence = tuple(
        status_state.observe(
            source_row_id=int(source_row_id),
            split=str(split_value),
            status_id=status_id,
            corroboration_signal_values=(),
        )
        for source_row_id, split_value, status_id in zip(
            source_row_ids,
            split,
            status_ids,
            strict=True,
        )
    )
    return _LoadedEvent(
        event_id=int(event["event_id"]),
        source_asset_id=str(event["source_asset_id"]),
        parquet_sha256=expected_hash,
        source_row_ids=source_row_ids,
        source_timestamps=tuple(
            _timestamp_text(value) for value in table["time_stamp"].to_pylist()
        ),
        split=split,
        status_ids=status_ids,
        status_evidence=status_evidence,
        values=values,
    )


def _finite_imputation(
    train_values: np.ndarray[Any, Any],
    prediction_values: np.ndarray[Any, Any],
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any], int, int]:
    finite_train = np.where(np.isfinite(train_values), train_values, np.nan)
    medians = np.nanmedian(finite_train, axis=0)
    if not np.isfinite(medians).all():
        raise CareOfflineEvaluationError("a model input feature has no finite train values")
    train_bad = ~np.isfinite(train_values)
    prediction_bad = ~np.isfinite(prediction_values)
    train = np.where(train_bad, medians, train_values)
    prediction = np.where(prediction_bad, medians, prediction_values)
    return train, prediction, medians, int(train_bad.sum()), int(prediction_bad.sum())


def _fit_event_model(
    event: _LoadedEvent,
    *,
    algorithm: str,
    projection_matrix: np.ndarray[Any, Any] | None,
) -> _EventModelOutput:
    train_mask = np.asarray(
        [
            str(split) == "train"
            and evaluate_status_point(
                farm="A",
                split=str(split),
                status_id=status_id,
                trusted_status_ids=TRAIN_TRUSTED_STATUS_IDS,
                disagreement_run_length=evidence.disagreement_run_length,
                corroborated_by_signal=evidence.corroborated_by_signal,
            ).model_usable
            for split, status_id, evidence in zip(
                event.split,
                event.status_ids,
                event.status_evidence,
                strict=True,
            )
        ],
        dtype=bool,
    )
    prediction_mask = event.split == "prediction"
    if not train_mask.any() or not prediction_mask.any():
        raise CareOfflineEvaluationError("event has no trusted train or prediction rows")
    train, prediction, medians, train_bad, prediction_bad = _finite_imputation(
        event.values[train_mask], event.values[prediction_mask]
    )
    means = train.mean(axis=0)
    standard_deviations = train.std(axis=0)
    standard_deviations = np.where(standard_deviations > 1e-12, standard_deviations, 1.0)
    train_z = (train - means) / standard_deviations
    prediction_z = (prediction - means) / standard_deviations
    profile: dict[str, Any] = {
        "event_id": event.event_id,
        "trusted_train_status_ids": list(TRAIN_TRUSTED_STATUS_IDS),
        "trusted_train_row_count": int(train.shape[0]),
        "prediction_row_count": int(prediction.shape[0]),
        "train_imputed_value_count": train_bad,
        "prediction_imputed_value_count": prediction_bad,
        "imputation": "per-feature-trusted-train-median-v1",
        "medians": medians.tolist(),
        "means": means.tolist(),
        "standard_deviations": standard_deviations.tolist(),
    }
    if algorithm == SIMPLE_ALGORITHM:
        train_scores = np.max(np.abs(train_z), axis=1)
        prediction_scores = np.max(np.abs(prediction_z), axis=1)
        profile["score"] = "maximum-absolute-standard-score"
    elif algorithm == TARGET_ALGORITHM:
        if projection_matrix is None:
            raise CareOfflineEvaluationError("target model projection matrix is missing")
        train_projection = train_z @ projection_matrix
        prediction_projection = prediction_z @ projection_matrix
        projection_means = train_projection.mean(axis=0)
        projection_std = train_projection.std(axis=0)
        projection_std = np.where(projection_std > 1e-12, projection_std, 1.0)
        train_scores = np.max(
            np.abs((train_projection - projection_means) / projection_std), axis=1
        )
        prediction_scores = np.max(
            np.abs((prediction_projection - projection_means) / projection_std), axis=1
        )
        profile.update(
            {
                "score": "maximum-absolute-standardized-random-projection",
                "projection_means": projection_means.tolist(),
                "projection_standard_deviations": projection_std.tolist(),
            }
        )
    else:  # pragma: no cover - internal algorithm table is frozen
        raise CareOfflineEvaluationError(f"unsupported offline algorithm: {algorithm}")
    if not np.isfinite(train_scores).all() or not np.isfinite(prediction_scores).all():
        raise CareOfflineEvaluationError("offline anomaly model emitted a non-finite score")
    return _EventModelOutput(profile, train_scores, prediction_scores)


def _truth_from_document(value: Mapping[str, Any]) -> CareEventTruth:
    if (
        value.get("access_scope") != "benchmark-evaluation-truth"
        or value.get("model_input_allowed") is not False
    ):
        raise CareOfflineEvaluationError("restricted truth access contract is invalid")
    description = str(value.get("event_description", "")).strip()
    return CareEventTruth(
        event_id=int(value["event_id"]),
        farm=str(value["farm"]),
        source_asset_id=str(value.get("source_asset_id", "0")),
        event_label=str(value["event_label"]),
        event_start_source_row_id=int(value["event_start_id"]),
        event_end_source_row_id=int(value["event_end_id"]),
        failure_type=description or None,
    )


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


def _metric_snapshots(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    if summary.get("status") != "scored":
        raise CareOfflineEvaluationError("completed model evaluation must be scoreable")
    event_metrics = summary["event_metrics"]
    point_metrics = summary["point_metrics"]
    definitions = [
        ("care_score", float(summary["care_score"]), "ratio", True, 0.5, "gte"),
        (
            "event_detection_rate",
            float(event_metrics["event_detection_rate"]),
            "ratio",
            True,
            1.0,
            "gte",
        ),
        (
            "normal_event_false_positive_rate",
            float(event_metrics["normal_event_false_positive_rate"]),
            "ratio",
            True,
            0.0,
            "lte",
        ),
        (
            "requested_event_count",
            float(summary["requested_event_count"]),
            "events",
            False,
            None,
            None,
        ),
        ("scored_event_count", float(summary["scored_event_count"]), "events", False, None, None),
        (
            "unscorable_event_count",
            float(summary["unscorable_event_count"]),
            "events",
            True,
            0.0,
            "eq",
        ),
        (
            "data_failure_event_count",
            float(summary["data_failure_event_count"]),
            "events",
            True,
            0.0,
            "eq",
        ),
        (
            "model_failure_event_count",
            float(summary["model_failure_event_count"]),
            "events",
            True,
            0.0,
            "eq",
        ),
        ("point_f0_5", float(point_metrics["f0_5"]), "ratio", False, None, None),
    ]
    pr_auc = point_metrics.get("pr_auc_average_precision")
    if pr_auc is not None:
        definitions.append(("pr_auc_average_precision", float(pr_auc), "ratio", False, None, None))
    metrics: list[dict[str, Any]] = []
    for name, value, unit, release, threshold, direction in definitions:
        if not math.isfinite(value):
            raise CareOfflineEvaluationError(f"metric {name} is non-finite")
        passed = None
        if direction is not None:
            if threshold is None:
                raise CareOfflineEvaluationError(
                    f"release metric {name} has a direction without a threshold"
                )
            if direction == "gte":
                passed = value >= float(threshold)
            elif direction == "lte":
                passed = value <= float(threshold)
            elif direction == "eq":
                passed = value == float(threshold)
            else:
                raise CareOfflineEvaluationError(
                    f"release metric {name} has unsupported direction {direction}"
                )
        metrics.append(
            {
                "metric_name": name,
                "protocol_version": SCORE_PROTOCOL_VERSION,
                "metric_version": METRIC_VERSION,
                "value": value,
                "unit": unit,
                "numerator": None,
                "denominator": None,
                "is_release_metric": release,
                "threshold_value": threshold,
                "threshold_direction": direction,
                "passed": passed,
            }
        )
    return metrics


def _result_identity(models: Sequence[Mapping[str, Any]]) -> str:
    return _canonical_hash(
        [
            {
                "model_id": model["model_id"],
                "model_version": model["model_version"],
                "package_document_sha256": model["package"]["document_sha256"],
                "prediction_document_sha256": [
                    reference["document_sha256"] for reference in model["prediction_artifacts"]
                ],
                "evaluation_document_sha256": model["evaluation_artifact"]["document_sha256"],
            }
            for model in models
        ]
    )


def verify_offline_model_package(package: Mapping[str, Any]) -> None:
    """Validate the safe JSON model package before any online score is computed."""

    actual = package.get("model_package_sha256")
    unsigned = {key: value for key, value in package.items() if key != "model_package_sha256"}
    if (
        not isinstance(actual, str)
        or _canonical_hash(unsigned) != actual
        or package.get("schema_version") != MODEL_PACKAGE_SCHEMA_VERSION
        or package.get("dataset_id") != DATASET_ID
        or package.get("dataset_version") != DATASET_VERSION
        or package.get("model_kind") != "anomaly"
        or package.get("prediction_truth_used") is not False
        or package.get("training_split") != "train"
    ):
        raise CareOfflineEvaluationError("offline model package identity is invalid")
    algorithm = package.get("algorithm")
    if algorithm not in {SIMPLE_ALGORITHM, TARGET_ALGORITHM}:
        raise CareOfflineEvaluationError("offline model package algorithm is unsupported")
    feature_columns = package.get("feature_columns")
    profiles = package.get("event_profiles")
    if (
        not isinstance(feature_columns, list)
        or not feature_columns
        or not all(isinstance(item, str) and item for item in feature_columns)
        or len(feature_columns) != len(set(feature_columns))
        or not isinstance(profiles, list)
        or not profiles
    ):
        raise CareOfflineEvaluationError(
            "offline model package feature/profile structure is invalid"
        )
    threshold = package.get("threshold_policy")
    if not isinstance(threshold, Mapping):
        raise CareOfflineEvaluationError("offline model package threshold policy is missing")
    threshold_actual = threshold.get("threshold_policy_sha256")
    threshold_unsigned = {
        key: value for key, value in threshold.items() if key != "threshold_policy_sha256"
    }
    if (
        not isinstance(threshold_actual, str)
        or _canonical_hash(threshold_unsigned) != threshold_actual
        or threshold.get("prediction_truth_used") is not False
        or threshold.get("calibration_split") not in {"train", "train-validation"}
        or threshold.get("comparison") != "strict-greater-than"
        or isinstance(threshold.get("value"), bool)
        or not isinstance(threshold.get("value"), int | float)
        or not math.isfinite(float(threshold["value"]))
        or float(threshold["value"]) <= 0
    ):
        raise CareOfflineEvaluationError("offline model package threshold policy is invalid")

    expected_length = len(feature_columns)
    profile_ids: set[int] = set()
    for raw_profile in profiles:
        if not isinstance(raw_profile, Mapping):
            raise CareOfflineEvaluationError("offline model package contains a malformed profile")
        event_id = raw_profile.get("event_id")
        if isinstance(event_id, bool) or not isinstance(event_id, int) or event_id in profile_ids:
            raise CareOfflineEvaluationError("offline model package profile identity is invalid")
        profile_ids.add(event_id)
        required_vectors = ("medians", "means", "standard_deviations")
        for name in required_vectors:
            values = raw_profile.get(name)
            if (
                not isinstance(values, list)
                or len(values) != expected_length
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, int | float)
                    or not math.isfinite(float(value))
                    for value in values
                )
            ):
                raise CareOfflineEvaluationError(
                    f"offline model package profile {event_id} has an invalid {name}"
                )
        if any(float(value) <= 0 for value in raw_profile["standard_deviations"]):
            raise CareOfflineEvaluationError("offline model package standard deviation is invalid")
        if algorithm == TARGET_ALGORITHM:
            projection_means = raw_profile.get("projection_means")
            projection_std = raw_profile.get("projection_standard_deviations")
            if (
                not isinstance(projection_means, list)
                or not isinstance(projection_std, list)
                or len(projection_means) != len(projection_std)
                or not projection_means
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, int | float)
                    or not math.isfinite(float(value))
                    for value in [*projection_means, *projection_std]
                )
                or any(float(value) <= 0 for value in projection_std)
            ):
                raise CareOfflineEvaluationError(
                    "offline target model package projection profile is invalid"
                )

    projection_matrix = package.get("projection_matrix")
    if algorithm == SIMPLE_ALGORITHM:
        if projection_matrix is not None:
            raise CareOfflineEvaluationError("simple model package must not carry projections")
        return
    if (
        not isinstance(projection_matrix, list)
        or len(projection_matrix) != expected_length
        or not all(isinstance(row, list) for row in projection_matrix)
    ):
        raise CareOfflineEvaluationError("offline target model projection matrix is invalid")
    projection_count = len(profiles[0]["projection_means"])
    if any(
        len(row) != projection_count
        or any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(float(value))
            for value in row
        )
        for row in projection_matrix
    ):
        raise CareOfflineEvaluationError("offline target model projection matrix shape is invalid")


def score_offline_model_package(
    package: Mapping[str, Any],
    *,
    event_id: int,
    feature_values: Mapping[str, float],
) -> float:
    """Execute one deterministic point through the verified, non-executable JSON package."""

    verify_offline_model_package(package)
    feature_columns = [str(value) for value in package["feature_columns"]]
    if set(feature_values) != set(feature_columns):
        raise CareOfflineEvaluationError(
            "online feature values must exactly match the offline model feature set"
        )
    raw_values = [feature_values[column] for column in feature_columns]
    if any(
        isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value)
        for value in raw_values
    ):
        raise CareOfflineEvaluationError("online feature values must be finite numbers")
    profile = next(
        (
            value
            for value in package["event_profiles"]
            if isinstance(value, Mapping) and value.get("event_id") == event_id
        ),
        None,
    )
    if profile is None:
        raise CareOfflineEvaluationError("offline model package has no profile for this event")
    values = np.asarray(raw_values, dtype=np.float64)
    means = np.asarray(profile["means"], dtype=np.float64)
    standard_deviations = np.asarray(profile["standard_deviations"], dtype=np.float64)
    standardized = (values - means) / standard_deviations
    if package["algorithm"] == SIMPLE_ALGORITHM:
        score = float(np.max(np.abs(standardized)))
    else:
        projections = standardized @ np.asarray(package["projection_matrix"], dtype=np.float64)
        projection_means = np.asarray(profile["projection_means"], dtype=np.float64)
        projection_std = np.asarray(profile["projection_standard_deviations"], dtype=np.float64)
        score = float(np.max(np.abs((projections - projection_means) / projection_std)))
    if not math.isfinite(score) or score < 0:
        raise CareOfflineEvaluationError("offline model package emitted an invalid score")
    return score


def _verify_local_artifact(
    reference: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    output_root: Path,
) -> None:
    relative = PurePosixPath(str(reference.get("local_relative_path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise CareOfflineEvaluationError("offline evaluation artifact path is unsafe")
    target = output_root.joinpath(*relative.parts).resolve(strict=True)
    if not target.is_relative_to(output_root):
        raise CareOfflineEvaluationError("offline evaluation artifact escaped its root")
    if _file_hash(target) != reference.get("file_sha256") or target.stat().st_size != reference.get(
        "size_bytes"
    ):
        raise CareOfflineEvaluationError("offline evaluation artifact content drifted")
    document = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise CareOfflineEvaluationError("offline evaluation artifact is not a JSON object")
    source_dataset_sha256 = str(manifest["identity"]["source_dataset_sha256"])
    source_import_sha256 = str(manifest["identity"]["source_import_manifest_sha256"])
    path_text = relative.as_posix()
    if "/models/" in path_text:
        verify_offline_model_package(document)
        actual = document["model_package_sha256"]
        if actual != reference.get("document_sha256"):
            raise CareOfflineEvaluationError("offline model package reference drifted")
        license_metadata = document.get("license")
        if not isinstance(license_metadata, Mapping):
            raise CareOfflineEvaluationError("offline model package license is missing")
        verify_care_artifact_license(
            license_metadata,
            artifact_type="offline-anomaly-model-package",
            source_dataset_sha256=source_dataset_sha256,
            source_artifact_sha256=source_import_sha256,
            transformation_versions={
                "evaluation": OFFLINE_EVALUATION_VERSION,
                "feature_set": FEATURE_SET_VERSION,
                "model_algorithm": str(document["algorithm"]),
                "quality_rules": QUALITY_RULE_VERSION,
            },
        )
    elif "/predictions/" in path_text:
        verify_prediction_artifact(document)
        if document.get("prediction_artifact_sha256") != reference.get("document_sha256"):
            raise CareOfflineEvaluationError("offline prediction reference drifted")
        event_sources = manifest["identity"]["event_parquet_sha256"]
        source_artifact_sha256 = str(event_sources[str(document["event_id"])])
        license_metadata = document.get("license")
        if not isinstance(license_metadata, Mapping):
            raise CareOfflineEvaluationError("offline prediction license is missing")
        verify_care_artifact_license(
            license_metadata,
            artifact_type="offline-event-prediction",
            source_dataset_sha256=source_dataset_sha256,
            source_artifact_sha256=source_artifact_sha256,
            transformation_versions={
                "evaluation": OFFLINE_EVALUATION_VERSION,
                "feature_set": FEATURE_SET_VERSION,
                "model_algorithm": str(
                    next(
                        model["algorithm"]
                        for model in manifest["models"]
                        if model["model_id"] == document["model_id"]
                    )
                ),
                "quality_rules": QUALITY_RULE_VERSION,
                "score_protocol": SCORE_PROTOCOL_VERSION,
            },
        )
    elif "/evaluations/" in path_text:
        verify_evaluation_suite_artifact(document)
        if document.get("evaluation_artifact_sha256") != reference.get("document_sha256"):
            raise CareOfflineEvaluationError("offline evaluation reference drifted")
    else:
        raise CareOfflineEvaluationError("offline evaluation artifact type is unknown")


def verify_offline_evaluation_manifest(
    manifest: Mapping[str, Any],
    *,
    output_root: Path | None = None,
    trust_anchor: CareTrustAnchor | None = None,
) -> None:
    actual = manifest.get("manifest_sha256")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if (
        not isinstance(actual, str)
        or _canonical_hash(unsigned) != actual
        or manifest.get("schema_version") != OFFLINE_EVALUATION_SCHEMA_VERSION
        or manifest.get("dataset_id") != DATASET_ID
        or manifest.get("dataset_version") != DATASET_VERSION
        or manifest.get("event_ids") != [0, 24]
        or manifest.get("suite_protocol") != EVALUATION_SUITE_PROTOCOL
        or manifest.get("component_generalization_protocol") != COMPONENT_GENERALIZATION_PROTOCOL
        or manifest.get("prediction_truth_available_to_training_or_calibration") is not False
    ):
        raise CareOfflineEvaluationError("offline evaluation manifest identity is invalid")
    approval = manifest.get("care_approval")
    if not isinstance(approval, Mapping):
        raise CareOfflineEvaluationError("offline evaluation is missing CARE approved-root lineage")
    try:
        verify_embedded_care_approval(approval, trust_anchor=trust_anchor)
    except CareContractError as exc:
        raise CareOfflineEvaluationError(str(exc)) from exc
    identity = manifest.get("identity")
    models = manifest.get("models")
    artifacts = manifest.get("artifacts")
    license_metadata = manifest.get("license")
    if (
        not isinstance(identity, Mapping)
        or not isinstance(models, list)
        or not isinstance(artifacts, list)
        or not isinstance(license_metadata, Mapping)
    ):
        raise CareOfflineEvaluationError("offline evaluation manifest structure is malformed")
    if [model.get("model_id") for model in models if isinstance(model, Mapping)] != [
        algorithm["model_id"] for algorithm in _ALGORITHMS
    ]:
        raise CareOfflineEvaluationError("offline evaluation model set or ordering drifted")
    nested_references: list[Mapping[str, Any]] = []
    for model in models:
        if not isinstance(model, Mapping):
            raise CareOfflineEvaluationError("offline evaluation model record is malformed")
        prediction_references = model.get("prediction_artifacts")
        event_results = model.get("event_results")
        summary = model.get("summary")
        metrics = model.get("metrics")
        package = model.get("package")
        evaluation = model.get("evaluation_artifact")
        if (
            not isinstance(prediction_references, list)
            or not isinstance(event_results, list)
            or not isinstance(summary, Mapping)
            or not isinstance(metrics, list)
            or not isinstance(package, Mapping)
            or not isinstance(evaluation, Mapping)
        ):
            raise CareOfflineEvaluationError("offline evaluation model evidence is malformed")
        if (
            [reference.get("event_id") for reference in prediction_references] != [0, 24]
            or [result.get("event_id") for result in event_results] != [0, 24]
            or summary.get("requested_event_count") != 2
            or summary.get("scored_event_count") != 2
            or summary.get("data_failure_event_count") != 0
            or summary.get("model_failure_event_count") != 0
            or summary.get("unscorable_event_count") != 0
            or metrics != _metric_snapshots(summary)
        ):
            raise CareOfflineEvaluationError("offline evaluation result summary is inconsistent")
        for result in event_results:
            if not isinstance(result, Mapping):
                raise CareOfflineEvaluationError("offline event result is malformed")
            result_hash = result.get("event_result_sha256")
            result_unsigned = {
                key: value for key, value in result.items() if key != "event_result_sha256"
            }
            if not isinstance(result_hash, str) or _canonical_hash(result_unsigned) != result_hash:
                raise CareOfflineEvaluationError("offline event result hash is invalid")
        nested_references.extend([package, *prediction_references, evaluation])
    if len(artifacts) != 8 or [_canonical_hash(item) for item in artifacts] != [
        _canonical_hash(item) for item in nested_references
    ]:
        raise CareOfflineEvaluationError("offline evaluation artifact index is inconsistent")
    if manifest.get("result_identity_sha256") != _result_identity(models):
        raise CareOfflineEvaluationError("offline evaluation result identity is invalid")
    source_dataset_sha256 = str(identity["source_dataset_sha256"])
    source_import_sha256 = str(identity["source_import_manifest_sha256"])
    verify_care_artifact_license(
        license_metadata,
        artifact_type="offline-evaluation-manifest",
        source_dataset_sha256=source_dataset_sha256,
        source_artifact_sha256=source_import_sha256,
        transformation_versions={
            "evaluation": OFFLINE_EVALUATION_VERSION,
            "feature_set": FEATURE_SET_VERSION,
            "quality_rules": QUALITY_RULE_VERSION,
            "score_protocol": SCORE_PROTOCOL_VERSION,
        },
    )
    if output_root is not None:
        resolved_root = output_root.resolve(strict=True)
        for reference in artifacts:
            if not isinstance(reference, Mapping):
                raise CareOfflineEvaluationError(
                    "offline evaluation artifact reference is malformed"
                )
            _verify_local_artifact(reference, manifest=manifest, output_root=resolved_root)


def _validate_existing_manifest(
    path: Path,
    *,
    output_root: Path,
    evaluation_identity_sha256: str,
    trust_anchor: CareTrustAnchor | None,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise CareOfflineEvaluationError("offline evaluation manifest root is malformed")
    actual = raw.get("manifest_sha256")
    unsigned = {key: value for key, value in raw.items() if key != "manifest_sha256"}
    if (
        not isinstance(actual, str)
        or _canonical_hash(unsigned) != actual
        or raw.get("schema_version") != OFFLINE_EVALUATION_SCHEMA_VERSION
        or raw.get("evaluation_identity_sha256") != evaluation_identity_sha256
    ):
        raise CareOfflineEvaluationError("offline evaluation manifest identity mismatch")
    verify_offline_evaluation_manifest(
        raw,
        output_root=output_root,
        trust_anchor=trust_anchor,
    )
    return dict(raw)


def build_offline_evaluations(
    import_manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    import_root: Path,
    output_root: Path,
    *,
    created_at: str,
    random_seed: int = DEFAULT_RANDOM_SEED,
    artifact_store: ImmutableArtifactStore | None = None,
    trust_anchor: CareTrustAnchor | None = None,
) -> OfflineEvaluationResult:
    verify_minimal_import_manifest(import_manifest)
    verify_quality_contract(quality_contract)
    approval = import_manifest.get("care_approval")
    if not isinstance(approval, Mapping):
        raise CareOfflineEvaluationError("source import is missing CARE approved-root lineage")
    try:
        verify_embedded_care_approval(approval, trust_anchor=trust_anchor)
    except CareContractError as exc:
        raise CareOfflineEvaluationError(str(exc)) from exc
    if (
        import_manifest.get("quality_contract_sha256")
        != quality_contract.get("quality_contract_sha256")
        or import_manifest.get("feature_set_version") != FEATURE_SET_VERSION
        or import_manifest.get("quality_rule_version") != QUALITY_RULE_VERSION
        or tuple(import_manifest.get("event_ids", [])) != (0, 24)
        or approval.get("quality_contract_sha256")
        != quality_contract.get("quality_contract_sha256")
    ):
        raise CareOfflineEvaluationError("offline evaluation controls do not match H003")
    if isinstance(random_seed, bool) or not 0 <= random_seed <= 2_147_483_647:
        raise CareOfflineEvaluationError("offline evaluation random seed is invalid")
    EvaluationSuiteSpec(
        run_id="created-at-validation",
        purpose="final-holdout",
        event_ids=(0, 24),
        model_id="created-at-validation",
        model_version="1",
        created_at=created_at,
    )
    dependency_identity = _dependency_identity()
    identity_payload = {
        "evaluation_version": OFFLINE_EVALUATION_VERSION,
        "source_import_manifest_sha256": import_manifest["manifest_sha256"],
        "source_dataset_sha256": import_manifest["source_dataset_sha256"],
        "quality_contract_sha256": quality_contract["quality_contract_sha256"],
        "care_approved_root_sha256": approval["approved_root_sha256"],
        "feature_set_sha256": quality_contract["feature_set_sha256"],
        "score_protocol_sha256": build_score_protocol()["score_protocol_sha256"],
        "event_ids": [0, 24],
        "algorithms": list(_ALGORITHMS),
        "random_seed": random_seed,
        "created_at": created_at,
        "dependency_identity": dependency_identity,
        "event_parquet_sha256": {
            str(event["event_id"]): event["parquet"]["data"]["file_sha256"]
            for event in import_manifest["events"]
        },
        "truth_available_to_training_or_calibration": False,
    }
    evaluation_identity_sha256 = _canonical_hash(identity_payload)
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "care/v6/reports/offline-evaluation/manifest.json"
    existing = _validate_existing_manifest(
        manifest_path,
        output_root=output_root,
        evaluation_identity_sha256=evaluation_identity_sha256,
        trust_anchor=trust_anchor,
    )
    if existing is not None:
        return OfflineEvaluationResult(manifest_path, existing, _file_hash(manifest_path), True)

    import_root = import_root.resolve(strict=True)
    store = artifact_store or LocalImmutableArtifactStore(output_root / "immutable-object-store")
    feature_columns = tuple(str(item) for item in import_manifest["model_input_columns"])
    if (
        len(feature_columns) != 54
        or len(feature_columns) != len(set(feature_columns))
        or set(feature_columns).intersection(
            import_manifest["truth_fields_forbidden_from_model_input"]
        )
    ):
        raise CareOfflineEvaluationError("offline evaluation model-input boundary is invalid")
    events = tuple(
        _load_event(import_root, event, feature_columns) for event in import_manifest["events"]
    )
    if tuple(event.event_id for event in events) != (0, 24):
        raise CareOfflineEvaluationError("offline evaluation event ordering drifted")

    artifacts: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    total_started = time.perf_counter()
    total_peak_bytes = 0
    source_dataset_sha256 = str(import_manifest["source_dataset_sha256"])
    source_import_sha256 = str(import_manifest["manifest_sha256"])
    rng = np.random.default_rng(random_seed)
    projection_matrix = rng.normal(size=(len(feature_columns), 32))
    projection_matrix /= np.linalg.norm(projection_matrix, axis=0)

    for algorithm_spec in _ALGORITHMS:
        tracemalloc.start()
        model_started = time.perf_counter()
        algorithm = str(algorithm_spec["algorithm"])
        active_projection = projection_matrix if algorithm == TARGET_ALGORITHM else None
        outputs = {
            event.event_id: _fit_event_model(
                event,
                algorithm=algorithm,
                projection_matrix=active_projection,
            )
            for event in events
        }
        training_scores = np.concatenate([outputs[event.event_id].train_scores for event in events])
        quantile_raw: Any = algorithm_spec["threshold_quantile"]
        quantile_value = float(quantile_raw)
        raw_threshold: Any = np.quantile(training_scores, quantile_value)
        threshold_value = float(raw_threshold)
        training_run_id = (
            f"care-a-train-{algorithm.replace('care-', '').replace('-v1', '')}-"
            f"{evaluation_identity_sha256[:12]}"
        )
        threshold_policy = fixed_threshold_policy(
            CalibrationInput(
                tuple(float(value) for value in training_scores), "train", training_run_id
            ),
            value=threshold_value,
            version=f"{algorithm}-train-quantile-v1",
            strategy=(
                f"linear-quantile-{algorithm_spec['threshold_quantile']}-from-trusted-train-"
                "scores-across-fixed-events"
            ),
        )
        model_id = str(algorithm_spec["model_id"])
        model_version = str(algorithm_spec["model_version"])
        run_id = (
            "care-eval-a0-a24-zscore-v1"
            if algorithm == SIMPLE_ALGORITHM
            else "care-eval-a0-a24-rp-v1"
        )
        selection = ModelSelectionProvenance(
            training_run_id=training_run_id,
            feature_selection_split="not-used",
            early_stopping_split="not-used",
            hyperparameter_selection_split="not-used",
        )
        package_license = build_care_artifact_license(
            artifact_type="offline-anomaly-model-package",
            changes_made=(
                "Fit a deterministic label-free anomaly model on each event's trusted train "
                "partition and calibrated one shared threshold from train scores only."
            ),
            source_dataset_sha256=source_dataset_sha256,
            source_artifact_sha256=source_import_sha256,
            transformation_versions={
                "evaluation": OFFLINE_EVALUATION_VERSION,
                "feature_set": FEATURE_SET_VERSION,
                "model_algorithm": algorithm,
                "quality_rules": QUALITY_RULE_VERSION,
            },
        )
        package_payload: dict[str, Any] = {
            "schema_version": MODEL_PACKAGE_SCHEMA_VERSION,
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "model_id": model_id,
            "model_name": algorithm_spec["model_name"],
            "model_version": model_version,
            "model_kind": "anomaly",
            "algorithm": algorithm,
            "random_seed": random_seed,
            "feature_columns": list(feature_columns),
            "feature_set_version": FEATURE_SET_VERSION,
            "feature_set_sha256": quality_contract["feature_set_sha256"],
            "quality_rule_version": QUALITY_RULE_VERSION,
            "quality_contract_sha256": quality_contract["quality_contract_sha256"],
            "care_approval": dict(approval),
            "training_split": "train",
            "trusted_train_status_ids": list(TRAIN_TRUSTED_STATUS_IDS),
            "prediction_truth_used": False,
            "model_selection_provenance": selection.to_dict(),
            "threshold_policy": threshold_policy.to_dict(),
            "dependency_identity": dependency_identity,
            "event_profiles": [outputs[event.event_id].profile for event in events],
            "projection_matrix": (
                projection_matrix.tolist() if algorithm == TARGET_ALGORITHM else None
            ),
            "license": package_license,
        }
        package_document_sha256 = _canonical_hash(package_payload)
        package = {**package_payload, "model_package_sha256": package_document_sha256}
        package_path = output_root / f"care/v6/reports/models/model={model_id}/package.json"
        _write_immutable_json(package_path, package)
        package_reference = _artifact_reference(
            output_root=output_root,
            path=package_path,
            document_sha256=package_document_sha256,
            object_key_prefix=f"care/v6/reports/models/model={model_id}",
            artifact_store=store,
        )
        artifacts.append(package_reference)

        prediction_artifacts: list[dict[str, Any]] = []
        prediction_references: list[dict[str, Any]] = []
        for event in events:
            prediction_mask = event.split == "prediction"
            indexes = np.flatnonzero(prediction_mask)
            scores = outputs[event.event_id].prediction_scores
            if len(indexes) != len(scores):
                raise CareOfflineEvaluationError("prediction score count drifted")
            prediction_license = build_care_artifact_license(
                artifact_type="offline-event-prediction",
                changes_made=(
                    "Applied a train-only calibrated anomaly model to the prediction partition; "
                    "the artifact contains scores and decisions but no event truth."
                ),
                source_dataset_sha256=source_dataset_sha256,
                source_artifact_sha256=event.parquet_sha256,
                transformation_versions={
                    "evaluation": OFFLINE_EVALUATION_VERSION,
                    "feature_set": FEATURE_SET_VERSION,
                    "model_algorithm": algorithm,
                    "quality_rules": QUALITY_RULE_VERSION,
                    "score_protocol": SCORE_PROTOCOL_VERSION,
                },
            )
            batch = PredictionBatch(
                event_id=event.event_id,
                farm="A",
                source_asset_id=event.source_asset_id,
                points=tuple(
                    PredictionPoint(
                        source_row_id=int(event.source_row_ids[index]),
                        source_timestamp=event.source_timestamps[index],
                        anonymous_time=event.source_timestamps[index],
                        anomaly_score=float(score),
                        status_id=event.status_ids[index],
                        disagreement_run_length=(
                            event.status_evidence[index].disagreement_run_length
                        ),
                        corroborated_by_signal=(
                            event.status_evidence[index].corroborated_by_signal
                        ),
                        corroboration_signal_count=(
                            event.status_evidence[index].corroboration_signal_count
                        ),
                        corroboration_finite_signal_count=(
                            event.status_evidence[index].corroboration_finite_signal_count
                        ),
                        corroboration_inactive_or_invalid_signal_count=(
                            event.status_evidence[
                                index
                            ].corroboration_inactive_or_invalid_signal_count
                        ),
                    )
                    for index, score in zip(indexes, scores, strict=True)
                ),
                model_id=model_id,
                model_version=model_version,
                deployment_id=None,
                feature_set_version=FEATURE_SET_VERSION,
                feature_set_sha256=str(quality_contract["feature_set_sha256"]),
                quality_rule_version=QUALITY_RULE_VERSION,
                quality_contract_sha256=str(quality_contract["quality_contract_sha256"]),
                model_selection_provenance=selection,
            )
            prediction = build_prediction_artifact(
                batch,
                threshold_policy,
                trusted_status_ids=TRAIN_TRUSTED_STATUS_IDS,
                license_metadata=prediction_license,
                approval_lineage=approval,
            )
            verify_prediction_artifact(prediction)
            prediction_path = output_root / (
                f"care/v6/predictions/model={model_id}/run={run_id}/farm=A/"
                f"event={event.event_id}/prediction.json"
            )
            _write_immutable_json(prediction_path, prediction)
            prediction_reference = _artifact_reference(
                output_root=output_root,
                path=prediction_path,
                document_sha256=str(prediction["prediction_artifact_sha256"]),
                object_key_prefix=(
                    f"care/v6/predictions/model={model_id}/run={run_id}/"
                    f"farm=A/event={event.event_id}"
                ),
                artifact_store=store,
            )
            prediction_reference["event_id"] = event.event_id
            artifacts.append(prediction_reference)
            prediction_references.append(prediction_reference)
            prediction_artifacts.append(prediction)

        # Truth is deliberately opened only after every prediction artifact is complete.
        truths: list[CareEventTruth] = []
        for imported_event in import_manifest["events"]:
            truth_reference = imported_event["restricted_truth"]["artifact"]
            relative = PurePosixPath(str(truth_reference["local_relative_path"]))
            if relative.is_absolute() or ".." in relative.parts:
                raise CareOfflineEvaluationError("restricted truth path is unsafe")
            truth_path = import_root.joinpath(*relative.parts).resolve(strict=True)
            if _file_hash(truth_path) != truth_reference["file_sha256"]:
                raise CareOfflineEvaluationError("restricted truth content hash mismatch")
            truth_document = json.loads(truth_path.read_text(encoding="utf-8"))
            if not isinstance(truth_document, Mapping):
                raise CareOfflineEvaluationError("restricted truth document is malformed")
            truths.append(_truth_from_document(truth_document))

        evaluation_license = build_care_artifact_license(
            artifact_type="offline-evaluation-suite",
            changes_made=(
                "Evaluated the fixed anomaly and normal events with care-score-v6 after all "
                "truth-free predictions were frozen; retained explicit event outcomes."
            ),
            source_dataset_sha256=source_dataset_sha256,
            source_artifact_sha256=source_import_sha256,
            transformation_versions={
                "evaluation": OFFLINE_EVALUATION_VERSION,
                "feature_set": FEATURE_SET_VERSION,
                "quality_rules": QUALITY_RULE_VERSION,
                "score_protocol": SCORE_PROTOCOL_VERSION,
            },
        )
        evaluation = build_evaluation_suite_artifact(
            EvaluationSuiteSpec(
                run_id=run_id,
                purpose="final-holdout",
                event_ids=(0, 24),
                model_id=model_id,
                model_version=model_version,
                created_at=created_at,
            ),
            prediction_artifacts,
            truths,
            source_dataset_sha256=source_dataset_sha256,
            source_import_manifest_sha256=source_import_sha256,
            license_metadata=evaluation_license,
            approval_lineage=approval,
        )
        verify_evaluation_suite_artifact(evaluation)
        evaluation_path = output_root / (
            f"care/v6/reports/evaluations/model={model_id}/run={run_id}/evaluation.json"
        )
        _write_immutable_json(evaluation_path, evaluation)
        evaluation_reference = _artifact_reference(
            output_root=output_root,
            path=evaluation_path,
            document_sha256=str(evaluation["evaluation_artifact_sha256"]),
            object_key_prefix=f"care/v6/reports/evaluations/model={model_id}/run={run_id}",
            artifact_store=store,
        )
        artifacts.append(evaluation_reference)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        total_peak_bytes = max(total_peak_bytes, peak_bytes)
        model_elapsed = time.perf_counter() - model_started
        model_input_identity = _canonical_hash(
            {
                "evaluation_identity_sha256": evaluation_identity_sha256,
                "model_package_file_sha256": package_reference["file_sha256"],
                "threshold_policy_sha256": threshold_policy.to_dict()["threshold_policy_sha256"],
                "model_id": model_id,
                "model_version": model_version,
            }
        )
        models.append(
            {
                "model_id": model_id,
                "model_name": algorithm_spec["model_name"],
                "model_version": model_version,
                "model_kind": "anomaly",
                "algorithm": algorithm,
                "random_seed": random_seed,
                "training_run_id": training_run_id,
                "input_identity_sha256": model_input_identity,
                "package": package_reference,
                "threshold_policy": threshold_policy.to_dict(),
                "prediction_artifacts": prediction_references,
                "evaluation_run_id": run_id,
                "evaluation_artifact": evaluation_reference,
                "metrics": _metric_snapshots(evaluation["summary"]),
                "event_results": evaluation["event_results"],
                "summary": evaluation["summary"],
                "care_approval": dict(approval),
                "resource_stats": {
                    "elapsed_seconds": model_elapsed,
                    "peak_tracemalloc_bytes": peak_bytes,
                    "train_score_count": int(len(training_scores)),
                    "prediction_score_count": sum(
                        len(outputs[event.event_id].prediction_scores) for event in events
                    ),
                },
            }
        )

    total_elapsed = time.perf_counter() - total_started
    manifest_payload: dict[str, Any] = {
        "schema_version": OFFLINE_EVALUATION_SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "farm": "A",
        "event_ids": [0, 24],
        "evaluation_identity_sha256": evaluation_identity_sha256,
        "identity": identity_payload,
        "suite_protocol": EVALUATION_SUITE_PROTOCOL,
        "component_generalization_protocol": COMPONENT_GENERALIZATION_PROTOCOL,
        "score_protocol_version": SCORE_PROTOCOL_VERSION,
        "feature_set_version": FEATURE_SET_VERSION,
        "feature_set_sha256": quality_contract["feature_set_sha256"],
        "quality_rule_version": QUALITY_RULE_VERSION,
        "quality_contract_sha256": quality_contract["quality_contract_sha256"],
        "care_approval": dict(approval),
        "prediction_truth_available_to_training_or_calibration": False,
        "models": models,
        "artifacts": artifacts,
        "result_identity_sha256": _result_identity(models),
        "resource_stats": {
            "elapsed_seconds": total_elapsed,
            "peak_tracemalloc_bytes": total_peak_bytes,
        },
        "license": build_care_artifact_license(
            artifact_type="offline-evaluation-manifest",
            changes_made=(
                "Indexed two deterministic model packages, their truth-free predictions, "
                "care-score-v6 evaluation suites, structured metrics, and resource evidence."
            ),
            source_dataset_sha256=source_dataset_sha256,
            source_artifact_sha256=source_import_sha256,
            transformation_versions={
                "evaluation": OFFLINE_EVALUATION_VERSION,
                "feature_set": FEATURE_SET_VERSION,
                "quality_rules": QUALITY_RULE_VERSION,
                "score_protocol": SCORE_PROTOCOL_VERSION,
            },
        ),
    }
    manifest = {**manifest_payload, "manifest_sha256": _canonical_hash(manifest_payload)}
    verify_offline_evaluation_manifest(
        manifest,
        output_root=output_root,
        trust_anchor=trust_anchor,
    )
    _write_immutable_json(manifest_path, manifest)
    return OfflineEvaluationResult(manifest_path, manifest, _file_hash(manifest_path), False)


async def register_offline_evaluations(
    session: AsyncSession,
    manifest: Mapping[str, Any],
    *,
    artifact_root: Path,
    subject: str,
    trust_anchor: CareTrustAnchor | None = None,
) -> OfflineEvaluationRegistration:
    verify_offline_evaluation_manifest(
        manifest,
        output_root=artifact_root,
        trust_anchor=trust_anchor,
    )
    created = replayed = 0
    model_ids: list[str] = []
    evaluation_run_ids: list[str] = []
    created_at = datetime.fromisoformat(
        str(manifest["identity"]["created_at"]).replace("Z", "+00:00")
    )
    for model_record in manifest["models"]:
        model_id = str(model_record["model_id"])
        model_ids.append(model_id)
        package = model_record["package"]
        model, was_replayed = await register_model(
            session,
            ModelRegisterRequest(
                model_id=model_id,
                name=str(model_record["model_name"]),
                version=str(model_record["model_version"]),
                kind="anomaly",
                description=(
                    "Deterministic CARE v6 A0/A24 offline anomaly model; prediction truth is "
                    "excluded from training, selection, and threshold calibration."
                ),
                artifact_uri=str(package["artifact_uri"]),
                artifact_sha256=str(package["file_sha256"]),
                content_type="application/json",
                input_schema=canonical_anomaly_input_schema(),
                output_schema=canonical_anomaly_output_schema(),
                metrics={
                    "algorithm": model_record["algorithm"],
                    "evaluation_role": (
                        "baseline" if model_record["algorithm"] == SIMPLE_ALGORITHM else "target"
                    ),
                    "dependency_identity": manifest["identity"]["dependency_identity"],
                    "evaluation_suite_protocol": EVALUATION_SUITE_PROTOCOL,
                    "feature_set_version": manifest["feature_set_version"],
                    "quality_rule_version": manifest["quality_rule_version"],
                    "training_run_id": model_record["training_run_id"],
                    "model_package_sha256": package["document_sha256"],
                    "care_approval": dict(manifest["care_approval"]),
                },
            ),
            content_size_bytes=int(package["size_bytes"]),
            subject=subject,
        )
        created += 0 if was_replayed else 1
        replayed += 1 if was_replayed else 0
        run_id = str(model_record["evaluation_run_id"])
        evaluation_run_ids.append(run_id)
        threshold = model_record["threshold_policy"]
        run, was_replayed = await get_or_create_evaluation_run(
            session,
            BenchmarkEvaluationRunCreateRequest(
                evaluation_run_id=run_id,
                dataset_version_id="care-v6",
                model_id=model.id,
                model_version=model.version,
                run_kind="final-holdout",
                protocol_version=EVALUATION_SUITE_PROTOCOL,
                farm="A",
                feature_set_version=str(manifest["feature_set_version"]),
                quality_rule_version=str(manifest["quality_rule_version"]),
                threshold_policy_version=str(threshold["version"]),
                threshold_policy_sha256=str(threshold["threshold_policy_sha256"]),
                random_seed=int(model_record["random_seed"]),
                input_identity_sha256=str(model_record["input_identity_sha256"]),
                requested_event_count=2,
                extension_data={
                    "algorithm": model_record["algorithm"],
                    "evaluation_role": (
                        "baseline" if model_record["algorithm"] == SIMPLE_ALGORITHM else "target"
                    ),
                    "dependency_identity": manifest["identity"]["dependency_identity"],
                    "component_generalization_protocol": COMPONENT_GENERALIZATION_PROTOCOL,
                    "evaluation_artifact": model_record["evaluation_artifact"],
                    "model_package": package,
                    "prediction_truth_used": False,
                    "care_approval": dict(manifest["care_approval"]),
                },
            ),
            subject=subject,
        )
        created += 0 if was_replayed else 1
        replayed += 1 if was_replayed else 0
        prediction_by_event = {
            int(reference["event_id"]): reference
            for reference in model_record["prediction_artifacts"]
        }
        evaluation_artifact_reference = model_record["evaluation_artifact"]
        evaluation_artifact_uri = str(evaluation_artifact_reference["artifact_uri"])
        # Event details are copied from the verified suite embedded in the manifest.
        for event_result in model_record["event_results"]:
            event_id = int(event_result["event_id"])
            status = str(event_result["status"])
            scored = status == "scored"
            prediction_reference = prediction_by_event.get(event_id)
            event_row, was_replayed = await record_event_result(
                session,
                BenchmarkEventResultCreateRequest(
                    event_result_id=f"{run_id}-event-{event_id}",
                    evaluation_run_id=run.id,
                    event_id=f"care-v6-event-a-{event_id}",
                    status=(
                        "scored" if scored else "unscorable" if status == "unscorable" else "failed"
                    ),
                    scorable=scored,
                    anomaly_detected=(bool(event_result["event_detected"]) if scored else None),
                    care_score=(float(model_record["summary"]["care_score"]) if scored else None),
                    coverage_score=(
                        float(event_result["coverage_f0_5"])
                        if scored and event_result.get("coverage_f0_5") is not None
                        else None
                    ),
                    accuracy_score=(float(event_result["point_accuracy"]) if scored else None),
                    reliability_score=(
                        float(model_record["summary"]["components"]["reliability_event_f0_5"])
                        if scored
                        else None
                    ),
                    earliness_score=(
                        float(event_result["earliness"])
                        if scored and event_result.get("earliness") is not None
                        else None
                    ),
                    prediction_artifact_uri=(
                        str(prediction_reference["artifact_uri"])
                        if prediction_reference is not None
                        else None
                    ),
                    prediction_artifact_sha256=(
                        str(prediction_reference["file_sha256"])
                        if prediction_reference is not None
                        else None
                    ),
                    failure_code=(
                        str(
                            event_result.get("unscorable_reason")
                            or event_result.get("failure_reason")
                        )
                        if not scored
                        else None
                    ),
                    result_sha256=str(event_result["event_result_sha256"]),
                    details={
                        "event_label": event_result.get("event_label"),
                        "failure_type": event_result.get("failure_type"),
                        "care_score_scope": "evaluation-run-aggregate-reference",
                        "reliability_score_scope": "evaluation-run-aggregate-reference",
                        "evaluation_artifact_uri": evaluation_artifact_uri,
                        "evaluation_artifact_sha256": evaluation_artifact_reference["file_sha256"],
                        "point_confusion": {
                            key: event_result.get(key) for key in ("tp", "fp", "tn", "fn")
                        },
                    },
                ),
            )
            del event_row
            created += 0 if was_replayed else 1
            replayed += 1 if was_replayed else 0
        for metric_index, metric in enumerate(model_record["metrics"]):
            metric_name = str(metric["metric_name"])
            metric_row, was_replayed = await record_metric_snapshot(
                session,
                BenchmarkMetricSnapshotCreateRequest(
                    metric_snapshot_id=f"{run_id}-m-{metric_index:02d}",
                    evaluation_run_id=run.id,
                    metric_name=metric_name,
                    protocol_version=str(metric["protocol_version"]),
                    metric_version=str(metric["metric_version"]),
                    value=float(metric["value"]),
                    unit=str(metric["unit"]),
                    numerator=metric["numerator"],
                    denominator=metric["denominator"],
                    is_release_metric=bool(metric["is_release_metric"]),
                    threshold_value=metric["threshold_value"],
                    threshold_direction=metric["threshold_direction"],
                    passed=metric["passed"],
                    details={
                        "evaluation_artifact_sha256": evaluation_artifact_reference["file_sha256"]
                    },
                ),
            )
            del metric_row
            created += 0 if was_replayed else 1
            replayed += 1 if was_replayed else 0
        await complete_evaluation_run(
            session,
            evaluation_run_id=run.id,
            artifact_uri=evaluation_artifact_uri,
            artifact_sha256=str(evaluation_artifact_reference["file_sha256"]),
            completed_at=created_at,
            subject=subject,
        )
    return OfflineEvaluationRegistration(
        created,
        replayed,
        tuple(model_ids),
        tuple(evaluation_run_ids),
    )


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CareOfflineEvaluationError(f"JSON document must be an object: {path}")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CARE v6 A0/A24 offline baselines")
    parser.add_argument("--import-manifest", type=Path, required=True)
    parser.add_argument("--quality-contract", type=Path, required=True)
    parser.add_argument("--import-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--random-seed", type=int, default=DEFAULT_RANDOM_SEED)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = build_offline_evaluations(
        _load_json(args.import_manifest),
        _load_json(args.quality_contract),
        args.import_root,
        args.output_root,
        created_at=args.created_at,
        random_seed=args.random_seed,
    )
    print(
        json.dumps(
            {
                "manifest": str(result.manifest_path),
                "manifest_file_sha256": result.manifest_file_sha256,
                "evaluation_identity_sha256": result.manifest["evaluation_identity_sha256"],
                "models": [model["model_id"] for model in result.manifest["models"]],
                "replayed": result.replayed,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
