from datetime import UTC, datetime
from typing import Any, Literal

import orjson
from fastapi import APIRouter, Depends, Header, Path, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.api.deps import (
    Principal,
    get_session,
    require_global_roles,
    require_read_access,
)
from windops_backend.errors import NotFoundError
from windops_backend.models import (
    AgentExecution,
    GeneratedReport,
    IngestSource,
    IngestSourceSecurityAudit,
)
from windops_backend.platform_configuration import platform_configuration_schema_names
from windops_backend.schemas import (
    DataContractCreateRequest,
    IngestSourcePolicyRequest,
    PlatformConfigurationCreateRequest,
    PlatformConfigurationRotationConfirmationRequest,
    ReportGenerateRequest,
)
from windops_backend.services.idempotency import execute_idempotent_command
from windops_backend.services.operational_views import (
    data_catalog_payload,
    diagnosis_rows,
    maintenance_plan_rows,
)
from windops_backend.services.platform_governance import (
    active_data_contracts,
    active_platform_configurations,
    confirm_ingest_source_rotation,
    confirm_platform_configuration_rotation,
    create_data_contract,
    create_platform_configuration_revision,
    platform_configuration_security_audits,
    redacted_platform_configuration_status,
    serialize_platform_configuration_revision,
    upsert_ingest_source_policy,
)
from windops_backend.services.reports import (
    generate_report,
    generated_report_rows,
    serialize_generated_report,
)

router = APIRouter()


@router.get("/diagnoses", tags=["diagnosis"])
async def diagnoses(
    query: str = Query(default="", alias="q", max_length=100),
    turbine_id: str | None = Query(default=None, alias="turbineId"),
    status_filter: str | None = Query(default=None, alias="status"),
    risk: str | None = None,
    sort_mode: str = Query(default="priority-desc", alias="sort"),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=64, ge=1, le=64),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> Response:
    # The SQL access policy compares case-insensitively, while these explicit
    # page predicates should preserve the configured identifier spelling so
    # PostgreSQL can keep using the existing plain B-tree indexes.
    scoped_tenant_id = _principal.tenant_ids[0] if len(_principal.tenant_ids) == 1 else None
    scoped_wind_farm_id = (
        _principal.wind_farm_ids[0] if len(_principal.wind_farm_ids) == 1 else None
    )
    page = await diagnosis_rows(
        session,
        query=query,
        tenant_id=scoped_tenant_id,
        wind_farm_id=scoped_wind_farm_id,
        turbine_id=turbine_id,
        status_filter=status_filter,
        risk=risk,
        sort_mode=sort_mode,
        offset=offset,
        limit=limit,
    )
    real_inference = (
        await session.scalar(
            select(AgentExecution.id)
            .where(AgentExecution.provider.not_in(("deterministic", "sqlalchemy")))
            .limit(1)
        )
        is not None
    )
    return Response(
        content=orjson.dumps(
            {
                "data": page.rows,
                "meta": {
                    "count": len(page.rows),
                    "total": page.total,
                    "filtered_total": page.filtered_total,
                    "offset": offset,
                    "limit": limit,
                    "has_more": offset + len(page.rows) < page.filtered_total,
                    "next_offset": (
                        offset + len(page.rows)
                        if offset + len(page.rows) < page.filtered_total
                        else None
                    ),
                    "snapshot_at": datetime.now(UTC),
                    "source": "postgresql-governed-missions",
                    "real_inference": real_inference,
                    "related_data_boundaries": page.related_data_boundaries,
                },
            }
        ),
        media_type="application/json",
    )


