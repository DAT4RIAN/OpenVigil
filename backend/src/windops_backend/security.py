from __future__ import annotations

import hashlib
import time
from collections import deque

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

RATE_LIMIT_SCRIPT = """
local principal = redis.call('INCR', KEYS[1])
if principal == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local client = redis.call('INCR', KEYS[2])
if client == 1 then
  redis.call('EXPIRE', KEYS[2], ARGV[1])
end
return {principal, client}
"""


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                await self._reject(scope, receive, send, "Content-Length must be an integer")
                return
            if declared_length < 0 or declared_length > self.max_bytes:
                await self._reject(scope, receive, send, self._limit_message())
                return

        received = 0
        buffered: deque[Message] = deque()
        chunk_count = 0
        while True:
            message = await receive()
            if message["type"] == "http.request":
                chunk_count += 1
                received += len(message.get("body", b""))
                if received > self.max_bytes or chunk_count > 2048:
                    await self._reject(scope, receive, send, self._limit_message())
                    return
                buffered.append(message)
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                buffered.append(message)
                break

        async def replay_receive() -> Message:
            if buffered:
                return buffered.popleft()
            return await receive()

        await self.app(scope, replay_receive, send)

    def _limit_message(self) -> str:
        return f"Request bodies are limited to {self.max_bytes} bytes"

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        message: str,
    ) -> None:
        del receive
        response = JSONResponse(
            status_code=413,
            content={"error": {"code": "REQUEST_TOO_LARGE", "message": message}},
        )
        await response(scope, _empty_receive, send)


async def _empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


class ApiSecurityHeadersMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        production: bool,
        release_id: str,
        release_commit_sha: str,
        release_image_digest: str,
    ) -> None:
        self.app = app
        self.production = production
        self.release_id = release_id
        self.release_commit_sha = release_commit_sha
        self.release_image_digest = release_image_digest

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def security_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}
                required: dict[bytes, bytes] = {
                    b"cache-control": b"no-store",
                    b"cross-origin-resource-policy": b"same-site",
                    b"referrer-policy": b"no-referrer",
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                }
                if self.production and scope.get("scheme") == "https":
                    required[b"strict-transport-security"] = (
                        b"max-age=63072000; includeSubDomains; preload"
                    )
                if self.production:
                    required.update(
                        {
                            b"x-windops-release-id": self.release_id.encode("ascii"),
                            b"x-windops-commit-sha": self.release_commit_sha.encode("ascii"),
                            b"x-windops-image-digest": self.release_image_digest.encode("ascii"),
                        }
                    )
                headers.extend(
                    (name, value) for name, value in required.items() if name not in existing
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, security_send)


class RedisRateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool,
        requests_per_minute: int,
        client_requests_per_minute: int,
    ) -> None:
        self.app = app
        self.enabled = enabled
        self.requests_per_minute = requests_per_minute
        self.client_requests_per_minute = client_requests_per_minute

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", ""))
        if (
            not self.enabled
            or scope["type"] != "http"
            or path == "/metrics"
            or path.endswith("/healthz")
            or path.endswith("/readyz")
        ):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        client = scope.get("client")
        client_identity = str(client[0]) if client else "unknown"
        principal_identity = (
            headers.get("x-windops-user-id") or headers.get("authorization") or client_identity
        )
        principal_digest = hashlib.sha256(principal_identity.encode()).hexdigest()
        client_digest = hashlib.sha256(client_identity.encode()).hexdigest()
        minute_bucket = int(time.time() // 60)
        principal_key = f"windops:rate:v1:principal:{minute_bucket}:{principal_digest}"
        client_key = f"windops:rate:v1:client:{minute_bucket}:{client_digest}"
        redis_client = scope["app"].state.redis_client
        try:
            counts = await redis_client.eval(
                RATE_LIMIT_SCRIPT,
                2,
                principal_key,
                client_key,
                60,
            )
            principal_count, client_count = (int(counts[0]), int(counts[1]))
        except Exception:
            await _json_error_response(
                scope,
                receive,
                send,
                status_code=503,
                code="RATE_LIMIT_UNAVAILABLE",
                message="Request admission control is unavailable",
            )
            return
        if (
            principal_count > self.requests_per_minute
            or client_count > self.client_requests_per_minute
        ):
            await _json_error_response(
                scope,
                receive,
                send,
                status_code=429,
                code="RATE_LIMITED",
                message="Request rate limit exceeded",
                headers={"Retry-After": "60"},
            )
            return
        await self.app(scope, receive, send)


async def _json_error_response(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> None:
    response = JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )
    await response(scope, receive, send)
