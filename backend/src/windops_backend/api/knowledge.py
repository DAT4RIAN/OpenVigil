from typing import Any, cast

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.api.deps import (
    Principal,
    _drain_or_dispatch_graph_projection_events,
    get_artifact_verifier,
    get_runtime_settings,
    get_session,
    require_read_access,
    require_roles,
)
from windops_backend.config import Settings
from windops_backend.errors import (
    InvalidTransitionError,
    NotFoundError,
)
from windops_backend.knowledge_parsing import parse_knowledge_content
from windops_backend.models import (
    KnowledgeCase,
    KnowledgeDocument,
)
from windops_backend.outbox import (
    mark_dispatched,
)
from windops_backend.schemas import (
    KnowledgeDocumentCreateRequest,
    KnowledgeDocumentUploadRequest,
)
from windops_backend.services.document_parse import configured_parse_identity
from windops_backend.services.idempotency import (
    execute_idempotent_command,
    replace_idempotent_response,
)
from windops_backend.services.knowledge import (
    ALLOWED_KNOWLEDGE_CONTENT_TYPES,
    MAX_KNOWLEDGE_ARTIFACT_BYTES,
    create_knowledge_document,
    process_knowledge_document_index_event,
    serialize_knowledge_document,
)
from windops_backend.services.knowledge_access import (
    knowledge_case_scope_clause,
    knowledge_document_query,
    resolve_knowledge_document_scope,
)
from windops_backend.storage import ArtifactVerifier

router = APIRouter()


