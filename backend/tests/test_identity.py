import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest

from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.identity import (
    DelegatedIdentityAuthenticator,
    IdentityRoleError,
    InvalidIdentityError,
)
from windops_backend.main import create_app

SECRET = "test-delegation-secret-with-at-least-forty-eight-characters"


def identity_fixture() -> DelegatedIdentityAuthenticator:
    return DelegatedIdentityAuthenticator(
        secrets=(SECRET,),
        issuer="windops-sites-gateway",
        audience="windops-python-backend",
        role_mappings={
            "sites-user-42": ["field_technician", "operations_manager"],
        },
        clock_skew_seconds=15,
    )


def assertion(**overrides: Any) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "iss": "windops-sites-gateway",
        "aud": "windops-python-backend",
        "sub": "sites-user-42",
        "email": "technician@example.com",
        "iat": now,
        "exp": now + timedelta(seconds=60),
        "jti": "delegation-42",
        "method": "POST",
        "target": "/api/v1/work-orders/WO-42/tasks/TASK-7/complete",
        "body_sha256": "a" * 64,
    }
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def test_delegation_is_verified_request_bound_and_maps_multiple_roles() -> None:
    identity = identity_fixture().authenticate(
        assertion(),
        request_method="POST",
        request_target="/api/v1/work-orders/WO-42/tasks/TASK-7/complete",
        body_sha256="a" * 64,
    )
    assert identity.subject == "sites-user-42"
    assert identity.email == "technician@example.com"
    assert identity.roles == ("field_technician", "operations_manager")
    assert identity.delegation_id == "delegation-42"
    assert identity.expires_at > datetime.now(UTC)


def test_delegation_rejects_tampering_wrong_request_and_unassigned_users() -> None:
    authenticator = identity_fixture()
    with pytest.raises(InvalidIdentityError):
        authenticator.authenticate(
            f"{assertion()}tampered",
            request_method="POST",
            request_target="/api/v1/work-orders/WO-42/tasks/TASK-7/complete",
            body_sha256="a" * 64,
        )
    with pytest.raises(InvalidIdentityError):
        authenticator.authenticate(
            assertion(),
            request_method="POST",
            request_target="/api/v1/work-orders/WO-42/tasks/TASK-8/complete",
            body_sha256="a" * 64,
        )
    with pytest.raises(IdentityRoleError):
        authenticator.authenticate(
            assertion(sub="sites-user-without-role"),
            request_method="POST",
            request_target="/api/v1/work-orders/WO-42/tasks/TASK-7/complete",
            body_sha256="a" * 64,
        )


async def test_fastapi_accepts_only_a_delegation_bound_to_the_exact_request(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'identity.sqlite'}",
        schema_bootstrap=True,
        knowledge_graph_backend="memory",
        auth_mode="sites_delegation",
        gateway_delegation_secret=SECRET,
        identity_role_mappings={"sites-user-42": ["operations_manager"]},
    )
    app = create_app(settings)
    body = json.dumps(
        {
            "alarm_id": "ALARM-NOT-FOUND",
            "title": "Authorized mission request",
            "analysis_profile": {
                "component": "gearbox",
                "primary_variable": "gearbox_oil_temperature",
                "knowledge_query": "gearbox inspection",
            },
        },
        separators=(",", ":"),
    ).encode()
    body_hash = hashlib.sha256(body).hexdigest()
    target = "/api/v1/missions"
    token = assertion(method="POST", target=target, body_sha256=body_hash)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            authorized = await client.post(
                target,
                content=body,
                headers={
                    "authorization": f"Bearer {token}",
                    "content-type": "application/json",
                    "idempotency-key": "delegated-mission-001",
                },
            )
            assert authorized.status_code == 404
            assert authorized.json()["error"]["code"] == "NOT_FOUND"

            wrong_target_token = assertion(
                method="POST", target="/api/v1/resources", body_sha256=body_hash
            )
            wrong_target = await client.post(
                target,
                content=body,
                headers={
                    "authorization": f"Bearer {wrong_target_token}",
                    "content-type": "application/json",
                    "idempotency-key": "delegated-mission-002",
                },
            )
            assert wrong_target.status_code == 401
            assert wrong_target.json()["error"]["code"] == "UNAUTHENTICATED"
