"""Add durable alarm acknowledgement and assignment command state.

Revision ID: 0015_alarm_command_state
Revises: 0014_reasoning_evaluations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_alarm_command_state"
down_revision: str | None = "0014_reasoning_evaluations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("alarms", sa.Column("acknowledged_at", sa.DateTime(timezone=True)))
    op.add_column("alarms", sa.Column("acknowledged_by", sa.String(length=160)))
    op.add_column("alarms", sa.Column("assigned_to", sa.String(length=160)))
    op.add_column("alarms", sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.add_column(
        "alarms",
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "alarms",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("alarms", "updated_at")
    op.drop_column("alarms", "revision")
    op.drop_column("alarms", "resolved_at")
    op.drop_column("alarms", "assigned_to")
    op.drop_column("alarms", "acknowledged_by")
    op.drop_column("alarms", "acknowledged_at")