@router.get("/knowledge/parser-capabilities", tags=["knowledge"])
async def knowledge_parser_capabilities(
    settings: Settings = Depends(get_runtime_settings),
    principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    del principal
    configured = bool(
        settings.document_parser_enabled
        and settings.document_parser_models_path is not None
        and settings.document_parser_model_manifest_sha256
        and settings.document_parser_python
    )
    return {
        "native": True,
        "docling_pdf_configured": configured,
        "configuration_status": "configured" if configured else "unconfigured",
        "max_pdf_pages": 200,
        "max_pdf_page_width_points": 2000,
        "max_pdf_page_height_points": 2000,
        "max_artifact_bytes": MAX_KNOWLEDGE_ARTIFACT_BYTES,
        "ocr_requires_numeric_review": True,
        "worker_health_verified": False,
    }


@router.get("/knowledge/documents", tags=["knowledge"])
async def knowledge_document_collection(
    query: str | None = Query(default=None, alias="q", max_length=240),
    document_type: str | None = None,
    ingestion_status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = knowledge_document_query(principal.graph_access_policy())
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            KnowledgeDocument.title.ilike(pattern) | KnowledgeDocument.document_type.ilike(pattern)
        )
    if document_type:
        statement = statement.where(KnowledgeDocument.document_type == document_type)
    if ingestion_status:
        statement = statement.where(KnowledgeDocument.ingestion_status == ingestion_status)
    if cursor:
        statement = statement.where(KnowledgeDocument.id > cursor)
    rows = list(
        (await session.scalars(statement.order_by(KnowledgeDocument.id).limit(limit + 1))).all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "count": len(page),
        "next_cursor": page[-1].id if has_more and page else None,
        "documents": [serialize_knowledge_document(document) for document in page],
    }


@router.post("/knowledge/documents/uploads/presign", tags=["knowledge"])
async def presign_knowledge_document_upload(
    payload: KnowledgeDocumentUploadRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        try:
            upload = await artifact_verifier.create_object_upload(
                bucket=settings.minio_knowledge_bucket,
                prefix=f"documents/{payload.document_id}",
                file_name=payload.file_name,
                content_type=payload.content_type,
                artifact_sha256=payload.artifact_sha256,
                allowed_content_types=ALLOWED_KNOWLEDGE_CONTENT_TYPES,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        return {"document_id": payload.document_id, **upload}

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="knowledge.document-upload.presign.v1",
        target=payload.document_id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_200_OK,
        operation=operation,
    )
    await session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.post(
    "/knowledge/documents",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["knowledge"],
)
async def ingest_knowledge_document(
    payload: KnowledgeDocumentCreateRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    principal: Principal = Depends(require_roles("operations_manager")),
) -> dict[str, Any]:
    event_ids: list[str] = []
    # Current scope is required even when the command receipt is replayed.
    scope = await resolve_knowledge_document_scope(
        session,
        document_id=payload.document_id,
        policy=principal.graph_access_policy(),
        tenant_id=payload.tenant_id,
        wind_farm_id=payload.wind_farm_id,
        turbine_id=payload.turbine_id,
        data_scope=payload.data_scope,
    )

    async def operation() -> dict[str, Any]:
        try:
            content, stored_content_type = await artifact_verifier.read_verified_object(
                payload.artifact_uri,
                payload.artifact_sha256,
                bucket=settings.minio_knowledge_bucket,
                prefix=f"documents/{payload.document_id}",
                allowed_content_types=ALLOWED_KNOWLEDGE_CONTENT_TYPES,
                max_bytes=MAX_KNOWLEDGE_ARTIFACT_BYTES,
            )
            if stored_content_type != payload.content_type:
                raise ValueError("stored knowledge object content type does not match the command")
            parse_identity = (
                await configured_parse_identity(
                    settings,
                    source_sha256=payload.artifact_sha256,
                    document_version=payload.document_version,
                )
                if payload.parser == "docling"
                else None
            )
            parsed = (
                await parse_knowledge_content(content, stored_content_type)
                if parse_identity is None
                else None
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        document, document_replayed, event_id = await create_knowledge_document(
            session,
            payload,
            extracted_text=parsed.body if parsed else "",
            content_size_bytes=len(content),
            subject=principal.subject,
            scope=scope,
            parsed=parsed,
            parse_identity=parse_identity,
        )
        if event_id is not None:
            event_ids.append(event_id)
        return {**serialize_knowledge_document(document), "replayed": document_replayed}

    result, replayed = await execute_idempotent_command(
        session,
        subject=principal.subject,
        command_type="knowledge.document.ingest.v1",
        target=payload.document_id,
        idempotency_key=idempotency_key,
        # Native v1 receipts predate the parser field. Preserve their exact
        # canonical payload; explicit Docling remains a different command input.
        payload=payload.model_dump(exclude={"parser"}) if payload.parser == "native" else payload,
        status_code=status.HTTP_202_ACCEPTED,
        operation=operation,
    )
    await session.commit()
    if payload.parser == "docling":
        if event_ids and not settings.outbox_inline_drain:
            from windops_backend.workers import dispatch_document_parse_event_ids

            dispatch_document_parse_event_ids(event_ids)
            await mark_dispatched(
                cast(async_sessionmaker[AsyncSession], request.app.state.session_factory), event_ids
            )
        response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
        return result
    if event_ids:
        factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
        if settings.outbox_inline_drain:
            await process_knowledge_document_index_event(factory, settings, event_ids[0])
            await _drain_or_dispatch_graph_projection_events(request, settings)
        else:
            from windops_backend.workers import dispatch_knowledge_document_event_ids

            dispatch_knowledge_document_event_ids(event_ids)
            await mark_dispatched(factory, event_ids)
        async with factory() as refresh_session:
            refreshed = await refresh_session.get(KnowledgeDocument, payload.document_id)
            if refreshed is not None:
                result = {**serialize_knowledge_document(refreshed), "replayed": False}
            await replace_idempotent_response(
                refresh_session,
                subject=principal.subject,
                command_type="knowledge.document.ingest.v1",
                target=payload.document_id,
                idempotency_key=idempotency_key,
                response_body=result,
            )
            await refresh_session.commit()
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@router.get("/knowledge/documents/{document_id}", tags=["knowledge"])
async def knowledge_document_detail(
    document_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    document = await session.scalar(
        knowledge_document_query(principal.graph_access_policy()).where(
            KnowledgeDocument.id == document_id
        )
    )
    if document is None:
        raise NotFoundError(f"knowledge document {document_id} was not found")
    return {
        **serialize_knowledge_document(document),
        "body": document.body,
        "source_storage": "database",
    }


@router.get("/knowledge/cases", tags=["knowledge"])
async def knowledge_cases(
    mission_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    statement = (
        select(KnowledgeCase)
        .where(knowledge_case_scope_clause(principal.graph_access_policy()))
        .order_by(desc(KnowledgeCase.created_at))
    )
    if mission_id:
        statement = statement.where(KnowledgeCase.mission_id == mission_id)
    cases = (await session.scalars(statement)).all()
    return {
        "count": len(cases),
        "cases": [
            {
                "case_id": case.id,
                "mission_id": case.mission_id,
                "work_order_id": case.work_order_id,
                "turbine_id": case.turbine_id,
                "title": case.title,
                "diagnosis": case.diagnosis,
                "resolution": case.resolution,
                "created_at": case.created_at,
            }
            for case in cases
        ],
    }
