from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import select

from windops_backend.api import router as api_router
from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.main import create_app
from windops_backend.models import AgentExecution, Base, ReadAccessAudit
from windops_backend.outbox import process_outbox_event
from windops_backend.schemas import TASK_MEASUREMENT_SCHEMAS
from windops_backend.storage import OutboxEvent


def anomaly(event_id: str) -> dict[str, Any]:
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


def test_every_business_get_route_has_the_attributed_read_dependency() -> None:
    public_probes = {"/healthz", "/readyz"}
    business_reads = [
        route
        for route in api_router.routes
        if isinstance(route, APIRoute)
        and "GET" in route.methods
        and route.path not in public_probes
    ]
    assert business_reads
    for route in business_reads:
        calls = {dependency.call for dependency in route.dependant.dependencies}
        assert any(getattr(call, "__name__", "") == "require_read_access" for call in calls), (
            route.path
        )


@pytest.mark.asyncio
async def test_business_reads_require_auth_and_are_durably_attributed(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anonymous:
        denied = await anonymous.get("/api/v1/turbines/WT-023/health")
    assert denied.status_code == 401

    allowed = await client.get("/api/v1/turbines/WT-023/health")
    assert allowed.status_code == 200
    async with app.state.session_factory() as session:
        audit = await session.scalar(
            select(ReadAccessAudit)
            .where(ReadAccessAudit.endpoint == "/api/v1/turbines/WT-023/health")
            .order_by(ReadAccessAudit.accessed_at.desc())
        )
        assert audit is not None
        assert audit.subject == "integration-test-system"
        assert audit.role == "test_system"


@pytest.mark.asyncio
async def test_bearer_secret_maps_to_server_owned_subject_not_unsigned_headers(tmp_path) -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'read-auth.sqlite'}",
        schema_bootstrap=True,
        demo_seed=True,
        test_auth_bypass_enabled=False,
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={
                "Authorization": (
                    f"Bearer {settings.operations_manager_api_key.get_secret_value()}"
                ),
                "X-WindOps-Test-Principal": "forged-reader",
            },
        ) as reader:
            response = await reader.get("/api/v1/knowledge/documents/KB-MB-GW165-001")
        assert response.status_code == 200
        assert response.json()["source_storage"] == "database"
        assert response.json()["citation_uri"].startswith("windops://knowledge/documents/")
        async with application.state.session_factory() as session:
            audit = await session.scalar(
                select(ReadAccessAudit).where(
                    ReadAccessAudit.endpoint == "/api/v1/knowledge/documents/KB-MB-GW165-001"
                )
            )
            assert audit is not None
            assert audit.subject == "operations-manager"
            assert audit.role == "operations_manager"


@pytest.mark.asyncio
async def test_versioned_catalog_is_persisted_and_linked_to_executions(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    catalog = (await client.get("/api/v1/catalog")).json()
    assert catalog["catalog_version"]["version"] == "2026.08.1"
    assert len(catalog["agents"]) == 8
    assert len(catalog["skills"]) == 8
    assert len(catalog["tools"]) == 11
    assert all(agent["skills"] for agent in catalog["agents"])

    ingested = await client.post("/api/v1/scada/ingest", json=anomaly("SCADA-WT023-CATALOG-001"))
    mission_id = ingested.json()["results"][0]["mission_id"]
    detail = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert all(row["catalog_version_id"] for row in detail["executions"])
    assert all(row["agent_definition_id"] for row in detail["executions"])
    recorded_calls = [call for row in detail["executions"] for call in row["tool_calls"]]
    assert recorded_calls
    assert {call["version"] for call in recorded_calls} == {"2026.08.1"}

    async with app.state.session_factory() as session:
        rows = (
            await session.scalars(
                select(AgentExecution).where(AgentExecution.mission_id == mission_id)
            )
        ).all()
        assert all(row.catalog_version_id for row in rows)


@pytest.mark.asyncio
async def test_observability_aggregates_24h_and_retains_public_failure_context(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    ingested = await client.post(
        "/api/v1/scada/ingest", json=anomaly("SCADA-WT023-OBSERVABILITY-001")
    )
    mission_id = ingested.json()["results"][0]["mission_id"]
    async with app.state.session_factory() as session, session.begin():
        event = OutboxEvent(
            event_type="mission.analysis.requested",
            aggregate_type="mission",
            aggregate_id=mission_id,
            payload={"mission_id": mission_id},
        )
        session.add(event)
        await session.flush()
        event_id = event.id

    async def fail_with_public_context(session: Any, settings: Settings, value: str) -> None:
        del session, settings
        error = RuntimeError("controlled provider timeout")
        error.windops_public_context = {  # type: ignore[attr-defined]
            "node": "diagnosis",
            "agent_role": "failure_diagnosis_agent",
            "input_refs": {"mission_id": value, "evidence_refs": ["EVD-public"]},
            "public_output": {
                "failure": {
                    "node": "diagnosis",
                    "error_code": "ProviderTimeout",
                    "message": "controlled provider timeout",
                }
            },
            "tool_calls": [{"name": "query_similar_failures", "version": "2026.08.1"}],
            "latency_ms": 1250,
            "provider": "litellm",
            "model": "test-provider",
            "token_usage": {"total_tokens": 17},
            "error_code": "ProviderTimeout",
        }
        raise error

    with pytest.raises(RuntimeError, match="controlled provider timeout"):
        await process_outbox_event(
            app.state.session_factory,
            app.state.settings,
            event_id,
            fail_with_public_context,
        )

    response = await client.get("/api/v1/observability/agent-executions/24h")
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["window"] == "24h"
    assert metrics["summary"]["total"] >= 8
    assert metrics["summary"]["failed"] == 1
    assert metrics["summary"]["p95_latency_ms"] >= 0
    failure = metrics["failures"][0]
    assert failure["node"] == "diagnosis"
    assert failure["error_code"] == "ProviderTimeout"
    assert failure["input_refs"]["evidence_refs"] == ["EVD-public"]
    assert failure["public_output"]["failure"]["message"] == "controlled provider timeout"


@pytest.mark.parametrize(
    ("sequence", "measurement"),
    [
        (1, {"lubrication_condition": "acceptable", "water_content_ppm": 501}),
        (2, {"vibration_rms_mm_s": 4.51, "bpfo_band_energy_pct": 4}),
        (3, {"bearing_temperature_c": 75.1}),
        (4, {"defect_severity": "moderate", "spall_area_mm2": 1}),
        (
            5,
            {
                "photo_count": 2,
                "main_bearing_health_score": 77,
                "turbine_health_score": 81,
            },
        ),
    ],
)
def test_each_field_task_measurement_schema_rejects_unsafe_closure_values(
    sequence: int, measurement: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        TASK_MEASUREMENT_SCHEMAS[sequence].model_validate(measurement)


def test_alembic_metadata_and_0004_cover_operational_hardening() -> None:
    assert {"outbox_events", "field_task_evidence"} <= set(Base.metadata.tables)
    root = Path(__file__).parents[1]
    env_source = (root / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "from windops_backend import storage as _storage" in env_source
    migration = (
        root / "alembic" / "versions" / "0004_operational_hardening_and_versioned_catalog.py"
    ).read_text(encoding="utf-8")
    for value in (
        '"claim_token"',
        '"lease_expires_at"',
        '"read_access_audits"',
        '"catalog_versions"',
        '"agent_definitions"',
        '"skill_definitions"',
        '"tool_definitions"',
        '"agent_skill_links"',
        '"agent_tool_links"',
    ):
        assert value in migration
