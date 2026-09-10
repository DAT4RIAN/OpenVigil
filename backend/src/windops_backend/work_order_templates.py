from __future__ import annotations

from typing import Any

from windops_backend.schemas import (
    BorescopeTaskMeasurement,
    ClosureTaskMeasurement,
    LubricationTaskMeasurement,
    TemperatureTaskMeasurement,
    VibrationTaskMeasurement,
    WorkOrderPlan,
    WorkOrderTaskTemplate,
)


def _schema(model: type[Any]) -> dict[str, Any]:
    return dict(model.model_json_schema())


def default_work_order_plan(
    *, component: str, turbine_id: str, primary_variable: str
) -> WorkOrderPlan:
    """Return a controlled server-side template when no governed plan was supplied."""

    if component == "main_bearing":
        return WorkOrderPlan(
            title=f"{turbine_id} Main Bearing Inspection",
            priority="high",
            required_resource_types=["crew", "vessel", "spare_part"],
            safety_plan={
                "ppe": ["offshore survival PPE", "fall-arrest harness", "electrical gloves"],
                "required_tools": ["vibration analyzer", "thermal camera", "borescope"],
                "spare_parts": ["GW165 main-bearing kit"],
                "procedures": ["LOTO", "offshore access permit", "toolbox talk"],
                "estimated_duration_hours": 10,
                "risk_level": "high",
            },
            tasks=[
                WorkOrderTaskTemplate(
                    title="Inspect main-bearing lubrication condition",
                    schema_version="main-bearing-lubrication-v1",
                    measurement_schema=_schema(LubricationTaskMeasurement),
                ),
                WorkOrderTaskTemplate(
                    title="Acquire vibration spectrum and RMS data",
                    schema_version="main-bearing-vibration-v1",
                    measurement_schema=_schema(VibrationTaskMeasurement),
                ),
                WorkOrderTaskTemplate(
                    title="Measure and record bearing temperature",
                    schema_version="main-bearing-temperature-v1",
                    measurement_schema=_schema(TemperatureTaskMeasurement),
                ),
                WorkOrderTaskTemplate(
                    title="Perform main-bearing borescope inspection",
                    schema_version="main-bearing-borescope-v1",
                    measurement_schema=_schema(BorescopeTaskMeasurement),
                ),
                WorkOrderTaskTemplate(
                    title="Upload traceable field photographs",
                    schema_version="main-bearing-closure-v1",
                    measurement_schema=_schema(ClosureTaskMeasurement),
                ),
            ],
            closure_health_score_field="turbine_health_score",
            healthy_threshold=82,
        )

    display_component = component.replace("_", " ")
    return WorkOrderPlan(
        title=f"{turbine_id} {display_component.title()} Inspection",
        priority="high",
        required_resource_types=["crew", "vessel"],
        safety_plan={
            "ppe": ["site-approved PPE", "fall-arrest harness"],
            "required_tools": ["calibrated condition-monitoring instrument"],
            "procedures": ["LOTO", "site access permit", "toolbox talk"],
            "estimated_duration_hours": 8,
            "risk_level": "high",
        },
        tasks=[
            WorkOrderTaskTemplate(
                title=f"Inspect {display_component} condition and isolation controls",
                schema_version=f"{component}-inspection-v1",
                measurement_schema={
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "inspection_result": {"type": "string", "const": "acceptable"},
                        "observations": {"type": "string", "minLength": 3, "maxLength": 2000},
                    },
                    "required": ["inspection_result", "observations"],
                },
            ),
            WorkOrderTaskTemplate(
                title=f"Capture calibrated {primary_variable} measurement",
                schema_version=f"{component}-condition-measurement-v1",
                measurement_schema={
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "measured_value": {"type": "number"},
                        "unit": {"type": "string", "minLength": 1, "maxLength": 24},
                        "within_operational_limit": {"type": "boolean", "const": True},
                    },
                    "required": ["measured_value", "unit", "within_operational_limit"],
                },
            ),
            WorkOrderTaskTemplate(
                title="Verify health recovery and authorize return to service",
                schema_version=f"{component}-closure-v1",
                measurement_schema={
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "photo_count": {"type": "integer", "minimum": 3, "maximum": 100},
                        "component_health_score": {
                            "type": "number",
                            "minimum": 80,
                            "maximum": 100,
                        },
                        "turbine_health_score": {
                            "type": "number",
                            "minimum": 80,
                            "maximum": 100,
                        },
                        "return_to_service": {"type": "boolean", "const": True},
                    },
                    "required": [
                        "photo_count",
                        "component_health_score",
                        "turbine_health_score",
                        "return_to_service",
                    ],
                },
            ),
        ],
        closure_health_score_field="turbine_health_score",
        healthy_threshold=80,
    )
