from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from windops_backend.agents.tools import (
    TOOL_CATALOG,
    DeterministicTestEmbeddingProvider,
    SQLToolAdapter,
)
from windops_backend.models import Decision, Evidence, ResourceReservation


def anomaly_sample(event_id: str) -> dict[str, Any]:
    return {
        "samples": [
            {
                "source_event_id": event_id,
                "turbine_id": "WT-023",
                "observed_at": "2026-08-13T02:14:03Z",
                "variable": "main_bearing_vibration_rms",
                "value": 4.81,
                "unit": "mm/s",
                "quality": "good",
                "attributes": {
                    "baseline": 3.79,
                    "anomaly_score": 0.86,
                    "temperature_delta_c": 8.4,
                    "power_fluctuation_pct": 6,
                },
            }
        ]
    }


async def create_review_mission(client: httpx.AsyncClient, event_id: str) -> dict[str, Any]:
    ingested = await client.post("/api/v1/scada/ingest", json=anomaly_sample(event_id))
    assert ingested.status_code == 202
    mission_id = ingested.json()["results"][0]["mission_id"]
    detail = await client.get(f"/api/v1/missions/{mission_id}")
    assert detail.status_code == 200
    return detail.json()


def test_catalog_is_the_exact_eleven_public_domain_tools() -> None:
    assert [item["name"] for item in TOOL_CATALOG] == [
        "get_turbine_status",
        "query_scada",
        "query_alarm_history",
        "query_vibration",
        "query_weather",
        "query_maintenance_history",
        "query_similar_failures",
        "calculate_health_score",
        "predict_rul",
        "create_decision",
        "create_work_order",
    ]
    assert TOOL_CATALOG[-2]["mode"] == "draft-write-gated"
    assert TOOL_CATALOG[-1]["mode"] == "human-approval-gated-write"


@pytest.mark.asyncio
async def test_graph_persists_public_evidence_decision_and_complete_execution_audit(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    mission = await create_review_mission(client, "SCADA-WT023-DOMAIN-001")

    assert len(mission["evidence"]) == 3
    assert all(item["evidence_id"].startswith("EVD-") for item in mission["evidence"])
    knowledge = next(
        item for item in mission["evidence"] if item["evidence_type"] == "knowledge_citation"
    )
    assert knowledge["retrieval_method"] == "deterministic_test_cosine"
    assert knowledge["citation_uri"].startswith("/api/v1/knowledge/documents/")

    decision = mission["decision"]
    assert decision["status"] == "pending_approval"
    assert len(decision["alternatives"]) == 3
    assert decision["recommended_alternative_id"] == "ALT-B"
    assert len(decision["risks"]) == 2
    assert decision["approval_id"] is None

    executions = mission["executions"]
    assert all(isinstance(item["tool_calls"], list) for item in executions)
    assert all(item["latency_ms"] >= 0 for item in executions)
    model_nodes = [item for item in executions if item["provider"] == "deterministic"]
    assert {item["node"] for item in model_nodes} == {
        "diagnosis",
        "alternatives",
        "reviews",
    }
    assert all(
        item["token_usage"]["source"] == "deterministic_test_no_model" for item in model_nodes
    )
    assert all(item["token_usage"]["total_tokens"] == 0 for item in model_nodes)

    async with app.state.session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Evidence)
                .where(Evidence.mission_id == mission["mission_id"])
            )
        ) == 3
        persisted = await session.scalar(
            select(Decision).where(Decision.mission_id == mission["mission_id"])
        )
        assert persisted is not None
        assert persisted.recommended_alternative_id == "ALT-B"


@pytest.mark.asyncio
async def test_rag_uses_explicit_test_embedding_and_honest_database_citation(
    app: FastAPI,
) -> None:
    async with app.state.session_factory() as session:
        adapter = SQLToolAdapter(session, DeterministicTestEmbeddingProvider())
        matches = await adapter.query_similar_failures(
            "main bearing vibration temperature inspection", "WT-023"
        )
        assert matches[0]["retrieval_method"] == "deterministic_test_cosine"
        assert matches[0]["embedding_provider"] == "deterministic_test"
        assert matches[0]["citation_uri"].startswith("windops://knowledge/documents/")
        assert matches[0]["citation_href"].startswith("/api/v1/knowledge/documents/")


@pytest.mark.asyncio
async def test_sql_read_and_compute_tools_report_real_empty_and_baseline_state(
    app: FastAPI,
) -> None:
    async with app.state.session_factory() as session:
        adapter = SQLToolAdapter(session, DeterministicTestEmbeddingProvider())
        status = await adapter.get_turbine_status("WT-023")
        assert status["health_score"] == 96
        assert len(status["maintenance_resources"]) == 3
        assert await adapter.query_alarm_history("WT-023") == []
        assert await adapter.query_maintenance_history("WT-023") == []
        health = await adapter.calculate_health_score("WT-023")
        assert health["health_score"] == 100
        assert health["persisted"] is False
        rul = await adapter.predict_rul("WT-023", "main_bearing")
        assert rul["estimated_rul_days"] > 30
        assert rul["inputs"] == {"anomaly_score": 0.0, "trend_pct": 0.0}


@pytest.mark.asyncio
async def test_atomic_resource_claim_prevents_a_second_mission_from_double_booking(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    first = await create_review_mission(client, "SCADA-WT023-RESOURCE-001")
    first_approval = await client.post(
        f"/api/v1/missions/{first['mission_id']}/approvals",
        json={
            "action": "approve",
            "expected_revision": first["revision"],
            "reason": "First mission owns the controlled maintenance resources",
        },
    )
    assert first_approval.status_code == 200
    first_after_approval = (await client.get(f"/api/v1/missions/{first['mission_id']}")).json()
    assert first_after_approval["decision"]["status"] == "approved"
    assert first_after_approval["decision"]["approval_id"] == first_approval.json()["approval_id"]

    second = await create_review_mission(client, "SCADA-WT023-RESOURCE-002")
    second_approval = await client.post(
        f"/api/v1/missions/{second['mission_id']}/approvals",
        json={
            "action": "approve",
            "expected_revision": second["revision"],
            "reason": "Attempting to claim resources already held by another mission",
        },
    )
    assert second_approval.status_code == 409

    async with app.state.session_factory() as session:
        first_count = await session.scalar(
            select(func.count())
            .select_from(ResourceReservation)
            .where(ResourceReservation.mission_id == first["mission_id"])
        )
        second_count = await session.scalar(
            select(func.count())
            .select_from(ResourceReservation)
            .where(ResourceReservation.mission_id == second["mission_id"])
        )
        assert first_count == 3
        assert second_count == 0


def test_second_migration_adds_domain_entities_and_execution_audit() -> None:
    migration = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0002_domain_evidence_decisions_and_execution_audit.py"
    ).read_text(encoding="utf-8")
    assert '"evidence"' in migration
    assert '"decisions"' in migration
    assert '"tool_calls"' in migration
    assert '"token_usage"' in migration


def test_production_rag_source_requires_provider_vectors_and_pgvector_cosine() -> None:
    tools_source = (
        Path(__file__).parents[1] / "src" / "windops_backend" / "agents" / "tools.py"
    ).read_text(encoding="utf-8")
    assert "await litellm.aembedding" in tools_source
    assert "KnowledgeDocument.embedding.cosine_distance(query_vector)" in tools_source
    assert 'retrieval_method = "pgvector_hnsw_cosine"' in tools_source
    assert "production PostgreSQL RAG requires a production embedding provider" in tools_source
