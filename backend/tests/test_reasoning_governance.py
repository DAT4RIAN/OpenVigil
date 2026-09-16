from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from windops_backend.agents.reasoning import (
    LiteLLMReasoningProvider,
    ReasoningEvaluationError,
    ReasoningProviderUnavailableError,
    build_reasoning_provider,
    evaluate_public_output,
)
from windops_backend.config import Settings
from windops_backend.schemas import PublicDiagnosis


def _context() -> dict[str, Any]:
    return {
        "analysis_profile": {"component": "main_bearing"},
        "evidence": [{"evidence_id": "EVIDENCE-001"}],
    }


def test_reasoning_evaluation_requires_governed_evidence_and_scope() -> None:
    result = evaluate_public_output(
        PublicDiagnosis(
            failure_mode="early_degradation",
            component="main_bearing",
            confidence=0.82,
            conclusion="Governed evidence supports human review.",
            evidence_refs=["EVIDENCE-001"],
        ),
        public_context=_context(),
        minimum_diagnosis_confidence=0.5,
    )
    assert result["status"] == "passed"
    assert "evidence_grounding" in result["checks"]

    with pytest.raises(ReasoningEvaluationError, match="outside the governed context"):
        evaluate_public_output(
            PublicDiagnosis(
                failure_mode="unsupported",
                component="main_bearing",
                confidence=0.9,
                conclusion="This citation was not supplied.",
                evidence_refs=["HALLUCINATED-EVIDENCE"],
            ),
            public_context=_context(),
            minimum_diagnosis_confidence=0.5,
        )


@pytest.mark.asyncio
async def test_litellm_provider_timeout_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def timeout_completion(**_kwargs: Any) -> Any:
        raise TimeoutError

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=timeout_completion))
    provider = LiteLLMReasoningProvider(
        "provider/model",
        timeout_seconds=5,
        max_retries=1,
        minimum_diagnosis_confidence=0.5,
    )
    with pytest.raises(ReasoningProviderUnavailableError, match="timed out"):
        await provider.generate(PublicDiagnosis, "diagnose", _context())
    usage = provider.consume_usage()
    assert usage["provider"] == "litellm"
    assert usage["evaluation_result"]["status"] == "failed"
    assert usage["degradation_policy"] == {
        "mode": "fail_closed",
        "automatic_deterministic_fallback": False,
        "human_review_required": True,
        "max_retries": 1,
        "timeout_seconds": 5,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_name", "key_field", "model", "base_url"),
    [
        (
            "siliconflow",
            "siliconflow_api_key",
            "openai/deepseek-ai/DeepSeek-V4-Flash",
            "https://api.siliconflow.cn/v1",
        ),
        (
            "bailian",
            "bailian_api_key",
            "openai/qwen-plus",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        (
            "deepseek",
            "deepseek_api_key",
            "openai/deepseek-flash",
            "https://api.deepseek.com",
        ),
    ],
)
async def test_selected_llm_provider_routes_credentials_to_litellm(
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
    key_field: str,
    model: str,
    base_url: str,
) -> None:
    captured: dict[str, Any] = {}

    async def capture_completion(**kwargs: Any) -> Any:
        captured.update(kwargs)
        raise TimeoutError

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=capture_completion))
    settings = Settings(
        agent_mode="litellm",
        llm_provider=provider_name,
        **{key_field: "test-only-provider-key"},
    )
    provider = build_reasoning_provider(settings)
    with pytest.raises(ReasoningProviderUnavailableError, match="timed out"):
        await provider.generate(PublicDiagnosis, "diagnose", _context())
    assert captured["model"] == model
    assert captured["api_base"] == base_url
    assert captured["api_key"] == "test-only-provider-key"
    assert "test-only-provider-key" not in repr(settings)
