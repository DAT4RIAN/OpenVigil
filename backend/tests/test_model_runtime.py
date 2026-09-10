from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from windops_backend.api import model_registry
from windops_backend.config import ModelInferenceTarget
from windops_backend.models import IngestReceipt, IngestSource, ModelPrediction, ScadaSample
from windops_backend.services.models import run_predictive_inference
from windops_backend.storage import InMemoryArtifactVerifier

INPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["turbine_id", "observed_at", "signals"],
    "properties": {
        "turbine_id": {"type": "string"},
        "turbine_model": {"type": "string"},
        "health_score": {"type": "number"},
        "active_alarm_count": {"type": "integer", "minimum": 0},
        "observed_at": {"type": "string", "format": "date-time"},
        "signals": {
            "type": "object",
            "additionalProperties": {"type": "number"},
        },
    },
}
OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "component",
        "failure_probability_30d",
        "remaining_useful_life_days",
        "anomaly_score",
        "primary_finding",
    ],
    "properties": {
        "component": {"type": "string"},
        "component_health": {"type": "number", "minimum": 0, "maximum": 100},
        "failure_probability_30d": {"type": "number", "minimum": 0, "maximum": 100},
        "remaining_useful_life_days": {"type": "number", "minimum": 0},
        "anomaly_score": {"type": "number", "minimum": 0, "maximum": 1},
        "primary_finding": {"type": "string"},
        "trend": {"enum": ["improving", "stable", "declining"]},
    },
}


class FakeInferenceClient:
    def __init__(self, output: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[dict[str, Any], str]] = []
        self.output = output or {
            "component": "main bearing",
            "component_health": 68,
            "failure_probability_30d": 37.5,
            "remaining_useful_life_days": 42,
            "anomaly_score": 0.81,
            "primary_finding": "Persistent vibration and thermal features exceed baseline",
            "trend": "declining",
        }

    async def predict(
        self,
        target: ModelInferenceTarget,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int]:
        del target
        self.calls.append((payload, idempotency_key))
        return self.output, 27


class BlockingInferenceClient(FakeInferenceClient):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def predict(
        self,
        target: ModelInferenceTarget,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int]:
        del target
        self.calls.append((payload, idempotency_key))
        self.started.set()
        await self.release.wait()
        return self.output, 27


class CancellableInferenceClient(FakeInferenceClient):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def predict(
        self,
        target: ModelInferenceTarget,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int]:
        del target
        self.calls.append((payload, idempotency_key))
        self.started.set()
        await asyncio.sleep(3600)
        return self.output, 27


def _manager_headers() -> dict[str, str]:
    return {
        "X-WindOps-Test-Principal": "model-operator@example.com",
        "X-WindOps-Test-Role": "operations_manager",
        "Idempotency-Key": "model-runtime-command-001",
    }


async def _seed_good_scada(app: FastAPI) -> None:
    factory = app.state.session_factory
    observed_at = datetime(2026, 8, 14, 9, 30, tzinfo=UTC)
    async with factory() as session, session.begin():
        session.add(
            IngestSource(
                id="model-test-source",
                display_name="Model test source",
                source_kind="cms",
                policy={},
                status="healthy",
            )
        )
        session.add(
            IngestReceipt(
                source_event_id="model-feature-event-1",
                source_id="model-test-source",
                payload_hash="f" * 64,
                disposition="accepted",
            )
        )
        session.add(
            ScadaSample(
                id="model-feature-sample-1",
                observed_at=observed_at,
                source_event_id="model-feature-event-1",
                source_id="model-test-source",
                source_sequence=1,
                turbine_id="WT-023",
                variable="main_bearing_vibration_rms",
                value=7.2,
                unit="mm/s",
                quality="good",
            )
        )


@pytest.mark.asyncio
async def test_empty_model_registry_has_no_deployments_or_predictions(client: Any) -> None:
    response = await client.get("/api/v1/models")

    assert response.status_code == 200
    assert response.json() == {
        "count": 0,
        "models": [],
        "meta": {
            "artifact_count": 0,
            "active_deployment_count": 0,
            "real_inference_count": 0,
            "monitoring": {
                "prediction_count": 0,
                "succeeded_count": 0,
                "failed_count": 0,
                "success_rate": None,
                "p95_latency_ms": 0,
                "last_prediction_at": None,
            },
        },
    }


