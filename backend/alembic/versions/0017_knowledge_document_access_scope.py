"""Add trusted tenant and asset ownership to knowledge documents.

Revision ID: 0017_knowledge_document_access_scope
Revises: 0016_version_num_length
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_knowledge_document_access_scope"
down_revision: str | None = "0016_version_num_length"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "tenant-east-china"


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("tenant_id", sa.String(64), nullable=True))
    op.add_column("knowledge_documents", sa.Column("wind_farm_id", sa.String(36), nullable=True))
    op.add_column("knowledge_documents", sa.Column("turbine_id", sa.String(32), nullable=True))
    op.add_column(
        "knowledge_documents",
        sa.Column("data_scope", sa.String(48), nullable=False, server_default="knowledge"),
    )
    # Existing data predates the tenant boundary and belongs to the only
    # tenant provisioned by 0016. Metadata is descriptive and is not used for
    # this backfill or for future authorization decisions.
    op.execute(
        sa.text(
            "UPDATE knowledge_documents SET tenant_id = :tenant_id WHERE tenant_id IS NULL"
        ).bindparams(tenant_id=DEFAULT_TENANT_ID)
    )
    op.create_foreign_key(
        "fk_knowledge_documents_tenant_id",
        "knowledge_documents",
        "tenants",
        ["tenant_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_knowledge_documents_wind_farm_id",
        "knowledge_documents",
        "wind_farms",
        ["wind_farm_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_knowledge_documents_turbine_id",
        "knowledge_documents",
        "turbines",
        ["turbine_id"],
        ["id"],
    )
    op.create_index(
        "ix_knowledge_documents_tenant_scope",
        "knowledge_documents",
        ["tenant_id", "wind_farm_id", "turbine_id", "data_scope"],
    )
    op.alter_column("knowledge_documents", "data_scope", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_tenant_scope", table_name="knowledge_documents")
    op.drop_constraint(
        "fk_knowledge_documents_turbine_id", "knowledge_documents", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_knowledge_documents_wind_farm_id", "knowledge_documents", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_knowledge_documents_tenant_id", "knowledge_documents", type_="foreignkey"
    )
    op.drop_column("knowledge_documents", "data_scope")
    op.drop_column("knowledge_documents", "turbine_id")
    op.drop_column("knowledge_documents", "wind_farm_id")
    op.drop_column("knowledge_documents", "tenant_id")
