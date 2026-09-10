from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.api.deps import Principal, get_session, require_read_access
from windops_backend.schemas import BenchmarkArtifactExportRequest
from windops_backend.services.benchmark_catalog import (
    BENCHMARK_CURVE_POINT_MAX,
    BENCHMARK_CURVE_POINT_MIN,
    BENCHMARK_DATASET_PAGE_MAX,
    BENCHMARK_DIAGNOSIS_PAGE_MAX,
    BENCHMARK_EVALUATION_PAGE_MAX,
    BENCHMARK_EVENT_PAGE_MAX,
    BENCHMARK_EVENT_RESULT_PAGE_MAX,
    benchmark_dataset_page,
    benchmark_diagnosis_page,
    benchmark_domains_allowed,
    benchmark_evaluation_page,
    benchmark_evaluation_result_page,
    benchmark_event_page,
    benchmark_replay_curve,
    benchmark_truth_allowed,
)
from windops_backend.services.benchmark_governance import build_governed_benchmark_export

router = APIRouter()


def _require_benchmark_domains(
    principal: Principal, *domains: str, code: str, message: str
) -> None:
    if not benchmark_domains_allowed(principal.graph_access_policy(), *domains):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": code, "message": message},
        )


@router.get("/benchmarks/datasets", tags=["benchmarks"])
async def benchmark_datasets(
    query: str = Query(default="", alias="q", max_length=100),
    status_filter: Literal["registered", "importing", "ready", "failed"] | None = Query(
        default=None, alias="status"
    ),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=20, ge=1, le=BENCHMARK_DATASET_PAGE_MAX),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, object]:
    return await benchmark_dataset_page(
        session,
        principal.graph_access_policy(),
        query=query,
        status=status_filter,
        offset=offset,
        limit=limit,
    )


@router.get("/benchmarks/datasets/{dataset_version_id}/events", tags=["benchmarks"])
async def benchmark_events(
    dataset_version_id: str,
    query: str = Query(default="", alias="q", max_length=100),
    farm: Literal["A", "B", "C"] | None = None,
    event_label: Literal["anomaly", "normal"] | None = Query(default=None, alias="eventLabel"),
    reveal_truth: bool = Query(default=False, alias="revealTruth"),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=20, ge=1, le=BENCHMARK_EVENT_PAGE_MAX),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, object]:
    policy = principal.graph_access_policy()
    if (event_label is not None or reveal_truth) and not benchmark_truth_allowed(policy):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "BENCHMARK_TRUTH_FORBIDDEN",
                "message": "Prediction truth requires the benchmark_truth data scope",
            },
        )
    return await benchmark_event_page(
        session,
        policy,
        dataset_version_id=dataset_version_id,
        query=query,
        farm=farm,
        event_label=event_label,
        reveal_truth=reveal_truth,
        offset=offset,
        limit=limit,
    )


@router.get("/benchmarks/evaluations", tags=["benchmarks", "models"])
async def benchmark_evaluations(
    query: str = Query(default="", alias="q", max_length=100),
    model_id: str | None = Query(default=None, alias="modelId", min_length=1, max_length=64),
    status_filter: Literal["pending", "running", "completed", "failed", "cancelled"] | None = Query(
        default=None, alias="status"
    ),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=20, ge=1, le=BENCHMARK_EVALUATION_PAGE_MAX),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, object]:
    _require_benchmark_domains(
        principal,
        "benchmark",
        "model",
        code="BENCHMARK_MODEL_FORBIDDEN",
        message="Benchmark evaluation access requires benchmark and model data scopes",
    )
    return await benchmark_evaluation_page(
        session,
        principal.graph_access_policy(),
        query=query,
        model_id=model_id,
        status=status_filter,
        offset=offset,
        limit=limit,
    )


