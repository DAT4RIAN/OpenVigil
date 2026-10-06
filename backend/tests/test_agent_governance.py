from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI

from windops_backend.enums import AlarmSeverity
from windops_backend.models import Alarm, IngestReceipt


@pytest.mark.asyncio
async def test_bundled_catalog_upgrade_preserves_stops_and_custom_active_releases(app) -> None:
    from sqlalchemy import delete

    from windops_backend.models import (
        AgentDefinition,
        AgentSkillLink,
        AgentToolLink,
        CatalogVersion,
    )
    from windops_backend.services.seed import CATALOG_VERSION, seed_agent_catalog

    async with app.state.session_factory() as session, session.begin():
        # Replace only this test database's pristine bundled definitions with a
        # previous-install snapshot; no production data or deployment is involved.
        await session.execute(delete(AgentSkillLink))
        await session.execute(delete(AgentToolLink))
        await session.execute(delete(AgentDefinition))
        session.add(
            CatalogVersion(
                id="synthetic-previous-catalog",
                version="2026.08.1",
                description="Synthetic previous-install governance challenge",
            )
        )
        await session.flush()
        for key, version, active in (
            ("scada_analysis_agent", "2026.08.1", False),
            ("vibration_diagnosis_agent", "2026.08.1", True),
            ("work_order_agent", "2026.09.2", True),
        ):
            session.add(
                AgentDefinition(
                    id=f"agent:{key}@{version}",
                    agent_key=key,
                    role=key,
                    version=version,
                    catalog_version_id="synthetic-previous-catalog",
                    display_name=key,
                    description="Synthetic prior governed state",
                    active=active,
                )
            )
        await session.flush()
        await seed_agent_catalog(session)
        stopped = await session.get(
            AgentDefinition, f"agent:scada_analysis_agent@{CATALOG_VERSION}"
        )
        vibration = await session.get(
            AgentDefinition, f"agent:vibration_diagnosis_agent@{CATALOG_VERSION}"
        )
        workorder = await session.get(AgentDefinition, f"agent:work_order_agent@{CATALOG_VERSION}")
        assert stopped.active is False
        assert vibration.active is True
        assert workorder.active is False
        assert (await session.get(AgentDefinition, "agent:work_order_agent@2026.09.2")).active
        assert not (
            await session.get(AgentDefinition, "agent:vibration_diagnosis_agent@2026.08.1")
        ).active
        vibration.active = False
        await session.flush()
        await seed_agent_catalog(session)
        assert vibration.active is False


async def _seed_alarm(app: FastAPI) -> str:
    alarm_id = "ALARM-AGENT-TOOL-001"
    async with app.state.session_factory() as session, session.begin():
        session.add(
            IngestReceipt(
                source_event_id="source-agent-tool-001",
                payload_hash="a" * 64,
            )
        )
        session.add(
            Alarm(
                id=alarm_id,
                turbine_id="WT-023",
                source_event_id="source-agent-tool-001",
                code="GB-OIL-TEMP-HIGH",
                subsystem="gearbox",
                title="Gearbox oil temperature sustained high",
                severity=AlarmSeverity.MAJOR.value,
                triggered_at=datetime.now(UTC),
                evidence={
                    "variable": "gearbox_oil_temperature",
                    "value": 92.4,
                    "unit": "celsius",
                    "attributes": {"anomaly_score": 0.91},
                },
            )
        )
    return alarm_id


