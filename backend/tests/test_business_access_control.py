from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from windops_backend.models import (
    Alarm,
    AssetHealthEvent,
    DomainEvent,
    IngestReceipt,
    IngestSource,
    Mission,
    ReadAccessAudit,
    ScadaSample,
    Tenant,
    Turbine,
    WindFarm,
)


async def _seed_second_tenant(app: FastAPI) -> None:
    async with app.state.session_factory() as session, session.begin():
        session.add(Tenant(id="tenant-west", name="West tenant"))
        session.add(
            WindFarm(
                id="WF-WEST-01",
                tenant_id="tenant-west",
                name="West wind farm",
                capacity_mw=120.0,
            )
        )
        session.add(
            Turbine(
                id="WT-999",
                wind_farm_id="WF-WEST-01",
                model="GW-999",
                status="running",
                health_score=91.0,
            )
        )


def _scoped_headers(turbine_id: str, *, role: str = "field_technician") -> dict[str, str]:
    return {
        "X-WindOps-Test-Principal": f"scoped-{role}",
        "X-WindOps-Test-Role": role,
        "X-WindOps-Test-Turbine-Ids": turbine_id,
    }


async def _seed_west_business_rows(app: FastAPI) -> None:
    await _seed_second_tenant(app)
    now = datetime.now(UTC)
    async with app.state.session_factory() as session, session.begin():
        source_id = await session.scalar(select(IngestSource.id).order_by(IngestSource.id).limit(1))
        if source_id is None:
            source_id = "scope-test-source"
            session.add(
                IngestSource(
                    id=source_id,
                    display_name="Scope test source",
                    source_kind="rest",
                    policy={},
                )
            )
        session.add(
            IngestReceipt(
                source_event_id="scope-west-source-event",
                source_id=source_id,
                payload_hash="e" * 64,
            )
        )
        session.add(
            ScadaSample(
                id="scope-west-sample",
                observed_at=now,
                source_event_id="scope-west-source-event",
                source_id=source_id,
                turbine_id="WT-999",
                variable="active_power",
                value=9.9,
                unit="MW",
                quality="good",
                attributes={},
            )
        )
        session.add(
            Alarm(
                id="ALARM-SCOPE-WEST",
                turbine_id="WT-999",
                source_event_id="scope-west-source-event",
                code="WEST-ONLY",
                subsystem="generator",
                title="West tenant private alarm",
                severity="critical",
                status="open",
                triggered_at=now,
                evidence={"private": "west"},
            )
        )
        session.add(
            Mission(
                id="MISSION-SCOPE-WEST",
                alarm_id="ALARM-SCOPE-WEST",
                turbine_id="WT-999",
                title="West tenant private mission",
                status="detected",
                public_state={"private": "west"},
            )
        )
        session.add(
            AssetHealthEvent(
                id="HEALTH-SCOPE-WEST",
                turbine_id="WT-999",
                mission_id="MISSION-SCOPE-WEST",
                score=51.0,
                status="critical",
                reason="West tenant private health event",
            )
        )


