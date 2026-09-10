from __future__ import annotations

import hashlib
import importlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from windops_backend.benchmarks.care.evaluation import (
    CareOfflineEvaluationError,
    score_offline_model_package,
    verify_offline_model_package,
)
from windops_backend.benchmarks.care.importer import verify_minimal_import_manifest
from windops_backend.benchmarks.care.online_contract import (
    ONLINE_ALERT_POLICY_ID,
    ONLINE_ALERT_POLICY_VERSION,
    ONLINE_COMPONENT,
    ONLINE_RUNTIME_SCHEMA_VERSION,
    ONLINE_SCORE_TRANSFORM_VERSION,
    ONLINE_THRESHOLD_POLICY_VERSION,
    ONLINE_WINDOW_SELECTION_VERSION,
    CareOnlineReplayError,
    canonical_online_hash,
    verify_online_runtime_configuration,
)
from windops_backend.benchmarks.care.replay import ReplaySourceRow, ReplayVariable
from windops_backend.benchmarks.care.scoring import (
    CalibrationInput,
    ThresholdPolicy,
    fixed_threshold_policy,
    verify_prediction_artifact,
)
from windops_backend.config import ModelInferenceTarget

parquet: Any = importlib.import_module("pyarrow.parquet")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_local_path(root: Path, relative: str) -> Path:
    logical = PurePosixPath(relative)
    if logical.is_absolute() or ".." in logical.parts:
        raise CareOnlineReplayError("CARE replay artifact path is unsafe")
    resolved_root = root.resolve(strict=True)
    target = resolved_root.joinpath(*logical.parts).resolve(strict=True)
    if not target.is_relative_to(resolved_root):
        raise CareOnlineReplayError("CARE replay artifact escaped its declared root")
    return target


def normalized_online_score(raw_score: float, offline_threshold: float) -> float:
    """Map a non-negative offline score to 0..1 without changing its binary boundary."""

    if (
        isinstance(raw_score, bool)
        or isinstance(offline_threshold, bool)
        or not math.isfinite(raw_score)
        or not math.isfinite(offline_threshold)
        or raw_score < 0
        or offline_threshold <= 0
    ):
        raise CareOnlineReplayError("online score normalization requires finite positive controls")
    return raw_score / (raw_score + offline_threshold)


def online_threshold_policy(package: Mapping[str, Any]) -> ThresholdPolicy:
    verify_offline_model_package(package)
    offline = package["threshold_policy"]
    return fixed_threshold_policy(
        CalibrationInput(
            source_split=str(offline["calibration_split"]),
            anomaly_scores=(float(offline["value"]),),
            source_run_id=str(offline["calibration_run_id"]),
        ),
        value=0.5,
        version=ONLINE_THRESHOLD_POLICY_VERSION,
        strategy=(
            f"{ONLINE_SCORE_TRANSFORM_VERSION}; equivalent to immutable offline policy "
            f"{offline['threshold_policy_sha256']}"
        ),
    )


@dataclass(frozen=True, slots=True)
class OnlineWindowSelection:
    event_id: int
    start_source_row_id: int
    end_source_row_id: int
    point_count: int
    minimum_score: float
    mean_score: float
    binary_predictions: tuple[bool, ...]
    selection_version: str = ONLINE_WINDOW_SELECTION_VERSION
    prediction_truth_used: bool = False

    def to_document(self) -> dict[str, Any]:
        return {
            "selection_version": self.selection_version,
            "event_id": self.event_id,
            "start_source_row_id": self.start_source_row_id,
            "end_source_row_id": self.end_source_row_id,
            "point_count": self.point_count,
            "minimum_score": self.minimum_score,
            "mean_score": self.mean_score,
            "binary_predictions": list(self.binary_predictions),
            "prediction_truth_used": self.prediction_truth_used,
        }


