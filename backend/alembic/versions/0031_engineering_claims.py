"""Add frozen structural evidence cards and human claim-review history.

Revision ID: 0031_engineering_claims
Revises: 0030_knowledge_passages
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_engineering_claims"
down_revision = "0030_knowledge_passages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "engineering_claims",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("wind_farm_id", sa.String(36), sa.ForeignKey("wind_farms.id"), nullable=False),
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
        sa.Column("mission_id", sa.String(40), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("component_id", sa.String(36), nullable=False),
        sa.Column("claim_kind", sa.String(48), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=False),
        sa.Column("applicability", json_type, nullable=False),
        sa.Column("evidence_cards", json_type, nullable=False),
        sa.Column("missing_evidence", json_type, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.String(160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["component_id", "turbine_id"], ["tower_components.id", "tower_components.turbine_id"]
        ),
        sa.CheckConstraint("revision >= 1", name="ck_engineering_claim_revision"),
        sa.CheckConstraint(
            "claim_kind IN ('screening_finding','retest_recommendation','procedure_guidance')",
            name="ck_engineering_claim_kind",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected','withdrawn')",
            name="ck_engineering_claim_review",
        ),
        sa.CheckConstraint("valid_until > created_at", name="ck_engineering_claim_expiry"),
    )
    op.create_index("ix_engineering_claims_turbine_id", "engineering_claims", ["turbine_id"])
    op.create_index(
        "ix_engineering_claim_mission", "engineering_claims", ["mission_id", "created_at"]
    )
    op.create_table(
        "engineering_claim_reviews",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "claim_id", sa.String(36), sa.ForeignKey("engineering_claims.id"), nullable=False
        ),
        sa.Column("claim_revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "claim_id", "claim_revision", name="uq_engineering_claim_review_revision"
        ),
        sa.CheckConstraint("claim_revision >= 2", name="ck_engineering_review_revision"),
        sa.CheckConstraint(
            "action IN ('approve','reject','withdraw')", name="ck_engineering_review_action"
        ),
    )
    op.create_index(
        "ix_engineering_claim_review_history",
        "engineering_claim_reviews",
        ["claim_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("engineering_claim_reviews")
    op.drop_table("engineering_claims")
