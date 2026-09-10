"""Align required timestamps and ORM index contracts with PostgreSQL.

Revision ID: 0026_schema_contract_alignment
Revises: 0025_benchmark_event_score_scope
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_schema_contract_alignment"
down_revision: str | None = "0025_benchmark_event_score_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REQUIRED_TIMESTAMPS = (
    ("agent_executions", "started_at"),
    ("approvals", "created_at"),
    ("asset_health_events", "recorded_at"),
    ("decisions", "created_at"),
    ("decisions", "updated_at"),
    ("evidence", "created_at"),
    ("ingest_receipts", "received_at"),
    ("knowledge_cases", "created_at"),
    ("knowledge_documents", "updated_at"),
    ("missions", "created_at"),
    ("missions", "updated_at"),
    ("resource_reservations", "created_at"),
    ("tenants", "created_at"),
    ("turbines", "updated_at"),
    ("wind_farms", "created_at"),
    ("work_orders", "created_at"),
)


def _backfill_and_require(table_name: str, column_name: str) -> None:
    timestamp = sa.column(column_name, sa.DateTime(timezone=True))
    table = sa.table(table_name, timestamp)
    op.execute(
        table.update().where(timestamp.is_(None)).values({column_name: sa.func.current_timestamp()})
    )
    op.alter_column(
        table_name,
        column_name,
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def upgrade() -> None:
    for table_name, column_name in _REQUIRED_TIMESTAMPS:
        _backfill_and_require(table_name, column_name)


def downgrade() -> None:
    for table_name, column_name in reversed(_REQUIRED_TIMESTAMPS):
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
