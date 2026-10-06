"""Actual PostgreSQL read fences; synthetic FDD inputs and in-memory object verifier."""

import os
from uuid import uuid4

import httpx
import pytest
import test_postgres_migrations as postgres_contract
from sqlalchemy import select

from test_structural_graph import (
    approved_graph_claim,
)
from test_structural_graph import (
    test_verification_failure_is_unavailable_and_concurrent_changes_fence_read as _fenced,
)
from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.knowledge_graph.structural_access import current_structural_graph_policy
from windops_backend.main import create_app
from windops_backend.models import DomainEvent

pytestmark = [
    pytest.mark.external_release,
    pytest.mark.skipif(
        os.getenv("WINDOPS_RUN_POSTGRES_CONTRACT_TESTS") != "1",
        reason="requires the explicitly isolated PostgreSQL test service",
    ),
]
migration_database_urls = postgres_contract.migration_database_urls


def application(database_url):
    postgres_contract._run_alembic(database_url, "upgrade", "head")
    return create_app(
        Settings(
            environment=Environment.TEST,
            database_url=database_url,
            schema_bootstrap=False,
            demo_seed=True,
            agent_mode="deterministic",
            test_auth_bypass_enabled=True,
            outbox_inline_drain=True,
            knowledge_graph_backend="memory",
        )
    )


@pytest.mark.parametrize("mutation", ["withdraw", "source_change", "content_change"])
async def test_postgres_graph_rechecks_changes_committed_during_original_byte_read(
    migration_database_urls, monkeypatch, mutation
):
    app = application(migration_database_urls[0])
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-WindOps-Test-Principal": "synthetic-postgres-reader",
                "X-WindOps-Test-Role": "test_system",
            },
        ) as client,
    ):
        await _fenced(app, client, monkeypatch, mutation)


async def test_postgres_graph_fresh_identity_map_preserves_caller_transaction(
    migration_database_urls,
):
    app = application(migration_database_urls[0])
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-WindOps-Test-Principal": "synthetic-postgres-reader",
                "X-WindOps-Test-Role": "test_system",
            },
        ) as client,
    ):
        claim, _ = await approved_graph_claim(app, client)
        identity = str(uuid4())
        async with app.state.session_factory() as session:
            row = DomainEvent(
                id=identity,
                event_type="synthetic.graph.transaction-probe",
                aggregate_type="synthetic_test",
                aggregate_id=identity,
                payload={"source_kind": "synthetic_test"},
            )
            session.add(row)
            await session.flush()
            policy = await current_structural_graph_policy(
                session,
                GraphAccessPolicy(unrestricted=True),
                app.state.artifact_verifier,
                app.state.settings,
            )
            assert (
                f"{claim['id']}:{claim['revision']}:{claim['content_sha256']}"
                in policy.validated_claim_identities
            )
            # The child identity map neither closes nor rolls back the caller's
            # active transaction, and it never commits uncommitted business rows.
            assert (
                await session.scalar(select(DomainEvent.id).where(DomainEvent.id == identity))
                == identity
            )
            async with app.state.session_factory() as observer:
                assert (
                    await observer.scalar(select(DomainEvent.id).where(DomainEvent.id == identity))
                    is None
                )
            await session.rollback()
        async with app.state.session_factory() as observer:
            assert (
                await observer.scalar(select(DomainEvent.id).where(DomainEvent.id == identity))
                is None
            )
