import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import windops_backend.agents.runtime as runtime
import windops_backend.main as main
from windops_backend.agents.reasoning import LiteLLMReasoningProvider, build_reasoning_provider
from windops_backend.config import Settings


def settings(tmp_path: Path, mode: str) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        agent_mode=mode,
        llm_provider="default",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'runtime.sqlite'}",
        schema_bootstrap=True,
        knowledge_graph_backend="memory",
    )


def test_only_selected_live_sdk_is_prepared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    load = Mock()
    monkeypatch.delenv("LITELLM_MODE", raising=False)
    monkeypatch.setattr(runtime, "importlib", SimpleNamespace(import_module=load))
    assert runtime.prepare_reasoning_runtime(settings(tmp_path, "deterministic")) == 0
    load.assert_not_called()
    assert runtime.prepare_reasoning_runtime(settings(tmp_path, "litellm")) >= 0
    load.assert_called_once_with("litellm")
    assert os.environ["LITELLM_MODE"] == "PRODUCTION"


@pytest.mark.asyncio
async def test_api_prepares_sdk_before_serving_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = settings(tmp_path, "litellm")
    prepare = Mock(return_value=7.5)
    monkeypatch.setattr(main, "prepare_reasoning_runtime", prepare)
    app = main.create_app(configured)
    async with app.router.lifespan_context(app):
        prepare.assert_called_once_with(configured)
        assert app.state.reasoning_sdk_startup_seconds == 7.5
    prepare.side_effect = ImportError("SDK unavailable")
    broken = main.create_app(configured)
    with pytest.raises(ImportError, match="SDK unavailable"):
        async with broken.router.lifespan_context(broken):
            pytest.fail("API must not become ready after SDK initialization fails")


def test_sdk_import_failure_is_not_hidden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    load = Mock(side_effect=ImportError("missing selected SDK"))
    monkeypatch.setattr(runtime, "importlib", SimpleNamespace(import_module=load))
    with pytest.raises(ImportError, match="missing selected SDK"):
        runtime.prepare_reasoning_runtime(settings(tmp_path, "litellm"))


def test_explicit_output_budget_reaches_the_real_provider(tmp_path: Path) -> None:
    configured = settings(tmp_path, "litellm")
    assert configured.litellm_max_output_tokens is None
    configured.litellm_max_output_tokens = 2048
    provider = build_reasoning_provider(configured)
    assert isinstance(provider, LiteLLMReasoningProvider)
    assert provider.max_output_tokens == 2048


def test_sdk_dev_dotenv_cannot_override_governed_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LITELLM_MODE", "DEV")
    with pytest.raises(ValueError, match="dotenv"):
        runtime.prepare_reasoning_runtime(settings(tmp_path, "litellm"))
