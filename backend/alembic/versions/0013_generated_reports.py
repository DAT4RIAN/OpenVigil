"""Add immutable generated report snapshots.

Revision ID: 0013_generated_reports
Revises: 0012_platform_governance
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_generated_reports"
down_revision: str | None = "0012_platform_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "generated_reports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("report_type", sa.String(48), nullable=False),
        sa.Column("period", sa.String(24), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("snapshot", json_type, nullable=False),
        sa.Column("generation_reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_generated_reports_type_created",
        "generated_reports",
        ["report_type", "created_at"],
    )
    op.create_index(
        "ix_generated_reports_period_created",
        "generated_reports",
        ["period", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("generated_reports")
