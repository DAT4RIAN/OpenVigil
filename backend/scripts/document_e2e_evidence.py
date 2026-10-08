"""Verify actual PG/pgvector/Neo4j receipts after the document browser scenario."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from windops_backend.config import Settings
from windops_backend.document_parse_contract import PARSE_CONTRACT
from windops_backend.document_parse_identity import DOCUMENT_PARSER_VERSIONS, parser_code_identity
from windops_backend.document_parse_result_identity import (
    DOCUMENT_RESULT_HASH_CONTRACT,
    document_parse_result_hash,
)
from windops_backend.knowledge_graph.domain import NodeType
from windops_backend.knowledge_graph.factory import create_knowledge_graph_store
from windops_backend.knowledge_graph.projection import KNOWLEDGE_GRAPH_PROJECTION_ID
from windops_backend.model_knowledge_passage import KnowledgePassage
from windops_backend.models import DomainEvent, KnowledgeDocument, ReadAccessAudit
from windops_backend.services.document_parse import PARSE_STATE_KEY
from windops_backend.services.knowledge_contracts import (
    KNOWLEDGE_DOCUMENT_INDEX_REQUESTED,
    KNOWLEDGE_DOCUMENT_PARSE_REQUESTED,
)
from windops_backend.storage import OutboxEvent


async def document_database_evidence(config: dict[str, Any], folder: Path) -> dict[str, Any]:
    browser = json.loads((folder / "document-browser.json").read_text(encoding="utf-8"))
    ids = [browser["document_id"], browser["failed_document_id"]]
    engine = create_async_engine(config["database_url"])
    factory = async_sessionmaker(engine)
    try:
        async with factory() as session:
            documents = list(
                await session.scalars(
                    select(KnowledgeDocument).where(KnowledgeDocument.id.in_(ids))
                )
            )
            if len(documents) != 2:
                raise RuntimeError("Exactly two acceptance documents must persist")
            by_id = {row.id: row for row in documents}
            document, failed = by_id[ids[0]], by_id[ids[1]]
            assert document.ingestion_status == "indexed" and document.vectorized
            assert failed.ingestion_status == "parse_failed" and not failed.vectorized
            assert failed.body == "" and failed.embedding is None
            pieces = list(
                await session.scalars(
                    select(KnowledgePassage)
                    .where(KnowledgePassage.document_id.in_(ids))
                    .order_by(KnowledgePassage.ordinal)
                )
            )
            assert len(pieces) == 15 and all(piece.document_id == document.id for piece in pieces)
            assert all(
                piece.page_number == 2 and piece.source_sha256 == browser["artifact_sha256"]
                for piece in pieces
            )
            assert all(
                piece.embedding is not None and len(piece.embedding) == 1536 for piece in pieces
            )
            assert sum("table_cell" in piece.native_locator for piece in pieces) == 9
            state = document.metadata_[PARSE_STATE_KEY]
            assert state["status"] == "parsed" and state["attempts"] == 1
            assert state["observed_execution_code_sha256"] == parser_code_identity()
            assert state["observed_library_versions"] == DOCUMENT_PARSER_VERSIONS
            assert (
                state["identity"]["model_manifest_sha256"]
                == config["document_parser_model_manifest_sha256"]
            )
            assert document.metadata_["_openvigil_source_layout"]["unextracted_pages"] == [1]
            # Reconstruct from real JSONB values/immutable rows, not the transient wire output.
            result = {
                "contract": PARSE_CONTRACT,
                "source_sha256": document.artifact_sha256,
                "model_manifest_sha256": state["identity"]["model_manifest_sha256"],
                "execution_code_sha256": state["observed_execution_code_sha256"],
                "library_versions": state["observed_library_versions"],
                "body": document.body,
                "source_page_count": document.metadata_["_openvigil_source_layout"]["page_count"],
                "passages": [
                    {
                        **{
                            key: getattr(piece, key)
                            for key in (
                                "ordinal",
                                "text",
                                "text_sha256",
                                "char_start",
                                "char_end",
                                "parser_version",
                                "page_number",
                                "section",
                            )
                        },
                        "native_locator": {
                            key: value
                            for key, value in piece.native_locator.items()
                            if key != "source_verified"
                        },
                    }
                    for piece in pieces
                ],
            }
            assert state["result_hash_contract"] == DOCUMENT_RESULT_HASH_CONTRACT
            assert document_parse_result_hash(result) == state["result_sha256"]
            jobs = list(
                await session.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id.in_(ids),
                        OutboxEvent.event_type.in_(
                            (KNOWLEDGE_DOCUMENT_PARSE_REQUESTED, KNOWLEDGE_DOCUMENT_INDEX_REQUESTED)
                        ),
                    )
                )
            )
            assert len(jobs) == 3
            succeeded = [row for row in jobs if row.aggregate_id == document.id]
            assert len(succeeded) == 2 and all(
                row.status == "succeeded" and row.attempts == 1 for row in succeeded
            )
            rejected = [row for row in jobs if row.aggregate_id == failed.id]
            assert (
                len(rejected) == 1 and rejected[0].status == "failed" and rejected[0].attempts == 3
            )
            assert rejected[0].last_error == "DocumentParseFailure"
            events = list(
                await session.scalars(select(DomainEvent).where(DomainEvent.aggregate_id.in_(ids)))
            )
            assert sum(row.event_type == "knowledge.document.parsed" for row in events) == 1
            assert sum(row.event_type == "knowledge.document.parse.failed" for row in events) == 3
            for _ in range(30):
                audit_count = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ReadAccessAudit)
                        .where(ReadAccessAudit.subject == "business-manager")
                    )
                    or 0
                )
                if audit_count:
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Actual read-audit worker did not persist document reads")
            artifacts = [
                {"uri": row.artifact_uri, "sha256": row.artifact_sha256} for row in documents
            ]
        settings = Settings(
            **{"_env_file": None, **{k: v for k, v in config.items() if k != "fixture"}}
        )
        store = create_knowledge_graph_store(settings)
        try:
            for _ in range(60):
                snapshot = await store.snapshot(KNOWLEDGE_GRAPH_PROJECTION_ID)
                if snapshot is not None:
                    nodes = {node.entity_id: node for node in snapshot.nodes}
                    if all(piece.id in nodes for piece in pieces):
                        break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Real Neo4j projection did not publish all OCR passages")
            assert snapshot is not None
            for piece in pieces:
                node = nodes[piece.id]
                assert node.node_type is NodeType.KNOWLEDGE_PASSAGE
                assert node.properties["body"] == piece.text
                assert node.properties["sourceSha256"] == piece.source_sha256
                assert node.properties["textSha256"] == piece.text_sha256
                assert json.loads(str(node.properties["nativeLocator"])) == piece.native_locator
            assert not any(
                node.node_type is NodeType.KNOWLEDGE_PASSAGE
                and (
                    node.entity_id == f"{failed.id}#body"
                    or node.properties.get("documentId") == failed.id
                )
                for node in snapshot.nodes
            )
            graph = {
                "backend": "neo4j",
                "nodes": len(snapshot.nodes),
                "relationships": len(snapshot.relationships),
                "source_revision": snapshot.source_revision,
                "verified_ocr_passages": 15,
                "failed_document_passages": 0,
            }
        finally:
            await store.close()
        return {
            "counts": {
                "scenario_documents": 2,
                "scenario_passages": 15,
                "scenario_parse_jobs": 2,
                "scenario_index_jobs": 1,
            },
            "result_sha256": state["result_sha256"],
            "jsonb_result_reconstructed": True,
            "parse_attempts": {document.id: 1, failed.id: 3},
            "observed_versions": state["observed_library_versions"],
            "manager_read_audits": audit_count,
            "artifacts": artifacts,
            "graph": graph,
        }
    finally:
        await engine.dispose()
