from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from typing import Any, Protocol

import httpx
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import ValidationError  # type: ignore[import-untyped]

from windops_backend.config import ModelInferenceTarget
from windops_backend.errors import (
    InvalidTransitionError,
)

ALLOWED_MODEL_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "application/octet-stream",
        "application/onnx",
        "application/zip",
    }
)
MAX_MODEL_ARTIFACT_BYTES = 50 * 1024 * 1024
_prediction_locks: dict[str, asyncio.Lock] = {}
CARE_ACTIVATION_GATE_POLICY_VERSION = "care-server-activation-gate-v1"
CARE_ACTIVATION_ARTIFACT_CONTENT_TYPES = frozenset({"application/json"})
MAX_CARE_ACTIVATION_ARTIFACT_BYTES = 50 * 1024 * 1024


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ModelInferenceClient(Protocol):
    async def predict(
        self,
        target: ModelInferenceTarget,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int]: ...


class HttpModelInferenceClient:
    """Strict HTTPS JSON client; package bytes are never executed by OpenVigil."""

    async def predict(
        self,
        target: ModelInferenceTarget,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int]:
        started = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=target.timeout_seconds,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                target.endpoint_url,
                headers={
                    "Authorization": f"Bearer {target.api_token.get_secret_value()}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                json=payload,
            )
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        if response.is_redirect:
            raise RuntimeError("model inference redirects are rejected")
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("model inference response must be a JSON object")
        return body, latency_ms


def _validate_instance(schema: Mapping[str, Any], value: dict[str, Any], label: str) -> None:
    try:
        Draft202012Validator(schema).validate(value)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "$"
        raise InvalidTransitionError(
            f"{label} contract violation at {location}: {exc.message}"
        ) from exc
