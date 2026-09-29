import asyncio
import json
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from windops_backend.agents.embedding_audit import capture_embedding_usage, merge_embedding_usage
from windops_backend.agents.embeddings import EMBEDDING_DIMENSIONS, LiteLLMEmbeddingProvider
from windops_backend.agents.graph import OpenVigilWorkflowGraph
from windops_backend.agents.reasoning import (
    DeterministicReasoningProvider,
    ReasoningProviderUnavailableError,
    ReviewBundle,
)
from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.models import AgentExecution
from windops_backend.storage import OutboxEvent


async def _mission(client):
    response = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": "EMBEDDING-AUDIT-MISSION",
                    "turbine_id": "WT-023",
                    "observed_at": "2026-09-27T00:00:00Z",
                    "variable": "main_bearing_vibration_rms",
                    "value": 4.81,
                    "unit": "mm/s",
                    "attributes": {"baseline": 3.79, "anomaly_score": 0.86},
                }
            ]
        },
    )
    assert response.status_code == 202
    result = response.json()["results"][0]
    assert result["mission_id"] and result["alarm_id"], result
    return {
        "mission_id": result["mission_id"],
        "alarm_id": result["alarm_id"],
        "turbine_id": "WT-023",
    }


def _response(prompt_tokens=49, total_tokens=49):
    return SimpleNamespace(
        data=[{"index": 0, "embedding": [0.1] * EMBEDDING_DIMENSIONS}],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, total_tokens=total_tokens),
    )


async def test_paid_query_usage_is_persisted_on_knowledge_execution(app, client, monkeypatch):
    state = await _mission(client)
    calls = []

    async def embedding(**kwargs):
        calls.append(kwargs)
        return _response()

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(aembedding=embedding))
    async with app.state.session_factory() as session, session.begin():
        tools = SQLToolAdapter(
            session,
            embedding_provider=LiteLLMEmbeddingProvider("synthetic/embedding"),
            settings=app.state.settings.model_copy(update={"embedding_max_retries": 0}),
        )
        graph = OpenVigilWorkflowGraph(session, tools, DeterministicReasoningProvider())

        async def retrieve(_state):
            matches = await tools.query_similar_failures(
                "private synthetic embedding query", vectorize_missing=False
            )
            return {"documents_retrieved": len(matches)}

        await graph._recorded(state, "knowledge", "knowledge_agent", retrieve)
        recorded = (
            await session.scalars(
                select(AgentExecution)
                .where(
                    AgentExecution.mission_id == state["mission_id"],
                    AgentExecution.node == "knowledge",
                )
                .order_by(AgentExecution.started_at.desc())
            )
        ).first()
        assert recorded.provider == "litellm"
        assert recorded.model == "synthetic/embedding"
        assert recorded.token_usage == {
            "prompt_tokens": 49,
            "completion_tokens": 0,
            "total_tokens": 49,
            "source": "provider_reported",
        }
        receipt = recorded.evaluation_result["embedding_calls"][0]
        assert receipt["status"] == "succeeded"
        assert len(receipt["request"]["input_texts_sha256"]) == 64
        assert receipt["request"]["input_count"] == 1
        assert "private synthetic embedding query" not in json.dumps(receipt)
    assert len(calls) == 1
    assert calls[0]["num_retries"] == calls[0]["max_retries"] == 0
    detail = (await client.get(f"/api/v1/missions/{state['mission_id']}")).json()
    knowledge = [e for e in detail["executions"] if e["node"] == "knowledge"]
    assert knowledge[-1]["token_usage"]["total_tokens"] == 49


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"prompt_tokens": 0, "total_tokens": 0},
        {"prompt_tokens": True, "total_tokens": 1},
        {"prompt_tokens": -1, "total_tokens": -1},
        {"prompt_tokens": 49, "total_tokens": 50},
        {"prompt_tokens": "49", "total_tokens": 49},
    ],
)
async def test_missing_or_invalid_usage_never_becomes_a_known_zero(usage, monkeypatch):
    async def embedding(**_kwargs):
        response = _response()
        response.usage = usage
        return response

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(aembedding=embedding))
    with capture_embedding_usage() as receipts:
        vectors = await LiteLLMEmbeddingProvider("synthetic/embedding").embed(["query"])
    assert len(vectors) == 1
    merged = merge_embedding_usage({}, receipts)
    assert merged["token_usage"]["prompt_tokens"] is None
    assert merged["token_usage"]["total_tokens"] is None
    assert merged["token_usage"]["source"] == "unavailable"
    assert merged["token_usage"]["unknown_attempts"] == 1
    assert receipts[0]["status"] == "succeeded"


async def test_paid_usage_survives_invalid_vectors(monkeypatch):
    async def embedding(**_kwargs):
        response = _response()
        response.data[0]["embedding"] = [0.1]
        return response

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(aembedding=embedding))
    with capture_embedding_usage() as receipts, pytest.raises(RuntimeError, match="1536"):
        await LiteLLMEmbeddingProvider("synthetic/embedding").embed(["query"])
    assert receipts[0]["status"] == "failed"
    assert receipts[0]["token_usage"]["total_tokens"] == 49
    assert merge_embedding_usage({}, receipts)["token_usage"]["total_tokens"] == 49


