"""Synthetic source-grounded claim challenges; no engineering or field acceptance."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from test_hybrid_structure import acquisition, identities, post, run_analysis
from test_knowledge_passages import ingest
from windops_backend.models import (
    EngineeringClaim,
    EngineeringClaimReview,
    KnowledgeDocument,
)

REVIEWER = {
    "X-WindOps-Test-Principal": "independent-claim-reviewer",
    "X-WindOps-Test-Role": "maintenance_reviewer",
}


async def claim_input(app, client, *, knowledge=False, bad_signal=False):
    component, sensors = await identities(client)
    record, _, _ = await acquisition(
        app,
        client,
        sensors,
        transform=(lambda body: body["channels"][0].update(samples=[0.0] * 4096))
        if bad_signal
        else None,
    )
    run, _ = await run_analysis(app, client, record)
    # This suite tests claims attached to an existing authorized mission. The
    # separate structural-mission workflow is not claimed as accepted here.
    ingested = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": f"SYNTHETIC-CLAIM-MISSION-{uuid4().hex}",
                    "turbine_id": "WT-023",
                    "observed_at": datetime.now(UTC).isoformat(),
                    "variable": "main_bearing_vibration_rms",
                    "value": 4.81,
                    "unit": "mm/s",
                    "quality": "good",
                    "attributes": {
                        "baseline": 3.79,
                        "anomaly_score": 0.86,
                        "source_kind": "synthetic_test",
                    },
                }
            ]
        },
    )
    assert ingested.status_code == 202, ingested.text
    mission_id = ingested.json()["results"][0]["mission_id"]
    assert mission_id
    if knowledge:
        document = await ingest(
            app, client, b"# Synthetic procedure\n\nRecord direct force with valid calibration.\n"
        )
        passages = (
            await client.get(f"/api/v1/knowledge/documents/{document['document_id']}/passages")
        ).json()["passages"]
        evidence = [
            {
                "kind": "knowledge_passage",
                "source_id": passages[-1]["passage_id"],
                "relation": "supports",
                "quote": "Record direct force with valid calibration.",
            }
        ]
    else:
        evidence = [
            {
                "kind": "analysis" if bad_signal else "modal",
                "source_id": run["id"] if bad_signal else run["modal_observations"][0]["id"],
                "relation": "supports",
            }
        ]
        document = None
    return {
        "turbine_id": "WT-023",
        "mission_id": mission_id,
        "component_id": component["id"],
        "claim_kind": "procedure_guidance" if knowledge else "screening_finding",
        "conclusion": "Synthetic source requires scoped human review; qualification is unverified.",
        "applicability": {"boundary": "synthetic software challenge only"},
        "evidence": evidence,
        "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }, document


async def create(client, payload, key=None):
    result = await post(client, "engineering-claims", payload, key=key)
    assert result.status_code == 201, result.text
    return result.json()


async def review(client, claim, *, action="approve", headers=None, revision=None, key=None):
    return await post(
        client,
        f"engineering-claims/{claim['id']}/review",
        {
            "action": action,
            "expected_revision": revision or claim["revision"],
            "reason": "Synthetic independent review of the exact source and applicability.",
        },
        key=key,
        headers=headers or REVIEWER,
    )


async def test_modal_card_preserves_input_identity_units_and_unquantified_limits(app, client):
    payload, _ = await claim_input(app, client)
    key = str(uuid4())
    claim = await create(client, payload, key)
    replay = await post(client, "engineering-claims", payload, key)
    assert replay.status_code == 201 and replay.json() == claim
    assert replay.headers["Idempotency-Replayed"] == "true"
    card = claim["evidence_cards"][0]
    assert card["tenant_id"] == claim["tenant_id"]
    assert card["wind_farm_id"] == claim["wind_farm_id"]
    assert card["applicability"]["component_identity"]["revision"] == "test-r1"
    assert card["source"]["source_kind"] == "synthetic_test"
    assert card["source"]["integrity"] == "verified_at_ingestion"
    assert card["measurements"][0] == {"name": "frequency", "value": 0.5, "unit": "Hz"}
    assert card["measurements"][1]["value"] is None
    assert card["uncertainty"]["status"] == "unquantified"
    assert card["method"]["absolute_prestress_available"] is False
    assert card["method"]["algorithm_identity"]["adapter_sha256"]
    assert claim["effective_status"] == "pending" and claim["usable_for_reasoning"] is False
    assert claim["authorizes_work"] is False and claim["field_qualification"] == "unverified"
    approved = await review(client, claim)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["effective_status"] == "approved" and body["revision"] == 2
    assert body["usable_for_reasoning"] is True and body["authorizes_work"] is False
    assert body["content_sha256"] == claim["content_sha256"]
    assert (
        len(body["reviews"]) == 1
        and body["reviews"][0]["reviewed_by"] == REVIEWER["X-WindOps-Test-Principal"]
    )
    stale = await review(client, claim)
    assert stale.status_code == 409
    withdrawn = await review(client, body, action="withdraw")
    assert withdrawn.status_code == 200 and withdrawn.json()["usable_for_reasoning"] is False
    assert len(withdrawn.json()["reviews"]) == 2


async def test_author_role_and_missing_evidence_cannot_bypass_review(app, client):
    payload, _ = await claim_input(app, client)
    claim = await create(
        client,
        {**payload, "missing_evidence": ["Authorized site procedure has not been supplied."]},
    )
    self_review = await review(
        client,
        claim,
        headers={
            "X-WindOps-Test-Principal": "integration-test-system",
            "X-WindOps-Test-Role": "test_system",
        },
    )
    assert self_review.status_code == 422 and "own independent review" in self_review.text
    denied = await review(
        client,
        claim,
        headers={
            "X-WindOps-Test-Principal": "field-claim-reader",
            "X-WindOps-Test-Role": "field_technician",
        },
    )
    assert denied.status_code == 403
    missing = await review(client, claim)
    assert missing.status_code == 422 and "missing or unusable" in missing.text
    rejected = await review(client, claim, action="reject")
    assert rejected.status_code == 200 and rejected.json()["effective_status"] == "rejected"
    assert (await review(client, rejected.json())).status_code == 422


async def test_unusable_analysis_is_preserved_without_a_qualified_finding(app, client):
    payload, _ = await claim_input(app, client, bad_signal=True)
    claim = await create(client, payload)
    assert claim["evidence_cards"][0]["quality"]["usable"] is False
    calibration = claim["evidence_cards"][0]["method"]["calibration"]
    assert claim["evidence_cards"][0]["quality"]["exclusions"] == [
        f"{calibration[0]['id']}:flat_channel"
    ]
    assert claim["evidence_cards"][0]["measurements"] == []
    rejected = await review(client, claim)
    assert rejected.status_code == 422
    recommendation = await create(
        client,
        {
            **payload,
            "claim_kind": "retest_recommendation",
            "missing_evidence": ["A usable synchronized measurement window must be recollected."],
        },
    )
    approved = await review(client, recommendation)
    assert approved.status_code == 200, approved.text
    assert approved.json()["permitted_use"] == "retest_proposal_only"
    assert approved.json()["missing_evidence"] == recommendation["missing_evidence"]
    assert approved.json()["evidence_cards"][0]["quality"]["usable"] is False
    assert approved.json()["authorizes_work"] is False


async def test_exact_quote_unknown_page_and_source_version_drift(app, client):
    payload, document = await claim_input(app, client, knowledge=True)
    wrong = {
        **payload,
        "evidence": [{**payload["evidence"][0], "quote": "Invented site acceptance threshold."}],
    }
    assert (await post(client, "engineering-claims", wrong)).status_code == 422
    claim = await create(client, payload)
    source = claim["evidence_cards"][0]["source"]
    assert source["page_number"] is None and source["native_locator"]["kind"] == "text_lines"
    assert source["document_version"] == "synthetic-r1"
    assert source["quote_char_end"] - source["quote_char_start"] == len(source["quote"])
    async with app.state.session_factory() as session:
        row = await session.get(KnowledgeDocument, document["document_id"])
        row.document_version = "synthetic-r2-drift-challenge"
        await session.commit()
    stale = await client.get(f"/api/v1/engineering-claims/{claim['id']}")
    assert stale.status_code == 200 and stale.json()["effective_status"] == "source_changed"
    assert (await review(client, claim)).status_code == 422


async def test_changed_source_bytes_fail_review_and_leave_claim_pending(app, client):
    payload, document = await claim_input(app, client, knowledge=True)
    claim = await create(client, payload)
    app.state.artifact_verifier.register_object(
        document["artifact_uri"], b"replaced source", "text/markdown"
    )
    result = await review(client, claim)
    assert result.status_code == 422 and "SHA-256" in result.text
    async with app.state.session_factory() as session:
        row = await session.get(EngineeringClaim, claim["id"])
        assert row.review_status == "pending" and row.revision == 1
        assert not (
            await session.scalars(
                select(EngineeringClaimReview).where(EngineeringClaimReview.claim_id == row.id)
            )
        ).all()


async def test_expiry_cross_asset_duplicate_and_contradictory_sources(app, client):
    payload, _ = await claim_input(app, client)
    assert (
        await post(client, "engineering-claims", {**payload, "turbine_id": "WT-001"})
    ).status_code == 404
    assert (
        await post(client, "engineering-claims", {**payload, "valid_until": "2026-01-01T00:00:00Z"})
    ).status_code == 422
    assert (
        await post(client, "engineering-claims", {**payload, "evidence": payload["evidence"] * 2})
    ).status_code == 422
    second = await ingest(
        app, client, b"This is synthetic counterevidence requiring manual interpretation."
    )
    passage = (
        await client.get(f"/api/v1/knowledge/documents/{second['document_id']}/passages")
    ).json()["passages"][0]
    claim = await create(
        client,
        {
            **payload,
            "evidence": [
                *payload["evidence"],
                {
                    "kind": "knowledge_passage",
                    "source_id": passage["passage_id"],
                    "relation": "contradicts",
                    "quote": passage["text"],
                },
            ],
        },
    )
    assert [c["reference"]["relation"] for c in claim["evidence_cards"]] == [
        "supports",
        "contradicts",
    ]
    # Expiry is a read-time gate; no scheduler is needed to invalidate approval.
    async with app.state.session_factory() as session:
        row = await session.get(EngineeringClaim, claim["id"])
        row.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        row.valid_until = datetime(2026, 1, 2, tzinfo=UTC)
        await session.commit()
    expired = await client.get(f"/api/v1/engineering-claims/{claim['id']}")
    assert (
        expired.json()["effective_status"] == "expired"
        and expired.json()["usable_for_reasoning"] is False
    )
    assert (await review(client, claim)).status_code == 422


async def test_current_source_permissions_are_rechecked_for_mixed_domain_claims(app, client):
    payload, _ = await claim_input(app, client, knowledge=True)
    headers = {
        "X-WindOps-Test-Principal": "structural-only-reader",
        "X-WindOps-Test-Role": "maintenance_reviewer",
        "X-WindOps-Test-Turbine-Ids": "WT-023",
        "X-WindOps-Test-Data-Scopes": "structural",
        "X-WindOps-Test-Allow-Global": "true",
    }
    key = str(uuid4())
    granted = await post(
        client,
        "engineering-claims",
        payload,
        key=key,
        headers={**headers, "X-WindOps-Test-Data-Scopes": "structural,knowledge"},
    )
    assert granted.status_code == 201, granted.text
    claim = granted.json()
    denied = await client.get(f"/api/v1/engineering-claims/{claim['id']}", headers=headers)
    assert denied.status_code == 404
    replay = await post(client, "engineering-claims", payload, key=key, headers=headers)
    assert replay.status_code == 404
    cross = await client.get(
        f"/api/v1/engineering-claims/{claim['id']}",
        headers={
            **headers,
            "X-WindOps-Test-Principal": "other-asset-reader",
            "X-WindOps-Test-Turbine-Ids": "WT-001",
            "X-WindOps-Test-Data-Scopes": "structural,knowledge",
        },
    )
    assert cross.status_code == 404


async def test_direct_force_card_retains_calibration_and_does_not_infer_loss(app, client):
    import json

    payload, _ = await claim_input(app, client)
    tendon = await post(
        client,
        "tendon-assemblies",
        {
            "turbine_id": "WT-023",
            "component_id": payload["component_id"],
            "code": "SYNTHETIC-TENDON",
            "revision": "r1",
        },
    )
    assert tendon.status_code == 201, tendon.text
    sensor = await post(
        client,
        "sensor-channels",
        {
            "turbine_id": "WT-023",
            "component_id": payload["component_id"],
            "tendon_id": tendon.json()["id"],
            "code": "SYNTHETIC-FORCE",
            "revision": "r1",
            "quantity": "force",
            "unit": "N",
            "direction": "axial",
            "range_min": 0,
            "range_max": 500000,
            "calibration_version": "synthetic-cal1",
            "calibration_at": "2026-01-01T00:00:00Z",
            "calibration_valid_until": "2027-01-01T00:00:00Z",
            "calibration_reference": "synthetic fixture only",
            "synchronization_source": "test-clock",
        },
    )
    assert sensor.status_code == 201, sensor.text
    body = {
        "schema_version": "openvigil.direct-force.v1",
        "tendon_id": tendon.json()["id"],
        "sensor_id": sensor.json()["id"],
        "observed_at": datetime.now(UTC).isoformat(),
        "unit": "N",
        "value": 125000,
        "calibration_version": "synthetic-cal1",
        "uncertainty_kn": 0.25,
    }
    uri = f"minio://windops-field-evidence/structural/turbines/WT-023/{uuid4()}.json"
    sha = app.state.artifact_verifier.register_object(
        uri, json.dumps(body).encode(), "application/json"
    )
    observation = await post(
        client,
        "prestress-observations",
        {
            "turbine_id": "WT-023",
            "tendon_id": tendon.json()["id"],
            "sensor_id": sensor.json()["id"],
            "artifact_uri": uri,
            "artifact_sha256": sha,
            "source_kind": "synthetic_test",
        },
    )
    assert observation.status_code == 201, observation.text
    claim = await create(
        client,
        {
            **payload,
            "evidence": [
                {"kind": "prestress", "source_id": observation.json()["id"], "relation": "supports"}
            ],
        },
    )
    card = claim["evidence_cards"][0]
    assert card["measurements"] == [{"name": "direct_force", "value": 125, "unit": "kN"}]
    assert card["uncertainty"] == {
        "status": "quantified",
        "absolute_kn": 0.25,
        "source": "measurement_artifact",
    }
    assert card["method"]["sensor"]["calibration_version"] == "synthetic-cal1"
    assert card["source"]["sha256"] == sha and card["source"]["tendon_id"] == tendon.json()["id"]
    assert "loss_percentage" not in card and "damage_probability" not in card
    approved = await review(client, claim)
    assert approved.status_code == 200, approved.text
