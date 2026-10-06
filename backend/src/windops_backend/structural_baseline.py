"""Bounded, explainable environmental screening with explicit applicability gates."""

import math
from typing import Any

import numpy as np

BASELINE_CONTRACT = "openvigil.environmental-ols.v1"


def modal_assurance(left: list[dict[str, float]], right: list[dict[str, float]]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    a = [complex(x["real"], x["imag"]) for x in left]
    b = [complex(x["real"], x["imag"]) for x in right]
    denominator = sum(abs(x) ** 2 for x in a) * sum(abs(x) ** 2 for x in b)
    return (
        min(
            1.0,
            float(
                abs(sum(x.conjugate() * y for x, y in zip(a, b, strict=True))) ** 2 / denominator
            ),
        )
        if denominator > 0
        else 0.0
    )


def measurement_signature(run: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": run["method"],
        "config": run["config"],
        "algorithm": (run.get("result") or {}).get("algorithm", {}),
        "channels": record["channel_snapshot"],
        "sample_rate_hz": record["sample_rate_hz"],
        "sample_count": record["sample_count"],
    }


def fit_environmental_baseline(
    rows: list[dict[str, Any]],
    reference: dict[str, Any],
    features: list[str],
    minimum_mac: float,
    maximum_relative_frequency_shift: float,
    screening_sigma: float,
) -> dict[str, Any]:
    """Last 20% of chronological windows are retained for independent validation."""
    if not 30 <= len(rows) <= 256:
        raise ValueError("baseline requires 30 to 256 confirmed healthy windows")
    state = reference["environment"].get("operating_state")
    if state not in {"stopped", "running"}:
        raise ValueError("healthy windows must have an explicit operating state")
    for row in rows:
        if row["signature"] != reference["signature"]:
            raise ValueError(
                "baseline requires identical method, channel, calibration and acquisition versions"
            )
        if row["source_kind"] != reference["source_kind"]:
            raise ValueError("field and non-field inputs cannot share a baseline")
        if row["environment"].get("operating_state") != state:
            raise ValueError("operating states cannot be combined in a baseline")
        if row["quality"].get("status") != "candidate":
            raise ValueError("harmonic or rejected observations cannot train a baseline")
        if modal_assurance(reference["mode_shape"], row["mode_shape"]) < minimum_mac:
            raise ValueError("training mode shapes do not match the reference")
        if (
            abs(row["frequency_hz"] / reference["frequency_hz"] - 1)
            > maximum_relative_frequency_shift
        ):
            raise ValueError("training frequencies exceed the approved matching range")
        if any(row["environment"].get(f) is None for f in features):
            raise ValueError("baseline environment features are missing")
    ordered = sorted(rows, key=lambda row: row["started_at"])
    if len({r["record_id"] for r in ordered}) != len(ordered):
        raise ValueError("baseline needs independent acquisition windows, one mode per window")
    if any(a["ended_at"] > b["started_at"] for a, b in zip(ordered, ordered[1:], strict=False)):
        raise ValueError("baseline windows must not overlap")
    x = np.asarray([[float(r["environment"][f]) for f in features] for r in ordered])
    y = np.asarray([r["frequency_hz"] for r in ordered], dtype=float)
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("baseline values must be finite")
    count = len(ordered) * 4 // 5
    center, scale = x[:count].mean(axis=0), x[:count].std(axis=0)
    if np.any(scale <= np.finfo(float).eps):
        raise ValueError("baseline training features have no variation")
    design = np.column_stack([np.ones(len(x)), (x - center) / scale])
    train = design[:count]
    if np.linalg.matrix_rank(train) != train.shape[1] or np.linalg.cond(train) > 1e8:
        raise ValueError("baseline features are collinear or ill-conditioned")
    coefficients, *_ = np.linalg.lstsq(train, y[:count], rcond=None)
    training_error = y[:count] - train @ coefficients
    validation_error = y[count:] - design[count:] @ coefficients
    residual_scale = max(
        float(np.sqrt(np.sum(training_error**2) / (count - train.shape[1]))),
        float(np.sqrt(np.mean(validation_error**2))),
    )
    resolution = float(reference["uncertainty"].get("frequency_bin_width_hz", 0))
    if resolution <= 0 or not math.isfinite(resolution):
        raise ValueError("baseline reference must preserve spectral resolution")
    return {
        "contract": BASELINE_CONTRACT,
        "features": features,
        "center": center.tolist(),
        "scale": scale.tolist(),
        "coefficients": coefficients.tolist(),
        "inverse_information": np.linalg.inv(train.T @ train).tolist(),
        "residual_scale_hz": residual_scale,
        "frequency_bin_width_hz": resolution,
        "domain": {
            f: {"min": float(x[:, i].min()), "max": float(x[:, i].max())}
            for i, f in enumerate(features)
        },
        "operating_state": state,
        "source_kind": reference["source_kind"],
        "signature": reference["signature"],
        "reference_frequency_hz": reference["frequency_hz"],
        "reference_mode_shape": reference["mode_shape"],
        "minimum_mac": minimum_mac,
        "maximum_relative_frequency_shift": maximum_relative_frequency_shift,
        "screening_sigma": screening_sigma,
        "validation": {
            "split": "chronological_holdout_20_percent",
            "training_count": count,
            "validation_count": len(ordered) - count,
            "rmse_hz": float(np.sqrt(np.mean(validation_error**2))),
            "maximum_absolute_error_hz": float(np.max(np.abs(validation_error))),
        },
        "training_window": {"start": ordered[0]["started_at"], "end": ordered[-1]["ended_at"]},
        "training_sources": [
            {
                "modal_id": r["id"],
                "record_id": r["record_id"],
                "artifact_sha256": r["artifact_sha256"],
            }
            for r in ordered
        ],
        "uncertainty": {
            "status": "partial",
            "reason": (
                "environmental_residual_and_resolution_only; "
                "calibration_and_model_bias_not_quantified"
            ),
        },
        "qualification": "requires_field_validation",
    }


def compare_to_baseline(
    model: dict[str, Any], run: dict[str, Any], record: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "not_applicable",
        "exclusions": [],
        "damage_probability": None,
    }
    reasons = result["exclusions"]
    if model["contract"] != BASELINE_CONTRACT:
        reasons.append("unsupported_baseline_version")
        return result
    if measurement_signature(run, record) != model["signature"]:
        reasons.append("method_channel_or_calibration_version_changed")
    if record["source_kind"] != model["source_kind"]:
        reasons.append("source_kind_changed")
    if record["environment"].get("operating_state") != model["operating_state"]:
        reasons.append("operating_state_out_of_domain")
    values = []
    for feature in model["features"]:
        value = record["environment"].get(feature)
        bounds = model["domain"][feature]
        if value is None or not math.isfinite(value) or not bounds["min"] <= value <= bounds["max"]:
            reasons.append(f"{feature}_out_of_domain")
        else:
            values.append(float(value))
    if reasons:
        return result
    candidates = []
    for mode in (run.get("result") or {}).get("modes", []):
        mac = modal_assurance(model["reference_mode_shape"], mode["mode_shape"])
        if (
            mode["quality"].get("status") == "candidate"
            and mac >= model["minimum_mac"]
            and abs(mode["frequency_hz"] / model["reference_frequency_hz"] - 1)
            <= model["maximum_relative_frequency_shift"]
        ):
            candidates.append((mode, mac))
    if len(candidates) != 1:
        reasons.append("no_unique_matching_mode")
        return result
    mode, mac = candidates[0]
    vector = np.concatenate([[1.0], (np.asarray(values) - model["center"]) / model["scale"]])
    expected = float(vector @ np.asarray(model["coefficients"]))
    residual = float(mode["frequency_hz"] - expected)
    predictive_scale = model["residual_scale_hz"] * math.sqrt(
        1 + float(vector @ np.asarray(model["inverse_information"]) @ vector)
    )
    threshold = max(model["screening_sigma"] * predictive_scale, model["frequency_bin_width_hz"])
    return {
        **result,
        "status": "requires_review" if abs(residual) > threshold else "within_screening_range",
        "mode_mac": mac,
        "observed_frequency_hz": mode["frequency_hz"],
        "expected_frequency_hz": expected,
        "raw_change_hz": mode["frequency_hz"] - model["reference_frequency_hz"],
        "environmental_residual_hz": residual,
        "screening_threshold_hz": threshold,
        "uncertainty": model["uncertainty"],
        "qualification": model["qualification"],
        "recommendation": "engineering_review_and_repeat_measurement",
        "persistence": "not_assessed",
    }
