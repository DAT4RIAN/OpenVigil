"""Add versioned hybrid-tower assets, acquisitions and structural analysis.

Revision ID: 0029_hybrid_tower_structural
Revises: 0028_read_audit_pipeline
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_hybrid_tower_structural"
down_revision = "0028_read_audit_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tower_components",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("component_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("revision", sa.String(length=80), nullable=False),
        sa.Column("design_reference", sa.String(length=320), nullable=False),
        sa.Column(
            "geometry", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("wind_farm_id", sa.String(length=36), nullable=False),
        sa.Column("turbine_id", sa.String(length=32), nullable=False),
        sa.CheckConstraint("parent_id IS NULL OR parent_id != id", name="ck_component_parent"),
        sa.ForeignKeyConstraint(["turbine_id"], ["turbines.id"], name=None),
        sa.ForeignKeyConstraint(
            ["parent_id", "turbine_id"],
            ["tower_components.id", "tower_components.turbine_id"],
            name=None,
        ),
        sa.ForeignKeyConstraint(["wind_farm_id"], ["wind_farms.id"], name=None),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=None),
        sa.UniqueConstraint("id", "turbine_id", name="uq_tower_component_asset"),
        sa.UniqueConstraint("turbine_id", "code", "revision", name="uq_tower_component_revision"),
    )
    op.create_index("ix_tower_components_turbine_id", "tower_components", ["turbine_id"])
    op.create_table(
        "waveform_records",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_rate_hz", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column(
            "channel_ids", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column(
            "channel_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("artifact_uri", sa.String(length=1024), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_reference", sa.String(length=320), nullable=False),
        sa.Column(
            "environment", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("wind_farm_id", sa.String(length=36), nullable=False),
        sa.Column("turbine_id", sa.String(length=32), nullable=False),
        sa.CheckConstraint("sample_rate_hz > 0", name="ck_waveform_rate"),
        sa.CheckConstraint("sample_count > 0", name="ck_waveform_samples"),
        sa.CheckConstraint("ended_at > started_at", name="ck_waveform_window"),
        sa.ForeignKeyConstraint(["turbine_id"], ["turbines.id"], name=None),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=None),
        sa.ForeignKeyConstraint(["wind_farm_id"], ["wind_farms.id"], name=None),
        sa.UniqueConstraint("id", "turbine_id", name="uq_waveform_asset"),
        sa.UniqueConstraint("turbine_id", "input_fingerprint", name="uq_waveform_fingerprint"),
    )
    op.create_index("ix_waveform_asset_time", "waveform_records", ["turbine_id", "started_at"])
    op.create_index("ix_waveform_records_turbine_id", "waveform_records", ["turbine_id"])
    op.create_table(
        "structural_analysis_runs",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=80), nullable=False),
        sa.Column(
            "config", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column(
            "algorithm_identity",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "result", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True
        ),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("wind_farm_id", sa.String(length=36), nullable=False),
        sa.Column("turbine_id", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','insufficient_data','failed')",
            name="ck_structural_run_status",
        ),
        sa.ForeignKeyConstraint(["wind_farm_id"], ["wind_farms.id"], name=None),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=None),
        sa.ForeignKeyConstraint(
            ["record_id", "turbine_id"],
            ["waveform_records.id", "waveform_records.turbine_id"],
            name=None,
        ),
        sa.ForeignKeyConstraint(["turbine_id"], ["turbines.id"], name=None),
        sa.UniqueConstraint("id", "turbine_id", name="uq_structural_run_asset"),
        sa.UniqueConstraint(
            "turbine_id", "input_fingerprint", name="uq_structural_run_fingerprint"
        ),
    )
    op.create_index(
        "ix_structural_analysis_runs_turbine_id", "structural_analysis_runs", ["turbine_id"]
    )
    op.create_index(
        "ix_structural_run_asset_time", "structural_analysis_runs", ["turbine_id", "created_at"]
    )
    op.create_table(
        "tendon_assemblies",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("revision", sa.String(length=80), nullable=False),
        sa.Column("component_id", sa.String(length=36), nullable=False),
        sa.Column("effective_length_m", sa.Float(), nullable=True),
        sa.Column("line_density_kg_m", sa.Float(), nullable=True),
        sa.Column(
            "boundary", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("wind_farm_id", sa.String(length=36), nullable=False),
        sa.Column("turbine_id", sa.String(length=32), nullable=False),
        sa.CheckConstraint("line_density_kg_m > 0", name="ck_tendon_density"),
        sa.CheckConstraint("effective_length_m > 0", name="ck_tendon_length"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=None),
        sa.ForeignKeyConstraint(["wind_farm_id"], ["wind_farms.id"], name=None),
        sa.ForeignKeyConstraint(
            ["component_id", "turbine_id"],
            ["tower_components.id", "tower_components.turbine_id"],
            name=None,
        ),
        sa.ForeignKeyConstraint(["turbine_id"], ["turbines.id"], name=None),
        sa.UniqueConstraint("id", "turbine_id", name="uq_tendon_asset"),
        sa.UniqueConstraint("turbine_id", "code", "revision", name="uq_tendon_revision"),
    )
    op.create_index("ix_tendon_assemblies_turbine_id", "tendon_assemblies", ["turbine_id"])
    op.create_table(
        "modal_observations",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("mode_index", sa.Integer(), nullable=False),
        sa.Column("frequency_hz", sa.Float(), nullable=False),
        sa.Column(
            "mode_shape", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column(
            "quality", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column(
            "uncertainty", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("wind_farm_id", sa.String(length=36), nullable=False),
        sa.Column("turbine_id", sa.String(length=32), nullable=False),
        sa.CheckConstraint("frequency_hz > 0", name="ck_modal_frequency"),
        sa.ForeignKeyConstraint(["wind_farm_id"], ["wind_farms.id"], name=None),
        sa.ForeignKeyConstraint(["turbine_id"], ["turbines.id"], name=None),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=None),
        sa.ForeignKeyConstraint(
            ["run_id", "turbine_id"],
            ["structural_analysis_runs.id", "structural_analysis_runs.turbine_id"],
            name=None,
        ),
        sa.UniqueConstraint("id", "turbine_id", name="uq_modal_asset"),
        sa.UniqueConstraint("run_id", "mode_index", name="uq_modal_run_mode"),
    )
    op.create_index("ix_modal_observations_turbine_id", "modal_observations", ["turbine_id"])
    op.create_table(
        "sensor_channels",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("revision", sa.String(length=80), nullable=False),
        sa.Column("component_id", sa.String(length=36), nullable=False),
        sa.Column("tendon_id", sa.String(length=36), nullable=True),
        sa.Column("quantity", sa.String(length=32), nullable=False),
        sa.Column("unit", sa.String(length=24), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("range_min", sa.Float(), nullable=False),
        sa.Column("range_max", sa.Float(), nullable=False),
        sa.Column("calibration_version", sa.String(length=80), nullable=False),
        sa.Column("calibration_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calibration_valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calibration_reference", sa.String(length=320), nullable=False),
        sa.Column("synchronization_source", sa.String(length=160), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("wind_farm_id", sa.String(length=36), nullable=False),
        sa.Column("turbine_id", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "calibration_valid_until > calibration_at", name="ck_sensor_calibration"
        ),
        sa.CheckConstraint("range_max > range_min", name="ck_sensor_range"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=None),
        sa.ForeignKeyConstraint(
            ["component_id", "turbine_id"],
            ["tower_components.id", "tower_components.turbine_id"],
            name=None,
        ),
        sa.ForeignKeyConstraint(["turbine_id"], ["turbines.id"], name=None),
        sa.ForeignKeyConstraint(
            ["tendon_id", "turbine_id"],
            ["tendon_assemblies.id", "tendon_assemblies.turbine_id"],
            name=None,
        ),
        sa.ForeignKeyConstraint(["wind_farm_id"], ["wind_farms.id"], name=None),
        sa.UniqueConstraint("id", "turbine_id", name="uq_sensor_asset"),
        sa.UniqueConstraint("turbine_id", "code", "revision", name="uq_sensor_revision"),
    )
    op.create_index("ix_sensor_channels_turbine_id", "sensor_channels", ["turbine_id"])
    op.create_table(
        "health_baselines",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("component_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("revision", sa.String(length=80), nullable=False),
        sa.Column("confirmation_reference", sa.String(length=320), nullable=False),
        sa.Column("reference_modal_id", sa.String(length=36), nullable=False),
        sa.Column(
            "training_modal_ids",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "model", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("wind_farm_id", sa.String(length=36), nullable=False),
        sa.Column("turbine_id", sa.String(length=32), nullable=False),
        sa.CheckConstraint("valid_until > created_at", name="ck_baseline_expiry"),
        sa.ForeignKeyConstraint(["wind_farm_id"], ["wind_farms.id"], name=None),
        sa.ForeignKeyConstraint(["turbine_id"], ["turbines.id"], name=None),
        sa.ForeignKeyConstraint(
            ["component_id", "turbine_id"],
            ["tower_components.id", "tower_components.turbine_id"],
            name=None,
        ),
        sa.ForeignKeyConstraint(
            ["reference_modal_id", "turbine_id"],
            ["modal_observations.id", "modal_observations.turbine_id"],
            name=None,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=None),
        sa.UniqueConstraint("turbine_id", "code", "revision", name="uq_health_baseline_revision"),
    )
    op.create_index("ix_baseline_asset_time", "health_baselines", ["turbine_id", "created_at"])
    op.create_index("ix_health_baselines_turbine_id", "health_baselines", ["turbine_id"])
    op.create_table(
        "prestress_observations",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("tendon_id", sa.String(length=36), nullable=False),
        sa.Column("sensor_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value_kn", sa.Float(), nullable=False),
        sa.Column("calibration_version", sa.String(length=80), nullable=False),
        sa.Column("artifact_uri", sa.String(length=1024), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "uncertainty", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("wind_farm_id", sa.String(length=36), nullable=False),
        sa.Column("turbine_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["turbine_id"], ["turbines.id"], name=None),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=None),
        sa.ForeignKeyConstraint(
            ["tendon_id", "turbine_id"],
            ["tendon_assemblies.id", "tendon_assemblies.turbine_id"],
            name=None,
        ),
        sa.ForeignKeyConstraint(["wind_farm_id"], ["wind_farms.id"], name=None),
        sa.ForeignKeyConstraint(
            ["sensor_id", "turbine_id"],
            ["sensor_channels.id", "sensor_channels.turbine_id"],
            name=None,
        ),
        sa.UniqueConstraint("turbine_id", "input_fingerprint", name="uq_prestress_fingerprint"),
    )
    op.create_index(
        "ix_prestress_observations_turbine_id", "prestress_observations", ["turbine_id"]
    )
    op.create_index(
        "ix_prestress_tendon_time", "prestress_observations", ["tendon_id", "observed_at"]
    )


def downgrade() -> None:
    op.drop_table("prestress_observations")
    op.drop_table("health_baselines")
    op.drop_table("sensor_channels")
    op.drop_table("modal_observations")
    op.drop_table("tendon_assemblies")
    op.drop_table("structural_analysis_runs")
    op.drop_table("waveform_records")
    op.drop_table("tower_components")
