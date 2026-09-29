"""Prepare the selected reasoning SDK before a service accepts business work."""

import importlib
import os
from time import perf_counter

from windops_backend.config import Settings


def prepare_reasoning_runtime(settings: Settings) -> float:
    if settings.agent_mode != "litellm":
        return 0.0
    # The application owns configuration loading. LiteLLM's DEV import otherwise
    # loads .env into os.environ and can change unrelated Host/auth settings.
    # This is the SDK mode only, not WINDOPS_ENVIRONMENT or production acceptance.
    if os.environ.setdefault("LITELLM_MODE", "PRODUCTION") != "PRODUCTION":
        raise ValueError("LiteLLM SDK must not load DEV dotenv configuration")
    started = perf_counter()
    # Import only: no completion, credential check, or paid warm-up request.
    # Failures must abort startup rather than appear during the first mission.
    importlib.import_module("litellm")
    return perf_counter() - started
