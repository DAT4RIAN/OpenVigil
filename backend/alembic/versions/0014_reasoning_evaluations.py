"""Add reasoning evaluation and fail-closed policy evidence.

Revision ID: 0014_reasoning_evaluations
Revises: 0013_generated_reports
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_reasoning_evaluations"
down_revision: str | None = "0013_generated_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text())
    op.add_column(
        "agent_executions",
        sa.Column(
            "evaluation_result",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "agent_executions",
        sa.Column(
            "degradation_policy",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_executions", "degradation_policy")
    op.drop_column("agent_executions", "evaluation_result")