async def test_business_collections_and_details_are_filtered_at_the_database_boundary(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _seed_second_tenant(app)

    east = await client.get("/api/v1/turbines", headers=_scoped_headers("WT-023"))
    assert east.status_code == 200
    assert [row["turbine_id"] for row in east.json()["turbines"]] == ["WT-023"]
    assert east.json()["count"] == 1

    hidden_detail = await client.get(
        "/api/v1/turbines/WT-999",
        headers=_scoped_headers("WT-023"),
    )
    assert hidden_detail.status_code == 404

    west = await client.get("/api/v1/turbines", headers=_scoped_headers("WT-999"))
    assert west.status_code == 200
    assert [row["turbine_id"] for row in west.json()["turbines"]] == ["WT-999"]

    async with app.state.session_factory() as session:
        audits = list(
            (
                await session.scalars(
                    select(ReadAccessAudit).where(
                        ReadAccessAudit.subject == "scoped-field_technician",
                        ReadAccessAudit.endpoint == "/api/v1/turbines",
                    )
                )
            ).all()
        )
    recorded_scopes = {row.query["authorization"]["scope_fingerprint_sha256"] for row in audits}
    assert len(recorded_scopes) == 2
    assert {row.query["authorization"]["turbine_count"] for row in audits} == {1}


async def test_scoped_counts_aggregates_and_related_rows_do_not_leak_other_tenant_data(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _seed_west_business_rows(app)
    headers = _scoped_headers("WT-023")

    async with app.state.session_factory() as session:
        expected_samples = int(
            await session.scalar(
                select(func.count())
                .select_from(ScadaSample)
                .where(ScadaSample.turbine_id == "WT-023")
            )
            or 0
        )
        expected_missions = int(
            await session.scalar(
                select(func.count()).select_from(Mission).where(Mission.turbine_id == "WT-023")
            )
            or 0
        )

    measurements = await client.get(
        "/api/v1/scada/measurements",
        params={"limit": 1000},
        headers=headers,
    )
    assert measurements.status_code == 200
    assert measurements.json()["meta"]["total"] == expected_samples
    assert "WT-999" not in str(measurements.json())

    sample_count = await client.get("/api/v1/scada/sample-count", headers=headers)
    assert sample_count.status_code == 200
    assert sample_count.json()["count"] == expected_samples

    alarms = await client.get("/api/v1/alarms", headers=headers)
    missions = await client.get("/api/v1/missions", headers=headers)
    health = await client.get("/api/v1/health/assessments", headers=headers)
    diagnoses = await client.get(
        "/api/v1/diagnoses",
        params={"limit": 1},
        headers=headers,
    )
    dashboard = await client.get("/api/v1/dashboard", headers=headers)
    for response in (alarms, missions, health, diagnoses, dashboard):
        assert response.status_code == 200
        assert "WT-999" not in str(response.json())
        assert "SCOPE-WEST" not in str(response.json())
        assert "private" not in str(response.json()).casefold()
    assert dashboard.json()["data"]["fleet"]["asset_count"] == 1
    assert health.json()["meta"]["total"] == 1
    assert diagnoses.json()["meta"]["total"] == expected_missions
    assert diagnoses.json()["meta"]["filtered_total"] == expected_missions


async def test_machine_identity_is_denied_every_business_read(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/resources",
        headers={
            "X-WindOps-Test-Principal": "ingest-source:offshore-opcua-01",
            "X-WindOps-Test-Role": "scada_ingestor",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "BUSINESS_READ_FORBIDDEN"


async def test_restricted_data_scope_cannot_cross_into_another_business_domain(
    client: AsyncClient,
) -> None:
    headers = {
        "X-WindOps-Test-Principal": "knowledge-only-reader",
        "X-WindOps-Test-Role": "field_technician",
        "X-WindOps-Test-Tenant-Ids": "tenant-east-china",
        "X-WindOps-Test-Data-Scopes": "knowledge",
    }
    allowed = await client.get("/api/v1/knowledge/documents", headers=headers)
    denied = await client.get("/api/v1/turbines", headers=headers)
    assert allowed.status_code == 200
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "DATA_SCOPE_FORBIDDEN"


async def test_global_control_plane_write_requires_explicit_unbounded_global_grant(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/platform/configurations",
        headers=_scoped_headers("WT-023", role="operations_manager"),
        json={
            "configuration_key": "backup_policy",
            "value": {"rpo_minutes": 15, "rto_minutes": 60},
            "expected_revision": 0,
            "reason": "scope boundary must reject this global write",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "GLOBAL_SCOPE_REQUIRED"


async def test_scoped_events_filter_payloads_and_use_subject_bound_opaque_cursors(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _seed_second_tenant(app)
    async with app.state.session_factory() as session, session.begin():
        session.add_all(
            [
                DomainEvent(
                    id="scope-event-east",
                    event_type="scope.test",
                    aggregate_type="turbine",
                    aggregate_id="WT-023",
                    payload={"turbine_id": "WT-023", "private": "east"},
                ),
                DomainEvent(
                    id="scope-event-west",
                    event_type="scope.test",
                    aggregate_type="turbine",
                    aggregate_id="WT-999",
                    payload={"turbine_id": "WT-999", "private": "west"},
                ),
            ]
        )

    east_headers = _scoped_headers("WT-023")
    east = await client.get(
        "/api/v1/events",
        params={"event_type": "scope.test"},
        headers=east_headers,
    )
    assert east.status_code == 200
    east_body = east.json()
    assert [row["aggregate_id"] for row in east_body["events"]] == ["WT-023"]
    cursor = east_body["next_cursor"]
    assert isinstance(cursor, str) and cursor.startswith("v1.")
    assert east_body["events"][0]["sequence"] == cursor
    assert "WT-999" not in str(east_body)

    resumed = await client.get(
        "/api/v1/events",
        params={"event_type": "scope.test", "cursor": cursor},
        headers=east_headers,
    )
    assert resumed.status_code == 200
    assert resumed.json()["events"] == []

    wrong_subject = await client.get(
        "/api/v1/events",
        params={"event_type": "scope.test", "cursor": cursor},
        headers=_scoped_headers("WT-999"),
    )
    assert wrong_subject.status_code == 422

    raw_cursor = await client.get(
        "/api/v1/events",
        params={"event_type": "scope.test", "after": 1},
        headers=east_headers,
    )
    assert raw_cursor.status_code == 422


async def test_out_of_scope_write_is_rejected_without_receipt_or_event(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _seed_second_tenant(app)
    async with app.state.session_factory() as session, session.begin():
        session.add(
            IngestReceipt(
                source_event_id="scope-write-alarm-source",
                payload_hash="f" * 64,
            )
        )
        session.add(
            Alarm(
                id="ALARM-SCOPE-WRITE",
                turbine_id="WT-023",
                source_event_id="scope-write-alarm-source",
                code="SCOPE-TEST",
                subsystem="main_bearing",
                title="Scope boundary alarm",
                severity="major",
                status="open",
                triggered_at=datetime.now(UTC),
                evidence={},
            )
        )
    async with app.state.session_factory() as session:
        alarm = await session.scalar(select(Alarm).where(Alarm.turbine_id == "WT-023"))
        assert alarm is not None
        alarm_id = alarm.id
        original_status = alarm.status
        original_revision = alarm.revision
        event_count = int(
            await session.scalar(
                select(func.count())
                .select_from(DomainEvent)
                .where(DomainEvent.aggregate_id == alarm_id)
            )
            or 0
        )

    response = await client.post(
        f"/api/v1/alarms/{alarm_id}",
        json={"action": "acknowledge", "expected_revision": original_revision},
        headers={
            **_scoped_headers("WT-999", role="operations_manager"),
            "Idempotency-Key": "out-of-scope-alarm-command",
        },
    )
    assert response.status_code == 404

    async with app.state.session_factory() as session:
        unchanged = await session.get(Alarm, alarm_id)
        assert unchanged is not None
        assert unchanged.status == original_status
        assert unchanged.revision == original_revision
        assert (
            int(
                await session.scalar(
                    select(func.count())
                    .select_from(DomainEvent)
                    .where(DomainEvent.aggregate_id == alarm_id)
                )
                or 0
            )
            == event_count
        )


async def test_mixed_scope_batch_fails_atomically_without_partial_mission_or_event(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _seed_second_tenant(app)
    now = datetime.now(UTC)
    async with app.state.session_factory() as session, session.begin():
        for suffix, turbine_id in (("EAST", "WT-023"), ("WEST", "WT-999")):
            source_event_id = f"scope-batch-{suffix.lower()}"
            session.add(
                IngestReceipt(
                    source_event_id=source_event_id,
                    payload_hash=("a" if suffix == "EAST" else "b") * 64,
                )
            )
            session.add(
                Alarm(
                    id=f"ALARM-SCOPE-BATCH-{suffix}",
                    turbine_id=turbine_id,
                    source_event_id=source_event_id,
                    code=f"SCOPE-{suffix}",
                    subsystem="main_bearing",
                    title=f"Scope batch {suffix.lower()} alarm",
                    severity="major",
                    status="open",
                    triggered_at=now,
                    evidence={},
                )
            )

    def mission_payload(suffix: str) -> dict[str, object]:
        return {
            "alarm_id": f"ALARM-SCOPE-BATCH-{suffix}",
            "title": f"Scoped batch mission {suffix}",
            "analysis_profile": {
                "component": "main_bearing",
                "primary_variable": "main_bearing_temperature",
                "related_variables": ["active_power"],
                "failure_mode_hint": "scope test",
                "knowledge_query": "scope test bearing inspection",
            },
        }

    response = await client.post(
        "/api/v1/missions/batch",
        headers={
            **_scoped_headers("WT-023", role="operations_manager"),
            "Idempotency-Key": "scope-batch-atomicity",
        },
        json={"missions": [mission_payload("EAST"), mission_payload("WEST")]},
    )
    assert response.status_code == 404

    async with app.state.session_factory() as session:
        mission_count = int(
            await session.scalar(
                select(func.count())
                .select_from(Mission)
                .where(Mission.alarm_id.in_(["ALARM-SCOPE-BATCH-EAST", "ALARM-SCOPE-BATCH-WEST"]))
            )
            or 0
        )
        event_count = int(
            await session.scalar(
                select(func.count())
                .select_from(DomainEvent)
                .where(
                    DomainEvent.event_type == "mission.created",
                    DomainEvent.payload["alarm_id"]
                    .as_string()
                    .in_(["ALARM-SCOPE-BATCH-EAST", "ALARM-SCOPE-BATCH-WEST"]),
                )
            )
            or 0
        )
    assert mission_count == 0
    assert event_count == 0
