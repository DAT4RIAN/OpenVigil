"""Create the production WT-023 operational vertical slice.

Revision ID: 0001_wt023
Revises: None
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_wt023"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # These extensions are mandatory production capabilities, not test emulation.
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "wind_farms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("capacity_mw", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "turbines",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("wind_farm_id", sa.String(36), sa.ForeignKey("wind_farms.id"), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("health_score", sa.Float(), nullable=False, server_default="96"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ingest_receipts",
        sa.Column("source_event_id", sa.String(128), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "scada_samples",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source_event_id",
            sa.String(128),
            sa.ForeignKey("ingest_receipts.source_event_id"),
            nullable=False,
        ),
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
        sa.Column("variable", sa.String(96), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("quality", sa.String(24), nullable=False, server_default="good"),
        sa.Column("attributes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id", "observed_at", name="pk_scada_samples"),
    )
    op.create_index("ix_scada_samples_source_event_id", "scada_samples", ["source_event_id"])
    op.create_index(
        "ix_scada_turbine_variable_observed",
        "scada_samples",
        ["turbine_id", "variable", sa.text("observed_at DESC")],
    )
    op.execute(
        "SELECT create_hypertable('scada_samples', 'observed_at', "
        "if_not_exists => TRUE, migrate_data => TRUE)"
    )

    op.create_table(
        "alarms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
        sa.Column(
            "source_event_id",
            sa.String(128),
            sa.ForeignKey("ingest_receipts.source_event_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("subsystem", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False, server_default="major"),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("ai_status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_alarms_turbine_id", "alarms", ["turbine_id"])
    op.create_table(
        "missions",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "alarm_id",
            sa.String(36),
            sa.ForeignKey("alarms.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="detected"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("public_state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_missions_turbine_id", "missions", ["turbine_id"])
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("document_type", sa.String(64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("citation_uri", sa.String(320), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("vectorized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_knowledge_documents_embedding_hnsw",
        "knowledge_documents",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "resources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="available"),
    )
    op.create_table(
        "weather_windows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("wind_farm_id", sa.String(36), sa.ForeignKey("wind_farms.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("wind_speed_ms", sa.Float(), nullable=False),
        sa.Column("wave_height_m", sa.Float(), nullable=False),
        sa.Column("suitable", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "agent_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(40), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("node", sa.String(64), nullable=False),
        sa.Column("agent_role", sa.String(96), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="running"),
        sa.Column("input_refs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("public_output", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(96)),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_agent_execution_mission_started",
        "agent_executions",
        ["mission_id", "started_at"],
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(40), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("mission_revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("approver", sa.String(160), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("mission_id", "mission_revision", name="uq_approval_mission_revision"),
    )
    op.create_index("ix_approvals_mission_id", "approvals", ["mission_id"])
    op.create_table(
        "work_orders",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "mission_id",
            sa.String(40),
            sa.ForeignKey("missions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "approval_id",
            sa.String(36),
            sa.ForeignKey("approvals.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="scheduled"),
        sa.Column("priority", sa.String(24), nullable=False, server_default="high"),
        sa.Column("assigned_team", sa.String(160), nullable=False),
        sa.Column("created_by", sa.String(96), nullable=False, server_default="work_order_agent"),
        sa.Column("safety_plan", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_work_orders_turbine_id", "work_orders", ["turbine_id"])
    op.create_table(
        "work_order_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("work_order_id", sa.String(40), sa.ForeignKey("work_orders.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("result", sa.Text()),
        sa.Column("completed_by", sa.String(160)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("work_order_id", "sequence", name="uq_work_order_task_sequence"),
    )
    op.create_index("ix_work_order_tasks_work_order_id", "work_order_tasks", ["work_order_id"])
    op.create_table(
        "asset_health_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
        sa.Column("mission_id", sa.String(40), sa.ForeignKey("missions.id")),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_asset_health_events_turbine_id", "asset_health_events", ["turbine_id"])
    op.create_table(
        "knowledge_cases",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "mission_id",
            sa.String(40),
            sa.ForeignKey("missions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "work_order_id",
            sa.String(40),
            sa.ForeignKey("work_orders.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("diagnosis", JSONB, nullable=False),
        sa.Column("resolution", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_cases_turbine_id", "knowledge_cases", ["turbine_id"])
    op.create_table(
        "resource_reservations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(40), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("resource_id", sa.String(64), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("mission_id", "resource_id", name="uq_reservation_mission_resource"),
    )


def downgrade() -> None:
    op.drop_table("resource_reservations")
    op.drop_index("ix_knowledge_cases_turbine_id", table_name="knowledge_cases")
    op.drop_table("knowledge_cases")
    op.drop_index("ix_asset_health_events_turbine_id", table_name="asset_health_events")
    op.drop_table("asset_health_events")
    op.drop_index("ix_work_order_tasks_work_order_id", table_name="work_order_tasks")
    op.drop_table("work_order_tasks")
    op.drop_index("ix_work_orders_turbine_id", table_name="work_orders")
    op.drop_table("work_orders")
    op.drop_index("ix_approvals_mission_id", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_agent_execution_mission_started", table_name="agent_executions")
    op.drop_table("agent_executions")
    op.drop_table("weather_windows")
    op.drop_table("resources")
    op.drop_index("ix_knowledge_documents_embedding_hnsw", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("ix_missions_turbine_id", table_name="missions")
    op.drop_table("missions")
    op.drop_index("ix_alarms_turbine_id", table_name="alarms")
    op.drop_table("alarms")
    op.drop_index("ix_scada_turbine_variable_observed", table_name="scada_samples")
    op.drop_index("ix_scada_samples_source_event_id", table_name="scada_samples")
    op.drop_table("scada_samples")
    op.drop_table("ingest_receipts")
    op.drop_table("turbines")
    op.drop_table("wind_farms")
    # Extensions are shared cluster capabilities and are intentionally retained.
