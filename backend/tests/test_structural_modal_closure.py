"""Actual FDD/30-window software closure; synthetic signals and explicit virtual time.

The virtual clock avoids waiting for a full 256-second post-work acquisition.
It changes time only, never the method, calibration, source bytes or window gates.
The object verifier is in memory; this is not site or MinIO acceptance.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import func, select

from test_engineering_claims import review
from test_hybrid_structure import FS, N, acquisition, identities, post, run_analysis
from test_structural_workflow import CASE, HEALTH, finish_field_task
from windops_backend import model_base
from windops_backend.knowledge_graph.domain import NodeType, graph_uid
from windops_backend.knowledge_graph.projection import build_knowledge_graph_snapshot
from windops_backend.models import (
    Alarm,
    Mission,
    ModalObservation,
    Resource,
    Turbine,
    WaveformRecord,
)
from windops_backend.schema_structural import aware
from windops_backend.services import structural_closure, workorders


async def test_actual_modal_retest_closes_with_confirmed_baseline_and_complete_postwork_window(
    app, client, monkeypatch
):
    component, sensors = await identities(client)
    now = datetime.now(UTC)
    modal_ids = []
    # Independent, chronological windows cover a repeated environment range;
    # FDD runs via the actual bounded worker, not prefilled ModalObservation rows.
    for index in range(30):
        record, _, _ = await acquisition(
            app,
            client,
            sensors,
            started_at=now - timedelta(days=3) + timedelta(hours=index),
            environment={
                "operating_state": "stopped",
                "rotor_speed_rpm": 0,
                "temperature_c": index % 10,
            },
        )
        result, _ = await run_analysis(app, client, record)
        assert result["status"] == "succeeded", result
        assert result["result"]["quality"]["usable"] is True
        modal_ids.append(result["modal_observations"][0]["id"])
    published = await post(
        client,
        "health-baselines",
        {
            "turbine_id": "WT-023",
            "component_id": component["id"],
            "code": "synthetic-modal-closure",
            "revision": "synthetic-r1",
            "confirmation_reference": "Synthetic healthy software windows; no field qualification.",
            "reference_modal_id": modal_ids[0],
            "training_modal_ids": modal_ids,
            "features": ["temperature_c"],
            "valid_until": (now + timedelta(days=30)).isoformat(),
        },
    )
    assert published.status_code == 201, published.text
    baseline = published.json()
    assert baseline["source_kind"] == "synthetic_test"
    assert baseline["model"]["validation"]["training_count"] == 24
    assert baseline["model"]["validation"]["validation_count"] == 6

    def shifted_signal(body):
        time = np.arange(N) / FS
        for index, channel in enumerate(body["channels"]):
            channel["samples"] = (np.sin(2 * np.pi * 0.45 * time) * (1.0 + index / 2)).tolist()

    original, _, _ = await acquisition(
        app,
        client,
        sensors,
        transform=shifted_signal,
        started_at=now - timedelta(days=1),
        environment={"operating_state": "stopped", "rotor_speed_rpm": 0, "temperature_c": 5},
    )
    original_run, _ = await run_analysis(app, client, original)
    assert original_run["status"] == "succeeded", original_run
    async with app.state.session_factory() as session, session.begin():
        session.add(
            Resource(
                id="SYNTHETIC-MODAL-KIT",
                resource_type="measurement_equipment",
                name="Synthetic modal measurement kit",
                quantity=1,
                status="available",
            )
        )
        turbine = await session.get(Turbine, "WT-023")
        original_asset_state = (turbine.health_score, turbine.status)
    created = await post(
        client,
        "structural-missions",
        {
            "turbine_id": "WT-023",
            "component_id": component["id"],
            "title": "Synthetic modal anomaly and calibrated post-work retest",
            "scenario": "modal_frequency_review",
            "source_id": original_run["modal_observations"][0]["id"],
            "baseline_id": baseline["id"],
            "planning_duration_hours": 1,
        },
    )
    assert created.status_code == 202, created.text
    context = created.json()
    assert context["missing_evidence"] == []
    assert context["comparison"]["status"] == "requires_review"
    assert context["comparison"]["damage_probability"] is None
    mission = (await client.get(f"/api/v1/missions/{context['mission_id']}")).json()
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
            "reason": "Approve synthetic modal retest only; no operating or field authority.",
        },
    )
    assert approved.status_code == 200, approved.text
    order = (
        await client.get(f"/api/v1/structural-work-orders/{approved.json()['work_order_id']}")
    ).json()
    work_order_created = aware(datetime.fromisoformat(order["work_order"]["created_at"]))
    start = work_order_created + timedelta(seconds=1)
    end = start + timedelta(seconds=N / FS)
    retest, _, _ = await acquisition(
        app,
        client,
        sensors,
        started_at=start,
        environment={"operating_state": "stopped", "rotor_speed_rpm": 0, "temperature_c": 5},
    )
    retest_run, _ = await run_analysis(app, client, retest)
    assert retest_run["status"] == "succeeded", retest_run
    retest_mode = retest_run["modal_observations"][0]["id"]
    assert retest_mode not in {*modal_ids, original_run["modal_observations"][0]["id"]}

    class AcquisitionClock(datetime):
        current = start

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)

    with monkeypatch.context() as patch:
        patch.setattr(structural_closure, "datetime", AcquisitionClock)
        patch.setattr(workorders, "datetime", AcquisitionClock)
        patch.setattr(model_base, "datetime", AcquisitionClock)
        prerequisite = await finish_field_task(
            app,
            client,
            order,
            1,
            {
                "permit_reference": "synthetic-modal-permit",
                "isolation_reference": "synthetic-modal-isolation",
                "calibration_reference": "synthetic-calibration-v1",
            },
        )
        assert prerequisite.status_code == 200, prerequisite.text
        measurement = {
            "retest_source_id": retest_mode,
            "measurement_reference": "Actual FDD result of synthetic complete post-work window",
        }
        premature = await finish_field_task(app, client, order, 2, measurement)
        assert premature.status_code == 422, premature.text
        assert "future dated" in premature.text
        # The gate remains unchanged; only the simulated acquisition clock advances.
        AcquisitionClock.current = end + timedelta(seconds=1)
        handed = await finish_field_task(app, client, order, 2, measurement)
        assert handed.status_code == 200, handed.text
        assert handed.json()["workflow_finalized"] is False
        assert handed.json()["work_order_status"] == "awaiting_health_review"
        reviewed = await post(
            client,
            f"structural-work-orders/{order['work_order']['id']}/health-review",
            {
                "expected_mission_revision": order["context"]["revision"],
                "action": "resolve_review",
                "reason": (
                    "Independent synthetic modal retest is within the confirmed screening range."
                ),
                "hypothesis_outcome": "not_supported",
            },
            headers=HEALTH,
        )
        assert reviewed.status_code == 200, reviewed.text
        result = reviewed.json()
        assessment = result["review"]["assessment"]
        assert assessment["eligible_to_resolve_review"] is True
        assert assessment["exclusions"] == []
        assert assessment["comparison"]["status"] == "within_screening_range"
        assert assessment["comparison"]["mode_mac"] >= 0.9
        assert assessment["comparison"]["damage_probability"] is None
        assert assessment["evidence_card"]["source"]["sha256"] == retest["artifact_sha256"]
        assert assessment["evidence_card"]["method"] == context["evidence_cards"][0]["method"]
        assert assessment["field_qualification"] == "unverified"
        assert assessment["authorizes_operation"] is False
        assert result["work_order_status"] == "completed"
        assert result["case_review_status"] == "pending"
        case_id = result["knowledge_case_id"]
        case_review = await post(
            client,
            f"structural-cases/{case_id}/review",
            {
                "expected_revision": 1,
                "action": "approve",
                "reason": "Independent synthetic modal case source review; no field qualification.",
            },
            headers=CASE,
        )
        assert case_review.status_code == 200, case_review.text
    assert (await client.get(f"/api/v1/health-baselines/{baseline['id']}")).json() == baseline
    completed = (await client.get(f"/api/v1/missions/{context['mission_id']}")).json()
    assert [execution["node"] for execution in completed["executions"]] == [
        "scada",
        "vibration",
        "knowledge",
        "diagnosis",
        "alternatives",
        "reviews",
        "hitl",
        "workorder",
    ]
    assert completed["status"] == "completed"
    async with app.state.session_factory() as session:
        current = await session.get(Mission, context["mission_id"])
        assert (await session.get(Alarm, current.alarm_id)).status == "resolved"
        turbine = await session.get(Turbine, "WT-023")
        assert (turbine.health_score, turbine.status) == original_asset_state
        assert await session.scalar(select(func.count()).select_from(ModalObservation)) == 32
        assert await session.scalar(select(func.count()).select_from(WaveformRecord)) == 32
        snapshot = await build_knowledge_graph_snapshot(session)
        nodes = {node.uid: node for node in snapshot.nodes}
        projected_baseline = nodes[graph_uid(NodeType.HEALTH_BASELINE, baseline["id"])]
        assert projected_baseline.properties["trainingWindowCount"] == 30
        import json

        assert (
            json.loads(projected_baseline.properties["domainJson"]) == baseline["model"]["domain"]
        )
        assert (
            json.loads(projected_baseline.properties["validationJson"])
            == baseline["model"]["validation"]
        )
        assert projected_baseline.properties["qualification"] == "requires_field_validation"
        assert projected_baseline.properties["authorizesWork"] is False
        assert any(
            edge.source_uid == projected_baseline.uid
            and edge.target_uid == graph_uid(NodeType.MODAL_OBSERVATION, modal_ids[0])
            and edge.relationship_type.value == "DERIVED_FROM"
            for edge in snapshot.relationships
        )
        assert (
            sum(node.node_type is NodeType.STRUCTURAL_ANALYSIS_RUN for node in snapshot.nodes) == 32
        )
        assert sum(node.node_type is NodeType.FIELD_MEASUREMENT for node in snapshot.nodes) == 1
        assert sum(node.node_type is NodeType.CLOSURE_ASSESSMENT for node in snapshot.nodes) == 1
