"""Analytical, non-field datasets validate regression and applicability independently of FDD."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from windops_backend.structural_baseline import (
    compare_to_baseline,
    fit_environmental_baseline,
    modal_assurance,
)

SHAPE = [{"real": 1.0, "imag": 0.0}, {"real": 0.5, "imag": 0.0}]
SIGNATURE = {
    "method": "pyoma2_fdd_v1",
    "config": {},
    "algorithm": {},
    "channels": [],
    "sample_rate_hz": 16,
    "sample_count": 4096,
}


def healthy_rows():
    start = datetime(2026, 10, 1, tzinfo=UTC)
    # Repeat the environmental range across chronological train/holdout windows.
    return [
        {
            "id": f"mode-{i}",
            "record_id": f"record-{i}",
            "started_at": (start + timedelta(hours=i)).isoformat(),
            "ended_at": (start + timedelta(hours=i, minutes=5)).isoformat(),
            "environment": {"operating_state": "stopped", "temperature_c": float(i % 10)},
            "signature": deepcopy(SIGNATURE),
            "source_kind": "synthetic_test",
            "quality": {"status": "candidate"},
            "mode_shape": deepcopy(SHAPE),
            "frequency_hz": 0.5 + 0.001 * (i % 10),
            "uncertainty": {"frequency_bin_width_hz": 0.002},
            "artifact_sha256": f"{i:064x}",
        }
        for i in range(40)
    ]


def baseline(rows=None):
    rows = rows or healthy_rows()
    return fit_environmental_baseline(rows, rows[0], ["temperature_c"], 0.9, 0.2, 3)


def subject(frequency=0.505):
    return (
        {
            "method": "pyoma2_fdd_v1",
            "config": {},
            "result": {
                "modes": [
                    {
                        "frequency_hz": frequency,
                        "quality": {"status": "candidate"},
                        "mode_shape": deepcopy(SHAPE),
                    }
                ]
            },
        },
        {
            "channel_snapshot": [],
            "sample_rate_hz": 16,
            "sample_count": 4096,
            "source_kind": "synthetic_test",
            "environment": {"operating_state": "stopped", "temperature_c": 5},
        },
    )


def test_regression_recovers_known_temperature_relationship_and_uses_holdout():
    model = baseline()
    assert model["validation"]["training_count"] == 32
    assert model["validation"]["validation_count"] == 8
    assert model["validation"]["rmse_hz"] < 1e-12
    run, record = subject()
    result = compare_to_baseline(model, run, record)
    assert result["expected_frequency_hz"] == pytest.approx(0.505)
    assert result["environmental_residual_hz"] == pytest.approx(0, abs=1e-12)
    assert result["raw_change_hz"] == pytest.approx(0.005)
    assert result["status"] == "within_screening_range"
    assert result["damage_probability"] is None
    assert result["uncertainty"]["status"] == "partial"
    drift, record = subject(0.49)
    assert compare_to_baseline(model, drift, record)["status"] == "requires_review"


def test_mac_is_phase_invariant_and_rejects_orthogonal_and_zero_shapes():
    rotated = [{"real": 0, "imag": 1}, {"real": 0, "imag": 0.5}]
    assert modal_assurance(SHAPE, rotated) == pytest.approx(1)
    assert modal_assurance(
        SHAPE, [{"real": -0.5, "imag": 0}, {"real": 1, "imag": 0}]
    ) == pytest.approx(0)
    assert modal_assurance(SHAPE, [{"real": 0, "imag": 0}, {"real": 0, "imag": 0}]) == 0


@pytest.mark.parametrize(
    "challenge",
    ["calibration", "state", "missing", "out_of_domain", "harmonic", "ambiguous", "source_kind"],
)
def test_live_applicability_rejects_incompatible_inputs(challenge):
    run, record = subject()
    if challenge == "calibration":
        record["channel_snapshot"] = [{"calibration_version": "changed"}]
    elif challenge == "state":
        record["environment"]["operating_state"] = "running"
    elif challenge == "missing":
        record["environment"]["temperature_c"] = None
    elif challenge == "out_of_domain":
        record["environment"]["temperature_c"] = 12
    elif challenge == "harmonic":
        run["result"]["modes"][0]["quality"]["status"] = "harmonic_overlap"
    elif challenge == "source_kind":
        record["source_kind"] = "field_measurement"
    else:
        run["result"]["modes"].append(deepcopy(run["result"]["modes"][0]))
    result = compare_to_baseline(baseline(), run, record)
    assert result["status"] == "not_applicable"
    assert result["exclusions"]
    assert "expected_frequency_hz" not in result


@pytest.mark.parametrize(
    "challenge",
    [
        "overlap",
        "duplicate_window",
        "collinear",
        "mixed_source",
        "harmonic",
        "shape",
        "version",
        "missing",
    ],
)
def test_baseline_refuses_invalid_healthy_training(challenge):
    rows = healthy_rows()
    if challenge == "overlap":
        rows[1]["started_at"] = rows[0]["started_at"]
    elif challenge == "duplicate_window":
        rows[1]["record_id"] = rows[0]["record_id"]
    elif challenge == "collinear":
        for row in rows:
            row["environment"]["temperature_c"] = 1
    elif challenge == "mixed_source":
        rows[1]["source_kind"] = "field_measurement"
    elif challenge == "harmonic":
        rows[1]["quality"]["status"] = "harmonic_overlap"
    elif challenge == "shape":
        rows[1]["mode_shape"][1]["real"] = -3
    elif challenge == "version":
        rows[1]["signature"]["method"] = "unknown"
    else:
        rows[1]["environment"]["temperature_c"] = None
    with pytest.raises(ValueError):
        baseline(rows)
