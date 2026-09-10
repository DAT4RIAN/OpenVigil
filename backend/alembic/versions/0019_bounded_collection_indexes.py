"""Add indexes for bounded operational collections and latest health reads.

Revision ID: 0019_bounded_collection_indexes
Revises: 0018_platform_configuration_security
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_bounded_collection_indexes"
down_revision: str | None = "0018_platform_configuration_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("ix_alarms_turbine_status_severity_id", "alarms", ["turbine_id", "status", "severity", "id"]),
    ("ix_missions_updated_id", "missions", ["updated_at", "id"]),
    ("ix_missions_status_updated_id", "missions", ["status", "updated_at", "id"]),
    ("ix_missions_turbine_updated_id", "missions", ["turbine_id", "updated_at", "id"]),
    ("ix_work_orders_planned_id", "work_orders", ["planned_start", "id"]),
    (
        "ix_work_orders_status_planned_id",
        "work_orders",
        ["status", "planned_start", "id"],
    ),
    (
        "ix_work_orders_team_planned_id",
        "work_orders",
        ["assigned_team", "planned_start", "id"],
    ),
    ("ix_resources_type_status_id", "resources", ["resource_type", "status", "id"]),
    (
        "ix_reservations_resource_created_id",
        "resource_reservations",
        ["resource_id", "created_at", "id"],
    ),
    (
        "ix_weather_farm_starts_ends_id",
        "weather_windows",
        ["wind_farm_id", "starts_at", "ends_at", "id"],
    ),
)


def upgrade() -> None:
    for name, table_name, columns in INDEXES:
        op.create_index(name, table_name, columns)
    op.create_index(
        "ix_asset_health_turbine_recorded_id",
        "asset_health_events",
        ["turbine_id", sa.text("recorded_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asset_health_turbine_recorded_id",
        table_name="asset_health_events",
    )
    for name, table_name, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table_name)
