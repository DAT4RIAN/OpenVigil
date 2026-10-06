from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.api.deps import (
    Principal,
    get_artifact_verifier,
    get_runtime_settings,
    get_session,
    require_read_access,
)
from windops_backend.config import Settings
from windops_backend.errors import InvalidTransitionError, NotFoundError
from windops_backend.model_knowledge_passage import KnowledgePassage
from windops_backend.models import KnowledgeDocument
from windops_backend.services.knowledge import (
    ALLOWED_KNOWLEDGE_CONTENT_TYPES,
    MAX_KNOWLEDGE_ARTIFACT_BYTES,
)
from windops_backend.services.knowledge_access import knowledge_document_query
from windops_backend.services.knowledge_passages import serialize_passage
from windops_backend.storage import ArtifactVerifier

router = APIRouter()


async def _document(
    session: AsyncSession, principal: Principal, document_id: str
) -> KnowledgeDocument:
    document = await session.scalar(
        knowledge_document_query(principal.graph_access_policy()).where(
            KnowledgeDocument.id == document_id
        )
    )
    if document is None:
        raise NotFoundError("knowledge document was not found")
    return document


@router.get("/knowledge/documents/{document_id}/passages", tags=["knowledge"])
async def knowledge_passage_collection(
    document_id: str,
    cursor: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    document = await _document(session, principal, document_id)
    statement = select(KnowledgePassage).where(KnowledgePassage.document_id == document.id)
    if cursor is not None:
        statement = statement.where(KnowledgePassage.ordinal > cursor)
    rows = list(
        (await session.scalars(statement.order_by(KnowledgePassage.ordinal).limit(limit + 1))).all()
    )
    page = rows[:limit]
    return {
        "document_id": document.id,
        "document_version": document.document_version,
        "count": len(page),
        "next_cursor": page[-1].ordinal if len(rows) > limit and page else None,
        "passages": [serialize_passage(passage) for passage in page],
        "fixtureFallback": False,
    }


@router.get("/knowledge/passages/{passage_id}", tags=["knowledge"])
async def knowledge_passage_detail(
    passage_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    passage = await session.get(KnowledgePassage, passage_id)
    if passage is None:
        raise NotFoundError("knowledge passage was not found")
    document = await _document(session, principal, passage.document_id)
    return {**serialize_passage(passage), "title": document.title, "fixtureFallback": False}


@router.get("/knowledge/documents/{document_id}/source", tags=["knowledge"])
async def knowledge_document_source(
    document_id: str,
    passage_id: str | None = Query(default=None, max_length=64),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_read_access),
    settings: Settings = Depends(get_runtime_settings),
    artifact_verifier: ArtifactVerifier = Depends(get_artifact_verifier),
) -> dict[str, Any]:
    document = await _document(session, principal, document_id)
    passage = None
    if passage_id is not None:
        passage = await session.scalar(
            select(KnowledgePassage).where(
                KnowledgePassage.id == passage_id, KnowledgePassage.document_id == document.id
            )
        )
        if passage is None:
            raise NotFoundError("knowledge passage was not found in this document")
        if passage.document_version != document.document_version or (
            passage.source_sha256 is not None and passage.source_sha256 != document.artifact_sha256
        ):
            raise InvalidTransitionError(
                "passage does not match the immutable document source version"
            )
    if not document.artifact_uri or not document.artifact_sha256 or not document.content_type:
        raise InvalidTransitionError("historical document has no verified source artifact")
    try:
        # Recheck immutable source bytes before granting a short download URL.
        # A page locator is meaningful only for this exact file version.
        _, stored_type = await artifact_verifier.read_verified_object(
            document.artifact_uri,
            document.artifact_sha256,
            bucket=settings.minio_knowledge_bucket,
            prefix=f"documents/{document.id}",
            allowed_content_types=ALLOWED_KNOWLEDGE_CONTENT_TYPES,
            max_bytes=MAX_KNOWLEDGE_ARTIFACT_BYTES,
        )
        if stored_type != document.content_type:
            raise ValueError("stored source content type does not match the document")
        download = await artifact_verifier.create_object_download(
            document.artifact_uri,
            bucket=settings.minio_knowledge_bucket,
            prefix=f"documents/{document.id}",
            response_content_type=document.content_type,
        )
    except ValueError as exc:
        raise InvalidTransitionError(str(exc)) from exc
    return {
        "document_id": document.id,
        "document_version": document.document_version,
        "artifact_sha256": document.artifact_sha256,
        "content_type": document.content_type,
        "passage_id": passage.id if passage else None,
        "page_number": passage.page_number if passage else None,
        "native_locator": passage.native_locator if passage else None,
        **download,
        "fixtureFallback": False,
    }
