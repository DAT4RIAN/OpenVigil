from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import NotFoundError
from windops_backend.models import GeneratedReport
from windops_backend.schemas import ReportGenerateRequest
from windops_backend.services.idempotency import execute_idempotent_command
from windops_backend.services.operational_views import live_report_rows

_PERIOD_DURATION = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "incident": timedelta(days=1),
    "snapshot": timedelta(0),
}

_PERIOD_LABEL = {
    "daily": "Previous 24 hours",
    "weekly": "Previous seven days",
    "incident": "Incident window (previous 24 hours)",
    "snapshot": "Point-in-time governed snapshot",
}


def _canonical_payload(value: dict[str, Any]) -> tuple[dict[str, Any], str]:
    encoded = json.dumps(value, default=lambda item: item.isoformat(), sort_keys=True).encode()
    return json.loads(encoded), hashlib.sha256(encoded).hexdigest()


def serialize_generated_report(row: GeneratedReport) -> dict[str, Any]:
    return {
        **row.snapshot,
        "contentDigest": row.content_sha256,
        "generationReason": row.generation_reason,
        "createdBy": row.created_by,
        "persisted": True,
    }


async def generated_report_rows(session: AsyncSession) -> list[dict[str, Any]]:
    rows = list(
        (
            await session.scalars(
                select(GeneratedReport).order_by(desc(GeneratedReport.created_at))
            )
        ).all()
    )
    return [serialize_generated_report(row) for row in rows]


async def generate_report(
    session: AsyncSession,
    *,
    request: ReportGenerateRequest,
    idempotency_key: str,
    subject: str,
) -> tuple[dict[str, Any], bool]:
    async def operation() -> dict[str, Any]:
        generated_at = datetime.now(UTC)
        candidates = await live_report_rows(session, generated_at=generated_at)
        candidate = next(
            (row for row in candidates if row["type"] == request.report_type),
            None,
        )
        if candidate is None:
            raise NotFoundError(f"report template {request.report_type} was not found")
        report_id = (
            f"RPT-{request.report_type.upper()}-"
            f"{generated_at:%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}"
        )
        period_start = generated_at - _PERIOD_DURATION[request.period]
        source_revision = int(candidate.get("workflow", {}).get("revision", 0) or 0)
        snapshot, content_sha256 = _canonical_payload(
            {
                **candidate,
                "id": report_id,
                "period": request.period,
                "periodLabel": _PERIOD_LABEL[request.period],
                "periodStart": period_start,
                "periodEnd": generated_at,
                "generatedAt": generated_at,
                "status": "ready",
            }
        )
        row = GeneratedReport(
            id=report_id,
            report_type=request.report_type,
            period=request.period,
            period_start=period_start,
            period_end=generated_at,
            source_revision=source_revision,
            content_sha256=content_sha256,
            snapshot=snapshot,
            generation_reason=request.reason.strip(),
            created_by=subject,
        )
        session.add(row)
        await session.flush()
        return {
            "data": serialize_generated_report(row),
            "meta": {
                "persisted": True,
                "replayed": False,
                "source": "postgresql-immutable-report-snapshots",
            },
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=subject,
        command_type="generate_report",
        target=request.report_type,
        idempotency_key=idempotency_key,
        payload=request,
        status_code=201,
        operation=operation,
    )
    # Receipts created before migration 0020 stored only the report id. Preserve
    # their replay path while all new receipts store the exact HTTP response.
    legacy_report_id = result.get("report_id")
    if legacy_report_id is not None:
        legacy = await session.get(GeneratedReport, str(legacy_report_id))
        if legacy is None:
            raise NotFoundError("the idempotent report snapshot no longer exists")
        result = {
            "data": serialize_generated_report(legacy),
            "meta": {
                "persisted": True,
                "replayed": True,
                "source": "postgresql-immutable-report-snapshots",
            },
        }
    return result, replayed
