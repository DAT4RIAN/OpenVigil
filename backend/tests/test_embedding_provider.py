from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from windops_backend.agents.embeddings import EMBEDDING_DIMENSIONS, LiteLLMEmbeddingProvider
from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.config import Settings
from windops_backend.services.knowledge import _embedding_provider


def _vector(value: float = 0.1) -> list[float]:
    return [value] * EMBEDDING_DIMENSIONS


def _install_response(monkeypatch: pytest.MonkeyPatch, data: list[dict[str, Any]]) -> list[dict]:
    calls: list[dict] = []

    async def embedding(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(data=data)

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(aembedding=embedding))
    return calls


async def test_default_embedding_request_preserves_provider_defaults(monkeypatch) -> None:
    calls = _install_response(monkeypatch, [{"index": 0, "embedding": _vector()}])
    assert await LiteLLMEmbeddingProvider("text-embedding-3-small").embed(["query"]) == [_vector()]
    assert calls == [
        {"model": "text-embedding-3-small", "input": ["query"], "num_retries": 0, "max_retries": 0}
    ]


async def test_custom_embedding_connection_reaches_indexing_and_query_providers(
    monkeypatch,
) -> None:
    calls = _install_response(
        monkeypatch,
        [{"index": 1, "embedding": _vector(0.2)}, {"index": 0, "embedding": _vector(0.1)}],
    )
    settings = Settings(
        embedding_model="openai/Qwen/Qwen3-Embedding-4B",
        embedding_api_base="https://api.siliconflow.cn/v1",
        embedding_api_key=SecretStr("synthetic-embedding-secret"),
        embedding_dimensions=1536,
    )
    session = SimpleNamespace(bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    providers = [
        _embedding_provider(settings),
        SQLToolAdapter(session, settings=settings).embedding_provider,
    ]
    for provider in providers:
        assert await provider.embed(["document", "query"]) == [_vector(0.1), _vector(0.2)]
    assert len(calls) == 2
    assert all(
        call
        == {
            "model": "openai/Qwen/Qwen3-Embedding-4B",
            "input": ["document", "query"],
            "api_base": "https://api.siliconflow.cn/v1",
            "api_key": "synthetic-embedding-secret",
            "dimensions": 1536,
            "allowed_openai_params": ["dimensions"],
            "num_retries": 0,
            "max_retries": 0,
        }
        for call in calls
    )
    assert "synthetic-embedding-secret" not in repr(settings)


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 1, "embedding": _vector()}],
        [{"index": 0, "embedding": _vector()}, {"index": 0, "embedding": _vector()}],
        [{"index": 0, "embedding": [0.1]}],
        [{"index": 0, "embedding": _vector(float("nan"))}],
        [{"index": 0, "embedding": _vector(float("inf"))}],
    ],
)
async def test_embedding_response_rejects_invalid_indices_shapes_and_values(monkeypatch, data):
    _install_response(monkeypatch, data)
    with pytest.raises(RuntimeError):
        await LiteLLMEmbeddingProvider("test-model").embed(["query"])


async def test_empty_embedding_input_does_not_call_provider(monkeypatch) -> None:
    calls = _install_response(monkeypatch, [])
    assert await LiteLLMEmbeddingProvider("test-model").embed([]) == []
    assert calls == []


@pytest.mark.parametrize(
    "base",
    [
        "http://example.com/v1",
        "https://user:password@example.com/v1",
        "https://example.com?key=x",
        "https://example.com/#fragment",
    ],
)
def test_embedding_endpoint_rejects_plaintext_and_embedded_credentials(base) -> None:
    with pytest.raises(ValidationError, match="embedding.*HTTPS"):
        Settings(embedding_api_base=base, embedding_api_key=SecretStr("synthetic-key"))


def test_embedding_custom_endpoint_requires_explicit_credentials() -> None:
    with pytest.raises(ValidationError, match="embedding.*API key"):
        Settings(embedding_api_base="https://api.siliconflow.cn/v1")


def test_embedding_configuration_error_does_not_print_plaintext_key() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            embedding_api_base="http://example.com/v1",
            embedding_api_key="synthetic-private-credential",
        )
    assert "synthetic-private-credential" not in str(error.value)


def test_embedding_dimensions_match_database_contract(monkeypatch) -> None:
    with pytest.raises(ValidationError):
        Settings(embedding_dimensions=1024)
    with pytest.raises(ValueError, match="1536"):
        LiteLLMEmbeddingProvider("test-model", dimensions=1024)
    monkeypatch.setenv("WINDOPS_EMBEDDING_DIMENSIONS", "1536")
    assert Settings().embedding_dimensions == 1536
