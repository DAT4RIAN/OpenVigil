"""Real Linux FDD with explicit synthetic signals; no field authority."""

import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import subprocess  # nosec B404
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from windops_backend.schema_structural import FDDConfiguration
from windops_backend.structural_analysis import analyze_waveform
from windops_backend.structural_contract import SCIENTIFIC_VERSIONS, algorithm_identity
from windops_backend.structural_dependencies import verify_installed_lock


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(f"structural runtime smoke failed: {code}")


def structural_runtime_smoke() -> dict[str, object]:
    _require(platform.system() == "Linux" and platform.machine() == "x86_64", "platform")
    # Linux APIs are absent from Windows stubs; resolve only after checking the platform.
    uid, gid = (int(getattr(os, name)()) for name in ("getuid", "getgid"))
    _require(uid == gid == 10001, "uid_gid")
    _require(importlib.util.find_spec("pytest") is None, "test_dependencies_absent")
    subprocess.run(["python", "-m", "pip", "check"], check=True, timeout=30)  # nosec B603, B607
    versions = {name: importlib.metadata.version(name) for name in SCIENTIFIC_VERSIONS}
    _require(versions == SCIENTIFIC_VERSIONS, "scientific_versions")
    closure = verify_installed_lock(Path("/app/requirements.structural.txt"))
    start = datetime.now(UTC) - timedelta(days=1)
    fs = 16.0
    n = 4096
    ids = ["SYNTHETIC-LINUX-A", "SYNTHETIC-LINUX-B"]
    meta = [
        {
            "id": value,
            "unit": "m/s2",
            "quantity": "acceleration",
            "range_min": -10,
            "range_max": 10,
            "calibration_at": (start - timedelta(days=1)).isoformat(),
            "calibration_valid_until": (start + timedelta(days=2)).isoformat(),
            "synchronization_source": "synthetic-clock",
        }
        for value in ids
    ]
    body: dict[str, Any] = {
        "schema_version": "openvigil.waveform.v1",
        "turbine_id": "WT-023",
        "started_at": start.isoformat(),
        "sample_rate_hz": fs,
        "channels": [
            {
                "channel_id": value,
                "unit": "m/s2",
                "offset_seconds": 0,
                "samples": [
                    math.sin(2 * math.pi * 0.5 * sample / fs) * (1 + channel / 2)
                    for sample in range(n)
                ],
            }
            for channel, value in enumerate(ids)
        ],
    }
    record = {
        "turbine_id": "WT-023",
        "started_at": start.isoformat(),
        "ended_at": (start + timedelta(seconds=n / fs)).isoformat(),
        "sample_rate_hz": fs,
        "sample_count": n,
        "channel_ids": ids,
        "channel_snapshot": meta,
        "source_kind": "synthetic_test",
        "environment": {"operating_state": "stopped", "rotor_speed_rpm": 0},
    }
    result = analyze_waveform(json.dumps(body).encode(), record, FDDConfiguration().model_dump())
    _require(result["quality"]["usable"] is True, "healthy_signal_quality")
    _require(len(result["modes"]) == 1, "mode_count")
    _require(abs(result["modes"][0]["frequency_hz"] - 0.5) <= fs / 1024, "mode_frequency")
    _require(result["modes"][0]["damping_ratio"] is None, "unqualified_damping")
    _require(result["modes"][0]["uncertainty"]["status"] == "unquantified", "uncertainty")
    _require(result["absolute_prestress"]["status"] == "unavailable", "prestress_qualification")
    for channel in body["channels"]:
        channel["samples"] = [0.0] * n
    rejected = analyze_waveform(json.dumps(body).encode(), record, FDDConfiguration().model_dump())
    _require(
        rejected["quality"]["usable"] is False and rejected["modes"] == [], "flatline_rejected"
    )
    return {
        "platform": "linux/amd64",
        "uid": uid,
        "gid": gid,
        "versions": versions,
        "adapter_sha256": algorithm_identity()["adapter_sha256"],
        "frequency_hz": result["modes"][0]["frequency_hz"],
        "flatline_rejected": True,
        "field_qualification": "unverified",
        "pip_check": "passed",
        "dependency_closure": closure,
    }


if __name__ == "__main__":
    print(json.dumps(structural_runtime_smoke()))
