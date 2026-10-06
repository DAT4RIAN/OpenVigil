"""Add structural mission context, independent health review and pending case governance.

Revision ID: 0032_structural_workflow
Revises: 0031_engineering_claims
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032_structural_workflow"
down_revision = "0031_engineering_claims"
branch_labels = None
depends_on = None


def _asset_columns() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("wind_farm_id", sa.String(36), sa.ForeignKey("wind_farms.id"), nullable=False),
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
    ]


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_unique_constraint(
        "uq_prestress_id_asset", "prestress_observations", ["id", "turbine_id"]
    )
    op.create_table(
        "structural_mission_contexts",
        sa.Column(
            "mission_id",
            sa.String(40),
            sa.ForeignKey("missions.id"),
            primary_key=True,
            nullable=False,
        ),
        *_asset_columns(),
        sa.Column("component_id", sa.String(36), nullable=False),
        sa.Column("scenario", sa.String(40), nullable=False),
        sa.Column("origin_fingerprint", sa.String(64), nullable=False),
        sa.Column("context_sha256", sa.String(64), nullable=False),
        sa.Column("frozen_context", json_type, nullable=False),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("engineering_claims.id"), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["component_id", "turbine_id"], ["tower_components.id", "tower_components.turbine_id"]
        ),
        sa.UniqueConstraint(
            "turbine_id", "origin_fingerprint", name="uq_structural_mission_origin"
        ),
        sa.CheckConstraint(
            "scenario IN ('modal_frequency_review','prestress_retest')",
            name="ck_structural_mission_scenario",
        ),
    )
    op.create_table(
        "structural_health_reviews",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        *_asset_columns(),
        sa.Column(
            "mission_id",
            sa.String(40),
            sa.ForeignKey("structural_mission_contexts.mission_id"),
            nullable=False,
        ),
        sa.Column("work_order_id", sa.String(40), sa.ForeignKey("work_orders.id"), nullable=False),
        sa.Column("mission_revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("hypothesis_outcome", sa.String(24), nullable=False),
        sa.Column("assessment", json_type, nullable=False),
        sa.Column("reviewed_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "work_order_id", "mission_revision", name="uq_structural_health_revision"
        ),
        sa.CheckConstraint(
            "action IN ('resolve_review','requires_followup')", name="ck_structural_health_action"
        ),
    )
    op.create_index(
        "ix_structural_health_history", "structural_health_reviews", ["work_order_id", "created_at"]
    )
    op.create_table(
        "structural_case_reviews",
        sa.Column(
            "case_id",
            sa.String(40),
            sa.ForeignKey("knowledge_cases.id"),
            primary_key=True,
            nullable=False,
        ),
        *_asset_columns(),
        sa.Column(
            "health_review_id",
            sa.String(36),
            sa.ForeignKey("structural_health_reviews.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.String(160), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected')", name="ck_structural_case_status"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_structural_case_revision"),
    )
    op.create_table(
        "structural_retest_handoffs",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        *_asset_columns(),
        sa.Column(
            "mission_id",
            sa.String(40),
            sa.ForeignKey("structural_mission_contexts.mission_id"),
            nullable=False,
        ),
        sa.Column("work_order_id", sa.String(40), sa.ForeignKey("work_orders.id"), nullable=False),
        sa.Column(
            "health_review_id",
            sa.String(36),
            sa.ForeignKey("structural_health_reviews.id"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("work_order_tasks.id"), nullable=False),
        sa.Column("modal_id", sa.String(36), nullable=True),
        sa.Column("prestress_id", sa.String(36), nullable=True),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("artifact_uri", sa.String(1024), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("measurement", json_type, nullable=False),
        sa.Column("verified_by", sa.String(160), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["modal_id", "turbine_id"], ["modal_observations.id", "modal_observations.turbine_id"]
        ),
        sa.CheckConstraint(
            "(modal_id IS NOT NULL AND prestress_id IS NULL) OR "
            "(modal_id IS NULL AND prestress_id IS NOT NULL)",
            name="ck_structural_retest_one_source",
        ),
        sa.ForeignKeyConstraint(
            ["prestress_id", "turbine_id"],
            ["prestress_observations.id", "prestress_observations.turbine_id"],
        ),
        sa.UniqueConstraint(
            "work_order_id", "source_fingerprint", name="uq_structural_retest_handoff"
        ),
    )
    op.create_index(
        "ix_structural_retest_order_time",
        "structural_retest_handoffs",
        ["work_order_id", "verified_at"],
    )
    for table in (
        "structural_mission_contexts",
        "structural_health_reviews",
        "structural_case_reviews",
        "structural_retest_handoffs",
    ):
        op.create_index(f"ix_{table}_turbine_id", table, ["turbine_id"])


def downgrade() -> None:
    op.drop_table("structural_retest_handoffs")
    op.drop_table("structural_case_reviews")
    op.drop_table("structural_health_reviews")
    op.drop_table("structural_mission_contexts")
    op.drop_constraint("uq_prestress_id_asset", "prestress_observations", type_="unique")
