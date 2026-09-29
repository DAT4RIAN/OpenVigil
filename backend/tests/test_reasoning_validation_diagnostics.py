import json
import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from pydantic_core import PydanticCustomError

from windops_backend.agents.reasoning import LiteLLMReasoningProvider, ReviewBundle


def review_payload():
    return {
        "reviews": [
            {
                "review_type": kind,
                "reviewer_agent": "review_committee",
                "outcome": "fail",
                "public_summary": "Synthetic review requires isolation verification.",
            }
            for kind in ("engineering", "safety", "economic", "resource", "compliance")
        ],
    }


async def rejected_usage(monkeypatch, content, schema=ReviewBundle):
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model="provider/model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            choices=[
                SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))
            ],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    provider = LiteLLMReasoningProvider(
        "provider/model", timeout_seconds=5, max_retries=0, minimum_diagnosis_confidence=0.5
    )
    with pytest.raises(ValidationError):
        await provider.generate(
            schema,
            "Review the supplied plan",
            {
                "review_target": {
                    "scope": "maintenance_execution",
                    "alternative_id": "TEST-1",
                    "execution_plan_id": "workplan:" + "a" * 64,
                }
            },
        )
    assert len(calls) == 1
    usage = provider.consume_usage()
    assert usage["token_usage"]["total_tokens"] == 30
    assert usage["evaluation_result"]["status"] == "failed"
    assert usage["evaluation_result"]["error_code"] == "ValidationError"
    assert provider.consume_usage() == {}
    return usage


@pytest.mark.asyncio
async def test_missing_review_field_identifies_nested_path_without_response(monkeypatch):
    payload = review_payload()
    del payload["reviews"][2]["outcome"]
    payload["reviews"][2]["public_summary"] = "PRIVATE-RESPONSE-MARKER"
    usage = await rejected_usage(monkeypatch, json.dumps(payload))
    assert usage["evaluation_result"]["validation"] == {
        "stage": "response_schema",
        "error_count": 1,
        "errors": [{"path": ["reviews", 2, "outcome"], "type": "missing"}],
        "truncated": False,
    }
    assert "PRIVATE-RESPONSE-MARKER" not in json.dumps(usage)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "invalid_value", "error_type"),
    [
        ("outcome", "PRIVATE-INVALID-ENUM", "literal_error"),
        ("conditions", "PRIVATE-NOT-A-LIST", "list_type"),
    ],
)
async def test_enum_and_type_errors_exclude_invalid_values(
    monkeypatch, field, invalid_value, error_type
):
    payload = review_payload()
    payload["reviews"][0][field] = invalid_value
    usage = await rejected_usage(monkeypatch, json.dumps(payload))
    assert usage["evaluation_result"]["validation"]["errors"] == [
        {"path": ["reviews", 0, field], "type": error_type}
    ]
    assert invalid_value not in json.dumps(usage)


@pytest.mark.asyncio
async def test_invalid_json_excludes_parser_message_and_content(monkeypatch):
    usage = await rejected_usage(monkeypatch, '{"PRIVATE-JSON-MARKER": invalid}')
    assert usage["evaluation_result"]["validation"]["errors"] == [
        {"path": [], "type": "json_invalid"}
    ]
    assert "PRIVATE-JSON-MARKER" not in json.dumps(usage)


@pytest.mark.asyncio
async def test_review_coverage_validator_remains_rejected(monkeypatch):
    payload = review_payload()
    payload["reviews"][1]["review_type"] = "engineering"
    usage = await rejected_usage(monkeypatch, json.dumps(payload))
    assert usage["evaluation_result"]["validation"]["errors"] == [
        {"path": [], "type": "value_error"}
    ]


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int


@pytest.mark.asyncio
async def test_untrusted_extra_keys_are_redacted_and_error_list_is_bounded(monkeypatch):
    payload = {f"PRIVATE-KEY-{index}": "PRIVATE-VALUE" for index in range(30)}
    usage = await rejected_usage(monkeypatch, json.dumps(payload), StrictPayload)
    diagnostic = usage["evaluation_result"]["validation"]
    assert diagnostic["error_count"] == 31
    assert len(diagnostic["errors"]) == 20
    assert diagnostic["truncated"] is True
    assert {"path": ["<redacted>"], "type": "extra_forbidden"} in diagnostic["errors"]
    assert all(
        error
        in (
            {"path": ["count"], "type": "missing"},
            {"path": ["<redacted>"], "type": "extra_forbidden"},
        )
        for error in diagnostic["errors"]
    )
    assert "PRIVATE-" not in json.dumps(usage)


class CustomErrorPayload(BaseModel):
    count: int

    @field_validator("count")
    @classmethod
    def reject_count(cls, value):
        raise PydanticCustomError(
            "PRIVATE-CUSTOM-CODE", "PRIVATE-MESSAGE {value}", {"value": value}
        )


@pytest.mark.asyncio
async def test_custom_error_code_and_message_are_not_exposed(monkeypatch):
    usage = await rejected_usage(monkeypatch, '{"count": 17}', CustomErrorPayload)
    assert usage["evaluation_result"]["validation"]["errors"] == [
        {"path": ["count"], "type": "custom_error"}
    ]
    assert "PRIVATE-" not in json.dumps(usage)
