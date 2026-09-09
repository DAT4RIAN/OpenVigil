from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from minio import Minio

from windops_backend.api import router
from windops_backend.config import Settings, get_settings
from windops_backend.db import bootstrap_schema, create_engine, create_session_factory
from windops_backend.errors import DomainError
from windops_backend.services.seed import seed_wt023_demo
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
        if runtime_settings.environment.value == "test":
            app.state.artifact_verifier = InMemoryArtifactVerifier()
        else:
            app.state.artifact_verifier = MinioArtifactVerifier(
                Minio(
                    runtime_settings.minio_endpoint,
                    access_key=runtime_settings.minio_access_key,
                    secret_key=runtime_settings.minio_secret_key.get_secret_value(),
                    secure=runtime_settings.minio_secure,
                )
            )
        await bootstrap_schema(engine, runtime_settings)
        if runtime_settings.demo_seed:
            async with session_factory() as session:
                await seed_wt023_demo(session)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="WindOps Backend",
        version="0.1.0",
        description=(
            "Auditable WT-023 SCADA → multi-agent review → human approval → work-order API"
        ),
        lifespan=lifespan,
    )

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

    app.include_router(router, prefix=runtime_settings.api_prefix)
    return app


app = create_app()


def run() -> Any:
    return uvicorn.run("windops_backend.main:app", host="0.0.0.0", port=8000, reload=False)
