"""Bounded subprocess transport; Docling never imports into the API process."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from windops_backend.document_parse_contract import (
    MAX_INPUT_BYTES,
    MAX_OUTPUT_BYTES,
    DocumentParseResult,
)
from windops_backend.document_parse_identity import DOCUMENT_PARSER_VERSIONS, parser_code_identity

PARSE_TIMEOUT_SECONDS = 180
MAX_STDERR_BYTES = 64 * 1024
PACKAGE_PATH = str(Path(__file__).resolve().parent)
PARSER_BOOTSTRAP = """
import importlib.util, pathlib, runpy, sys
package_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location(
    'windops_backend', package_path / '__init__.py',
    submodule_search_locations=[str(package_path)],
)
if spec is None or spec.loader is None:
    raise RuntimeError('document parser package could not be loaded')
package = importlib.util.module_from_spec(spec)
sys.modules['windops_backend'] = package
spec.loader.exec_module(package)
runpy.run_module('windops_backend.document_parse_compute', run_name='__main__')
"""


class DocumentParseFailure(RuntimeError):
    """Public failures contain a fixed code, never source text or credentials."""

    def __init__(self, error_code: str, failure_type: str | None = None) -> None:
        self.failure_type = (
            failure_type
            if failure_type and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", failure_type)
            else None
        )
        super().__init__(error_code + (f" ({self.failure_type})" if self.failure_type else ""))


async def _bounded_read(stream: asyncio.StreamReader, limit: int) -> bytes:
    pieces: list[bytes] = []
    size = 0
    while piece := await stream.read(64 * 1024):
        size += len(piece)
        if size > limit:
            raise DocumentParseFailure("document_parser_output_limit")
        pieces.append(piece)
    return b"".join(pieces)


async def parse_document_subprocess(
    content: bytes,
    *,
    models_path: Path,
    manifest_sha256: str,
    python_executable: str | None = None,
    runtime_directory: Path | None = None,
) -> DocumentParseResult:
    if not content or len(content) > MAX_INPUT_BYTES:
        raise ValueError("document parser input is empty or exceeds the byte limit")
    runtime = await asyncio.to_thread(
        tempfile.TemporaryDirectory, prefix="openvigil-document-", dir=runtime_directory
    )
    try:
        return await _parse_document_subprocess(
            content,
            models_path=models_path,
            manifest_sha256=manifest_sha256,
            python_executable=python_executable,
            runtime_home=runtime.name,
        )
    finally:
        await asyncio.to_thread(runtime.cleanup)


async def _parse_document_subprocess(
    content: bytes,
    *,
    models_path: Path,
    manifest_sha256: str,
    python_executable: str | None,
    runtime_home: str,
) -> DocumentParseResult:
    source_sha256 = hashlib.sha256(content).hexdigest()
    expected_code = await asyncio.to_thread(parser_code_identity)
    resolved_models_path = await asyncio.to_thread(models_path.resolve)
    header = (
        json.dumps(
            {
                "source_sha256": source_sha256,
                "models_path": str(resolved_models_path),
                "model_manifest_sha256": manifest_sha256,
            }
        ).encode()
        + b"\n"
    )
    process = await asyncio.create_subprocess_exec(
        python_executable or sys.executable,
        "-I",
        "-X",
        "utf8",
        "-c",
        PARSER_BOOTSTRAP,
        PACKAGE_PATH,
        cwd=runtime_home,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            **{
                name: value
                for name, value in os.environ.items()
                if name.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
            },
            "HOME": runtime_home,
            "USERPROFILE": runtime_home,
            "HF_HOME": runtime_home,
            "XDG_CACHE_HOME": runtime_home,
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "TOKENIZERS_PARALLELISM": "false",
        },
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise RuntimeError("document parser subprocess pipes were not created")

    async def send_input() -> None:
        if process.stdin is None:
            raise RuntimeError("document parser input pipe is missing")
        try:
            process.stdin.write(header)
            for start in range(0, len(content), 64 * 1024):
                process.stdin.write(content[start : start + 64 * 1024])
                await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            # A parser may reject its header before consuming document bytes.
            pass
        finally:
            process.stdin.close()

    input_task = asyncio.create_task(send_input())
    output_task = asyncio.create_task(_bounded_read(process.stdout, MAX_OUTPUT_BYTES))
    stderr_task = asyncio.create_task(_bounded_read(process.stderr, MAX_STDERR_BYTES))
    wait_task = asyncio.create_task(process.wait())
    tasks = [input_task, output_task, stderr_task, wait_task]
    try:
        async with asyncio.timeout(PARSE_TIMEOUT_SECONDS):
            await asyncio.gather(*tasks)
        output = output_task.result()
        if process.returncode != 0:
            try:
                failure = json.loads(output)
                failure_type = failure.get("failure_type") if isinstance(failure, dict) else None
            except (ValueError, UnicodeDecodeError):
                failure_type = None
            raise DocumentParseFailure(
                "document_parser_failed", failure_type if isinstance(failure_type, str) else None
            )
        result = DocumentParseResult.model_validate_json(output)
        if result.source_sha256 != source_sha256 or result.model_manifest_sha256 != manifest_sha256:
            raise DocumentParseFailure("document_parser_identity_mismatch")
        if (
            result.execution_code_sha256 != expected_code
            or result.library_versions != DOCUMENT_PARSER_VERSIONS
        ):
            raise DocumentParseFailure("document_parser_execution_identity_mismatch")
        return result
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
