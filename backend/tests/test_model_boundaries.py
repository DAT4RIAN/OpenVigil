from __future__ import annotations

import ast
import hashlib
import importlib
import re
from pathlib import Path

from windops_backend import models

MODEL_MODULES = (
    "model_identity_assets",
    "model_ingest_governance",
    "model_telemetry_operations",
    "model_agent_execution",
    "model_platform_governance",
    "model_workflow",
    "model_knowledge",
    "model_registry",
    "model_benchmark",
    "model_operations_support",
)
SOURCE_ROOT = Path(__file__).parents[1] / "src" / "windops_backend"
MODEL_TOKEN_SHA256 = "761d3a2071c2e3b052d83ec90623fe9dd54129a7cd49e30a371ba0a338f680b9"


def test_model_facade_reexports_the_exact_owned_declarations() -> None:
    owned: dict[str, type[object]] = {}
    token_stream: list[str] = []
    for module_name in MODEL_MODULES:
        module = importlib.import_module(f"windops_backend.{module_name}")
        source = (SOURCE_ROOT / f"{module_name}.py").read_text(encoding="utf-8")
        class_offset = source.index("class ")
        token_stream.append(re.sub(r"\s+", "", source[class_offset:]))
        for node in ast.parse(source).body:
            if isinstance(node, ast.ClassDef):
                owned[node.name] = getattr(module, node.name)

    exported_classes = {
        name: getattr(models, name)
        for name in models.__all__
        if isinstance(getattr(models, name), type) and name != "Base"
    }
    assert exported_classes == owned
    owned_tables = {model.__table__.key for model in exported_classes.values()}
    assert len(owned_tables) == 57
    assert owned_tables <= set(models.Base.metadata.tables)
    assert hashlib.sha256("".join(token_stream).encode()).hexdigest() == MODEL_TOKEN_SHA256


def test_model_facade_contains_no_orm_declarations() -> None:
    source = (SOURCE_ROOT / "models.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.ClassDef) for node in tree.body)
