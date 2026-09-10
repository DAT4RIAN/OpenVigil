"""Add governed knowledge-document artifacts and indexing state.

Revision ID: 0009_knowledge_ingestion
Revises: 0008_external_eam
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_knowledge_ingestion"
down_revision: str | None = "0008_external_eam"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("artifact_uri", sa.String(1024)))
    op.add_column("knowledge_documents", sa.Column("artifact_sha256", sa.String(64)))
    op.add_column("knowledge_documents", sa.Column("content_type", sa.String(128)))
    op.add_column("knowledge_documents", sa.Column("content_size_bytes", sa.BigInteger()))
    op.add_column(
        "knowledge_documents",
        sa.Column("document_version", sa.String(32), server_default="1", nullable=False),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("ingestion_status", sa.String(32), server_default="pending", nullable=False),
    )
    op.add_column("knowledge_documents", sa.Column("embedding_provider", sa.String(96)))
    op.add_column("knowledge_documents", sa.Column("embedding_model", sa.String(160)))
    op.add_column("knowledge_documents", sa.Column("indexed_at", sa.DateTime(timezone=True)))
    op.add_column("knowledge_documents", sa.Column("created_by", sa.String(160)))
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.execute(
        """
        UPDATE knowledge_documents
        SET ingestion_status = CASE WHEN vectorized THEN 'indexed' ELSE 'pending' END,
            indexed_at = CASE WHEN vectorized THEN updated_at ELSE NULL END,
            created_at = updated_at
        """
    )


def downgrade() -> None:
    for column in (
        "created_at",
        "created_by",
        "indexed_at",
        "embedding_model",
        "embedding_provider",
        "ingestion_status",
        "metadata",
        "document_version",
        "content_size_bytes",
        "content_type",
        "artifact_sha256",
        "artifact_uri",
    ):
        op.drop_column("knowledge_documents", column)
