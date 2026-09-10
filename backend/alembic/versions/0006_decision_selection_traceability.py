"""Persist human alternative selection through approval and work execution.

Revision ID: 0006_decision_selection
Revises: 0005_generic_commands
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_decision_selection"
down_revision: str | None = "0005_generic_commands"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("approvals", sa.Column("selected_alternative_id", sa.String(64)))
    op.add_column("decisions", sa.Column("selected_alternative_id", sa.String(64)))
    op.add_column("work_orders", sa.Column("selected_alternative_id", sa.String(64)))
    op.add_column("work_orders", sa.Column("selected_action", sa.Text()))
    op.execute(
        """
        UPDATE decisions
        SET selected_alternative_id = recommended_alternative_id
        WHERE selected_alternative_id IS NULL AND approval_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE approvals AS approval
        SET selected_alternative_id = decision.selected_alternative_id
        FROM decisions AS decision
        WHERE approval.id = decision.approval_id
          AND approval.selected_alternative_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE work_orders AS work_order
        SET selected_alternative_id = decision.selected_alternative_id,
            selected_action = COALESCE(
                (
                    SELECT alternative ->> 'action'
                    FROM jsonb_array_elements(decision.alternatives::jsonb) AS alternative
                    WHERE alternative ->> 'alternative_id' = decision.selected_alternative_id
                    LIMIT 1
                ),
                'Legacy approved maintenance action'
            )
        FROM decisions AS decision
        WHERE decision.mission_id = work_order.mission_id
        """
    )
    op.alter_column("work_orders", "selected_alternative_id", nullable=False)
    op.alter_column("work_orders", "selected_action", nullable=False)


def downgrade() -> None:
    op.drop_column("work_orders", "selected_action")
    op.drop_column("work_orders", "selected_alternative_id")
    op.drop_column("decisions", "selected_alternative_id")
    op.drop_column("approvals", "selected_alternative_id")
