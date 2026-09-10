"""Add selective indexes for diagnosis risk-priority pagination.

Revision ID: 0022_diagnosis_priority_indexes
Revises: 0021_ingest_source_secret_audits
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_diagnosis_priority_indexes"
down_revision: str | None = "0021_ingest_source_secret_audits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_alarms_severity_id", "alarms", ["severity", "id"])
    op.create_index("ix_turbines_health_id", "turbines", ["health_score", "id"])


def downgrade() -> None:
    op.drop_index("ix_turbines_health_id", table_name="turbines")
    op.drop_index("ix_alarms_severity_id", table_name="alarms")
