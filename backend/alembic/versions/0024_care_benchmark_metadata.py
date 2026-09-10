"""Add CARE benchmark metadata, structured anomaly provenance, and alarm sources.

Revision ID: 0024_care_benchmark_metadata
Revises: 0023_bounded_weather_selection
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_care_benchmark_metadata"
down_revision: str | None = "0023_bounded_weather_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def _create_dataset_tables() -> None:
    json_type = _json_type()
    op.create_table(
        "benchmark_dataset_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="registered"),
        sa.Column("source_uri", sa.String(1024), nullable=False),
        sa.Column("manifest_uri", sa.String(1024), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("source_archive_md5", sa.String(32)),
        sa.Column("source_archive_sha256", sa.String(64)),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("license_name", sa.String(160), nullable=False),
        sa.Column("license_url", sa.String(1024), nullable=False),
        sa.Column("doi", sa.String(256), nullable=False),
        sa.Column("citation", sa.Text(), nullable=False),
        sa.Column("attribution", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("dataset_id", "version", name="uq_benchmark_dataset_version"),
        sa.UniqueConstraint("content_sha256", name="uq_benchmark_dataset_content_sha256"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_benchmark_dataset_size"),
        sa.CheckConstraint("file_count >= 0", name="ck_benchmark_dataset_file_count"),
    )
    op.create_index(
        "ix_benchmark_dataset_versions_tenant_id",
        "benchmark_dataset_versions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_benchmark_datasets_tenant_status",
        "benchmark_dataset_versions",
        ["tenant_id", "status"],
    )

    op.create_table(
        "benchmark_files",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "dataset_version_id",
            sa.String(64),
            sa.ForeignKey("benchmark_dataset_versions.id"),
            nullable=False,
        ),
        sa.Column("file_kind", sa.String(32), nullable=False),
        sa.Column("relative_path", sa.String(512), nullable=False),
        sa.Column("farm", sa.String(1)),
        sa.Column("event_id", sa.Integer()),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("schema_sha256", sa.String(64), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("metadata", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "dataset_version_id", "relative_path", name="uq_benchmark_file_dataset_path"
        ),
        sa.CheckConstraint(
            "farm IS NULL OR farm IN ('A', 'B', 'C')", name="ck_benchmark_files_farm"
        ),
        sa.CheckConstraint(
            "event_id IS NULL OR (event_id >= 0 AND event_id <= 94)",
            name="ck_benchmark_files_event_id",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_benchmark_files_size"),
        sa.CheckConstraint("row_count >= 0", name="ck_benchmark_files_row_count"),
    )
    op.create_index(
        "ix_benchmark_files_dataset_version_id", "benchmark_files", ["dataset_version_id"]
    )
    op.create_index(
        "ix_benchmark_files_dataset_farm_event",
        "benchmark_files",
        ["dataset_version_id", "farm", "event_id"],
    )

    op.create_table(
        "benchmark_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "dataset_version_id",
            sa.String(64),
            sa.ForeignKey("benchmark_dataset_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "source_file_id",
            sa.String(64),
            sa.ForeignKey("benchmark_files.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("farm", sa.String(1), nullable=False),
        sa.Column("source_asset_id", sa.String(64), nullable=False),
        sa.Column("logical_asset_id", sa.String(64), nullable=False),
        sa.Column("event_label", sa.String(16), nullable=False),
        sa.Column("first_source_row_id", sa.BigInteger(), nullable=False),
        sa.Column("last_source_row_id", sa.BigInteger(), nullable=False),
        sa.Column("train_row_count", sa.BigInteger(), nullable=False),
        sa.Column("prediction_row_count", sa.BigInteger(), nullable=False),
        sa.Column("event_interval_start", sa.BigInteger(), nullable=False),
        sa.Column("event_interval_end", sa.BigInteger(), nullable=False),
        sa.Column(
            "truth_metadata", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "dataset_version_id", "event_id", name="uq_benchmark_event_dataset_event"
        ),
        sa.CheckConstraint("farm IN ('A', 'B', 'C')", name="ck_benchmark_events_farm"),
        sa.CheckConstraint("event_id >= 0 AND event_id <= 94", name="ck_benchmark_events_event_id"),
        sa.CheckConstraint(
            "event_label IN ('anomaly', 'normal')", name="ck_benchmark_events_label"
        ),
        sa.CheckConstraint(
            "first_source_row_id >= 0 AND last_source_row_id >= first_source_row_id",
            name="ck_benchmark_events_row_interval",
        ),
        sa.CheckConstraint(
            "train_row_count >= 0 AND prediction_row_count >= 0",
            name="ck_benchmark_events_split_counts",
        ),
        sa.CheckConstraint(
            "event_interval_start >= 0 AND event_interval_end >= event_interval_start",
            name="ck_benchmark_events_event_interval",
        ),
    )
    op.create_index(
        "ix_benchmark_events_dataset_version_id", "benchmark_events", ["dataset_version_id"]
    )
    op.create_index(
        "ix_benchmark_events_dataset_farm_asset",
        "benchmark_events",
        ["dataset_version_id", "farm", "source_asset_id"],
    )

    op.create_table(
        "benchmark_feature_maps",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "dataset_version_id",
            sa.String(64),
            sa.ForeignKey("benchmark_dataset_versions.id"),
            nullable=False,
        ),
        sa.Column("mapping_version", sa.String(64), nullable=False),
        sa.Column("farm", sa.String(1), nullable=False),
        sa.Column("source_column", sa.String(160), nullable=False),
        sa.Column("canonical_feature", sa.String(160), nullable=False),
        sa.Column("statistic", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("semantics", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "dataset_version_id",
            "mapping_version",
            "farm",
            "source_column",
            name="uq_benchmark_feature_map_source",
        ),
        sa.CheckConstraint("farm IN ('A', 'B', 'C')", name="ck_benchmark_feature_maps_farm"),
    )
    op.create_index(
        "ix_benchmark_feature_maps_dataset_version_id",
        "benchmark_feature_maps",
        ["dataset_version_id"],
    )
    op.create_index(
        "ix_benchmark_feature_maps_enabled",
        "benchmark_feature_maps",
        ["dataset_version_id", "farm", "enabled"],
    )

    op.create_table(
        "benchmark_quality_reports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("event_id", sa.String(64), sa.ForeignKey("benchmark_events.id"), nullable=False),
        sa.Column("quality_rule_version", sa.String(64), nullable=False),
        sa.Column("feature_set_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("artifact_uri", sa.String(1024), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("mask_uri", sa.String(1024), nullable=False),
        sa.Column("mask_sha256", sa.String(64), nullable=False),
        sa.Column("summary", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "event_id",
            "quality_rule_version",
            "feature_set_version",
            name="uq_benchmark_quality_report_identity",
        ),
    )
    op.create_index(
        "ix_benchmark_quality_reports_event_id", "benchmark_quality_reports", ["event_id"]
    )
    op.create_index(
        "ix_benchmark_quality_reports_status_created",
        "benchmark_quality_reports",
        ["status", "created_at"],
    )


def _create_evaluation_tables() -> None:
    json_type = _json_type()
    op.create_unique_constraint(
        "uq_registered_model_id_version", "registered_models", ["id", "version"]
    )
    op.create_table(
        "benchmark_evaluation_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "dataset_version_id",
            sa.String(64),
            sa.ForeignKey("benchmark_dataset_versions.id"),
            nullable=False,
        ),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("run_kind", sa.String(24), nullable=False),
        sa.Column("protocol_version", sa.String(96), nullable=False),
        sa.Column("farm", sa.String(1)),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("feature_set_version", sa.String(64), nullable=False),
        sa.Column("quality_rule_version", sa.String(64), nullable=False),
        sa.Column("threshold_policy_version", sa.String(64), nullable=False),
        sa.Column("threshold_policy_sha256", sa.String(64), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("input_identity_sha256", sa.String(64), nullable=False),
        sa.Column("artifact_uri", sa.String(1024)),
        sa.Column("artifact_sha256", sa.String(64)),
        sa.Column("requested_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scored_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unscorable_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "extension_data", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["model_id", "model_version"],
            ["registered_models.id", "registered_models.version"],
            name="fk_benchmark_evaluation_registered_model_version",
        ),
        sa.UniqueConstraint("input_identity_sha256", name="uq_benchmark_evaluation_input_identity"),
        sa.CheckConstraint(
            "run_kind IN ('development', 'tuning', 'final-holdout')",
            name="ck_benchmark_evaluation_run_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_benchmark_evaluation_status",
        ),
        sa.CheckConstraint(
            "farm IS NULL OR farm IN ('A', 'B', 'C')",
            name="ck_benchmark_evaluation_farm",
        ),
        sa.CheckConstraint(
            "requested_event_count >= 0 AND scored_event_count >= 0 "
            "AND failed_event_count >= 0 AND unscorable_event_count >= 0",
            name="ck_benchmark_evaluation_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR (completed_at IS NOT NULL AND artifact_uri IS NOT NULL "
            "AND length(artifact_sha256) = 64 "
            "AND requested_event_count = scored_event_count + failed_event_count "
            "+ unscorable_event_count)",
            name="ck_benchmark_evaluation_completed",
        ),
    )
    op.create_index(
        "ix_benchmark_evaluation_runs_dataset_version_id",
        "benchmark_evaluation_runs",
        ["dataset_version_id"],
    )
    op.create_index(
        "ix_benchmark_evaluation_dataset_status",
        "benchmark_evaluation_runs",
        ["dataset_version_id", "status"],
    )
    op.create_index(
        "ix_benchmark_evaluation_model_created",
        "benchmark_evaluation_runs",
        ["model_id", "created_at"],
    )

    op.create_table(
        "benchmark_event_results",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "evaluation_run_id",
            sa.String(64),
            sa.ForeignKey("benchmark_evaluation_runs.id"),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(64), sa.ForeignKey("benchmark_events.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("scorable", sa.Boolean(), nullable=False),
        sa.Column("anomaly_detected", sa.Boolean()),
        sa.Column("care_score", sa.Float()),
        sa.Column("coverage_score", sa.Float()),
        sa.Column("accuracy_score", sa.Float()),
        sa.Column("reliability_score", sa.Float()),
        sa.Column("earliness_score", sa.Float()),
        sa.Column("prediction_artifact_uri", sa.String(1024)),
        sa.Column("prediction_artifact_sha256", sa.String(64)),
        sa.Column("failure_code", sa.String(96)),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("details", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "evaluation_run_id", "event_id", name="uq_benchmark_event_result_run_event"
        ),
        sa.UniqueConstraint("result_sha256", name="uq_benchmark_event_result_sha256"),
        sa.CheckConstraint(
            "status IN ('scored', 'failed', 'unscorable')",
            name="ck_benchmark_event_result_status",
        ),
        sa.CheckConstraint(
            "(status = 'scored' AND scorable = TRUE AND care_score IS NOT NULL) OR "
            "(status IN ('failed', 'unscorable') AND scorable = FALSE AND care_score IS NULL)",
            name="ck_benchmark_event_result_score_state",
        ),
    )
    op.create_index(
        "ix_benchmark_event_results_evaluation_run_id",
        "benchmark_event_results",
        ["evaluation_run_id"],
    )
    op.create_index("ix_benchmark_event_results_event_id", "benchmark_event_results", ["event_id"])
    op.create_index(
        "ix_benchmark_event_results_run_status",
        "benchmark_event_results",
        ["evaluation_run_id", "status"],
    )

    op.create_table(
        "benchmark_metric_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "evaluation_run_id",
            sa.String(64),
            sa.ForeignKey("benchmark_evaluation_runs.id"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(96), nullable=False),
        sa.Column("protocol_version", sa.String(96), nullable=False),
        sa.Column("metric_version", sa.String(64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("numerator", sa.Float()),
        sa.Column("denominator", sa.Float()),
        sa.Column("is_release_metric", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("threshold_value", sa.Float()),
        sa.Column("threshold_direction", sa.String(8)),
        sa.Column("passed", sa.Boolean()),
        sa.Column("details", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "metric_name",
            "protocol_version",
            "metric_version",
            name="uq_benchmark_metric_snapshot_identity",
        ),
        sa.CheckConstraint(
            "threshold_direction IS NULL OR threshold_direction IN ('gte', 'lte', 'eq')",
            name="ck_benchmark_metric_threshold_direction",
        ),
        sa.CheckConstraint(
            "is_release_metric = FALSE OR (threshold_value IS NOT NULL "
            "AND threshold_direction IS NOT NULL AND passed IS NOT NULL)",
            name="ck_benchmark_metric_release_structure",
        ),
    )
    op.create_index(
        "ix_benchmark_metric_snapshots_evaluation_run_id",
        "benchmark_metric_snapshots",
        ["evaluation_run_id"],
    )
    op.create_index(
        "ix_benchmark_metric_release",
        "benchmark_metric_snapshots",
        ["evaluation_run_id", "is_release_metric"],
    )


def _create_replay_table() -> None:
    json_type = _json_type()
    op.create_table(
        "benchmark_replay_runs",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column(
            "dataset_version_id",
            sa.String(64),
            sa.ForeignKey("benchmark_dataset_versions.id"),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(64), sa.ForeignKey("benchmark_events.id"), nullable=False),
        sa.Column("source_asset_id", sa.String(64), nullable=False),
        sa.Column("logical_asset_id", sa.String(64), nullable=False),
        sa.Column("online_turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
        sa.Column("farm", sa.String(1), nullable=False),
        sa.Column("source_event_number", sa.Integer(), nullable=False),
        sa.Column("replay_mode", sa.String(32), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("replay_anchor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_rule_version", sa.String(64), nullable=False),
        sa.Column("sequence_rule_version", sa.String(64), nullable=False),
        sa.Column("source_event_id_rule_version", sa.String(64), nullable=False),
        sa.Column(
            "selected_variables", json_type, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("window_start_row_id", sa.BigInteger(), nullable=False),
        sa.Column("window_end_row_id", sa.BigInteger(), nullable=False),
        sa.Column("checkpoint", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("checkpoint_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint_sha256", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(64)),
        sa.Column("model_version", sa.String(64)),
        sa.Column("deployment_id", sa.String(36), sa.ForeignKey("model_deployments.id")),
        sa.Column("threshold_policy_version", sa.String(64)),
        sa.Column("threshold_policy_sha256", sa.String(64)),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_by", sa.String(160)),
        sa.Column("error", sa.Text()),
        sa.ForeignKeyConstraint(
            ["model_id", "model_version"],
            ["registered_models.id", "registered_models.version"],
            name="fk_benchmark_replay_registered_model_version",
        ),
        sa.UniqueConstraint("online_turbine_id", name="uq_benchmark_replay_online_turbine"),
        sa.CheckConstraint("farm IN ('A', 'B', 'C')", name="ck_benchmark_replay_farm"),
        sa.CheckConstraint(
            "source_event_number >= 0 AND source_event_number <= 94",
            name="ck_benchmark_replay_event_number",
        ),
        sa.CheckConstraint(
            "source_event_id_rule_version <> ''", name="ck_benchmark_replay_source_rule"
        ),
        sa.CheckConstraint(
            "replay_mode IN ('live-relative', 'historical-fixed')",
            name="ck_benchmark_replay_mode",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'cancelling', 'cancelled', 'completed', 'failed')",
            name="ck_benchmark_replay_status",
        ),
        sa.CheckConstraint("speed > 0", name="ck_benchmark_replay_speed"),
        sa.CheckConstraint(
            "window_start_row_id >= 0 AND window_end_row_id >= window_start_row_id",
            name="ck_benchmark_replay_window",
        ),
        sa.CheckConstraint(
            "checkpoint_revision >= 0", name="ck_benchmark_replay_checkpoint_revision"
        ),
        sa.CheckConstraint(
            "(model_id IS NULL AND model_version IS NULL) OR "
            "(model_id IS NOT NULL AND model_version IS NOT NULL)",
            name="ck_benchmark_replay_model_identity",
        ),
        sa.CheckConstraint(
            "deployment_id IS NULL OR model_id IS NOT NULL",
            name="ck_benchmark_replay_deployment_model",
        ),
        sa.CheckConstraint(
            "status NOT IN ('cancelled', 'completed', 'failed') OR finished_at IS NOT NULL",
            name="ck_benchmark_replay_terminal_time",
        ),
    )
    op.create_index(
        "ix_benchmark_replay_runs_dataset_version_id",
        "benchmark_replay_runs",
        ["dataset_version_id"],
    )
    op.create_index("ix_benchmark_replay_runs_event_id", "benchmark_replay_runs", ["event_id"])
    op.create_index(
        "ix_benchmark_replay_event_status",
        "benchmark_replay_runs",
        ["event_id", "status"],
    )


def _extend_predictions() -> None:
    columns = (
        sa.Column("prediction_kind", sa.String(24), nullable=False, server_default="predictive"),
        sa.Column("benchmark_replay_run_id", sa.String(8)),
        sa.Column("benchmark_evaluation_run_id", sa.String(64)),
        sa.Column("feature_window_start", sa.DateTime(timezone=True)),
        sa.Column("feature_window_end", sa.DateTime(timezone=True)),
        sa.Column("feature_start_sequence", sa.BigInteger()),
        sa.Column("feature_end_sequence", sa.BigInteger()),
        sa.Column("anomaly_score", sa.Float()),
        sa.Column("binary_prediction", sa.Boolean()),
        sa.Column("component", sa.String(80)),
        sa.Column("threshold_policy_version", sa.String(64)),
        sa.Column("threshold_policy_sha256", sa.String(64)),
        sa.Column("feature_set_version", sa.String(64)),
        sa.Column("quality_rule_version", sa.String(64)),
        sa.Column("evidence_artifact_uri", sa.String(1024)),
        sa.Column("evidence_artifact_sha256", sa.String(64)),
    )
    for column in columns:
        op.add_column("model_predictions", column)

    op.create_foreign_key(
        "fk_model_predictions_benchmark_replay",
        "model_predictions",
        "benchmark_replay_runs",
        ["benchmark_replay_run_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_model_predictions_benchmark_evaluation",
        "model_predictions",
        "benchmark_evaluation_runs",
        ["benchmark_evaluation_run_id"],
        ["id"],
    )
    op.create_index(
        "ix_model_predictions_benchmark_replay_created",
        "model_predictions",
        ["benchmark_replay_run_id", "created_at"],
    )
    op.create_index(
        "ix_model_predictions_benchmark_evaluation_created",
        "model_predictions",
        ["benchmark_evaluation_run_id", "created_at"],
    )

    op.execute(
        sa.text(
            """
            UPDATE model_predictions AS prediction
            SET prediction_kind = CASE
                WHEN model.kind = 'anomaly' THEN 'anomaly'
                ELSE 'predictive'
            END
            FROM registered_models AS model
            WHERE model.id = prediction.model_id
            """
        )
    )
    migration_context = op.get_context()
    if migration_context.dialect.name == "postgresql" and not migration_context.as_sql:
        invalid_count = int(
            op.get_bind().scalar(
                sa.text(
                    """
                    SELECT COUNT(*)
                    FROM model_predictions
                    WHERE prediction_kind = 'anomaly' AND status = 'succeeded' AND (
                        jsonb_typeof(output -> 'anomaly_score') IS DISTINCT FROM 'number'
                        OR jsonb_typeof(output -> 'binary_prediction') IS DISTINCT FROM 'boolean'
                        OR COALESCE(output ->> 'component', '') = ''
                        OR COALESCE(output ->> 'threshold_policy_version', '') = ''
                        OR COALESCE(output ->> 'threshold_policy_sha256', '') !~ '^[0-9a-f]{64}$'
                        OR NOT pg_input_is_valid(
                            COALESCE(output ->> 'feature_window_start', ''),
                            'timestamp with time zone'
                        )
                        OR NOT pg_input_is_valid(
                            COALESCE(output ->> 'feature_window_end', ''),
                            'timestamp with time zone'
                        )
                        OR jsonb_typeof(output -> 'feature_start_sequence')
                            IS DISTINCT FROM 'number'
                        OR jsonb_typeof(output -> 'feature_end_sequence')
                            IS DISTINCT FROM 'number'
                        OR COALESCE(output ->> 'feature_set_version', '') = ''
                        OR COALESCE(output ->> 'quality_rule_version', '') = ''
                        OR COALESCE(output #>> '{evidence_artifact_ref,uri}', '') = ''
                        OR COALESCE(output #>> '{evidence_artifact_ref,sha256}', '')
                            !~ '^[0-9a-f]{64}$'
                    )
                    """
                )
            )
            or 0
        )
        if invalid_count:
            raise RuntimeError(
                "cannot migrate succeeded anomaly predictions without governed structured output"
            )
    if migration_context.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE model_predictions
                SET anomaly_score = (output ->> 'anomaly_score')::double precision,
                    binary_prediction = (output ->> 'binary_prediction')::boolean,
                    component = output ->> 'component',
                    threshold_policy_version = output ->> 'threshold_policy_version',
                    threshold_policy_sha256 = output ->> 'threshold_policy_sha256',
                    feature_window_start = (output ->> 'feature_window_start')::timestamptz,
                    feature_window_end = (output ->> 'feature_window_end')::timestamptz,
                    feature_start_sequence = (output ->> 'feature_start_sequence')::bigint,
                    feature_end_sequence = (output ->> 'feature_end_sequence')::bigint,
                    feature_set_version = output ->> 'feature_set_version',
                    quality_rule_version = output ->> 'quality_rule_version',
                    evidence_artifact_uri = output #>> '{evidence_artifact_ref,uri}',
                    evidence_artifact_sha256 = output #>> '{evidence_artifact_ref,sha256}'
                WHERE prediction_kind = 'anomaly' AND status = 'succeeded'
                """
            )
        )

    op.create_check_constraint(
        "ck_model_predictions_kind",
        "model_predictions",
        "prediction_kind IN ('predictive', 'anomaly')",
    )
    op.create_check_constraint(
        "ck_model_predictions_feature_window",
        "model_predictions",
        "feature_window_start IS NULL OR feature_window_end IS NULL "
        "OR feature_window_start <= feature_window_end",
    )
    op.create_check_constraint(
        "ck_model_predictions_feature_sequence",
        "model_predictions",
        "feature_start_sequence IS NULL OR feature_end_sequence IS NULL "
        "OR feature_start_sequence <= feature_end_sequence",
    )
    op.create_check_constraint(
        "ck_model_predictions_anomaly_score",
        "model_predictions",
        "anomaly_score IS NULL OR (anomaly_score >= 0 AND anomaly_score <= 1)",
    )
    op.create_check_constraint(
        "ck_model_predictions_anomaly_structure",
        "model_predictions",
        "prediction_kind <> 'anomaly' OR status <> 'succeeded' OR ("
        "anomaly_score IS NOT NULL AND binary_prediction IS NOT NULL "
        "AND component IS NOT NULL AND threshold_policy_version IS NOT NULL "
        "AND length(threshold_policy_sha256) = 64 "
        "AND feature_window_start IS NOT NULL AND feature_window_end IS NOT NULL "
        "AND feature_start_sequence IS NOT NULL AND feature_end_sequence IS NOT NULL "
        "AND feature_set_version IS NOT NULL AND quality_rule_version IS NOT NULL "
        "AND evidence_artifact_uri IS NOT NULL AND length(evidence_artifact_sha256) = 64)",
    )
    op.alter_column("model_predictions", "prediction_kind", server_default=None)


