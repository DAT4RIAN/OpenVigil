import asyncio
import json
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, Field, model_validator

from windops_backend.config import Settings
from windops_backend.schemas import (
    MaintenanceAlternative,
    PublicDiagnosis,
    ReviewResult,
)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AlternativeBundle(BaseModel):
    alternatives: list[MaintenanceAlternative] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def validate_governed_choice(self) -> "AlternativeBundle":
        identifiers = [item.alternative_id for item in self.alternatives]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("maintenance alternative IDs must be unique")
        recommended = [item for item in self.alternatives if item.recommended]
        if len(recommended) != 1:
            raise ValueError("exactly one maintenance alternative must be recommended")
        if recommended[0].safety_risk == "critical":
            raise ValueError("a critical-safety-risk alternative cannot be recommended")
        return self


class ReviewBundle(BaseModel):
    reviews: list[ReviewResult] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_review_coverage(self) -> "ReviewBundle":
        required = {"engineering", "safety", "economic", "resource", "compliance"}
        observed = [item.review_type for item in self.reviews]
        if set(observed) != required or len(set(observed)) != len(observed):
            raise ValueError("reviews must cover each governed review type exactly once")
        return self


class ReasoningEvaluationError(ValueError):
    pass


class ReasoningProviderUnavailableError(RuntimeError):
    pass


