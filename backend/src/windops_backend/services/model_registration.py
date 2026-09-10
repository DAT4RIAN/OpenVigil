from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.config import Settings
from windops_backend.errors import (
    ConflictError,
    InvalidTransitionError,
    NotFoundError,
)
from windops_backend.models import (
    ModelDeployment,
    RegisteredModel,
)
from windops_backend.schemas import ModelRegisterRequest
from windops_backend.services.events import append_domain_event


async def register_model(
    session: AsyncSession,
    request: ModelRegisterRequest,
    *,
    content_size_bytes: int,
    subject: str,
) -> tuple[RegisteredModel, bool]:
    existing = await session.get(RegisteredModel, request.model_id)
    if existing is not None:
        immutable_identity = (
            existing.name,
            existing.version,
            existing.kind,
            existing.artifact_uri,
            existing.artifact_sha256,
            existing.content_type,
            existing.content_size_bytes,
            existing.input_schema,
            existing.output_schema,
            existing.metrics,
            existing.description,
            existing.created_by,
        )
        requested_identity = (
            request.name,
            request.version,
            request.kind,
            request.artifact_uri,
            request.artifact_sha256.lower(),
            request.content_type,
            content_size_bytes,
            request.input_schema,
            request.output_schema,
            request.metrics,
            request.description,
            subject,
        )
        if immutable_identity == requested_identity:
            return existing, True
        raise ConflictError(f"model {request.model_id} already exists with different content")
    same_version = await session.scalar(
        select(RegisteredModel).where(
            RegisteredModel.name == request.name,
            RegisteredModel.version == request.version,
        )
    )
    if same_version is not None:
        raise ConflictError("the model name and version are already registered")
    model = RegisteredModel(
        id=request.model_id,
        name=request.name,
        version=request.version,
        kind=request.kind,
        status="registered",
        artifact_uri=request.artifact_uri,
        artifact_sha256=request.artifact_sha256.lower(),
        content_type=request.content_type,
        content_size_bytes=content_size_bytes,
        input_schema=request.input_schema,
        output_schema=request.output_schema,
        metrics=request.metrics,
        description=request.description,
        created_by=subject,
    )
    session.add(model)
    append_domain_event(
        session,
        event_type="model.registered",
        aggregate_type="model",
        aggregate_id=model.id,
        payload={
            "model_id": model.id,
            "name": model.name,
            "version": model.version,
            "kind": model.kind,
            "artifact_sha256": model.artifact_sha256,
            "created_by": subject,
        },
    )
    await session.flush()
    return model, False


async def create_deployment(
    session: AsyncSession,
    settings: Settings,
    *,
    model_id: str,
    target_id: str,
    stage: str,
    evaluation_gate: dict[str, Any],
    subject: str,
) -> ModelDeployment:
    model = await session.get(RegisteredModel, model_id)
    if model is None:
        raise NotFoundError(f"model {model_id} was not found")
    if model.kind not in {"predictive", "anomaly"}:
        raise InvalidTransitionError("only predictive or anomaly models can use model runtime")
    if target_id not in settings.model_inference_targets:
        raise InvalidTransitionError("the requested inference target is not configured")
    deployment = ModelDeployment(
        id=str(uuid4()),
        model_id=model.id,
        target_id=target_id,
        stage=stage,
        status="staged",
        traffic_percent=0,
        evaluation_gate=evaluation_gate,
        deployed_by=subject,
    )
    session.add(deployment)
    model.status = "staged"
    model.updated_at = datetime.now(UTC)
    append_domain_event(
        session,
        event_type="model.deployment.staged",
        aggregate_type="model_deployment",
        aggregate_id=deployment.id,
        payload={
            "deployment_id": deployment.id,
            "model_id": model.id,
            "target_id": target_id,
            "stage": stage,
            "deployed_by": subject,
        },
    )
    await session.flush()
    return deployment
