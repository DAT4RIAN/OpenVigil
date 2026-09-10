from collections.abc import AsyncIterator

import httpx
import pytest

from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.main import create_app


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def eval(
        self,
        script: str,
        key_count: int,
        principal_key: str,
        client_key: str,
        ttl: int,
    ) -> list[int]:
        assert "INCR" in script
        assert key_count == 2
        assert principal_key.startswith("windops:rate:v1:principal:")
        assert client_key.startswith("windops:rate:v1:client:")
        assert ttl == 60
        for key in (principal_key, client_key):
            self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[principal_key], self.counts[client_key]]

    async def aclose(self) -> None:
        return None


class FailingRedis(FakeRedis):
    async def eval(
        self,
        script: str,
        key_count: int,
        principal_key: str,
        client_key: str,
        ttl: int,
    ) -> list[int]:
        del script, key_count, principal_key, client_key, ttl
        raise ConnectionError("Redis unavailable")


async def _client(
    redis_client: FakeRedis | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        environment=Environment.TEST,
        database_url="sqlite+aiosqlite:///:memory:",
        schema_bootstrap=True,
        knowledge_graph_backend="memory",
        test_auth_bypass_enabled=True,
        rate_limit_enabled=True,
        rate_limit_requests_per_minute=10,
        rate_limit_client_requests_per_minute=100,
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        application.state.redis_client = redis_client or FakeRedis()
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={
                "X-WindOps-Test-Principal": "rate-limit-test",
                "X-WindOps-Test-Role": "test_system",
            },
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_redis_rate_limit_is_atomic_and_probes_are_exempt() -> None:
    async for client in _client():
        for _ in range(10):
            response = await client.get("/api/v1/turbines")
            assert response.status_code == 200
        limited = await client.get("/api/v1/turbines")
        assert limited.status_code == 429
        assert limited.headers["retry-after"] == "60"
        assert limited.json() == {
            "error": {"code": "RATE_LIMITED", "message": "Request rate limit exceeded"}
        }

        health = await client.get("/api/v1/healthz")
        ready = await client.get("/api/v1/readyz")
        assert health.status_code == 200
        assert ready.status_code == 200


@pytest.mark.asyncio
async def test_client_limit_is_stable_across_rotating_delegated_tokens() -> None:
    async for client in _client():
        for index in range(100):
            response = await client.get(
                "/api/v1/turbines",
                headers={
                    "X-WindOps-User-Id": f"sites-user-{index}",
                    "Authorization": f"Bearer delegated-token-{index}",
                },
            )
            assert response.status_code == 200

        limited = await client.get(
            "/api/v1/turbines",
            headers={
                "X-WindOps-User-Id": "sites-user-100",
                "Authorization": "Bearer delegated-token-100",
            },
        )
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_rate_limit_fails_closed_when_redis_is_unavailable() -> None:
    async for client in _client(FailingRedis()):
        response = await client.get("/api/v1/turbines")
        assert response.status_code == 503
        assert response.json() == {
            "error": {
                "code": "RATE_LIMIT_UNAVAILABLE",
                "message": "Request admission control is unavailable",
            }
        }
