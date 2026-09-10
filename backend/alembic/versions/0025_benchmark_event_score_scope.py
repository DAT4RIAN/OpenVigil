"""Allow point-scorable CARE events without a run-aggregate CARE score.

Revision ID: 0025_benchmark_event_score_scope
Revises: 0024_care_benchmark_metadata
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025_benchmark_event_score_scope"
down_revision: str | None = "0024_care_benchmark_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_benchmark_event_result_score_state",
        "benchmark_event_results",
        type_="check",
    )
    op.create_check_constraint(
        "ck_benchmark_event_result_score_state",
        "benchmark_event_results",
        "(status = 'scored' AND scorable = TRUE) OR "
        "(status IN ('failed', 'unscorable') AND scorable = FALSE AND care_score IS NULL)",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE benchmark_event_results SET status = 'unscorable', scorable = FALSE, "
        "anomaly_detected = NULL, coverage_score = NULL, accuracy_score = NULL, "
        "reliability_score = NULL, earliness_score = NULL, "
        "failure_code = COALESCE(failure_code, 'aggregate-care-score-unavailable') "
        "WHERE status = 'scored' AND care_score IS NULL"
    )
    op.drop_constraint(
        "ck_benchmark_event_result_score_state",
        "benchmark_event_results",
        type_="check",
    )
    op.create_check_constraint(
        "ck_benchmark_event_result_score_state",
        "benchmark_event_results",
        "(status = 'scored' AND scorable = TRUE AND care_score IS NOT NULL) OR "
        "(status IN ('failed', 'unscorable') AND scorable = FALSE AND care_score IS NULL)",
    )
