import json
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from windops_backend.config import Settings
from windops_backend.schemas import (
    MaintenanceAlternative,
    PublicDiagnosis,
    ReviewResult,
)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AlternativeBundle(BaseModel):
    alternatives: list[MaintenanceAlternative]


class ReviewBundle(BaseModel):
    reviews: list[ReviewResult]


class PublicReasoningProvider(Protocol):
    async def generate(
        self, schema: type[SchemaT], instruction: str, public_context: dict[str, Any]
    ) -> SchemaT: ...

    def reset_usage(self) -> None: ...

    def consume_usage(self) -> dict[str, Any]: ...


class DeterministicReasoningProvider:
    """Repeatable engineering policy used for tests and offline demonstrations."""

    def __init__(self) -> None:
        self._last_usage: dict[str, Any] = {}

    def reset_usage(self) -> None:
        self._last_usage = {}

    def consume_usage(self) -> dict[str, Any]:
        usage, self._last_usage = self._last_usage, {}
        return usage

    async def generate(
        self, schema: type[SchemaT], instruction: str, public_context: dict[str, Any]
    ) -> SchemaT:
        del instruction
        self._last_usage = {
            "provider": "deterministic",
            "model": "engineering-policy-2026.08",
            "token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "source": "deterministic_test_no_model",
            },
        }
        if schema is PublicDiagnosis:
            evidence_refs = [
                str(item["evidence_id"]) for item in public_context.get("evidence", [])
            ]
            value: BaseModel = PublicDiagnosis(
                failure_mode="early_main_bearing_degradation",
                component="main_bearing",
                confidence=0.87,
                conclusion=(
                    "Main-bearing RMS and temperature trends are consistent with early degradation."
                ),
                evidence_refs=evidence_refs,
            )
        elif schema is AlternativeBundle:
            value = AlternativeBundle(
                alternatives=[
                    MaintenanceAlternative(
                        alternative_id="ALT-A",
                        title="Immediate shutdown and inspection",
                        action="Stop WT-023 and inspect immediately.",
                        safety_risk="low",
                        estimated_downtime_hours=18,
                        estimated_cost_cny=420000,
                    ),
                    MaintenanceAlternative(
                        alternative_id="ALT-B",
                        title="Derate and inspect within 72 hours",
                        action=(
                            "Derate to 70%, increase monitoring, then inspect in the safe window."
                        ),
                        safety_risk="medium",
                        estimated_downtime_hours=10,
                        estimated_cost_cny=260000,
                        recommended=True,
                    ),
                    MaintenanceAlternative(
                        alternative_id="ALT-C",
                        title="Continue with enhanced monitoring",
                        action="Continue operation and acquire vibration data every 15 minutes.",
                        safety_risk="high",
                        estimated_downtime_hours=0,
                        estimated_cost_cny=35000,
                    ),
                ]
            )
        elif schema is ReviewBundle:
            value = ReviewBundle(
                reviews=[
                    ReviewResult(
                        review_type="engineering",
                        reviewer_agent="engineering_review_agent",
                        outcome="conditional_pass",
                        public_summary="Derated operation is acceptable for no more than 72 hours.",
                        conditions=["vibration RMS must remain below 5.2 mm/s"],
                    ),
                    ReviewResult(
                        review_type="safety",
                        reviewer_agent="safety_review_agent",
                        outcome="conditional_pass",
                        public_summary=(
                            "Field work requires isolation and offshore access approval."
                        ),
                        conditions=["human approval", "LOTO", "suitable marine weather"],
                    ),
                    ReviewResult(
                        review_type="economic",
                        reviewer_agent="economic_review_agent",
                        outcome="pass",
                        public_summary=(
                            "Alternative B balances failure exposure and production loss."
                        ),
                    ),
                    ReviewResult(
                        review_type="resource",
                        reviewer_agent="resource_review_agent",
                        outcome="pass",
                        public_summary="Crew, vessel, and bearing kit are available.",
                    ),
                    ReviewResult(
                        review_type="compliance",
                        reviewer_agent="compliance_agent",
                        outcome="pass",
                        public_summary=(
                            "The inspection plan follows the controlled maintenance procedure."
                        ),
                    ),
                ]
            )
        else:  # pragma: no cover - makes unsupported schemas fail loudly
            raise TypeError(f"Unsupported deterministic schema: {schema.__name__}")
        return schema.model_validate(value.model_dump())


class LiteLLMReasoningProvider:
    """Production structured-output adapter; prompts explicitly exclude private reasoning."""

    def __init__(self, model: str) -> None:
        self.model = model
        self._last_usage: dict[str, Any] = {}

    def reset_usage(self) -> None:
        self._last_usage = {}

    def consume_usage(self) -> dict[str, Any]:
        usage, self._last_usage = self._last_usage, {}
        return usage

    async def generate(
        self, schema: type[SchemaT], instruction: str, public_context: dict[str, Any]
    ) -> SchemaT:
        # LiteLLM imports tokenizer data in some releases. Keep that production-only
        # initialization out of deterministic/offline test processes.
        import litellm

        response = await litellm.acompletion(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return one JSON object matching the supplied schema. Include only public, "
                        "auditable conclusions, evidence references, actions, and review "
                        "summaries. "
                        "Never include hidden reasoning or chain-of-thought."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": instruction,
                            "schema": schema.model_json_schema(),
                            "public_context": public_context,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise ValueError("LiteLLM returned no structured content")
        raw_usage = getattr(response, "usage", None)
        if raw_usage is not None and hasattr(raw_usage, "model_dump"):
            raw_usage = raw_usage.model_dump()
        usage = raw_usage if isinstance(raw_usage, dict) else {}
        self._last_usage = {
            "provider": "litellm",
            "model": str(getattr(response, "model", None) or self.model),
            "token_usage": {
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
                "total_tokens": int(usage.get("total_tokens", 0)),
                "source": "provider_reported",
            },
        }
        return schema.model_validate_json(content)


def build_reasoning_provider(settings: Settings) -> PublicReasoningProvider:
    if settings.agent_mode == "litellm":
        return LiteLLMReasoningProvider(settings.litellm_model)
    return DeterministicReasoningProvider()
