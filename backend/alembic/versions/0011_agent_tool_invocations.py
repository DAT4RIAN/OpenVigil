"""Add durable production Agent Tool invocation ledger.

Revision ID: 0011_agent_tool_ledger
Revises: 0010_model_runtime
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_agent_tool_ledger"
down_revision: str | None = "0010_model_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "agent_tool_invocations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_key", sa.String(96), nullable=False),
        sa.Column("tool_key", sa.String(96), nullable=False),
        sa.Column("mission_id", sa.String(40), sa.ForeignKey("missions.id")),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("arguments", json_type, nullable=False),
        sa.Column("result", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(96)),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("subject", "idempotency_key", name="uq_agent_tool_subject_key"),
    )
    op.create_index(
        "ix_agent_tool_invocations_mission_id",
        "agent_tool_invocations",
        ["mission_id"],
    )
    op.create_index(
        "ix_agent_tool_invocations_completed", "agent_tool_invocations", ["completed_at"]
    )


def downgrade() -> None:
    op.drop_table("agent_tool_invocations")
