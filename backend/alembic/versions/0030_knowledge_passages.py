"""Add immutable native document passages and independent vector indexes.

Revision ID: 0030_knowledge_passages
Revises: 0029_hybrid_tower_structural
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0030_knowledge_passages"
down_revision = "0029_hybrid_tower_structural"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_passages",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("document_version", sa.String(32), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=True),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(160), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(320), nullable=True),
        sa.Column(
            "native_locator",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "embedding", Vector(1536).with_variant(sa.LargeBinary(), "sqlite"), nullable=True
        ),
        sa.Column("embedding_provider", sa.String(96), nullable=True),
        sa.Column("embedding_model", sa.String(160), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"]),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_knowledge_passage_ordinal"),
        sa.CheckConstraint("ordinal >= 0", name="ck_knowledge_passage_ordinal"),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number >= 1", name="ck_knowledge_passage_page"
        ),
        sa.CheckConstraint(
            "char_start >= 0 AND char_end > char_start", name="ck_knowledge_passage_span"
        ),
    )
    op.create_index(
        "ix_knowledge_passages_document", "knowledge_passages", ["document_id", "ordinal"]
    )
    op.create_index(
        "ix_knowledge_passages_embedding_hnsw",
        "knowledge_passages",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("knowledge_passages")
