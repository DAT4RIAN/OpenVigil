"""Add governed model artifacts, deployments, routing, and inference ledger.

Revision ID: 0010_model_runtime
Revises: 0009_knowledge_ingestion
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_model_runtime"
down_revision: str | None = "0009_knowledge_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "registered_models",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="registered"),
        sa.Column("artifact_uri", sa.String(1024), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("content_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("input_schema", json_type, nullable=False),
        sa.Column("output_schema", json_type, nullable=False),
        sa.Column("metrics", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("name", "version", name="uq_registered_model_name_version"),
    )
    op.create_index("ix_registered_models_kind_status", "registered_models", ["kind", "status"])
    op.create_table(
        "model_deployments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_id", sa.String(64), sa.ForeignKey("registered_models.id"), nullable=False),
        sa.Column("target_id", sa.String(96), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False, server_default="production"),
        sa.Column("status", sa.String(24), nullable=False, server_default="staged"),
        sa.Column("traffic_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "evaluation_gate", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("rollback_from_id", sa.String(36)),
        sa.Column("deployed_by", sa.String(160), nullable=False),
        sa.Column(
            "deployed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_model_deployments_model_id", "model_deployments", ["model_id"])
    op.create_index(
        "ix_model_deployments_model_status", "model_deployments", ["model_id", "status"]
    )
    op.create_index("ix_model_deployments_stage_status", "model_deployments", ["stage", "status"])
    op.create_table(
        "model_predictions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_id", sa.String(64), sa.ForeignKey("registered_models.id"), nullable=False),
        sa.Column(
            "deployment_id", sa.String(36), sa.ForeignKey("model_deployments.id"), nullable=False
        ),
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
        sa.Column("feature_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("input_snapshot", json_type, nullable=False),
        sa.Column("output", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(96)),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "deployment_id",
            "turbine_id",
            "feature_observed_at",
            name="uq_prediction_deployment_turbine_features",
        ),
    )
    op.create_index("ix_model_predictions_model_id", "model_predictions", ["model_id"])
    op.create_index("ix_model_predictions_deployment_id", "model_predictions", ["deployment_id"])
    op.create_index("ix_model_predictions_turbine_id", "model_predictions", ["turbine_id"])
    op.create_index(
        "ix_model_predictions_turbine_created",
        "model_predictions",
        ["turbine_id", "created_at"],
    )
    op.create_index(
        "ix_model_predictions_deployment_created",
        "model_predictions",
        ["deployment_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("model_predictions")
    op.drop_table("model_deployments")
    op.drop_table("registered_models")