async def test_timeout_and_controlled_retry_preserve_unknown_and_known_attempts(app, monkeypatch):
    from windops_backend.agents.embeddings import embed_texts_with_controls

    calls = []

    async def embedding(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TimeoutError("private synthetic failure text")
        return _response()

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(aembedding=embedding))
    with capture_embedding_usage() as receipts:
        vectors = await embed_texts_with_controls(
            LiteLLMEmbeddingProvider("synthetic/embedding"),
            ["private synthetic query"],
            settings=app.state.settings.model_copy(update={"embedding_max_retries": 1}),
        )
    assert len(vectors) == 1
    assert len(calls) == len(receipts) == 2
    assert all(c["num_retries"] == c["max_retries"] == 0 for c in calls)
    assert [r["status"] for r in receipts] == ["failed", "succeeded"]
    summary = merge_embedding_usage({}, receipts)["token_usage"]
    assert summary["source"] == "partially_reported"
    assert summary["total_tokens"] is None
    assert summary["known_total_tokens"] == 49
    assert summary["unknown_attempts"] == 1
    assert "private synthetic" not in json.dumps(receipts)


async def test_parallel_scopes_do_not_share_receipts(monkeypatch):
    async def embedding(**kwargs):
        await asyncio.sleep(0)
        tokens = {"query-one": 31, "query-two": 57}[kwargs["input"][0]]
        return _response(tokens, tokens)

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(aembedding=embedding))
    provider = LiteLLMEmbeddingProvider("synthetic/embedding")

    async def run(text):
        with capture_embedding_usage() as receipts:
            await provider.embed([text])
        return receipts

    first, second = await asyncio.gather(run("query-one"), run("query-two"))
    assert len(first) == len(second) == 1
    assert first[0]["token_usage"]["total_tokens"] == 31
    assert second[0]["token_usage"]["total_tokens"] == 57
    assert first[0]["request"]["input_texts_sha256"] != second[0]["request"]["input_texts_sha256"]
    with capture_embedding_usage() as empty:
        assert await provider.embed([]) == []
    assert empty == []


async def test_cancelled_attempt_is_propagated_and_does_not_leak_scope(monkeypatch):
    async def embedding(**_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(aembedding=embedding))
    with capture_embedding_usage() as receipts, pytest.raises(asyncio.CancelledError):
        await LiteLLMEmbeddingProvider("synthetic/embedding").embed(["query"])
    assert len(receipts) == 1
    assert receipts[0]["status"] == "failed"
    assert receipts[0]["error_code"] == "CancelledError"
    assert receipts[0]["token_usage"]["total_tokens"] is None
    with capture_embedding_usage() as next_operation:
        assert next_operation == []


def test_embedding_metadata_keeps_separate_reasoning_model_and_usage():
    from windops_backend.agents.embedding_audit import (
        begin_embedding_attempt,
        embedding_response_usage,
    )

    reasoning = {
        "provider": "litellm",
        "model": "synthetic/reasoning",
        "token_usage": {"total_tokens": 17},
    }
    with capture_embedding_usage() as receipts:
        receipt = begin_embedding_attempt("synthetic/embedding", ["query"])
        receipt["token_usage"] = embedding_response_usage({"prompt_tokens": 49, "total_tokens": 49})
        receipt["status"] = "succeeded"
    merged = merge_embedding_usage(reasoning, receipts)
    assert merged["model"] == "synthetic/reasoning"
    assert merged["token_usage"] == {"total_tokens": 17}
    assert merged["evaluation_result"]["embedding_token_usage"]["total_tokens"] == 49
    assert "evaluation_result" not in reasoning


async def test_later_failure_preserves_embedding_usage_after_workflow_rollback(
    app, client, monkeypatch
):
    original_init = SQLToolAdapter.__init__
    original_generate = DeterministicReasoningProvider.generate
    calls = []

    def init(self, *args, **kwargs):
        kwargs["embedding_provider"] = LiteLLMEmbeddingProvider("synthetic/embedding")
        original_init(self, *args, **kwargs)

    async def embedding(**kwargs):
        calls.append(kwargs)
        count = len(kwargs["input"])
        return SimpleNamespace(
            data=[{"index": i, "embedding": [0.1] * EMBEDDING_DIMENSIONS} for i in range(count)],
            usage={"prompt_tokens": count * 7, "total_tokens": count * 7},
        )

    async def generate(self, schema, instruction, context):
        if schema is ReviewBundle:
            self._last_usage = {
                "provider": "litellm",
                "model": "synthetic/review",
                "token_usage": {
                    "total_tokens": None,
                    "source": "unavailable_before_provider_response",
                },
            }
            raise ReasoningProviderUnavailableError("Synthetic later review failure")
        return await original_generate(self, schema, instruction, context)

    monkeypatch.setattr(SQLToolAdapter, "__init__", init)
    monkeypatch.setattr(DeterministicReasoningProvider, "generate", generate)
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(aembedding=embedding))
    with pytest.raises(ReasoningProviderUnavailableError, match="Synthetic later review failure"):
        await _mission(client)
    async with app.state.session_factory() as session:
        event = (
            await session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == "mission.analysis.requested",
                    OutboxEvent.status == "failed",
                )
            )
        ).one()
        mission_id = event.payload["mission_id"]
    detail = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert detail["status"] == "detected"
    assert detail["decision"] is None and detail["work_order_id"] is None
    assert detail["approvals"] == []
    assert len(detail["executions"]) == 1
    prior = detail["executions"][0]["evaluation_result"]["completed_node_usage"]
    knowledge = next(item for item in prior if item["node"] == "knowledge")
    assert knowledge["model"] == "synthetic/embedding"
    assert calls
    assert knowledge["token_usage"]["total_tokens"] == sum(len(c["input"]) * 7 for c in calls)
    assert len(knowledge["evaluation_result"]["embedding_calls"]) == len(calls)
    assert "public_output" not in knowledge
