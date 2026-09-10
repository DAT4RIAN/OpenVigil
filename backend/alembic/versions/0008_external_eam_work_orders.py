"""Persist idempotent external EAM work-order synchronization.

Revision ID: 0008_external_eam
Revises: 0007_ordered_ingest_events
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_external_eam"
down_revision: str | None = "0007_ordered_ingest_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_work_order_links",
        sa.Column(
            "work_order_id",
            sa.String(40),
            sa.ForeignKey("work_orders.id"),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("sync_status", sa.String(48), nullable=False),
        sa.Column("last_payload_hash", sa.String(64), nullable=False),
        sa.Column("external_updated_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("provider", "external_id", name="uq_external_work_order_provider_id"),
    )
    op.create_index(
        "ix_external_work_order_status_updated",
        "external_work_order_links",
        ["sync_status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_external_work_order_status_updated", table_name="external_work_order_links")
    op.drop_table("external_work_order_links")