def _create_alert_policy_table() -> None:
    json_type = _json_type()
    op.create_table(
        "anomaly_alert_policy_states",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "deployment_id", sa.String(36), sa.ForeignKey("model_deployments.id"), nullable=False
        ),
        sa.Column("turbine_id", sa.String(32), sa.ForeignKey("turbines.id"), nullable=False),
        sa.Column("component", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("policy_sha256", sa.String(64), nullable=False),
        sa.Column("phase", sa.String(24), nullable=False, server_default="normal"),
        sa.Column("consecutive_trigger_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_recovery_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cooldown_until", sa.DateTime(timezone=True)),
        sa.Column("last_prediction_id", sa.String(36), sa.ForeignKey("model_predictions.id")),
        sa.Column("last_prediction_created_at", sa.DateTime(timezone=True)),
        sa.Column("dedup_key", sa.String(128)),
        sa.Column(
            "policy_document", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "state_document", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "deployment_id",
            "turbine_id",
            "component",
            "policy_version",
            name="uq_anomaly_alert_policy_scope",
        ),
        sa.CheckConstraint(
            "phase IN ('normal', 'triggering', 'active', 'recovering', 'cooldown')",
            name="ck_anomaly_alert_policy_phase",
        ),
        sa.CheckConstraint(
            "consecutive_trigger_count >= 0 AND consecutive_recovery_count >= 0 AND revision >= 0",
            name="ck_anomaly_alert_policy_counters",
        ),
    )
    op.create_index(
        "ix_anomaly_alert_policy_states_deployment_id",
        "anomaly_alert_policy_states",
        ["deployment_id"],
    )
    op.create_index(
        "ix_anomaly_alert_policy_states_turbine_id",
        "anomaly_alert_policy_states",
        ["turbine_id"],
    )
    op.create_index(
        "ix_anomaly_alert_policy_phase_updated",
        "anomaly_alert_policy_states",
        ["phase", "updated_at"],
    )