@pytest.mark.asyncio
async def test_model_artifact_upload_presign_is_scoped_and_idempotent(client: Any) -> None:
    headers = {
        **_manager_headers(),
        "Idempotency-Key": "model-upload-presign-001",
    }
    payload = {
        "model_id": "PRED-RUL-001",
        "file_name": "package.onnx",
        "content_type": "application/onnx",
        "artifact_sha256": "a" * 64,
    }

    first = await client.post(
        "/api/v1/models/uploads/presign",
        headers=headers,
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert first.headers["Idempotency-Replayed"] == "false"
    body = first.json()
    assert body["model_id"] == "PRED-RUL-001"
    assert body["artifact_uri"].startswith("minio://windops-model-artifacts/models/PRED-RUL-001/")
    assert body["upload_url"].startswith("memory://upload/")
    assert body["required_headers"] == {"content-type": "application/onnx"}

    replay = await client.post(
        "/api/v1/models/uploads/presign",
        headers=headers,
        json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == body


async def _register_and_activate(
    client: Any,
    app: FastAPI,
    *,
    model_id: str = "PRED-RUL-001",
    version: str = "1.0.0",
) -> str:
    package = f"verified model package {version}".encode()
    digest = hashlib.sha256(package).hexdigest()
    uri = f"minio://windops-model-artifacts/models/{model_id}/package.onnx"
    verifier = app.state.artifact_verifier
    assert isinstance(verifier, InMemoryArtifactVerifier)
    assert verifier.register_object(uri, package, "application/onnx") == digest
    registered = await client.post(
        "/api/v1/models",
        headers=_manager_headers(),
        json={
            "model_id": model_id,
            "name": "Main bearing RUL model",
            "version": version,
            "kind": "predictive",
            "description": "Externally hosted predictive inference package",
            "artifact_uri": uri,
            "artifact_sha256": digest,
            "content_type": "application/onnx",
            "input_schema": INPUT_SCHEMA,
            "output_schema": OUTPUT_SCHEMA,
            "metrics": {"validation_auc": 0.91, "validation_set": "holdout-2026q2"},
        },
    )
    assert registered.status_code == 201, registered.text
    staged = await client.post(
        f"/api/v1/models/{model_id}/deployments",
        headers=_manager_headers(),
        json={
            "target_id": "predictive-primary",
            "stage": "production",
            "evaluation_gate": {"approved_ticket": "MLOPS-1042"},
        },
    )
    assert staged.status_code == 201, staged.text
    deployment_id = staged.json()["deployment_id"]
    activated = await client.post(
        f"/api/v1/models/deployments/{deployment_id}/activate",
        headers=_manager_headers(),
        json={"traffic_percent": 100, "reason": "passed offline validation gate"},
    )
    assert activated.status_code == 200, activated.text
    return str(deployment_id)


@pytest.mark.asyncio
async def test_verified_artifact_deployment_inference_and_monitoring(
    client: Any, app: FastAPI
) -> None:
    app.state.settings.model_inference_targets["predictive-primary"] = ModelInferenceTarget(
        endpoint_url="http://inference.test/v1/predict",
        api_token=SecretStr("test-model-token"),
    )
    fake = FakeInferenceClient()
    app.state.model_inference_client = fake
    await _seed_good_scada(app)
    deployment_id = await _register_and_activate(client, app)

    first = await client.post(
        "/api/v1/predictive-assessments/run",
        headers=_manager_headers(),
        json={"turbine_ids": ["WT-023"]},
    )
    assert first.status_code == 200, first.text
    prediction = first.json()["predictions"][0]
    assert prediction["status"] == "succeeded"
    assert prediction["deployment_id"] == deployment_id
    assert prediction["latency_ms"] == 27
    assert fake.calls[0][0]["inputs"]["signals"]
    assert fake.calls[0][1].startswith(f"windops:{deployment_id}:WT-023:")

    replay = await client.post(
        "/api/v1/predictive-assessments/run",
        headers=_manager_headers(),
        json={"turbine_ids": ["WT-023"]},
    )
    assert replay.status_code == 200
    assert replay.json()["predictions"][0]["prediction_id"] == prediction["prediction_id"]
    assert len(fake.calls) == 1

    assessments = await client.get("/api/v1/predictive-assessments")
    assert assessments.status_code == 200
    row = assessments.json()["assessments"][0]
    assert row["turbine_id"] == "WT-023"
    assert row["failure_probability_30d"] == 37.5
    assert row["matrix_risk"] == "medium"
    assert row["model_id"] == "PRED-RUL-001"
    filtered_assessments = await client.get(
        "/api/v1/predictive-assessments",
        params={"turbine_id": "WT-023", "risk": "medium", "trend": "declining"},
    )
    assert filtered_assessments.status_code == 200
    assert filtered_assessments.json()["count"] == 1
    assert (
        filtered_assessments.json()["assessments"][0]["prediction_id"]
        == prediction["prediction_id"]
    )

    registry = await client.get("/api/v1/models")
    assert registry.status_code == 200
    meta = registry.json()["meta"]
    assert meta["artifact_count"] == 1
    assert meta["active_deployment_count"] == 1
    assert meta["real_inference_count"] == 1
    assert meta["monitoring"]["success_rate"] == 1.0
    assert meta["monitoring"]["p95_latency_ms"] == 27
    filtered_registry = await client.get(
        "/api/v1/models",
        params={"q": " PRED-RUL ", "kind": "predictive", "status": "active"},
    )
    assert filtered_registry.status_code == 200
    assert filtered_registry.json()["count"] == 1
    assert filtered_registry.json()["models"][0]["model_id"] == "PRED-RUL-001"


@pytest.mark.asyncio
async def test_concurrent_prediction_requests_use_one_inference_call(
    client: Any, app: FastAPI
) -> None:
    app.state.settings.model_inference_targets["predictive-primary"] = ModelInferenceTarget(
        endpoint_url="http://inference.test/v1/predict",
        api_token=SecretStr("test-model-token"),
    )
    fake = BlockingInferenceClient()
    app.state.model_inference_client = fake
    await _seed_good_scada(app)
    await _register_and_activate(client, app)

    first_task = asyncio.create_task(
        client.post(
            "/api/v1/predictive-assessments/run",
            headers=_manager_headers(),
            json={"turbine_ids": ["WT-023"]},
        )
    )
    await fake.started.wait()
    second_task = asyncio.create_task(
        client.post(
            "/api/v1/predictive-assessments/run",
            headers=_manager_headers(),
            json={"turbine_ids": ["WT-023"]},
        )
    )
    fake.release.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert (
        first.json()["predictions"][0]["prediction_id"]
        == second.json()["predictions"][0]["prediction_id"]
    )
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_prediction_cancellation_propagates_without_persisting_failure(
    client: Any, app: FastAPI
) -> None:
    app.state.settings.model_inference_targets["predictive-primary"] = ModelInferenceTarget(
        endpoint_url="http://inference.test/v1/predict",
        api_token=SecretStr("test-model-token"),
    )
    fake = CancellableInferenceClient()
    app.state.model_inference_client = fake
    await _seed_good_scada(app)
    await _register_and_activate(client, app)

    async with app.state.session_factory() as session:
        task = asyncio.create_task(
            run_predictive_inference(
                session,
                app.state.settings,
                fake,
                turbine_id="WT-023",
                subject="cancelled-model-operator",
            )
        )
        await fake.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await session.rollback()

    async with app.state.session_factory() as session:
        prediction = await session.scalar(
            select(ModelPrediction).where(ModelPrediction.turbine_id == "WT-023")
        )
        assert prediction is None


@pytest.mark.asyncio
async def test_predictive_batch_timeout_rolls_back_inflight_item(
    client: Any, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(model_registry, "PREDICTIVE_BATCH_TIMEOUT_SECONDS", 0.05)
    app.state.settings.model_inference_targets["predictive-primary"] = ModelInferenceTarget(
        endpoint_url="http://inference.test/v1/predict",
        api_token=SecretStr("test-model-token"),
    )
    fake = BlockingInferenceClient()
    app.state.model_inference_client = fake
    await _seed_good_scada(app)
    await _register_and_activate(client, app)

    result = await client.post(
        "/api/v1/predictive-assessments/run",
        headers=_manager_headers(),
        json={"turbine_ids": ["WT-023"]},
    )

    assert result.status_code == 207, result.text
    body = result.json()
    assert body["failed"] == 1
    assert body["predictions"] == [
        {
            "turbine_id": "WT-023",
            "status": "failed",
            "error_code": "BATCH_TIMEOUT",
        }
    ]
    async with app.state.session_factory() as session:
        prediction = await session.scalar(
            select(ModelPrediction).where(ModelPrediction.turbine_id == "WT-023")
        )
        assert prediction is None


@pytest.mark.asyncio
async def test_invalid_inference_output_fails_closed_and_is_audited(
    client: Any, app: FastAPI
) -> None:
    app.state.settings.model_inference_targets["predictive-primary"] = ModelInferenceTarget(
        endpoint_url="http://inference.test/v1/predict",
        api_token=SecretStr("test-model-token"),
    )
    app.state.model_inference_client = FakeInferenceClient(
        {
            "component": "main bearing",
            "failure_probability_30d": 140,
            "remaining_useful_life_days": 42,
            "anomaly_score": 0.8,
            "primary_finding": "invalid probability",
        }
    )
    await _seed_good_scada(app)
    await _register_and_activate(client, app)

    result = await client.post(
        "/api/v1/predictive-assessments/run",
        headers=_manager_headers(),
        json={"turbine_ids": ["WT-023"]},
    )
    assert result.status_code == 207
    prediction = result.json()["predictions"][0]
    assert prediction["status"] == "failed"
    assert prediction["output"] == {}
    assert prediction["error_code"] == "InvalidTransitionError"

    assessments = await client.get("/api/v1/predictive-assessments")
    assert assessments.json()["assessments"] == []
    registry = await client.get("/api/v1/models")
    assert registry.json()["meta"]["monitoring"]["failed_count"] == 1


@pytest.mark.asyncio
async def test_model_governance_write_roles_are_enforced(client: Any) -> None:
    denied = await client.post(
        "/api/v1/models/PRED-RUL-001/deployments",
        headers={
            "X-WindOps-Test-Principal": "viewer@example.com",
            "X-WindOps-Test-Role": "maintenance_reviewer",
            "Idempotency-Key": "model-runtime-denied-001",
        },
        json={"target_id": "predictive-primary"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"
