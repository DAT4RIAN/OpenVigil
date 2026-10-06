"""Stable numeric JSON identity across PostgreSQL JSONB and Python reads."""

import hashlib
import json
import math
from decimal import Decimal
from typing import Any

RESULT_HASH_CONTRACT = "openvigil.structural-result-json.v1"


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("structural result identity requires finite JSON numbers")
        number = Decimal(str(value))
        if number == 0:
            return "0"
        text = format(number, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return (
            "{" + ",".join(_encode(key) + ":" + _encode(value[key]) for key in sorted(value)) + "}"
        )
    raise ValueError("structural result identity requires JSON values and string object keys")


def structural_result_hash(result: dict[str, Any]) -> str:
    return hashlib.sha256(_encode(result).encode("utf-8")).hexdigest()
