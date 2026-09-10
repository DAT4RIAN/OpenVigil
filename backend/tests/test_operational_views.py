from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import delete, event, update

from windops_backend.models import (
    AgentExecution,
    Alarm,
    Approval,
    Decision,
    Evidence,
    IngestReceipt,
    IngestSource,
    KnowledgeDocument,
    Mission,
    Resource,
    ResourceReservation,
    ScadaSample,
    Turbine,
    WeatherWindow,
    WindFarm,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.services import operational_views
from windops_backend.services.operational_views import (
    DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT,
    DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT,
    MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT,
    MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT,
    build_diagnosis_query,
    build_maintenance_query,
)


async def _seed_operational_view_records(app: FastAPI) -> None:
    now = datetime.now(UTC)
    async with app.state.session_factory() as session, session.begin():
        session.add(
            IngestSource(
                id="view-source",
                display_name="Operational view source",
                source_kind="rest",
                policy={"retention": "365 days"},
                status="healthy",
                last_seen_at=now,
            )
        )

        session.add(
            IngestReceipt(
                source_event_id="view-event-1",
                source_id="view-source",
                payload_hash="a" * 64,
            )
        )
        session.add(
            ScadaSample(
                id="view-sample-1",
                source_event_id="view-event-1",
                source_id="view-source",
                source_sequence=1,
                turbine_id="WT-023",
                variable="active_power",
                observed_at=now,
                received_at=now,
                value=5.2,
                unit="MW",
                quality="good",
                attributes={"is_anomaly": False},
            )
        )
        session.add(
            Alarm(
                id="ALARM-VIEW-001",
                turbine_id="WT-023",
                source_event_id="view-event-1",
                code="VIEW-ANOMALY",
                subsystem="main_bearing",
                title="Governed main-bearing condition",
                severity="major",
                triggered_at=now,
                evidence={
                    "variable": "active_power",
                    "value": 5.2,
                    "unit": "MW",
                    "attributes": {"anomaly_score": 0.82},
                },
            )
        )
        session.add(
            Mission(
                id="MISSION-VIEW-001",
                alarm_id="ALARM-VIEW-001",
                turbine_id="WT-023",
                title="Operational view mission",
                status="under_review",
                public_state={
                    "diagnosis": {
                        "failure_mode": "main_bearing_degradation",
                        "component": "main_bearing",
                        "confidence": 0.86,
                        "conclusion": "Governed evidence supports controlled inspection.",
                    }
                },
            )
        )
        session.add(
            Evidence(
                id="EVIDENCE-VIEW-001",
                mission_id="MISSION-VIEW-001",
                source_key="active-power-window",
                evidence_type="scada_window",
                summary="The quality-aware source window was retained.",
                source_refs=["view-event-1"],
            )
        )
        session.add(
            Approval(
                id="APPROVAL-VIEW-001",
                mission_id="MISSION-VIEW-001",
                mission_revision=1,
                action="approve",
                approver="integration-test-system",
                reason="approved for operational view test",
                selected_alternative_id="ALT-VIEW",
            )
        )
        session.add(
            Decision(
                id="DECISION-VIEW-001",
                mission_id="MISSION-VIEW-001",
                status="approved",
                alternatives=[
                    {
                        "alternative_id": "ALT-VIEW",
                        "action": "Inspect the main bearing in the governed window.",
                    }
                ],
                recommended_alternative_id="ALT-VIEW",
                selected_alternative_id="ALT-VIEW",
                recommendation_reason="governed evidence",
                approval_id="APPROVAL-VIEW-001",
            )
        )
        session.add(
            WorkOrder(
                id="WO-VIEW-001",
                mission_id="MISSION-VIEW-001",
                approval_id="APPROVAL-VIEW-001",
                turbine_id="WT-023",
                title="Inspect governed condition",
                selected_alternative_id="ALT-VIEW",
                selected_action="Inspect the main bearing in the governed window.",
                assigned_team="Mechanical Maintenance Team A",
                planned_start=now + timedelta(hours=24),
                deadline=now + timedelta(hours=30),
                estimated_duration_hours=4,
            )
        )
        session.add(
            WorkOrderTask(
                id="TASK-VIEW-001",
                work_order_id="WO-VIEW-001",
                sequence=1,
                title="Inspect condition",
                schema_version="inspection-v1",
                measurement_schema={"type": "object", "additionalProperties": False},
            )
        )
        session.add(
            KnowledgeDocument(
                id="KB-VIEW-INDEXED",
                title="Governed main-bearing manual excerpt",
                document_type="manufacturer_manual",
                body="Indexed retrieval excerpt for the governed main-bearing condition.",
                citation_uri="windops://knowledge/documents/KB-VIEW-INDEXED",
                ingestion_status="indexed",
                metadata_={"turbine_id": "WT-023"},
            )
        )
        session.add(
            KnowledgeDocument(
                id="KB-VIEW-PENDING",
                title="Pending manual still being ingested",
                document_type="manufacturer_manual",
                body="Ingestion has not completed; the document is not retrievable yet.",
                citation_uri="windops://knowledge/documents/KB-VIEW-PENDING",
                ingestion_status="pending",
                metadata_={"turbine_id": "WT-023"},
            )
        )
        session.add(
            KnowledgeDocument(
                id="KB-VIEW-FAILED",
                title="Failed ingestion manual",
                document_type="manufacturer_manual",
                body="Ingestion failed; the document must not surface on asset views.",
                citation_uri="windops://knowledge/documents/KB-VIEW-FAILED",
                ingestion_status="failed",
                metadata_={"related_turbine_ids": ["WT-023"]},
            )
        )


def test_operational_performance_builders_cover_default_filters_and_scope() -> None:
    diagnosis_plans = [
        build_diagnosis_query(sort_mode="priority-desc", limit=64),
        build_diagnosis_query(
            query="bearing",
            tenant_id="tenant-east-china",
            wind_farm_id="WF-001",
            turbine_id="WT-023",
            status_filter="awaiting-review",
            risk="high",
            sort_mode="confidence-desc",
            offset=128,
            limit=32,
        ),
        build_diagnosis_query(sort_mode="updated-desc"),
        build_diagnosis_query(sort_mode="turbine-asc"),
    ]
    maintenance_plans = [
        build_maintenance_query(sort_mode="start-asc"),
        build_maintenance_query(
            dialect_name="sqlite",
            query="inspection",
            tenant_id="tenant-east-china",
            wind_farm_id="WF-001",
            turbine_id="WT-023",
            status_filter="at-risk",
            risk="high",
            team="Mechanical Maintenance Team A",
            window="suitable",
            sort_mode="readiness-desc",
            offset=100,
            limit=25,
        ),
        build_maintenance_query(sort_mode="risk-desc"),
        build_maintenance_query(sort_mode="deadline-asc"),
    ]
    diagnosis_sql = " ".join(str(plan.page) for plan in diagnosis_plans)
    maintenance_sql = " ".join(str(plan.page) for plan in maintenance_plans)
    assert "alarms" in diagnosis_sql and "work_orders" in diagnosis_sql
    assert "wind_farms" in diagnosis_sql and "LIMIT" in diagnosis_sql
    assert "weather_windows" in maintenance_sql and "resource_reservations" in maintenance_sql
    assert "LIMIT" in maintenance_sql and "OFFSET" in maintenance_sql


@pytest.mark.asyncio
async def test_production_operational_views_are_backed_by_governed_ledgers(
    app: FastAPI,
    client: Any,
) -> None:
    await _seed_operational_view_records(app)
    diagnoses = await client.get("/api/v1/diagnoses")
    assert diagnoses.status_code == 200, diagnoses.text
    diagnosis_body = diagnoses.json()
    assert diagnosis_body["meta"]["source"] == "postgresql-governed-missions"
    assert diagnosis_body["data"]
    diagnosis = diagnosis_body["data"][0]
    assert diagnosis["missionId"]
    assert diagnosis["candidates"]
    assert diagnosis["gate"]["state"] == "authorized"
    assert diagnosis["gate"]["humanReviewRequired"] is False

    dashboard = await client.get("/api/v1/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    dashboard_body = dashboard.json()["data"]
    assert dashboard_body["source"] == "postgresql-timescaledb-domain-events"
    assert dashboard_body["fleet"]["asset_count"] >= 1
    assert dashboard_body["fleet"]["current_power_mw"] == 5.2
    assert dashboard_body["fleet"]["telemetry_asset_count"] == 1
    assert dashboard_body["alarms"][0]["id"] == "ALARM-VIEW-001"
    assert dashboard_body["missions"][0]["id"] == "MISSION-VIEW-001"

    asset_detail = await client.get("/api/v1/turbines/WT-023")
    assert asset_detail.status_code == 200, asset_detail.text
    asset_body = asset_detail.json()["data"]
    assert asset_body["asset"]["id"] == "WT-023"
    assert asset_body["telemetry"][0]["sourceId"] == "view-source"
    assert asset_body["alarms"][0]["id"] == "ALARM-VIEW-001"
    assert asset_body["missions"][0]["id"] == "MISSION-VIEW-001"
    assert asset_body["workOrders"][0]["id"] == "WO-VIEW-001"
    document_ids = {document["id"] for document in asset_body["documents"]}
    assert document_ids == {"KB-VIEW-INDEXED"}

    plans = await client.get("/api/v1/maintenance-plans")
    assert plans.status_code == 200, plans.text
    plan_body = plans.json()
    assert plan_body["meta"]["source"] == "postgresql-work-orders-resources-weather"
    assert plan_body["data"]
    plan = plan_body["data"][0]
    assert plan["source"] == "postgresql-governed-schedule"
    assert plan["readOnly"] is False
    assert plan["relatedMissionId"]

    twin = await client.get("/api/v1/digital-twin", params={"turbineId": "WT-023"})
    assert twin.status_code == 200, twin.text
    twin_body = twin.json()
    assert twin_body["data"]["model"]["source"] == "postgresql-timescaledb"
    assert twin_body["data"]["signals"]
    assert all(item["sourceId"] for item in twin_body["data"]["signals"])

    empty_reports = await client.get("/api/v1/reports")
    assert empty_reports.status_code == 200, empty_reports.text
    assert empty_reports.json()["data"] == []
    report_request = {
        "report_type": "daily-operations",
        "period": "daily",
        "reason": "Create an immutable operations handover snapshot",
    }
    generated = await client.post(
        "/api/v1/reports",
        json=report_request,
        headers={"Idempotency-Key": "report-view-test-001"},
    )
    assert generated.status_code == 201, generated.text
    generated_body = generated.json()
    assert generated_body["meta"]["persisted"] is True
    assert generated_body["meta"]["replayed"] is False
    assert len(generated_body["data"]["contentDigest"]) == 64

    replay = await client.post(
        "/api/v1/reports",
        json=report_request,
        headers={"Idempotency-Key": "report-view-test-001"},
    )
    assert replay.status_code == 201, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == generated_body

    reports = await client.get("/api/v1/reports")
    assert reports.status_code == 200, reports.text
    report_body = reports.json()
    assert len(report_body["data"]) == 1
    assert report_body["meta"]["persisted"] is True
    assert all("production" in report["tags"] for report in report_body["data"])

    report_id = generated_body["data"]["id"]
    detail = await client.get(f"/api/v1/reports/{report_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"] == generated_body["data"]
    assert detail.json()["meta"]["persisted"] is True

    missing_detail = await client.get("/api/v1/reports/RPT-MISSING")
    assert missing_detail.status_code == 404
    assert missing_detail.json()["error"]["code"] == "NOT_FOUND"

    catalog = await client.get("/api/v1/data-catalog")
    assert catalog.status_code == 200, catalog.text
    catalog_body = catalog.json()
    assert catalog_body["meta"]["fixture_fallback"] is False
    assert catalog_body["meta"]["scada_archive_count"] > 0
    assert catalog_body["data"]


@pytest.mark.asyncio
async def test_maintenance_weather_selection_is_bounded_deterministic_and_scoped(
    app: FastAPI,
    client: Any,
) -> None:
    await _seed_operational_view_records(app)
    async with app.state.session_factory() as session, session.begin():
        work_order = await session.get(WorkOrder, "WO-VIEW-001")
        assert work_order is not None and work_order.planned_start is not None
        turbine = await session.get(Turbine, work_order.turbine_id)
        assert turbine is not None
        wind_farm_id = turbine.wind_farm_id
        planned_start = work_order.planned_start
        await session.execute(delete(WeatherWindow))
        session.add(
            WindFarm(
                id="WF-WEATHER-OTHER",
                tenant_id="tenant-other",
                name="Other tenant weather farm",
                capacity_mw=1,
            )
        )
        session.add_all(
            [
                WeatherWindow(
                    id="WEATHER-UNSAFE-EARLY",
                    wind_farm_id=wind_farm_id,
                    starts_at=planned_start - timedelta(hours=2),
                    ends_at=planned_start + timedelta(hours=5),
                    wind_speed_ms=30,
                    wave_height_m=5,
                    suitable=False,
                ),
                WeatherWindow(
                    id="WEATHER-SUITABLE-Z",
                    wind_farm_id=wind_farm_id,
                    starts_at=planned_start - timedelta(hours=1),
                    ends_at=planned_start + timedelta(hours=3),
                    wind_speed_ms=8,
                    wave_height_m=1,
                    suitable=True,
                ),
                WeatherWindow(
                    id="WEATHER-SUITABLE-B",
                    wind_farm_id=wind_farm_id,
                    starts_at=planned_start - timedelta(hours=1),
                    ends_at=planned_start + timedelta(hours=2),
                    wind_speed_ms=7,
                    wave_height_m=1,
                    suitable=True,
                ),
                WeatherWindow(
                    id="WEATHER-SUITABLE-A",
                    wind_farm_id=wind_farm_id,
                    starts_at=planned_start - timedelta(hours=1),
                    ends_at=planned_start + timedelta(hours=2),
                    wind_speed_ms=6,
                    wave_height_m=1,
                    suitable=True,
                ),
                WeatherWindow(
                    id="WEATHER-CROSS-FARM",
                    wind_farm_id="WF-WEATHER-OTHER",
                    starts_at=planned_start - timedelta(hours=3),
                    ends_at=planned_start + timedelta(hours=6),
                    wind_speed_ms=5,
                    wave_height_m=0.5,
                    suitable=True,
                ),
            ]
        )

    scoped_headers = {
        "X-WindOps-Test-Principal": "weather-contract",
        "X-WindOps-Test-Role": "test_system",
        "X-WindOps-Test-Tenant-Ids": "tenant-east-china",
    }
    response = await client.get(
        "/api/v1/maintenance-plans",
        params={"q": "WO-VIEW-001", "limit": 1},
        headers=scoped_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"][0]["weather"]["id"] == "WEATHER-SUITABLE-A"
    assert body["data"][0]["weather"]["state"] == "suitable"
    assert body["meta"]["related_data_boundaries"]["weather_windows"] == {
        "strategy": "suitable_first_then_earliest_overlap",
        "per_work_order_limit": MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT,
        "deterministic_order": ["starts_at_asc", "ends_at_asc", "id_asc"],
        "truncated_work_order_count": 1,
    }

    wrong_tenant = await client.get(
        "/api/v1/maintenance-plans",
        params={"q": "WO-VIEW-001", "limit": 1},
        headers={**scoped_headers, "X-WindOps-Test-Tenant-Ids": "tenant-other"},
    )
    assert wrong_tenant.status_code == 200, wrong_tenant.text
    assert wrong_tenant.json()["data"] == []

    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            update(WeatherWindow)
            .where(WeatherWindow.wind_farm_id == wind_farm_id)
            .values(suitable=False)
        )
    fallback = await client.get(
        "/api/v1/maintenance-plans",
        params={"q": "WO-VIEW-001", "limit": 1},
        headers=scoped_headers,
    )
    assert fallback.status_code == 200, fallback.text
    assert fallback.json()["data"][0]["weather"]["id"] == "WEATHER-UNSAFE-EARLY"
    assert fallback.json()["data"][0]["weather"]["state"] == "unsafe"

    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            delete(WeatherWindow).where(WeatherWindow.wind_farm_id == wind_farm_id)
        )
    unmatched = await client.get(
        "/api/v1/maintenance-plans",
        params={"q": "WO-VIEW-001", "limit": 1},
        headers=scoped_headers,
    )
    assert unmatched.status_code == 200, unmatched.text
    unmatched_body = unmatched.json()
    assert unmatched_body["data"][0]["weather"]["id"] is None
    assert unmatched_body["data"][0]["weather"]["state"] == "unmatched"
    assert (
        unmatched_body["meta"]["related_data_boundaries"]["weather_windows"][
            "truncated_work_order_count"
        ]
        == 0
    )


@pytest.mark.asyncio
async def test_operational_view_fanout_is_bounded_and_query_count_is_constant(
    app: FastAPI,
    client: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_operational_view_records(app)
    now = datetime.now(UTC) + timedelta(hours=1)
    async with app.state.session_factory() as session, session.begin():
        for index in range(8):
            session.add(
                Evidence(
                    id=f"EVIDENCE-HIGH-FANOUT-{index:02d}",
                    mission_id="MISSION-VIEW-001",
                    source_key=f"high-fanout-{index:02d}",
                    evidence_type="performance_contract",
                    summary=f"Bounded evidence row {index}",
                    source_refs=[f"source-{index}"],
                    created_at=now + timedelta(seconds=index),
                )
            )
            session.add(
                AgentExecution(
                    id=f"EXEC-HIGH-FANOUT-{index:02d}",
                    mission_id="MISSION-VIEW-001",
                    node="performance_contract",
                    agent_role="diagnosis_agent",
                    status="succeeded",
                    public_output={"summary": f"Bounded execution row {index}"},
                    started_at=now + timedelta(seconds=index),
                    completed_at=now + timedelta(seconds=index, milliseconds=1),
                )
            )
        for sequence in range(2, 22):
            session.add(
                WorkOrderTask(
                    id=f"TASK-HIGH-FANOUT-{sequence:02d}",
                    work_order_id="WO-VIEW-001",
                    sequence=sequence,
                    title=f"High fanout task {sequence}",
                    schema_version="inspection-v1",
                    measurement_schema={"type": "object", "additionalProperties": False},
                    status="completed" if sequence % 2 == 0 else "pending",
                )
            )
        for resource_type in ("crew", "vessel", "spare_part", "tool"):
            for index in range(4):
                resource_id = f"RESOURCE-HIGH-FANOUT-{resource_type}-{index}"
                session.add(
                    Resource(
                        id=resource_id,
                        resource_type=resource_type,
                        name=f"Bounded {resource_type} {index}",
                        quantity=1,
                        status="reserved",
                        updated_at=now + timedelta(seconds=index),
                    )
                )
                session.add(
                    ResourceReservation(
                        id=f"RSV-HF-{resource_type[:3]}-{index}",
                        mission_id="MISSION-VIEW-001",
                        resource_id=resource_id,
                        created_at=now + timedelta(seconds=index),
                    )
                )

    builder_calls = {"diagnosis": 0, "maintenance": 0}
    original_diagnosis_builder = operational_views.build_diagnosis_query
    original_maintenance_builder = operational_views.build_maintenance_query

    def tracked_diagnosis_builder(**kwargs: Any) -> Any:
        builder_calls["diagnosis"] += 1
        return original_diagnosis_builder(**kwargs)

    def tracked_maintenance_builder(**kwargs: Any) -> Any:
        builder_calls["maintenance"] += 1
        return original_maintenance_builder(**kwargs)

    monkeypatch.setattr(
        operational_views,
        "build_diagnosis_query",
        tracked_diagnosis_builder,
    )
    monkeypatch.setattr(
        operational_views,
        "build_maintenance_query",
        tracked_maintenance_builder,
    )

    statements: list[str] = []

    def capture_statement(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    sync_engine = app.state.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", capture_statement)
    try:
        diagnosis_response = await client.get(
            "/api/v1/diagnoses",
            params={"q": "MISSION-VIEW-001", "limit": 1},
        )
        diagnosis_query_count = len(statements)
        statements.clear()
        maintenance_response = await client.get(
            "/api/v1/maintenance-plans",
            params={"q": "WO-VIEW-001", "limit": 1},
        )
        maintenance_query_count = len(statements)
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture_statement)

    assert diagnosis_response.status_code == 200, diagnosis_response.text
    diagnosis_body = diagnosis_response.json()
    diagnosis = diagnosis_body["data"][0]
    assert len(diagnosis["citations"]) == DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT
    assert len(diagnosis["collaboration"]) == DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT
    assert diagnosis_body["meta"]["related_data_boundaries"] == {
        "evidence": {
            "strategy": "latest_per_mission",
            "per_mission_limit": DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT,
            "truncated_mission_count": 1,
        },
        "agent_executions": {
            "strategy": "latest_per_mission",
            "per_mission_limit": DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT,
            "truncated_mission_count": 1,
        },
    }
    assert builder_calls["diagnosis"] == 1
    assert diagnosis_query_count <= 15
    assert len(diagnosis_response.content) < 512 * 1024

    assert maintenance_response.status_code == 200, maintenance_response.text
    maintenance_body = maintenance_response.json()
    maintenance = maintenance_body["data"][0]
    assert maintenance["taskProgressPercent"] == 48
    assert len(maintenance["vessels"]) == MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT
    assert len(maintenance["spareParts"]) == MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT
    assert len(maintenance["tools"]) == MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT
    assert maintenance_body["meta"]["related_data_boundaries"]["tasks"]["strategy"] == (
        "aggregate_only"
    )
    assert maintenance_body["meta"]["related_data_boundaries"]["reservations"] == {
        "strategy": "latest_per_mission_and_resource_type",
        "per_mission_type_limit": MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT,
        "truncated_group_count": 4,
    }
    assert builder_calls["maintenance"] == 1
    assert maintenance_query_count <= 9
    assert len(maintenance_response.content) < 512 * 1024


@pytest.mark.asyncio
async def test_priority_desc_pagination_preserves_risk_buckets_and_bucket_order(
    app: FastAPI,
    client: Any,
) -> None:
    await _seed_operational_view_records(app)
    now = datetime.now(UTC) + timedelta(hours=2)
    records = (
        ("CRITICAL", "critical", now - timedelta(minutes=20)),
        ("HIGH-NEW", "major", now),
        ("HIGH-OLD", "major", now - timedelta(minutes=1)),
        ("MEDIUM", "minor", now + timedelta(minutes=10)),
        ("LOW", "info", now + timedelta(minutes=20)),
    )
    async with app.state.session_factory() as session, session.begin():
        for suffix, severity, updated_at in records:
            source_event_id = f"PRIORITY-EVENT-{suffix}"
            alarm_id = f"PRIORITY-ALARM-{suffix}"
            mission_id = f"PRIORITY-MISSION-{suffix}"
            session.add(
                IngestReceipt(
                    source_event_id=source_event_id,
                    source_id="view-source",
                    payload_hash=suffix.lower().ljust(64, "a")[:64],
                )
            )
            session.add(
                Alarm(
                    id=alarm_id,
                    turbine_id="WT-023",
                    source_event_id=source_event_id,
                    code="PRIORITY-CONTRACT",
                    subsystem="bearing",
                    title="priority-contract alarm",
                    severity=severity,
                    triggered_at=updated_at,
                )
            )
            session.add(
                Mission(
                    id=mission_id,
                    alarm_id=alarm_id,
                    turbine_id="WT-023",
                    title="priority-contract mission",
                    status="diagnosed",
                    public_state={"diagnosis": {"confidence": 0.8}},
                    created_at=updated_at,
                    updated_at=updated_at,
                )
            )

    response = await client.get(
        "/api/v1/diagnoses",
        params={
            "q": "priority-contract",
            "sort": "priority-desc",
            "offset": 1,
            "limit": 3,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["filtered_total"] == 5
    assert [row["id"] for row in body["data"]] == [
        "DX-PRIORITY-MISSION-HIGH-NEW",
        "DX-PRIORITY-MISSION-HIGH-OLD",
        "DX-PRIORITY-MISSION-MEDIUM",
    ]
    assert [row["risk"] for row in body["data"]] == ["high", "high", "medium"]
