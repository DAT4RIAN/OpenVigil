import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.api.deps import (
    Principal,
    _drain_or_dispatch_graph_projection_events,
    get_artifact_verifier,
    get_model_inference_client,
    get_runtime_settings,
    get_session,
    require_global_roles,
    require_read_access,
)
from windops_backend.config import Settings
from windops_backend.errors import (
    AnomalyActivationArtifactDriftError,
    AnomalyActivationBindingError,
    AnomalyActivationConcurrencyError,
    AnomalyActivationEvaluationError,
    DomainError,
    InvalidTransitionError,
    NotFoundError,
)
from windops_backend.models import (
    Alarm,
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
    Turbine,
)
from windops_backend.outbox import (
    mark_dispatched,
    pending_events_for_missions,
    process_outbox_event,
)
from windops_backend.schemas import (
    AnomalyReplayInferenceRequest,
    ModelActivationRequest,
    ModelArtifactUploadRequest,
    ModelDeploymentRequest,
    ModelRegisterRequest,
    ModelRollbackRequest,
    PredictiveRunRequest,
)
from windops_backend.services.anomaly_alerts import (
    evaluate_anomaly_alert,
    run_replay_anomaly_inference,
)
from windops_backend.services.events import append_domain_event
from windops_backend.services.idempotency import execute_idempotent_command
from windops_backend.services.models import (
    ALLOWED_MODEL_CONTENT_TYPES,
    MAX_MODEL_ARTIFACT_BYTES,
    ModelInferenceClient,
    create_deployment,
    govern_and_activate_deployment,
    register_model,
    run_predictive_inference,
    serialize_deployment,
    serialize_model,
    serialize_prediction,
)
from windops_backend.services.workflow import advance_mission_to_review
from windops_backend.storage import ArtifactVerifier

router = APIRouter()
# The model target allows at most 20s, each batch has 25s, and the production
# gateway gives this path a dedicated 30s deadline.  Keep this contract in the
# backend rather than relying on the gateway's shorter global default.
PREDICTIVE_BATCH_TIMEOUT_SECONDS = 25


@router.post(
    "/models/deployments/{deployment_id}/anomaly-predictions/run",
    tags=["models"],
)
async def run_anomaly_replay_prediction(
    deployment_id: str,
    payload: AnomalyReplayInferenceRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    inference_client: ModelInferenceClient = Depends(get_model_inference_client),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="model")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        prediction = await run_replay_anomaly_inference(
            session,
            settings,
            inference_client,
            deployment_id=deployment_id,
            benchmark_replay_run_id=payload.benchmark_replay_run_id,
            source_row_id=payload.source_row_id,
            subject=principal.subject,
        )
        return serialize_prediction(prediction)

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="model.anomaly-replay-inference.run.v1",
        target=deployment_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post("/model-predictions/{prediction_id}/alert-evaluation", tags=["models"])
