"""Add durable idempotency receipts for generic business commands.

Revision ID: 0005_generic_commands
Revises: 0004_operational_hardening
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_generic_commands"
down_revision: str | None = "0004_operational_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "command_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("command_type", sa.String(96), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("response_body", JSONB, nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("command_type", "idempotency_key", name="uq_command_receipt_scope_key"),
    )
    op.create_index(
        "ix_command_receipts_subject_created",
        "command_receipts",
        ["subject", "created_at"],
    )
    op.add_column(
        "work_orders",
        sa.Column(
            "closure_policy",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("work_orders", sa.Column("planned_start", sa.DateTime(timezone=True)))
    op.add_column("work_orders", sa.Column("deadline", sa.DateTime(timezone=True)))
    op.add_column(
        "work_orders",
        sa.Column("estimated_duration_hours", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "work_orders",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "work_order_tasks",
        sa.Column("schema_version", sa.String(64), nullable=False, server_default="legacy-v1"),
    )
    op.add_column(
        "work_order_tasks",
        sa.Column(
            "measurement_schema",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "resources",
        sa.Column("attributes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "resources",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "weather_windows",
        sa.Column("attributes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("weather_windows", "attributes")
    op.drop_column("resources", "updated_at")
    op.drop_column("resources", "attributes")
    op.drop_column("work_order_tasks", "measurement_schema")
    op.drop_column("work_order_tasks", "schema_version")
    op.drop_column("work_orders", "updated_at")
    op.drop_column("work_orders", "estimated_duration_hours")
    op.drop_column("work_orders", "deadline")
    op.drop_column("work_orders", "planned_start")
    op.drop_column("work_orders", "closure_policy")
    op.drop_index("ix_command_receipts_subject_created", table_name="command_receipts")
    op.drop_table("command_receipts")
