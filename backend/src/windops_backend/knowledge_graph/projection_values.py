"""Stable identities and value serialization for graph projections."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

KNOWLEDGE_GRAPH_PROJECTION_ID = "windops-operational-knowledge-v1"
KNOWLEDGE_GRAPH_MODEL_VERSION = "2026.10.2"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "unknown"


def _subsystem_for_variable(variable: str) -> str:
    normalized = variable.lower()
    if "main_bearing" in normalized or "main-bearing" in normalized:
        return "main_bearing"
    if "gearbox" in normalized:
        return "gearbox"
    if "generator" in normalized:
        return "generator"
    return "turbine"
