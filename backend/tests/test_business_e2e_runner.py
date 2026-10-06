import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from cryptography import x509


def runner_module():
    path = Path(__file__).parents[1] / "scripts/run_business_e2e.py"
    spec = importlib.util.spec_from_file_location("business_e2e_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ephemeral_dependencies_have_no_external_volumes_or_fixed_ports() -> None:
    definition = runner_module().compose_definition("ephemeral-test-password")
    assert set(definition["services"]) == {"postgres", "redis", "minio", "neo4j"}
    assert all(value is None for value in definition["volumes"].values())
    for service in definition["services"].values():
        assert "@sha256:" in service["image"]
        assert all(port.startswith("127.0.0.1::") for port in service["ports"])
        assert "container_name" not in service
        for mount in service["volumes"]:
            assert mount.split(":")[0] in definition["volumes"]
    assert definition["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"] == (
        "ephemeral-test-password"
    )


def test_private_ca_is_only_valid_for_loopback(tmp_path: Path) -> None:
    cert_path, key_path = runner_module().certificate(tmp_path)
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert [str(value) for value in names.get_values_for_type(x509.IPAddress)] == ["127.0.0.1"]
    assert names.get_values_for_type(x509.DNSName) == []
    assert key_path.parent == tmp_path


@pytest.mark.parametrize("kind", ["general", "structural"])
@pytest.mark.parametrize("hybrid", [False, True])
def test_isolated_bootstrap_registers_only_its_own_broker_actors(kind: str, hybrid: bool) -> None:
    from windops_backend.operations.hybrid_identity import hybrid_bundle_id

    root = Path(__file__).resolve().parents[2]
    parent = root / ".artifacts/business-e2e"
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="broker-contract-", dir=parent) as directory:
        config_path = Path(directory) / "settings.json"
        config_path.write_text(
            json.dumps(
                {
                    "fixture": "openvigil.business-e2e.v1",
                    "environment": "test",
                    "agent_mode": "deterministic",
                    "database_url": "postgresql+asyncpg://unit:unit@127.0.0.1:1/unit",
                    "redis_url": "redis://127.0.0.1:2/0",
                    "neo4j_uri": "neo4j://127.0.0.1:3",
                    "minio_endpoint": "127.0.0.1:4",
                    "minio_public_base": "http://127.0.0.1:4",
                }
            ),
            encoding="utf-8",
        )
        if hybrid:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            raw.update(
                release_id="synthetic-broker-v1",
                release_commit_sha="a" * 40,
                release_image_digest="sha256:" + "b" * 64,
                api_image_digest="sha256:" + "b" * 64,
                structural_image_digest="sha256:" + "c" * 64,
            )
            raw["release_bundle_id"] = hybrid_bundle_id(
                raw["release_id"],
                raw["release_commit_sha"],
                raw["api_image_digest"],
                raw["structural_image_digest"],
            )
            config_path.write_text(json.dumps(raw), encoding="utf-8")
        env = {name: value for name, value in os.environ.items() if not name.startswith("WINDOPS_")}
        env.update(
            {
                "PYTHONPATH": os.pathsep.join(
                    [str(root / "backend/src"), str(root / "backend/scripts")]
                ),
                "WINDOPS_BUSINESS_E2E": "1",
                "WINDOPS_BUSINESS_E2E_CONFIG": str(config_path),
                "WINDOPS_E2E_PROCESS_KIND": kind,
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json,dramatiq,business_e2e_runtime; "
                "print(json.dumps({'actors': sorted(dramatiq.get_broker().actors), "
                "'own_digest': business_e2e_runtime.settings.release_image_digest}))",
            ],
            cwd=root / "backend",
            env=env,
            text=True,
            capture_output=True,
            timeout=60,
            check=True,
        )
        state = json.loads(result.stdout)
        actors = state["actors"]
        if hybrid:
            assert state["own_digest"] == "sha256:" + ("c" if kind == "structural" else "b") * 64
        if kind == "structural":
            assert actors == ["process_structural_analysis"]
        else:
            assert "process_mission_analysis" in actors
            assert "project_knowledge_graph" in actors
            assert "process_structural_analysis" not in actors
