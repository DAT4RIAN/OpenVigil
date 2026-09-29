"""Isolated business E2E process bootstrap; never a deployment entrypoint.

Uses real PostgreSQL/Redis/MinIO/Neo4j and the regular workers. Only reference
data, identity-provider headers, diagnosis and embedding models are test fixtures.
HTTP production branches are exercised with test-validated loopback settings, as in
the existing release smoke. Production configuration validation is unchanged.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import windops_backend.config as configuration
from windops_backend.config import Settings
from windops_backend.enums import Environment

ROOT = Path(__file__).resolve().parents[2]


def load_fixture_settings() -> Settings:
    if os.getenv("WINDOPS_BUSINESS_E2E") != "1":
        raise RuntimeError("Explicit isolated business E2E opt-in is required")
    path = Path(os.environ["WINDOPS_BUSINESS_E2E_CONFIG"]).resolve()
    if not path.is_relative_to(ROOT / ".artifacts/business-e2e"):
        raise RuntimeError("Fixture configuration must belong to this checkout")
    raw = json.loads(path.read_text())
    if raw.pop("fixture", None) != "openvigil.business-e2e.v1":
        raise RuntimeError("Missing fixture identity")
    for key in ("database_url", "redis_url", "neo4j_uri", "minio_public_base"):
        if urlparse(raw[key]).hostname != "127.0.0.1":
            raise RuntimeError("Business E2E dependencies must be isolated loopback services")
    if raw["minio_endpoint"] != urlparse(raw["minio_public_base"]).netloc:
        raise RuntimeError("Internal and public fixture object stores must be identical")
    if raw["environment"] != "test" or raw["agent_mode"] != "deterministic":
        raise RuntimeError("Only test-validated deterministic fixture settings are allowed")
    settings = Settings(_env_file=None, **raw)
    return settings


settings = load_fixture_settings()
if __name__ == "__main__" and sys.argv[1:] == ["api"]:
    # Only the HTTP process exercises production auth/storage/readiness branches.
    # Workers retain TEST mode for explicitly non-production embeddings; their
    # database, queue, graph store and event consumers remain real implementations.
    settings.environment = Environment.PRODUCTION
# Each spawned process imports this bootstrap before the regular worker module.
# No credentials or environment changes escape these test-owned processes.
configuration.get_settings = lambda: settings  # type: ignore[assignment]
from windops_backend import workers  # noqa: E402


def main() -> None:
    role = sys.argv[1]
    if role == "api":
        import uvicorn

        from windops_backend.main import create_app

        uvicorn.run(
            create_app(settings),
            host="127.0.0.1",
            port=int(os.environ["WINDOPS_BUSINESS_E2E_API_PORT"]),
            ssl_certfile=os.environ["WINDOPS_BUSINESS_E2E_TLS_CERT"],
            ssl_keyfile=os.environ["WINDOPS_BUSINESS_E2E_TLS_KEY"],
            log_level="warning",
        )
    elif role == "relay":
        workers.run_outbox_relay()
    elif role == "read-audit":
        from windops_backend.read_audit import run_read_audit_worker

        run_read_audit_worker()
    else:
        raise ValueError("Unknown fixture process role")


if __name__ == "__main__":
    main()
