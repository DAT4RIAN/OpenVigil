from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from windops_backend.agents.reasoning import LiteLLMReasoningProvider, ReasoningEvaluationError
from windops_backend.operations.reasoning_eval import (
    Pricing,
    Suite,
    compare_baseline,
    evaluate,
    grade,
    read_baseline,
    summarize,
    token_cost,
)
from windops_backend.schemas import PublicDiagnosis


def suite() -> Suite:
    return Suite.model_validate_json(
        (Path(__file__).parents[1] / "evaluations/wind-diagnosis-v1.json").read_bytes()
    )


def pricing() -> Pricing:
    return Pricing(
        model="test/model",
        currency="CNY",
        input_per_million=2,
        output_per_million=4,
        source="unit-test-only",
        verified_at="2026-09-27",
        maximum_total_cost=1,
    )


def answer(index: int = 0) -> PublicDiagnosis:
    case = suite().cases[index]
    return PublicDiagnosis(
        failure_mode=case.expected_mode,
        component=case.component,
        confidence=0 if case.abstain else 0.8,
        conclusion="Public synthetic conclusion.",
        evidence_refs=case.required_evidence,
    )


def test_grading_rejects_wrong_scope_unknown_or_missing_citations_and_overconfident_refusal() -> (
    None
):
    cases = suite().cases
    assert grade(cases[0], answer(), 0.5)["correct"]
    for updates in (
        {"component": "gearbox"},
        {"evidence_refs": ["HALLUCINATED"]},
        {"evidence_refs": ["OTHER-01"]},
        {"evidence_refs": ["INSPECT-MB-01", "OTHER-01"]},
        {"confidence": 0.1},
    ):
        assert not grade(cases[0], answer().model_copy(update=updates), 0.5)["correct"]
    assert grade(cases[3], answer(3), 0.5)["explicit_abstention"]
    assert not grade(cases[3], answer(3).model_copy(update={"confidence": 0.8}), 0.5)["correct"]


@pytest.mark.asyncio
async def test_rejected_paid_response_keeps_usage_and_output_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def completion(**kwargs: Any) -> Any:
        assert kwargs["max_tokens"] == 1024
        bad = answer().model_copy(update={"evidence_refs": ["UNKNOWN"]})
        return SimpleNamespace(
            model="test/model",
            usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            choices=[SimpleNamespace(message=SimpleNamespace(content=bad.model_dump_json()))],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "test/model",
        timeout_seconds=5,
        max_retries=0,
        minimum_diagnosis_confidence=0,
        max_output_tokens=1024,
    )
    with pytest.raises(ReasoningEvaluationError):
        await provider.generate(
            PublicDiagnosis,
            "diagnose",
            {
                "analysis_profile": {"component": "main_bearing"},
                "evidence": [e.model_dump() for e in suite().cases[0].evidence],
            },
        )
    usage = provider.consume_usage()
    assert usage["token_usage"]["total_tokens"] == 30
    assert usage["evaluation_result"]["status"] == "failed"
    assert token_cost(usage, pricing()) == pytest.approx(0.00008)
    assert token_cost({"token_usage": {"source": "provider_usage_missing"}}, pricing()) is None


@pytest.mark.asyncio
async def test_network_failures_are_not_refusals_or_free_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def completion(**_kwargs: Any) -> Any:
        raise TimeoutError("never emit credentials")

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "test/model", timeout_seconds=5, max_retries=0, minimum_diagnosis_confidence=0
    )
    results = await evaluate(suite(), provider, pricing())
    summary = summarize(suite(), results, pricing())
    assert len(results) == 6
    assert summary["accuracy"] == summary["abstention_accuracy"] == 0
    assert summary["total_cost"] is None
    assert not summary["passed"]
    assert "credentials" not in json.dumps(results)
    with pytest.raises(ValueError, match="every case"):
        summarize(suite(), results[:-1], pricing())


def test_suite_rejects_leaked_labels_and_missing_required_coverage() -> None:
    value = suite().model_dump()
    value["cases"][0]["required_evidence"] = ["NOT-IN-CONTEXT"]
    with pytest.raises(ValueError, match="public context"):
        Suite.model_validate(value)
    value = suite().model_dump()
    value["cases"] = value["cases"][:3]
    with pytest.raises(ValueError, match="both diagnosis and abstention"):
        Suite.model_validate(value)


