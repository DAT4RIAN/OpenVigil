"""Separate canonical quality identity from append-only stage artifacts.

Revision ID: 0027_quality_artifact_stages
Revises: 0026_schema_contract_alignment
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_quality_artifact_stages"
down_revision: str | None = "0026_schema_contract_alignment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "benchmark_quality_reports",
        sa.Column("canonical_content_sha256", sa.String(64), nullable=True),
    )
    op.create_table(
        "benchmark_quality_artifacts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "quality_report_id",
            sa.String(64),
            sa.ForeignKey("benchmark_quality_reports.id"),
            nullable=False,
        ),
        sa.Column("artifact_stage", sa.String(64), nullable=False),
        sa.Column("identity_sha256", sa.String(64), nullable=False),
        sa.Column("artifact_uri", sa.String(1024), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("mask_uri", sa.String(1024), nullable=False),
        sa.Column("mask_sha256", sa.String(64), nullable=False),
        sa.Column("summary", _json_type(), nullable=False),
        sa.Column("audit_subject", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("identity_sha256", name="uq_benchmark_quality_artifact_identity"),
    )
    op.create_index(
        "ix_benchmark_quality_artifacts_quality_report_id",
        "benchmark_quality_artifacts",
        ["quality_report_id"],
    )
    op.create_index(
        "ix_benchmark_quality_artifacts_report_created",
        "benchmark_quality_artifacts",
        ["quality_report_id", "created_at"],
    )
    op.create_index(
        "ix_benchmark_quality_artifacts_stage_created",
        "benchmark_quality_artifacts",
        ["artifact_stage", "created_at"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO benchmark_quality_artifacts (
                id,
                quality_report_id,
                artifact_stage,
                identity_sha256,
                artifact_uri,
                artifact_sha256,
                mask_uri,
                mask_sha256,
                summary,
                audit_subject,
                created_at
            )
            SELECT
                'legacy-' || substr(id, 1, 57),
                id,
                'legacy-migrated-v1',
                artifact_sha256,
                artifact_uri,
                artifact_sha256,
                mask_uri,
                mask_sha256,
                summary,
                'migration:0027_quality_artifact_stages',
                created_at
            FROM benchmark_quality_reports
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_benchmark_quality_artifacts_stage_created",
        table_name="benchmark_quality_artifacts",
    )
    op.drop_index(
        "ix_benchmark_quality_artifacts_report_created",
        table_name="benchmark_quality_artifacts",
    )
    op.drop_index(
        "ix_benchmark_quality_artifacts_quality_report_id",
        table_name="benchmark_quality_artifacts",
    )
    op.drop_table("benchmark_quality_artifacts")
    op.drop_column("benchmark_quality_reports", "canonical_content_sha256")
