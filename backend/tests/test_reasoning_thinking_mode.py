import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from windops_backend.agents.reasoning import (
    LiteLLMReasoningProvider,
    build_reasoning_provider,
)
from windops_backend.config import Settings
from windops_backend.schemas import PublicDiagnosis


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [None, False, True])
async def test_explicit_mode_reaches_transport_and_audited_contract(monkeypatch, mode):
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model="provider/model",
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "component": "main_bearing",
                                "failure_mode": "inspection_required",
                                "confidence": 0.8,
                                "conclusion": "Supplied evidence requires human review.",
                                "evidence_refs": ["EVD-1"],
                            }
                        )
                    ),
                )
            ],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "provider/model",
        timeout_seconds=5,
        max_retries=0,
        minimum_diagnosis_confidence=0.5,
        enable_thinking=mode,
    )
    await provider.generate(
        PublicDiagnosis,
        "Diagnose",
        {
            "analysis_profile": {"component": "main_bearing"},
            "evidence": [{"evidence_id": "EVD-1"}],
        },
    )
    assert len(calls) == 1
    call = calls[0]
    usage = provider.consume_usage()
    contract = {
        "system": call["messages"][0]["content"],
        "schema": json.loads(call["messages"][1]["content"])["schema"],
    }
    citations = contract["schema"]["properties"]["evidence_refs"]["description"]
    assert "Do not cite unrelated component evidence" in citations
    assert "contradictory or missing-data evidence" in citations
    if mode is None:
        assert "extra_body" not in call
        assert "enable_thinking" not in usage["evaluation_result"]["request"]
    else:
        assert call["extra_body"] == {"enable_thinking": mode}
        assert usage["evaluation_result"]["request"]["enable_thinking"] is mode
        contract["generation_options"] = {"enable_thinking": mode}
    assert (
        usage["request_contract_sha256"]
        == hashlib.sha256(
            json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    )
    assert usage["evaluation_result"]["status"] == "passed"
    assert usage["token_usage"]["total_tokens"] == 30


@pytest.mark.parametrize("provider_name", ["siliconflow", "default", "bailian", "deepseek"])
def test_siliconflow_mode_does_not_leak_to_other_routes(provider_name):
    settings = Settings(
        agent_mode="litellm",
        llm_provider=provider_name,
        siliconflow_enable_thinking=False,
        litellm_review_timeout_seconds=90,
        siliconflow_api_key="test-only",
        bailian_api_key="test-only",
        deepseek_api_key="test-only",
    )
    provider = build_reasoning_provider(settings)
    assert isinstance(provider, LiteLLMReasoningProvider)
    assert provider.enable_thinking is (False if provider_name == "siliconflow" else None)


def test_mode_environment_parsing_preserves_false_and_rejects_invalid(monkeypatch):
    monkeypatch.setenv("WINDOPS_SILICONFLOW_ENABLE_THINKING", "false")
    assert Settings().siliconflow_enable_thinking is False
    monkeypatch.setenv("WINDOPS_SILICONFLOW_ENABLE_THINKING", "invalid")
    with pytest.raises(ValidationError):
        Settings()


def test_evaluation_cli_uses_the_configured_siliconflow_mode(monkeypatch, tmp_path):
    from windops_backend.operations import reasoning_eval

    configured = Settings(
        agent_mode="litellm",
        llm_provider="siliconflow",
        siliconflow_api_key="test-only",
        siliconflow_enable_thinking=False,
        litellm_review_timeout_seconds=90,
    )
    captured = []

    class ProviderReached(Exception):
        pass

    def capture_provider(*args, **kwargs):
        captured.append(kwargs)
        raise ProviderReached

    cases = Path(__file__).parents[1] / "evaluations/wind-diagnosis-v1.json"
    monkeypatch.setattr(reasoning_eval, "get_settings", lambda: configured)
    monkeypatch.setattr(reasoning_eval, "prepare_reasoning_runtime", lambda _: 0)
    monkeypatch.setattr(reasoning_eval, "LiteLLMReasoningProvider", capture_provider)
    monkeypatch.setattr(
        sys, "argv", ["reasoning_eval", "--cases", str(cases), "--report", str(tmp_path / "r.json")]
    )
    with pytest.raises(ProviderReached):
        reasoning_eval.main()
    assert captured[0]["enable_thinking"] is False
    assert captured[0]["max_retries"] == 0
    assert captured[0]["review_timeout_seconds"] == configured.litellm_review_timeout_seconds
