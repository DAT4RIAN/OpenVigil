"""A fenced document parse job backed by the existing document and Outbox ledger."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.config import Settings
from windops_backend.document_parse_identity import DOCUMENT_PARSER_VERSIONS, parser_code_identity
from windops_backend.document_parse_process import DocumentParseFailure, parse_document_subprocess
from windops_backend.document_parse_result_identity import (
    DOCUMENT_RESULT_HASH_CONTRACT,
    document_parse_result_hash,
)
from windops_backend.knowledge_parsing import ParsedKnowledge, ParsedPassage
from windops_backend.model_base import utcnow
from windops_backend.models import KnowledgeDocument
from windops_backend.outbox import OutboxLeaseLostError, assert_current_claim, claim_event
from windops_backend.services.events import append_domain_event
from windops_backend.services.knowledge_contracts import (
    ALLOWED_KNOWLEDGE_CONTENT_TYPES,
    KNOWLEDGE_DOCUMENT_INDEX_REQUESTED,
    KNOWLEDGE_DOCUMENT_PARSE_REQUESTED,
    MAX_KNOWLEDGE_ARTIFACT_BYTES,
)
from windops_backend.services.knowledge_passages import add_passages
from windops_backend.storage import ArtifactVerifier, OutboxEvent

PARSE_STATE_KEY = "_openvigil_document_parse"
MAX_PARSE_ATTEMPTS = 3


class DocumentParserIdentityMismatch(RuntimeError):
    pass


async def configured_parse_identity(
    settings: Settings, *, source_sha256: str, document_version: str
) -> dict[str, Any]:
    if (
        not settings.document_parser_enabled
        or settings.document_parser_models_path is None
        or not settings.document_parser_model_manifest_sha256
        or not settings.document_parser_python
    ):
        raise ValueError("the isolated PDF parser is not configured")
    return {
        "method": "docling_pdf_v1",
        "source_sha256": source_sha256.lower(),
        "document_version": document_version,
        "model_manifest_sha256": settings.document_parser_model_manifest_sha256,
        "execution_code_sha256": await asyncio.to_thread(parser_code_identity),
        "library_versions": dict(DOCUMENT_PARSER_VERSIONS),
    }


def _set_state(document: KnowledgeDocument, **changes: Any) -> None:
    metadata = dict(document.metadata_ or {})
    metadata[PARSE_STATE_KEY] = {**metadata[PARSE_STATE_KEY], **changes}
    document.metadata_ = metadata
    document.updated_at = utcnow()


def _finish_event(event: OutboxEvent, *, error_code: str | None = None) -> None:
    event.status = "failed" if error_code else "succeeded"
    event.last_error = error_code
    event.claim_token = None
    event.lease_expires_at = None
    event.processed_at = utcnow()


async def recoverable_document_parse_events(
    factory: async_sessionmaker[AsyncSession], limit: int = 50
) -> list[tuple[str, str]]:
    async with factory() as session:
        rows = (
            await session.execute(
                select(OutboxEvent.id, OutboxEvent.event_type)
                .join(KnowledgeDocument, KnowledgeDocument.id == OutboxEvent.aggregate_id)
                .where(
                    OutboxEvent.event_type == KNOWLEDGE_DOCUMENT_PARSE_REQUESTED,
                    KnowledgeDocument.ingestion_status.in_(("pending_parse", "parsing")),
                    (OutboxEvent.status == "failed")
                    | (
                        (OutboxEvent.status == "processing")
                        & (OutboxEvent.lease_expires_at <= utcnow())
                    ),
                )
                .order_by(OutboxEvent.created_at)
                .limit(limit)
            )
        ).all()
        return [(str(identity), str(event_type)) for identity, event_type in rows]


async def _verified_pdf(
    verifier: ArtifactVerifier, settings: Settings, snapshot: dict[str, Any]
) -> bytes:
    content, content_type = await verifier.read_verified_object(
        snapshot["artifact_uri"],
        snapshot["artifact_sha256"],
        bucket=settings.minio_knowledge_bucket,
        prefix=f"documents/{snapshot['document_id']}",
        allowed_content_types=ALLOWED_KNOWLEDGE_CONTENT_TYPES,
        max_bytes=MAX_KNOWLEDGE_ARTIFACT_BYTES,
    )
    if content_type != "application/pdf" or len(content) != snapshot["content_size_bytes"]:
        raise ValueError("document parse source no longer matches its registered PDF")
    return content


async def process_document_parse_event(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    verifier: ArtifactVerifier,
    event_id: str,
) -> bool:
    async with factory() as session, session.begin():
        event = await session.get(OutboxEvent, event_id)
        if event is None or event.event_type != KNOWLEDGE_DOCUMENT_PARSE_REQUESTED:
            return False
        if event.status == "failed":
            terminal_document = await session.get(KnowledgeDocument, event.aggregate_id)
            terminal_state = (
                (terminal_document.metadata_ or {}).get(PARSE_STATE_KEY, {})
                if (terminal_document is not None)
                else {}
            )
            if terminal_state.get("status") == "failed":
                return True
        event = await claim_event(session, event_id)
        if event is None:
            return False
        token = str(event.claim_token)
        document = await session.get(KnowledgeDocument, event.aggregate_id)
        if document is None:
            raise RuntimeError("document parse event references a missing document")
        state = (document.metadata_ or {}).get(PARSE_STATE_KEY)
        if not isinstance(state, dict) or state.get("event_id") != event.id:
            raise RuntimeError("document parse event does not match its server-owned job")
        if state.get("status") in {"parsed", "failed"}:
            _finish_event(event, error_code=state.get("error_code"))
            return True
        if event.attempts > MAX_PARSE_ATTEMPTS:
            document.ingestion_status = "parse_failed"
            _set_state(document, status="failed", error_code="DocumentParseAttemptsExhausted")
            _finish_event(event, error_code="DocumentParseAttemptsExhausted")
            append_domain_event(
                session,
                event_type="knowledge.document.parse.failed",
                aggregate_type="knowledge_document",
                aggregate_id=document.id,
                payload={"document_id": document.id, "error_code": event.last_error},
            )
            return True
        expected = deepcopy(event.payload.get("parse_identity"))
        document.ingestion_status = "parsing"
        _set_state(
            document, status="running", attempts=event.attempts, started_at=utcnow().isoformat()
        )
        snapshot: dict[str, Any] = {
            "document_id": document.id,
            "document_version": document.document_version,
            "artifact_uri": document.artifact_uri,
            "artifact_sha256": document.artifact_sha256,
            "content_size_bytes": document.content_size_bytes,
            "identity": deepcopy(state.get("identity")),
        }
        append_domain_event(
            session,
            event_type="knowledge.document.parse.started",
            aggregate_type="knowledge_document",
            aggregate_id=document.id,
            payload={"document_id": document.id, "attempt": event.attempts, "event_id": event.id},
        )
    try:
        current = await configured_parse_identity(
            settings,
            source_sha256=str(snapshot["artifact_sha256"]),
            document_version=snapshot["document_version"],
        )
        if expected != current or snapshot["identity"] != expected:
            raise DocumentParserIdentityMismatch("document parser changed after job registration")
        content = await _verified_pdf(verifier, settings, snapshot)
        if settings.document_parser_models_path is None:
            raise RuntimeError("document parser model directory is missing")
        result = await parse_document_subprocess(
            content,
            models_path=settings.document_parser_models_path,
            manifest_sha256=current["model_manifest_sha256"],
            python_executable=settings.document_parser_python,
            runtime_directory=settings.document_parser_runtime_directory,
        )
        if (
            result.source_sha256 != expected["source_sha256"]
            or result.model_manifest_sha256 != expected["model_manifest_sha256"]
            or result.execution_code_sha256 != expected["execution_code_sha256"]
            or result.library_versions != expected["library_versions"]
        ):
            raise DocumentParserIdentityMismatch(
                "document parser returned another execution identity"
            )
        # Recheck mutable object storage after a long conversion, before publishing text.
        await _verified_pdf(verifier, settings, snapshot)
        parsed = ParsedKnowledge(
            body=result.body,
            passages=tuple(ParsedPassage(**piece.model_dump()) for piece in result.passages),
            source_page_count=result.source_page_count,
        )
        async with factory() as session, session.begin():
            await assert_current_claim(session, event_id, token)
            document = await session.scalar(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.id == snapshot["document_id"])
                .with_for_update()
            )
            if (
                document is None
                or document.body
                or document.vectorized
                or document.document_version != snapshot["document_version"]
                or document.artifact_uri != snapshot["artifact_uri"]
                or document.artifact_sha256 != snapshot["artifact_sha256"]
                or (document.metadata_ or {}).get(PARSE_STATE_KEY, {}).get("identity") != expected
            ):
                raise DocumentParserIdentityMismatch("document changed before parse publication")
            document.body = parsed.body
            document.ingestion_status = "pending"
            result_sha = document_parse_result_hash(result.model_dump())
            _set_state(
                document,
                status="parsed",
                completed_at=utcnow().isoformat(),
                error_code=None,
                result_sha256=result_sha,
                result_hash_contract=DOCUMENT_RESULT_HASH_CONTRACT,
                observed_execution_code_sha256=result.execution_code_sha256,
                observed_library_versions=result.library_versions,
            )
            document.metadata_ = {
                **document.metadata_,
                "_openvigil_source_layout": {
                    "page_count": result.source_page_count,
                    "parser_version": result.passages[0].parser_version,
                    "native_passages": len(result.passages),
                    "unextracted_pages": sorted(
                        set(range(1, result.source_page_count + 1))
                        - {piece.page_number for piece in result.passages}
                    ),
                    "requires_numeric_review": True,
                },
            }
            add_passages(session, document, parsed, verified=True)
            session.add(
                OutboxEvent(
                    event_type=KNOWLEDGE_DOCUMENT_INDEX_REQUESTED,
                    aggregate_type="knowledge_document",
                    aggregate_id=document.id,
                    payload={"document_id": document.id},
                )
            )
            append_domain_event(
                session,
                event_type="knowledge.document.parsed",
                aggregate_type="knowledge_document",
                aggregate_id=document.id,
                payload={
                    "document_id": document.id,
                    "artifact_sha256": document.artifact_sha256,
                    "result_sha256": result_sha,
                    "page_count": result.source_page_count,
                    "passage_count": len(parsed.passages),
                    "requires_numeric_review": True,
                },
            )
            event = await session.get(OutboxEvent, event_id)
            if event is None:
                raise RuntimeError("document parse event disappeared during publication")
            _finish_event(event)
        return True
    except asyncio.CancelledError:
        raise
    except OutboxLeaseLostError:
        return False
    except Exception as exc:
        async with factory() as session, session.begin():
            try:
                await assert_current_claim(session, event_id, token)
            except OutboxLeaseLostError:
                return False
            document = await session.get(KnowledgeDocument, snapshot["document_id"])
            event = await session.get(OutboxEvent, event_id)
            if document is None or event is None:
                raise RuntimeError("document parse failure ledger is missing") from exc
            code = type(exc).__name__
            terminal = event.attempts >= MAX_PARSE_ATTEMPTS or isinstance(
                exc, DocumentParserIdentityMismatch
            )
            document.ingestion_status = "parse_failed" if terminal else "pending_parse"
            _set_state(
                document,
                status="failed" if terminal else "pending",
                error_code=code,
                parser_failure_type=getattr(exc, "failure_type", None),
                completed_at=utcnow().isoformat() if terminal else None,
            )
            _finish_event(event, error_code=code)
            append_domain_event(
                session,
                event_type="knowledge.document.parse.failed",
                aggregate_type="knowledge_document",
                aggregate_id=document.id,
                payload={
                    "document_id": document.id,
                    "attempt": event.attempts,
                    "error_code": code,
                    "terminal": terminal,
                },
            )
        if not terminal:
            raise DocumentParseFailure(code) from None
        return True