@pytest.mark.asyncio
async def test_agent_start_stop_release_and_cas(client: Any) -> None:
    catalog = await client.get("/api/v1/agents")
    assert catalog.status_code == 200
    agent = next(
        row for row in catalog.json()["agents"] if row["agent_key"] == "scada_analysis_agent"
    )
    stopped = await client.post(
        "/api/v1/agents/scada_analysis_agent/commands",
        headers={"Idempotency-Key": "agent-control-stop-001"},
        json={
            "action": "stop",
            "expected_definition_id": agent["definition_id"],
            "reason": "planned provider maintenance",
        },
    )
    assert stopped.status_code == 200
    assert stopped.json()["active"] is False

    stale = await client.post(
        "/api/v1/agents/scada_analysis_agent/commands",
        headers={"Idempotency-Key": "agent-control-stale-001"},
        json={
            "action": "start",
            "expected_definition_id": "agent:stale@0",
            "reason": "stale operator view",
        },
    )
    assert stale.status_code == 409

    started = await client.post(
        "/api/v1/agents/scada_analysis_agent/commands",
        headers={"Idempotency-Key": "agent-control-start-001"},
        json={
            "action": "start",
            "expected_definition_id": agent["definition_id"],
            "reason": "provider maintenance completed",
        },
    )
    assert started.status_code == 200
    released = await client.post(
        "/api/v1/agents/scada_analysis_agent/releases",
        headers={"Idempotency-Key": "agent-release-2026-08-2"},
        json={
            "source_definition_id": agent["definition_id"],
            "version": "2026.10.2",
            "display_name": "SCADA Analysis Agent",
            "role": "scada_analysis_agent",
            "description": "Production release with governed source-quality checks",
            "reason": "change request AGENT-2042 approved",
        },
    )
    assert released.status_code == 201, released.text
    assert released.json()["active"] is True
    assert released.json()["version"] == "2026.10.2"

    refreshed = await client.get("/api/v1/agents")
    row = next(
        item for item in refreshed.json()["agents"] if item["agent_key"] == "scada_analysis_agent"
    )
    assert row["definition_id"] == released.json()["definition_id"]
    assert "query_scada" in row["tools"]


@pytest.mark.asyncio
async def test_agent_tool_reads_and_decision_writes_are_durable_and_idempotent(
    app: FastAPI, client: Any
) -> None:
    read = await client.post(
        "/api/v1/agent-tools",
        headers={"Idempotency-Key": "agent-read-wt023-001"},
        json={
            "tool": "get_turbine_status",
            "args": {"turbineId": "WT-023"},
            "agentId": "scada_analysis_agent",
            "idempotencyKey": "agent-read-wt023-001",
        },
    )
    assert read.status_code == 200, read.text
    assert read.json()["data"]["execution"]["result"]["data"]["turbine_id"] == "WT-023"
    # Deterministic SQL tools have no provider usage; the ledger must not
    # fabricate a zero token estimate.
    assert read.json()["data"]["execution"]["tokenEstimate"] is None
    replay = await client.post(
        "/api/v1/agent-tools",
        headers={"Idempotency-Key": "agent-read-wt023-001"},
        json={
            "tool": "get_turbine_status",
            "args": {"turbineId": "WT-023"},
            "agentId": "scada_analysis_agent",
            "idempotencyKey": "agent-read-wt023-001",
        },
    )
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == read.json()
    assert (
        replay.json()["data"]["execution"]["executionId"]
        == (read.json()["data"]["execution"]["executionId"])
    )

    alarm_id = await _seed_alarm(app)
    created = await client.post(
        "/api/v1/missions",
        headers={"Idempotency-Key": "agent-tool-mission-001"},
        json={
            "alarm_id": alarm_id,
            "title": "Agent Tool Gearbox Investigation",
            "analysis_profile": {
                "component": "gearbox",
                "primary_variable": "gearbox_oil_temperature",
                "related_variables": ["active_power"],
                "failure_mode_hint": "cooling degradation",
                "knowledge_query": "gearbox oil cooling inspection",
            },
        },
    )
    assert created.status_code == 202, created.text
    mission_id = created.json()["mission_id"]
    decisions = await client.get("/api/v1/decisions", params={"mission_id": mission_id})
    decision = decisions.json()["decisions"][0]
    write = await client.post(
        "/api/v1/agent-tools",
        headers={"Idempotency-Key": "agent-decision-write-001"},
        json={
            "tool": "create_decision",
            "agentId": "maintenance_strategy_agent",
            "missionId": mission_id,
            "idempotencyKey": "agent-decision-write-001",
            "args": {
                "missionId": mission_id,
                "alternatives": decision["alternatives"],
                "recommendedAlternativeId": decision["recommended_alternative_id"],
                "recommendationReason": "Revalidated against latest governed evidence",
                "risks": decision["risks"],
            },
        },
    )
    assert write.status_code == 200, write.text
    result = write.json()["data"]["execution"]["result"]["data"]
    assert result["decision_id"] == decision["decision_id"]
    assert result["requires_human_approval"] is True

    ledger = await client.get("/api/v1/agent-tools", params={"limit": 10})
    assert ledger.status_code == 200
    assert ledger.json()["meta"]["persistence"] == "postgresql"
    history = ledger.json()["data"]["executionHistory"]
    assert len(history) == 2
    assert all(item["tokenEstimate"] is None for item in history)
