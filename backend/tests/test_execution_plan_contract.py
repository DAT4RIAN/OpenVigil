from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from windops_backend.agents.reasoning import (
    AlternativeBundle,
    ReasoningEvaluationError,
    _response_schema,
    evaluate_public_output,
)
from windops_backend.schemas import MissionAnalysisProfile, WorkOrderPlan
from windops_backend.work_plan_binding import describe_execution_plan


def profile() -> MissionAnalysisProfile:
    return MissionAnalysisProfile(
        component="main_bearing",
        primary_variable="main_bearing_vibration_rms",
        knowledge_query="main bearing inspection",
    )


def test_no_available_plan_still_produces_valid_proposal_schema() -> None:
    schema = _response_schema(AlternativeBundle, {})
    Draft202012Validator.check_schema(schema)
    payload = {
        "alternatives": [
            proposal("Replacement proposal pending a controlled plan", None, recommended=True),
            proposal("Continue observation pending assessment", None, recommended=False),
        ]
    }
    Draft202012Validator(schema).validate(payload)
    evaluate_public_output(
        AlternativeBundle.model_validate(payload),
        public_context={},
        minimum_diagnosis_confidence=0.5,
    )


def proposal(action: str, plan_id: str | None, *, recommended: bool) -> dict:
    return {
        "alternative_id": "recommended" if recommended else "other",
        "title": "Maintenance option",
        "action": action,
        "execution_plan_id": plan_id,
        "safety_risk": "medium",
        "estimated_downtime_hours": 10,
        "estimated_cost_cny": 1000,
        "estimated_energy_loss_mwh": 10,
        "deterioration_risk_percent": None,
        "rationale": "Synthetic regression proposal",
        "recommended": recommended,
    }


@pytest.mark.parametrize("mutation", ["tasks", "safety", "closure", "asset"])
def test_plan_binding_tracks_the_entire_controlled_plan(mutation: str) -> None:
    original = profile()
    descriptor = describe_execution_plan(original, "WT-023")
    changed = deepcopy(descriptor["plan"])
    if mutation == "tasks":
        changed["tasks"][0]["title"] += " with additional verified measurement"
    elif mutation == "safety":
        changed["safety_plan"]["estimated_duration_hours"] = 11
    elif mutation == "closure":
        changed["healthy_threshold"] = 83
        changed["tasks"][-1]["measurement_schema"]["properties"]["turbine_health_score"][
            "minimum"
        ] = 83
    modified = original.model_copy(
        update={"work_order_plan": WorkOrderPlan.model_validate(changed)}
    )
    new = describe_execution_plan(modified, "WT-OTHER" if mutation == "asset" else "WT-023")
    assert new["execution_plan_id"] != descriptor["execution_plan_id"]
    assert describe_execution_plan(original, "WT-023") == descriptor


@pytest.mark.parametrize("invalid", ["action", "unknown_id"])
def test_model_schema_and_independent_evaluator_reject_false_binding(invalid: str) -> None:
    plan = describe_execution_plan(profile(), "WT-023")
    context = {"available_execution_plans": [plan]}
    bound = proposal(plan["action"], plan["execution_plan_id"], recommended=True)
    unbound = proposal(
        "Propose a replacement pending a governed work plan", None, recommended=False
    )
    payload = {"alternatives": [bound, unbound]}
    schema = _response_schema(AlternativeBundle, context)
    Draft202012Validator(schema).validate(payload)
    result = evaluate_public_output(
        AlternativeBundle.model_validate(payload),
        public_context=context,
        minimum_diagnosis_confidence=0.5,
    )
    assert "execution_plan_binding" in result["checks"]
    if invalid == "action":
        bound["action"] = "Replace the bearing, not inspect it"
    else:
        bound["execution_plan_id"] = "unregistered-replacement-v1"
    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ReasoningEvaluationError):
        evaluate_public_output(
            AlternativeBundle.model_validate(payload),
            public_context=context,
            minimum_diagnosis_confidence=0.5,
        )
    assert "allOf" not in AlternativeBundle.model_json_schema()["$defs"]["MaintenanceAlternative"]