def _extend_alarm_sources() -> None:
    op.add_column("alarms", sa.Column("model_prediction_id", sa.String(36)))
    op.create_foreign_key(
        "fk_alarms_model_prediction",
        "alarms",
        "model_predictions",
        ["model_prediction_id"],
        ["id"],
    )
    op.create_unique_constraint("uq_alarms_model_prediction_id", "alarms", ["model_prediction_id"])
    op.alter_column("alarms", "source_event_id", existing_type=sa.String(128), nullable=True)
    op.create_check_constraint(
        "ck_alarms_has_source",
        "alarms",
        "source_event_id IS NOT NULL OR model_prediction_id IS NOT NULL",
    )


def upgrade() -> None:
    _create_dataset_tables()
    _create_evaluation_tables()
    _create_replay_table()
    _extend_predictions()
    _create_alert_policy_table()
    _extend_alarm_sources()


def downgrade() -> None:
    migration_context = op.get_context()
    if not migration_context.as_sql:
        model_only_alarm_count = int(
            op.get_bind().scalar(
                sa.text(
                    "SELECT COUNT(*) FROM alarms "
                    "WHERE source_event_id IS NULL AND model_prediction_id IS NOT NULL"
                )
            )
            or 0
        )
        if model_only_alarm_count:
            raise RuntimeError(
                "cannot downgrade while model-only alarms exist; "
                "export or remediate provenance first"
            )
    op.drop_constraint("ck_alarms_has_source", "alarms", type_="check")
    op.alter_column("alarms", "source_event_id", existing_type=sa.String(128), nullable=False)
    op.drop_constraint("uq_alarms_model_prediction_id", "alarms", type_="unique")
    op.drop_constraint("fk_alarms_model_prediction", "alarms", type_="foreignkey")
    op.drop_column("alarms", "model_prediction_id")

    op.drop_index("ix_anomaly_alert_policy_phase_updated", table_name="anomaly_alert_policy_states")
    op.drop_index(
        "ix_anomaly_alert_policy_states_turbine_id", table_name="anomaly_alert_policy_states"
    )
    op.drop_index(
        "ix_anomaly_alert_policy_states_deployment_id",
        table_name="anomaly_alert_policy_states",
    )
    op.drop_table("anomaly_alert_policy_states")

    for name in (
        "ck_model_predictions_anomaly_structure",
        "ck_model_predictions_anomaly_score",
        "ck_model_predictions_feature_sequence",
        "ck_model_predictions_feature_window",
        "ck_model_predictions_kind",
    ):
        op.drop_constraint(name, "model_predictions", type_="check")
    op.drop_index(
        "ix_model_predictions_benchmark_evaluation_created", table_name="model_predictions"
    )
    op.drop_index("ix_model_predictions_benchmark_replay_created", table_name="model_predictions")
    op.drop_constraint(
        "fk_model_predictions_benchmark_evaluation",
        "model_predictions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_model_predictions_benchmark_replay", "model_predictions", type_="foreignkey"
    )
    for column_name in (
        "evidence_artifact_sha256",
        "evidence_artifact_uri",
        "quality_rule_version",
        "feature_set_version",
        "threshold_policy_sha256",
        "threshold_policy_version",
        "component",
        "binary_prediction",
        "anomaly_score",
        "feature_end_sequence",
        "feature_start_sequence",
        "feature_window_end",
        "feature_window_start",
        "benchmark_evaluation_run_id",
        "benchmark_replay_run_id",
        "prediction_kind",
    ):
        op.drop_column("model_predictions", column_name)

    op.drop_index("ix_benchmark_replay_event_status", table_name="benchmark_replay_runs")
    op.drop_index("ix_benchmark_replay_runs_event_id", table_name="benchmark_replay_runs")
    op.drop_index("ix_benchmark_replay_runs_dataset_version_id", table_name="benchmark_replay_runs")
    op.drop_table("benchmark_replay_runs")

    op.drop_index("ix_benchmark_metric_release", table_name="benchmark_metric_snapshots")
    op.drop_index(
        "ix_benchmark_metric_snapshots_evaluation_run_id",
        table_name="benchmark_metric_snapshots",
    )
    op.drop_table("benchmark_metric_snapshots")
    op.drop_index("ix_benchmark_event_results_run_status", table_name="benchmark_event_results")
    op.drop_index("ix_benchmark_event_results_event_id", table_name="benchmark_event_results")
    op.drop_index(
        "ix_benchmark_event_results_evaluation_run_id", table_name="benchmark_event_results"
    )
    op.drop_table("benchmark_event_results")
    op.drop_index("ix_benchmark_evaluation_model_created", table_name="benchmark_evaluation_runs")
    op.drop_index("ix_benchmark_evaluation_dataset_status", table_name="benchmark_evaluation_runs")
    op.drop_index(
        "ix_benchmark_evaluation_runs_dataset_version_id",
        table_name="benchmark_evaluation_runs",
    )
    op.drop_table("benchmark_evaluation_runs")
    op.drop_constraint("uq_registered_model_id_version", "registered_models", type_="unique")

    op.drop_index(
        "ix_benchmark_quality_reports_status_created",
        table_name="benchmark_quality_reports",
    )
    op.drop_index("ix_benchmark_quality_reports_event_id", table_name="benchmark_quality_reports")
    op.drop_table("benchmark_quality_reports")
    op.drop_index("ix_benchmark_feature_maps_enabled", table_name="benchmark_feature_maps")
    op.drop_index(
        "ix_benchmark_feature_maps_dataset_version_id", table_name="benchmark_feature_maps"
    )
    op.drop_table("benchmark_feature_maps")
    op.drop_index("ix_benchmark_events_dataset_farm_asset", table_name="benchmark_events")
    op.drop_index("ix_benchmark_events_dataset_version_id", table_name="benchmark_events")
    op.drop_table("benchmark_events")
    op.drop_index("ix_benchmark_files_dataset_farm_event", table_name="benchmark_files")
    op.drop_index("ix_benchmark_files_dataset_version_id", table_name="benchmark_files")
    op.drop_table("benchmark_files")
    op.drop_index("ix_benchmark_datasets_tenant_status", table_name="benchmark_dataset_versions")
    op.drop_index(
        "ix_benchmark_dataset_versions_tenant_id",
        table_name="benchmark_dataset_versions",
    )
    op.drop_table("benchmark_dataset_versions")
