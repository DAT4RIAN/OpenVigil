"""Synthetic engineering challenges; these are never field acceptance evidence."""

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import httpx
import numpy as np
import pytest
from sqlalchemy import func, select

from windops_backend.model_structural import (
    ModalObservation,
    StructuralAnalysisRun,
    WaveformRecord,
)
from windops_backend.models import Turbine
from windops_backend.services.structural import STRUCTURAL_ANALYSIS_REQUESTED
from windops_backend.storage import OutboxEvent
from windops_backend.structural_worker import expired_structural_events, process_structural_event

START = datetime(2026, 10, 1, tzinfo=UTC)
FS = 16.0
N = 4096


async def post(client, path, payload, key=None, **kwargs):
    return await client.post(
        f"/api/v1/{path}",
        json=payload,
        headers={"Idempotency-Key": key or str(uuid4()), **kwargs.pop("headers", {})},
        **kwargs,
    )


async def identities(client, count=2, **overrides):
    component = await post(
        client,
        "tower-components",
        {
            "turbine_id": "WT-023",
            "code": "C01",
            "name": "混凝土测试段",
            "component_type": "concrete_segment",
            "revision": "test-r1",
            "design_reference": "synthetic engineering fixture, not an OEM drawing",
        },
    )
    assert component.status_code == 201, component.text
    component_id = component.json()["id"]
    sensors = []
    for i in range(count):
        payload = {
            "turbine_id": "WT-023",
            "component_id": component_id,
            "code": f"A{i}",
            "revision": "r1",
            "quantity": "acceleration",
            "unit": "m/s2",
            "direction": "X",
            "range_min": -10,
            "range_max": 10,
            "calibration_version": "synthetic-calibration-v1",
            "calibration_at": "2026-01-01T00:00:00Z",
            "calibration_valid_until": "2027-01-01T00:00:00Z",
            "calibration_reference": "test calibration only",
            "synchronization_source": "synthetic-clock",
            **overrides,
        }
        sensor = await post(client, "sensor-channels", payload)
        assert sensor.status_code == 201, sensor.text
        sensors.append(sensor.json())
    return component.json(), sensors


async def acquisition(
    app,
    client,
    sensors,
    transform=None,
    source_kind="synthetic_test",
    *,
    started_at=START,
    environment=None,
):
    time = np.arange(N) / FS
    signal = np.sin(2 * np.pi * 0.5 * time)
    channels = [
        {
            "channel_id": s["id"],
            "unit": s["unit"],
            "offset_seconds": 0.0,
            "samples": (signal * (1.0 + i / 2)).tolist(),
        }
        for i, s in enumerate(sensors)
    ]
    body = {
        "schema_version": "openvigil.waveform.v1",
        "turbine_id": "WT-023",
        "started_at": started_at.isoformat(),
        "sample_rate_hz": FS,
        "channels": channels,
    }
    if transform:
        transform(body)
    content = json.dumps(body).encode()
    uri = f"minio://windops-field-evidence/structural/turbines/WT-023/{uuid4()}.json"
    sha = app.state.artifact_verifier.register_object(uri, content, "application/json")
    payload = {
        "turbine_id": "WT-023",
        "channel_ids": [s["id"] for s in sensors],
        "started_at": started_at.isoformat(),
        "ended_at": (started_at + timedelta(seconds=N / FS)).isoformat(),
        "sample_rate_hz": FS,
        "sample_count": N,
        "artifact_uri": uri,
        "artifact_sha256": sha,
        "source_kind": source_kind,
        "source_reference": "synthetic sinusoid test",
        "environment": environment or {"operating_state": "stopped", "rotor_speed_rpm": 0},
    }
    response = await post(client, "structural-records", payload)
    assert response.status_code == 201, response.text
    return response.json(), payload, body


