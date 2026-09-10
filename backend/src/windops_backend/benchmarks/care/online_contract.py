from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

ONLINE_RUNTIME_SCHEMA_VERSION = "care-v6-online-runtime-config-v1"
ONLINE_SCORE_TRANSFORM_VERSION = "care-score-ratio-to-train-threshold-v1"
ONLINE_THRESHOLD_POLICY_VERSION = "care-rp-online-equivalent-threshold-v1"
ONLINE_WINDOW_SELECTION_VERSION = "care-highest-minimum-valid-three-point-window-v1"
ONLINE_ALERT_POLICY_ID = "care-v6-generic-anomaly-alert"
ONLINE_ALERT_POLICY_VERSION = "care-v6-alert-trigger3-recover2-v1"
ONLINE_COMPONENT = "care-multivariate"


class CareOnlineReplayError(ValueError):
    """Raised when the online replay would drift from its immutable offline evidence."""


def canonical_online_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_online_runtime_configuration(
    value: Mapping[str, object],
    *,
    model_id: str,
    model_version: str,
) -> None:
    actual = value.get("runtime_configuration_sha256")
    unsigned = {key: item for key, item in value.items() if key != "runtime_configuration_sha256"}
    threshold = value.get("online_threshold_policy")
    alert = value.get("alert_policy_template")
    evidence = value.get("evidence_artifact")
    if (
        not isinstance(actual, str)
        or canonical_online_hash(unsigned) != actual
        or value.get("schema_version") != ONLINE_RUNTIME_SCHEMA_VERSION
        or value.get("model_id") != model_id
        or value.get("model_version") != model_version
        or value.get("score_transform_version") != ONLINE_SCORE_TRANSFORM_VERSION
        or value.get("prediction_truth_used") is not False
        or value.get("release_claim") != "development-vertical-slice-only"
        or not isinstance(threshold, Mapping)
        or not isinstance(alert, Mapping)
        or not isinstance(evidence, Mapping)
    ):
        raise CareOnlineReplayError("online runtime configuration identity is invalid")
    threshold_actual = threshold.get("threshold_policy_sha256")
    threshold_unsigned = {
        key: item for key, item in threshold.items() if key != "threshold_policy_sha256"
    }
    if (
        canonical_online_hash(threshold_unsigned) != threshold_actual
        or threshold.get("value") != 0.5
        or threshold.get("version") != ONLINE_THRESHOLD_POLICY_VERSION
        or threshold.get("prediction_truth_used") is not False
        or alert.get("policy_id") != ONLINE_ALERT_POLICY_ID
        or alert.get("policy_version") != ONLINE_ALERT_POLICY_VERSION
        or alert.get("component") != ONLINE_COMPONENT
        or alert.get("trigger_threshold") != 0.5
        or alert.get("consecutive_trigger_windows") != 3
        or alert.get("consecutive_recovery_windows") != 2
        or alert.get("prediction_truth_used") is not False
    ):
        raise CareOnlineReplayError("online threshold or alert policy drifted")
    uri = evidence.get("uri")
    digest = evidence.get("sha256")
    if (
        not isinstance(uri, str)
        or not (uri.startswith("minio://") or uri.startswith("https://"))
        or not isinstance(digest, str)
        or len(digest) != 64
    ):
        raise CareOnlineReplayError("online runtime evidence reference is invalid")


__all__ = [
    "ONLINE_ALERT_POLICY_ID",
    "ONLINE_ALERT_POLICY_VERSION",
    "ONLINE_COMPONENT",
    "ONLINE_RUNTIME_SCHEMA_VERSION",
    "ONLINE_SCORE_TRANSFORM_VERSION",
    "ONLINE_THRESHOLD_POLICY_VERSION",
    "ONLINE_WINDOW_SELECTION_VERSION",
    "CareOnlineReplayError",
    "canonical_online_hash",
    "verify_online_runtime_configuration",
]
