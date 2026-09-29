import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

_calls: ContextVar[list[dict[str, Any]] | None] = ContextVar("embedding_audit_calls", default=None)


@contextmanager
def capture_embedding_usage() -> Iterator[list[dict[str, Any]]]:
    """Keep embedding receipts local to one async graph operation."""
    receipts: list[dict[str, Any]] = []
    token = _calls.set(receipts)
    try:
        yield receipts
    finally:
        _calls.reset(token)


def begin_embedding_attempt(model: str, texts: list[str]) -> dict[str, Any]:
    payload = json.dumps(texts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    receipt: dict[str, Any] = {
        "provider": "litellm",
        "model": model,
        "status": "request_started",
        "request": {
            "input_texts_sha256": hashlib.sha256(payload).hexdigest(),
            "utf8_bytes": len(payload),
            "input_count": len(texts),
            "sdk_retries": 0,
        },
        "token_usage": {
            "prompt_tokens": None,
            "completion_tokens": 0,
            "total_tokens": None,
            "source": "unavailable_before_provider_response",
        },
    }
    collector = _calls.get()
    if collector is not None:
        collector.append(receipt)
    return receipt


def embedding_response_usage(usage: Any) -> dict[str, Any]:
    prompt = (
        usage.get("prompt_tokens")
        if isinstance(usage, dict)
        else getattr(usage, "prompt_tokens", None)
    )
    total = (
        usage.get("total_tokens")
        if isinstance(usage, dict)
        else getattr(usage, "total_tokens", None)
    )
    if type(prompt) is int and type(total) is int and prompt > 0 and total == prompt:
        return {
            "prompt_tokens": prompt,
            "completion_tokens": 0,
            "total_tokens": total,
            "source": "provider_reported",
        }
    # LiteLLM can synthesize Usage(0, 0) when an embedding response omits usage.
    # Nonempty inputs therefore cannot establish a known zero bill from this value.
    source = (
        "unavailable_in_provider_response"
        if usage is None or (prompt == 0 and total == 0)
        else "invalid_or_incomplete_provider_usage"
    )
    return {"prompt_tokens": None, "completion_tokens": 0, "total_tokens": None, "source": source}


def merge_embedding_usage(usage: dict[str, Any], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    if not receipts:
        return usage
    known = [
        r["token_usage"] for r in receipts if r["token_usage"]["source"] == "provider_reported"
    ]
    unknown = len(receipts) - len(known)
    prompt = sum(u["prompt_tokens"] for u in known)
    summary: dict[str, Any] = {
        "prompt_tokens": None if unknown else prompt,
        "completion_tokens": 0,
        "total_tokens": None if unknown else prompt,
        "source": "provider_reported"
        if not unknown
        else "partially_reported"
        if known
        else "unavailable",
    }
    if unknown:
        summary.update(
            known_prompt_tokens=prompt, known_total_tokens=prompt, unknown_attempts=unknown
        )
    models = {r["model"] for r in receipts}
    merged: dict[str, Any] = (
        deepcopy(usage)
        if usage
        else {
            "provider": "litellm",
            "model": receipts[0]["model"] if len(models) == 1 else None,
            "token_usage": summary,
        }
    )
    evaluation = merged.setdefault("evaluation_result", {})
    evaluation["embedding_calls"] = deepcopy(receipts)
    evaluation["embedding_token_usage"] = summary
    policy = merged.setdefault("degradation_policy", {})
    policy["embedding_sdk_retries"] = 0
    policy["embedding_application_attempts"] = len(receipts)
    return merged