async def run_analysis(app, client, record, config=None):
    response = await post(
        client, "structural-analyses", {"record_id": record["id"], "config": config or {}}
    )
    assert response.status_code == 202, response.text
    async with app.state.session_factory() as session:
        event = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == response.json()["id"],
                OutboxEvent.event_type == STRUCTURAL_ANALYSIS_REQUESTED,
            )
        )
        assert event is not None
        event_id = event.id
    # The HTTP response only queued a run; this executes the real worker boundary.
    assert response.json()["status"] == "pending"
    assert await process_structural_event(
        app.state.session_factory, app.state.artifact_verifier, "windops-field-evidence", event_id
    )
    detail = await client.get(f"/api/v1/structural-analyses/{response.json()['id']}")
    assert detail.status_code == 200
    return detail.json(), event_id


async def test_asset_topology_and_idempotent_immutable_revisions(client):
    payload = {
        "turbine_id": "WT-023",
        "code": "C01",
        "name": "混凝土段",
        "component_type": "concrete_segment",
        "revision": "r1",
        "design_reference": "drawing-r1",
    }
    first = await post(client, "tower-components", payload, "component-key-0001")
    second = await post(client, "tower-components", payload, "component-key-0001")
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert second.headers["Idempotency-Replayed"] == "true"
    changed = await post(
        client, "tower-components", {**payload, "name": "changed"}, "component-key-0001"
    )
    assert changed.status_code == 409
    duplicate = await post(client, "tower-components", payload)
    assert duplicate.status_code == 409
    revision = await post(client, "tower-components", {**payload, "revision": "r2"})
    assert revision.status_code == 201
    topology = (await client.get("/api/v1/turbines/WT-023/tower-components?limit=1")).json()
    assert len(topology["components"]["items"]) == 1
    assert topology["components"]["next_cursor"]
    assert topology["tendons"]["items"] == []


