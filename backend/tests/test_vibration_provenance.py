from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from windops_backend.agents.tools import SQLToolAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [3.0, 4.5, 4.81])
async def test_rms_amplitude_does_not_establish_a_spectral_marker(
    app: FastAPI, client: httpx.AsyncClient, value: float
) -> None:
    event_id = f"RMS-ONLY-{value}"
    response = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": event_id,
                    "turbine_id": "WT-023",
                    "observed_at": "2026-09-27T00:00:00Z",
                    "variable": "main_bearing_vibration_rms",
                    "value": value,
                    "unit": "mm/s",
                    "quality": "good",
                    "attributes": {"baseline": 3.0, "anomaly_score": 0.86},
                }
            ]
        },
    )
    assert response.status_code == 202
    async with app.state.session_factory() as session:
        analysis = await SQLToolAdapter(session).query_vibration("WT-023")
    assert analysis["rms_mm_s"] == value
    assert analysis["trend_pct"] == round((value - 3.0) / 3.0 * 100, 1)
    assert analysis["samples"][0]["source_event_id"] == event_id
    assert analysis["spectrum_marker"] == "unavailable"

    mission_id = response.json()["results"][0]["mission_id"]
    if mission_id is not None:
        detail = await client.get(f"/api/v1/missions/{mission_id}")
        assert detail.status_code == 200
        state: dict[str, Any] = detail.json()["public_state"]
        evidence = next(item for item in state["evidence"] if "rms_mm_s" in item["metrics"])
        assert evidence["evidence_type"] == "vibration_rms"
        assert evidence["metrics"]["spectrum_marker"] == "unavailable"
        assert evidence["metrics"]["rms_mm_s"] == value
        assert event_id in evidence["source_refs"]
        assert "no frequency-domain spectrum" in evidence["summary"]
        persisted = next(
            item
            for item in detail.json()["evidence"]
            if item["evidence_id"] == evidence["evidence_id"]
        )
        assert persisted["evidence_type"] == "vibration_rms"
        assert persisted["metrics"]["spectrum_marker"] == "unavailable"


@pytest.mark.asyncio
async def test_no_vibration_samples_do_not_claim_normal_spectrum(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        analysis = await SQLToolAdapter(session).query_vibration("WT-023")
    assert analysis["samples"] == []
    assert "rms_mm_s" not in analysis
    assert analysis["spectrum_marker"] == "unavailable"
