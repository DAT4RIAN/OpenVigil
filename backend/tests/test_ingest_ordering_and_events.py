import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from windops_backend.config import TelemetrySourcePolicy, TelemetryVariablePolicy
from windops_backend.models import Base, IngestSource, IngestStreamState
from windops_backend.schemas import ScadaSampleIn
from windops_backend.services.ingest import _is_main_bearing_anomaly, _stream_state


def _sample(
    event_id: str,
    sequence: int,
    observed_at: datetime,
    *,
    value: float = 2.1,
) -> dict[str, object]:
    return {
        "source_event_id": event_id,
        "source_sequence": sequence,
        "turbine_id": "WT-023",
        "observed_at": observed_at.isoformat(),
        "variable": "main_bearing_vibration_rms",
        "value": value,
        "unit": "mm/s",
        "quality": "good",
        "quality_code": "OPC_GOOD",
        "attributes": {"gateway": "edge-01"},
    }


def test_malformed_anomaly_score_does_not_turn_ingest_into_a_server_error() -> None:
    sample = ScadaSampleIn(
        source_event_id="MALFORMED-SCORE-001",
        turbine_id="WT-023",
        observed_at=datetime.now(UTC),
        variable="main_bearing_vibration_rms",
        value=2.1,
        unit="mm/s",
        attributes={"anomaly_score": "not-a-number"},
    )
    assert _is_main_bearing_anomaly(sample) is False