async def test_real_fdd_replay_retains_input_spectrum_and_uncertainty(app, client):
    _, sensors = await identities(client)
    record, payload, _ = await acquisition(app, client, sensors)
    replay = await post(client, "structural-records", payload)
    assert replay.json()["id"] == record["id"]
    result, event_id = await run_analysis(app, client, record)
    assert result["status"] == "succeeded"
    analysis = result["result"]
    assert analysis["source_kind"] == "synthetic_test"
    assert analysis["quality"]["usable"]
    assert analysis["modes"][0]["frequency_hz"] == pytest.approx(0.5, abs=FS / 1024)
    assert analysis["modes"][0]["damping_ratio"] is None
    assert analysis["modes"][0]["uncertainty"]["status"] == "unquantified"
    assert analysis["engineering_status"] == "requires_engineering_review"
    assert analysis["input"]["artifact_sha256"] == payload["artifact_sha256"]
    assert len(analysis["spectrum"]["frequency_hz"]) > 100
    assert len(analysis["result_sha256"]) == 64
    assert analysis["algorithm"]["versions"]["pyOMA_2"] == "1.4.3"
    assert analysis["absolute_prestress"]["status"] == "unavailable"
    # A duplicate queue delivery cannot create a second observation.
    assert not await process_structural_event(
        app.state.session_factory, app.state.artifact_verifier, "windops-field-evidence", event_id
    )
    again = await post(client, "structural-analyses", {"record_id": record["id"]})
    assert again.json()["id"] == result["id"]
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(StructuralAnalysisRun)) == 1
        assert await session.scalar(select(func.count()).select_from(WaveformRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(ModalObservation)) == 1


@pytest.mark.parametrize(
    "challenge,reason",
    [
        ("missing", "missing_or_nonfinite_samples"),
        ("flat", "flat_channel"),
        ("clipped", "saturated_or_out_of_range"),
        ("offset", "synchronization_offset_exceeded"),
        ("unit", "quantity_or_unit_mismatch"),
        ("asset", "artifact_asset_mismatch"),
        ("count", "sample_count_mismatch"),
        ("channel", "artifact_channel_mismatch"),
        ("rate", "artifact_sample_rate_mismatch"),
        ("time", "artifact_time_mismatch"),
    ],
)
async def test_signal_quality_fail_closed_without_modal_results(app, client, challenge, reason):
    _, sensors = await identities(client)

    def transform(body):
        c = body["channels"][0]
        if challenge == "missing":
            c["samples"][0] = None
        if challenge == "flat":
            c["samples"] = [0.0] * N
        if challenge == "clipped":
            c["samples"][0] = 10.0
        if challenge == "offset":
            c["offset_seconds"] = 0.1
        if challenge == "unit":
            c["unit"] = "g"
        if challenge == "asset":
            body["turbine_id"] = "WT-999"
        if challenge == "count":
            c["samples"].pop()
        if challenge == "channel":
            body["channels"].reverse()
        if challenge == "rate":
            body["sample_rate_hz"] = 32.0
        if challenge == "time":
            body["started_at"] = "2026-09-30T00:00:00Z"

    record, _, _ = await acquisition(app, client, sensors, transform)
    result, _ = await run_analysis(app, client, record)
    assert result["status"] == "insufficient_data"
    assert any(reason in r for r in result["result"]["quality"]["exclusions"])
    assert result["result"]["modes"] == []


async def test_expired_calibration_is_not_usable(app, client):
    _, sensors = await identities(client, calibration_valid_until="2026-09-01T00:00:00Z")
    record, _, _ = await acquisition(app, client, sensors)
    result, _ = await run_analysis(app, client, record)
    assert result["status"] == "insufficient_data"
    assert "calibration_does_not_cover_window" in str(result["result"]["quality"])


@pytest.mark.parametrize(
    "config,reason",
    [
        ({"max_frequency_hz": 9}, "frequency_band_exceeds_nyquist"),
        ({"nperseg": 8192}, "insufficient_spectral_segments"),
        ({"min_frequency_hz": 0.001}, "window_has_fewer_than_three_low_band_cycles"),
    ],
)
async def test_analysis_window_and_band_applicability(app, client, config, reason):
    _, sensors = await identities(client)
    record, _, _ = await acquisition(app, client, sensors)
    result, _ = await run_analysis(app, client, record, config)
    assert result["status"] == "insufficient_data"
    assert reason in result["result"]["quality"]["exclusions"]


async def test_artifact_hash_and_prefix_are_checked_before_registration(app, client):
    _, sensors = await identities(client)
    _, payload, _ = await acquisition(app, client, sensors)
    bad_hash = await post(client, "structural-records", {**payload, "artifact_sha256": "0" * 64})
    assert bad_hash.status_code == 422
    wrong_scope = await post(
        client,
        "structural-records",
        {
            **payload,
            "artifact_uri": "minio://windops-field-evidence/structural/turbines/WT-999/data.json",
        },
    )
    # Transport URI is omitted from fingerprint, but the supplied location must
    # still be scoped, even when the content identity already exists.
    assert wrong_scope.status_code == 422


async def test_invalid_artifact_fails_durably_without_fake_results(app, client):
    _, sensors = await identities(client)
    record, _, _ = await acquisition(
        app, client, sensors, lambda b: b.update(schema_version="unknown")
    )
    result, event_id = await run_analysis(app, client, record)
    assert result["status"] == "failed"
    assert result["error_code"] == "ValidationError"
    assert result["result"] is None
    async with app.state.session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
        assert event.status == "failed"
        assert event.last_error
        assert await session.scalar(select(func.count()).select_from(ModalObservation)) == 0


async def test_no_data_is_not_health(client):
    response = await client.get("/api/v1/turbines/WT-023/structural-health")
    assert response.status_code == 200
    assert response.json()["assessment_status"] == "no_data"
    assert response.json()["damage_probability"] is None
    assert response.json()["field_qualification"] == "unverified"


async def test_cross_asset_references_and_data_scope_are_denied(app, client):
    component, sensors = await identities(client)
    record, _, _ = await acquisition(app, client, sensors)
    run = await post(client, "structural-analyses", {"record_id": record["id"]})
    async with app.state.session_factory() as session, session.begin():
        original = await session.get(Turbine, "WT-023")
        session.add(Turbine(id="WT-999", wind_farm_id=original.wind_farm_id, model=original.model))
    invalid_parent = await post(
        client,
        "tower-components",
        {
            "turbine_id": "WT-999",
            "code": "C9",
            "name": "wrong parent",
            "component_type": "joint",
            "revision": "r1",
            "design_reference": "test",
            "parent_id": component["id"],
        },
    )
    assert invalid_parent.status_code == 404
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-WindOps-Test-Principal": "limited-engineer",
            "X-WindOps-Test-Role": "maintenance_reviewer",
            "X-WindOps-Test-Turbine-Ids": "WT-999",
            "X-WindOps-Test-Data-Scopes": "structural",
        },
    ) as limited:
        denied = await limited.get(f"/api/v1/structural-analyses/{run.json()['id']}")
        assert denied.status_code == 404
        denied_submit = await post(limited, "structural-analyses", {"record_id": record["id"]})
        assert denied_submit.status_code == 404
        topology = await limited.get("/api/v1/turbines/WT-023/tower-components")
        assert topology.status_code == 404
        own = await limited.get("/api/v1/turbines/WT-999/tower-components")
        assert own.status_code == 200
        assert own.json()["sensors"]["items"] == []
    denied_domain = await client.get(
        "/api/v1/turbines/WT-023/structural-health",
        headers={
            "X-WindOps-Test-Principal": "domain-limited-manager",
            "X-WindOps-Test-Role": "operations_manager",
            "X-WindOps-Test-Turbine-Ids": "WT-023",
            "X-WindOps-Test-Data-Scopes": "asset",
        },
    )
    assert denied_domain.status_code == 403
    assert denied_domain.json()["error"]["code"] == "DATA_SCOPE_FORBIDDEN"


