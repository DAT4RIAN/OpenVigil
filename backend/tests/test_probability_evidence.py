from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from windops_backend.agents.reasoning import (
    AlternativeBundle,
    DeterministicReasoningProvider,
    ReasoningEvaluationError,
    _response_schema,
    evaluate_public_output,
)
from windops_backend.schemas import MaintenanceAlternative


def proposal(identifier: str, *, recommended: bool) -> dict:
    return {
        "alternative_id": identifier,
        "title": "Proposed inspection",
        "action": "Inspection pending a governed execution plan",
        "execution_plan_id": None,
        "safety_risk": "medium",
        "estimated_downtime_hours": 10,
        "estimated_cost_cny": 1000,
        "estimated_energy_loss_mwh": 8,
        "deterioration_risk_percent": None,
        "rationale": "Condition evidence does not provide a calibrated probability.",
        "recommended": recommended,
    }


def test_unknown_probability_and_legacy_records_remain_distinct() -> None:
    payload = proposal("A", recommended=True)
    assert MaintenanceAlternative.model_validate(payload).deterioration_risk_percent is None
    payload.pop("deterioration_risk_percent")
    assert MaintenanceAlternative.model_validate(payload).deterioration_risk_percent is None
    for value in (0, 12, 100):
        payload["deterioration_risk_percent"] = value
        assert MaintenanceAlternative.model_validate(payload).deterioration_risk_percent == value


@pytest.mark.parametrize("invented_probability", [0, 12, 100])
def test_generated_probabilities_are_rejected_without_a_calibrated_probability_contract(
    invented_probability: int,
) -> None:
    payload = {"alternatives": [proposal("A", recommended=True), proposal("B", recommended=False)]}
    # Neither an anomaly score nor an arbitrary extra context property constitutes
    # a governed, calibrated probability provider in the current implementation.
    context = {"condition_evidence": {"inputs": {"anomaly_score": 0.86}}, "probability": 12}
    for alternative in payload["alternatives"]:
        alternative["deterioration_risk_percent"] = invented_probability
    parsed = AlternativeBundle.model_validate(payload)
    with pytest.raises(ReasoningEvaluationError, match="probability"):
        evaluate_public_output(parsed, public_context=context, minimum_diagnosis_confidence=0.5)


def test_provider_schema_requires_unknown_probability_without_mutating_the_public_schema() -> None:
    original = deepcopy(AlternativeBundle.model_json_schema())
    schema = _response_schema(AlternativeBundle, {})
    Draft202012Validator.check_schema(schema)
    payload = {"alternatives": [proposal("A", recommended=True), proposal("B", recommended=False)]}
    Draft202012Validator(schema).validate(payload)
    result = evaluate_public_output(
        AlternativeBundle.model_validate(payload),
        public_context={},
        minimum_diagnosis_confidence=0.5,
    )
    assert "no_unsupported_probability" in result["checks"]
    payload["alternatives"][0]["deterioration_risk_percent"] = 0
    assert list(Draft202012Validator(schema).iter_errors(payload))
    assert AlternativeBundle.model_json_schema() == original


@pytest.mark.asyncio
async def test_engineering_provider_does_not_invent_calibrated_probabilities() -> None:
    result = await DeterministicReasoningProvider().generate(
        AlternativeBundle, "Generate public alternatives", {"turbine_id": "WT-023"}
    )
    assert all(
        alternative.deterioration_risk_percent is None for alternative in result.alternatives
    )
