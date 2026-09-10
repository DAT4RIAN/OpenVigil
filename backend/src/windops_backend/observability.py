from __future__ import annotations

import hmac
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Info
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from windops_backend.config import Settings
from windops_backend.enums import ExecutionStatus, MissionStatus
from windops_backend.models import AgentExecution, Mission, ScadaSample


@dataclass
class ObservabilityRuntime:
    registry: CollectorRegistry
    http_requests: Counter
    http_duration: Histogram
    delegated_write_security_events: Counter
    missions: Gauge
    agent_executions: Gauge
    telemetry_freshness: Gauge
    slo_targets: Gauge
    release: Info
    tracer_provider: TracerProvider | None = None
    httpx_instrumentor: HTTPXClientInstrumentor | None = None

    def shutdown(self) -> None:
        if self.httpx_instrumentor is not None:
            self.httpx_instrumentor.uninstrument()
        if self.tracer_provider is not None:
            self.tracer_provider.shutdown()


def create_observability_runtime(settings: Settings) -> ObservabilityRuntime:
    registry = CollectorRegistry(auto_describe=True)
    runtime = ObservabilityRuntime(
        registry=registry,
        http_requests=Counter(
            "windops_http_requests_total",
            "HTTP requests processed by the WindOps API.",
            ("method", "route", "status"),
            registry=registry,
        ),
        http_duration=Histogram(
            "windops_http_request_duration_seconds",
            "HTTP request duration by stable route template.",
            ("method", "route"),
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
            registry=registry,
        ),
        delegated_write_security_events=Counter(
            "windops_delegated_write_security_events_total",
            "Accepted, replayed, or store-failed delegated write assertions.",
            ("outcome",),
            registry=registry,
        ),
        missions=Gauge(
            "windops_missions",
            "Current durable Mission count by status.",
            ("status",),
            registry=registry,
        ),
        agent_executions=Gauge(
            "windops_agent_executions",
            "Durable agent execution count by status and evaluation window.",
            ("status", "window"),
            registry=registry,
        ),
        telemetry_freshness=Gauge(
            "windops_telemetry_freshness_seconds",
            "Age in seconds of the most recently received telemetry sample.",
            registry=registry,
        ),
        slo_targets=Gauge(
            "windops_slo_target",
            "Runtime-validated service-level objective target.",
            ("objective", "unit"),
            registry=registry,
        ),
        release=Info(
            "windops_release",
            "Immutable build identity reported by the running WindOps API.",
            registry=registry,
        ),
    )
    runtime.release.info(
        {
            "release_id": settings.release_id,
            "commit_sha": settings.release_commit_sha or "development",
            "image_digest": settings.release_image_digest or "development",
        }
    )
    runtime.slo_targets.labels(objective="http_availability", unit="ratio").set(
        settings.slo_http_availability_target
    )
    runtime.slo_targets.labels(objective="http_p95_latency", unit="seconds").set(
        settings.slo_http_p95_latency_seconds
    )
    runtime.slo_targets.labels(objective="agent_success", unit="ratio").set(
        settings.slo_agent_success_target
    )
    runtime.slo_targets.labels(objective="telemetry_freshness", unit="seconds").set(
        settings.slo_telemetry_freshness_seconds
    )
    return runtime


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, runtime: ObservabilityRuntime) -> None:
        super().__init__(app)
        self.runtime = runtime

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        request_id = _request_id(request.headers.get("X-Request-ID"))
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            route = request.scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            self.runtime.http_requests.labels(
                method=request.method,
                route=route_template,
                status=str(status_code),
            ).inc()
            self.runtime.http_duration.labels(
                method=request.method,
                route=route_template,
            ).observe(time.perf_counter() - started)
        response.headers["X-Request-ID"] = request_id
        span = trace.get_current_span()
        context = span.get_span_context()
        if context.is_valid:
            response.headers["Traceparent"] = (
                f"00-{context.trace_id:032x}-{context.span_id:016x}-"
                f"{'01' if context.trace_flags.sampled else '00'}"
            )
        return response


def _request_id(candidate: str | None) -> str:
    if (
        candidate
        and 1 <= len(candidate) <= 128
        and all(char.isalnum() or char in "-_." for char in candidate)
    ):
        return candidate
    return str(uuid4())


def metrics_token_matches(settings: Settings, authorization: str | None) -> bool:
    scheme, _, supplied = (authorization or "").partition(" ")
    expected = settings.metrics_bearer_token.get_secret_value()
    return scheme.lower() == "bearer" and bool(supplied) and hmac.compare_digest(supplied, expected)


async def refresh_business_metrics(
    session: AsyncSession,
    runtime: ObservabilityRuntime,
) -> None:
    mission_rows = (
        await session.execute(select(Mission.status, func.count()).group_by(Mission.status))
    ).all()
    mission_counts = {str(status): int(count) for status, count in mission_rows}
    for mission_status in MissionStatus:
        runtime.missions.labels(status=mission_status.value).set(
            mission_counts.get(mission_status.value, 0)
        )

    execution_windows = {
        "all": None,
        "30d": datetime.now(UTC) - timedelta(days=30),
    }
    for window, cutoff in execution_windows.items():
        statement = select(AgentExecution.status, func.count()).group_by(AgentExecution.status)
        if cutoff is not None:
            statement = statement.where(AgentExecution.started_at >= cutoff)
        execution_rows = (await session.execute(statement)).all()
        execution_counts = {str(status): int(count) for status, count in execution_rows}
        for execution_status in ExecutionStatus:
            runtime.agent_executions.labels(
                status=execution_status.value,
                window=window,
            ).set(execution_counts.get(execution_status.value, 0))

    latest_received = await session.scalar(select(func.max(ScadaSample.received_at)))
    if latest_received is None:
        runtime.telemetry_freshness.set(float("nan"))
    else:
        if latest_received.tzinfo is None:
            latest_received = latest_received.replace(tzinfo=UTC)
        runtime.telemetry_freshness.set(
            max(0.0, (datetime.now(UTC) - latest_received).total_seconds())
        )


def configure_otel(app: FastAPI, settings: Settings) -> None:
    runtime = app.state.observability
    if not settings.otel_enabled:
        return
    provider = TracerProvider(
        resource=Resource.create(
            {
                SERVICE_NAME: settings.otel_service_name,
                DEPLOYMENT_ENVIRONMENT: settings.environment.value,
                "service.version": settings.release_id,
                "vcs.ref.head.revision": settings.release_commit_sha or "development",
                "container.image.repo_digests": settings.release_image_digest or "development",
            }
        )
    )
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        headers={
            key: value.get_secret_value()
            for key, value in settings.otel_exporter_otlp_headers.items()
        },
        timeout=10,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="healthz,readyz,metrics",
        http_capture_headers_sanitize_fields=["authorization", "cookie", "set-cookie"],
        exclude_spans=["receive", "send"],
    )
    httpx_instrumentor = HTTPXClientInstrumentor()
    httpx_instrumentor.instrument(tracer_provider=provider)
    runtime.tracer_provider = provider
    runtime.httpx_instrumentor = httpx_instrumentor
