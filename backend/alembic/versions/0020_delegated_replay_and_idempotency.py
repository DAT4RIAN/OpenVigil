"""Add delegated write replay protection and subject-scoped command receipts.

Revision ID: 0020_delegated_replay_and_idempotency
Revises: 0019_bounded_collection_indexes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_delegated_replay_and_idempotency"
down_revision: str | None = "0019_bounded_collection_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("command_receipts") as batch:
        batch.drop_constraint("uq_command_receipt_scope_key", type_="unique")
        batch.add_column(
            sa.Column("target", sa.String(length=160), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("replay_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("last_replayed_at", sa.DateTime(timezone=True)))
        batch.create_unique_constraint(
            "uq_command_receipt_subject_scope_target_key",
            ["subject", "command_type", "target", "idempotency_key"],
        )

    op.create_table(
        "delegated_request_nonces",
        sa.Column("jti_sha256", sa.String(length=64), primary_key=True),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("target", sa.String(length=1024), nullable=False),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_delegated_request_nonces_expires",
        "delegated_request_nonces",
        ["expires_at"],
    )
    op.create_table(
        "delegated_request_audits",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("jti_sha256", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("target", sa.String(length=1024), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_delegated_request_audits_subject_occurred",
        "delegated_request_audits",
        ["subject", "occurred_at"],
    )
    op.create_index(
        "ix_delegated_request_audits_jti_occurred",
        "delegated_request_audits",
        ["jti_sha256", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_delegated_request_audits_jti_occurred",
        table_name="delegated_request_audits",
    )
    op.drop_index(
        "ix_delegated_request_audits_subject_occurred",
        table_name="delegated_request_audits",
    )
    op.drop_table("delegated_request_audits")
    op.drop_index(
        "ix_delegated_request_nonces_expires",
        table_name="delegated_request_nonces",
    )
    op.drop_table("delegated_request_nonces")
    with op.batch_alter_table("command_receipts") as batch:
        batch.drop_constraint(
            "uq_command_receipt_subject_scope_target_key",
            type_="unique",
        )
        batch.drop_column("last_replayed_at")
        batch.drop_column("replay_count")
        batch.drop_column("target")
        batch.create_unique_constraint(
            "uq_command_receipt_scope_key",
            ["command_type", "idempotency_key"],
        )
