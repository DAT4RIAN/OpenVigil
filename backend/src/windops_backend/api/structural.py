from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.api.deps import (
    Principal,
    get_artifact_verifier,
    get_runtime_settings,
    get_session,
    require_read_access,
    require_roles,
)
from windops_backend.config import Settings
from windops_backend.errors import InvalidTransitionError, NotFoundError
from windops_backend.model_base import utcnow
from windops_backend.model_structural import (
    HealthBaseline,
    ModalObservation,
    PrestressObservation,
    SensorChannel,
    StructuralAnalysisRun,
    TendonAssembly,
    TowerComponent,
    WaveformRecord,
)
from windops_backend.schema_structural import (
    AnalysisCreate,
    BaselineCreate,
    ComponentCreate,
    PrestressCreate,
    SensorCreate,
    StructuralUpload,
    TendonCreate,
    WaveformCreate,
    aware,
)
from windops_backend.services.idempotency import execute_idempotent_command
from windops_backend.services.structural import (
    STRUCTURAL_CONTENT_TYPES,
    artifact_prefix,
    asset_scope,
    create_component,
    create_sensor,
    create_tendon,
    prestress_page_trends,
    register_prestress,
    register_waveform,
    related,
    serialize,
    submit_analysis,
)
from windops_backend.services.structural_baseline import publish_baseline
from windops_backend.storage import ArtifactVerifier
from windops_backend.structural_baseline import compare_to_baseline
from windops_backend.structural_provenance import deployment_identity

router = APIRouter(tags=["structural"])


async def _command(
    session: AsyncSession,
    response: Response,
    principal: Principal,
    key: str,
    command: str,
    target: str,
    payload: Any,
    operation: Callable[[], Awaitable[dict[str, Any]]],
    status_code: int = 201,
) -> dict[str, Any]:
    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type=f"structural.{command}.v1",
        target=target,
        idempotency_key=key,
        payload=payload,
        status_code=status_code,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post("/tower-components", status_code=201)
