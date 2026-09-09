"""Add structured evidence, decisions, and complete execution audit fields.

Revision ID: 0002_domain_audit
Revises: 0001_wt023
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_domain_audit"
down_revision: str | None = "0001_wt023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "agent_executions",
        sa.Column("tool_calls", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "agent_executions",
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_executions",
        sa.Column("provider", sa.String(96), nullable=False, server_default="sqlalchemy"),
    )
    op.add_column("agent_executions", sa.Column("model", sa.String(160)))
    op.add_column(
        "agent_executions",
        sa.Column("token_usage", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "evidence",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("mission_id", sa.String(40), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("source_key", sa.String(96), nullable=False),
        sa.Column("evidence_type", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metrics", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("citation_uri", sa.String(640)),
        sa.Column("retrieval_method", sa.String(96)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("mission_id", "source_key", name="uq_evidence_mission_source_key"),
    )
    op.create_index("ix_evidence_mission_created", "evidence", ["mission_id", "created_at"])

    op.create_table(
        "decisions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column(
            "mission_id",
            sa.String(40),
            sa.ForeignKey("missions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_approval"),
        sa.Column("alternatives", JSONB, nullable=False),
        sa.Column("recommended_alternative_id", sa.String(64), nullable=False),
        sa.Column("recommendation_reason", sa.Text(), nullable=False),
        sa.Column("risks", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("approval_id", sa.String(36), sa.ForeignKey("approvals.id"), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_decisions_mission_id", "decisions", ["mission_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_decisions_mission_id", table_name="decisions")
    op.drop_table("decisions")
    op.drop_index("ix_evidence_mission_created", table_name="evidence")
    op.drop_table("evidence")
    op.drop_column("agent_executions", "token_usage")
    op.drop_column("agent_executions", "model")
    op.drop_column("agent_executions", "provider")
    op.drop_column("agent_executions", "latency_ms")
    op.drop_column("agent_executions", "tool_calls")
