"""Legacy SQL policy compatibility without replacing governed constraints."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from windops_backend.models import IngestSource
from windops_backend.services.ingest import stored_source_policy


def source(**changes):
    return IngestSource(
        id="synthetic-legacy-source",
        display_name="Synthetic legacy split-column source",
        source_kind="rest",
        enabled=True,
        policy={
            "sequence_required": False,
            "allowed_variables": ["main_bearing_vibration_rms"],
            **changes,
        },
    )


def test_legacy_source_uses_actual_identity_columns_and_preserves_json_limits():
    row = source(max_lateness_seconds=15, enabled=False)
    policy = stored_source_policy(row)
    assert policy.display_name == row.display_name and policy.source_kind == row.source_kind
    assert policy.enabled is False
    assert policy.sequence_required is False and policy.max_lateness_seconds == 15
    assert policy.allowed_variables == row.policy["allowed_variables"]
    assert "display_name" not in row.policy


@pytest.mark.parametrize("changes", [{"max_lateness_seconds": -1}, {"source_kind": "invalid-kind"}])
def test_legacy_source_does_not_replace_invalid_persisted_limits(changes):
    with pytest.raises(ValidationError):
        stored_source_policy(source(**changes))


async def test_legacy_source_can_activate_contract_and_ingest_without_losing_restrictions(
    app, client
):
    async with app.state.session_factory() as session, session.begin():
        session.add(source())
    contract = await client.post(
        "/api/v1/platform/data-contracts",
        headers={"Idempotency-Key": "synthetic-legacy-source-contract"},
        json={
            "source_id": "synthetic-legacy-source",
            "variable": "main_bearing_temperature",
            "contract": {
                "label": "Synthetic temperature",
                "unit": "celsius",
                "normal_min": -20,
                "normal_max": 75,
            },
            "expected_revision": 0,
            "reason": "Synthetic compatibility check of an actual legacy policy row.",
        },
    )
    assert contract.status_code == 201, contract.text
    payload = {
        "source_id": "synthetic-legacy-source",
        "samples": [
            {
                "source_event_id": "SYNTHETIC-LEGACY-POLICY-001",
                "turbine_id": "WT-023",
                "observed_at": datetime.now(UTC).isoformat(),
                "variable": "main_bearing_vibration_rms",
                "value": 2.0,
                "unit": "mm/s",
                "quality": "good",
            }
        ],
    }
    accepted = await client.post("/api/v1/scada/ingest", json=payload)
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["results"][0]["disposition"] == "accepted"
    payload["samples"][0].update(
        source_event_id="SYNTHETIC-LEGACY-POLICY-002",
        variable="main_bearing_temperature",
        unit="celsius",
    )
    rejected = await client.post("/api/v1/scada/ingest", json=payload)
    assert rejected.status_code == 202, rejected.text
    assert rejected.json()["results"][0]["disposition"] == "quarantined"
    async with app.state.session_factory() as session:
        row = await session.get(IngestSource, "synthetic-legacy-source")
        assert row.policy["allowed_variables"] == ["main_bearing_vibration_rms"]
        assert row.policy["sequence_required"] is False
        assert row.policy["display_name"] == row.display_name
        row.enabled = False
        await session.commit()
    disabled = await client.post("/api/v1/scada/ingest", json=payload)
    assert disabled.status_code == 403
    assert disabled.json()["error"]["code"] == "INGEST_SOURCE_DISABLED"
