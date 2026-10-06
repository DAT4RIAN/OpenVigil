from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.model_base import JSON_VALUE, Base, utcnow


class KnowledgePassage(Base):
    """Immutable text and source locator; visibility is inherited from its document."""

    __tablename__ = "knowledge_passages"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_knowledge_passage_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_knowledge_passage_ordinal"),
        CheckConstraint(
            "page_number IS NULL OR page_number >= 1", name="ck_knowledge_passage_page"
        ),
        CheckConstraint(
            "char_start >= 0 AND char_end > char_start", name="ck_knowledge_passage_span"
        ),
        Index("ix_knowledge_passages_document", "document_id", "ordinal"),
        Index(
            "ix_knowledge_passages_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    document_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(160), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(320))
    native_locator: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | bytes | None] = mapped_column(
        Vector(1536).with_variant(LargeBinary(), "sqlite"), nullable=True
    )
    embedding_provider: Mapped[str | None] = mapped_column(String(96))
    embedding_model: Mapped[str | None] = mapped_column(String(160))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
