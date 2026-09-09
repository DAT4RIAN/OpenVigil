from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from fastapi import FastAPI

from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.main import create_app
from windops_backend.storage import InMemoryArtifactVerifier

ARTIFACT_HASHES = {
    f"minio://test/field-task-{index}.json": f"{index:064x}" for index in range(1, 6)
}
ARTIFACT_HASHES["minio://test/security-evidence.json"] = "a" * 64


@pytest_asyncio.fixture
async def app(tmp_path) -> AsyncIterator[FastAPI]:
    settings = Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'windops-test.sqlite'}",
        schema_bootstrap=True,
        demo_seed=True,
        agent_mode="deterministic",
        test_auth_bypass_enabled=True,
        outbox_inline_drain=True,
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        verifier = application.state.artifact_verifier
        assert isinstance(verifier, InMemoryArtifactVerifier)
        for uri, sha256 in ARTIFACT_HASHES.items():
            verifier.register(uri, sha256)
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-WindOps-Test-Principal": "integration-test-system",
            "X-WindOps-Test-Role": "test_system",
        },
    ) as value:
        yield value
