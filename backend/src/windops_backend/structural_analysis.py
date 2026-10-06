"""Bounded signal quality and pyOMA2 FDD screening, executed only by a worker."""

from collections.abc import Callable
from importlib.metadata import version
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, Field

from windops_backend.schema_structural import Finite, Identity, StructuralRequest
from windops_backend.structural_contract import (
    ANALYSIS_CONTRACT_VERSION,
    SCIENTIFIC_VERSIONS,
    algorithm_identity,
)


class WaveformChannel(StructuralRequest):
    channel_id: Identity
    unit: Literal["m/s2", "g"]
    offset_seconds: Finite
    samples: Annotated[list[Finite | None], Field(min_length=16, max_length=262144)]


class WaveformArtifact(StructuralRequest):
    schema_version: Literal["openvigil.waveform.v1"]
    turbine_id: Identity
    started_at: AwareDatetime
    sample_rate_hz: Annotated[float, Field(gt=0, le=100000, allow_inf_nan=False)]
    channels: Annotated[list[WaveformChannel], Field(min_length=1, max_length=16)]


def analyze_waveform(
    content: bytes, record: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    # Scientific imports are intentionally lazy; the API image has no OMA stack.
    import numpy as np

    artifact = WaveformArtifact.model_validate_json(content, strict=True)
    if sum(len(channel.samples) for channel in artifact.channels) > 1048576:
        raise ValueError("signal exceeds the one-million-sample computation bound")
    fs = float(record["sample_rate_hz"])
    n = int(record["sample_count"])
    channels = artifact.channels
    exclusions: list[str] = []
    warnings: list[str] = ["no_field_qualification", "healthy_environment_baseline_missing"]
    if artifact.turbine_id != record["turbine_id"]:
        exclusions.append("artifact_asset_mismatch")
    if artifact.started_at.isoformat() != record["started_at"]:
        # Compare instants, including equivalent UTC serialization.
        from datetime import datetime

        if artifact.started_at != datetime.fromisoformat(record["started_at"]):
            exclusions.append("artifact_time_mismatch")
    if artifact.sample_rate_hz != fs:
        exclusions.append("artifact_sample_rate_mismatch")
    if [c.channel_id for c in channels] != record["channel_ids"]:
        exclusions.append("artifact_channel_mismatch")
    if len(channels) < 2:
        exclusions.append("fdd_requires_multiple_channels")
    if any(len(c.samples) != n for c in channels):
        exclusions.append("sample_count_mismatch")
    if n < 2 * config["nperseg"]:
        exclusions.append("insufficient_spectral_segments")
    if config["max_frequency_hz"] >= fs / 2:
        exclusions.append("frequency_band_exceeds_nyquist")
    if n / fs * config["min_frequency_hz"] < 3:
        exclusions.append("window_has_fewer_than_three_low_band_cycles")
    from datetime import datetime

    start = datetime.fromisoformat(record["started_at"])
    end = datetime.fromisoformat(record["ended_at"])
    sources = {c["synchronization_source"] for c in record["channel_snapshot"]}
    if len(sources) != 1:
        exclusions.append("synchronization_sources_differ")
    channel_quality: list[dict[str, Any]] = []
    arrays = []
    snapshot_by_id = {c["id"]: c for c in record["channel_snapshot"]}
    for channel in channels:
        meta = snapshot_by_id.get(channel.channel_id)
        if meta is None:
            continue
        failures: list[str] = []
        if meta["quantity"] != "acceleration" or channel.unit != meta["unit"]:
            failures.append("quantity_or_unit_mismatch")
        if (
            datetime.fromisoformat(meta["calibration_at"]) > start
            or datetime.fromisoformat(meta["calibration_valid_until"]) < end
        ):
            failures.append("calibration_does_not_cover_window")
        if abs(channel.offset_seconds) > min(0.001, 0.1 / fs):
            failures.append("synchronization_offset_exceeded")
        values = np.asarray([np.nan if x is None else x for x in channel.samples], dtype=float)
        missing = int(np.count_nonzero(~np.isfinite(values)))
        if missing:
            failures.append("missing_or_nonfinite_samples")
        elif len(values):
            if np.ptp(values) <= np.finfo(float).eps * max(1.0, abs(float(values.mean()))):
                failures.append("flat_channel")
            if np.any(values <= meta["range_min"]) or np.any(values >= meta["range_max"]):
                failures.append("saturated_or_out_of_range")
        arrays.append(values * (9.80665 if channel.unit == "g" else 1.0))
        channel_quality.append(
            {
                "channel_id": channel.channel_id,
                "missing_count": missing,
                "exclusions": failures,
                "usable": not failures,
            }
        )
        exclusions.extend(f"{channel.channel_id}:{failure}" for failure in failures)
    result: dict[str, Any] = {
        "algorithm": {
            **algorithm_identity(),
            "versions": {name: version(name) for name in SCIENTIFIC_VERSIONS},
            "config": config,
        },
        "schema_version": ANALYSIS_CONTRACT_VERSION,
        "quality": {
            "usable": not exclusions,
            "exclusions": exclusions,
            "channels": channel_quality,
            "policy_version": "strict-synchronous-window.v1",
        },
        "source_kind": record["source_kind"],
        "modes": [],
        "engineering_status": "insufficient_data" if exclusions else "requires_engineering_review",
        "warnings": warnings,
        "absolute_prestress": {
            "status": "unavailable",
            "reason": "tower_modal_signal_is_not_cable_force",
        },
    }
    if exclusions:
        return result
    if result["algorithm"]["versions"] != SCIENTIFIC_VERSIONS:
        raise RuntimeError("structural worker numerical versions do not match the frozen contract")
    from pyoma2.functions.fdd import SD_est, SD_svalsvec
    from scipy.signal import find_peaks  # type: ignore[import-untyped]

    # pyOMA2's numerical API has no annotations; give its boundary a typed
    # return contract while retaining the implementation and shape checks.
    estimate: Callable[..., tuple[Any, Any]] = SD_est
    decompose: Callable[[Any], tuple[Any, Any]] = SD_svalsvec

    matrix = np.stack(arrays)
    frequencies, spectra = estimate(
        matrix, matrix, 1 / fs, config["nperseg"], method="per", pov=0.5
    )
    singular_values, shapes = decompose(spectra)
    powers = np.asarray(singular_values[0, 0, :] ** 2, dtype=float)
    in_band = (frequencies >= config["min_frequency_hz"]) & (
        frequencies <= config["max_frequency_hz"]
    )
    if not np.any(in_band) or not np.all(np.isfinite(powers)):
        raise ValueError("FDD produced no finite spectral result in the requested band")
    peaks, _ = find_peaks(powers, prominence=max(float(powers[in_band].max()) * 0.01, 1e-30))
    peaks = [int(i) for i in peaks if in_band[i]]
    peaks = sorted(peaks, key=lambda i: -powers[i])[: config["max_modes"]]
    peaks.sort(key=lambda i: float(frequencies[i]))
    resolution = fs / config["nperseg"]
    rotor = record["environment"].get("rotor_speed_rpm")
    if rotor is None:
        warnings.append("rotor_harmonics_unchecked")
    for index in peaks:
        f = float(frequencies[index])
        harmonics = (
            []
            if rotor is None or rotor == 0
            else [
                label
                for order, label in ((1, "1P"), (3, "3P"))
                if abs(f - float(rotor) / 60 * order) <= resolution
            ]
        )
        shape = shapes[0, :, index]
        pivot = shape[int(np.argmax(np.abs(shape)))]
        normalized = shape / pivot
        result["modes"].append(
            {
                "frequency_hz": f,
                "damping_ratio": None,
                "mode_shape": [{"real": float(x.real), "imag": float(x.imag)} for x in normalized],
                "quality": {
                    "status": "harmonic_overlap" if harmonics else "candidate",
                    "harmonics": harmonics,
                    "selection": "spectral_peak_screening",
                },
                "uncertainty": {
                    "status": "unquantified",
                    "frequency_bin_width_hz": resolution,
                    "reason": "bin_width_is_resolution_not_a_confidence_interval",
                },
            }
        )
    if not peaks:
        result["engineering_status"] = "insufficient_data"
        result["quality"]["usable"] = False
        result["quality"]["exclusions"].append("no_spectral_candidates")
    result["spectrum"] = {
        "frequency_hz": frequencies[in_band].tolist(),
        "leading_singular_value_power": powers[in_band].tolist(),
        "input_unit": "m/s2",
        "method": "pyOMA2 periodogram cross-spectral FDD",
    }
    return result
