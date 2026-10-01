from __future__ import annotations

import json
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


@pytest.mark.asyncio
async def test_diagnosis_request_binds_scope_and_evidence_without_cross_request_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts = [
        _context(),
        {"analysis_profile": {"component": "gearbox"}, "evidence": [{"evidence_id": "GB-1"}]},
    ]
    captured: list[dict[str, Any]] = []

    async def completion(**kwargs: Any) -> Any:
        payload = json.loads(kwargs["messages"][1]["content"])
        context = payload["public_context"]
        captured.append(payload["schema"])
        value = PublicDiagnosis(
            failure_mode="inspection_finding",
            component=context["analysis_profile"]["component"],
            confidence=0.8,
            conclusion="Inspection supports human review.",
            evidence_refs=[context["evidence"][0]["evidence_id"]],
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=value.model_dump_json()))]
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "provider/model", timeout_seconds=5, max_retries=0, minimum_diagnosis_confidence=0.5
    )
    generic = PublicDiagnosis.model_json_schema()
    for context in contexts:
        await provider.generate(PublicDiagnosis, "diagnose", context)
    for schema, context in zip(captured, contexts, strict=True):
        properties = schema["properties"]
        assert properties["component"]["const"] == context["analysis_profile"]["component"]
        assert properties["evidence_refs"]["items"]["enum"] == [
            context["evidence"][0]["evidence_id"]
        ]
        assert properties["evidence_refs"]["uniqueItems"] is True
        # A scope contract must not force the model to invent higher confidence.
        assert properties["confidence"]["minimum"] == 0
    assert PublicDiagnosis.model_json_schema() == generic


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"component": "gearbox"},
        {"evidence_refs": ["UNKNOWN"]},
        {"evidence_refs": ["EVIDENCE-001", "EVIDENCE-001"]},
        {"confidence": 0.1},
        {"failure_mode": "insufficient_evidence", "confidence": 0.9},
    ],
)
async def test_provider_ignoring_request_contract_is_still_rejected(
    monkeypatch: pytest.MonkeyPatch, changes: dict[str, Any]
) -> None:
    async def completion(**_kwargs: Any) -> Any:
        value = PublicDiagnosis(
            failure_mode="inspection_finding",
            component="main_bearing",
            confidence=0.8,
            conclusion="Public output only.",
            evidence_refs=["EVIDENCE-001"],
        ).model_copy(update=changes)
        return SimpleNamespace(
            model="provider/model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            choices=[SimpleNamespace(message=SimpleNamespace(content=value.model_dump_json()))],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "provider/model", timeout_seconds=5, max_retries=0, minimum_diagnosis_confidence=0.5
    )
    with pytest.raises(ReasoningEvaluationError):
        await provider.generate(PublicDiagnosis, "diagnose", _context())
    usage = provider.consume_usage()
    assert usage["token_usage"]["total_tokens"] == 15
    assert usage["evaluation_result"]["status"] == "failed"
    assert usage["degradation_policy"]["automatic_deterministic_fallback"] is False


@pytest.mark.parametrize("minimum_confidence", [0.0, 0.5])
def test_zero_confidence_abstention_preserves_production_release_gate(
    minimum_confidence: float,
) -> None:
    answer = PublicDiagnosis(
        failure_mode="insufficient_evidence",
        component="main_bearing",
        confidence=0,
        conclusion="The inspection cannot be bound to the governed asset identity.",
        evidence_refs=["EVIDENCE-001"],
    )
    if minimum_confidence == 0:
        assert (
            evaluate_public_output(
                answer,
                public_context=_context(),
                minimum_diagnosis_confidence=minimum_confidence,
            )["status"]
            == "passed"
        )
    else:
        with pytest.raises(ReasoningEvaluationError, match="below the release gate"):
            evaluate_public_output(
                answer,
                public_context=_context(),
                minimum_diagnosis_confidence=minimum_confidence,
            )


def _guidance_context() -> dict[str, Any]:
    return {
        **_context(),
        "evidence": [
            {"evidence_id": "EVIDENCE-001"},
            {
                "evidence_id": "KB-MAIN-BEARING",
                "evidence_type": "knowledge_citation",
                "summary": "The controlled corpus returned main-bearing inspection guidance.",
                "source_refs": ["/api/v1/knowledge/documents/KB-MAIN-BEARING"],
                "metrics": {"documents_retrieved": 1},
            },
        ],
    }


@pytest.mark.parametrize(
    "conclusion",
    [
        "The supplied knowledge citation provides inspection guidance but does not itself "
        "confirm physical failure.",
        "知识引用提供检查指南，但指南本身不能确认物理故障。",
    ],
)
def test_diagnosis_rejects_uncited_retrieved_guidance(conclusion: str) -> None:
    answer = PublicDiagnosis(
        failure_mode="main_bearing_degradation",
        component="main_bearing",
        confidence=0.7,
        conclusion=conclusion,
        evidence_refs=["EVIDENCE-001"],
    )
    with pytest.raises(ReasoningEvaluationError, match="guidance without a knowledge citation"):
        evaluate_public_output(
            answer, public_context=_guidance_context(), minimum_diagnosis_confidence=0.5
        )


@pytest.mark.parametrize("discuss_guidance", [False, True])
def test_guidance_citation_is_required_only_when_discussed(discuss_guidance: bool) -> None:
    answer = PublicDiagnosis(
        failure_mode="main_bearing_degradation",
        component="main_bearing",
        confidence=0.7,
        conclusion=(
            "The inspection guidance is available but does not confirm physical failure."
            if discuss_guidance
            else "The vibration exceeded its supplied threshold; the failure mechanism is unknown."
        ),
        evidence_refs=["EVIDENCE-001", "KB-MAIN-BEARING"] if discuss_guidance else ["EVIDENCE-001"],
    )
    assert (
        evaluate_public_output(
            answer, public_context=_guidance_context(), minimum_diagnosis_confidence=0.5
        )["status"]
        == "passed"
    )
