from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from windops_backend.connectors import (
    BackendIngestClient,
    ConnectorConfig,
    EdgeObservation,
    TelemetrySpool,
    normalize_observation,
)


def _config(tmp_path, **updates) -> ConnectorConfig:
    values = {
        "source_id": "offshore-opcua-01",
        "transport": "http",
        "backend_base_url": "https://windops.example",
        "backend_api_key_env": "WINDOPS_EDGE_KEY",
        "upstream_url": "https://edge.example/measurements",
        "spool_path": str(tmp_path / "telemetry-spool.sqlite"),
        "mappings": [
            {
                "key": "WT-023.MainBearing.VibrationRms",
                "turbine_id": "WT-023",
                "variable": "main_bearing_vibration_rms",
                "unit": "mm/s",
            }
        ],
    }
    values.update(updates)
    return ConnectorConfig.model_validate(values)


def test_connector_config_and_normalization_are_governed(tmp_path) -> None:
    config = _config(tmp_path)
    mapping = config.mappings[0]
    observation = normalize_observation(
        mapping,
        {
            "value": 4.2,
            "observed_at": "2026-08-14T12:00:00+08:00",
            "sequence": 81,
            "source_event_id": "OPC-81",
            "quality": "suspect",
            "quality_code": "UncertainDataSubNormal",
            "engineering_mode": "normal",
        },
    )
    assert observation.observed_at == datetime(2026, 8, 14, 4, tzinfo=UTC)
    assert observation.quality == "uncertain"
    assert observation.attributes == {"engineering_mode": "normal"}

    with pytest.raises(ValidationError, match="must use HTTPS"):
        _config(tmp_path, backend_base_url="http://windops.example")
    with pytest.raises(ValidationError, match="mapping keys must be unique"):
        _config(tmp_path, mappings=[mapping.model_dump(), mapping.model_dump()])


def test_spool_sequences_deduplicates_and_retains_dead_letters(tmp_path) -> None:
    spool = TelemetrySpool(str(tmp_path / "spool.sqlite"), "source-1", max_attempts=1)
    first = EdgeObservation(
        source_event_id="EDGE-1",
        turbine_id="WT-023",
        observed_at=datetime.now(UTC),
        variable="active_power",
        value=4.2,
        unit="MW",
    )
    assert spool.enqueue(first) == ("EDGE-1", True)
    assert spool.enqueue(first) == ("EDGE-1", False)
    generated_id, inserted = spool.enqueue(first.model_copy(update={"source_event_id": None}))
    assert inserted is True
    pending = spool.pending(10)
    assert [row["source_sequence"] for row in pending] == [1, 2]
    assert generated_id.startswith("edge-")

    spool.fail(["EDGE-1"], "upstream unavailable")
    assert spool.counts() == {"pending": 1, "dead": 1}
    assert [row["source_event_id"] for row in spool.pending(10)] == [generated_id]


async def test_backend_delivery_acknowledges_complete_governed_batch(tmp_path) -> None:
    config = _config(tmp_path)
    spool = TelemetrySpool(config.spool_path, config.source_id)
    event_id, _ = spool.enqueue(
        EdgeObservation(
            source_event_id="OPC-81",
            source_sequence=81,
            turbine_id="WT-023",
            observed_at=datetime.now(UTC),
            variable="main_bearing_vibration_rms",
            value=4.2,
            unit="mm/s",
            quality="good",
        )
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://windops.example/api/v1/scada/ingest"
        assert request.headers["authorization"] == "Bearer source-secret"
        body = __import__("json").loads(request.content)
        assert body["source_id"] == config.source_id
        assert body["samples"][0]["source_sequence"] == 81
        return httpx.Response(
            200,
            json={
                "accepted": 1,
                "duplicates": 0,
                "quarantined": 0,
                "results": [
                    {
                        "source_event_id": event_id,
                        "disposition": "accepted",
                        "late": False,
                    }
                ],
            },
        )

    delivery = BackendIngestClient(
        config,
        spool,
        "source-secret",
        transport=httpx.MockTransport(handler),
    )
    assert await delivery.flush_once() == 1
    assert spool.counts() == {"pending": 0, "dead": 0}


async def test_backend_failure_moves_poison_batch_to_durable_dead_letter(tmp_path) -> None:
    config = _config(tmp_path, max_delivery_attempts=1)
    spool = TelemetrySpool(config.spool_path, config.source_id, max_attempts=1)
    spool.enqueue(
        EdgeObservation(
            source_event_id="POISON-1",
            source_sequence=1,
            turbine_id="WT-023",
            observed_at=datetime.now(UTC),
            variable="main_bearing_vibration_rms",
            value=4.2,
            unit="mm/s",
        )
    )
    delivery = BackendIngestClient(
        config,
        spool,
        "source-secret",
        transport=httpx.MockTransport(lambda _request: httpx.Response(503)),
    )
    with pytest.raises(httpx.HTTPStatusError):
        await delivery.flush_once()
    assert spool.counts() == {"pending": 0, "dead": 1}
