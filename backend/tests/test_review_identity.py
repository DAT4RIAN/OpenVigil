import hashlib
import json
import sys
from copy import deepcopy
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


def context():
    return {
        "review_target": {
            "scope": "maintenance_execution",
            "alternative_id": "INSPECT-1",
            "execution_plan_id": "workplan:" + "a" * 64,
        }
    }


def payload():
    return {
        "target": context()["review_target"],
        "reviews": [
            {
                "review_type": kind,
                "reviewer_agent": "review_committee",
                "outcome": "fail" if kind == "safety" else "conditional_pass",
                "public_summary": "Isolation must be verified before field work.",
                "conditions": ["Verify isolation"],
            }
            for kind in ("engineering", "safety", "economic", "resource", "compliance")
        ],
    }


@pytest.mark.parametrize("index", range(5))
def test_fabricated_reviewer_identity_is_rejected_in_schema_and_post_validation(index):
    value = payload()
    value["reviews"][index]["reviewer_agent"] = "safety_review_agent_v4.1"
    schema = _response_schema(ReviewBundle, context())
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(value))
    parsed = ReviewBundle.model_validate(value)
    with pytest.raises(ReasoningEvaluationError, match="reviewer identity"):
        evaluate_public_output(parsed, public_context=context(), minimum_diagnosis_confidence=0.5)
    # Historical records are readable without inventing replacement provenance.
    assert parsed.model_dump()["reviews"][index]["reviewer_agent"] == "safety_review_agent_v4.1"


def test_real_committee_identity_preserves_failed_review_and_legacy_schema():
    value = ReviewBundle.model_validate(payload())
    original = deepcopy(value.model_dump())
    Draft202012Validator(_response_schema(ReviewBundle, context())).validate(payload())
    result = evaluate_public_output(
        value, public_context=context(), minimum_diagnosis_confidence=0.5
    )
    assert "reviewer_identity_binding" in result["checks"]
    assert value.model_dump() == original
    assert value.reviews[1].outcome == "fail"
    assert (
        "const"
        not in ReviewBundle.model_json_schema()["$defs"]["ReviewResult"]["properties"][
            "reviewer_agent"
        ]
    )


@pytest.mark.asyncio
async def test_review_evidence_contract_is_sent_and_hashed_without_rewriting_fail(monkeypatch):
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model="provider/model",
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=json.dumps(payload())),
                )
            ],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "provider/model", timeout_seconds=5, max_retries=0, minimum_diagnosis_confidence=0.5
    )
    answer = await provider.generate(ReviewBundle, "Review supplied proposal", context())
    assert answer.reviews[1].outcome == "fail"
    assert len(calls) == 1
    messages = calls[0]["messages"]
    contract = json.loads(messages[1]["content"])["schema"]
    for rule in (
        "inventory availability only",
        "not approved operating limits",
        "Do not claim budget compliance when no budget is supplied",
        "Keep each review concise",
        "Retain every material safety finding and prerequisite",
    ):
        assert rule in contract["description"]
    expected_hash = hashlib.sha256(
        json.dumps(
            {"system": messages[0]["content"], "schema": contract},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    restrictions = contract["$defs"]["ReviewResult"]["properties"]["operating_constraints"][
        "description"
    ]
    assert "never permission" in restrictions
    assert "never an exception permitting operation" in restrictions
    assert "already-exceeded limit" in restrictions
    assert provider.consume_usage()["request_contract_sha256"] == expected_hash
    bad_review = payload()
    bad_review["reviews"][0]["review_type"] = "unregistered_review"
    assert list(Draft202012Validator(contract).iter_errors(bad_review))
    assert (
        "enum"
        not in ReviewBundle.model_json_schema()["$defs"]["ReviewResult"]["properties"][
            "review_type"
        ]
    )


@pytest.mark.asyncio
async def test_provider_rejects_fabricated_identity_without_retry_and_retains_paid_usage(
    monkeypatch,
):
    value = payload()
    value["reviews"][0]["reviewer_agent"] = "engineering_review_agent_v3.2"
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model="provider/model",
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=ReviewBundle.model_validate(value).model_dump_json()
                    ),
                )
            ],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "provider/model", timeout_seconds=5, max_retries=0, minimum_diagnosis_confidence=0.5
    )
    with pytest.raises(ReasoningEvaluationError, match="reviewer identity"):
        await provider.generate(ReviewBundle, "Review the supplied proposal", context())
    assert len(calls) == 1
    usage = provider.consume_usage()
    assert usage["token_usage"]["total_tokens"] == 30
    assert usage["evaluation_result"]["status"] == "failed"


@pytest.mark.asyncio
async def test_workflow_rejects_provider_bypass_before_review_persistence(app, client, monkeypatch):
    original = DeterministicReasoningProvider.generate

    async def generate(self, schema, instruction, public_context):
        value = await original(self, schema, instruction, public_context)
        if schema is ReviewBundle:
            value.reviews[0].reviewer_agent = "invented_committee_v99"
        return value

    monkeypatch.setattr(DeterministicReasoningProvider, "generate", generate)
    response = await client.post(
        "/api/v1/scada/ingest",
        json={
            "samples": [
                {
                    "source_event_id": "REVIEW-IDENTITY-SYNTHETIC",
                    "turbine_id": "WT-023",
                    "observed_at": "2026-09-28T00:00:00Z",
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
    assert "reviewer identity" in response.json()["error"]["message"]
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
    assert not detail["public_state"].get("reviews")
