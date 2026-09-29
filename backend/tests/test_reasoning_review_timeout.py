import asyncio
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from windops_backend.agents.reasoning import (
    AlternativeBundle,
    LiteLLMReasoningProvider,
    ReasoningProviderUnavailableError,
    ReviewBundle,
    build_reasoning_provider,
)
from windops_backend.config import Settings
from windops_backend.schemas import PublicDiagnosis


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("schema", "override", "expected"),
    [
        (PublicDiagnosis, 90, 45),
        (AlternativeBundle, 90, 45),
        (ReviewBundle, 90, 90),
        (ReviewBundle, None, 45),
    ],
)
async def test_only_reviews_use_override_in_transport_deadline_and_failed_audit(
    monkeypatch, schema, override, expected
):
    calls, deadlines, cancelled = [], [], []
    real_timeout = asyncio.timeout

    def short_deadline(seconds):
        deadlines.append(seconds)
        return real_timeout(0.01)

    async def completion(**kwargs):
        calls.append(kwargs)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    monkeypatch.setattr(asyncio, "timeout", short_deadline)
    provider = LiteLLMReasoningProvider(
        "provider/model",
        timeout_seconds=45,
        review_timeout_seconds=override,
        max_retries=0,
        minimum_diagnosis_confidence=0.5,
        enable_thinking=False,
    )
    context = {
        "review_target": {
            "scope": "maintenance_execution",
            "alternative_id": "INSPECT-1",
            "execution_plan_id": "workplan:" + "a" * 64,
        }
    }
    with pytest.raises(ReasoningProviderUnavailableError, match="timed out"):
        await provider.generate(schema, "Review supplied evidence", context)
    assert deadlines == [expected] and cancelled == [True]
    assert len(calls) == 1
    call = calls[0]
    assert call["timeout"] == expected and call["num_retries"] == 0
    assert call["extra_body"] == {"enable_thinking": False}
    audit = provider.consume_usage()
    assert audit["degradation_policy"]["timeout_seconds"] == expected
    assert audit["evaluation_result"]["request"]["timeout_seconds"] == expected
    assert audit["evaluation_result"]["error_code"] == "provider_timeout"
    assert audit["evaluation_result"]["status"] == "failed"
    assert audit["token_usage"]["source"] == "unavailable_before_provider_response"
    contract = {
        "system": call["messages"][0]["content"],
        "schema": json.loads(call["messages"][1]["content"])["schema"],
        "generation_options": {"enable_thinking": False},
    }
    if schema is AlternativeBundle:
        assert "do not invent monitoring intervals" in contract["schema"]["description"]
        assert "already exceeded" in contract["schema"]["description"]
    if schema is ReviewBundle and override is not None:
        contract["execution_options"] = {"timeout_seconds": expected}
    assert (
        audit["request_contract_sha256"]
        == hashlib.sha256(
            json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    )


def test_review_timeout_environment_and_factory(monkeypatch):
    monkeypatch.delenv("WINDOPS_LITELLM_REVIEW_TIMEOUT_SECONDS", raising=False)
    assert Settings().litellm_review_timeout_seconds is None
    monkeypatch.setenv("WINDOPS_LITELLM_REVIEW_TIMEOUT_SECONDS", "90")
    provider = build_reasoning_provider(Settings(agent_mode="litellm"))
    assert isinstance(provider, LiteLLMReasoningProvider)
    assert provider.review_timeout_seconds == 90
    assert provider.timeout_seconds == 45
    for invalid in ("0", "121", "invalid"):
        monkeypatch.setenv("WINDOPS_LITELLM_REVIEW_TIMEOUT_SECONDS", invalid)
        with pytest.raises(ValidationError):
            Settings()


def test_provider_rejects_unbounded_review_timeout():
    with pytest.raises(ValueError, match="review_timeout_seconds"):
        LiteLLMReasoningProvider(
            "provider/model",
            timeout_seconds=45,
            review_timeout_seconds=0,
            max_retries=0,
            minimum_diagnosis_confidence=0.5,
        )
