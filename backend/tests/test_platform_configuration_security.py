from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from windops_backend.enums import Environment
from windops_backend.models import (
    DomainEvent,
    IngestSource,
    IngestSourceSecurityAudit,
    PlatformConfigurationRevision,
    PlatformConfigurationSecurityAudit,
)
from windops_backend.services.platform_governance import (
    remediate_ingest_source_credentials,
    remediate_platform_configuration_history,
    unresolved_platform_configuration_rotations,
)


def _scoped_headers(role: str, *, allow_global: bool = False) -> dict[str, str]:
    return {
        "X-WindOps-Test-Principal": f"h001-{role}",
        "X-WindOps-Test-Role": role,
        "X-WindOps-Test-Tenant-Ids": "tenant-east-china",
        "X-WindOps-Test-Data-Scopes": "platform",
        "X-WindOps-Test-Allow-Global": str(allow_global).lower(),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "submitted_secret"),
    [
        (
            {
                "schema_version": 1,
                "issuer": "https://identity.example.com",
                "audience": "sk-proj-auditfixture0123456789",
            },
            "sk-proj-auditfixture0123456789",
        ),
        (
            {"rpo_minutes": 15, "rto_minutes": 60, "api_token": "audit-secret-value"},
            "audit-secret-value",
        ),
        (
            {
                "rpo_minutes": 15,
                "rto_minutes": 60,
                "verification": {
                    "restore_test_interval_days": 30,
                    "retention_days": 30,
                    "Private-Key": "-----BEGIN PRIVATE KEY-----fixture",
                },
            },
            "-----BEGIN PRIVATE KEY-----fixture",
        ),
        (
            {"rpo_minutes": 15, "rto_minutes": 60, "ＰＡＳＳＷＯＲＤ": "fixture-value"},
            "fixture-value",
        ),
        (
            {
                "rpo_minutes": 15,
                "rto_minutes": 60,
                "notes": "password=fixture-credential-value",
            },
            "fixture-credential-value",
        ),
    ],
)
async def test_platform_configuration_rejects_recursive_secret_material_without_echo(
    app: FastAPI,
    client: Any,
    value: dict[str, Any],
    submitted_secret: str,
) -> None:
    response = await client.post(
        "/api/v1/platform/configurations",
        headers={"Idempotency-Key": "secret-rejection-config-001"},
        json={
            "configuration_key": "backup_policy",
            "value": value,
            "expected_revision": 0,
            "reason": "exercise the platform configuration safety boundary",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert submitted_secret not in response.text

    async with app.state.session_factory() as session:
        revision_count = int(
            await session.scalar(select(func.count()).select_from(PlatformConfigurationRevision))
            or 0
        )
        event_count = int(
            await session.scalar(
                select(func.count())
                .select_from(DomainEvent)
                .where(DomainEvent.event_type == "platform.configuration.activated")
            )
            or 0
        )
    assert revision_count == 0
    assert event_count == 0


@pytest.mark.asyncio
async def test_platform_configuration_schemas_are_strict_versioned_and_bounded(
    app: FastAPI,
    client: Any,
) -> None:
    valid_values: dict[str, tuple[dict[str, Any], str | None]] = {
        "scada_retention": (
            {"days": 365, "downsample_after_days": 30},
            None,
        ),
        "event_stream": (
            {"schema_version": 1, "transport": "sse", "max_batch_size": 200},
            None,
        ),
        "identity": (
            {
                "schema_version": 1,
                "issuer": "https://identity.example.com",
                "audience": "windops",
            },
            "vault://openvigil/identity/client",
        ),
        "model_governance": (
            {
                "schema_version": 1,
                "approval_required": True,
                "evaluation": {
                    "schema_version": 1,
                    "minimum_validation_auc": 0.82,
                    "minimum_evaluation_samples": 100,
                },
            },
            None,
        ),
        "backup_policy": (
            {"schema_version": 1, "rpo_minutes": 15, "rto_minutes": 60},
            None,
        ),
    }
    for key, (value, secret_reference) in valid_values.items():
        response = await client.post(
            "/api/v1/platform/configurations",
            headers={"Idempotency-Key": f"valid-config-{key}-001"},
            json={
                "configuration_key": key,
                "value": value,
                "secret_reference": secret_reference,
                "expected_revision": 0,
                "reason": f"activate the approved {key} version one policy",
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["schema_version"] == 1
        assert response.json()["value"]["schema_version"] == 1
        assert "vault://" not in response.text

    invalid_requests = [
        {
            "configuration_key": "backup_policy",
            "value": {"rpo_minutes": 15, "rto_minutes": 60, "unknown": True},
            "secret_reference": None,
        },
        {
            "configuration_key": "backup_policy",
            "value": {"rpo_minutes": True, "rto_minutes": 60},
            "secret_reference": None,
        },
        {
            "configuration_key": "model_governance",
            "value": {"schema_version": 1, "approval_required": True},
            "secret_reference": None,
        },
        {
            "configuration_key": "identity",
            "value": {
                "schema_version": 1,
                "issuer": "https://identity.example.com",
                "audience": "windops",
            },
            "secret_reference": "vault://user:password@windops/identity/client",
        },
        {
            "configuration_key": "event_stream",
            "value": {
                "schema_version": 1,
                "transport": "kafka",
                "topic": "windops-events",
            },
            "secret_reference": None,
        },
        {
            "configuration_key": "backup_policy",
            "value": {"rpo_minutes": 15, "rto_minutes": 60, "padding": "x" * 17_000},
            "secret_reference": None,
        },
    ]
    for index, invalid in enumerate(invalid_requests):
        response = await client.post(
            "/api/v1/platform/configurations",
            headers={"Idempotency-Key": f"invalid-config-{index}-001"},
            json={
                **invalid,
                "expected_revision": 1,
                "reason": f"invalid schema regression case {index}",
            },
        )
        assert response.status_code == 422

    async with app.state.session_factory() as session:
        stored = list((await session.scalars(select(PlatformConfigurationRevision))).all())
        events = list(
            (
                await session.scalars(
                    select(DomainEvent).where(
                        DomainEvent.event_type == "platform.configuration.activated"
                    )
                )
            ).all()
        )
    assert len(stored) == len(valid_values)
    assert all(row.value["schema_version"] == 1 for row in stored)
    serialized_storage = json.dumps(
        [
            {
                "value": row.value,
                "reason": row.reason,
                "secret_reference": row.secret_reference,
            }
            for row in stored
        ]
    )
    assert "audit-secret-value" not in serialized_storage
    assert all("secret_reference" not in event.payload for event in events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_reference",
    [
        "vault://user:password@windops/source",
        "vault://openvigil/source?version=latest",
        "vault://openvigil/source#fragment",
        "vault://openvigil/%2e%2e/other",
        "vault://openvigil/%252e%252e/other",
        "vault://user%3Apassword@windops/source",
        "vault://openvigil/source%3Fpassword%3Dfixture",
        "vault://openvigil/source%253Fpassword%253Dfixture",
    ],
)
async def test_ingest_source_secret_reference_uses_the_strict_secret_manager_validator(
    app: FastAPI,
    client: Any,
    unsafe_reference: str,
) -> None:
    source_id = f"unsafe-source-{abs(hash(unsafe_reference)) % 1_000_000:06d}"
    response = await client.post(
        "/api/v1/platform/data-sources",
        headers={"Idempotency-Key": "reject-source-credential-001"},
        json={
            "source_id": source_id,
            "display_name": "Unsafe source fixture",
            "source_kind": "opcua",
            "secret_reference": unsafe_reference,
            "reason": "exercise the source credential safety boundary",
        },
    )
    assert response.status_code == 422
    assert unsafe_reference not in response.text
    async with app.state.session_factory() as session:
        assert await session.get(IngestSource, source_id) is None


@pytest.mark.asyncio
async def test_legacy_ingest_source_credentials_are_quarantined_with_secret_free_evidence(
    app: FastAPI,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        session.add(
            IngestSource(
                id="legacy-unsafe-source",
                display_name="Legacy unsafe source",
                source_kind="opcua",
                enabled=True,
                policy={},
                credential_secret_reference="vault://legacy-user:legacy-password@windops/source",
            )
        )

    async with app.state.session_factory() as session, session.begin():
        assert await remediate_ingest_source_credentials(session) == 1

    async with app.state.session_factory() as session:
        source = await session.get(IngestSource, "legacy-unsafe-source")
        assert source is not None
        assert source.credential_secret_reference is None
        assert source.enabled is False
        assert source.status == "quarantined"
        assert await unresolved_platform_configuration_rotations(session) == 1


@pytest.mark.asyncio
async def test_ingest_source_rotation_confirmation_closes_audit_without_echoing_reference(
    app: FastAPI,
    client: Any,
) -> None:
    source_id = "source-rotation-001"
    audit_id = "source-rotation-audit-001"
    async with app.state.session_factory() as session, session.begin():
        session.add(
            IngestSource(
                id=source_id,
                display_name="Source requiring rotation",
                source_kind="opcua",
                enabled=False,
                status="quarantined",
                policy={},
            )
        )
        session.add(
            IngestSourceSecurityAudit(
                id=audit_id,
                source_id=source_id,
                finding_categories=["invalid_secret_reference"],
                original_fingerprint="b" * 64,
                action="quarantined_and_redacted",
                rotation_required=True,
            )
        )

    pending = await client.get("/api/v1/platform/configurations")
    assert pending.status_code == 200
    assert pending.json()["meta"]["pending_credential_rotations"] == 1
    confirmed = await client.post(
        f"/api/v1/platform/data-source-security-audits/{audit_id}/rotation-confirmation",
        headers={"Idempotency-Key": "source-rotation-confirm-001"},
        json={
            "replacement_secret_reference": "vault://openvigil/source/rotated",
            "rotation_evidence": "CHG-SOURCE-ROTATION-001 completed and revoked",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert "vault://" not in confirmed.text
    async with app.state.session_factory() as session:
        source = await session.get(IngestSource, source_id)
        audit = await session.get(IngestSourceSecurityAudit, audit_id)
        assert source is not None and source.enabled is True
        assert audit is not None and audit.rotation_required is False
        assert await unresolved_platform_configuration_rotations(session) == 0


@pytest.mark.asyncio
async def test_full_platform_configuration_is_manager_only_with_redacted_status(
    client: Any,
) -> None:
    created = await client.post(
        "/api/v1/platform/configurations",
        headers={"Idempotency-Key": "manager-only-config-001"},
        json={
            "configuration_key": "backup_policy",
            "value": {"rpo_minutes": 15, "rto_minutes": 60},
            "expected_revision": 0,
            "reason": "activate the approved recovery objectives",
        },
    )
    assert created.status_code == 201

    field_headers = _scoped_headers("field_technician", allow_global=True)
    forbidden = await client.get(
        "/api/v1/platform/configurations",
        headers=field_headers,
    )
    assert forbidden.status_code == 403

    scoped_manager = await client.get(
        "/api/v1/platform/configurations",
        headers=_scoped_headers("operations_manager"),
    )
    assert scoped_manager.status_code == 403
    assert scoped_manager.json()["error"]["code"] == "GLOBAL_SCOPE_REQUIRED"

    status = await client.get(
        "/api/v1/platform/configuration-status",
        headers=_scoped_headers("field_technician"),
    )
    assert status.status_code == 200, status.text
    assert status.json()["meta"]["redacted"] is True
    assert status.json()["data"]["configured_keys"] == ["backup_policy"]
    assert "value" not in status.text
    assert "created_by" not in status.text


@pytest.mark.asyncio
async def test_historical_secret_is_redacted_audited_and_requires_rotation(
    app: FastAPI,
    client: Any,
) -> None:
    submitted_secret = "historical-fixture-credential"
    revision_id = "h001-historical-revision"
    async with app.state.session_factory() as session, session.begin():
        session.add(
            PlatformConfigurationRevision(
                id=revision_id,
                configuration_key="backup_policy",
                revision=1,
                value={
                    "rpo_minutes": 15,
                    "rto_minutes": 60,
                    "nested": {"Connection-String": f"password={submitted_secret}"},
                },
                secret_reference=None,
                reason="legacy row imported before strict schema enforcement",
                created_by="legacy-import",
            )
        )

    async with app.state.session_factory() as session, session.begin():
        assert await remediate_platform_configuration_history(session) == 1

    async with app.state.session_factory() as session:
        revision = await session.get(PlatformConfigurationRevision, revision_id)
        audit = await session.scalar(
            select(PlatformConfigurationSecurityAudit).where(
                PlatformConfigurationSecurityAudit.configuration_id == revision_id
            )
        )
        assert revision is not None
        assert audit is not None
        assert revision.value == {}
        assert revision.secret_reference is None
        assert revision.active is False
        assert revision.security_status == "quarantined_rotation_required"
        assert audit.rotation_required is True
        assert audit.action == "quarantined_and_redacted"
        assert await unresolved_platform_configuration_rotations(session) == 1
        persisted = json.dumps(
            {
                "revision": revision.value,
                "reason": revision.reason,
                "audit": {
                    "categories": audit.finding_categories,
                    "fingerprint": audit.original_fingerprint,
                    "action": audit.action,
                },
            }
        )
        audit_id = audit.id
    assert submitted_secret not in persisted

    manager_view = await client.get("/api/v1/platform/configurations")
    assert manager_view.status_code == 200
    assert submitted_secret not in manager_view.text
    assert manager_view.json()["meta"]["pending_credential_rotations"] == 1

    status = await client.get(
        "/api/v1/platform/configuration-status",
        headers=_scoped_headers("field_technician"),
    )
    assert status.status_code == 200
    assert status.json()["data"]["status"] == "attention_required"
    assert status.json()["data"]["pending_credential_rotations"] == 1

    app.state.settings.environment = Environment.PRODUCTION
    not_ready = await client.get("/api/v1/readyz")
    app.state.settings.environment = Environment.TEST
    assert not_ready.status_code == 503
    assert not_ready.json()["error"]["code"] == "CONFIGURATION_SECURITY_REMEDIATION_REQUIRED"

    confirmed = await client.post(
        f"/api/v1/platform/configuration-security-audits/{audit_id}/rotation-confirmation",
        headers={"Idempotency-Key": "rotation-confirmation-001"},
        json={
            "replacement_secret_reference": "vault://openvigil/platform/rotated-credential",
            "rotation_evidence": "CHG-2026-0819 credential revoked and replacement activated",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["rotation_required"] is False
    assert "vault://" not in confirmed.text
    assert submitted_secret not in confirmed.text

    async with app.state.session_factory() as session:
        assert await unresolved_platform_configuration_rotations(session) == 0
        rotation_event = await session.scalar(
            select(DomainEvent).where(
                DomainEvent.event_type == "platform.configuration.credential_rotation_confirmed"
            )
        )
    assert rotation_event is not None
    assert submitted_secret not in json.dumps(rotation_event.payload)
    assert "vault://" not in json.dumps(rotation_event.payload)
