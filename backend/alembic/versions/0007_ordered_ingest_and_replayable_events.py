"""Add governed source ordering, quarantine, and replayable domain events.

Revision ID: 0007_ordered_ingest_events
Revises: 0006_decision_selection
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0007_ordered_ingest_events"
down_revision: str | None = "0006_decision_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_sources",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("policy", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(24), nullable=False, server_default="never_seen"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute(
        """
        INSERT INTO ingest_sources (id, display_name, source_kind, enabled, policy, status)
        VALUES (
            'scada-default',
            'Legacy normalized SCADA source',
            'rest',
            TRUE,
            '{"sequence_required": false, "max_lateness_seconds": 300}'::jsonb,
            'unknown'
        )
        """
    )
    op.add_column(
        "ingest_receipts",
        sa.Column("source_id", sa.String(96), nullable=False, server_default="scada-default"),
    )
    op.add_column(
        "ingest_receipts",
        sa.Column("disposition", sa.String(24), nullable=False, server_default="accepted"),
    )
    op.alter_column("ingest_receipts", "source_id", server_default=None)
    op.alter_column("ingest_receipts", "disposition", server_default=None)

    op.create_table(
        "ingest_stream_states",
        sa.Column(
            "source_id",
            sa.String(96),
            sa.ForeignKey("ingest_sources.id"),
            primary_key=True,
        ),
        sa.Column("stream_key", sa.String(160), primary_key=True),
        sa.Column("highest_sequence", sa.BigInteger()),
        sa.Column("watermark_observed_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("late_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("quarantined_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_ingest_stream_source_updated",
        "ingest_stream_states",
        ["source_id", "updated_at"],
    )

    op.add_column(
        "scada_samples",
        sa.Column(
            "source_id",
            sa.String(96),
            sa.ForeignKey("ingest_sources.id"),
            nullable=False,
            server_default="scada-default",
        ),
    )
    op.add_column("scada_samples", sa.Column("source_sequence", sa.BigInteger()))
    op.add_column(
        "scada_samples",
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column(
        "scada_samples",
        sa.Column("is_late", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_scada_samples_source_id", "scada_samples", ["source_id"])
    op.alter_column("scada_samples", "source_id", server_default=None)
    op.alter_column("scada_samples", "received_at", server_default=None)
    op.alter_column("scada_samples", "is_late", server_default=None)

    op.create_table(
        "quarantined_scada_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "source_event_id",
            sa.String(128),
            sa.ForeignKey("ingest_receipts.source_event_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source_id", sa.String(96), sa.ForeignKey("ingest_sources.id"), nullable=False),
        sa.Column("stream_key", sa.String(160), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index(
        "ix_quarantined_source_received",
        "quarantined_scada_samples",
        ["source_id", "received_at"],
    )

    op.create_table(
        "domain_events",
        sa.Column("sequence", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("id", sa.String(36), nullable=False, unique=True),
        sa.Column("event_type", sa.String(96), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(128), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_domain_events_type_sequence", "domain_events", ["event_type", "sequence"])
    op.create_index(
        "ix_domain_events_aggregate_sequence",
        "domain_events",
        ["aggregate_type", "aggregate_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_domain_events_aggregate_sequence", table_name="domain_events")
    op.drop_index("ix_domain_events_type_sequence", table_name="domain_events")
    op.drop_table("domain_events")
    op.drop_index("ix_quarantined_source_received", table_name="quarantined_scada_samples")
    op.drop_table("quarantined_scada_samples")
    op.drop_index("ix_scada_samples_source_id", table_name="scada_samples")
    op.drop_column("scada_samples", "is_late")
    op.drop_column("scada_samples", "received_at")
    op.drop_column("scada_samples", "source_sequence")
    op.drop_column("scada_samples", "source_id")
    op.drop_index("ix_ingest_stream_source_updated", table_name="ingest_stream_states")
    op.drop_table("ingest_stream_states")
    op.drop_column("ingest_receipts", "disposition")
    op.drop_column("ingest_receipts", "source_id")
    op.drop_table("ingest_sources")
