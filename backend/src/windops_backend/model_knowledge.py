from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.model_base import JSON_VALUE, Base, utcnow


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index(
            "ix_knowledge_documents_tenant_scope",
            "tenant_id",
            "wind_farm_id",
            "turbine_id",
            "data_scope",
        ),
        Index(
            "ix_knowledge_documents_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # These columns are the server-trusted visibility boundary.  Metadata is
    # descriptive only and must never be used to authorize a document read.
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    wind_farm_id: Mapped[str | None] = mapped_column(ForeignKey("wind_farms.id"), nullable=True)
    turbine_id: Mapped[str | None] = mapped_column(ForeignKey("turbines.id"), nullable=True)
    data_scope: Mapped[str] = mapped_column(String(48), nullable=False, default="knowledge")
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    citation_uri: Mapped[str] = mapped_column(String(320), nullable=False)
    artifact_uri: Mapped[str | None] = mapped_column(String(1024))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(128))
    content_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    document_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_VALUE, default=dict)
    ingestion_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    embedding: Mapped[list[float] | bytes | None] = mapped_column(
        Vector(1536).with_variant(LargeBinary(), "sqlite"), nullable=True
    )
    vectorized: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding_provider: Mapped[str | None] = mapped_column(String(96))
    embedding_model: Mapped[str | None] = mapped_column(String(160))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
