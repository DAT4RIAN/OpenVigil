"""Add the index used by bounded suitable-first weather selection.

Revision ID: 0023_bounded_weather_selection
Revises: 0022_diagnosis_priority_indexes
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023_bounded_weather_selection"
down_revision: str | None = "0022_diagnosis_priority_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_weather_farm_suitable_starts_ends_id",
        "weather_windows",
        ["wind_farm_id", "suitable", "starts_at", "ends_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weather_farm_suitable_starts_ends_id",
        table_name="weather_windows",
    )
