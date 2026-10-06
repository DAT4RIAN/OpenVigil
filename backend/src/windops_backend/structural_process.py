import asyncio
import json
import os
import re
import sys
from typing import Any

COMPUTATION_TIMEOUT_SECONDS = 120


class StructuralComputationFailure(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = (
            error_code
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,79}", error_code)
            else "StructuralComputationFailure"
        )
        super().__init__(f"structural calculation failed ({self.error_code})")


async def compute_waveform(
    content: bytes, record: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    payload = json.dumps(
        {"artifact_text": content.decode("utf-8"), "record": record, "config": config}
    ).encode()
    if len(payload) > 36 * 1024 * 1024:
        raise ValueError("structural calculation exceeded the bounded input size")
    # Native math libraries must not multiply the dedicated queue's CPU budget.
    env = {
        **os.environ,
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "windops_backend.structural_compute",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        output, _stderr = await asyncio.wait_for(
            process.communicate(payload), COMPUTATION_TIMEOUT_SECONDS
        )
    except BaseException:
        # This PID was created here. Kill it on timeout/cancellation, then reap it
        # before letting the retry or shutdown proceed.
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    if len(output) > 2 * 1024 * 1024:
        raise ValueError("structural calculation exceeded the bounded result size")
    result = json.loads(output)
    if not isinstance(result, dict):
        raise ValueError("invalid structural calculation result")
    if process.returncode != 0:
        raise StructuralComputationFailure(
            str(result.get("error_code", "StructuralComputationFailure"))
        )
    if "quality" not in result:
        raise ValueError("invalid structural calculation result")
    return result
