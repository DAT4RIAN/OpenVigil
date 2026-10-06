"""Synthetic software acceptance of the actual API, workers and human boundaries."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from test_engineering_claims import review
from test_hybrid_structure import acquisition, identities, post, run_analysis
from test_knowledge_passages import ingest
from windops_backend.models import (
    Alarm,
    IngestReceipt,
    Mission,
    Resource,
    ScadaSample,
    StructuralMissionContext,
    Turbine,
    WorkOrder,
)

FIELD = {
    "X-WindOps-Test-Principal": "synthetic-field-author",
    "X-WindOps-Test-Role": "field_technician",
}
HEALTH = {
    "X-WindOps-Test-Principal": "synthetic-health-reviewer",
    "X-WindOps-Test-Role": "maintenance_reviewer",
}
CASE = {
    "X-WindOps-Test-Principal": "synthetic-case-reviewer",
    "X-WindOps-Test-Role": "maintenance_reviewer",
}


async def force_source(app, client, tendon, sensor, value, *, observed_at=None):
    body = {
        "schema_version": "openvigil.direct-force.v1",
        "tendon_id": tendon["id"],
        "sensor_id": sensor["id"],
        "observed_at": (observed_at or datetime.now(UTC)).isoformat(),
        "unit": "N",
        "value": value,
        "calibration_version": sensor["calibration_version"],
        "uncertainty_kn": 0.25,
    }
    uri = f"minio://windops-field-evidence/structural/turbines/WT-023/{uuid4()}.json"
    sha = app.state.artifact_verifier.register_object(
        uri, json.dumps(body).encode(), "application/json"
    )
    result = await post(
        client,
        "prestress-observations",
        {
            "turbine_id": "WT-023",
            "tendon_id": tendon["id"],
            "sensor_id": sensor["id"],
            "artifact_uri": uri,
            "artifact_sha256": sha,
            "source_kind": "synthetic_test",
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


async def force_order(app, client):
    component, _ = await identities(client)
    tendon = await post(
        client,
        "tendon-assemblies",
        {
            "turbine_id": "WT-023",
            "component_id": component["id"],
            "code": "SYNTHETIC-T1",
            "revision": "r1",
            "boundary": {"anchor": "synthetic calibration fixture"},
        },
    )
    assert tendon.status_code == 201, tendon.text
    sensor = await post(
        client,
        "sensor-channels",
        {
            "turbine_id": "WT-023",
            "component_id": component["id"],
            "tendon_id": tendon.json()["id"],
            "code": "SYNTHETIC-F1",
            "revision": "r1",
            "quantity": "force",
            "unit": "N",
            "direction": "axial",
            "range_min": 0,
            "range_max": 500000,
            "calibration_version": "synthetic-cal1",
            "calibration_at": "2026-01-01T00:00:00Z",
            "calibration_valid_until": "2027-01-01T00:00:00Z",
            "calibration_reference": "synthetic test only",
            "synchronization_source": "synthetic-clock",
        },
    )
    assert sensor.status_code == 201, sensor.text
    tendon, sensor = tendon.json(), sensor.json()
    previous = await force_source(
        app, client, tendon, sensor, 125000, observed_at=datetime.now(UTC) - timedelta(days=2)
    )
    origin = await force_source(
        app, client, tendon, sensor, 110000, observed_at=datetime.now(UTC) - timedelta(days=1)
    )
    document = await ingest(
        app,
        client,
        b"# Synthetic acceptance fixture\n\n"
        b"Accept direct force from 120 kN to 130 kN for this synthetic test only.\n",
    )
    passages = (
        await client.get(f"/api/v1/knowledge/documents/{document['document_id']}/passages")
    ).json()["passages"]
    async with app.state.session_factory() as session, session.begin():
        session.add(
            Resource(
                id="SYNTHETIC-MEASUREMENT-KIT",
                resource_type="measurement_equipment",
                name="Synthetic measurement kit",
                quantity=1,
                status="available",
            )
        )
    payload = {
        "turbine_id": "WT-023",
        "component_id": component["id"],
        "title": "Synthetic prestress anomaly retest",
        "scenario": "prestress_retest",
        "source_id": origin["id"],
        "previous_prestress_id": previous["id"],
        "planning_duration_hours": 1,
        "force_acceptance": {
            "minimum_kn": 120,
            "maximum_kn": 130,
            "procedure": {
                "kind": "knowledge_passage",
                "source_id": passages[-1]["passage_id"],
                "relation": "supports",
                "quote": "Accept direct force from 120 kN to 130 kN for this synthetic test only.",
            },
        },
    }
    created = await post(client, "structural-missions", payload)
    assert created.status_code == 202, created.text
    mission = (await client.get(f"/api/v1/missions/{created.json()['mission_id']}")).json()
    claim = (
        await client.get(
            f"/api/v1/engineering-claims/{mission['public_state']['engineering_claim_id']}"
        )
    ).json()
    assert (await review(client, claim)).status_code == 200
    approved = await post(
        client,
        f"missions/{mission['mission_id']}/approvals",
        {
            "action": "approve",
            "expected_revision": mission["revision"],
            "reason": (
                "Approve source-reviewed synthetic retest only; "
                "no field or operating qualification."
            ),
        },
    )
    assert approved.status_code == 200, approved.text
    order = (
        await client.get(f"/api/v1/structural-work-orders/{approved.json()['work_order_id']}")
    ).json()
    return tendon, sensor, origin, order


async def finish_field_task(app, client, order, sequence, measurement):
    task = order["tasks"][sequence - 1]
    work_order_id = order["work_order"]["id"]
    uri = f"minio://windops-field-evidence/work-orders/{work_order_id}/tasks/{task['id']}/{uuid4()}.json"
    sha = app.state.artifact_verifier.register_object(
        uri, json.dumps(measurement).encode(), "application/json"
    )
    return await post(
        client,
        f"work-orders/{work_order_id}/tasks/{task['id']}/complete",
        {
            "result": "Synthetic field evidence for software acceptance only.",
            "artifact_uri": uri,
            "artifact_sha256": sha,
            "measurement": measurement,
        },
        headers=FIELD,
    )


async def field_handoff(app, client, order, source_id):
    first = await finish_field_task(
        app,
        client,
        order,
        1,
        {
            "permit_reference": "synthetic-permit",
            "isolation_reference": "synthetic-isolation",
            "calibration_reference": "synthetic-cal1",
        },
    )
    assert first.status_code == 200, first.text
    last = await finish_field_task(
        app,
        client,
        order,
        2,
        {"retest_source_id": source_id, "measurement_reference": "synthetic calibrated retest"},
    )
    assert last.status_code == 200, last.text
    assert last.json()["work_order_status"] == "awaiting_health_review"
    assert last.json()["workflow_finalized"] is False


async def test_force_retest_closes_only_after_independent_health_review_and_case_approval(
    app, client
):
    tendon, sensor, origin, order = await force_order(app, client)
    comparison = order["context"]["comparison"]
    assert comparison["change_kn"] == -15 and comparison["status"] == "requires_review"
    assert comparison["damage_probability"] is None
    assert order["context"]["missing_evidence"] == []
    observation = await force_source(app, client, tendon, sensor, 125000)
    await field_handoff(app, client, order, observation["id"])
    mission_id, work_order_id = order["work_order"]["mission_id"], order["work_order"]["id"]
    before = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert before["status"] == "executing"
    async with app.state.session_factory() as session:
        turbine = await session.get(Turbine, "WT-023")
        score, status = turbine.health_score, turbine.status
        alarm = await session.get(Alarm, before["alarm_id"])
        assert alarm.status == "open"
    request = {
        "expected_mission_revision": before["revision"],
        "action": "resolve_review",
        "reason": (
            "Synthetic independent review: exact procedure, calibration, retest and asset checked."
        ),
        "hypothesis_outcome": "not_supported",
    }
    author_attempt = await post(
        client,
        f"structural-work-orders/{work_order_id}/health-review",
        request,
        headers={**FIELD, "X-WindOps-Test-Role": "maintenance_reviewer"},
    )
    assert author_attempt.status_code == 422 and "independent" in author_attempt.text
    key = str(uuid4())
    result = await post(
        client,
        f"structural-work-orders/{work_order_id}/health-review",
        request,
        key,
        headers=HEALTH,
    )
    assert result.status_code == 200, result.text
    replay = await post(
        client,
        f"structural-work-orders/{work_order_id}/health-review",
        request,
        key,
        headers=HEALTH,
    )
    assert replay.json() == result.json() and replay.headers["Idempotency-Replayed"] == "true"
    case_id = result.json()["knowledge_case_id"]
    assert result.json()["case_review_status"] == "pending"
    async with app.state.session_factory() as session:
        turbine = await session.get(Turbine, "WT-023")
        assert (turbine.health_score, turbine.status) == (score, status)
        assert (await session.get(Mission, mission_id)).status == "completed"
        assert (await session.get(Alarm, before["alarm_id"])).status == "resolved"
        from windops_backend.agents.tools import SQLToolAdapter

        hits = await SQLToolAdapter(session).query_similar_failures("direct force", "WT-023")
        assert not any(hit.get("case_id") == case_id for hit in hits)
    pending = (await client.get("/api/v1/structural-cases?turbine_id=WT-023")).json()
    assert pending["items"][0]["case"]["id"] == case_id
    case_request = {
        "expected_revision": 1,
        "action": "approve",
        "reason": (
            "Synthetic independent case review preserves actual observations and uncertainty."
        ),
    }
    self_review = await post(
        client, f"structural-cases/{case_id}/review", case_request, headers=HEALTH
    )
    assert self_review.status_code == 422
    published = await post(client, f"structural-cases/{case_id}/review", case_request, headers=CASE)
    assert published.status_code == 200 and published.json()["status"] == "approved"
    async with app.state.session_factory() as session:
        from windops_backend.agents.tools import SQLToolAdapter

        hits = await SQLToolAdapter(session).query_similar_failures("direct force", "WT-023")
        assert any(hit.get("case_id") == case_id for hit in hits)


async def test_out_of_bounds_retest_preserves_unresolved_alarm_and_immutable_followup_review(
    app, client
):
    tendon, sensor, _, order = await force_order(app, client)
    observation = await force_source(app, client, tendon, sensor, 115000)
    await field_handoff(app, client, order, observation["id"])
    request = {
        "expected_mission_revision": order["context"]["revision"],
        "action": "resolve_review",
        "reason": "Synthetic review of still-out-of-bounds result.",
        "hypothesis_outcome": "inconclusive",
    }
    path = f"structural-work-orders/{order['work_order']['id']}/health-review"
    blocked = await post(client, path, request, headers=HEALTH)
    assert blocked.status_code == 422 and "force_outside" in blocked.text
    followup = await post(client, path, {**request, "action": "requires_followup"}, headers=HEALTH)
    assert followup.status_code == 200, followup.text
    assert followup.json()["knowledge_case_id"] is None
    assert followup.json()["review"]["assessment"]["eligible_to_resolve_review"] is False
    assert followup.json()["work_order_status"] == "awaiting_health_review"
    stale = await post(client, path, {**request, "action": "requires_followup"}, headers=HEALTH)
    assert stale.status_code == 409
    async with app.state.session_factory() as session:
        mission = await session.get(Mission, order["work_order"]["mission_id"])
        assert mission.status == "executing"
        assert (await session.get(Alarm, mission.alarm_id)).status == "open"
    # A fresh follow-up is appended under the same reviewed scope; no old
    # measurements or reviews are overwritten to manufacture closure.
    followup_source = await force_source(app, client, tendon, sensor, 125000)
    measurement = {
        "retest_source_id": followup_source["id"],
        "measurement_reference": "new synthetic retest after unresolved review",
    }
    content = json.dumps(measurement).encode()
    import hashlib

    uploaded = await post(
        client,
        f"structural-work-orders/{order['work_order']['id']}/retests/uploads/presign",
        {
            "file_name": "synthetic-followup.json",
            "content_type": "application/json",
            "artifact_sha256": hashlib.sha256(content).hexdigest(),
        },
        headers=FIELD,
    )
    assert uploaded.status_code == 200, uploaded.text
    uri = uploaded.json()["artifact_uri"]
    sha = app.state.artifact_verifier.register_object(uri, content, "application/json")
    handoff = await post(
        client,
        f"structural-work-orders/{order['work_order']['id']}/retests",
        {
            "expected_mission_revision": followup.json()["mission_revision"],
            "measurement": measurement,
            "result": "New calibrated synthetic handoff; old out-of-bounds evidence retained.",
            "artifact_uri": uri,
            "artifact_sha256": sha,
        },
        headers=FIELD,
    )
    assert handoff.status_code == 201, handoff.text
    history = (
        await client.get(f"/api/v1/structural-work-orders/{order['work_order']['id']}")
    ).json()["retest_handoffs"]
    assert len(history) == 1
    assert history[0]["id"] == handoff.json()["evidence"]["id"]
    assert history[0]["health_review_id"] == followup.json()["review"]["id"]
    assert history[0]["prestress_id"] == followup_source["id"]
    assert history[0]["modal_id"] is None
    assert history[0]["artifact_sha256"] == sha
    denied_history = await client.get(
        f"/api/v1/structural-work-orders/{order['work_order']['id']}",
        headers={
            "X-WindOps-Test-Principal": "foreign-handoff-reader",
            "X-WindOps-Test-Role": "maintenance_reviewer",
            "X-WindOps-Test-Turbine-Ids": "WT-999",
            "X-WindOps-Test-Data-Scopes": "structural",
        },
    )
    assert denied_history.status_code == 404
    assert sha not in denied_history.text
    resolved = await post(
        client,
        path,
        {**request, "expected_mission_revision": handoff.json()["mission_revision"]},
        headers=HEALTH,
    )
    assert resolved.status_code == 200, resolved.text
    refreshed = (
        await client.get(f"/api/v1/structural-work-orders/{order['work_order']['id']}")
    ).json()
    assert [row["action"] for row in refreshed["health_reviews"]] == [
        "requires_followup",
        "resolve_review",
    ]
    assert refreshed["health_reviews"][0]["assessment"]["comparison"]["value_kn"] == 115
    assert refreshed["health_reviews"][1]["assessment"]["comparison"]["value_kn"] == 125
    assert refreshed["retest_handoffs"] == history


async def test_retest_rejects_original_and_prework_sources(app, client):
    tendon, sensor, original, order = await force_order(app, client)
    first = await finish_field_task(
        app,
        client,
        order,
        1,
        {
            "permit_reference": "synthetic-permit",
            "isolation_reference": "synthetic-isolation",
            "calibration_reference": "synthetic-cal1",
        },
    )
    assert first.status_code == 200
    reused = await finish_field_task(
        app,
        client,
        order,
        2,
        {"retest_source_id": original["id"], "measurement_reference": "invalid original reuse"},
    )
    assert reused.status_code == 422 and "original" in reused.text
    earlier = await force_source(
        app, client, tendon, sensor, 124000, observed_at=datetime.now(UTC) - timedelta(hours=2)
    )
    prework = await finish_field_task(
        app,
        client,
        order,
        2,
        {"retest_source_id": earlier["id"], "measurement_reference": "invalid old acquisition"},
    )
    assert prework.status_code == 422 and "after the work order" in prework.text
    refreshed = (
        await client.get(f"/api/v1/structural-work-orders/{order['work_order']['id']}")
    ).json()
    assert refreshed["tasks"][1]["status"] == "pending"
    assert refreshed["work_order"]["status"] == "in_progress"


async def test_structural_mission_grants_and_frozen_profile_cannot_be_bypassed(app, client):
    payload, created, mission = await modal_mission(app, client)
    denied = await client.get(
        f"/api/v1/structural-missions/{created['mission_id']}",
        headers={
            "X-WindOps-Test-Principal": "foreign-structural-reader",
            "X-WindOps-Test-Role": "maintenance_reviewer",
            "X-WindOps-Test-Turbine-Ids": "WT-999",
            "X-WindOps-Test-Data-Scopes": "structural",
        },
    )
    assert denied.status_code == 404
    forbidden = await post(
        client,
        "structural-missions",
        payload,
        headers={
            "X-WindOps-Test-Principal": "domain-limited-manager",
            "X-WindOps-Test-Role": "operations_manager",
            "X-WindOps-Test-Turbine-Ids": "WT-023",
            "X-WindOps-Test-Data-Scopes": "asset",
        },
    )
    assert forbidden.status_code == 403
    technician = await post(client, "structural-missions", payload, headers=FIELD)
    assert technician.status_code == 403
    async with app.state.session_factory() as session, session.begin():
        row = await session.get(Mission, created["mission_id"])
        profile = dict(row.public_state["analysis_profile"])
        profile["primary_variable"] = "main_bearing_vibration_rms"
        row.public_state = {**row.public_state, "analysis_profile": profile}
    invalid = await client.get(f"/api/v1/structural-missions/{created['mission_id']}")
    assert invalid.status_code == 422 and "frozen template" in invalid.text


async def test_approval_rechecks_actual_source_bytes_after_claim_review(app, client):
    payload, created, mission = await modal_mission(app, client)
    claim = (
        await client.get(
            f"/api/v1/engineering-claims/{mission['public_state']['engineering_claim_id']}"
        )
    ).json()
    approved = await review(client, claim)
    assert approved.status_code == 200
    card = claim["evidence_cards"][0]
    app.state.artifact_verifier.register_object(
        card["source"]["artifact_uri"], b'{"changed":"after-human-review"}', "application/json"
    )
    result = await post(
        client,
        f"missions/{created['mission_id']}/approvals",
        {
            "action": "approve",
            "expected_revision": mission["revision"],
            "reason": "Synthetic attempt with source bytes changed after review.",
        },
    )
    assert result.status_code == 422 and "SHA-256" in result.text
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(WorkOrder)) == 0
        assert (await session.get(Mission, created["mission_id"])).status == "under_review"


async def test_approval_receipt_replay_cannot_bypass_revoked_asset_grant(app, client):
    _, created, mission = await modal_mission(app, client)
    key = str(uuid4())
    payload = {
        "action": "reject",
        "expected_revision": mission["revision"],
        "reason": "Synthetic rejection to test receipt permission changes.",
    }
    path = f"missions/{created['mission_id']}/approvals"
    principal = {
        "X-WindOps-Test-Principal": "synthetic-scoped-approver",
        "X-WindOps-Test-Role": "operations_approver",
        "X-WindOps-Test-Turbine-Ids": "WT-023",
    }
    initial = await post(client, path, payload, key, headers=principal)
    assert initial.status_code == 200, initial.text
    changed_grant = await post(
        client,
        path,
        payload,
        key,
        headers={**principal, "X-WindOps-Test-Turbine-Ids": "WT-999"},
    )
    assert changed_grant.status_code == 404


def test_legacy_execution_plan_identity_survives_structural_closure_extension():
    from windops_backend.schemas import MissionAnalysisProfile
    from windops_backend.work_plan_binding import describe_execution_plan

    # Captured by executing the unchanged HEAD schema/template/binding source,
    # not reconstructed from the new serializer or its implementation.
    expected = {
        "main_bearing": "workplan:ffd5bd29d521adaabd1e2593cccd9e434dc460138724bb634e1fb17b6fd2b25b",
        "gearbox": "workplan:1e783caeee8b1abdc1c576339037ddbae5b39d03512e436505e0de04b0d161af",
    }
    for component, variable in (
        ("main_bearing", "main_bearing_vibration_rms"),
        ("gearbox", "gearbox_oil_temperature"),
    ):
        descriptor = describe_execution_plan(
            MissionAnalysisProfile(
                component=component,
                primary_variable=variable,
                knowledge_query="controlled legacy inspection",
            ),
            "WT-023",
        )
        assert descriptor["execution_plan_id"] == expected[component]
        assert "closure_kind" not in descriptor["plan"]


async def modal_mission(app, client):
    component, sensors = await identities(client)
    record, _, _ = await acquisition(app, client, sensors)
    run, _ = await run_analysis(app, client, record)
    payload = {
        "turbine_id": "WT-023",
        "component_id": component["id"],
        "title": "Synthetic modal review with no pilot qualification",
        "scenario": "modal_frequency_review",
        "source_id": run["modal_observations"][0]["id"],
        "planning_duration_hours": 1.5,
    }
    result = await post(client, "structural-missions", payload)
    assert result.status_code == 202, result.text
    mission_id = result.json()["mission_id"]
    mission = await client.get(f"/api/v1/missions/{mission_id}")
    assert mission.status_code == 200, mission.text
    return payload, result.json(), mission.json()


async def test_modal_origin_uses_actual_source_and_abstains_without_baseline(app, client):
    payload, created, mission = await modal_mission(app, client)
    assert mission["status"] == "under_review", mission
    public = mission["public_state"]
    assert public["diagnosis"]["confidence"] is None
    assert public["diagnosis"]["damage_probability"] is None
    assert public["diagnosis"]["failure_mode"] == "insufficient_structural_evidence"
    assert public["diagnosis"]["missing_evidence"] == ["confirmed_environmental_baseline"]
    assert public["engineering_claim_id"]
    assert [execution["node"] for execution in mission["executions"]] == [
        "scada",
        "vibration",
        "knowledge",
        "diagnosis",
        "alternatives",
        "reviews",
        "hitl",
    ]
    assert all(execution["status"] == "succeeded" for execution in mission["executions"])
    alternatives = mission["decision"]["alternatives"]
    assert alternatives[0]["estimated_cost_cny"] is None
    assert alternatives[0]["estimated_energy_loss_mwh"] is None
    assert alternatives[0]["required_resources"] == ["crew", "measurement_equipment"]
    assert "turbine_health_score" not in str(created["analysis_profile"]["work_order_plan"])
    assert created["evidence_cards"][0]["measurements"][0]["value"] == 0.5
    async with app.state.session_factory() as session:
        origin = await session.get(StructuralMissionContext, created["mission_id"])
        alarm = await session.get(Alarm, created["alarm_id"])
        receipt = await session.get(IngestReceipt, alarm.source_event_id)
        assert receipt.source_id == "structural-evidence"
        assert receipt.payload_hash == origin.origin_fingerprint
        assert await session.scalar(select(func.count()).select_from(ScadaSample)) == 0
        assert await session.scalar(select(func.count()).select_from(WorkOrder)) == 0
    duplicate = await post(client, "structural-missions", payload)
    assert duplicate.status_code == 202
    assert duplicate.json()["mission_id"] == created["mission_id"]
    assert (
        await post(client, "structural-missions", {**payload, "planning_duration_hours": 2})
    ).status_code == 409


async def test_structural_approval_requires_exact_reviewed_claim_and_cannot_use_generic_endpoint(
    app, client
):
    payload, created, mission = await modal_mission(app, client)
    before = await post(
        client,
        f"missions/{created['mission_id']}/approvals",
        {
            "action": "approve",
            "expected_revision": mission["revision"],
            "reason": "Synthetic human approval attempt before claim review.",
        },
    )
    assert before.status_code == 422, before.text
    assert "claim" in before.text
    generic = await post(
        client,
        "missions",
        {
            "alarm_id": created["alarm_id"],
            "title": "Bypass attempt",
            "analysis_profile": created["analysis_profile"],
        },
    )
    assert generic.status_code == 400, generic.text
    assert "server-frozen" in generic.text
    claim = (
        await client.get(
            f"/api/v1/engineering-claims/{mission['public_state']['engineering_claim_id']}"
        )
    ).json()
    approved = await review(client, claim)
    assert approved.status_code == 200, approved.text
    assert approved.json()["permitted_use"] == "retest_proposal_only"
    async with app.state.session_factory() as session, session.begin():
        session.add(
            Resource(
                id="SYNTHETIC-MEASUREMENT-KIT",
                resource_type="measurement_equipment",
                name="Synthetic calibrated measurement test kit",
                quantity=1,
                status="available",
            )
        )
    # Missing inventory caused an actual fail review. Request revision to recompute it;
    # approval cannot silently turn that review into a pass.
    revision = await post(
        client,
        f"missions/{created['mission_id']}/approvals",
        {
            "action": "request_revision",
            "expected_revision": mission["revision"],
            "reason": "Synthetic measurement kit is now available; recompute reviews.",
        },
    )
    assert revision.status_code == 200, revision.text
    refreshed = (await client.get(f"/api/v1/missions/{created['mission_id']}")).json()
    new_claim = (
        await client.get(
            f"/api/v1/engineering-claims/{refreshed['public_state']['engineering_claim_id']}"
        )
    ).json()
    assert new_claim["review_status"] == "pending"
    assert (await review(client, new_claim)).status_code == 200
    result = await post(
        client,
        f"missions/{created['mission_id']}/approvals",
        {
            "action": "approve",
            "expected_revision": refreshed["revision"],
            "reason": "Approve controlled synthetic retest only.",
        },
    )
    assert result.status_code == 200, result.text
    order = (
        await client.get(f"/api/v1/structural-work-orders/{result.json()['work_order_id']}")
    ).json()
    assert order["work_order"]["closure_policy"]["kind"] == "structural_retest"
    assert order["work_order"]["assigned_team"] == "Onshore structural measurement team"
    assert len(order["tasks"]) == 2
    assert order["work_order"]["safety_plan"]["tensioning_authority"] is False
