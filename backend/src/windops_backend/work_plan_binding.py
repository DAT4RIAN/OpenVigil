"""Bind model proposals to server-controlled execution plans without rewriting actions."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from windops_backend.schemas import MissionAnalysisProfile
from windops_backend.work_order_templates import default_work_order_plan


def describe_execution_plan(profile: MissionAnalysisProfile, turbine_id: str) -> dict[str, Any]:
    plan = profile.work_order_plan or default_work_order_plan(
        component=profile.component,
        turbine_id=turbine_id,
        primary_variable=profile.primary_variable,
    )
    body = plan.model_dump(mode="json")
    identity = {
        "version": 1,
        "turbine_id": turbine_id,
        "component": profile.component,
        "primary_variable": profile.primary_variable,
        "plan": body,
    }
    digest = hashlib.sha256(
        json.dumps(
            identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()
    return {"execution_plan_id": "workplan:" + digest, "action": plan.title, "plan": body}


def validate_execution_binding(
    alternative: Mapping[str, Any],
    available_plans: Sequence[Mapping[str, Any]],
    *,
    require_bound: bool = False,
) -> None:
    plan_id = alternative.get("execution_plan_id")
    if plan_id is None:
        if require_bound:
            raise ValueError(
                "the selected alternative has no governed execution plan; request revision"
            )
        return
    plan = next((item for item in available_plans if item["execution_plan_id"] == plan_id), None)
    if plan is None:
        raise ValueError("the selected execution plan is unknown or has changed; request revision")
    if alternative.get("action") != plan["action"]:
        raise ValueError("the selected action does not match its governed execution plan")
