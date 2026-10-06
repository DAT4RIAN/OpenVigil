"""Isolated business E2E process bootstrap; never a deployment entrypoint.

Uses real PostgreSQL/Redis/MinIO/Neo4j and the regular workers. Only reference
data, identity-provider headers, diagnosis and embedding models are test fixtures.
HTTP production branches are exercised with test-validated loopback settings, as in
the existing release smoke. Production configuration validation is unchanged.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
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
    if os.getenv("WINDOPS_E2E_PROCESS_KIND") == "structural" and raw.get("structural_image_digest"):
        raw["release_image_digest"] = raw["structural_image_digest"]
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
if os.getenv("WINDOPS_E2E_PROCESS_KIND") == "structural":
    # Each Dramatiq process owns one broker registry. Importing the general
    # actors first would replace their broker when structural_tasks is loaded.
    from windops_backend import structural_tasks  # noqa: E402, F401
else:
    from windops_backend import workers  # noqa: E402


def run_structural_worker() -> None:
    """Actual single-thread Dramatiq worker, without the Windows CLI supervisor."""
    if os.getenv("WINDOPS_E2E_PROCESS_KIND") != "structural":
        raise RuntimeError("Dedicated structural process identity is required")
    import dramatiq

    broker = dramatiq.get_broker()
    if set(broker.actors) != {"process_structural_analysis"}:
        raise RuntimeError("Dedicated structural actor registry is required")
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    # Dramatiq 1.18's public Worker/broker methods have no type annotations.
    broker.emit_after("process_boot")  # type: ignore[no-untyped-call]
    worker = dramatiq.Worker(  # type: ignore[no-untyped-call]
        broker, queues={"structural-analysis"}, worker_threads=1
    )
    worker.start()  # type: ignore[no-untyped-call]
    print("Owned structural Dramatiq worker started: processes=1 threads=1", flush=True)
    try:
        stopped.wait()
    finally:
        worker.stop(timeout=30_000)  # type: ignore[no-untyped-call]
        broker.close()  # type: ignore[no-untyped-call]


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
    elif role == "structural-worker":
        run_structural_worker()
    else:
        raise ValueError("Unknown fixture process role")


if __name__ == "__main__":
    main()