@router.get("/benchmarks/evaluations/{evaluation_run_id}/results", tags=["benchmarks", "models"])
async def benchmark_evaluation_results(
    evaluation_run_id: str,
    status_filter: Literal["scored", "failed", "unscorable"] | None = Query(
        default=None, alias="status"
    ),
    reveal_truth: bool = Query(default=False, alias="revealTruth"),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=20, ge=1, le=BENCHMARK_EVENT_RESULT_PAGE_MAX),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, object]:
    _require_benchmark_domains(
        principal,
        "benchmark",
        "model",
        code="BENCHMARK_MODEL_FORBIDDEN",
        message="Benchmark evaluation access requires benchmark and model data scopes",
    )
    policy = principal.graph_access_policy()
    if reveal_truth and not benchmark_truth_allowed(policy):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "BENCHMARK_TRUTH_FORBIDDEN",
                "message": "Prediction truth requires the benchmark_truth data scope",
            },
        )
    return await benchmark_evaluation_result_page(
        session,
        policy,
        evaluation_run_id=evaluation_run_id,
        status=status_filter,
        reveal_truth=reveal_truth,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/benchmarks/evaluations/{evaluation_run_id}/exports",
    tags=["benchmarks", "models"],
)
async def export_benchmark_evaluation(
    evaluation_run_id: str,
    request: BenchmarkArtifactExportRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> Response:
    _require_benchmark_domains(
        principal,
        "benchmark",
        "model",
        "benchmark_export",
        code="BENCHMARK_EXPORT_FORBIDDEN",
        message=(
            "Benchmark report export requires benchmark, model, and benchmark_export data scopes"
        ),
    )
    policy = principal.graph_access_policy()
    if request.include_truth and not benchmark_truth_allowed(policy):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "BENCHMARK_TRUTH_FORBIDDEN",
                "message": "Prediction truth requires the benchmark_truth data scope",
            },
        )
    exported = await build_governed_benchmark_export(
        session,
        policy,
        evaluation_run_id=evaluation_run_id,
        request=request,
        idempotency_key=idempotency_key,
        subject=principal.subject,
    )
    await session.commit()
    return Response(
        content=exported.content,
        media_type=exported.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{exported.file_name}"',
            "X-WindOps-Artifact-SHA256": exported.artifact_sha256,
            "X-WindOps-Payload-SHA256": exported.payload_sha256,
            "X-WindOps-Audit-Event-ID": exported.audit_event_id,
            "X-WindOps-Export-Replayed": str(exported.replayed).lower(),
            "X-WindOps-Data-License": "CC BY-SA 4.0",
            "Cache-Control": "no-store",
        },
    )


@router.get("/benchmarks/diagnoses", tags=["benchmarks", "diagnosis"])
async def benchmark_diagnoses(
    query: str = Query(default="", alias="q", max_length=100),
    status_filter: Literal["pending", "running", "cancelling", "cancelled", "completed", "failed"]
    | None = Query(default=None, alias="status"),
    reveal_truth: bool = Query(default=False, alias="revealTruth"),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=20, ge=1, le=BENCHMARK_DIAGNOSIS_PAGE_MAX),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, object]:
    _require_benchmark_domains(
        principal,
        "benchmark",
        "model",
        "mission",
        code="BENCHMARK_DIAGNOSIS_FORBIDDEN",
        message="Benchmark diagnosis access requires benchmark, model, and mission data scopes",
    )
    policy = principal.graph_access_policy()
    if reveal_truth and not benchmark_truth_allowed(policy):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "BENCHMARK_TRUTH_FORBIDDEN",
                "message": "Prediction truth requires the benchmark_truth data scope",
            },
        )
    return await benchmark_diagnosis_page(
        session,
        policy,
        query=query,
        status=status_filter,
        reveal_truth=reveal_truth,
        offset=offset,
        limit=limit,
    )


@router.get("/benchmarks/replay-runs/{replay_run_id}/curve", tags=["benchmarks"])
async def benchmark_replay_run_curve(
    replay_run_id: str,
    variable: str = Query(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$"),
    max_points: int = Query(
        default=256,
        alias="maxPoints",
        ge=BENCHMARK_CURVE_POINT_MIN,
        le=BENCHMARK_CURVE_POINT_MAX,
    ),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, object]:
    return await benchmark_replay_curve(
        session,
        principal.graph_access_policy(),
        replay_run_id=replay_run_id,
        variable=variable,
        max_points=max_points,
    )
