"""Run the isolated HTTP backend used by the real Worker release smoke.

The smoke keeps PostgreSQL and the FastAPI application real while replacing only
Redis and MinIO with narrow readiness doubles.  It intentionally starts with
test-validated settings and then switches the runtime environment to production
after validation, so the local CI fixture cannot accidentally become a deployable
production configuration.
"""

from __future__ import annotations

import os

import uvicorn

import windops_backend.main as backend_main
from windops_backend.config import IdentityAccessScope, Settings
from windops_backend.enums import Environment

SUBJECT = os.getenv("WINDOPS_E2E_SUBJECT", "sites-release-manager")


def _gateway_delegation_secret() -> str:
    value = os.getenv("WINDOPS_GATEWAY_DELEGATION_SECRET", "").strip()
    if not value:
        raise RuntimeError(
            "WINDOPS_GATEWAY_DELEGATION_SECRET is required for the real cross-layer smoke"
        )
    return value


class _SmokeRedis:
    @classmethod
    def from_url(cls, *_args: object, **_kwargs: object) -> _SmokeRedis:
        return cls()

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class _SmokeMinio:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def bucket_exists(self, _bucket: str) -> bool:
        return True


def build_app():
    database_url = os.getenv("WINDOPS_DATABASE_URL", "").strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        raise RuntimeError("WINDOPS_DATABASE_URL must point to the isolated PostgreSQL service")
    backend_main.Redis = _SmokeRedis  # type: ignore[assignment]
    backend_main.Minio = _SmokeMinio  # type: ignore[assignment]
    settings = Settings(
        environment=Environment.TEST,
        database_url=database_url,
        schema_bootstrap=False,
        demo_seed=False,
        knowledge_graph_backend="memory",
        outbox_inline_drain=True,
        auth_mode="sites_delegation",
        gateway_delegation_secret=_gateway_delegation_secret(),
        identity_role_mappings={SUBJECT: ["operations_manager"]},
        identity_scope_mappings={
            SUBJECT: IdentityAccessScope(data_scopes=["platform"], allow_global=True)
        },
        release_id=os.getenv("WINDOPS_RELEASE_ID", "real-worker-release-smoke"),
        release_commit_sha=os.getenv("WINDOPS_RELEASE_COMMIT_SHA", "a" * 40),
        release_image_digest=os.getenv("WINDOPS_RELEASE_IMAGE_DIGEST", "sha256:" + "b" * 64),
        bind_host="127.0.0.1",
        trusted_hosts=["127.0.0.1", "localhost"],
    )
    # Exercise the production readiness/auth branches without relaxing the
    # production Settings validator for the real deployment configuration.
    settings.environment = Environment.PRODUCTION
    return backend_main.create_app(settings)


if __name__ == "__main__":
    app = build_app()
    port = int(os.getenv("WINDOPS_REAL_SMOKE_PORT", "8443"))
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        ssl_keyfile=os.environ["WINDOPS_REAL_SMOKE_TLS_KEY"],
        ssl_certfile=os.environ["WINDOPS_REAL_SMOKE_TLS_CERT"],
        log_level="warning",
    )
