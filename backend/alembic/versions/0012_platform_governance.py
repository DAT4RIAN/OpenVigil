"""Add collaboration, versioned platform policies, data contracts, and twin profiles.

Revision ID: 0012_platform_governance
Revises: 0011_agent_tool_ledger
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_platform_governance"
down_revision: str | None = "0011_agent_tool_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text())
    op.add_column("ingest_sources", sa.Column("credential_secret_reference", sa.String(512)))
    op.create_table(
        "mission_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(40), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_subject", sa.String(160), nullable=False),
        sa.Column("author_email", sa.String(320)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_mission_comments_mission_created", "mission_comments", ["mission_id", "created_at"]
    )
    op.create_table(
        "platform_configuration_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("configuration_key", sa.String(96), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("value", json_type, nullable=False),
        sa.Column("secret_reference", sa.String(512)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "configuration_key", "revision", name="uq_platform_config_key_revision"
        ),
    )
    op.create_index(
        "ix_platform_config_key_active",
        "platform_configuration_revisions",
        ["configuration_key", "active"],
    )
    op.create_table(
        "data_contract_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(96), sa.ForeignKey("ingest_sources.id"), nullable=False),
        sa.Column("variable", sa.String(96), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("contract", json_type, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("source_id", "variable", "revision", name="uq_data_contract_revision"),
    )
    op.create_index(
        "ix_data_contract_source_active",
        "data_contract_definitions",
        ["source_id", "active"],
    )
    op.create_table(
        "asset_twin_profiles",
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), primary_key=True),
        sa.Column("manufacturer", sa.String(160), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("elevation_m", sa.Float(), nullable=False, server_default="0"),
        sa.Column("coordinate_reference_system", sa.String(96), nullable=False),
        sa.Column("geometry_uri", sa.String(1024), nullable=False),
        sa.Column("geometry_sha256", sa.String(64), nullable=False),
        sa.Column("updated_by", sa.String(160), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("asset_twin_profiles")
    op.drop_table("data_contract_definitions")
    op.drop_table("platform_configuration_revisions")
    op.drop_table("mission_comments")
    op.drop_column("ingest_sources", "credential_secret_reference")
