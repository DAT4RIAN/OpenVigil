"""State/lease tests inject a declared parser wire fixture, not OCR inference.

Actual Docling inference is validated separately using the isolated fixed runtime.
"""

import asyncio
import hashlib
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from test_knowledge_passages import ingest, pdf_with_second_page_text
from windops_backend.document_parse_contract import DocumentParseResult
from windops_backend.document_parse_identity import DOCUMENT_PARSER_VERSIONS, parser_code_identity
from windops_backend.document_parse_process import DocumentParseFailure
from windops_backend.model_base import utcnow
from windops_backend.model_knowledge_passage import KnowledgePassage
from windops_backend.models import CommandReceipt, KnowledgeDocument, Tenant
from windops_backend.schemas import KnowledgeDocumentCreateRequest
from windops_backend.services import document_parse
from windops_backend.services.document_parse import (
    PARSE_STATE_KEY,
    process_document_parse_event,
    recoverable_document_parse_events,
)
from windops_backend.services.idempotency import canonical_request_hash
from windops_backend.services.knowledge import process_knowledge_document_index_event
from windops_backend.services.knowledge_contracts import (
    KNOWLEDGE_DOCUMENT_INDEX_REQUESTED,
    KNOWLEDGE_DOCUMENT_PARSE_REQUESTED,
)
from windops_backend.storage import OutboxEvent


def enable_parser(app):
    settings = app.state.settings
    settings.document_parser_enabled = True
    settings.document_parser_models_path = Path("configured-test-only-models")
    settings.document_parser_model_manifest_sha256 = "a" * 64
    settings.document_parser_python = "configured-test-only-python"


def protocol_result(content):
    text = "Declared wire fixture: review +123.45 kN"
    return DocumentParseResult.model_validate(
        {
            "contract": "openvigil.document-parse.v1",
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "model_manifest_sha256": "a" * 64,
            "execution_code_sha256": parser_code_identity(),
            "library_versions": dict(DOCUMENT_PARSER_VERSIONS),
            "body": text,
            "source_page_count": 2,
            "passages": [
                {
                    "ordinal": 0,
                    "text": text,
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "char_start": 0,
                    "char_end": len(text),
                    "parser_version": "declared-state-machine-wire-fixture",
                    "page_number": 2,
                    "native_locator": {
                        "kind": "docling_pdf_item",
                        "requires_numeric_review": True,
                        "regions": [
                            {
                                "page_number": 2,
                                "bbox": [20.0, 180.0, 280.0, 210.0],
                                "page_width": 300.0,
                                "page_height": 400.0,
                                "coordinate_space": "pdf_points_top_left",
                            }
                        ],
                    },
                }
            ],
        }
    )


async def queued_document(app, client):
    enable_parser(app)
    payload = await ingest(
        app, client, pdf_with_second_page_text(), "application/pdf", parser="docling"
    )
    async with app.state.session_factory() as session:
        event = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == payload["document_id"],
                OutboxEvent.event_type == KNOWLEDGE_DOCUMENT_PARSE_REQUESTED,
            )
        )
        assert event is not None
        return payload, event.id


async def test_pdf_registration_defers_all_parse_and_embedding_work(app, client, monkeypatch):
    async def forbidden_parse(*_args, **_kwargs):
        pytest.fail("registration must not call the long PDF parser")

    monkeypatch.setattr(document_parse, "parse_document_subprocess", forbidden_parse)
    payload, _event_id = await queued_document(app, client)
    async with app.state.session_factory() as session:
        document = await session.get(KnowledgeDocument, payload["document_id"])
        assert document.body == "" and document.vectorized is False
        assert document.ingestion_status == "pending_parse"
        assert document.metadata_[PARSE_STATE_KEY]["status"] == "pending"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(KnowledgePassage)
                .where(KnowledgePassage.document_id == document.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_id == document.id,
                    OutboxEvent.event_type == KNOWLEDGE_DOCUMENT_INDEX_REQUESTED,
                )
            )
            == 0
        )