async def test_direct_force_uses_raw_instrument_value_and_unit_conversion(app, client):
    component, _ = await identities(client)
    tendon = await post(
        client,
        "tendon-assemblies",
        {
            "turbine_id": "WT-023",
            "component_id": component["id"],
            "code": "T01",
            "revision": "r1",
            "boundary": {"anchor": "synthetic anchor"},
        },
    )
    assert tendon.status_code == 201
    sensor = await post(
        client,
        "sensor-channels",
        {
            "turbine_id": "WT-023",
            "component_id": component["id"],
            "tendon_id": tendon.json()["id"],
            "code": "F01",
            "revision": "r1",
            "quantity": "force",
            "unit": "N",
            "direction": "axial",
            "range_min": 0,
            "range_max": 500000,
            "calibration_version": "test-cal1",
            "calibration_at": "2026-01-01T00:00:00Z",
            "calibration_valid_until": "2027-01-01T00:00:00Z",
            "calibration_reference": "test instrument",
            "synchronization_source": "test-clock",
        },
    )
    assert sensor.status_code == 201
    raw = {
        "schema_version": "openvigil.direct-force.v1",
        "tendon_id": tendon.json()["id"],
        "sensor_id": sensor.json()["id"],
        "observed_at": START.isoformat(),
        "value": 123000,
        "unit": "N",
        "calibration_version": "test-cal1",
    }
    uri = "minio://windops-field-evidence/structural/turbines/WT-023/force.json"
    sha = app.state.artifact_verifier.register_object(
        uri, json.dumps(raw).encode(), "application/json"
    )
    payload = {
        "turbine_id": "WT-023",
        "tendon_id": tendon.json()["id"],
        "sensor_id": sensor.json()["id"],
        "artifact_uri": uri,
        "artifact_sha256": sha,
        "source_kind": "synthetic_test",
    }
    response = await post(client, "prestress-observations", payload)
    assert response.status_code == 201, response.text
    assert response.json()["value_kn"] == 123
    assert response.json()["uncertainty"]["status"] == "unquantified"
    health = (await client.get("/api/v1/turbines/WT-023/structural-health")).json()
    assert health["prestress_trends"][0]["points"][0]["value_kn"] == 123
    assert health["prestress_trends"][0]["loss_percentage"] is None
    again = await post(client, "prestress-observations", payload)
    assert again.json()["id"] == response.json()["id"]
    raw["calibration_version"] = "wrong-calibration"
    payload["artifact_sha256"] = app.state.artifact_verifier.register_object(
        uri, json.dumps(raw).encode(), "application/json"
    )
    rejected = await post(client, "prestress-observations", payload)
    assert rejected.status_code == 422


