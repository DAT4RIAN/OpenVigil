"""Obtain current claim read identities from SQL and reverified immutable sources."""

import asyncio
import logging
from dataclasses import replace
from time import monotonic

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.access_control import attach_access_policy, data_scope_allowed
from windops_backend.config import Settings
from windops_backend.errors import InvalidTransitionError, NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.knowledge_graph.projection import (
    ProjectionLimits,
    _conservative_memory_bytes,
    _iter_bounded_scalar_rows,
    _ProjectionBudget,
)
from windops_backend.knowledge_graph.structural_projection import claim_read_identity
from windops_backend.model_base import utcnow
from windops_backend.model_engineering_claim import EngineeringClaim
from windops_backend.services.engineering_claims import (
    _effective_status,
    _sources,
    verify_card_sources,
)
from windops_backend.storage import ArtifactVerifier

logger = logging.getLogger(__name__)
GRAPH_CLAIM_READ_TIMEOUT_SECONDS = 10.0


async def current_structural_graph_policy(
    session: AsyncSession, policy: GraphAccessPolicy, verifier: ArtifactVerifier, settings: Settings
) -> GraphAccessPolicy:
    # A governed read must fit within the gateway request window; it must not
    # inherit the background rebuild's five-minute allowance or return partial proof.
    async with asyncio.timeout(GRAPH_CLAIM_READ_TIMEOUT_SECONDS):
        return await _current_structural_graph_policy(session, policy, verifier, settings)


async def _current_structural_graph_policy(
    session: AsyncSession, policy: GraphAccessPolicy, verifier: ArtifactVerifier, settings: Settings
) -> GraphAccessPolicy:
    if not data_scope_allowed(policy, "structural"):
        return replace(policy, validated_claim_identities=frozenset())
    # Use the same ORM scope enforcement as governed claim reads. Related Mission,
    # structural and knowledge grants are rechecked even for unrestricted test rows.
    attach_access_policy(session, policy)
    limits = ProjectionLimits.from_settings(settings)
    budget = _ProjectionBudget(
        replace(
            limits,
            max_runtime_seconds=min(limits.max_runtime_seconds, GRAPH_CLAIM_READ_TIMEOUT_SECONDS),
        )
    )
    identities: set[str] = set()
    try:
        async for claim in _iter_bounded_scalar_rows(
            session,
            select(EngineeringClaim)
            .where(
                EngineeringClaim.review_status == "approved",
                EngineeringClaim.valid_until > utcnow(),
            )
            .order_by(EngineeringClaim.id),
            budget=budget,
            key_column=EngineeringClaim.id,
            key_attribute="id",
        ):
            budget.check_runtime()
            try:
                cards, drift = await _sources(session, claim)
                if _effective_status(claim, cards, drift) != "approved":
                    continue
                remaining = budget.limits.max_runtime_seconds - (monotonic() - budget.started_at)
                async with asyncio.timeout(max(0.0, remaining)):
                    await verify_card_sources(cards, claim.turbine_id, verifier, settings)
                # Use an independent identity map on the caller's connection.
                # Fresh SQL rechecks both the statement and its immutable source
                # rows after object I/O, without expiring the paged claim iterator,
                # allocating another pool connection, or committing this read.
                async with AsyncSession(
                    bind=await session.connection(),
                    expire_on_commit=False,
                    join_transaction_mode="rollback_only",
                ) as recheck:
                    attach_access_policy(recheck, policy)
                    current = await recheck.scalar(
                        select(EngineeringClaim).where(
                            EngineeringClaim.id == claim.id,
                            EngineeringClaim.revision == claim.revision,
                            EngineeringClaim.content_sha256 == claim.content_sha256,
                            EngineeringClaim.review_status == "approved",
                            EngineeringClaim.valid_until > utcnow(),
                        )
                    )
                    if current is None:
                        continue
                    fresh_cards, fresh_drift = await _sources(recheck, current)
                    if _effective_status(current, fresh_cards, fresh_drift) != "approved":
                        continue
                    identity = claim_read_identity(current)
            except (NotFoundError, InvalidTransitionError) as exc:
                logger.info("structural graph withheld claim %s: %s", claim.id, type(exc).__name__)
                continue
            budget.reserve_memory(_conservative_memory_bytes(identity, entry_overhead=64))
            identities.add(identity)
        return replace(policy, validated_claim_identities=frozenset(identities))
    finally:
        budget.close()
