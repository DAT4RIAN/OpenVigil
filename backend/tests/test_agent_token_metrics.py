from datetime import UTC, datetime, timedelta

import pytest

from windops_backend.api.deps import _token_total
from windops_backend.models import AgentExecution


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        ({"total_tokens": 49}, 49),
        ({"total": 11}, 11),
        ({"total_tokens": 49, "total": 999}, 49),
        ({"total_tokens": 0, "total": 999}, 0),
        ({"total_tokens": None, "total": 999}, 0),
        ({"total_tokens": None, "known_total_tokens": 7}, 7),
        ({"total_tokens": None}, 0),
        ({}, 0),
        ({"total_tokens": True}, 0),
        ({"total_tokens": -5}, 0),
        ({"total_tokens": float("inf")}, 0),
        ({"total": "not-a-count"}, 0),
        ({"total": "18"}, 18),
    ],
)
def test_token_count_compatibility(usage, expected):
    assert _token_total(AgentExecution(token_usage=usage)) == expected


@pytest.mark.asyncio
async def test_agent_and_observation_totals_include_known_usage_within_window(app, client):
    response = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": "TOKEN-METRICS-MISSION",
                    "turbine_id": "WT-023",
                    "observed_at": "2026-09-27T00:00:00Z",
                    "variable": "main_bearing_vibration_rms",
                    "value": 4.81,
                    "unit": "mm/s",
                    "attributes": {"baseline": 3.79, "anomaly_score": 0.86},
                }
            ]
        },
    )
    assert response.status_code == 202
    mission = response.json()["results"][0]["mission_id"]
    assert mission
    before = await client.get("/api/v1/agents")
    assert before.status_code == 200
    original = next(r for r in before.json()["agents"] if r["agent_key"] == "knowledge_agent")
    assert original["metrics"]["token_usage"] == 0
    usages = [
        {"total_tokens": 49},
        {"total": 11},
        {"total_tokens": None, "known_total_tokens": 7, "source": "partially_reported"},
    ]
    async with app.state.session_factory() as session, session.begin():
        for i, usage in enumerate(usages):
            session.add(
                AgentExecution(
                    id=f"TOKEN-METRICS-{i}",
                    mission_id=mission,
                    node="knowledge",
                    agent_role="knowledge_agent",
                    status="succeeded",
                    token_usage=usage,
                    started_at=datetime.now(UTC),
                )
            )
        session.add(
            AgentExecution(
                id="TOKEN-METRICS-OLD",
                mission_id=mission,
                node="knowledge",
                agent_role="knowledge_agent",
                status="succeeded",
                token_usage={"total_tokens": 1000},
                started_at=datetime.now(UTC) - timedelta(hours=25),
            )
        )
    after = await client.get("/api/v1/agents")
    assert after.status_code == 200
    corrected = next(r for r in after.json()["agents"] if r["agent_key"] == "knowledge_agent")
    assert corrected["metrics"]["token_usage"] == 67
    assert corrected["metrics"]["requests"] == original["metrics"]["requests"] + 3
    assert corrected["metrics"]["succeeded"] == original["metrics"]["succeeded"] + 3
    assert corrected["metrics"]["failed"] == original["metrics"]["failed"]
    observer = await client.get("/api/v1/observability/agent-executions/24h")
    assert observer.status_code == 200
    assert observer.json()["summary"]["total_tokens"] == 67
    detail = await client.get(f"/api/v1/missions/{mission}")
    assert detail.status_code == 200
    partial = next(r for r in detail.json()["executions"] if r["execution_id"] == "TOKEN-METRICS-2")
    assert partial["token_usage"] == usages[2]
