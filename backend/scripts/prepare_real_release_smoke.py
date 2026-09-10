"""Seed one isolated pending rotation for the real Worker/backend release smoke."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from windops_backend.models import (
    CommandReceipt,
    PlatformConfigurationRevision,
    PlatformConfigurationSecurityAudit,
)

ROTATION_CONFIRMATION_COMMAND = "platform.configuration-rotation.confirm.v1"


async def prepare() -> str:
    if os.getenv("WINDOPS_RELEASE_SMOKE") != "1":
        raise RuntimeError("WINDOPS_RELEASE_SMOKE=1 is required for the isolated fixture")
    database_url = os.getenv("WINDOPS_DATABASE_URL", "").strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        raise RuntimeError(
            "WINDOPS_DATABASE_URL must point to the isolated PostgreSQL smoke database"
        )
    audit_id = os.getenv("WINDOPS_REAL_ROTATION_AUDIT_ID", f"real-smoke-audit-{uuid4().hex[:12]}")
    revision_id = os.getenv(
        "WINDOPS_REAL_ROTATION_REVISION_ID", f"real-smoke-revision-{uuid4().hex[:12]}"
    )
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with AsyncSession(engine) as session, session.begin():
            # The fixture is intentionally repeatable against one isolated CI
            # database. Remove a prior idempotency result for this owned target
            # before recreating the pending audit; otherwise a rerun can replay
            # yesterday's 200 response without confirming today's new row.
            await session.execute(
                delete(CommandReceipt).where(
                    CommandReceipt.command_type == ROTATION_CONFIRMATION_COMMAND,
                    CommandReceipt.target == audit_id,
                )
            )
            await session.execute(
                delete(PlatformConfigurationSecurityAudit).where(
                    PlatformConfigurationSecurityAudit.id == audit_id
                )
            )
            await session.execute(
                delete(PlatformConfigurationRevision).where(
                    PlatformConfigurationRevision.id == revision_id
                )
            )
            session.add(
                PlatformConfigurationRevision(
                    id=revision_id,
                    configuration_key="backup_policy",
                    revision=1,
                    value={},
                    secret_reference=None,
                    security_status="quarantined_rotation_required",
                    active=False,
                    reason="real Worker-to-FastAPI rotation smoke fixture",
                    created_by="release-smoke",
                    created_at=datetime.now(UTC),
                )
            )
            session.add(
                PlatformConfigurationSecurityAudit(
                    id=audit_id,
                    configuration_id=revision_id,
                    configuration_key="backup_policy",
                    revision=1,
                    finding_categories=["invalid_secret_reference"],
                    original_fingerprint="a" * 64,
                    action="quarantined_and_redacted",
                    rotation_required=True,
                )
            )
    finally:
        await engine.dispose()
    print(audit_id)
    return audit_id


if __name__ == "__main__":
    asyncio.run(prepare())