def test_baseline_comparison_rejects_different_cases_and_metric_regression(tmp_path: Path) -> None:
    report = {
        "schema": "v1",
        "suite_sha256": "cases",
        "pricing": {"currency": "CNY"},
        "summary": {
            "passed": True,
            "accuracy": 1,
            "diagnosis_accuracy": 1,
            "abstention_accuracy": 1,
            "citation_precision": 1,
            "required_citation_recall": 1,
            "p95_seconds": 2,
            "total_cost": 0.2,
        },
    }
    assert compare_baseline(report, report)["passed"]
    changed = {**report, "summary": {**report["summary"], "accuracy": 0.5, "p95_seconds": 3}}
    assert compare_baseline(changed, report)["regressions"] == ["accuracy", "p95_seconds"]
    with pytest.raises(ValueError, match="same report schema and case suite"):
        compare_baseline({**report, "suite_sha256": "other"}, report)
    with pytest.raises(ValueError, match="same currency"):
        compare_baseline({**report, "pricing": {"currency": "USD"}}, report)
    with pytest.raises(ValueError, match="passed all absolute gates"):
        compare_baseline(report, {**report, "summary": {**report["summary"], "passed": False}})
    for value in (float("nan"), float("inf"), None, -1):
        with pytest.raises(ValueError, match="complete finite metrics"):
            compare_baseline(
                report, {**report, "summary": {**report["summary"], "accuracy": value}}
            )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(report))
    baseline, digest = read_baseline(baseline_path, report)
    assert baseline == report and len(digest) == 64
    baseline_path.write_text("[]")
    with pytest.raises(ValueError, match="report object"):
        read_baseline(baseline_path, report)
    with pytest.raises(FileNotFoundError):
        read_baseline(tmp_path / "missing.json", report)


@pytest.mark.parametrize(
    "overrides",
    [
        {"prompt_tokens": True},
        {"completion_tokens": -1},
        {"total_tokens": 999},
        {"prompt_tokens": "20"},
        {"source": "provider_usage_missing"},
    ],
)
def test_cost_rejects_invalid_or_unverifiable_accounting(overrides: dict[str, Any]) -> None:
    usage = {
        "model": "test/model",
        "token_usage": {
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
            "source": "provider_reported",
            **overrides,
        },
    }
    assert token_cost(usage, pricing()) is None


def test_cost_requires_the_returned_model_to_match_the_rate_card() -> None:
    usage = {
        "model": "different/model",
        "token_usage": {
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
            "source": "provider_reported",
        },
    }
    assert token_cost(usage, pricing()) is None
    usage["model"] = "openai/test/model"
    assert token_cost(usage, pricing()) == pytest.approx(0.00008)


@pytest.mark.asyncio
@pytest.mark.parametrize("returned_model", [None, "", 123])
async def test_missing_returned_model_cannot_be_priced_as_requested_model(
    monkeypatch: pytest.MonkeyPatch,
    returned_model: Any,
) -> None:
    async def completion(**_kwargs: Any) -> Any:
        return SimpleNamespace(
            model=returned_model,
            usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            choices=[SimpleNamespace(message=SimpleNamespace(content=answer().model_dump_json()))],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "test/model",
        timeout_seconds=5,
        max_retries=0,
        minimum_diagnosis_confidence=0,
    )
    await provider.generate(
        PublicDiagnosis,
        "diagnose",
        {
            "analysis_profile": {"component": "main_bearing"},
            "evidence": [e.model_dump() for e in suite().cases[0].evidence],
        },
    )
    usage = provider.consume_usage()
    assert token_cost(usage, pricing()) is None
    assert usage["model"] is None
    assert usage["requested_model"] == "test/model"
    assert usage["token_usage"]["total_tokens"] == 30


@pytest.mark.asyncio
async def test_budget_exhaustion_retains_all_cases_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def completion(**_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            model="test/model",
            usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            choices=[SimpleNamespace(message=SimpleNamespace(content=answer().model_dump_json()))],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "test/model", timeout_seconds=5, max_retries=0, minimum_diagnosis_confidence=0
    )
    rate_card = pricing().model_copy(update={"maximum_total_cost": 0.00001})
    results = await evaluate(suite(), provider, rate_card)
    assert calls == 1
    assert len(results) == 6
    assert all(row["error"] == "BudgetExhausted" for row in results[1:])
    summary = summarize(suite(), results, rate_card)
    assert summary["unknown_cost_cases"] == 5
    assert summary["known_cost_subtotal"] == pytest.approx(0.00008)
    assert not summary["passed"]