def evaluate_public_output(
    value: BaseModel,
    *,
    public_context: dict[str, Any],
    minimum_diagnosis_confidence: float,
) -> dict[str, Any]:
    checks: list[str] = ["strict_schema"]
    if isinstance(value, PublicDiagnosis):
        profile = public_context.get("analysis_profile", {})
        expected_component = str(profile.get("component", ""))
        allowed_evidence = {
            str(item.get("evidence_id"))
            for item in public_context.get("evidence", [])
            if isinstance(item, dict) and item.get("evidence_id")
        }
        if value.component != expected_component:
            raise ReasoningEvaluationError("diagnosis component does not match governed scope")
        if len(set(value.evidence_refs)) != len(value.evidence_refs):
            raise ReasoningEvaluationError("diagnosis evidence references must be unique")
        if not set(value.evidence_refs).issubset(allowed_evidence):
            raise ReasoningEvaluationError("diagnosis cites evidence outside the governed context")
        if value.confidence < minimum_diagnosis_confidence:
            raise ReasoningEvaluationError("diagnosis confidence is below the release gate")
        checks.extend(["component_scope", "evidence_grounding", "confidence_gate"])
    elif isinstance(value, AlternativeBundle):
        checks.extend(["alternative_uniqueness", "single_recommendation", "safety_gate"])
    elif isinstance(value, ReviewBundle):
        checks.append("review_coverage")
    return {"status": "passed", "checks": checks, "score": 1.0}


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
        profile = public_context.get("analysis_profile", {})
        component = str(profile.get("component", "main_bearing"))
        display_component = component.replace("_", " ")
        turbine_id = str(public_context.get("turbine_id", "the turbine"))
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
            failure_mode_hint = str(profile.get("failure_mode_hint", "")).strip()
            failure_mode = (
                "early_main_bearing_degradation"
                if component == "main_bearing"
                else (failure_mode_hint or f"suspected {display_component} degradation")
                .lower()
                .replace(" ", "_")
                .replace("-", "_")
            )
            conclusion = (
                "Main-bearing RMS and temperature trends are consistent with early degradation."
                if component == "main_bearing"
                else (
                    f"The governed evidence is consistent with a developing "
                    f"{display_component} condition requiring controlled inspection."
                )
            )
            value: BaseModel = PublicDiagnosis(
                failure_mode=failure_mode,
                component=component,
                confidence=0.87,
                conclusion=conclusion,
                evidence_refs=evidence_refs,
            )
        elif schema is AlternativeBundle:
            asset_label = "WT-023" if turbine_id == "the turbine" else turbine_id
            value = AlternativeBundle(
                alternatives=[
                    MaintenanceAlternative(
                        alternative_id="ALT-A",
                        title="Immediate shutdown and inspection",
                        action=f"Stop {asset_label} and inspect {display_component} immediately.",
                        safety_risk="low",
                        estimated_downtime_hours=18,
                        estimated_cost_cny=420000,
                        estimated_energy_loss_mwh=24,
                        deterioration_risk_percent=3,
                        weather_window_id="WEATHER-WINDOW-WT023",
                        required_resources=["crew", "vessel", "spare_part"],
                        rationale="Minimizes deterioration risk but has the highest outage cost.",
                    ),
                    MaintenanceAlternative(
                        alternative_id="ALT-B",
                        title="Derate and inspect within 72 hours",
                        action=(
                            f"Derate {asset_label} to 70%, increase monitoring, then inspect "
                            f"{display_component} in the safe window."
                        ),
                        safety_risk="medium",
                        estimated_downtime_hours=10,
                        estimated_cost_cny=260000,
                        estimated_energy_loss_mwh=14,
                        deterioration_risk_percent=12,
                        weather_window_id="WEATHER-WINDOW-WT023",
                        required_resources=["crew", "vessel", "spare_part"],
                        rationale="Balances controlled derating, safe access, and repair cost.",
                        recommended=True,
                    ),
                    MaintenanceAlternative(
                        alternative_id="ALT-C",
                        title="Continue with enhanced monitoring",
                        action=(
                            f"Continue operation and acquire {display_component} condition data "
                            "every 15 minutes."
                        ),
                        safety_risk="high",
                        estimated_downtime_hours=0,
                        estimated_cost_cny=35000,
                        estimated_energy_loss_mwh=5,
                        deterioration_risk_percent=42,
                        weather_window_id=None,
                        required_resources=[],
                        rationale="Avoids an immediate outage but retains material failure risk.",
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

    def __init__(
        self,
        model: str,
        *,
        timeout_seconds: int,
        max_retries: int,
        minimum_diagnosis_confidence: float,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.minimum_diagnosis_confidence = minimum_diagnosis_confidence
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

        degradation_policy = {
            "mode": "fail_closed",
            "automatic_deterministic_fallback": False,
            "human_review_required": True,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
        }
        self._last_usage = {
            "provider": "litellm",
            "model": self.model,
            "token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "source": "unavailable_before_provider_response",
            },
            "evaluation_result": {"status": "pending", "checks": []},
            "degradation_policy": degradation_policy,
        }
        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await litellm.acompletion(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Return one JSON object matching the supplied schema. Include only "
                                "public, auditable conclusions, evidence references, actions, and "
                                "review summaries. Never include hidden reasoning or "
                                "chain-of-thought."
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
                    num_retries=self.max_retries,
                    timeout=self.timeout_seconds,
                )
            content = response.choices[0].message.content
            if not isinstance(content, str):
                raise ReasoningProviderUnavailableError("LiteLLM returned no structured content")
            value = schema.model_validate_json(content)
            evaluation = evaluate_public_output(
                value,
                public_context=public_context,
                minimum_diagnosis_confidence=self.minimum_diagnosis_confidence,
            )
        except TimeoutError as exc:
            self._last_usage["evaluation_result"] = {
                "status": "failed",
                "error_code": "provider_timeout",
            }
            raise ReasoningProviderUnavailableError("LiteLLM request timed out") from exc
        except Exception as exc:
            self._last_usage["evaluation_result"] = {
                "status": "failed",
                "error_code": type(exc).__name__,
            }
            raise
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
            "evaluation_result": evaluation,
            "degradation_policy": degradation_policy,
        }
        return value


def build_reasoning_provider(settings: Settings) -> PublicReasoningProvider:
    if settings.agent_mode == "litellm":
        return LiteLLMReasoningProvider(
            settings.litellm_model,
            timeout_seconds=settings.litellm_timeout_seconds,
            max_retries=settings.litellm_max_retries,
            minimum_diagnosis_confidence=settings.litellm_minimum_diagnosis_confidence,
        )
    return DeterministicReasoningProvider()
