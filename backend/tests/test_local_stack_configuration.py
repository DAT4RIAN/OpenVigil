from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "local_backend", PROJECT_ROOT / "scripts/local_backend.py"
)
assert spec and spec.loader
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    (tmp_path / "backend/deploy").mkdir(parents=True)
    shutil.copy(
        PROJECT_ROOT / "backend/docker-compose.yml", tmp_path / "backend/docker-compose.yml"
    )
    (tmp_path / ".env").write_text("DO_NOT_CHANGE=original\n")
    return tmp_path


def test_prepare_is_repeatable_and_preserves_user_config_and_credentials(checkout: Path) -> None:
    expected = local.prepare(checkout, 3000, 8000)
    folder = checkout / ".artifacts/local-stack"
    first = (folder / ".env.runtime").read_bytes()
    assert local.prepare(checkout, 3000, 8000) == expected
    assert (folder / ".env.runtime").read_bytes() == first
    assert (checkout / ".env").read_text() == "DO_NOT_CHANGE=original\n"
    values = dotenv_values(folder / ".env.runtime")
    assert values["WINDOPS_SCHEMA_BOOTSTRAP"] == "false"
    assert values["WINDOPS_AUTH_MODE"] == "static_tokens"
    assert values["WINDOPS_ENVIRONMENT"] == "development"
    compose_text = (folder / "compose.json").read_text()
    assert values["LOCAL_POSTGRES_PASSWORD"] not in compose_text
    compose = json.loads(compose_text)
    for service in compose["services"].values():
        assert all(port.startswith("127.0.0.1:") for port in service.get("ports", []))
    assert len(compose["volumes"]) == 4
    with pytest.raises(ValueError, match="original ports"):
        local.prepare(checkout, 3001, 8000)
    assert (folder / ".env.runtime").read_bytes() == first


def test_partial_setup_and_conflicting_ports_fail_without_overwriting(checkout: Path) -> None:
    with pytest.raises(ValueError, match="distinct"):
        local.prepare(checkout, 8000, 8000)
    folder = checkout / ".artifacts/local-stack"
    (folder / ".env.runtime").write_text("existing-secret")
    with pytest.raises(ValueError, match="Partial"):
        local.prepare(checkout, 3000, 8000)
    assert (folder / ".env.runtime").read_text() == "existing-secret"


def test_tampered_dependency_endpoint_is_rejected_before_service_start(
    checkout: Path, monkeypatch
) -> None:
    local.prepare(checkout, 3000, 8000)
    folder = checkout / ".artifacts/local-stack"
    monkeypatch.setattr(local, "ROOT", checkout)
    monkeypatch.setattr(local, "STATE_DIR", folder)
    # Preserve process environment because loading the isolated runtime replaces WINDOPS variables.
    monkeypatch.setattr(local.os, "environ", dict(local.os.environ))
    config = folder / ".env.runtime"
    config.write_text(config.read_text().replace("127.0.0.1:25432", "remote.example:5432"))
    with pytest.raises(ValueError, match="non-owned"):
        local.load_local_settings()
