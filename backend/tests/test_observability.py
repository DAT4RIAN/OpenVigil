import httpx
import pytest
from fastapi import FastAPI


@pytest.mark.asyncio
async def test_metrics_are_machine_authenticated_and_use_stable_route_labels(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    anonymous = await client.get("/metrics", headers={"Authorization": ""})
    assert anonymous.status_code == 401
    assert anonymous.json() == {
        "error": {
            "code": "UNAUTHENTICATED",
            "message": "Metrics authentication required",
        }
    }

    await client.get("/api/v1/turbines/WT-023")
    token = app.state.settings.metrics_bearer_token.get_secret_value()
    response = await client.get(
        "/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "windops_http_requests_total" in response.text
    labels = [
        sample.labels
        for metric in app.state.observability.http_requests.collect()
        for sample in metric.samples
        if sample.name == "windops_http_requests_total"
    ]
    assert any(label.get("route") == "/turbines/{turbine_id}" for label in labels), labels
    assert 'route="/turbines/{turbine_id}"' in response.text
    assert "windops_missions" in response.text
    assert "windops_agent_executions" in response.text
    assert "windops_telemetry_freshness_seconds" in response.text
    assert "windops_release_info" in response.text
    assert 'release_id="development"' in response.text


@pytest.mark.asyncio
async def test_slo_targets_and_request_correlation_are_exposed(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    token = app.state.settings.metrics_bearer_token.get_secret_value()
    response = await client.get(
        "/metrics/slo",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Request-ID": "production-probe-001",
        },
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "production-probe-001"
    assert response.json() == {
        "http_availability": 0.999,
        "http_p95_latency_seconds": 2.0,
        "agent_success": 0.99,
        "telemetry_freshness_seconds": 120,
        "source": "runtime-validated-config",
    }
