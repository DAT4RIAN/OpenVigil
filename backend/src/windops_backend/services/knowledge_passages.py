from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from windops_backend.agents.embeddings import (
    EmbeddingProvider,
    _citation_href,
    _cosine_similarity,
    _unpack_vector,
    aggregate_embedding_vectors,
    pack_embedding_vector,
)
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.knowledge_parsing import ParsedKnowledge, parse_legacy_body
from windops_backend.model_knowledge_passage import KnowledgePassage
from windops_backend.models import KnowledgeDocument
from windops_backend.services.knowledge_access import knowledge_scope_clause


def add_passages(
    session: AsyncSession, document: KnowledgeDocument, parsed: ParsedKnowledge, *, verified: bool
) -> list[KnowledgePassage]:
    if document.body != parsed.body:
        raise ValueError("passage text does not match the immutable document body")
    rows = [
        KnowledgePassage(
            id=str(uuid4()),
            document_id=document.id,
            ordinal=piece.ordinal,
            document_version=document.document_version,
            source_sha256=document.artifact_sha256 if verified else None,
            text_sha256=piece.text_sha256,
            parser_version=piece.parser_version,
            page_number=piece.page_number,
            section=piece.section,
            native_locator={**piece.native_locator, "source_verified": verified},
            char_start=piece.char_start,
            char_end=piece.char_end,
            text=piece.text,
        )
        for piece in parsed.passages
    ]
    session.add_all(rows)
    return rows


async def document_passages(
    session: AsyncSession, document: KnowledgeDocument, *, create_legacy: bool = False
) -> list[KnowledgePassage]:
    rows = list(
        (
            await session.scalars(
                select(KnowledgePassage)
                .where(KnowledgePassage.document_id == document.id)
                .order_by(KnowledgePassage.ordinal)
            )
        ).all()
    )
    if not rows and create_legacy:
        # Caller owns the document row lock. Old text is preserved byte for byte;
        # a database locator never implies a verified position in the original file.
        parsed = parse_legacy_body(document.body)
        if parsed.body != document.body:
            raise ValueError(
                "historical knowledge text requires explicit normalization before indexing"
            )
        rows = add_passages(session, document, parsed, verified=False)
        await session.flush()
    return rows


def passage_current(passage: KnowledgePassage, provider: EmbeddingProvider) -> bool:
    return (
        passage.embedding is not None
        and passage.embedding_provider == provider.provider_name
        and passage.embedding_model == provider.model_name
    )


def stale_document_clause(provider: EmbeddingProvider) -> ColumnElement[bool]:
    passages = KnowledgePassage.__table__.alias("index_passage")
    belongs = passages.c.document_id == KnowledgeDocument.id
    has_passages = exists(select(1).select_from(passages).where(belongs))
    has_stale_passages = exists(
        select(1)
        .select_from(passages)
        .where(
            belongs,
            or_(
                passages.c.embedding.is_(None),
                passages.c.embedding_provider.is_distinct_from(provider.provider_name),
                passages.c.embedding_model.is_distinct_from(provider.model_name),
            ),
        )
    )
    return or_(
        KnowledgeDocument.vectorized.is_(False),
        KnowledgeDocument.embedding_provider.is_distinct_from(provider.provider_name),
        KnowledgeDocument.embedding_model.is_distinct_from(provider.model_name),
        ~has_passages,
        has_stale_passages,
    )


def passage_embedding_input(document: KnowledgeDocument, passage: KnowledgePassage) -> str:
    return f"{document.title}\n{passage.section or ''}\n{passage.text}"


def store_passage_vectors(
    session: AsyncSession,
    document: KnowledgeDocument,
    passages: list[KnowledgePassage],
    vectors: list[list[float]],
    provider: EmbeddingProvider,
) -> None:
    if not passages or len(passages) != len(vectors):
        raise ValueError("passage vectors must match the complete document passage set")
    dialect = session.bind.dialect.name if session.bind is not None else "unknown"
    indexed_at = datetime.now(UTC)
    for passage, vector in zip(passages, vectors, strict=True):
        passage.embedding = pack_embedding_vector(vector) if dialect == "sqlite" else vector
        passage.embedding_provider = provider.provider_name
        passage.embedding_model = provider.model_name
        passage.indexed_at = indexed_at
    aggregate = aggregate_embedding_vectors(vectors)
    document.embedding = pack_embedding_vector(aggregate) if dialect == "sqlite" else aggregate
    document.vectorized = True
    document.ingestion_status = "indexed"
    document.embedding_provider = provider.provider_name
    document.embedding_model = provider.model_name
    document.indexed_at = indexed_at
    document.updated_at = indexed_at


def serialize_passage(passage: KnowledgePassage) -> dict[str, Any]:
    return {
        "passage_id": passage.id,
        "document_id": passage.document_id,
        "document_version": passage.document_version,
        "ordinal": passage.ordinal,
        "source_sha256": passage.source_sha256,
        "text_sha256": passage.text_sha256,
        "parser_version": passage.parser_version,
        "page_number": passage.page_number,
        "section": passage.section,
        "native_locator": passage.native_locator,
        "char_start": passage.char_start,
        "char_end": passage.char_end,
        "text": passage.text,
        "embedding_provider": passage.embedding_provider,
        "embedding_model": passage.embedding_model,
        "indexed_at": passage.indexed_at,
        "citation_uri": f"windops://knowledge/passages/{passage.id}",
        "citation_href": f"/api/v1/knowledge/passages/{passage.id}",
        "source_href": (
            f"/api/v1/knowledge/documents/{passage.document_id}/source?passage_id={passage.id}"
        ),
    }