async def test_ingest_applies_source_policy_watermarks_quarantine_and_replay(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    source_id = "offshore-opcua-01"
    app.state.settings.telemetry_source_policies[source_id] = TelemetrySourcePolicy(
        display_name="Offshore OPC UA gateway 01",
        source_kind="opcua",
        sequence_required=True,
        max_lateness_seconds=60,
        allowed_turbines=["WT-023"],
        allowed_variables=["main_bearing_vibration_rms"],
        variable_contracts={
            "main_bearing_vibration_rms": TelemetryVariablePolicy(
                label="Main bearing vibration RMS",
                unit="mm/s",
                precision=2,
                normal_min=0,
                normal_max=4.5,
                warning_threshold=4.5,
                critical_threshold=7.1,
            )
        },
    )
    now = datetime.now(UTC)

    first_sample = _sample("ORDERED-001", 10, now - timedelta(seconds=30))
    first = await client.post(
        "/api/v1/scada/ingest",
        json={"source_id": source_id, "samples": [first_sample]},
    )
    assert first.status_code == 202
    assert first.json()["accepted"] == 1
    assert first.json()["quarantined"] == 0
    assert first.json()["results"][0]["late"] is False

    late = await client.post(
        "/api/v1/scada/ingest",
        json={
            "source_id": source_id,
            "samples": [_sample("ORDERED-002", 9, now - timedelta(seconds=40))],
        },
    )
    assert late.status_code == 202
    assert late.json()["results"][0]["late"] is True

    too_late = await client.post(
        "/api/v1/scada/ingest",
        json={
            "source_id": source_id,
            "samples": [_sample("ORDERED-003", 8, now - timedelta(seconds=400))],
        },
    )
    assert too_late.status_code == 202
    assert too_late.json()["quarantined"] == 1
    assert too_late.json()["results"][0]["reason_code"] == "beyond_lateness_window"

    wrong_unit_sample = _sample("ORDERED-004", 11, now)
    wrong_unit_sample["unit"] = "g"
    wrong_unit = await client.post(
        "/api/v1/scada/ingest",
        json={"source_id": source_id, "samples": [wrong_unit_sample]},
    )
    assert wrong_unit.status_code == 202
    assert wrong_unit.json()["results"][0]["reason_code"] == "unit_mismatch"

    duplicate = await client.post(
        "/api/v1/scada/ingest",
        json={"source_id": source_id, "samples": [first_sample]},
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["duplicates"] == 1

    conflict = await client.post(
        "/api/v1/scada/ingest",
        json={
            "source_id": source_id,
            "samples": [{**first_sample, "value": 3.2}],
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    sources = await client.get("/api/v1/ingest/sources")
    assert sources.status_code == 200
    source = next(item for item in sources.json()["sources"] if item["source_id"] == source_id)
    stream = source["streams"][0]
    assert stream["highest_sequence"] == 10
    assert stream["accepted_count"] == 2
    assert stream["late_count"] == 1
    assert stream["quarantined_count"] == 2
    assert stream["duplicate_count"] == 1

    history = await client.get(
        "/api/v1/scada/history",
        params={
            "turbine_id": "WT-023",
            "from": (now - timedelta(seconds=500)).isoformat(),
            "to": (now + timedelta(seconds=1)).isoformat(),
            "points_per_series": 2000,
        },
    )
    assert history.status_code == 200
    history_body = history.json()
    assert history_body["meta"]["deterministic"] is False
    assert history_body["meta"]["range"] == "CUSTOM"
    assert history_body["data"][0]["source_id"] == source_id
    assert history_body["data"][0]["normal_range"] == [0.0, 4.5]
    assert len(history_body["data"][0]["points"]) == 2

    archive = await client.get(
        "/api/v1/scada/measurements",
        params={
            "turbine_id": "WT-023",
            "variable": "main_bearing_vibration_rms",
            "offset": 0,
            "limit": 1,
        },
    )
    assert archive.status_code == 200
    assert archive.json()["meta"]["total"] == 2
    assert archive.json()["measurements"][0]["source_id"] == source_id
    assert archive.json()["measurements"][0]["quality_code"] == "OPC_GOOD"

    health = await client.get("/api/v1/health/assessments", params={"turbine_id": "WT-023"})
    assert health.status_code == 200
    assessment = health.json()["assessments"][0]
    assert assessment["turbine_model"] == "Goldwind GW165-6.0MW"
    assert assessment["prediction_available"] is False
    assert assessment["failure_probability_30d"] is None

    first_page = await client.get("/api/v1/events", params={"after": 0, "limit": 2})
    assert first_page.status_code == 200
    assert first_page.json()["count"] == 2
    cursor = first_page.json()["next_cursor"]
    resumed = await client.get("/api/v1/events", params={"after": cursor, "limit": 100})
    assert resumed.status_code == 200
    assert all(item["sequence"] > cursor for item in resumed.json()["events"])

    all_events = await client.get("/api/v1/events", params={"after": 0, "limit": 100})
    event_types = {item["event_type"] for item in all_events.json()["events"]}
    assert {"scada.sample.accepted", "scada.sample.quarantined"} <= event_types

    app.state.settings.event_stream_connection_seconds = 1
    stream_response = await client.get(
        "/api/v1/events/stream",
        params={"after": 0, "event_type": "scada.sample.accepted"},
    )
    assert stream_response.status_code == 200
    assert stream_response.headers["content-type"].startswith("text/event-stream")
    assert "event: stream.ready" in stream_response.text
    assert "event: scada.sample.accepted" in stream_response.text
    assert "event: reconnect" in stream_response.text

    latest_stream = await client.get(
        "/api/v1/events/stream",
        params={"start": "latest", "event_type": "scada.sample.accepted"},
    )
    assert latest_stream.status_code == 200
    assert "event: stream.ready" in latest_stream.text
    assert "event: scada.sample.accepted" not in latest_stream.text
    assert '"start":"latest"' in latest_stream.text

    ahead_stream = await client.get(
        "/api/v1/events/stream",
        params={"after": 999_999, "event_type": "scada.sample.accepted"},
    )
    assert ahead_stream.status_code == 200
    assert f"id: {all_events.json()['next_cursor']}\nevent: stream.ready" in ahead_stream.text
    assert "event: scada.sample.accepted" not in ahead_stream.text


async def test_concurrent_first_stream_packets_initialize_one_idempotent_state(
    app: FastAPI,
) -> None:
    source_id = "concurrent-stream-source"
    stream_key = "WT-023:main_bearing_vibration_rms"
    async with app.state.session_factory() as session, session.begin():
        session.add(
            IngestSource(
                id=source_id,
                display_name="Concurrent stream test source",
                source_kind="rest",
                policy={},
            )
        )

    async def initialize_state() -> tuple[str, str]:
        async with app.state.session_factory() as session, session.begin():
            state = await _stream_state(session, source_id, stream_key)
            return state.source_id, state.stream_key

    results = await asyncio.gather(initialize_state(), initialize_state())
    assert results == [(source_id, stream_key), (source_id, stream_key)]

    async with app.state.session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(IngestStreamState)
            .where(
                IngestStreamState.source_id == source_id,
                IngestStreamState.stream_key == stream_key,
            )
        )
    assert count == 1


async def test_ingest_credential_cannot_write_another_source(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    source_id = "cms-gateway-01"
    app.state.settings.telemetry_source_policies[source_id] = TelemetrySourcePolicy(
        display_name="CMS gateway 01",
        source_kind="cms",
        sequence_required=True,
    )
    response = await client.post(
        "/api/v1/scada/ingest",
        json={
            "source_id": source_id,
            "samples": [_sample("CMS-MISMATCH-001", 1, datetime.now(UTC))],
        },
        headers={
            "X-WindOps-Test-Principal": "ingest-source:another-source",
            "X-WindOps-Test-Role": "scada_ingestor",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INGEST_SOURCE_MISMATCH"


def test_ordered_ingest_and_event_log_are_covered_by_metadata_and_migration() -> None:
    assert {
        "ingest_sources",
        "ingest_stream_states",
        "quarantined_scada_samples",
        "domain_events",
    } <= set(Base.metadata.tables)
    root = Path(__file__).parents[1]
    migration = (
        root / "alembic" / "versions" / "0007_ordered_ingest_and_replayable_events.py"
    ).read_text(encoding="utf-8")
    for value in (
        '"ingest_sources"',
        '"ingest_stream_states"',
        '"quarantined_scada_samples"',
        '"domain_events"',
        "sa.Identity()",
    ):
        assert value in migration
