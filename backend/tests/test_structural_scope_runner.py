"""Infrastructure challenges cannot address a foreign compose project."""

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from windops_backend.models import SensorChannel, TowerComponent


def controller_module():
    path = Path(__file__).parents[1] / "scripts/structural_scope_evidence.py"
    spec = importlib.util.spec_from_file_location("structural_scope_evidence", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_seed_uses_master_commit_then_atomic_topology(app):
    module = controller_module()
    fixture = await module.seed_scope_topology({"database_url": app.state.settings.database_url})
    assert len(fixture["components"]) == 2 and len(fixture["sensors"]) == 3
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(TowerComponent)) == 2
        assert await session.scalar(select(func.count()).select_from(SensorChannel)) == 3


def test_foreign_container_label_refuses_pause(tmp_path, monkeypatch):
    module = controller_module()
    commands = []

    def check_output(command, **kwargs):
        commands.append(command)
        if command[1] == "inspect":
            return json.dumps(
                [{"Config": {"Labels": {"com.docker.compose.project": "another-project"}}}]
            )
        return "synthetic-container-id"

    monkeypatch.setattr(module.subprocess, "check_output", check_output)
    controller = module.OwnedInfrastructureChallenges(
        tmp_path, ["docker", "compose"], "owned-project", lambda: None, lambda: None
    )
    with pytest.raises(ValueError, match="outside the current owned project"):
        controller._container_action("redis", "pause")
    assert commands == [
        ["docker", "compose", "ps", "--quiet", "redis"],
        ["docker", "inspect", "synthetic-container-id"],
    ]
    assert controller.paused == set()


@pytest.mark.parametrize(
    ("service", "action"), [("postgres", "pause"), ("redis", "rm"), ("other-project", "unpause")]
)
def test_unsupported_mutation_is_rejected_before_docker(tmp_path, monkeypatch, service, action):
    module = controller_module()

    def unexpected(*args, **kwargs):
        pytest.fail("an unsupported challenge must not call Docker")

    monkeypatch.setattr(module.subprocess, "check_output", unexpected)
    controller = module.OwnedInfrastructureChallenges(
        tmp_path, [], "owned-project", lambda: None, lambda: None
    )
    with pytest.raises(ValueError, match="unsupported"):
        controller._container_action(service, action)
