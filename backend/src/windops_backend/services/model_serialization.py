from __future__ import annotations

from typing import Any

from windops_backend.models import (
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
)


def serialize_model(model: RegisteredModel, deployments: list[ModelDeployment]) -> dict[str, Any]:
    return {
        "model_id": model.id,
        "name": model.name,
        "version": model.version,
        "kind": model.kind,
        "status": model.status,
        "description": model.description,
        "artifact_uri": model.artifact_uri,
        "artifact_sha256": model.artifact_sha256,
        "content_type": model.content_type,
        "content_size_bytes": model.content_size_bytes,
        "input_schema": model.input_schema,
        "output_schema": model.output_schema,
        "metrics": model.metrics,
        "created_by": model.created_by,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
        "deployments": [serialize_deployment(item) for item in deployments],
    }


def serialize_deployment(deployment: ModelDeployment) -> dict[str, Any]:
    return {
        "deployment_id": deployment.id,
        "model_id": deployment.model_id,
        "target_id": deployment.target_id,
        "stage": deployment.stage,
        "status": deployment.status,
        "traffic_percent": deployment.traffic_percent,
        "evaluation_gate": deployment.evaluation_gate,
        "rollback_from_id": deployment.rollback_from_id,
        "deployed_by": deployment.deployed_by,
        "deployed_at": deployment.deployed_at,
        "activated_at": deployment.activated_at,
        "retired_at": deployment.retired_at,
    }


def serialize_prediction(prediction: ModelPrediction) -> dict[str, Any]:
    return {
        "prediction_id": prediction.id,
        "model_id": prediction.model_id,
        "deployment_id": prediction.deployment_id,
        "turbine_id": prediction.turbine_id,
        "feature_observed_at": prediction.feature_observed_at,
        "input_digest": prediction.input_digest,
        "output": prediction.output,
        "status": prediction.status,
        "error_code": prediction.error_code,
        "latency_ms": prediction.latency_ms,
        "requested_by": prediction.requested_by,
        "created_at": prediction.created_at,
    }