def select_online_window(
    prediction_artifact: Mapping[str, Any],
    *,
    width: int = 3,
) -> OnlineWindowSelection:
    """Select one bounded stress window using only the frozen truth-free predictions."""

    verify_prediction_artifact(prediction_artifact)
    if prediction_artifact.get("prediction_truth_present") is not False:
        raise CareOnlineReplayError("online window selection cannot access prediction truth")
    if width < 1 or width > 32:
        raise CareOnlineReplayError("online replay window width must be within 1..32")
    raw_points = prediction_artifact.get("points")
    if not isinstance(raw_points, list):  # pragma: no cover - verifier already proves this
        raise CareOnlineReplayError("prediction points are unavailable")
    candidates: list[tuple[float, float, int, tuple[Mapping[str, Any], ...]]] = []
    for offset in range(0, len(raw_points) - width + 1):
        window = tuple(raw_points[offset : offset + width])
        if not all(isinstance(point, Mapping) for point in window):
            continue
        row_ids = [int(point["source_row_id"]) for point in window]
        if row_ids != list(range(row_ids[0], row_ids[0] + width)) or not all(
            point.get("valid_point_mask") is True for point in window
        ):
            continue
        scores = [float(point["anomaly_score"]) for point in window]
        candidates.append((min(scores), sum(scores) / width, -row_ids[0], window))
    if not candidates:
        raise CareOnlineReplayError("prediction artifact has no contiguous valid replay window")
    minimum, mean, _negative_start, selected = max(candidates, key=lambda value: value[:3])
    start = int(selected[0]["source_row_id"])
    return OnlineWindowSelection(
        event_id=int(prediction_artifact["event_id"]),
        start_source_row_id=start,
        end_source_row_id=start + width - 1,
        point_count=width,
        minimum_score=minimum,
        mean_score=mean,
        binary_predictions=tuple(bool(point["binary_prediction"]) for point in selected),
    )


def replay_variables_from_import(
    import_manifest: Mapping[str, Any],
    import_root: Path,
    *,
    feature_columns: Sequence[str],
) -> tuple[ReplayVariable, ...]:
    verify_minimal_import_manifest(import_manifest)
    approved = tuple(str(value) for value in import_manifest.get("model_input_columns", []))
    if tuple(feature_columns) != approved:
        raise CareOnlineReplayError("online replay features drifted from the minimal import")
    reference = import_manifest.get("mapping_artifact")
    if not isinstance(reference, Mapping):
        raise CareOnlineReplayError("minimal import has no governed mapping artifact")
    path = _safe_local_path(import_root, str(reference.get("local_relative_path", "")))
    if _file_hash(path) != reference.get("file_sha256"):
        raise CareOnlineReplayError("CARE mapping artifact file hash mismatch")
    mapping = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(mapping, Mapping):
        raise CareOnlineReplayError("CARE mapping artifact is malformed")
    actual_document_hash = mapping.get("document_sha256")
    unsigned_mapping = {key: value for key, value in mapping.items() if key != "document_sha256"}
    if actual_document_hash != reference.get(
        "document_sha256"
    ) or actual_document_hash != canonical_online_hash(unsigned_mapping):
        raise CareOnlineReplayError("CARE mapping artifact document hash mismatch")
    raw_mappings = mapping.get("mappings")
    if not isinstance(raw_mappings, list):
        raise CareOnlineReplayError("CARE mapping artifact has no mappings")
    by_source = {
        str(value["source_column"]): value
        for value in raw_mappings
        if isinstance(value, Mapping) and isinstance(value.get("source_column"), str)
    }
    variables: list[ReplayVariable] = []
    for feature in feature_columns:
        value = by_source.get(feature)
        semantics = value.get("quality_semantics") if value is not None else None
        if (
            not isinstance(value, Mapping)
            or value.get("statistic") != "average"
            or not isinstance(semantics, Mapping)
            or semantics.get("enabled_by_default") is not True
            or not isinstance(semantics.get("normalized_unit"), str)
        ):
            raise CareOnlineReplayError(f"feature {feature} is not an approved Avg replay signal")
        variables.append(ReplayVariable(feature, str(semantics["normalized_unit"])))
    return tuple(sorted(variables, key=lambda value: value.short_id))