@pytest.mark.parametrize(
    "mutation",
    [
        {"range_min": 20},
        {"unit": "kN"},
        {"calibration_valid_until": "2025-01-01T00:00:00Z"},
        {"calibration_at": "2026-01-01T00:00:00"},
        {"quantity": "force", "unit": "kN"},
    ],
)
async def test_sensor_schema_rejects_invalid_units_ranges_and_calibration(client, mutation):
    component, _ = await identities(client)
    payload = {
        "turbine_id": "WT-023",
        "component_id": component["id"],
        "code": "bad",
        "revision": "r1",
        "quantity": "acceleration",
        "unit": "m/s2",
        "direction": "X",
        "range_min": -10,
        "range_max": 10,
        "calibration_version": "c1",
        "calibration_at": "2026-01-01T00:00:00Z",
        "calibration_valid_until": "2027-01-01T00:00:00Z",
        "calibration_reference": "test",
        "synchronization_source": "clock",
        **mutation,
    }
    response = await post(client, "sensor-channels", payload)
    assert response.status_code == 422


async def queued_run(app, client):
    _, sensors = await identities(client)
    record, _, _ = await acquisition(app, client, sensors)
    run = (await post(client, "structural-analyses", {"record_id": record["id"]})).json()
    async with app.state.session_factory() as session:
        event = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == run["id"])
        )
        return run["id"], event.id


async def test_worker_restart_recovers_expired_processing_claim(app, client):
    run_id, event_id = await queued_run(app, client)
    async with app.state.session_factory() as session, session.begin():
        event = await session.get(OutboxEvent, event_id)
        event.status = "processing"
        event.claim_token = "lost-worker"
        event.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        event.attempts = 1
        run = await session.get(StructuralAnalysisRun, run_id)
        run.status = "running"
    expired = await expired_structural_events(app.state.session_factory)
    assert (event_id, STRUCTURAL_ANALYSIS_REQUESTED) in expired
    assert await process_structural_event(
        app.state.session_factory, app.state.artifact_verifier, "windops-field-evidence", event_id
    )
    result = (await client.get(f"/api/v1/structural-analyses/{run_id}")).json()
    assert result["status"] == "succeeded"
    assert result["attempts"] == 2
    assert await expired_structural_events(app.state.session_factory) == []


async def test_stale_worker_is_fenced_before_observation_commit(app, client, monkeypatch):
    run_id, event_id = await queued_run(app, client)
    from windops_backend import structural_worker

    original_compute = structural_worker.compute_waveform

    async def fence_after_computation(*args):
        result = await original_compute(*args)
        async with app.state.session_factory() as session, session.begin():
            event = await session.get(OutboxEvent, event_id)
            event.claim_token = "replacement-worker"
        return result

    with monkeypatch.context() as patch:
        patch.setattr(structural_worker, "compute_waveform", fence_after_computation)
        assert not await process_structural_event(
            app.state.session_factory,
            app.state.artifact_verifier,
            "windops-field-evidence",
            event_id,
        )
    async with app.state.session_factory() as session, session.begin():
        run = await session.get(StructuralAnalysisRun, run_id)
        assert run.result is None
        assert await session.scalar(select(func.count()).select_from(ModalObservation)) == 0
        event = await session.get(OutboxEvent, event_id)
        assert event.claim_token == "replacement-worker"
        event.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await process_structural_event(
        app.state.session_factory, app.state.artifact_verifier, "windops-field-evidence", event_id
    )
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ModalObservation)) == 1


