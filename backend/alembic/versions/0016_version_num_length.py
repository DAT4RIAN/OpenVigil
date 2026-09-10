"""Allow Alembic revisions longer than the default 32 characters.

Revision ID: 0016_version_num_length
Revises: 0016_tenant_asset_access_scope
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_version_num_length"
down_revision: str | None = "0016_tenant_asset_access_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic creates this table with VARCHAR(32) by default.  Keep the
    # migration revision itself short enough for the old column, then widen it
    # before applying longer, descriptive revision identifiers.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
