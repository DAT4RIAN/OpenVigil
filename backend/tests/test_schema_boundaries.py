from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

from windops_backend import schemas

SCHEMA_MODULES = (
    "schema_operations",
    "schema_model_care",
    "schema_reports",
    "schema_agents",
    "schema_governance",
    "schema_resources",
    "schema_common",
)
SOURCE_ROOT = Path(__file__).parents[1] / "src" / "windops_backend"
# Plan/review bindings retained; unknown deterioration probability is now nullable.
SCHEMA_JSON_SHA256 = "6457374415b4897b6f8155099aeb09ce8420e4605d04ebeab6dd38c371f181cf"
STRUCTURAL_PLAN_AFFECTED_SCHEMAS = {
    "WorkOrderPlan",
    "MissionAnalysisProfile",
    "MissionCreateRequest",
    "MissionBatchCreateRequest",
    "MaintenanceAlternative",
}
UNCHANGED_58_SCHEMA_SHA256 = "a47c17903917827edbdf416bd5082197c74c9103ac24833b0298d9f9694eee6f"


def test_schema_facade_preserves_public_model_identity_and_json_schema() -> None:
    assert len(schemas.__all__) == len(set(schemas.__all__)) == 70
    declared_classes: set[str] = set()
    for module_name in SCHEMA_MODULES:
        source = (SOURCE_ROOT / f"{module_name}.py").read_text(encoding="utf-8")
        declared_classes.update(
            node.name for node in ast.parse(source).body if isinstance(node, ast.ClassDef)
        )

    public_models = {
        name: getattr(schemas, name)
        for name in schemas.__all__
        if isinstance(getattr(schemas, name), type)
        and issubclass(getattr(schemas, name), BaseModel)
    }
    assert set(public_models) == declared_classes
    assert len(public_models) == 63
    payload = {name: model.model_json_schema() for name, model in public_models.items()}
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert hashlib.sha256(canonical).hexdigest() == SCHEMA_JSON_SHA256
    untouched = {
        name: value
        for name, value in payload.items()
        if name not in STRUCTURAL_PLAN_AFFECTED_SCHEMAS
    }
    assert len(untouched) == 58
    old_canonical = json.dumps(
        untouched, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(old_canonical).hexdigest() == UNCHANGED_58_SCHEMA_SHA256


def test_schema_facade_contains_no_pydantic_declarations() -> None:
    source = (SOURCE_ROOT / "schemas.py").read_text(encoding="utf-8")
    assert not any(isinstance(node, ast.ClassDef) for node in ast.parse(source).body)