async def test_parse_publication_and_replay_create_one_passage_and_index_job(
    app, client, monkeypatch
):
    calls = []

    async def parser(content, **_kwargs):
        calls.append(content)
        return protocol_result(content)

    monkeypatch.setattr(document_parse, "parse_document_subprocess", parser)
    payload, event_id = await queued_document(app, client)
    factory = app.state.session_factory
    assert await process_document_parse_event(
        factory, app.state.settings, app.state.artifact_verifier, event_id
    )
    assert (
        await process_document_parse_event(
            factory, app.state.settings, app.state.artifact_verifier, event_id
        )
        is False
    )
    assert len(calls) == 1
    async with factory() as session:
        document = await session.get(KnowledgeDocument, payload["document_id"])
        assert document.body == protocol_result(calls[0]).body
        assert document.ingestion_status == "pending" and document.vectorized is False
        assert document.metadata_[PARSE_STATE_KEY]["status"] == "parsed"
        pieces = list(
            (
                await session.scalars(
                    select(KnowledgePassage).where(KnowledgePassage.document_id == document.id)
                )
            ).all()
        )
        assert len(pieces) == 1 and pieces[0].page_number == 2
        assert pieces[0].source_sha256 == payload["artifact_sha256"]
        assert pieces[0].native_locator["requires_numeric_review"] is True
        events = list(
            (
                await session.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == document.id,
                        OutboxEvent.event_type == KNOWLEDGE_DOCUMENT_INDEX_REQUESTED,
                    )
                )
            ).all()
        )
        assert len(events) == 1
        index_id = events[0].id
    assert await process_knowledge_document_index_event(factory, app.state.settings, index_id)
    async with factory() as session:
        document = await session.get(KnowledgeDocument, payload["document_id"])
        assert document.vectorized is True and document.ingestion_status == "indexed"


async def test_failed_parser_has_three_attempts_and_keeps_terminal_failure(
    app, client, monkeypatch
):
    calls = []

    async def failing_parser(content, **_kwargs):
        calls.append(content)
        raise RuntimeError("controlled parser dependency failure")

    monkeypatch.setattr(document_parse, "parse_document_subprocess", failing_parser)
    payload, event_id = await queued_document(app, client)
    factory = app.state.session_factory
    for attempt in range(1, 4):
        if attempt < 3:
            with pytest.raises(DocumentParseFailure):
                await process_document_parse_event(
                    factory, app.state.settings, app.state.artifact_verifier, event_id
                )
            assert (
                event_id,
                KNOWLEDGE_DOCUMENT_PARSE_REQUESTED,
            ) in await recoverable_document_parse_events(factory)
        else:
            assert await process_document_parse_event(
                factory, app.state.settings, app.state.artifact_verifier, event_id
            )
    assert len(calls) == 3
    assert await recoverable_document_parse_events(factory) == []
    assert await process_document_parse_event(
        factory, app.state.settings, app.state.artifact_verifier, event_id
    )
    assert len(calls) == 3
    async with factory() as session:
        document = await session.get(KnowledgeDocument, payload["document_id"])
        event = await session.get(OutboxEvent, event_id)
        assert document.body == "" and document.vectorized is False
        assert document.ingestion_status == "parse_failed"
        assert document.metadata_[PARSE_STATE_KEY]["attempts"] == 3
        assert event.attempts == 3 and event.status == "failed"
        assert event.last_error == "RuntimeError"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(KnowledgePassage)
                .where(KnowledgePassage.document_id == document.id)
            )
            == 0
        )


async def test_new_lease_fences_old_parser_without_publishing_text(app, client, monkeypatch):
    payload, event_id = await queued_document(app, client)
    factory = app.state.session_factory

    async def superseded_parser(content, **_kwargs):
        async with factory() as session, session.begin():
            event = await session.get(OutboxEvent, event_id)
            event.claim_token = "a-new-owner"
            event.lease_expires_at = utcnow() + timedelta(minutes=5)
        return protocol_result(content)

    monkeypatch.setattr(document_parse, "parse_document_subprocess", superseded_parser)
    assert (
        await process_document_parse_event(
            factory, app.state.settings, app.state.artifact_verifier, event_id
        )
        is False
    )
    async with factory() as session:
        document = await session.get(KnowledgeDocument, payload["document_id"])
        event = await session.get(OutboxEvent, event_id)
        assert document.body == "" and document.vectorized is False
        assert event.claim_token == "a-new-owner" and event.status == "processing"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(KnowledgePassage)
                .where(KnowledgePassage.document_id == document.id)
            )
            == 0
        )