async def retrieve_passages(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    provider: EmbeddingProvider,
    query_vector: list[float],
    *,
    limit: int,
    minio_public_base: str,
) -> list[dict[str, Any]]:
    """Filter permissions and embedding version in SQL, before ranking or limiting."""
    scope = knowledge_scope_clause(
        policy,
        tenant_column=KnowledgeDocument.tenant_id,
        wind_farm_column=KnowledgeDocument.wind_farm_id,
        turbine_column=KnowledgeDocument.turbine_id,
        entity_column=KnowledgeDocument.id,
        data_scope_column=KnowledgeDocument.data_scope,
    )
    current = (
        KnowledgePassage.embedding.is_not(None),
        KnowledgePassage.embedding_provider == provider.provider_name,
        KnowledgePassage.embedding_model == provider.model_name,
        KnowledgePassage.document_version == KnowledgeDocument.document_version,
        or_(
            KnowledgePassage.source_sha256.is_(None),
            KnowledgePassage.source_sha256 == KnowledgeDocument.artifact_sha256,
        ),
    )
    dialect = session.bind.dialect.name if session.bind is not None else "unknown"
    statement = (
        select(KnowledgePassage, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgePassage.document_id)
        .where(scope, *current)
    )
    if dialect == "postgresql":
        distance = KnowledgePassage.embedding.cosine_distance(query_vector)
        rows = (
            await session.execute(
                statement.add_columns(distance).order_by(distance, KnowledgePassage.id).limit(limit)
            )
        ).all()
        ranked = [(passage, document, 1.0 - float(value)) for passage, document, value in rows]
        method = "pgvector_passage_hnsw_cosine"
    elif dialect == "sqlite":
        rows = (await session.execute(statement)).all()
        ranked = sorted(
            [
                (
                    passage,
                    document,
                    _cosine_similarity(
                        query_vector,
                        _unpack_vector(passage.embedding)
                        if isinstance(passage.embedding, bytes)
                        else list(passage.embedding or []),
                    ),
                )
                for passage, document in rows
            ],
            key=lambda item: (-item[2], item[0].id),
        )[:limit]
        method = "deterministic_test_passage_cosine"
    else:
        raise RuntimeError(f"unsupported RAG database dialect: {dialect}")
    result = []
    for passage, document, similarity in ranked:
        values = serialize_passage(passage)
        result.append(
            {
                "match_type": "knowledge_document",
                **{
                    key: value for key, value in values.items() if key not in {"text", "indexed_at"}
                },
                "title": document.title,
                "document_type": document.document_type,
                "excerpt": passage.text[:800],
                "similarity": round(similarity, 6),
                "retrieval_method": method,
                "embedding_provider": provider.provider_name,
                "embedding_model": provider.model_name,
            }
        )
    # Documents which predate passage indexing remain readable. They have no
    # verified page/section and never outrank as a second copy of an indexed file.
    has_passages = exists(
        select(1)
        .select_from(KnowledgePassage)
        .where(KnowledgePassage.document_id == KnowledgeDocument.id)
    )
    legacy_statement = select(KnowledgeDocument).where(
        scope,
        ~has_passages,
        KnowledgeDocument.vectorized.is_(True),
        KnowledgeDocument.embedding.is_not(None),
        KnowledgeDocument.embedding_provider == provider.provider_name,
        KnowledgeDocument.embedding_model == provider.model_name,
    )
    if dialect == "postgresql":
        distance = KnowledgeDocument.embedding.cosine_distance(query_vector)
        legacy_rows = (
            await session.execute(
                legacy_statement.add_columns(distance)
                .order_by(distance, KnowledgeDocument.id)
                .limit(limit)
            )
        ).all()
        legacy = [(document, 1.0 - float(value)) for document, value in legacy_rows]
    else:
        documents = (await session.scalars(legacy_statement)).all()
        legacy = [
            (
                document,
                _cosine_similarity(
                    query_vector,
                    _unpack_vector(document.embedding)
                    if isinstance(document.embedding, bytes)
                    else list(document.embedding or []),
                ),
            )
            for document in documents
        ]
    result.extend(
        {
            "match_type": "knowledge_document",
            "document_id": document.id,
            "document_version": document.document_version,
            "passage_id": None,
            "page_number": None,
            "native_locator": {"kind": "database_text", "source_verified": False},
            "title": document.title,
            "document_type": document.document_type,
            "excerpt": document.body[:320],
            "similarity": round(similarity, 6),
            "citation_uri": document.citation_uri,
            "citation_href": _citation_href(document.citation_uri, minio_public_base),
            "retrieval_method": "legacy_document_cosine",
            "embedding_provider": provider.provider_name,
            "embedding_model": provider.model_name,
        }
        for document, similarity in legacy
    )
    return sorted(
        result,
        key=lambda row: (
            -float(row["similarity"]),
            str(row.get("passage_id") or row["document_id"]),
        ),
    )[:limit]
