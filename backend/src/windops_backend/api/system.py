import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.access_control import access_scope_audit
from windops_backend.api.deps import (
    Principal,
    get_runtime_settings,
    get_session,
    require_read_access,
)
from windops_backend.capabilities import capabilities_for_principal
from windops_backend.errors import (
    KnowledgeGraphUnavailableError,
)
from windops_backend.knowledge_graph.store import KnowledgeGraphStore
from windops_backend.services.events import (
    EventCursorCodec,
    latest_domain_event_sequence,
    read_domain_events,
    serialize_domain_event,
)
from windops_backend.services.platform_governance import (
    unresolved_platform_configuration_rotations,
)

router = APIRouter()


def _invalid_event_cursor(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "INVALID_EVENT_CURSOR", "message": message},
    )


def _request_event_cursor(
    *,
    after: int,
    cursor: str | None,
    last_event_id: str | None,
    principal: Principal,
    settings: Any,
) -> tuple[int, EventCursorCodec | None]:
    supplied = last_event_id.strip() if last_event_id and last_event_id.strip() else cursor
    policy = principal.graph_access_policy()
    if policy.unrestricted:
        if supplied is None:
            return after, None
        try:
            parsed = int(supplied)
        except ValueError as exc:
            raise _invalid_event_cursor("Last-Event-ID or cursor must be an integer") from exc
        if parsed < 0:
            raise _invalid_event_cursor("Event cursor cannot be negative")
        return max(after, parsed), None

    if after != 0:
        raise _invalid_event_cursor(
            "Scoped event streams require the opaque cursor parameter or Last-Event-ID"
        )
    codec = EventCursorCodec.from_secret(
        settings.gateway_delegation_secret.get_secret_value(),
        principal.subject
        + "\0"
        + json.dumps(
            access_scope_audit(policy),
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    if supplied is None:
        return 0, codec
    try:
        return codec.decode(supplied), codec
    except ValueError as exc:
        raise _invalid_event_cursor(str(exc)) from exc


def _public_event_cursor(sequence: int, codec: EventCursorCodec | None) -> str | int:
    return sequence if codec is None else codec.encode(sequence)


@router.get("/healthz", tags=["system"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/session", tags=["identity"])
async def current_session(
    principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    policy = principal.graph_access_policy()
    return {
        "subject": principal.subject,
        "email": principal.email,
        "roles": sorted(principal.roles),
        "capabilities": capabilities_for_principal(principal),
        "scope": {
            "tenant_count": len(policy.tenant_ids),
            "wind_farm_count": len(policy.wind_farm_ids),
            "turbine_count": len(policy.turbine_ids),
            "entity_count": len(policy.entity_ids),
            "allow_global": policy.allow_global or policy.unrestricted,
        },
    }


@router.get("/readyz", tags=["system"])
async def readyz(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = get_runtime_settings(request)
    await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=3)
    if (
        settings.environment.value == "production"
        and await unresolved_platform_configuration_rotations(session)
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CONFIGURATION_SECURITY_REMEDIATION_REQUIRED",
                "message": "Platform configuration credential rotation is incomplete",
            },
        )
    graph_store = cast(KnowledgeGraphStore, request.app.state.knowledge_graph_store)
    try:
        await asyncio.wait_for(graph_store.verify_connectivity(), timeout=3)
    except Exception as exc:
        raise KnowledgeGraphUnavailableError("knowledge graph connectivity check failed") from exc
    if settings.environment.value != "production":
        return {"status": "ready", "knowledge_graph": graph_store.backend_name}

    unavailable: list[str] = []
    redis_client = request.app.state.redis_client
    try:
        if not await asyncio.wait_for(redis_client.ping(), timeout=3):
            unavailable.append("redis")
    except Exception:
        unavailable.append("redis")

    minio_client = request.app.state.minio_client
    buckets = (
        settings.minio_field_evidence_bucket,
        settings.minio_knowledge_bucket,
        settings.minio_model_bucket,
        settings.minio_twin_bucket,
        settings.minio_care_bucket,
    )
    try:
        present = await asyncio.wait_for(
            asyncio.gather(
                *(asyncio.to_thread(minio_client.bucket_exists, bucket) for bucket in buckets)
            ),
            timeout=5,
        )
        if not all(present):
            unavailable.append("minio-buckets")
    except Exception:
        unavailable.append("minio")
    if unavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DEPENDENCY_UNAVAILABLE",
                "message": f"Required dependencies unavailable: {', '.join(unavailable)}",
            },
        )
    return {
        "status": "ready",
        "release": {
            "release_id": settings.release_id,
            "commit_sha": settings.release_commit_sha,
            "image_digest": settings.release_image_digest,
        },
        "dependencies": {
            "postgresql": "ready",
            "redis": "ready",
            "minio": "ready",
            "knowledge_graph": graph_store.backend_name,
        },
    }


@router.get("/events", tags=["events"])
async def domain_events(
    request: Request,
    after: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None, min_length=4, max_length=256),
    limit: int = Query(default=200, ge=1, le=1000),
    event_type: list[str] | None = Query(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    raw_cursor, codec = _request_event_cursor(
        after=after,
        cursor=cursor,
        last_event_id=last_event_id,
        principal=principal,
        settings=get_runtime_settings(request),
    )
    policy = principal.graph_access_policy()
    rows = await read_domain_events(
        session,
        after=raw_cursor,
        limit=limit,
        event_types=event_type,
        policy=policy,
    )
    event_cursors = [_public_event_cursor(row.sequence, codec) for row in rows]
    events = [
        serialize_domain_event(row, cursor=public_cursor)
        for row, public_cursor in zip(rows, event_cursors, strict=True)
    ]
    public_after = _public_event_cursor(raw_cursor, codec)
    return {
        "after": public_after,
        "next_cursor": event_cursors[-1] if event_cursors else public_after,
        "count": len(events),
        "events": events,
    }


@router.get("/events/stream", tags=["events"])
async def domain_event_stream(
    request: Request,
    after: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None, min_length=4, max_length=256),
    start: Literal["cursor", "latest"] = Query(default="cursor"),
    event_type: list[str] | None = Query(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    principal: Principal = Depends(require_read_access),
) -> StreamingResponse:
    settings = get_runtime_settings(request)
    raw_cursor, codec = _request_event_cursor(
        after=after,
        cursor=cursor,
        last_event_id=last_event_id,
        principal=principal,
        settings=settings,
    )
    policy = principal.graph_access_policy()
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with factory() as cursor_session:
        latest_cursor = await latest_domain_event_sequence(cursor_session, policy=policy)
    if (
        start == "latest" and raw_cursor == 0 and not last_event_id and cursor is None
    ) or raw_cursor > latest_cursor:
        raw_cursor = latest_cursor

    async def generate() -> AsyncIterator[bytes]:
        nonlocal raw_cursor
        loop = asyncio.get_running_loop()
        deadline = loop.time() + settings.event_stream_connection_seconds
        next_heartbeat = loop.time() + 10
        yield b"retry: 1000\n\n"
        public_cursor = _public_event_cursor(raw_cursor, codec)
        ready = json.dumps(
            {"next_cursor": public_cursor, "start": start},
            separators=(",", ":"),
        )
        yield f"id: {public_cursor}\nevent: stream.ready\ndata: {ready}\n\n".encode()
        while loop.time() < deadline and not await request.is_disconnected():
            async with factory() as event_session:
                rows = await read_domain_events(
                    event_session,
                    after=raw_cursor,
                    limit=200,
                    event_types=event_type,
                    policy=policy,
                )
            if rows:
                for row in rows:
                    raw_cursor = row.sequence
                    public_cursor = _public_event_cursor(raw_cursor, codec)
                    body = json.dumps(
                        serialize_domain_event(row, cursor=public_cursor),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        default=str,
                    )
                    yield (
                        f"id: {public_cursor}\nevent: {row.event_type}\ndata: {body}\n\n"
                    ).encode()
                continue
            if loop.time() >= next_heartbeat:
                heartbeat_cursor = _public_event_cursor(raw_cursor, codec)
                yield f": keep-alive cursor={heartbeat_cursor}\n\n".encode()
                next_heartbeat = loop.time() + 10
            await asyncio.sleep(settings.event_stream_poll_milliseconds / 1000)
        reconnect_cursor = _public_event_cursor(raw_cursor, codec)
        reconnect = json.dumps({"next_cursor": reconnect_cursor}, separators=(",", ":"))
        yield (f"id: {reconnect_cursor}\nevent: reconnect\ndata: {reconnect}\n\n").encode()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
