from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import event, select

from windops_backend.models import AssetHealthEvent, WeatherWindow, WindFarm


@pytest.mark.asyncio
async def test_operational_pages_bound_primary_and_relation_queries(
    app: FastAPI,
    client: Any,
) -> None:
    ingested = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": "H004-BOUNDED-DIAGNOSIS",
                    "turbine_id": "WT-023",
                    "observed_at": datetime.now(UTC).isoformat(),
                    "variable": "main_bearing_vibration_rms",
                    "value": 5.1,
                    "unit": "mm/s",
                    "quality": "good",
                    "attributes": {"anomaly_score": 0.91},
                }
            ]
        },
    )
    assert ingested.status_code == 202, ingested.text
    statements: list[str] = []

    def capture_statement(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(" ".join(statement.split()))

    sync_engine = app.state.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", capture_statement)
    try:
        diagnoses = await client.get(
            "/api/v1/diagnoses",
            params={"limit": 1, "sort": "updated-desc"},
        )
        assert diagnoses.status_code == 200, diagnoses.text
        diagnosis_body = diagnoses.json()
        assert diagnosis_body["meta"]["count"] <= 1
        assert diagnosis_body["meta"]["filtered_total"] <= diagnosis_body["meta"]["total"]
        assert diagnosis_body["meta"]["has_more"] is (diagnosis_body["meta"]["filtered_total"] > 1)
        assert len(diagnoses.content) < 512 * 1024
        if diagnosis_body["data"]:
            diagnosis = diagnosis_body["data"][0]
            filtered_diagnosis = await client.get(
                "/api/v1/diagnoses",
                params={
                    "q": diagnosis["missionId"],
                    "status": diagnosis["status"],
                    "risk": diagnosis["risk"],
                    "sort": "confidence-desc",
                    "limit": 1,
                },
            )
            assert filtered_diagnosis.status_code == 200, filtered_diagnosis.text
            assert filtered_diagnosis.json()["data"][0]["id"] == diagnosis["id"]

        plans = await client.get(
            "/api/v1/maintenance-plans",
            params={"limit": 1, "sort": "start-asc"},
        )
        assert plans.status_code == 200, plans.text
        plan_body = plans.json()
        assert plan_body["meta"]["count"] <= 1
        assert plan_body["meta"]["filtered_total"] <= plan_body["meta"]["total"]
        assert len(plans.content) < 512 * 1024
        if plan_body["data"]:
            plan = plan_body["data"][0]
            filtered_plan = await client.get(
                "/api/v1/maintenance-plans",
                params={
                    "q": plan["workOrderId"],
                    "status": plan["status"],
                    "risk": plan["risk"],
                    "team": plan["teamKey"],
                    "window": plan["weather"]["state"],
                    "sort": "readiness-desc",
                    "limit": 1,
                },
            )
            assert filtered_plan.status_code == 200, filtered_plan.text
            assert filtered_plan.json()["data"][0]["id"] == plan["id"]
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture_statement)

    mission_page_queries = [
        statement
        for statement in statements
        if "FROM missions JOIN alarms" in statement and "COUNT" not in statement.upper()
    ]
    assert mission_page_queries
    assert all(" LIMIT " in statement for statement in mission_page_queries)
    assert any("missions.id IN" in statement for statement in statements)
    work_order_pages = [
        statement
        for statement in statements
        if "FROM work_orders JOIN turbines" in statement and "COUNT" not in statement.upper()
    ]
    assert work_order_pages
    assert all(" LIMIT " in statement for statement in work_order_pages)
    assert len(statements) <= 48


@pytest.mark.asyncio
async def test_resources_and_health_have_stable_bounded_cursors(
    app: FastAPI,
    client: Any,
) -> None:
    now = datetime.now(UTC)
    async with app.state.session_factory() as session, session.begin():
        farm_id = await session.scalar(select(WindFarm.id).order_by(WindFarm.id).limit(1))
        assert farm_id is not None
        session.add(
            WeatherWindow(
                id="WEATHER-BOUND-EXTRA",
                wind_farm_id=farm_id,
                starts_at=now + timedelta(days=10),
                ends_at=now + timedelta(days=10, hours=6),
                wind_speed_ms=6.0,
                wave_height_m=0.8,
                suitable=True,
            )
        )

    first_resources = await client.get(
        "/api/v1/resources",
        params={"limit": 1, "weather_limit": 1},
    )
    assert first_resources.status_code == 200, first_resources.text
    first_body = first_resources.json()
    assert first_body["count"] == 1
    assert first_body["total"] >= 3
    assert first_body["next_cursor"]
    assert len(first_body["weather_windows"]) == 1
    assert first_body["weather_next_cursor"]

    second_resources = await client.get(
        "/api/v1/resources",
        params={
            "limit": 1,
            "cursor": first_body["next_cursor"],
            "weather_limit": 1,
            "weather_cursor": first_body["weather_next_cursor"],
        },
    )
    assert second_resources.status_code == 200, second_resources.text
    second_body = second_resources.json()
    assert second_body["resources"][0]["resource_id"] != first_body["resources"][0]["resource_id"]
    assert (
        second_body["weather_windows"][0]["window_id"]
        != first_body["weather_windows"][0]["window_id"]
    )

    async with app.state.session_factory() as session, session.begin():
        for index in range(5):
            session.add(
                AssetHealthEvent(
                    id=f"HEALTH-BOUND-{index}",
                    turbine_id="WT-023",
                    score=80 - index,
                    status="watch",
                    reason=f"bounded health sample {index}",
                    recorded_at=now - timedelta(minutes=index),
                )
            )

    first_health = await client.get(
        "/api/v1/turbines/WT-023/health",
        params={"limit": 2},
    )
    assert first_health.status_code == 200, first_health.text
    health_body = first_health.json()
    assert health_body["count"] == 2
    assert len(health_body["history"]) == 2
    assert health_body["next_cursor"]

    next_health = await client.get(
        "/api/v1/turbines/WT-023/health",
        params={"limit": 2, "cursor": health_body["next_cursor"]},
    )
    assert next_health.status_code == 200, next_health.text
    assert (
        next_health.json()["history"][0]["health_event_id"]
        != health_body["history"][0]["health_event_id"]
    )

    assessments = await client.get(
        "/api/v1/health/assessments",
        params={"limit": 1},
    )
    assert assessments.status_code == 200, assessments.text
    assessment_body = assessments.json()
    assert assessment_body["meta"]["count"] <= 1
    assert len(assessment_body["assessments"]) <= 1
    if assessment_body["assessments"]:
        assessment = assessment_body["assessments"][0]
        filtered_assessment = await client.get(
            "/api/v1/health/assessments",
            params={
                "state": assessment["state"],
                "risk": assessment["risk_level"],
                "limit": 1,
            },
        )
        assert filtered_assessment.status_code == 200, filtered_assessment.text
        assert (
            filtered_assessment.json()["assessments"][0]["assessment_id"]
            == assessment["assessment_id"]
        )
