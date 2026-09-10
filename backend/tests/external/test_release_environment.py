import asyncio
import hashlib
import io
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from windops_backend.agents.reasoning import LiteLLMReasoningProvider
from windops_backend.agents.tools import EMBEDDING_DIMENSIONS, LiteLLMEmbeddingProvider
from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.main import create_app
from windops_backend.models import ModelDeployment, Turbine
from windops_backend.schemas import PublicDiagnosis
from windops_backend.services.models import run_predictive_inference

pytestmark = [
    pytest.mark.external_release,
    pytest.mark.skipif(
        os.getenv("WINDOPS_RUN_EXTERNAL_RELEASE_TESTS") != "1",
        reason="requires WINDOPS_RUN_EXTERNAL_RELEASE_TESTS=1 and isolated production services",
    ),
]


@pytest.mark.asyncio
async def test_real_release_dependencies_and_providers() -> None:
    settings = Settings()
    assert settings.environment is Environment.PRODUCTION
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        base_url = f"https://{settings.trusted_hosts[0]}"
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            ready = await client.get(f"{settings.api_prefix}/readyz")
            assert ready.status_code == 200, ready.text
            assert ready.json()["release"] == {
                "release_id": settings.release_id,
                "commit_sha": settings.release_commit_sha,
                "image_digest": settings.release_image_digest,
            }
            assert ready.json()["dependencies"] == {
                "postgresql": "ready",
                "redis": "ready",
                "minio": "ready",
                "knowledge_graph": "neo4j",
            }
            metrics = await client.get(
                "/metrics",
                headers={
                    "Authorization": (f"Bearer {settings.metrics_bearer_token.get_secret_value()}")
                },
            )
            assert metrics.status_code == 200
            assert "windops_slo_target" in metrics.text

        payload = b"windops isolated release verification"
        digest = hashlib.sha256(payload).hexdigest()
        object_name = f"work-orders/release-verification/tasks/artifact-roundtrip/{uuid4()}.txt"
        minio_client = application.state.minio_client
        await asyncio.to_thread(
            minio_client.put_object,
            settings.minio_field_evidence_bucket,
            object_name,
            io.BytesIO(payload),
            len(payload),
            content_type="text/plain",
            metadata={"sha256": digest},
        )
        try:
            await application.state.artifact_verifier.verify(
                f"minio://{settings.minio_field_evidence_bucket}/{object_name}",
                digest,
                work_order_id="release-verification",
                task_id="artifact-roundtrip",
            )
        finally:
            await asyncio.to_thread(
                minio_client.remove_object,
                settings.minio_field_evidence_bucket,
                object_name,
            )

        embedding = await LiteLLMEmbeddingProvider(settings.embedding_model).embed(
            ["OpenVigil production release embedding verification"]
        )
        assert len(embedding) == 1
        assert len(embedding[0]) == EMBEDDING_DIMENSIONS

        reasoning = LiteLLMReasoningProvider(
            settings.litellm_model,
            timeout_seconds=settings.litellm_timeout_seconds,
            max_retries=settings.litellm_max_retries,
            minimum_diagnosis_confidence=settings.litellm_minimum_diagnosis_confidence,
        )
        diagnosis = await reasoning.generate(
            PublicDiagnosis,
            "Diagnose only the governed gearbox scope and cite the supplied evidence.",
            {
                "turbine_id": "RELEASE-VERIFICATION",
                "analysis_profile": {"component": "gearbox"},
                "evidence": [{"evidence_id": "EVD-RELEASE-VERIFICATION"}],
            },
        )
        assert diagnosis.component == "gearbox"
        assert diagnosis.evidence_refs == ["EVD-RELEASE-VERIFICATION"]

        async with application.state.session_factory() as session, session.begin():
            deployment = await session.scalar(
                select(ModelDeployment).where(
                    ModelDeployment.status == "active",
                    ModelDeployment.traffic_percent > 0,
                )
            )
            turbine_id = await session.scalar(select(Turbine.id).order_by(Turbine.id).limit(1))
            assert deployment is not None, "release environment has no active model deployment"
            assert turbine_id is not None, "release environment has no turbine master data"
            prediction = await run_predictive_inference(
                session,
                settings,
                application.state.model_inference_client,
                turbine_id=turbine_id,
                subject="release-verifier",
            )
            assert prediction.status == "succeeded", prediction.error_code