async def test_cancelled_parser_recovers_only_after_lease_expiry(app, client, monkeypatch):
    payload, event_id = await queued_document(app, client)
    factory = app.state.session_factory

    async def cancelled_parser(*_args, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(document_parse, "parse_document_subprocess", cancelled_parser)
    with pytest.raises(asyncio.CancelledError):
        await process_document_parse_event(
            factory, app.state.settings, app.state.artifact_verifier, event_id
        )
    assert await recoverable_document_parse_events(factory) == []
    async with factory() as session, session.begin():
        event = await session.get(OutboxEvent, event_id)
        assert event.status == "processing" and event.attempts == 1
        event.lease_expires_at = utcnow() - timedelta(seconds=1)
    assert await recoverable_document_parse_events(factory) == [
        (event_id, KNOWLEDGE_DOCUMENT_PARSE_REQUESTED)
    ]

    async def recovered_parser(content, **_kwargs):
        return protocol_result(content)

    monkeypatch.setattr(document_parse, "parse_document_subprocess", recovered_parser)
    assert await process_document_parse_event(
        factory, app.state.settings, app.state.artifact_verifier, event_id
    )
    async with factory() as session:
        document = await session.get(KnowledgeDocument, payload["document_id"])
        event = await session.get(OutboxEvent, event_id)
        assert event.attempts == 2 and event.status == "succeeded"
        assert document.metadata_[PARSE_STATE_KEY]["status"] == "parsed"


async def test_changed_original_after_conversion_does_not_publish_passages(
    app, client, monkeypatch
):
    payload, event_id = await queued_document(app, client)

    async def parser(content, **_kwargs):
        app.state.artifact_verifier.register_object(
            payload["artifact_uri"], b"changed", "application/pdf"
        )
        return protocol_result(content)

    monkeypatch.setattr(document_parse, "parse_document_subprocess", parser)
    factory = app.state.session_factory
    with pytest.raises(DocumentParseFailure):
        await process_document_parse_event(
            factory, app.state.settings, app.state.artifact_verifier, event_id
        )
    async with factory() as session:
        document = await session.get(KnowledgeDocument, payload["document_id"])
        assert document.body == "" and document.vectorized is False
        assert (
            await session.scalar(
                select(func.count())
                .select_from(KnowledgePassage)
                .where(KnowledgePassage.document_id == document.id)
            )
            == 0
        )


async def test_changed_parser_identity_fails_without_calling_parser(app, client, monkeypatch):
    payload, event_id = await queued_document(app, client)
    app.state.settings.document_parser_model_manifest_sha256 = "b" * 64

    async def forbidden_parse(*_args, **_kwargs):
        pytest.fail("a changed parser must not consume the document")

    monkeypatch.setattr(document_parse, "parse_document_subprocess", forbidden_parse)
    factory = app.state.session_factory
    assert await process_document_parse_event(
        factory, app.state.settings, app.state.artifact_verifier, event_id
    )
    async with factory() as session:
        document = await session.get(KnowledgeDocument, payload["document_id"])
        assert document.body == "" and document.ingestion_status == "parse_failed"
        assert document.metadata_[PARSE_STATE_KEY]["error_code"] == "DocumentParserIdentityMismatch"


async def test_repeated_registration_and_changed_parser_keep_immutable_document(app, client):
    payload, event_id = await queued_document(app, client)
    for _index in range(2):
        response = await client.post(
            "/api/v1/knowledge/documents", json=payload, headers={"Idempotency-Key": str(uuid4())}
        )
        assert response.status_code == 202 and response.json()["replayed"] is True
    changed = await client.post(
        "/api/v1/knowledge/documents",
        json={**payload, "parser": "native"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert changed.status_code == 409
    async with app.state.session_factory() as session:
        events = list(
            (
                await session.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == payload["document_id"],
                        OutboxEvent.event_type == KNOWLEDGE_DOCUMENT_PARSE_REQUESTED,
                    )
                )
            ).all()
        )
        assert [event.id for event in events] == [event_id]
        document = await session.get(KnowledgeDocument, payload["document_id"])
        assert document.body == "" and document.ingestion_status == "pending_parse"


async def test_upload_cannot_supply_server_owned_parse_state(app, client):
    payload, _event_id = await queued_document(app, client)
    response = await client.post(
        "/api/v1/knowledge/documents",
        json={**payload, "metadata": {PARSE_STATE_KEY: {"status": "parsed"}}},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422


async def test_scoped_registration_denies_before_reading_private_original(app, client, monkeypatch):
    payload, _event_id = await queued_document(app, client)
    async with app.state.session_factory() as session, session.begin():
        session.add(Tenant(id="parser-other-tenant", name="Other software test tenant"))

    async def forbidden_read(*_args, **_kwargs):
        pytest.fail("the forbidden document scope must be checked before object I/O")

    monkeypatch.setattr(app.state.artifact_verifier, "read_verified_object", forbidden_read)
    headers = {
        "X-WindOps-Test-Principal": "east-parser-manager",
        "X-WindOps-Test-Role": "operations_manager",
        "X-WindOps-Test-Tenant-Ids": "tenant-east-china",
        "X-WindOps-Test-Data-Scopes": "knowledge",
        "Idempotency-Key": str(uuid4()),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
    ) as scoped:
        response = await scoped.post(
            "/api/v1/knowledge/documents",
            json={
                **payload,
                "document_id": "KB-PARSER-FORBIDDEN",
                "tenant_id": "parser-other-tenant",
            },
        )
    # The existing scoped command/read boundary conceals inaccessible identities.
    assert response.status_code == 404


async def test_native_command_preserves_pre_parser_hash_and_replays_without_object_io(
    app, client, monkeypatch
):
    payload = await ingest(app, client, pdf_with_second_page_text(), "application/pdf")
    async with app.state.session_factory() as session:
        receipt = await session.scalar(
            select(CommandReceipt).where(
                CommandReceipt.target == payload["document_id"],
                CommandReceipt.command_type == "knowledge.document.ingest.v1",
            )
        )
        # This is the pre-increment model's complete canonical field set.
        legacy_payload = KnowledgeDocumentCreateRequest(**payload).model_dump(exclude={"parser"})
        assert receipt.request_hash == canonical_request_hash(legacy_payload)
        key = receipt.idempotency_key

    async def forbidden_read(*_args, **_kwargs):
        pytest.fail("a successful old command replay must not repeat object I/O")

    monkeypatch.setattr(app.state.artifact_verifier, "read_verified_object", forbidden_read)
    for supplied in (payload, {**payload, "parser": "native"}):
        replay = await client.post(
            "/api/v1/knowledge/documents", json=supplied, headers={"Idempotency-Key": key}
        )
        assert replay.status_code == 202
        assert replay.headers["Idempotency-Replayed"] == "true"
        assert replay.json()["document_id"] == payload["document_id"]
    changed = await client.post(
        "/api/v1/knowledge/documents",
        json={**payload, "parser": "docling"},
        headers={"Idempotency-Key": key},
    )
    assert changed.status_code == 409


@pytest.mark.parametrize("parser", ["native", "docling"])
async def test_same_subject_replay_rechecks_revoked_scope_before_receipt_or_object_io(
    app, client, monkeypatch, parser
):
    if parser == "docling":
        enable_parser(app)
    payload = await ingest(
        app, client, pdf_with_second_page_text(), "application/pdf", parser=parser
    )
    async with app.state.session_factory() as session:
        receipt = await session.scalar(
            select(CommandReceipt).where(
                CommandReceipt.target == payload["document_id"],
                CommandReceipt.command_type == "knowledge.document.ingest.v1",
            )
        )
        key, subject, replay_count = receipt.idempotency_key, receipt.subject, receipt.replay_count

    async def forbidden_read(*_args, **_kwargs):
        pytest.fail("revoked scope must be checked before object I/O")

    monkeypatch.setattr(app.state.artifact_verifier, "read_verified_object", forbidden_read)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-WindOps-Test-Principal": subject,
            "X-WindOps-Test-Role": "operations_manager",
            "X-WindOps-Test-Tenant-Ids": "tenant-east-china",
            "X-WindOps-Test-Data-Scopes": "knowledge",
            "Idempotency-Key": key,
        },
    ) as revoked:
        response = await revoked.post("/api/v1/knowledge/documents", json=payload)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert set(response.json()) == {"error"}
    async with app.state.session_factory() as session:
        receipt = await session.scalar(
            select(CommandReceipt).where(
                CommandReceipt.target == payload["document_id"],
                CommandReceipt.command_type == "knowledge.document.ingest.v1",
            )
        )
        assert receipt.replay_count == replay_count
