"""Add durable workflow outbox and verified field-task evidence.

Revision ID: 0003_durable_execution
Revises: 0002_domain_audit
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_durable_execution"
down_revision: str | None = "0002_domain_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=96), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_outbox_status_created", "outbox_events", ["status", "created_at"])
    op.create_index("ix_outbox_aggregate", "outbox_events", ["aggregate_type", "aggregate_id"])
    op.create_table(
        "field_task_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(length=36),
            sa.ForeignKey("work_order_tasks.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("artifact_uri", sa.String(length=1024), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("measurement", postgresql.JSONB(), nullable=False),
        sa.Column("verified_by", sa.String(length=160), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_field_task_evidence_task_id", "field_task_evidence", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_field_task_evidence_task_id", table_name="field_task_evidence")
    op.drop_table("field_task_evidence")
    op.drop_index("ix_outbox_aggregate", table_name="outbox_events")
    op.drop_index("ix_outbox_status_created", table_name="outbox_events")
    op.drop_table("outbox_events")
