import json
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from windops_backend.agents.reasoning import (
    DeterministicReasoningProvider,
    LiteLLMReasoningProvider,
    ReasoningProviderUnavailableError,
    ReviewBundle,
)
from windops_backend.outbox import process_outbox_event
from windops_backend.schemas import PublicDiagnosis
from windops_backend.services.workflow import advance_mission_to_review
from windops_backend.storage import OutboxEvent


def context():
    return {
        "analysis_profile": {"component": "main_bearing"},
        "evidence": [{"evidence_id": "E-1", "summary": "private synthetic evidence marker"}],
    }


@pytest.mark.asyncio
async def test_timeout_keeps_request_identity_and_size_without_request_text(monkeypatch):
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs)
        raise TimeoutError

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "provider/model",
        timeout_seconds=5,
        max_retries=0,
        minimum_diagnosis_confidence=0.5,
        max_output_tokens=1024,
    )
    with pytest.raises(ReasoningProviderUnavailableError):
        await provider.generate(PublicDiagnosis, "diagnose", context())
    usage = provider.consume_usage()
    request = usage["evaluation_result"]["request"]
    assert request["utf8_bytes"] == sum(
        len(message["content"].encode("utf-8")) for message in calls[0]["messages"]
    )
    assert len(request["sha256"]) == 64
    assert request["max_output_tokens"] == 1024
    assert usage["token_usage"]["source"] == "unavailable_before_provider_response"
    assert "private synthetic evidence marker" not in json.dumps(usage)


@pytest.mark.asyncio
async def test_truncated_response_is_rejected_even_when_json_parses_and_usage_is_retained(
    monkeypatch,
):
    value = PublicDiagnosis(
        failure_mode="inspection_finding",
        component="main_bearing",
        confidence=0.8,
        conclusion="Synthetic finding",
        evidence_refs=["E-1"],
    )

    async def completion(**_kwargs):
        return SimpleNamespace(
            model="provider/model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            choices=[
                SimpleNamespace(
                    finish_reason="length", message=SimpleNamespace(content=value.model_dump_json())
                )
            ],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "provider/model",
        timeout_seconds=5,
        max_retries=0,
        minimum_diagnosis_confidence=0.5,
    )
    with pytest.raises(ReasoningProviderUnavailableError, match="truncated"):
        await provider.generate(PublicDiagnosis, "diagnose", context())
    usage = provider.consume_usage()
    assert usage["token_usage"]["total_tokens"] == 30
    assert usage["evaluation_result"]["response"]["finish_reason"] == "length"
    assert usage["evaluation_result"]["status"] == "failed"


@pytest.mark.asyncio
async def test_failed_workflow_preserves_prior_paid_node_usage_without_business_writes(
    app, client, monkeypatch
):
    original = DeterministicReasoningProvider.generate

    async def generate(self, schema, instruction, public_context):
        if schema is ReviewBundle:
            self._last_usage = {
                "provider": "litellm",
                "model": "synthetic-paid-model",
                "token_usage": {
                    "source": "unavailable_before_provider_response",
                    "total_tokens": 0,
                },
                "evaluation_result": {"status": "failed", "error_code": "provider_timeout"},
            }
            raise ReasoningProviderUnavailableError("Synthetic provider timeout")
        value = await original(self, schema, instruction, public_context)
        self._last_usage = {
            "provider": "litellm",
            "model": "synthetic-paid-model",
            "token_usage": {
                "source": "provider_reported",
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
            "evaluation_result": {"status": "passed", "checks": ["synthetic"]},
        }
        return value

    monkeypatch.setattr(DeterministicReasoningProvider, "generate", generate)
    with pytest.raises(ReasoningProviderUnavailableError, match="Synthetic provider timeout"):
        await client.post(
            "/api/v1/scada/ingest",
            json={
                "samples": [
                    {
                        "source_event_id": "AUDIT-FAILED-ATTEMPT",
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
    async with app.state.session_factory() as session:
        event = (
            await session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == "mission.analysis.requested",
                    OutboxEvent.status == "failed",
                )
            )
        ).one()
        event_id, mission_id = event.id, event.payload["mission_id"]
    for index in range(2):
        if index:
            with pytest.raises(
                ReasoningProviderUnavailableError, match="Synthetic provider timeout"
            ):
                await process_outbox_event(
                    app.state.session_factory,
                    app.state.settings,
                    event_id,
                    advance_mission_to_review,
                )
        detail = (await client.get(f"/api/v1/missions/{mission_id}")).json()
        assert detail["status"] == "detected"
        assert detail["decision"] is None and detail["work_order_id"] is None
        assert detail["approvals"] == []
        assert len(detail["executions"]) == index + 1
        execution = detail["executions"][-1]
        prior = execution["evaluation_result"]["completed_node_usage"]
        assert [item["node"] for item in prior] == ["diagnosis", "alternatives"]
        assert sum(item["token_usage"]["total_tokens"] for item in prior) == 60
        assert all(item["model"] == "synthetic-paid-model" for item in prior)
        assert execution["token_usage"]["source"] == "unavailable_before_provider_response"
        assert all("public_output" not in item for item in prior)
