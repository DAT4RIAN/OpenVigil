"""Create an ephemeral owned dependency stack and run real business browser tests."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import httpx
import yaml  # type: ignore[import-untyped]  # PyYAML has no bundled typing metadata.
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from minio import Minio

from windops_backend.operations.hybrid_identity import hybrid_bundle_id

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def signal_owned_process_group(pid: int) -> None:
    if os.name == "nt":
        raise RuntimeError("Windows child cleanup requires taskkill")
    # Windows type stubs omit this POSIX API; resolve it only in the POSIX branch.
    method_name = "killpg"
    signal_group = cast(Callable[[int, int], None], getattr(os, method_name))
    signal_group(pid, signal.SIGTERM)


def available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def certificate(folder: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OpenVigil local E2E only")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = folder / "cert.pem", folder / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


def compose_definition(password: str) -> dict[str, Any]:
    parsed = yaml.safe_load((BACKEND / "docker-compose.yml").read_text())
    if not isinstance(parsed, dict):
        raise RuntimeError("Business E2E Compose configuration must be an object")
    source = cast(dict[str, Any], parsed)
    source["services"].pop("minio-init")
    services = source["services"]
    for service, ports in {
        "postgres": [5432],
        "redis": [6379],
        "minio": [9000],
        "neo4j": [7687],
    }.items():
        services[service]["ports"] = [f"127.0.0.1::{port}" for port in ports]
    services["postgres"]["environment"]["POSTGRES_PASSWORD"] = password
    services["minio"]["environment"]["MINIO_ROOT_PASSWORD"] = password
    services["neo4j"]["environment"]["NEO4J_AUTH"] = f"neo4j/{password}"
    services["neo4j"]["healthcheck"]["test"] = [
        "CMD-SHELL",
        'cypher-shell -u neo4j -p "$${NEO4J_AUTH#*/}" "RETURN 1" || exit 1',
    ]
    return source


async def database_evidence(config: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from windops_backend.models import (
        Approval,
        KnowledgeCase,
        Mission,
        ReadAccessAudit,
        WorkOrder,
        WorkOrderTask,
    )
    from windops_backend.storage import FieldTaskEvidence

    engine = create_async_engine(config["database_url"])
    factory = async_sessionmaker(engine)
    try:
        async with factory() as session:
            counts = {
                model.__tablename__: int(
                    await session.scalar(select(func.count()).select_from(model)) or 0
                )
                for model in (
                    Approval,
                    KnowledgeCase,
                    Mission,
                    WorkOrder,
                    WorkOrderTask,
                    FieldTaskEvidence,
                )
            }
            expected = {
                "approvals": 1,
                "knowledge_cases": 1,
                "missions": 1,
                "work_orders": 1,
                "work_order_tasks": 5,
                "field_task_evidence": 5,
            }
            if counts != expected:
                raise RuntimeError(
                    "Persisted workflow counts differ from the single closure contract"
                )
            for _ in range(30):
                audit_count = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ReadAccessAudit)
                        .where(ReadAccessAudit.subject == "business-field")
                    )
                    or 0
                )
                if audit_count:
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Read-audit worker did not persist field-user reads")
            evidence = list(await session.scalars(select(FieldTaskEvidence)))
            return {
                "counts": counts,
                "field_read_audits": audit_count,
                "artifacts": [
                    {"uri": row.artifact_uri, "sha256": row.artifact_sha256} for row in evidence
                ],
            }
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("maintenance", "structural", "structural-modal", "structural-scope", "document"),
        default="maintenance",
    )
    parser.add_argument("--document-python", type=Path)
    parser.add_argument("--document-models", type=Path)
    parser.add_argument("--document-fixture", type=Path)
    arguments = parser.parse_args()
    scenario = arguments.scenario
    structural = scenario in {"structural", "structural-modal", "structural-scope"}
    document = scenario == "document"
    if document:
        for name in ("document_python", "document_models", "document_fixture"):
            path = getattr(arguments, name)
            if path is None or not path.resolve().is_relative_to(ROOT / ".artifacts"):
                parser.error("Document acceptance inputs must exist in this checkout's .artifacts")
            if not path.exists():
                parser.error("A required document acceptance input is missing")
    run_id = f"{datetime.now(UTC):%Y%m%d%H%M%S}-{secrets.token_hex(3)}"
    project = f"openvigil-business-e2e-{run_id}"
    folder = ROOT / ".artifacts/business-e2e" / run_id
    folder.mkdir(parents=True)
    report: dict[str, Any] = {
        "schema": "openvigil.business-e2e.v1",
        "project": project,
        "passed": False,
        "cleanup_passed": False,
        "scenario": scenario,
        "boundary": (
            "Real Worker/FastAPI/PostgreSQL/Redis/MinIO/Neo4j and asynchronous workers; "
            "synthetic observations, deterministic diagnosis and embeddings, "
            "fixture identity provider/release. "
            "Not production release acceptance."
        ),
    }
    protected_env = ROOT / ".env"
    protected_env_sha = (
        hashlib.sha256(protected_env.read_bytes()).hexdigest() if protected_env.exists() else None
    )
    staged_sha = hashlib.sha256(
        subprocess.check_output(["git", "diff", "--cached", "--binary"], cwd=ROOT)
    ).hexdigest()
    report["source_sha256"] = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in (
            "backend/scripts/run_business_e2e.py",
            "backend/scripts/business_e2e_runtime.py",
            "backend/src/windops_backend/services/workflow.py",
            "backend/src/windops_backend/agents/tools.py",
            "backend/src/windops_backend/api/knowledge.py",
            "backend/src/windops_backend/services/knowledge_access.py",
            "worker/index.ts",
            "lib/artifact-upload-policy.ts",
            "lib/worker-env.ts",
            "lib/production-runtime.ts",
            "tests/production-runtime.test.mjs",
            "components/pages/knowledge-graph-page.tsx",
            "dist/server/index.js",
            "tests/e2e/business-cross-layer.spec.ts",
            "scripts/e2e-production-server.mjs",
            "playwright.config.ts",
            "backend/scripts/structural_e2e_evidence.py",
            "tests/e2e/structural-cross-layer.spec.ts",
            "tests/e2e/structural-modal-cross-layer.spec.ts",
            "tests/e2e/structural-real-support.ts",
            "backend/scripts/structural_scope_evidence.py",
            "tests/e2e/structural-scope-cross-layer.spec.ts",
        )
    }
    if structural or document:
        report["backend_source_sha256"] = {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (BACKEND / "src").rglob("*.py")
        }
    if document:
        for name in (
            "backend/scripts/document_e2e_evidence.py",
            "tests/e2e/document-cross-layer.spec.ts",
            "components/pages/knowledge-base-page.tsx",
            "components/pages/knowledge-source-viewer.tsx",
            "lib/knowledge-source.ts",
            "lib/structural-artifact-command.ts",
        ):
            report["source_sha256"][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    env = {key: value for key, value in os.environ.items() if not key.startswith("WINDOPS_")}
    env.pop("NODE_TLS_REJECT_UNAUTHORIZED", None)
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND / "src"), str(BACKEND / "scripts")])
    env["WINDOPS_ENVIRONMENT"] = "test"
    env["WINDOPS_AGENT_MODE"] = "deterministic"
    password = secrets.token_hex(24)
    compose = folder / "compose.json"
    compose.write_text(json.dumps(compose_definition(password)))
    docker = ["docker", "compose", "--project-name", project, "--file", str(compose)]
    children: list[subprocess.Popen[bytes]] = []
    logs: list[Any] = []
    stopped_workers: set[int] = set()
    structural_worker: subprocess.Popen[bytes] | None = None
    challenges: Any = None
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def run(args: list[str], log_name: str, *, cwd: Path = ROOT, timeout: int = 300) -> None:
        with (folder / log_name).open("ab") as output:
            subprocess.run(
                args,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=True,
                creationflags=creationflags,
            )

    def start(
        args: list[str],
        log_name: str,
        *,
        cwd: Path = BACKEND,
        process_env: dict[str, str] | None = None,
    ) -> subprocess.Popen[bytes]:
        output = (folder / log_name).open("wb")
        logs.append(output)
        children.append(
            subprocess.Popen(
                args,
                cwd=cwd,
                env={**env, **(process_env or {})},
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=os.name != "nt",
                creationflags=creationflags,
            )
        )
        return children[-1]

    def start_structural_worker() -> None:
        nonlocal structural_worker
        if structural_worker is not None and structural_worker.poll() is None:
            raise RuntimeError("Structural worker is already running")
        structural_worker = start(
            [sys.executable, str(BACKEND / "scripts/business_e2e_runtime.py"), "structural-worker"]
            if os.name == "nt" and scenario == "structural-scope"
            else [
                sys.executable,
                "-m",
                "dramatiq",
                "business_e2e_runtime",
                "--queues",
                "structural-analysis",
                "--processes",
                "1",
                "--threads",
                "1",
            ],
            f"structural-worker-{len(stopped_workers)}.log",
            process_env={"WINDOPS_E2E_PROCESS_KIND": "structural"},
        )

    def stop_structural_worker() -> None:
        if structural_worker is None or structural_worker.poll() is not None:
            raise RuntimeError("Expected the owned structural worker to be running")
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(structural_worker.pid), "/T", "/F"],
                check=True,
                capture_output=True,
                creationflags=creationflags,
            )
        else:
            signal_owned_process_group(structural_worker.pid)
        structural_worker.wait(timeout=15)
        stopped_workers.add(structural_worker.pid)

    try:
        report["commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        report["worktree_dirty"] = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                text=True,
            ).strip()
        )
        print(f"Business E2E evidence: {folder}", flush=True)
        run(docker + ["up", "-d", "--wait", "--wait-timeout", "180"], "dependencies.log")
        ports = {}
        for service, internal in (
            ("postgres", 5432),
            ("redis", 6379),
            ("minio", 9000),
            ("neo4j", 7687),
        ):
            address = subprocess.check_output(
                docker + ["port", service, str(internal)],
                env=env,
                text=True,
                creationflags=creationflags,
            ).strip()
            if not address.startswith("127.0.0.1:"):
                raise RuntimeError("Dependency published outside loopback")
            ports[service] = int(address.split(":")[-1])
        api_port, web_port = available_port(), available_port()
        report["loopback_ports"] = {**ports, "api": api_port, "frontend": web_port}
        cert, key = certificate(folder)
        scopes = {
            subject: {"data_scopes": ["*"], "turbine_ids": ["WT-023"], "allow_global": True}
            for subject in (
                "business-manager",
                "business-approver",
                "business-field",
                "business-reviewer",
                "business-case-reviewer",
                "ingest-source:business-e2e",
            )
        }
        scopes["business-restricted"] = {"data_scopes": ["*"], "turbine_ids": ["WT-NOT-OWNED"]}
        config = {
            "fixture": "openvigil.business-e2e.v1",
            "environment": "test",
            "database_url": f"postgresql+asyncpg://windops:{password}@127.0.0.1:{ports['postgres']}/windops",
            "redis_url": f"redis://127.0.0.1:{ports['redis']}/0",
            "minio_endpoint": f"127.0.0.1:{ports['minio']}",
            "minio_public_base": f"http://127.0.0.1:{ports['minio']}",
            "minio_access_key": "windops",
            "minio_secret_key": password,
            "minio_secure": False,
            "neo4j_uri": f"neo4j://127.0.0.1:{ports['neo4j']}",
            "neo4j_user": "neo4j",
            "neo4j_password": password,
            "knowledge_graph_backend": "neo4j",
            "schema_bootstrap": False,
            "demo_seed": True,
            "agent_mode": "deterministic",
            "outbox_inline_drain": False,
            "test_auth_bypass_enabled": False,
            "auth_mode": "sites_delegation",
            "gateway_delegation_secret": secrets.token_hex(32),
            "identity_role_mappings": {
                "business-manager": ["operations_manager"],
                "business-approver": ["operations_approver"],
                "business-field": ["field_technician"],
                "business-restricted": ["operations_approver"],
                "business-reviewer": ["maintenance_reviewer"],
                "business-case-reviewer": ["maintenance_reviewer"],
            },
            "identity_scope_mappings": scopes,
            "ingest_source_api_keys": {"business-e2e": secrets.token_hex(32)},
            "telemetry_source_policies": {
                "business-e2e": {
                    "display_name": "Synthetic E2E source",
                    "source_kind": "rest",
                    "sequence_required": False,
                    "allowed_turbines": ["WT-023"],
                }
            },
            "release_id": f"business-e2e-{run_id}",
            "release_commit_sha": report["commit"],
            "release_image_digest": "sha256:" + "b" * 64,
            "bind_host": "127.0.0.1",
            "trusted_hosts": ["127.0.0.1", "localhost"],
        }
        config_path = folder / "settings.json"
        if document:
            models = arguments.document_models.resolve()
            config.update(
                document_parser_enabled=True,
                document_parser_python=str(arguments.document_python.resolve()),
                document_parser_models_path=str(models),
                document_parser_model_manifest_sha256=hashlib.sha256(
                    (models / "openvigil-model-manifest.json").read_bytes()
                ).hexdigest(),
                document_parser_runtime_directory=str(folder),
            )
            env["WINDOPS_E2E_DOCUMENT"] = "1"
            env["WINDOPS_E2E_DOCUMENT_FIXTURE"] = str(arguments.document_fixture.resolve())
            env["WINDOPS_E2E_DOCUMENT_RECEIPT"] = str(folder / "document-browser.json")
            env["PLAYWRIGHT_JUNIT_OUTPUT_FILE"] = str(folder / "browser.xml")
        if structural:
            # Explicit release fixtures exercise software binding; these are not
            # observed image identities or a formal signed release qualification.
            config.update(
                api_image_digest=config["release_image_digest"],
                structural_image_digest="sha256:" + "c" * 64,
            )
            config["release_bundle_id"] = hybrid_bundle_id(
                config["release_id"],
                report["commit"],
                config["api_image_digest"],
                config["structural_image_digest"],
            )
        config_path.write_text(json.dumps(config))
        if structural:
            from structural_e2e_evidence import seed_structural_equipment

            env["WINDOPS_E2E_STRUCTURAL_RECEIPT"] = str(folder / "structural-browser.json")
            env["WINDOPS_E2E_STRUCTURAL"] = "1"
            if scenario == "structural-modal":
                env["WINDOPS_E2E_STRUCTURAL_MODAL"] = "1"
            if scenario == "structural-scope":
                env["WINDOPS_E2E_STRUCTURAL_SCOPE"] = "1"
                env["WINDOPS_E2E_CHALLENGE_FOLDER"] = str(folder)
            env["PLAYWRIGHT_JUNIT_OUTPUT_FILE"] = str(folder / "browser.xml")
        env.update(
            {
                "WINDOPS_DATABASE_URL": config["database_url"],
                "WINDOPS_BUSINESS_E2E": "1",
                "WINDOPS_BUSINESS_E2E_CONFIG": str(config_path),
                "WINDOPS_BUSINESS_E2E_API_PORT": str(api_port),
                "WINDOPS_ARTIFACT_UPLOAD_ORIGINS": config["minio_public_base"],
                "WINDOPS_BUSINESS_E2E_INGEST_KEY": config["ingest_source_api_keys"]["business-e2e"],
                "WINDOPS_BUSINESS_E2E_TLS_CERT": str(cert),
                "WINDOPS_BUSINESS_E2E_TLS_KEY": str(key),
                "WINDOPS_E2E_REAL_BACKEND": "1",
                "WINDOPS_E2E_PORT": str(web_port),
                "WINDOPS_E2E_BACKEND_ORIGIN": f"https://127.0.0.1:{api_port}",
                "WINDOPS_GATEWAY_DELEGATION_SECRET": config["gateway_delegation_secret"],
                "WINDOPS_E2E_RELEASE_ID": config["release_id"],
                "WINDOPS_E2E_COMMIT_SHA": report["commit"],
                "WINDOPS_E2E_IMAGE_DIGEST": config["release_image_digest"],
                "NODE_EXTRA_CA_CERTS": str(cert),
                "WINDOPS_FAIL_ON_SKIPPED": "1",
            }
        )
        run([sys.executable, "-m", "alembic", "upgrade", "head"], "migrations.log", cwd=BACKEND)
        if structural:
            asyncio.run(seed_structural_equipment(config))
        if scenario == "structural-scope":
            from structural_scope_evidence import seed_scope_topology

            fixture = asyncio.run(seed_scope_topology(config))
            (folder / "scope-fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
            for subject, entity, data_scope in (
                ("business-component", fixture["components"][0]["id"], "structural"),
                ("business-sensor", fixture["sensors"][0]["id"], "structural"),
                ("business-knowledge-only", fixture["components"][0]["id"], "knowledge"),
            ):
                scopes[subject] = {
                    "turbine_ids": ["WT-023"],
                    "entity_ids": [entity],
                    "data_scopes": [data_scope],
                    "allow_global": False,
                }
                config["identity_role_mappings"][subject] = ["maintenance_reviewer"]
            config_path.write_text(json.dumps(config))
        client = Minio(
            config["minio_endpoint"], access_key="windops", secret_key=password, secure=False
        )
        for suffix in (
            "field-evidence",
            "knowledge-documents",
            "model-artifacts",
            "twin-artifacts",
            "care-benchmarks",
        ):
            client.make_bucket(f"windops-{suffix}")
        script = str(BACKEND / "scripts/business_e2e_runtime.py")
        start([sys.executable, script, "api"], "api.log")
        with httpx.Client(verify=str(cert), timeout=3) as http:
            for _ in range(90):
                if any(child.poll() is not None for child in children):
                    raise RuntimeError("Business API exited during startup")
                try:
                    if http.get(f"https://127.0.0.1:{api_port}/api/v1/readyz").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Business API failed readiness")
        start(
            [
                sys.executable,
                "-m",
                "dramatiq",
                "business_e2e_runtime",
                "--processes",
                "1",
                "--threads",
                "1",
            ],
            "worker.log",
        )
        start([sys.executable, script, "relay"], "relay.log")
        start([sys.executable, script, "read-audit"], "read-audit.log")
        if structural:
            start_structural_worker()
        if document:
            start(
                [sys.executable, script, "document-worker"],
                "document-worker.log",
                process_env={"WINDOPS_E2E_PROCESS_KIND": "document"},
            )
        if scenario == "structural-scope":
            from structural_scope_evidence import OwnedInfrastructureChallenges

            challenges = OwnedInfrastructureChallenges(
                folder, docker, project, stop_structural_worker, start_structural_worker
            )
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Node is required")
        browser = start(
            [
                node,
                str(ROOT / "node_modules/@playwright/test/cli.js"),
                "test",
                {
                    "maintenance": "tests/e2e/business-cross-layer.spec.ts",
                    "structural": "tests/e2e/structural-cross-layer.spec.ts",
                    "structural-modal": "tests/e2e/structural-modal-cross-layer.spec.ts",
                    "structural-scope": "tests/e2e/structural-scope-cross-layer.spec.ts",
                    "document": "tests/e2e/document-cross-layer.spec.ts",
                }[scenario],
                "--retries=0",
                *(
                    ["--reporter=line,junit,./scripts/playwright-no-skips-reporter.mjs"]
                    if structural or document
                    else []
                ),
            ],
            "browser.log",
            cwd=ROOT,
        )
        if challenges is not None:
            deadline = time.monotonic() + 600
            while browser.poll() is None:
                challenges.handle_pending()
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired("structural scope browser", 600)
                time.sleep(0.2)
            browser_code = browser.returncode
        else:
            browser_code = browser.wait(
                timeout=1140
                if scenario == "structural-modal"
                else (600 if structural or document else 360)
            )
        if browser_code:
            raise subprocess.CalledProcessError(browser_code, "business browser tests")
        if any(
            child is not browser and child.poll() is not None and child.pid not in stopped_workers
            for child in children
        ):
            raise RuntimeError("A business service exited unexpectedly")
        if document:
            from document_e2e_evidence import document_database_evidence

            junit = ET.parse(folder / "browser.xml").getroot()
            if len(junit.findall(".//testcase")) != 1 or any(
                junit.findall(f".//{tag}") for tag in ("failure", "error", "skipped")
            ):
                raise RuntimeError("Document browser evidence must contain one successful test")
            report["database"] = asyncio.run(document_database_evidence(config, folder))
        elif structural:
            from structural_e2e_evidence import structural_database_evidence

            junit = ET.parse(folder / "browser.xml").getroot()
            assert len(junit.findall(".//testcase")) == 1
            assert not any(junit.findall(f".//{tag}") for tag in ("failure", "error", "skipped"))
            if scenario == "structural-scope":
                from structural_scope_evidence import scope_database_evidence

                report["database"] = asyncio.run(scope_database_evidence(config, folder))
            else:
                report["database"] = asyncio.run(structural_database_evidence(config, folder))
        else:
            report["database"] = asyncio.run(database_evidence(config))
        for artifact in report["database"]["artifacts"]:
            uri = urlparse(artifact["uri"])
            response = client.get_object(uri.netloc, uri.path.lstrip("/"))
            try:
                actual = hashlib.sha256(response.read()).hexdigest()
            finally:
                response.close()
                response.release_conn()
            if actual != artifact["sha256"]:
                raise RuntimeError("Persisted field evidence differs from the stored MinIO object")
        report["verified_minio_objects"] = len(report["database"]["artifacts"])
        for name, digest in {
            **report["source_sha256"],
            **report.get("backend_source_sha256", {}),
        }.items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError("Acceptance source changed while services were running")
        report["passed"] = True
        print("Real business browser tests passed", flush=True)
    except Exception as exc:
        report["error"] = type(exc).__name__
        report["error_frames"] = [
            {
                "file": Path(frame.filename).resolve().relative_to(ROOT).as_posix(),
                "line": frame.lineno,
                "function": frame.name,
            }
            for frame in traceback.extract_tb(exc.__traceback__)
            if Path(frame.filename).resolve().is_relative_to(ROOT)
        ]
        print(
            f"Business E2E failed ({type(exc).__name__}); inspect the private evidence folder",
            flush=True,
        )
    finally:
        cleanup_errors = []
        if challenges is not None:
            report["infrastructure_challenges"] = challenges.actions
            try:
                challenges.restore()
            except Exception as exc:
                cleanup_errors.append("challenge restore: " + type(exc).__name__)
        for child in reversed(children):
            try:
                if child.poll() is None:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=creationflags,
                        )
                    else:
                        signal_owned_process_group(child.pid)
                    child.wait(timeout=15)
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        for output in logs:
            output.close()
        report["owned_process_ids"] = [child.pid for child in children]
        browser_artifacts = ROOT / ".artifacts/playwright"
        if browser_artifacts.exists() and (folder / "browser.log").exists():
            try:
                shutil.copytree(browser_artifacts, folder / "playwright", dirs_exist_ok=True)
            except Exception as exc:
                report["evidence_copy_error"] = type(exc).__name__
                report["passed"] = False
        # Only this fresh random project and its synthetic test volumes are removed.
        # Saved local-development stacks, credentials and data volumes are untouched.
        try:
            run(docker + ["down", "--volumes", "--remove-orphans"], "cleanup.log")
            assert not subprocess.check_output(
                docker + ["ps", "--all", "--quiet"], env=env, creationflags=creationflags
            ).strip()
            assert all(child.poll() is not None for child in children)
            report["cleanup_passed"] = not cleanup_errors
        except Exception as exc:
            report["cleanup_error"] = type(exc).__name__
        report["finished_at"] = datetime.now(UTC).isoformat()
        report["process_cleanup_errors"] = cleanup_errors
        report["protected_env_unchanged"] = protected_env_sha == (
            hashlib.sha256(protected_env.read_bytes()).hexdigest()
            if protected_env.exists()
            else None
        )
        report["git_index_unchanged"] = (
            staged_sha
            == hashlib.sha256(
                subprocess.check_output(["git", "diff", "--cached", "--binary"], cwd=ROOT)
            ).hexdigest()
        )
        if not report["protected_env_unchanged"] or not report["git_index_unchanged"]:
            report["passed"] = False
        # The generated credentials belong only to this removed synthetic stack.
        # Preserve settings/log evidence without keeping usable credentials.
        for path in folder.glob("*.log"):
            content = path.read_text(encoding="utf-8", errors="replace")
            for value in (
                password,
                config.get("gateway_delegation_secret", "") if "config" in locals() else "",
            ):
                if value:
                    content = content.replace(value, "REDACTED")
            path.write_text(content, encoding="utf-8")
        compose.write_text(json.dumps(compose_definition("REDACTED")), encoding="utf-8")
        if "config_path" in locals():
            public_config = {
                **config,
                "database_url": "REDACTED",
                "minio_secret_key": "REDACTED",
                "neo4j_password": "REDACTED",
                "gateway_delegation_secret": "REDACTED",
                "ingest_source_api_keys": {"business-e2e": "REDACTED"},
            }
            config_path.write_text(json.dumps(public_config), encoding="utf-8")
        (folder / "report.json").write_text(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] and report["cleanup_passed"] else 1)


if __name__ == "__main__":
    main()
