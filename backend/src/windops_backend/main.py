from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from minio import Minio
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from starlette.middleware.trustedhost import TrustedHostMiddleware

from windops_backend.api import router
from windops_backend.config import Settings, get_settings
from windops_backend.db import bootstrap_schema, create_engine, create_session_factory
from windops_backend.errors import DomainError
from windops_backend.identity import DelegatedIdentityAuthenticator
from windops_backend.knowledge_graph.api import router as knowledge_graph_router
from windops_backend.knowledge_graph.factory import create_knowledge_graph_store
from windops_backend.knowledge_graph.projection import ProjectionLimits
from windops_backend.knowledge_graph.service import KnowledgeGraphService
from windops_backend.observability import (
    RequestMetricsMiddleware,
    configure_otel,
    create_observability_runtime,
    metrics_token_matches,
    refresh_business_metrics,
)
from windops_backend.read_audit import DatabaseReadAuditSink, RedisReadAuditSink
from windops_backend.security import (
    ApiSecurityHeadersMiddleware,
    RedisRateLimitMiddleware,
    RequestBodyLimitMiddleware,
)
from windops_backend.services.ingest import ensure_ingest_source
from windops_backend.services.models import HttpModelInferenceClient
from windops_backend.services.platform_governance import (
    remediate_ingest_source_credentials,
    remediate_platform_configuration_history,
)
from windops_backend.services.seed import seed_agent_catalog, seed_wt023_demo
from windops_backend.storage import InMemoryArtifactVerifier, MinioArtifactVerifier


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(runtime_settings)
        session_factory = create_session_factory(engine)
        app.state.settings = runtime_settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        graph_store = create_knowledge_graph_store(runtime_settings)
        app.state.knowledge_graph_store = graph_store
        app.state.identity_authenticator = (
            DelegatedIdentityAuthenticator(
                secrets=tuple(
                    secret
                    for secret in (
                        runtime_settings.gateway_delegation_secret.get_secret_value(),
                        runtime_settings.gateway_delegation_previous_secret.get_secret_value(),
                    )
                    if secret
                ),
                issuer=runtime_settings.gateway_delegation_issuer,
                audience=runtime_settings.gateway_delegation_audience,
                role_mappings=runtime_settings.identity_role_mappings,
                clock_skew_seconds=runtime_settings.delegation_clock_skew_seconds,
            )
            if runtime_settings.auth_mode == "sites_delegation"
            else None
        )
        app.state.model_inference_client = HttpModelInferenceClient()
        app.state.redis_client = None
        app.state.minio_client = None
        try:
            if runtime_settings.environment.value == "test":
                app.state.artifact_verifier = InMemoryArtifactVerifier()
                app.state.read_audit_sink = DatabaseReadAuditSink(session_factory)
            else:
                public_minio = urlparse(runtime_settings.minio_public_base)
                internal_minio = Minio(
                    runtime_settings.minio_endpoint,
                    access_key=runtime_settings.minio_access_key,
                    secret_key=runtime_settings.minio_secret_key.get_secret_value(),
                    secure=runtime_settings.minio_secure,
                )
                app.state.minio_client = internal_minio
                app.state.redis_client = Redis.from_url(
                    runtime_settings.redis_url,
                    socket_connect_timeout=3,
                    socket_timeout=3,
                )
                app.state.read_audit_sink = RedisReadAuditSink(
                    app.state.redis_client, runtime_settings
                )
                app.state.artifact_verifier = MinioArtifactVerifier(
                    internal_minio,
                    runtime_settings.minio_field_evidence_bucket,
                    Minio(
                        public_minio.netloc,
                        access_key=runtime_settings.minio_access_key,
                        secret_key=runtime_settings.minio_secret_key.get_secret_value(),
                        secure=public_minio.scheme == "https",
                    ),
                )
            await bootstrap_schema(engine, runtime_settings)
            async with session_factory() as session, session.begin():
                await remediate_platform_configuration_history(session)
                await remediate_ingest_source_credentials(session)
            # Development/test startup loads the versioned catalog for DX only.
            # Production loads it exclusively through the authenticated
            # windops-reference-import CLI (see services/seed.py).
            if runtime_settings.environment.value != "production":
                async with session_factory() as session, session.begin():
                    await seed_agent_catalog(session)
            if runtime_settings.telemetry_source_policies:
                async with session_factory() as session, session.begin():
                    for source_id, policy in runtime_settings.telemetry_source_policies.items():
                        await ensure_ingest_source(session, source_id, policy)
            if runtime_settings.demo_seed:
                async with session_factory() as session:
                    await seed_wt023_demo(session)
            if runtime_settings.demo_seed or runtime_settings.knowledge_graph_rebuild_on_startup:
                async with session_factory() as session:
                    await KnowledgeGraphService(
                        graph_store,
                        limits=ProjectionLimits.from_settings(runtime_settings),
                    ).rebuild(session)
            yield
        finally:
            if app.state.redis_client is not None:
                await app.state.redis_client.aclose()
            await graph_store.close()
            await engine.dispose()
            app.state.observability.shutdown()

    app = FastAPI(
        title="OpenVigil Backend",
        version="0.1.0",
        description=(
            "Auditable wind-operations telemetry, multi-agent review, human approval, "
            "and field-work API"
        ),
        lifespan=lifespan,
        docs_url="/docs" if runtime_settings.docs_enabled else None,
        redoc_url="/redoc" if runtime_settings.docs_enabled else None,
        openapi_url="/openapi.json" if runtime_settings.docs_enabled else None,
    )
    app.state.observability = create_observability_runtime(runtime_settings)
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=runtime_settings.max_request_body_bytes,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=runtime_settings.trusted_hosts,
    )
    app.add_middleware(
        RedisRateLimitMiddleware,
        enabled=runtime_settings.rate_limit_enabled,
        requests_per_minute=runtime_settings.rate_limit_requests_per_minute,
        client_requests_per_minute=runtime_settings.rate_limit_client_requests_per_minute,
    )
    app.add_middleware(
        ApiSecurityHeadersMiddleware,
        production=runtime_settings.environment.value == "production",
        release_id=runtime_settings.release_id,
        release_commit_sha=runtime_settings.release_commit_sha,
        release_image_digest=runtime_settings.release_image_digest,
    )
    app.add_middleware(RequestMetricsMiddleware, runtime=app.state.observability)

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        del request
        detail: dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
        code = str(detail.get("code", "HTTP_ERROR"))
        message = str(detail.get("message", "Request rejected"))
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": message}},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        details = [
            {
                "location": ".".join(str(part) for part in error.get("loc", ())),
                "message": str(error.get("msg", "Invalid value")),
                "type": str(error.get("type", "value_error")),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Request validation failed",
                    "details": details,
                }
            },
        )

    def require_metrics_token(authorization: str | None) -> None:
        if not metrics_token_matches(runtime_settings, authorization):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "UNAUTHENTICATED", "message": "Metrics authentication required"},
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/metrics", include_in_schema=False)
    async def metrics(authorization: str | None = Header(default=None)) -> Response:
        require_metrics_token(authorization)
        async with app.state.session_factory() as session:
            await refresh_business_metrics(session, app.state.observability)
        return Response(
            content=generate_latest(app.state.observability.registry),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )

    @app.get("/metrics/slo", tags=["system"])
    async def service_level_objectives(
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_metrics_token(authorization)
        return {
            "http_availability": runtime_settings.slo_http_availability_target,
            "http_p95_latency_seconds": runtime_settings.slo_http_p95_latency_seconds,
            "agent_success": runtime_settings.slo_agent_success_target,
            "telemetry_freshness_seconds": runtime_settings.slo_telemetry_freshness_seconds,
            "source": "runtime-validated-config",
        }

    app.include_router(router, prefix=runtime_settings.api_prefix)
    app.include_router(knowledge_graph_router, prefix=runtime_settings.api_prefix)
    configure_otel(app, runtime_settings)
    return app


app = create_app()


def run() -> Any:
    return uvicorn.run(
        "windops_backend.main:app",
        host=get_settings().bind_host,
        port=8000,
        reload=False,
    )
