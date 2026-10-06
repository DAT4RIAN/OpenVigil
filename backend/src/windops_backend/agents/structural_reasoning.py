"""Offline software policy. Actual field conclusions still require independent human review."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from windops_backend.schema_operations import MaintenanceAlternative, ReviewResult
from windops_backend.schema_structural import aware
from windops_backend.schema_structural_workflow import StructuralScreeningOutput


def deterministic_structural_output(schema: type[BaseModel], context: dict[str, Any]) -> BaseModel:
    from windops_backend.agents.reasoning_contracts import (
        REVIEW_COMMITTEE_AGENT,
        AlternativeBundle,
        ReviewBundle,
        _review_target,
    )

    structural = context["structural_context"]
    missing = structural["missing_evidence"]
    if schema is StructuralScreeningOutput:
        comparison = structural["comparison"]
        return StructuralScreeningOutput(
            component=context["analysis_profile"]["component"],
            failure_mode="insufficient_structural_evidence" if missing else "structural_screening",
            conclusion=(
                f"Structural comparison status: {comparison['status']}. "
                "Registered measurements support human review and calibrated retest only; "
                "damage and operating qualification remain unverified."
            ),
            evidence_refs=[item["evidence_id"] for item in context["evidence"]],
            missing_evidence=missing,
        )
    if schema is AlternativeBundle:
        plan = context["available_execution_plans"][0]
        duration = plan["plan"]["safety_plan"]["estimated_duration_hours"]
        now = datetime.now(UTC)
        weather = next(
            (
                row
                for row in context["weather"]
                if row["suitable"]
                and aware(datetime.fromisoformat(row["ends_at"])) > now
                and (
                    aware(datetime.fromisoformat(row["ends_at"]))
                    - max(now, aware(datetime.fromisoformat(row["starts_at"])))
                ).total_seconds()
                >= duration * 3600
            ),
            None,
        )
        return AlternativeBundle(
            alternatives=[
                MaintenanceAlternative(
                    alternative_id="STRUCT-RETEST",
                    title=plan["plan"]["title"],
                    action=plan["action"],
                    execution_plan_id=plan["execution_plan_id"],
                    safety_risk="medium",
                    estimated_downtime_hours=None,
                    estimated_cost_cny=None,
                    estimated_energy_loss_mwh=None,
                    weather_window_id=weather["window_id"] if weather else None,
                    required_resources=plan["plan"]["required_resource_types"],
                    recommended=True,
                    rationale=(
                        "Acquire a calibrated retest under human-approved permits, "
                        "source-reviewed procedure and site conditions; costs and energy "
                        "impact are unassessed."
                    ),
                ),
                MaintenanceAlternative(
                    alternative_id="STRUCT-REVIEW",
                    title="Escalate evidence gaps to the responsible engineer",
                    action="Request a governed engineering investigation plan",
                    safety_risk="medium",
                    rationale=(
                        "Additional investigation requires a separate reviewed scope "
                        "and execution plan; operating authority is unresolved."
                    ),
                ),
                MaintenanceAlternative(
                    alternative_id="STRUCT-PROCEDURE",
                    title="Acquire applicable controlled procedure and acceptance limits",
                    action="Request a governed document and calibration verification plan",
                    safety_risk="medium",
                    rationale=(
                        "Evidence gaps require a responsible engineer to identify "
                        "applicable source documents and acceptance limits "
                        "before further execution."
                    ),
                ),
            ]
        )
    if schema is ReviewBundle:
        plan = context.get("execution_plan")
        resources = context["resources"]
        unavailable = (
            []
            if plan is None
            else [
                kind
                for kind in plan["plan"]["required_resource_types"]
                if not any(
                    row["resource_type"] == kind
                    and row["status"] == "available"
                    and row["quantity"] > 0
                    for row in resources
                )
            ]
        )
        conditions = {
            "engineering": [
                "independent approval of the exact evidence claim "
                "and declared acceptance procedure",
                "responsible engineer must review calibrated retest before closure",
            ],
            "safety": [
                "human approval, site work permit, isolation and safe access",
                "recheck site weather against the controlled work procedure",
            ],
            "economic": ["confirm the budget; cost and energy impact are unassessed"],
            "resource": [
                "verify measurement-equipment calibration and crew qualification",
                "reserve actual resources for the work window",
            ],
            "compliance": [
                "verify applicable controlled site procedure and permits; "
                "no tensioning authority is included"
            ],
        }
        return ReviewBundle(
            target=_review_target(context),
            reviews=[
                ReviewResult(
                    review_type=kind,
                    reviewer_agent=REVIEW_COMMITTEE_AGENT,
                    outcome="fail"
                    if plan is None or (kind == "resource" and unavailable)
                    else "conditional_pass",
                    public_summary=f"{kind} review requires controlled retest prerequisites."
                    + (
                        f" Missing available resource types: {', '.join(unavailable)}."
                        if kind == "resource" and unavailable
                        else ""
                    ),
                    conditions=items,
                    operating_constraints=[
                        "No turbine operation or rotation while personnel are exposed; "
                        "verified isolation is required before work. Operating decisions "
                        "require the responsible human and approved procedure."
                    ]
                    if kind == "safety"
                    else [],
                )
                for kind, items in conditions.items()
            ],
        )
    raise TypeError(f"unsupported structural schema: {schema.__name__}")