async def test_repeated_worker_crashes_are_bounded(app, client):
    run_id, event_id = await queued_run(app, client)
    async with app.state.session_factory() as session, session.begin():
        event = await session.get(OutboxEvent, event_id)
        event.status = "processing"
        event.claim_token = "crashed-third-worker"
        event.attempts = 3
        event.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await process_structural_event(
        app.state.session_factory, app.state.artifact_verifier, "windops-field-evidence", event_id
    )
    result = (await client.get(f"/api/v1/structural-analyses/{run_id}")).json()
    assert result["status"] == "failed"
    assert result["error_code"] == "StructuralAttemptsExhausted"
    assert result["result"] is None


async def test_baseline_publication_uses_real_computations_and_preserves_immutable_review(
    app, client
):
    component, sensors = await identities(client)
    modal_ids = []
    for index in range(30):
        record, _, _ = await acquisition(
            app,
            client,
            sensors,
            started_at=START + timedelta(hours=index),
            environment={
                "operating_state": "stopped",
                "rotor_speed_rpm": 0,
                "temperature_c": index % 10,
            },
        )
        result, _ = await run_analysis(app, client, record)
        assert result["status"] == "succeeded"
        modal_ids.append(result["modal_observations"][0]["id"])
    payload = {
        "turbine_id": "WT-023",
        "component_id": component["id"],
        "code": "healthy-stopped",
        "revision": "synthetic-r1",
        "confirmation_reference": "synthetic challenge, never field healthy confirmation",
        "reference_modal_id": modal_ids[0],
        "training_modal_ids": modal_ids,
        "features": ["temperature_c"],
        "valid_until": "2027-01-01T00:00:00Z",
    }
    published = await post(client, "health-baselines", payload, "healthy-baseline-command-1")
    assert published.status_code == 201, published.text
    baseline = published.json()
    assert baseline["source_kind"] == "synthetic_test"
    assert baseline["model"]["validation"]["validation_count"] == 6
    assert baseline["created_by"] == "integration-test-system"
    replayed = await post(client, "health-baselines", payload, "healthy-baseline-command-1")
    assert replayed.json() == baseline
    assert replayed.headers["Idempotency-Replayed"] == "true"
    duplicate = await post(client, "health-baselines", payload)
    assert duplicate.status_code == 409
    health = (
        await client.get(
            "/api/v1/turbines/WT-023/structural-health", params={"baseline_id": baseline["id"]}
        )
    ).json()
    assert health["baseline_status"] == "available_for_screening"
    assert health["comparisons"]
    assert all(c["status"] == "within_screening_range" for c in health["comparisons"])
    assert health["field_qualification"] == "unverified"
    rejected = await post(
        client,
        "health-baselines",
        {**payload, "revision": "bad-r2", "training_modal_ids": [modal_ids[0]] * 30},
    )
    assert rejected.status_code == 422
    other_asset = await post(client, "health-baselines", {**payload, "turbine_id": "WT-024"})
    assert other_asset.status_code == 404
    detail = await client.get(f"/api/v1/health-baselines/{baseline['id']}")
    assert detail.json() == baseline
    outside = await post(
        client,
        "health-baselines",
        {**payload, "revision": "expired", "valid_until": "2026-01-01T00:00:00Z"},
    )
    assert outside.status_code == 422


async def test_local_timezone_and_rotor_harmonics_retain_truthful_classification(app, client):
    _, sensors = await identities(client, calibration_at="2026-01-01T08:00:00+08:00")
    assert sensors[0]["calibration_at"].startswith("2026-01-01T00:00:00")
    record, _, _ = await acquisition(
        app,
        client,
        sensors,
        started_at=START.astimezone(timezone(timedelta(hours=8))),
        environment={"operating_state": "running", "rotor_speed_rpm": 10},
    )
    assert record["started_at"].startswith("2026-10-01T00:00:00")
    result, _ = await run_analysis(app, client, record)
    assert result["status"] == "succeeded"
    mode = result["result"]["modes"][0]
    assert mode["quality"]["status"] == "harmonic_overlap"
    assert mode["quality"]["harmonics"] == ["3P"]
    assert result["result"]["absolute_prestress"]["status"] == "unavailable"


