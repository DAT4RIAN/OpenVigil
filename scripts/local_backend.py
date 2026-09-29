"""Project-owned development stack configuration, entrypoints and readiness checks.

Never reads or rewrites user dotenv files. This isolated stack deliberately uses
development/deterministic mode; it does not certify the production gateway.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".artifacts" / "local-stack"


class LocalStackError(ValueError):
    """Operator-safe diagnostics written by this module, without secret values."""


def prepare(root: Path, frontend_port: int, api_port: int) -> dict[str, object]:
    import yaml
    from dotenv import set_key

    folder = root / ".artifacts" / "local-stack"
    folder.mkdir(parents=True, exist_ok=True)
    metadata = folder / "configuration.json"
    project = (
        "openvigil-dev-" + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:10]
    )
    config = {
        "root": str(root.resolve()),
        "project": project,
        "frontend_port": frontend_port,
        "api_port": api_port,
        "dependency_ports": [25432, 26379, 29000, 29001, 27474, 27687],
    }
    if metadata.exists():
        if json.loads(metadata.read_text()) != config:
            raise LocalStackError(
                "Saved local-stack configuration differs; keep its original ports."
            )
        if not all((folder / f).is_file() for f in (".env.runtime", "compose.json")):
            raise LocalStackError(
                "Local configuration is incomplete; restore it before starting."
            )
        return config
    if any((folder / f).exists() for f in (".env.runtime", "compose.json")):
        raise LocalStackError(
            "Partial configuration found; inspect it rather than replacing credentials."
        )
    if len({frontend_port, api_port, *config["dependency_ports"]}) != 8:
        raise LocalStackError("Local service ports must be distinct")
    password = secrets.token_hex(24)
    values = {
        "WINDOPS_ENVIRONMENT": "development",
        "WINDOPS_DATABASE_URL": f"postgresql+asyncpg://windops:{password}@127.0.0.1:25432/windops",
        "WINDOPS_REDIS_URL": "redis://127.0.0.1:26379/0",
        "WINDOPS_MINIO_ENDPOINT": "127.0.0.1:29000",
        "WINDOPS_MINIO_PUBLIC_BASE": "http://127.0.0.1:29000",
        "WINDOPS_MINIO_ACCESS_KEY": "windops",
        "WINDOPS_MINIO_SECRET_KEY": secrets.token_hex(24),
        "WINDOPS_MINIO_SECURE": "false",
        "WINDOPS_NEO4J_URI": "neo4j://127.0.0.1:27687",
        "WINDOPS_NEO4J_USER": "neo4j",
        "WINDOPS_NEO4J_PASSWORD": secrets.token_hex(24),
        "WINDOPS_KNOWLEDGE_GRAPH_BACKEND": "neo4j",
        "WINDOPS_AGENT_MODE": "deterministic",
        "WINDOPS_AUTH_MODE": "static_tokens",
        "WINDOPS_SCHEMA_BOOTSTRAP": "false",
        "WINDOPS_DEMO_SEED": "false",
        "WINDOPS_OUTBOX_INLINE_DRAIN": "false",
        "LOCAL_POSTGRES_PASSWORD": password,
    }
    for role in (
        "operations_manager",
        "operations_approver",
        "maintenance_reviewer",
        "field_technician",
    ):
        values[f"WINDOPS_{role.upper()}_API_KEY"] = secrets.token_hex(24)
    compose = yaml.safe_load((root / "backend/docker-compose.yml").read_text())
    services = compose["services"]
    for name, ports in {
        "postgres": ["127.0.0.1:25432:5432"],
        "redis": ["127.0.0.1:26379:6379"],
        "minio": ["127.0.0.1:29000:9000", "127.0.0.1:29001:9001"],
        "neo4j": ["127.0.0.1:27474:7474", "127.0.0.1:27687:7687"],
    }.items():
        services[name]["ports"] = ports
    services["postgres"]["environment"]["POSTGRES_PASSWORD"] = (
        "${LOCAL_POSTGRES_PASSWORD:?required}"
    )
    services["minio"]["environment"]["MINIO_ROOT_PASSWORD"] = (
        "${WINDOPS_MINIO_SECRET_KEY:?required}"
    )
    services["neo4j"]["environment"]["NEO4J_AUTH"] = (
        "neo4j/${WINDOPS_NEO4J_PASSWORD:?required}"
    )
    services["neo4j"]["healthcheck"]["test"] = [
        "CMD-SHELL",
        'cypher-shell -u neo4j -p "$${NEO4J_AUTH#*/}" "RETURN 1" || exit 1',
    ]
    init = services["minio-init"]
    init["entrypoint"][-1] = init["entrypoint"][-1].replace(
        "windops change-me-now", 'windops "${WINDOPS_MINIO_SECRET_KEY:?required}"'
    )
    init["volumes"] = [
        f"{(root / 'backend/deploy/care-minio-lifecycle.json').as_posix()}:/config/care-minio-lifecycle.json:ro"
    ]
    for key, value in values.items():
        set_key(str(folder / ".env.runtime"), key, value)
    (folder / "compose.json").write_text(json.dumps(compose, indent=2))
    metadata.write_text(json.dumps(config, indent=2))
    return config


def load_local_settings():
    from dotenv import dotenv_values
    from windops_backend.config import Settings

    config = json.loads((STATE_DIR / "configuration.json").read_text())
    if config["root"] != str(ROOT.resolve()):
        raise LocalStackError("Local stack belongs to a different checkout")
    values = dotenv_values(STATE_DIR / ".env.runtime")
    # Explicit values control this isolated runtime; no root/backend dotenv fallthrough.
    for key in list(os.environ):
        if key.startswith("WINDOPS_"):
            del os.environ[key]
    os.environ.update({k: v for k, v in values.items() if v is not None})
    settings = Settings()
    if (
        settings.environment.value != "development"
        or not settings.database_url.startswith("postgresql+asyncpg://windops:")
        or "@127.0.0.1:25432/windops" not in settings.database_url
        or settings.redis_url != "redis://127.0.0.1:26379/0"
        or settings.minio_endpoint != "127.0.0.1:29000"
        or settings.neo4j_uri != "neo4j://127.0.0.1:27687"
    ):
        raise LocalStackError("Refusing non-owned dependency endpoints")
    from windops_backend.config import get_settings

    os.environ["WINDOPS_LOCAL_STACK"] = "1"
    get_settings.cache_clear()
    return settings, config


async def verify(settings, config) -> None:
    import httpx
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from minio import Minio
    from neo4j import AsyncGraphDatabase
    from redis.asyncio import Redis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            current = (
                (
                    await connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    )
                )
                .scalars()
                .all()
            )
        expected = ScriptDirectory.from_config(
            Config(str(ROOT / "backend/alembic.ini"))
        ).get_heads()
        if current != expected:
            raise LocalStackError("Local database migration head differs from source")
        redis = Redis.from_url(
            settings.redis_url, socket_connect_timeout=3, socket_timeout=3
        )
        try:
            if not await redis.ping():
                raise LocalStackError("Local Redis is not ready")
        finally:
            await redis.aclose()
        minio = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key.get_secret_value(),
            secure=False,
        )
        for bucket in (
            settings.minio_field_evidence_bucket,
            settings.minio_knowledge_bucket,
            settings.minio_model_bucket,
            settings.minio_twin_bucket,
            settings.minio_care_bucket,
        ):
            if not await asyncio.wait_for(
                asyncio.to_thread(minio.bucket_exists, bucket), timeout=5
            ):
                raise LocalStackError("Required local MinIO bucket is missing")
        audit_started = datetime.now(UTC)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{config['api_port']}", timeout=10
        ) as client:
            for route in ("healthz", "readyz", "catalog"):
                response = await client.get(
                    f"/api/v1/{route}",
                    headers={
                        "Authorization": f"Bearer {settings.operations_manager_api_key.get_secret_value()}"
                    },
                )
                response.raise_for_status()
            unauthorized = await client.get("/api/v1/catalog")
            if unauthorized.status_code != 401:
                raise LocalStackError("Unauthenticated catalog must return 401")
        async with AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        ) as driver:
            await driver.verify_connectivity()
        # Confirm the separately running read-audit consumer persisted the authenticated read.
        for _ in range(20):
            async with engine.connect() as connection:
                count = (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM read_access_audits WHERE accessed_at >= :started "
                            "AND endpoint = '/api/v1/catalog' AND subject = 'operations-manager'"
                        ),
                        {"started": audit_started},
                    )
                ).scalar_one()
            if count:
                break
            await asyncio.sleep(0.5)
        else:
            raise LocalStackError(
                "No durable read audit observed; inspect read-audit worker"
            )
    finally:
        await engine.dispose()
    print(
        "Verified migration, API readiness/auth, Neo4j and durable read audit (development only)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "role",
        choices=[
            "prepare",
            "migrate",
            "api",
            "worker",
            "relay",
            "read-audit",
            "verify",
        ],
    )
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--api-port", type=int, default=8000)
    args = parser.parse_args()
    if args.role == "prepare":
        if not all(
            1024 <= port <= 65535 for port in (args.frontend_port, args.api_port)
        ):
            raise LocalStackError("Ports must be in 1024..65535")
        prepare(ROOT, args.frontend_port, args.api_port)
        print(
            "Isolated local configuration is ready; existing dotenv files are unchanged."
        )
        return
    settings, config = load_local_settings()
    os.chdir(ROOT / "backend")
    if args.role == "migrate":
        from alembic.config import main as alembic_main

        alembic_main(argv=["upgrade", "head"])
    elif args.role == "api":
        import uvicorn
        from windops_backend.main import create_app

        uvicorn.run(create_app(settings), host="127.0.0.1", port=config["api_port"])
    elif args.role == "worker":
        from dramatiq.cli import main as dramatiq_main

        sys.argv = [
            "dramatiq",
            "windops_backend.workers",
            "--processes",
            "1",
            "--threads",
            "4",
        ]
        raise SystemExit(dramatiq_main())
    elif args.role == "relay":
        from windops_backend.workers import run_outbox_relay

        run_outbox_relay()
    elif args.role == "read-audit":
        from windops_backend.read_audit import run_read_audit_worker

        run_read_audit_worker()
    else:
        asyncio.run(verify(settings, config))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 -- CLI boundary exits nonzero, never reports success
        # Connection errors may embed a URL with credentials. Keep details in local logs only.
        print(
            str(error)
            if isinstance(error, LocalStackError)
            else f"Local stack operation failed ({type(error).__name__}); inspect private service logs.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
