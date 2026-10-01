import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy import select

from windops_backend.agents.reasoning import (
    DeterministicReasoningProvider,
    LiteLLMReasoningProvider,
    ReasoningEvaluationError,
    ReviewBundle,
    _response_schema,
    evaluate_public_output,
)
from windops_backend.storage import OutboxEvent


def context() -> dict:
    return {
        "review_target": {
            "scope": "maintenance_execution",
            "alternative_id": "INSPECT-1",
            "execution_plan_id": "workplan:" + "a" * 64,
        }
    }


def legacy_payload() -> dict:
    return {
        "reviews": [
            {
                "review_type": kind,
                "reviewer_agent": kind + " reviewer",
                "outcome": "conditional_pass",
                "public_summary": "The inspection requires verified isolation before field work.",
                "conditions": ["Confirm isolation before work"],
            }
            for kind in ("engineering", "safety", "economic", "resource", "compliance")
        ]
    }


def test_generation_schema_rejects_reviews_without_a_maintenance_target() -> None:
    schema = _response_schema(ReviewBundle, context())
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(legacy_payload()))


def test_post_generation_check_rejects_ambiguous_review_scope() -> None:
    with pytest.raises(ReasoningEvaluationError, match="review target"):
        evaluate_public_output(
            ReviewBundle.model_validate(legacy_payload()),
            public_context=context(),
            minimum_diagnosis_confidence=0.5,
        )


def bound_payload() -> dict:
    payload = legacy_payload()
    payload["target"] = deepcopy(context()["review_target"])
    for review in payload["reviews"]:
        review["reviewer_agent"] = "review_committee"
        review["operating_constraints"] = ["Do not resume operation before field assessment"]
    return payload


@pytest.mark.parametrize("field", ["alternative_id", "execution_plan_id"])
def test_another_alternative_or_changed_plan_cannot_reuse_reviews(field: str) -> None:
    payload = bound_payload()
    payload["target"][field] = "other-plan-or-proposal"
    schema = _response_schema(ReviewBundle, context())
    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ReasoningEvaluationError, match="review target"):
        evaluate_public_output(
            ReviewBundle.model_validate(payload),
            public_context=context(),
            minimum_diagnosis_confidence=0.5,
        )


def test_scoped_failure_is_preserved_without_retry_or_rewriting() -> None:
    payload = bound_payload()
    payload["reviews"][1].update(
        outcome="fail", public_summary="Required isolation cannot be established for this work."
    )
    schema = _response_schema(ReviewBundle, context())
    Draft202012Validator(schema).validate(payload)
    value = ReviewBundle.model_validate(payload)
    result = evaluate_public_output(
        value, public_context=context(), minimum_diagnosis_confidence=0.5
    )
    assert "review_target_binding" in result["checks"]
    assert value.model_dump() == payload
    assert value.reviews[1].outcome == "fail"


def test_unbound_proposal_can_receive_a_scoped_failure() -> None:
    unbound = context()
    unbound["review_target"]["execution_plan_id"] = None
    payload = bound_payload()
    payload["target"]["execution_plan_id"] = None
    for review in payload["reviews"]:
        review.update(outcome="fail", conditions=["A controlled execution plan is required"])
    schema = _response_schema(ReviewBundle, unbound)
    Draft202012Validator(schema).validate(payload)
    evaluate_public_output(
        ReviewBundle.model_validate(payload),
        public_context=unbound,
        minimum_diagnosis_confidence=0.5,
    )


def test_historical_review_is_readable_without_inventing_a_target() -> None:
    legacy = ReviewBundle.model_validate(legacy_payload())
    assert legacy.target is None
    assert all(review.operating_constraints == [] for review in legacy.reviews)


@pytest.mark.parametrize(
    "constraint",
    [
        "Do not operate or rotate the turbine while personnel are in the nacelle or near "
        "the main bearing without LOTO in place.",
        "No turbine operation while personnel are exposed unless LOTO is applied.",
        "Do not rotate the turbine except with lockout/tagout in place.",
    ],
)
def test_loto_cannot_be_an_exception_to_personnel_exposure_restriction(constraint: str) -> None:
    payload = bound_payload()
    payload["reviews"][1]["operating_constraints"] = [constraint]
    value = ReviewBundle.model_validate(payload)
    with pytest.raises(ReasoningEvaluationError, match="LOTO as an operation exception"):
        evaluate_public_output(value, public_context=context(), minimum_diagnosis_confidence=0.5)
    assert value.model_dump() == payload
    # Stored historical output remains readable; only new generation is rejected.
    assert ReviewBundle.model_validate(payload).reviews[1].operating_constraints == [constraint]


@pytest.mark.parametrize(
    "constraint",
    [
        "No turbine operation or rotation while personnel are exposed; verified LOTO "
        "is required before maintenance work.",
        "Do not resume operation before responsible human approval of a separate "
        "restart procedure.",
        "LOTO must be verified before work. Turbine operation remains prohibited while "
        "personnel are exposed.",
    ],
)
def test_loto_work_prerequisite_and_unconditional_operating_restriction_are_preserved(
    constraint: str,
) -> None:
    payload = bound_payload()
    payload["reviews"][1]["operating_constraints"] = [constraint]
    payload["reviews"][1]["outcome"] = "fail"
    value = ReviewBundle.model_validate(payload)
    result = evaluate_public_output(
        value, public_context=context(), minimum_diagnosis_confidence=0.5
    )
    assert "no_loto_operation_exception" in result["checks"]
    assert value.model_dump() == payload