async def add_component(
    payload: ComponentCreate,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    await asset_scope(session, payload.turbine_id)
    return await _command(
        session,
        response,
        principal,
        key,
        "component.create",
        payload.turbine_id,
        payload,
        lambda: create_component(session, payload, principal.subject),
    )


@router.post("/tendon-assemblies", status_code=201)
async def add_tendon(
    payload: TendonCreate,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    await asset_scope(session, payload.turbine_id)
    return await _command(
        session,
        response,
        principal,
        key,
        "tendon.create",
        payload.turbine_id,
        payload,
        lambda: create_tendon(session, payload, principal.subject),
    )


@router.post("/sensor-channels", status_code=201)
async def add_sensor(
    payload: SensorCreate,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    await asset_scope(session, payload.turbine_id)
    return await _command(
        session,
        response,
        principal,
        key,
        "sensor.create",
        payload.turbine_id,
        payload,
        lambda: create_sensor(session, payload, principal.subject),
    )


@router.post("/structural-records/uploads/presign")
async def upload_acquisition(
    payload: StructuralUpload,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager", "field_technician")),
    settings: Settings = Depends(get_runtime_settings),
    verifier: ArtifactVerifier = Depends(get_artifact_verifier),
) -> dict[str, Any]:
    await asset_scope(session, payload.turbine_id)

    async def operation() -> dict[str, Any]:
        try:
            return await verifier.create_object_upload(
                bucket=settings.minio_field_evidence_bucket,
                prefix=artifact_prefix(payload.turbine_id),
                file_name=payload.file_name,
                content_type="application/json",
                artifact_sha256=payload.artifact_sha256,
                allowed_content_types=STRUCTURAL_CONTENT_TYPES,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc

    return await _command(
        session,
        response,
        principal,
        key,
        "upload",
        payload.turbine_id,
        payload,
        operation,
        status_code=200,
    )


@router.post("/structural-records", status_code=201)
async def add_waveform(
    payload: WaveformCreate,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager", "field_technician")),
    settings: Settings = Depends(get_runtime_settings),
    verifier: ArtifactVerifier = Depends(get_artifact_verifier),
) -> dict[str, Any]:
    await asset_scope(session, payload.turbine_id)
    return await _command(
        session,
        response,
        principal,
        key,
        "record.create",
        payload.turbine_id,
        payload,
        lambda: register_waveform(
            session, payload, principal.subject, verifier, settings.minio_field_evidence_bucket
        ),
    )


@router.post("/structural-analyses", status_code=202)
async def add_analysis(
    payload: AnalysisCreate,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager", "maintenance_reviewer")),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    # Recheck object scope even on receipt replay; permissions can be revoked.
    record = await session.get(WaveformRecord, payload.record_id)
    if record is None:
        raise NotFoundError("structural record was not found")
    return await _command(
        session,
        response,
        principal,
        key,
        "analysis.create",
        record.turbine_id,
        payload,
        lambda: submit_analysis(
            session, payload, principal.subject, deployment=deployment_identity(settings, "api")
        ),
        status_code=202,
    )


@router.get("/structural-analyses/{run_id}")
async def analysis_detail(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    row = await session.get(StructuralAnalysisRun, run_id)
    if row is None:
        raise NotFoundError("structural analysis was not found")
    modes = await session.scalars(
        select(ModalObservation)
        .where(ModalObservation.run_id == row.id)
        .order_by(ModalObservation.mode_index)
        .limit(8)
    )
    return {**serialize(row), "modal_observations": [serialize(mode) for mode in modes]}


@router.get("/structural-records")
async def waveform_collection(
    turbine_id: str,
    cursor: str | None = Query(None, max_length=36),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    await asset_scope(session, turbine_id)
    return await _page(session, WaveformRecord, turbine_id, cursor, limit)


@router.post("/prestress-observations", status_code=201)
async def add_prestress(
    payload: PrestressCreate,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager", "field_technician")),
    settings: Settings = Depends(get_runtime_settings),
    verifier: ArtifactVerifier = Depends(get_artifact_verifier),
) -> dict[str, Any]:
    await asset_scope(session, payload.turbine_id)
    return await _command(
        session,
        response,
        principal,
        key,
        "prestress.create",
        payload.turbine_id,
        payload,
        lambda: register_prestress(
            session, payload, principal.subject, verifier, settings.minio_field_evidence_bucket
        ),
    )


async def _page(
    session: AsyncSession, model: Any, turbine_id: str, cursor: str | None, limit: int
) -> dict[str, Any]:
    statement = select(model).where(model.turbine_id == turbine_id)
    if cursor:
        statement = statement.where(model.id > cursor)
    rows = list((await session.scalars(statement.order_by(model.id).limit(limit + 1))).all())
    return {
        "items": [serialize(r) for r in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


@router.get("/turbines/{turbine_id}/tower-components")
async def tower_topology(
    turbine_id: str,
    component_cursor: str | None = Query(None, max_length=36),
    tendon_cursor: str | None = Query(None, max_length=36),
    sensor_cursor: str | None = Query(None, max_length=36),
    limit: int = Query(100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    scope = await asset_scope(session, turbine_id)
    return {
        **scope,
        "components": await _page(session, TowerComponent, turbine_id, component_cursor, limit),
        "tendons": await _page(session, TendonAssembly, turbine_id, tendon_cursor, limit),
        "sensors": await _page(session, SensorChannel, turbine_id, sensor_cursor, limit),
    }


@router.get("/turbines/{turbine_id}/structural-health")
async def structural_health(
    turbine_id: str,
    run_cursor: str | None = Query(None, max_length=36),
    prestress_cursor: str | None = Query(None, max_length=36),
    baseline_id: str | None = Query(None, max_length=36),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    scope = await asset_scope(session, turbine_id)
    runs = await _page(session, StructuralAnalysisRun, turbine_id, run_cursor, limit)
    latest_run = await session.scalar(
        select(StructuralAnalysisRun)
        .where(StructuralAnalysisRun.turbine_id == turbine_id)
        .order_by(StructuralAnalysisRun.created_at.desc(), StructuralAnalysisRun.id.desc())
        .limit(1)
    )
    if baseline_id:
        baseline = await related(session, HealthBaseline, baseline_id, turbine_id)
    else:
        baseline = await session.scalar(
            select(HealthBaseline)
            .where(HealthBaseline.turbine_id == turbine_id)
            .order_by(HealthBaseline.created_at.desc(), HealthBaseline.id.desc())
            .limit(1)
        )
    baseline_status = (
        "unavailable"
        if baseline is None
        else ("expired" if aware(baseline.valid_until) <= utcnow() else "available_for_screening")
    )
    comparisons = []
    if baseline is not None and baseline_status == "available_for_screening":
        for run in runs["items"]:
            if run["status"] != "succeeded":
                continue
            record = await related(session, WaveformRecord, run["record_id"], turbine_id)
            comparisons.append(
                {
                    "run_id": run["id"],
                    "baseline_id": baseline.id,
                    "baseline_revision": baseline.revision,
                    **compare_to_baseline(baseline.model, run, serialize(record)),
                }
            )
    prestress = await _page(session, PrestressObservation, turbine_id, prestress_cursor, limit)
    has_prestress = await session.scalar(
        select(PrestressObservation.id)
        .where(PrestressObservation.turbine_id == turbine_id)
        .limit(1)
    )
    assessment_status = (
        {
            "succeeded": "requires_engineering_review",
            "pending": "analysis_in_progress",
            "running": "analysis_in_progress",
            "insufficient_data": "insufficient_data",
            "failed": "analysis_failed",
        }.get(latest_run.status, "no_data")
        if latest_run
        else ("requires_engineering_review" if has_prestress else "no_data")
    )
    return {
        **scope,
        "analyses": runs,
        "latest_analysis": serialize(latest_run) if latest_run else None,
        "prestress": prestress,
        "prestress_trends": prestress_page_trends(prestress["items"]),
        "assessment_status": assessment_status,
        "baseline_status": baseline_status,
        "baseline": serialize(baseline) if baseline else None,
        "comparisons": comparisons,
        "damage_probability": None,
        "field_qualification": "unverified",
        "fixture_fallback": False,
    }


@router.post("/health-baselines", status_code=201)
async def add_baseline(
    payload: BaselineCreate,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager", "maintenance_reviewer")),
) -> dict[str, Any]:
    await asset_scope(session, payload.turbine_id)
    return await _command(
        session,
        response,
        principal,
        key,
        "baseline.publish",
        payload.turbine_id,
        payload,
        lambda: publish_baseline(session, payload, principal.subject),
    )


@router.get("/health-baselines/{baseline_id}")
async def baseline_detail(
    baseline_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    baseline = await session.get(HealthBaseline, baseline_id)
    if baseline is None:
        raise NotFoundError("structural baseline was not found")
    return serialize(baseline)