def load_replay_rows(
    import_manifest: Mapping[str, Any],
    import_root: Path,
    *,
    event_id: int,
    start_source_row_id: int,
    end_source_row_id: int,
    variables: Sequence[ReplayVariable],
) -> tuple[ReplaySourceRow, ...]:
    """Read only the selected prediction rows and approved Avg columns from Parquet."""

    verify_minimal_import_manifest(import_manifest)
    if end_source_row_id < start_source_row_id:
        raise CareOnlineReplayError("online replay row window is reversed")
    event = next(
        (
            value
            for value in import_manifest.get("events", [])
            if isinstance(value, Mapping) and value.get("event_id") == event_id
        ),
        None,
    )
    if event is None:
        raise CareOnlineReplayError("minimal import has no selected replay event")
    data = event.get("parquet", {}).get("data", {})
    if not isinstance(data, Mapping):
        raise CareOnlineReplayError("minimal import event has no Parquet data artifact")
    path = _safe_local_path(import_root, str(data.get("local_relative_path", "")))
    if _file_hash(path) != data.get("file_sha256"):
        raise CareOnlineReplayError("CARE replay Parquet content hash mismatch")
    feature_columns = [value.canonical_variable for value in variables]
    columns = ["time_stamp", "id", "train_test", "status_type_id", *feature_columns]
    table = parquet.read_table(
        path,
        columns=columns,
        filters=[
            ("id", ">=", start_source_row_id),
            ("id", "<=", end_source_row_id),
        ],
    )
    expected_count = end_source_row_id - start_source_row_id + 1
    if table.num_rows != expected_count or table.column_names != columns:
        raise CareOnlineReplayError("CARE replay Parquet projection is incomplete")
    row_ids = [int(value) for value in table["id"].to_pylist()]
    if row_ids != list(range(start_source_row_id, end_source_row_id + 1)):
        raise CareOnlineReplayError("CARE replay rows are not contiguous")
    splits = [str(value) for value in table["train_test"].to_pylist()]
    if set(splits) != {"prediction"}:
        raise CareOnlineReplayError("online replay may read only the prediction split")
    timestamps = table["time_stamp"].to_pylist()
    statuses = table["status_type_id"].to_pylist()
    result: list[ReplaySourceRow] = []
    for index, row_id in enumerate(row_ids):
        status = statuses[index]
        if isinstance(status, float) and status.is_integer():
            status = int(status)
        timestamp = timestamps[index]
        timestamp_text = str(
            timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp
        )
        values = tuple(
            sorted(
                (
                    variable.canonical_variable,
                    float(table[variable.canonical_variable][index].as_py()),
                )
                for variable in variables
            )
        )
        result.append(
            ReplaySourceRow(
                source_row_id=row_id,
                source_time_stamp=timestamp_text,
                anonymous_observed_at=timestamp_text,
                status_type_id=str(status),
                values=values,
                source_interval_seconds=600.0,
            )
        )
    return tuple(result)


def build_online_runtime_configuration(
    package: Mapping[str, Any],
    *,
    evaluation_run_id: str,
    evidence_artifact_uri: str,
    evidence_artifact_sha256: str,
    primary_variable: str,
    related_variables: Sequence[str],
) -> dict[str, Any]:
    verify_offline_model_package(package)
    threshold = online_threshold_policy(package)
    payload: dict[str, Any] = {
        "schema_version": ONLINE_RUNTIME_SCHEMA_VERSION,
        "model_id": package["model_id"],
        "model_version": package["model_version"],
        "model_package_sha256": package["model_package_sha256"],
        "evaluation_run_id": evaluation_run_id,
        "feature_set_version": package["feature_set_version"],
        "quality_rule_version": package["quality_rule_version"],
        "score_transform_version": ONLINE_SCORE_TRANSFORM_VERSION,
        "offline_threshold_policy_sha256": package["threshold_policy"]["threshold_policy_sha256"],
        "online_threshold_policy": threshold.to_dict(),
        "evidence_artifact": {
            "uri": evidence_artifact_uri,
            "sha256": evidence_artifact_sha256,
        },
        "alert_policy_template": {
            "policy_id": ONLINE_ALERT_POLICY_ID,
            "policy_version": ONLINE_ALERT_POLICY_VERSION,
            "component": ONLINE_COMPONENT,
            "trigger_threshold": threshold.value,
            "consecutive_trigger_windows": 3,
            "recovery_threshold": 0.45,
            "consecutive_recovery_windows": 2,
            "cooldown_seconds": 3600,
            "missing_window_behavior": "reset",
            "uncertain_quality_behavior": "hold",
            "enabled": True,
            "prediction_truth_used": False,
        },
        "mission_analysis_profile": {
            "component": ONLINE_COMPONENT,
            "primary_variable": primary_variable,
            "related_variables": list(related_variables),
            "failure_mode_hint": "multivariate anomaly requiring governed investigation",
            "knowledge_query": "wind turbine multivariate anomaly inspection guidance",
        },
        "release_claim": "development-vertical-slice-only",
        "prediction_truth_used": False,
    }
    return {**payload, "runtime_configuration_sha256": canonical_online_hash(payload)}