async def evaluate_anomaly_prediction_alert(
    prediction_id: str,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="model")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        outcome = await evaluate_anomaly_alert(
            session,
            prediction_id=prediction_id,
            subject=principal.subject,
        )
        return outcome.to_document()

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="model.anomaly-alert.evaluate.v1",
        target=prediction_id,
        idempotency_key=idempotency_key,
        payload={"prediction_id": prediction_id},
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    mission_ids = [str(result["mission_id"])] if result.get("mission_id") else []
    event_ids = await pending_events_for_missions(session, mission_ids)
    await session.commit()
    app_factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    if settings.outbox_inline_drain:
        for event_id in event_ids:
            await process_outbox_event(app_factory, settings, event_id, advance_mission_to_review)
    else:
        from windops_backend.workers import dispatch_event_ids

        dispatch_event_ids(event_ids)
        await mark_dispatched(app_factory, event_ids)
    await _drain_or_dispatch_graph_projection_events(request, settings)
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.get("/models", tags=["models"])
async def model_collection(
    query: str | None = Query(default=None, alias="q", max_length=100),
    kind: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = select(RegisteredModel)
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            RegisteredModel.name.ilike(pattern) | RegisteredModel.id.ilike(pattern)
        )
    if kind:
        statement = statement.where(RegisteredModel.kind == kind)
    if status_filter:
        statement = statement.where(RegisteredModel.status == status_filter)
    models = list((await session.scalars(statement.order_by(RegisteredModel.id))).all())
    model_ids = [model.id for model in models]
    deployments = (
        list(
            (
                await session.scalars(
                    select(ModelDeployment).where(ModelDeployment.model_id.in_(model_ids))
                )
            ).all()
        )
        if model_ids
        else []
    )
    by_model: dict[str, list[ModelDeployment]] = {}
    for deployment in deployments:
        by_model.setdefault(deployment.model_id, []).append(deployment)
    prediction_total, succeeded_count, last_prediction_at = (
        await session.execute(
            select(
                func.count(ModelPrediction.id),
                func.sum(case((ModelPrediction.status == "succeeded", 1), else_=0)),
                func.max(ModelPrediction.created_at),
            )
        )
    ).one()
    prediction_total = int(prediction_total or 0)
    succeeded_count = int(succeeded_count or 0)
    failed_count = prediction_total - succeeded_count
    latency_rows = (
        select(
            ModelPrediction.latency_ms.label("latency_ms"),
            func.cume_dist()
            .over(order_by=ModelPrediction.latency_ms)
            .label("cumulative_distribution"),
        )
        .where(ModelPrediction.status == "succeeded")
        .subquery()
    )
    p95_latency = await session.scalar(
        select(func.min(latency_rows.c.latency_ms)).where(
            latency_rows.c.cumulative_distribution >= 0.95
        )
    )
    active_deployment_count = int(
        await session.scalar(
            select(func.count(ModelDeployment.id)).where(ModelDeployment.status == "active")
        )
        or 0
    )
    return {
        "count": len(models),
        "models": [serialize_model(model, by_model.get(model.id, [])) for model in models],
        "meta": {
            "artifact_count": len(models),
            "active_deployment_count": active_deployment_count,
            "real_inference_count": succeeded_count,
            "monitoring": {
                "prediction_count": prediction_total,
                "succeeded_count": succeeded_count,
                "failed_count": failed_count,
                "success_rate": (
                    round(succeeded_count / prediction_total, 4) if prediction_total else None
                ),
                "p95_latency_ms": int(p95_latency or 0),
                "last_prediction_at": last_prediction_at,
            },
        },
    }


