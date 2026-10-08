"""Transport tests use real owned processes; no OCR accuracy claim."""

import asyncio
import sys
from pathlib import Path

import pytest

from windops_backend import document_parse_process as transport


async def test_parser_deadline_kills_and_reaps_owned_process(monkeypatch):
    launch = asyncio.create_subprocess_exec
    children = []

    async def sleeping_child(*_args, **kwargs):
        child = await launch(
            sys.executable,
            "-c",
            "import sys,time; sys.stdin.buffer.read(); time.sleep(30)",
            **kwargs,
        )
        children.append(child)
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", sleeping_child)
    monkeypatch.setattr(transport, "PARSE_TIMEOUT_SECONDS", 0.1)
    with pytest.raises(TimeoutError):
        await transport.parse_document_subprocess(
            b"%PDF-", models_path=Path.cwd(), manifest_sha256="a" * 64
        )
    assert len(children) == 1 and children[0].returncode is not None
    assert children[0].returncode != 0


async def test_parser_cancellation_reaps_owned_process(monkeypatch):
    launch = asyncio.create_subprocess_exec
    children = []
    ready = asyncio.Event()

    async def sleeping_child(*_args, **kwargs):
        child = await launch(
            sys.executable,
            "-c",
            "import sys,time; sys.stdin.buffer.read(); time.sleep(30)",
            **kwargs,
        )
        children.append(child)
        ready.set()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", sleeping_child)
    task = asyncio.create_task(
        transport.parse_document_subprocess(
            b"%PDF-", models_path=Path.cwd(), manifest_sha256="a" * 64
        )
    )
    await asyncio.wait_for(ready.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(children) == 1 and children[0].returncode is not None


@pytest.mark.parametrize("pipe", ["stdout", "stderr"])
async def test_parser_output_flood_is_bounded_and_process_reaped(monkeypatch, pipe):
    launch = asyncio.create_subprocess_exec
    children = []

    async def flooding_child(*_args, **kwargs):
        child = await launch(
            sys.executable,
            "-c",
            f"import sys,time; sys.stdin.buffer.read(); "
            f"sys.{pipe}.buffer.write(b'x'*10000); sys.{pipe}.flush(); time.sleep(30)",
            **kwargs,
        )
        children.append(child)
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", flooding_child)
    monkeypatch.setattr(transport, "MAX_OUTPUT_BYTES", 64)
    monkeypatch.setattr(transport, "MAX_STDERR_BYTES", 64)
    with pytest.raises(transport.DocumentParseFailure, match="output_limit"):
        await transport.parse_document_subprocess(
            b"%PDF-", models_path=Path.cwd(), manifest_sha256="a" * 64
        )
    assert children[0].returncode is not None


async def test_parser_does_not_inherit_supplier_or_database_credentials(monkeypatch):
    launch = asyncio.create_subprocess_exec
    observed = {}

    async def rejecting_child(*_args, **kwargs):
        observed.update(kwargs["env"])
        return await launch(sys.executable, "-c", "raise SystemExit(1)", **kwargs)

    monkeypatch.setenv("WINDOPS_DATABASE_URL", "credential-bearing-test-url")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-secret")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", rejecting_child)
    with pytest.raises(transport.DocumentParseFailure, match="document_parser_failed"):
        await transport.parse_document_subprocess(
            b"%PDF-", models_path=Path.cwd(), manifest_sha256="a" * 64
        )
    assert "OPENAI_API_KEY" not in observed
    assert "WINDOPS_DATABASE_URL" not in observed
    assert observed["HF_HUB_OFFLINE"] == "1"
    assert observed["TRANSFORMERS_OFFLINE"] == "1"


async def test_empty_document_is_rejected_before_launch(monkeypatch):
    async def forbidden_launch(*_args, **_kwargs):
        pytest.fail("empty input must not launch a parser")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_launch)
    with pytest.raises(ValueError, match="input is empty"):
        await transport.parse_document_subprocess(
            b"", models_path=Path.cwd(), manifest_sha256="a" * 64
        )


async def test_packaged_parser_does_not_import_sibling_api_dependencies(tmp_path, monkeypatch):
    package = tmp_path / "api-site-packages" / "windops_backend"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "bootstrap-isolation-fixture"')
    (package.parent / "poison_api_dependency.py").write_text('raise RuntimeError("API leaked")')
    (package / "document_parse_compute.py").write_text(
        "import importlib.util,json,sys,windops_backend\n"
        "sys.stdin.buffer.read()\n"
        "assert windops_backend.__version__=='bootstrap-isolation-fixture'\n"
        "failure='ApiSiblingLeaked' if importlib.util.find_spec('poison_api_dependency') "
        "else 'IsolatedPackageScope'\n"
        "print(json.dumps({'failure_type':failure}))\n"
        "raise SystemExit(1)\n"
    )
    monkeypatch.setattr(transport, "PACKAGE_PATH", str(package))
    with pytest.raises(transport.DocumentParseFailure) as observed:
        await transport.parse_document_subprocess(
            b"%PDF-", models_path=tmp_path, manifest_sha256="a" * 64
        )
    assert observed.value.failure_type == "IsolatedPackageScope"