class CareJsonPackageInferenceClient:
    """Deterministic inference adapter for the verified JSON package; no arbitrary code runs."""

    def __init__(self, package: Mapping[str, Any]) -> None:
        verify_offline_model_package(package)
        self.package = dict(package)
        self.call_count = 0

    async def predict(
        self,
        target: ModelInferenceTarget,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int]:
        del target
        started = time.perf_counter()
        model = payload.get("model")
        inputs = payload.get("inputs")
        if (
            not isinstance(model, Mapping)
            or model.get("id") != self.package["model_id"]
            or model.get("version") != self.package["model_version"]
            or not isinstance(inputs, Mapping)
            or not idempotency_key.startswith("windops:anomaly:")
            or any(key in inputs for key in ("ground_truth", "event_label", "failure_type"))
        ):
            raise CareOnlineReplayError("online inference request identity is invalid")
        signals = inputs.get("signals")
        if not isinstance(signals, list) or not signals:
            raise CareOnlineReplayError("online inference request has no signals")
        sequences = {
            signal.get("source_sequence") for signal in signals if isinstance(signal, Mapping)
        }
        if len(sequences) != 1 or len(signals) != len(self.package["feature_columns"]):
            raise CareOnlineReplayError("online inference requires one complete feature point")
        feature_values: dict[str, float] = {}
        for signal in signals:
            if not isinstance(signal, Mapping):
                raise CareOnlineReplayError("online inference signal is malformed")
            variable = signal.get("variable")
            value = signal.get("value")
            if (
                not isinstance(variable, str)
                or variable in feature_values
                or isinstance(value, bool)
                or not isinstance(value, int | float)
            ):
                raise CareOnlineReplayError("online inference feature identity is invalid")
            feature_values[variable] = float(value)
        raw_score = score_offline_model_package(
            self.package,
            event_id=int(inputs["event_id"]),
            feature_values=feature_values,
        )
        offline_threshold = float(self.package["threshold_policy"]["value"])
        score = normalized_online_score(raw_score, offline_threshold)
        binary = raw_score > offline_threshold
        if binary != (score > 0.5):  # pragma: no cover - algebraic invariant
            raise CareOfflineEvaluationError("online score transform changed the binary result")
        self.call_count += 1
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        return {
            "anomaly_score": score,
            "binary_prediction": binary,
            "component": ONLINE_COMPONENT,
        }, latency_ms


__all__ = [
    "ONLINE_ALERT_POLICY_ID",
    "ONLINE_ALERT_POLICY_VERSION",
    "ONLINE_COMPONENT",
    "ONLINE_RUNTIME_SCHEMA_VERSION",
    "ONLINE_SCORE_TRANSFORM_VERSION",
    "ONLINE_THRESHOLD_POLICY_VERSION",
    "ONLINE_WINDOW_SELECTION_VERSION",
    "CareJsonPackageInferenceClient",
    "CareOnlineReplayError",
    "OnlineWindowSelection",
    "build_online_runtime_configuration",
    "load_replay_rows",
    "normalized_online_score",
    "online_threshold_policy",
    "replay_variables_from_import",
    "select_online_window",
    "verify_online_runtime_configuration",
]