@router.post("/models/uploads/presign", tags=["models"])
async def presign_model_artifact_upload(
    payload: ModelArtifactUploadRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="model")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        try:
            upload = await artifact_verifier.create_object_upload(
                bucket=settings.minio_model_bucket,
                prefix=f"models/{payload.model_id}",
                file_name=payload.file_name,
                content_type=payload.content_type,
                artifact_sha256=payload.artifact_sha256,
                allowed_content_types=ALLOWED_MODEL_CONTENT_TYPES,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        return {"model_id": payload.model_id, **upload}

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="model.upload.presign.v1",
        target=payload.model_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post("/models", status_code=status.HTTP_201_CREATED, tags=["models"])
async def register_model_artifact(
    payload: ModelRegisterRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="model")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        try:
            content, stored_content_type = await artifact_verifier.read_verified_object(
                payload.artifact_uri,
                payload.artifact_sha256,
                bucket=settings.minio_model_bucket,
                prefix=f"models/{payload.model_id}",
                allowed_content_types=ALLOWED_MODEL_CONTENT_TYPES,
                max_bytes=MAX_MODEL_ARTIFACT_BYTES,
            )
            if stored_content_type != payload.content_type:
                raise ValueError("stored model object content type does not match the command")
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        model, model_replayed = await register_model(
            session,
            payload,
            content_size_bytes=len(content),
            subject=principal.subject,
        )
        return {**serialize_model(model, []), "replayed": model_replayed}

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="model.register.v1",
        target=payload.model_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post(
    "/models/{model_id}/deployments",
    status_code=status.HTTP_201_CREATED,
    tags=["models"],
)
async def stage_model_deployment(
    model_id: str,
    payload: ModelDeploymentRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="model")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        deployment = await create_deployment(
            session,
            settings,
            model_id=model_id,
            target_id=payload.target_id,
            stage=payload.stage,
            evaluation_gate=payload.evaluation_gate,
            subject=principal.subject,
        )
        return serialize_deployment(deployment)

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="model.deployment.stage.v1",
        target=model_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post("/models/deployments/{deployment_id}/activate", tags=["models"])
async def activate_model_deployment(
    deployment_id: str,
    payload: ModelActivationRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="model")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        deployment = await govern_and_activate_deployment(
            session,
            settings,
            artifact_verifier,
            deployment_id=deployment_id,
            traffic_percent=payload.traffic_percent,
            reason=payload.reason,
            subject=principal.subject,
        )
        return serialize_deployment(deployment)

    try:
        result, replayed = await execute_idempotent_command(
            session,
            subject=principal.subject,
            command_type="model.deployment.activate.v1",
            target=deployment_id,
            idempotency_key=idempotency_key,
            payload=payload,
            status_code=status.HTTP_200_OK,
            operation=operation,
        )
    except (
        AnomalyActivationArtifactDriftError,
        AnomalyActivationBindingError,
        AnomalyActivationConcurrencyError,
        AnomalyActivationEvaluationError,
    ) as exc:
        append_domain_event(
            session,
            event_type="model.activation.denied",
            aggregate_type="model_deployment",
            aggregate_id=deployment_id,
            payload={
                "operation": "activate",
                "deployment_id": deployment_id,
                "error_code": exc.code,
                "reason": exc.message,
                "subject": principal.subject,
            },
        )
        await session.commit()
        raise
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post("/models/{model_id}/rollback", tags=["models"])
async def rollback_model_deployment(
    model_id: str,
    payload: ModelRollbackRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="model")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        target = await session.get(ModelDeployment, payload.target_deployment_id)
        if target is None or target.model_id != model_id:
            raise NotFoundError("the requested rollback deployment does not belong to this model")
        deployment = await govern_and_activate_deployment(
            session,
            settings,
            artifact_verifier,
            deployment_id=target.id,
            traffic_percent=100,
            reason=payload.reason,
            subject=principal.subject,
            rollback=True,
        )
        return serialize_deployment(deployment)

    try:
        result, replayed = await execute_idempotent_command(
            session,
            subject=principal.subject,
            command_type="model.deployment.rollback.v1",
            target=model_id,
            idempotency_key=idempotency_key,
            payload=payload,
            status_code=status.HTTP_200_OK,
            operation=operation,
        )
    except (
        AnomalyActivationArtifactDriftError,
        AnomalyActivationBindingError,
        AnomalyActivationConcurrencyError,
        AnomalyActivationEvaluationError,
    ) as exc:
        append_domain_event(
            session,
            event_type="model.activation.denied",
            aggregate_type="model_deployment",
            aggregate_id=payload.target_deployment_id,
            payload={
                "operation": "rollback",
                "deployment_id": payload.target_deployment_id,
                "model_id": model_id,
                "error_code": exc.code,
                "reason": exc.message,
                "subject": principal.subject,
            },
        )
        await session.commit()
        raise
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post("/predictive-assessments/run", tags=["models"])
async def run_predictive_assessments(
    payload: PredictiveRunRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    inference_client: ModelInferenceClient = Depends(get_model_inference_client),
    principal: Principal = Depends(require_global_roles("operations_manager", data_scopes="model")),
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failed = 0
    processed = 0
    replayed_count = 0
    try:
        # Keep synchronous batches below the path-specific gateway contract;
        # each turbine is committed independently so a slow target cannot keep
        # completed predictions in one transaction or hold an advisory lock.
        async with asyncio.timeout(PREDICTIVE_BATCH_TIMEOUT_SECONDS):
            for turbine_id in payload.turbine_ids:

                async def operation(turbine_id: str = turbine_id) -> dict[str, Any]:
                    try:
                        prediction = await run_predictive_inference(
                            session,
                            settings,
                            inference_client,
                            turbine_id=turbine_id,
                            subject=principal.subject,
                        )
                    except DomainError as exc:
                        return {
                            "turbine_id": turbine_id,
                            "status": "failed",
                            "error_code": exc.code,
                        }
                    return serialize_prediction(prediction)

                item_key = hashlib.sha256(
                    f"predictive-run-v1:{idempotency_key.strip()}:{processed}".encode()
                ).hexdigest()
                item_result, _replayed = await execute_idempotent_command(
                    session,
                    subject=principal.subject,
                    command_type="model.predictive-assessment.run.v1",
                    target="batch",
                    idempotency_key=item_key,
                    payload={"batch": payload, "position": processed},
                    status_code=status.HTTP_200_OK,
                    operation=operation,
                )
                await session.commit()
                replayed_count += int(_replayed)
                failed += item_result.get("status") == "failed"
                results.append(item_result)
                processed += 1
    except asyncio.CancelledError:
        await session.rollback()
        raise
    except TimeoutError:
        await session.rollback()
        failed += len(payload.turbine_ids) - processed
        results.extend(
            {
                "turbine_id": turbine_id,
                "status": "failed",
                "error_code": "BATCH_TIMEOUT",
            }
            for turbine_id in payload.turbine_ids[processed:]
        )
        response.status_code = status.HTTP_207_MULTI_STATUS
    if failed:
        response.status_code = status.HTTP_207_MULTI_STATUS
    response.headers["Idempotency-Replayed"] = "true" if replayed_count == len(results) else "false"
    return {
        "count": len(results),
        "failed": failed,
        "predictions": results,
    }


@router.get("/predictive-assessments", tags=["models"])
async def predictive_assessment_collection(
    turbine_id: str | None = None,
    risk: str | None = None,
    trend: str | None = None,
    limit: int = Query(default=64, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    ranked_predictions = select(
        ModelPrediction.id.label("prediction_id"),
        func.row_number()
        .over(
            partition_by=ModelPrediction.turbine_id,
            order_by=(desc(ModelPrediction.created_at), desc(ModelPrediction.id)),
        )
        .label("row_number"),
    ).where(ModelPrediction.status == "succeeded")
    if turbine_id:
        ranked_predictions = ranked_predictions.where(ModelPrediction.turbine_id == turbine_id)
    latest_predictions = ranked_predictions.subquery()
    active_alarm_counts = (
        select(
            Alarm.turbine_id.label("alarm_turbine_id"),
            func.count(Alarm.id).label("active_alarm_count"),
        )
        .where(Alarm.status != "resolved")
        .group_by(Alarm.turbine_id)
        .subquery()
    )
    active_alarm_count = func.coalesce(active_alarm_counts.c.active_alarm_count, 0)
    probability = ModelPrediction.output["failure_probability_30d"].as_float()
    anomaly_score = ModelPrediction.output["anomaly_score"].as_float()
    probability_band = case(
        (probability > 40, 5),
        (probability > 25, 4),
        (probability > 12, 3),
        (probability > 5, 2),
        else_=1,
    )
    base_consequence = case(
        (Turbine.status == "critical", 4),
        (Turbine.status.in_(("warning", "offline")), 3),
        else_=2,
    )
    consequence = base_consequence + case((active_alarm_count >= 3, 1), else_=0)
    risk_score = probability_band * consequence
    matrix_risk = case(
        (risk_score >= 20, "critical"),
        (risk_score >= 12, "high"),
        (risk_score >= 6, "medium"),
        else_="low",
    )
    assessment_trend = ModelPrediction.output["trend"].as_string()
    priority_score = probability * consequence + anomaly_score * 10
    common_filters = [
        latest_predictions.c.row_number == 1,
        ModelPrediction.status == "succeeded",
    ]
    if risk:
        common_filters.append(matrix_risk == risk)
    if trend:
        common_filters.append(assessment_trend == trend)
    count_statement = (
        select(func.count(ModelPrediction.id))
        .select_from(ModelPrediction)
        .join(latest_predictions, latest_predictions.c.prediction_id == ModelPrediction.id)
        .join(Turbine, Turbine.id == ModelPrediction.turbine_id)
        .outerjoin(
            active_alarm_counts,
            active_alarm_counts.c.alarm_turbine_id == ModelPrediction.turbine_id,
        )
        .where(*common_filters)
    )
    total = int(await session.scalar(count_statement) or 0)
    page_statement = (
        select(
            ModelPrediction,
            Turbine,
            active_alarm_count.label("active_alarm_count"),
            matrix_risk.label("matrix_risk"),
            probability_band.label("probability_band"),
            consequence.label("consequence_band"),
            risk_score.label("risk_score"),
            priority_score.label("priority_score"),
        )
        .join(latest_predictions, latest_predictions.c.prediction_id == ModelPrediction.id)
        .join(Turbine, Turbine.id == ModelPrediction.turbine_id)
        .outerjoin(
            active_alarm_counts,
            active_alarm_counts.c.alarm_turbine_id == ModelPrediction.turbine_id,
        )
        .where(*common_filters)
        .order_by(desc(priority_score), Turbine.id)
        .limit(limit)
    )
    rows = (await session.execute(page_statement)).all()
    assessments: list[dict[str, Any]] = []
    for (
        prediction,
        turbine,
        alarm_count,
        row_matrix_risk,
        row_probability_band,
        row_consequence,
        row_risk_score,
        row_priority_score,
    ) in rows:
        output = prediction.output
        assessment_trend_value = str(output.get("trend", "stable"))
        matrix_risk_value = str(row_matrix_risk)
        probability_value = float(output["failure_probability_30d"])
        anomaly_value = float(output["anomaly_score"])
        consequence_value = int(row_consequence)
        assessments.append(
            {
                "assessment_id": prediction.id,
                "prediction_id": prediction.id,
                "model_id": prediction.model_id,
                "deployment_id": prediction.deployment_id,
                "turbine_id": turbine.id,
                "turbine_model": turbine.model,
                "health_score": turbine.health_score,
                "component": str(output["component"]),
                "component_health": float(output.get("component_health", turbine.health_score)),
                "turbine_status": turbine.status,
                "active_alarm_count": int(alarm_count),
                "state": str(output.get("state", "watch")),
                "trend": assessment_trend_value,
                "risk_level": matrix_risk_value,
                "failure_probability_30d": probability_value,
                "remaining_useful_life_days": float(output["remaining_useful_life_days"]),
                "anomaly_score": anomaly_value,
                "primary_finding": str(output["primary_finding"]),
                "probability_band": int(row_probability_band),
                "consequence_band": consequence_value,
                "matrix_risk": matrix_risk_value,
                "risk_score": int(row_risk_score),
                "priority_score": round(float(row_priority_score), 2),
                "assessed_at": prediction.created_at,
                "feature_observed_at": prediction.feature_observed_at,
                "latency_ms": prediction.latency_ms,
            }
        )
    active_deployments = list(
        (
            await session.scalars(select(ModelDeployment).where(ModelDeployment.status == "active"))
        ).all()
    )
    return {
        "count": len(assessments),
        "assessments": assessments,
        "meta": {
            "total": total,
            "snapshot_at": datetime.now(UTC),
            "active_deployments": [serialize_deployment(item) for item in active_deployments],
            "prediction_provider": "external-governed-inference" if active_deployments else None,
        },
    }
