"""Add outbox fencing, read attribution, and a versioned agent catalog.

Revision ID: 0004_operational_hardening
Revises: 0003_durable_execution
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_operational_hardening"
down_revision: str | None = "0003_durable_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("claim_token", sa.String(36)))
    op.add_column("outbox_events", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.create_index("ix_outbox_status_lease", "outbox_events", ["status", "lease_expires_at"])

    op.create_table(
        "catalog_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.String(32), nullable=False, unique=True),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "agent_definitions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("agent_key", sa.String(96), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("role", sa.String(96), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column(
            "catalog_version_id",
            sa.String(64),
            sa.ForeignKey("catalog_versions.id"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("agent_key", "version", name="uq_agent_definition_key_version"),
    )
    op.create_index(
        "ix_agent_definitions_catalog_version_id",
        "agent_definitions",
        ["catalog_version_id"],
    )
    op.create_table(
        "skill_definitions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("skill_key", sa.String(96), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column(
            "catalog_version_id",
            sa.String(64),
            sa.ForeignKey("catalog_versions.id"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.UniqueConstraint("skill_key", "version", name="uq_skill_definition_key_version"),
    )
    op.create_index(
        "ix_skill_definitions_catalog_version_id",
        "skill_definitions",
        ["catalog_version_id"],
    )
    op.create_table(
        "tool_definitions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("tool_key", sa.String(96), nullable=False),
        sa.Column("mode", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column(
            "catalog_version_id",
            sa.String(64),
            sa.ForeignKey("catalog_versions.id"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.UniqueConstraint("tool_key", "version", name="uq_tool_definition_key_version"),
    )
    op.create_index(
        "ix_tool_definitions_catalog_version_id",
        "tool_definitions",
        ["catalog_version_id"],
    )
    op.create_table(
        "agent_skill_links",
        sa.Column(
            "agent_definition_id",
            sa.String(96),
            sa.ForeignKey("agent_definitions.id"),
            primary_key=True,
        ),
        sa.Column(
            "skill_definition_id",
            sa.String(96),
            sa.ForeignKey("skill_definitions.id"),
            primary_key=True,
        ),
        sa.Column(
            "catalog_version_id",
            sa.String(64),
            sa.ForeignKey("catalog_versions.id"),
            nullable=False,
        ),
    )
    op.create_table(
        "agent_tool_links",
        sa.Column(
            "agent_definition_id",
            sa.String(96),
            sa.ForeignKey("agent_definitions.id"),
            primary_key=True,
        ),
        sa.Column(
            "tool_definition_id",
            sa.String(96),
            sa.ForeignKey("tool_definitions.id"),
            primary_key=True,
        ),
        sa.Column(
            "catalog_version_id",
            sa.String(64),
            sa.ForeignKey("catalog_versions.id"),
            nullable=False,
        ),
    )

    op.add_column("agent_executions", sa.Column("catalog_version_id", sa.String(64)))
    op.add_column("agent_executions", sa.Column("agent_definition_id", sa.String(96)))
    op.create_foreign_key(
        "fk_agent_execution_catalog_version",
        "agent_executions",
        "catalog_versions",
        ["catalog_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_agent_execution_definition",
        "agent_executions",
        "agent_definitions",
        ["agent_definition_id"],
        ["id"],
    )
    op.create_index(
        "ix_agent_executions_catalog_version_id",
        "agent_executions",
        ["catalog_version_id"],
    )
    op.create_index(
        "ix_agent_executions_agent_definition_id",
        "agent_executions",
        ["agent_definition_id"],
    )

    op.create_table(
        "read_access_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("role", sa.String(96), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("endpoint", sa.String(320), nullable=False),
        sa.Column("query", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "accessed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_read_access_subject_accessed",
        "read_access_audits",
        ["subject", "accessed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_read_access_subject_accessed", table_name="read_access_audits")
    op.drop_table("read_access_audits")

    op.drop_index("ix_agent_executions_agent_definition_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_catalog_version_id", table_name="agent_executions")
    op.drop_constraint("fk_agent_execution_definition", "agent_executions", type_="foreignkey")
    op.drop_constraint("fk_agent_execution_catalog_version", "agent_executions", type_="foreignkey")
    op.drop_column("agent_executions", "agent_definition_id")
    op.drop_column("agent_executions", "catalog_version_id")

    op.drop_table("agent_tool_links")
    op.drop_table("agent_skill_links")
    op.drop_index("ix_tool_definitions_catalog_version_id", table_name="tool_definitions")
    op.drop_table("tool_definitions")
    op.drop_index("ix_skill_definitions_catalog_version_id", table_name="skill_definitions")
    op.drop_table("skill_definitions")
    op.drop_index("ix_agent_definitions_catalog_version_id", table_name="agent_definitions")
    op.drop_table("agent_definitions")
    op.drop_table("catalog_versions")

    op.drop_index("ix_outbox_status_lease", table_name="outbox_events")
    op.drop_column("outbox_events", "lease_expires_at")
    op.drop_column("outbox_events", "claim_token")