@pytest.mark.asyncio
async def test_loto_exception_rejection_keeps_paid_usage_without_retry(monkeypatch) -> None:
    payload = bound_payload()
    payload["reviews"][1]["operating_constraints"] = [
        "Do not operate or rotate the turbine while personnel are in the nacelle or near "
        "the main bearing without LOTO in place."
    ]
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model="provider/model",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=ReviewBundle.model_validate(payload).model_dump_json()
                    )
                )
            ],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "provider/model", timeout_seconds=5, max_retries=0, minimum_diagnosis_confidence=0.5
    )
    with pytest.raises(ReasoningEvaluationError, match="LOTO as an operation exception"):
        await provider.generate(ReviewBundle, "Review the supplied maintenance proposal", context())
    assert len(calls) == 1
    usage = provider.consume_usage()
    assert usage["token_usage"]["total_tokens"] == 30
    assert usage["evaluation_result"]["status"] == "failed"


@pytest.mark.asyncio
async def test_custom_provider_cannot_persist_a_loto_operation_exception(app, client, monkeypatch):
    original = DeterministicReasoningProvider.generate

    async def generate(self, schema, instruction, public_context):
        value = await original(self, schema, instruction, public_context)
        if schema is ReviewBundle:
            value.reviews[1].operating_constraints = [
                "Do not operate or rotate the turbine while personnel are in the nacelle or "
                "near the main bearing without LOTO in place."
            ]
        return value

    monkeypatch.setattr(DeterministicReasoningProvider, "generate", generate)
    response = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": "REVIEW-LOTO-EXCEPTION-REGRESSION",
                    "turbine_id": "WT-023",
                    "observed_at": (datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
                    "variable": "main_bearing_vibration_rms",
                    "value": 4.81,
                    "unit": "mm/s",
                    "attributes": {"baseline": 3.79, "anomaly_score": 0.86},
                }
            ]
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    assert "LOTO as an operation exception" in response.json()["error"]["message"]
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
    mission = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert mission["status"] == "detected"
    assert mission["decision"] is None and mission["work_order_id"] is None
    assert mission["approvals"] == [] and not mission["public_state"].get("reviews")


def test_review_request_cannot_omit_its_target_or_leak_a_prior_target() -> None:
    with pytest.raises(ReasoningEvaluationError, match="review target"):
        _response_schema(ReviewBundle, {})
    first = _response_schema(ReviewBundle, context())
    second_context = context()
    second_context["review_target"]["alternative_id"] = "SECOND"
    second = _response_schema(ReviewBundle, second_context)
    assert first["properties"]["target"]["const"]["alternative_id"] == "INSPECT-1"
    assert second["properties"]["target"]["const"]["alternative_id"] == "SECOND"
    assert "target" not in ReviewBundle.model_json_schema()["required"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_review", [False, True])
async def test_workflow_persists_plan_scoped_reviews_and_operation_restrictions(
    client, monkeypatch: pytest.MonkeyPatch, failed_review: bool
) -> None:
    original = DeterministicReasoningProvider.generate
    captured = []

    async def observe(self, schema, instruction, public_context):
        value = await original(self, schema, instruction, public_context)
        if schema is ReviewBundle:
            captured.append(deepcopy(public_context))
            if failed_review:
                value.reviews[1].outcome = "fail"
                value.reviews[1].public_summary = "Isolation is unavailable; do not execute work."
        return value

    monkeypatch.setattr(DeterministicReasoningProvider, "generate", observe)
    response = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": "REVIEW-SCOPE-SYNTHETIC-ANOMALY",
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
    assert response.status_code == 202, response.text
    mission_id = response.json()["results"][0]["mission_id"]
    detail = (await client.get(f"/api/v1/missions/{mission_id}")).json()
    assert detail["status"] == "under_review"
    assert len(captured) == 1
    supplied = captured[0]
    target = supplied["review_target"]
    recommended = next(item for item in detail["decision"]["alternatives"] if item["recommended"])
    assert target == {
        "scope": "maintenance_execution",
        "alternative_id": recommended["alternative_id"],
        "execution_plan_id": recommended["execution_plan_id"],
    }
    assert supplied["execution_plan"]["execution_plan_id"] == target["execution_plan_id"]
    assert len(supplied["execution_plan"]["plan"]["tasks"]) == 5
    assert supplied["evidence"] == detail["public_state"]["evidence"]
    reviews = detail["public_state"]["reviews"]
    assert {review["reviewer_agent"] for review in reviews} == {"review_committee"}
    assert detail["public_state"]["review_target"] == target
    assert reviews[0]["operating_constraints"]
    assert reviews[1]["outcome"] == ("fail" if failed_review else "conditional_pass")
    assert detail["approvals"] == [] and detail["work_order_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_target", [False, True])
async def test_provider_preserves_failed_reviews_and_rejects_mismatched_targets(
    monkeypatch: pytest.MonkeyPatch, wrong_target: bool
) -> None:
    calls = []
    payload = bound_payload()
    payload["reviews"][1]["outcome"] = "fail"
    if wrong_target:
        payload["target"]["alternative_id"] = "OTHER-ALTERNATIVE"
    value = ReviewBundle.model_validate(payload)

    async def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=value.model_dump_json()))],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "provider/model", timeout_seconds=5, max_retries=0, minimum_diagnosis_confidence=0.5
    )
    if wrong_target:
        with pytest.raises(ReasoningEvaluationError, match="review target"):
            await provider.generate(
                ReviewBundle, "Review the supplied maintenance proposal", context()
            )
    else:
        result = await provider.generate(
            ReviewBundle, "Review the supplied maintenance proposal", context()
        )
        assert result.reviews[1].outcome == "fail"
        assert result.model_dump() == payload
    assert len(calls) == 1
    assert provider.consume_usage()["token_usage"]["total_tokens"] == 30
