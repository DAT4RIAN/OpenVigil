"""Add the tenant boundary used by scoped knowledge-graph reads.

Revision ID: 0016_tenant_asset_access_scope
Revises: 0015_alarm_command_state
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_tenant_asset_access_scope"
down_revision: str | None = "0015_alarm_command_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "tenant-east-china"


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.bulk_insert(
        sa.table(
            "tenants",
            sa.column("id", sa.String(64)),
            sa.column("name", sa.String(160)),
            sa.column("status", sa.String(24)),
        ),
        [
            {
                "id": DEFAULT_TENANT_ID,
                "name": "East China Wind Operations",
                "status": "active",
            }
        ],
    )
    op.add_column(
        "wind_farms",
        sa.Column(
            "tenant_id",
            sa.String(64),
            nullable=False,
            server_default=sa.text(f"'{DEFAULT_TENANT_ID}'"),
        ),
    )
    op.create_foreign_key(
        "fk_wind_farms_tenant_id",
        "wind_farms",
        "tenants",
        ["tenant_id"],
        ["id"],
    )
    op.create_index("ix_wind_farms_tenant_id", "wind_farms", ["tenant_id"])
    op.alter_column("wind_farms", "tenant_id", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_wind_farms_tenant_id", table_name="wind_farms")
    op.drop_constraint("fk_wind_farms_tenant_id", "wind_farms", type_="foreignkey")
    op.drop_column("wind_farms", "tenant_id")
    op.drop_table("tenants")