@router.get("/maintenance-plans", tags=["maintenance"])
async def maintenance_plans(
    query: str = Query(default="", alias="q", max_length=100),
    turbine_id: str | None = Query(default=None, alias="turbineId"),
    status_filter: str | None = Query(default=None, alias="status"),
    risk: str | None = None,
    team: str | None = None,
    window: str | None = None,
    sort_mode: str = Query(default="start-asc", alias="sort"),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=50, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> Response:
    scoped_tenant_id = _principal.tenant_ids[0] if len(_principal.tenant_ids) == 1 else None
    scoped_wind_farm_id = (
        _principal.wind_farm_ids[0] if len(_principal.wind_farm_ids) == 1 else None
    )
    page = await maintenance_plan_rows(
        session,
        query=query,
        tenant_id=scoped_tenant_id,
        wind_farm_id=scoped_wind_farm_id,
        turbine_id=turbine_id,
        status_filter=status_filter,
        risk=risk,
        team=team,
        window=window,
        sort_mode=sort_mode,
        offset=offset,
        limit=limit,
    )
    return Response(
        content=orjson.dumps(
            {
                "data": page.rows,
                "meta": {
                    "count": len(page.rows),
                    "total": page.total,
                    "filtered_total": page.filtered_total,
                    "offset": offset,
                    "limit": limit,
                    "has_more": offset + len(page.rows) < page.filtered_total,
                    "next_offset": (
                        offset + len(page.rows)
                        if offset + len(page.rows) < page.filtered_total
                        else None
                    ),
                    "snapshot_at": datetime.now(UTC),
                    "source": "postgresql-work-orders-resources-weather",
                    "read_only": False,
                    "related_data_boundaries": page.related_data_boundaries,
                },
            }
        ),
        media_type="application/json",
    )


@router.get("/reports", tags=["reports"])
async def reports(
    report_type: str | None = Query(default=None, alias="type"),
    period: str | None = None,
    query: str = Query(default="", alias="q", max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    rows = await generated_report_rows(session)
    normalized_query = query.strip().lower()
    filtered = [
        row
        for row in rows
        if (not report_type or row["type"] == report_type)
        and (not period or row["period"] == period)
        and (
            not normalized_query
            or normalized_query
            in f"{row['id']} {row['title']} {row['subtitle']} {' '.join(row['tags'])}".lower()
        )
    ]
    return {
        "data": filtered[offset : offset + limit],
        "meta": {
            "count": len(filtered[offset : offset + limit]),
            "total": len(rows),
            "filtered_total": len(filtered),
            "offset": offset,
            "limit": limit,
            "snapshot_at": datetime.now(UTC),
            "source": "postgresql-immutable-report-snapshots",
            "persisted": True,
        },
    }


@router.get("/reports/{report_id}", tags=["reports"])
async def report_detail(
    report_id: str = Path(min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    report = await session.get(GeneratedReport, report_id)
    if report is None:
        raise NotFoundError(f"report {report_id} was not found")
    return {
        "data": serialize_generated_report(report),
        "meta": {
            "persisted": True,
            "source": "postgresql-immutable-report-snapshots",
            "snapshot_at": report.period_end,
        },
    }


@router.post(
    "/reports",
    status_code=status.HTTP_201_CREATED,
    tags=["reports"],
)
async def generate_report_command(
    payload: ReportGenerateRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(
        require_global_roles("operations_manager", data_scopes="report")
    ),
) -> dict[str, Any]:
    result, replayed = await generate_report(
        session,
        request=payload,
        idempotency_key=idempotency_key,
        subject=principal.subject,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.get("/data-catalog", tags=["platform"])
async def governed_data_catalog(
    query: str = Query(default="", alias="q", max_length=100),
    category: Literal["live", "archive", "api", "schema", "benchmark"] | None = None,
    status_filter: Literal["ready", "demo", "read-only"] | None = Query(
        default=None, alias="status"
    ),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=64, ge=1, le=64),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    payload = await data_catalog_payload(session, principal.graph_access_policy())
    normalized_query = query.strip().casefold()
    filtered_entries = [
        row
        for row in payload["entries"]
        if (not category or row["category"] == category)
        and (not status_filter or row["status"] == status_filter)
        and (
            not normalized_query
            or normalized_query
            in " ".join(
                str(row[field]) for field in ("id", "name", "description", "source")
            ).casefold()
        )
    ]
    entries = filtered_entries[offset : offset + limit]
    return {
        "data": entries,
        "meta": {
            "count": len(entries),
            "total": len(payload["entries"]),
            "filtered_total": len(filtered_entries),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(entries) < len(filtered_entries),
            "next_offset": (
                offset + len(entries) if offset + len(entries) < len(filtered_entries) else None
            ),
            "scada_archive_count": payload["sample_count"],
            "schema_object_count": payload["schema_object_count"],
            "benchmark_total": payload["benchmark_total"],
            "benchmark_page_max": payload["benchmark_page_max"],
            "snapshot_at": payload["snapshot_at"],
            "hierarchy": payload["hierarchy"],
            "source": "postgresql-governed-catalog",
            "fixture_fallback": False,
        },
    }


@router.get("/platform/configurations", tags=["platform"])
async def platform_configurations(
    session: AsyncSession = Depends(get_session),
    _read_principal: Principal = Depends(require_read_access),
    _manager: Principal = Depends(
        require_global_roles("operations_manager", data_scopes="platform")
    ),
) -> dict[str, Any]:
    configurations = await active_platform_configurations(session)
    serialized_configurations = [
        serialized
        for row in configurations
        if (serialized := serialize_platform_configuration_revision(row)) is not None
    ]
    quarantined_active_count = len(configurations) - len(serialized_configurations)
    contracts = await active_data_contracts(session)
    sources = list((await session.scalars(select(IngestSource).order_by(IngestSource.id))).all())
    security_audits = await platform_configuration_security_audits(session)
    source_security_audits = list(
        (
            await session.scalars(
                select(IngestSourceSecurityAudit).order_by(IngestSourceSecurityAudit.created_at)
            )
        ).all()
    )
    return {
        "configurations": serialized_configurations,
        "data_contracts": [
            {
                "contract_id": row.id,
                "source_id": row.source_id,
                "variable": row.variable,
                "revision": row.revision,
                "contract": row.contract,
                "reason": row.reason,
                "created_by": row.created_by,
                "created_at": row.created_at,
            }
            for row in contracts
        ],
        "data_sources": [
            {
                "source_id": row.id,
                "display_name": row.display_name,
                "source_kind": row.source_kind,
                "enabled": row.enabled,
                "policy": row.policy,
                "secret_configured": row.credential_secret_reference is not None,
                "last_seen_at": row.last_seen_at,
                "updated_at": row.updated_at,
            }
            for row in sources
        ],
        "security_audits": [
            {
                "audit_id": row.id,
                "configuration_id": row.configuration_id,
                "configuration_key": row.configuration_key,
                "revision": row.revision,
                "finding_categories": row.finding_categories,
                "original_fingerprint": row.original_fingerprint,
                "action": row.action,
                "rotation_required": row.rotation_required,
                "replacement_secret_configured": row.replacement_secret_reference is not None,
                "rotation_evidence": row.rotation_evidence,
                "rotation_confirmed_by": row.rotation_confirmed_by,
                "rotation_confirmed_at": row.rotation_confirmed_at,
                "created_at": row.created_at,
            }
            for row in security_audits
        ],
        "source_security_audits": [
            {
                "audit_id": row.id,
                "source_id": row.source_id,
                "finding_categories": row.finding_categories,
                "original_fingerprint": row.original_fingerprint,
                "action": row.action,
                "rotation_required": row.rotation_required,
                "replacement_secret_configured": row.replacement_secret_reference is not None,
                "rotation_evidence": row.rotation_evidence,
                "rotation_confirmed_by": row.rotation_confirmed_by,
                "rotation_confirmed_at": row.rotation_confirmed_at,
                "created_at": row.created_at,
            }
            for row in source_security_audits
        ],
        "meta": {
            "snapshot_at": datetime.now(UTC),
            "secrets_redacted": True,
            "serialization_verified": quarantined_active_count == 0,
            "quarantined_active_count": quarantined_active_count,
            "pending_credential_rotations": sum(
                1 for row in security_audits if row.rotation_required
            )
            + sum(1 for row in source_security_audits if row.rotation_required),
            "configuration_schemas": platform_configuration_schema_names(),
            "source": "postgresql-versioned-platform-governance",
        },
    }


@router.get("/platform/configuration-status", tags=["platform"])
async def platform_configuration_status(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    health = await redacted_platform_configuration_status(session)
    return {
        "data": health,
        "meta": {
            "snapshot_at": datetime.now(UTC),
            "redacted": True,
            "source": "postgresql-versioned-platform-governance",
        },
    }


@router.post("/platform/data-sources", tags=["platform"])
async def configure_data_source(
    payload: IngestSourcePolicyRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(
        require_global_roles("operations_manager", data_scopes="platform")
    ),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        row = await upsert_ingest_source_policy(session, payload, subject=principal.subject)
        return {
            "source_id": row.id,
            "display_name": row.display_name,
            "source_kind": row.source_kind,
            "enabled": row.enabled,
            "policy": row.policy,
            "secret_configured": row.credential_secret_reference is not None,
            "updated_at": row.updated_at,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="platform.data-source.configure.v1",
        target=payload.source_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post(
    "/platform/data-contracts",
    status_code=status.HTTP_201_CREATED,
    tags=["platform"],
)
async def create_data_contract_command(
    payload: DataContractCreateRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(
        require_global_roles("operations_manager", data_scopes="platform")
    ),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        row = await create_data_contract(session, payload, subject=principal.subject)
        return {
            "contract_id": row.id,
            "source_id": row.source_id,
            "variable": row.variable,
            "revision": row.revision,
            "contract": row.contract,
            "created_at": row.created_at,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="platform.data-contract.create.v1",
        target=f"{payload.source_id}:{payload.variable}",
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post(
    "/platform/configurations",
    status_code=status.HTTP_201_CREATED,
    tags=["platform"],
)
async def create_platform_configuration_command(
    payload: PlatformConfigurationCreateRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(
        require_global_roles("operations_manager", data_scopes="platform")
    ),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        row = await create_platform_configuration_revision(
            session,
            payload,
            subject=principal.subject,
        )
        serialized = serialize_platform_configuration_revision(row)
        if serialized is None:  # pragma: no cover - guarded before persistence
            raise RuntimeError("new platform configuration failed safe serialization")
        return {"configuration_id": row.id, **serialized}

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="platform.configuration.create.v1",
        target=payload.configuration_key,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post(
    "/platform/configuration-security-audits/{audit_id}/rotation-confirmation",
    tags=["platform"],
)
async def confirm_platform_configuration_rotation_command(
    audit_id: str,
    payload: PlatformConfigurationRotationConfirmationRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(
        require_global_roles("operations_manager", data_scopes="platform")
    ),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        audit = await confirm_platform_configuration_rotation(
            session,
            audit_id=audit_id,
            request=payload,
            subject=principal.subject,
        )
        return {
            "audit_id": audit.id,
            "configuration_id": audit.configuration_id,
            "rotation_required": audit.rotation_required,
            "replacement_secret_configured": audit.replacement_secret_reference is not None,
            "rotation_confirmed_by": audit.rotation_confirmed_by,
            "rotation_confirmed_at": audit.rotation_confirmed_at,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="platform.configuration-rotation.confirm.v1",
        target=audit_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post(
    "/platform/data-source-security-audits/{audit_id}/rotation-confirmation",
    tags=["platform"],
)
async def confirm_ingest_source_rotation_command(
    audit_id: str,
    payload: PlatformConfigurationRotationConfirmationRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(
        require_global_roles("operations_manager", data_scopes="platform")
    ),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        audit = await confirm_ingest_source_rotation(
            session,
            audit_id=audit_id,
            replacement_secret_reference=payload.replacement_secret_reference,
            rotation_evidence=payload.rotation_evidence,
            subject=principal.subject,
        )
        return {
            "audit_id": audit.id,
            "source_id": audit.source_id,
            "rotation_required": audit.rotation_required,
            "replacement_secret_configured": audit.replacement_secret_reference is not None,
            "rotation_confirmed_by": audit.rotation_confirmed_by,
            "rotation_confirmed_at": audit.rotation_confirmed_at,
        }

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="platform.data-source-rotation.confirm.v1",
        target=audit_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result
