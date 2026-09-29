import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from windops_backend.config import Settings
from windops_backend.security import ApiSecurityHeadersMiddleware


def local_config() -> dict:
    roles = [
        "operations_manager",
        "operations_approver",
        "maintenance_reviewer",
        "field_technician",
    ]
    return {
        "_env_file": None,
        "environment": "development",
        "local_acceptance": True,
        "release_id": "openvigil-local-test-rc1",
        "release_commit_sha": "a" * 40,
        "release_image_digest": "sha256:" + "b" * 64,
        "auth_mode": "sites_delegation",
        "gateway_delegation_secret": "test-only-local-gateway-secret-" + "x" * 48,
        "identity_role_mappings": {f"local-{role}": [role] for role in roles},
        "identity_scope_mappings": {f"local-{role}": {"turbine_ids": ["WT-023"]} for role in roles},
    }


def test_local_acceptance_is_explicit_and_scoped() -> None:
    settings = Settings(**local_config())
    assert settings.local_acceptance
    assert settings.environment.value == "development"
    assert not Settings(_env_file=None).local_acceptance


@pytest.mark.parametrize(
    "override",
    [
        {"environment": "production"},
        {"environment": "test"},
        {"release_commit_sha": ""},
        {"release_image_digest": "sha256:" + "0" * 64},
        {"release_id": "development"},
        {"auth_mode": "static_tokens"},
        {"gateway_delegation_secret": "dev-replace"},
        {"test_auth_bypass_enabled": True},
        {"identity_role_mappings": {}},
        {"identity_scope_mappings": {}},
    ],
)
def test_local_acceptance_rejects_incomplete_identity_and_bypasses(override: dict) -> None:
    with pytest.raises(ValidationError, match="local acceptance"):
        Settings(**{**local_config(), **override})


def test_local_acceptance_rejects_global_scope_and_combined_roles() -> None:
    config = local_config()
    config["identity_scope_mappings"]["local-operations_manager"] = {"tenant_ids": ["*"]}
    with pytest.raises(ValidationError, match="explicitly scoped"):
        Settings(**config)
    config = local_config()
    config["identity_role_mappings"]["local-operations_manager"].append("operations_approver")
    with pytest.raises(ValidationError, match="separate"):
        Settings(**config)


@pytest.mark.asyncio
@pytest.mark.parametrize("local", [False, True])
async def test_local_headers_are_opt_in_without_claiming_production(local: bool) -> None:
    app = FastAPI()

    @app.get("/")
    async def endpoint() -> dict:
        return {"ok": True}

    config = local_config()
    secured = ApiSecurityHeadersMiddleware(
        app,
        production=False,
        local_acceptance=local,
        release_id=config["release_id"],
        release_commit_sha=config["release_commit_sha"],
        release_image_digest=config["release_image_digest"],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=secured), base_url="https://test"
    ) as client:
        result = await client.get("/")
    assert result.status_code == 200
    assert (result.headers.get("x-windops-acceptance-scope") == "local") is local
    assert (result.headers.get("x-windops-release-id") == config["release_id"]) is local
    assert "strict-transport-security" not in result.headers