async def test_structure_events_do_not_leak_through_asset_data_grants(app, client):
    await identities(client)
    headers = {
        "X-WindOps-Test-Principal": "scoped-manager",
        "X-WindOps-Test-Role": "operations_manager",
        "X-WindOps-Test-Turbine-Ids": "WT-023",
    }
    asset = await client.get(
        "/api/v1/events",
        params={"event_type": "structural.identity.created"},
        headers={**headers, "X-WindOps-Test-Data-Scopes": "asset"},
    )
    assert asset.status_code == 200
    assert asset.json()["events"] == []
    structure = await client.get(
        "/api/v1/events",
        params={"event_type": "structural.identity.created"},
        headers={**headers, "X-WindOps-Test-Data-Scopes": "structural"},
    )
    assert structure.status_code == 200
    assert len(structure.json()["events"]) == 3


async def test_queued_algorithm_identity_separates_replay_and_rejects_changed_worker(
    app, client, monkeypatch
):
    from windops_backend.services import structural

    _, sensors = await identities(client)
    record, _, _ = await acquisition(app, client, sensors)
    first, _ = await run_analysis(app, client, record)
    original = structural.algorithm_identity()
    with monkeypatch.context() as patch:
        patch.setattr(
            structural, "algorithm_identity", lambda: {**original, "adapter_sha256": "0" * 64}
        )
        queued = await post(client, "structural-analyses", {"record_id": record["id"]})
    second = queued.json()
    assert second["id"] != first["id"]
    async with app.state.session_factory() as session:
        event = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == second["id"])
        )
        event_id = event.id
    before = (
        await client.get(
            "/api/v1/turbines/WT-023/structural-health", params={"run_cursor": "z" * 36}
        )
    ).json()
    assert before["analyses"]["items"] == []
    assert before["assessment_status"] == "analysis_in_progress"
    assert before["latest_analysis"]["id"] == second["id"]
    assert await process_structural_event(
        app.state.session_factory, app.state.artifact_verifier, "windops-field-evidence", event_id
    )
    failed = (await client.get(f"/api/v1/structural-analyses/{second['id']}")).json()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "StructuralAlgorithmVersionMismatch"
    assert failed["result"] is None
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ModalObservation)) == 1


async def test_structural_configuration_and_baseline_publication_roles_are_enforced(client):
    headers = {
        "X-WindOps-Test-Role": "field_technician",
        "X-WindOps-Test-Turbine-Ids": "WT-023",
        "X-WindOps-Test-Data-Scopes": "structural",
    }
    component = await post(
        client,
        "tower-components",
        {
            "turbine_id": "WT-023",
            "code": "C1",
            "name": "role challenge",
            "component_type": "joint",
            "revision": "r1",
            "design_reference": "synthetic",
        },
        headers=headers,
    )
    assert component.status_code == 403
    identities = [str(uuid4()) for _ in range(30)]
    payload = {
        "turbine_id": "WT-023",
        "component_id": str(uuid4()),
        "code": "B1",
        "revision": "r1",
        "reference_modal_id": identities[0],
        "training_modal_ids": identities,
        "features": ["temperature_c"],
        "confirmation_reference": "synthetic role challenge",
        "valid_until": "2027-01-01T00:00:00Z",
    }
    field = await post(client, "health-baselines", payload, headers=headers)
    assert field.status_code == 403
    reviewer = await post(
        client,
        "health-baselines",
        payload,
        headers={**headers, "X-WindOps-Test-Role": "maintenance_reviewer"},
    )
    # The legitimate reviewer passes RBAC, then the unavailable component is
    # denied by asset validation; no invalid baseline is created.
    assert reviewer.status_code == 404
