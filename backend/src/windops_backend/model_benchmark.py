from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.model_base import JSON_VALUE, Base, utcnow


class BenchmarkDatasetVersion(Base):
    """Immutable identity and licensing boundary for one benchmark dataset release."""

    __tablename__ = "benchmark_dataset_versions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version", name="uq_benchmark_dataset_version"),
        UniqueConstraint("content_sha256", name="uq_benchmark_dataset_content_sha256"),
        Index("ix_benchmark_datasets_tenant_status", "tenant_id", "status"),
        CheckConstraint("size_bytes >= 0", name="ck_benchmark_dataset_size"),
        CheckConstraint("file_count >= 0", name="ck_benchmark_dataset_file_count"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="registered")
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    manifest_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_archive_md5: Mapped[str | None] = mapped_column(String(32))
    source_archive_sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    license_name: Mapped[str] = mapped_column(String(160), nullable=False)
    license_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    doi: Mapped[str] = mapped_column(String(256), nullable=False)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    attribution: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkFile(Base):
    __tablename__ = "benchmark_files"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id", "relative_path", name="uq_benchmark_file_dataset_path"
        ),
        Index("ix_benchmark_files_dataset_farm_event", "dataset_version_id", "farm", "event_id"),
        CheckConstraint("farm IS NULL OR farm IN ('A', 'B', 'C')", name="ck_benchmark_files_farm"),
        CheckConstraint(
            "event_id IS NULL OR (event_id >= 0 AND event_id <= 94)",
            name="ck_benchmark_files_event_id",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_benchmark_files_size"),
        CheckConstraint("row_count >= 0", name="ck_benchmark_files_row_count"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_dataset_versions.id"), nullable=False, index=True
    )
    file_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    farm: Mapped[str | None] = mapped_column(String(1))
    event_id: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    schema_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkEvent(Base):
    __tablename__ = "benchmark_events"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "event_id", name="uq_benchmark_event_dataset_event"),
        Index(
            "ix_benchmark_events_dataset_farm_asset",
            "dataset_version_id",
            "farm",
            "source_asset_id",
        ),
        CheckConstraint("farm IN ('A', 'B', 'C')", name="ck_benchmark_events_farm"),
        CheckConstraint("event_id >= 0 AND event_id <= 94", name="ck_benchmark_events_event_id"),
        CheckConstraint("event_label IN ('anomaly', 'normal')", name="ck_benchmark_events_label"),
        CheckConstraint(
            "first_source_row_id >= 0 AND last_source_row_id >= first_source_row_id",
            name="ck_benchmark_events_row_interval",
        ),
        CheckConstraint(
            "train_row_count >= 0 AND prediction_row_count >= 0",
            name="ck_benchmark_events_split_counts",
        ),
        CheckConstraint(
            "event_interval_start >= 0 AND event_interval_end >= event_interval_start",
            name="ck_benchmark_events_event_interval",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_dataset_versions.id"), nullable=False, index=True
    )
    source_file_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_files.id"), nullable=False, unique=True
    )
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    farm: Mapped[str] = mapped_column(String(1), nullable=False)
    source_asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_label: Mapped[str] = mapped_column(String(16), nullable=False)
    first_source_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_source_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    train_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prediction_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_interval_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_interval_end: Mapped[int] = mapped_column(BigInteger, nullable=False)
    truth_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkFeatureMap(Base):
    __tablename__ = "benchmark_feature_maps"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id",
            "mapping_version",
            "farm",
            "source_column",
            name="uq_benchmark_feature_map_source",
        ),
        Index("ix_benchmark_feature_maps_enabled", "dataset_version_id", "farm", "enabled"),
        CheckConstraint("farm IN ('A', 'B', 'C')", name="ck_benchmark_feature_maps_farm"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_dataset_versions.id"), nullable=False, index=True
    )
    mapping_version: Mapped[str] = mapped_column(String(64), nullable=False)
    farm: Mapped[str] = mapped_column(String(1), nullable=False)
    source_column: Mapped[str] = mapped_column(String(160), nullable=False)
    canonical_feature: Mapped[str] = mapped_column(String(160), nullable=False)
    statistic: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    semantics: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkQualityReport(Base):
    __tablename__ = "benchmark_quality_reports"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "quality_rule_version",
            "feature_set_version",
            name="uq_benchmark_quality_report_identity",
        ),
        Index("ix_benchmark_quality_reports_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_events.id"), nullable=False, index=True
    )
    quality_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_content_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mask_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    mask_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkQualityArtifact(Base):
    __tablename__ = "benchmark_quality_artifacts"
    __table_args__ = (
        UniqueConstraint("identity_sha256", name="uq_benchmark_quality_artifact_identity"),
        Index(
            "ix_benchmark_quality_artifacts_report_created",
            "quality_report_id",
            "created_at",
        ),
        Index(
            "ix_benchmark_quality_artifacts_stage_created",
            "artifact_stage",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    quality_report_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_quality_reports.id"), nullable=False, index=True
    )
    artifact_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mask_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    mask_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    audit_subject: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkEvaluationRun(Base):
    __tablename__ = "benchmark_evaluation_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["model_id", "model_version"],
            ["registered_models.id", "registered_models.version"],
            name="fk_benchmark_evaluation_registered_model_version",
        ),
        UniqueConstraint("input_identity_sha256", name="uq_benchmark_evaluation_input_identity"),
        Index("ix_benchmark_evaluation_dataset_status", "dataset_version_id", "status"),
        Index("ix_benchmark_evaluation_model_created", "model_id", "created_at"),
        CheckConstraint(
            "run_kind IN ('development', 'tuning', 'final-holdout')",
            name="ck_benchmark_evaluation_run_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_benchmark_evaluation_status",
        ),
        CheckConstraint(
            "farm IS NULL OR farm IN ('A', 'B', 'C')", name="ck_benchmark_evaluation_farm"
        ),
        CheckConstraint(
            "requested_event_count >= 0 AND scored_event_count >= 0 "
            "AND failed_event_count >= 0 AND unscorable_event_count >= 0",
            name="ck_benchmark_evaluation_counts_nonnegative",
        ),
        CheckConstraint(
            "status <> 'completed' OR (completed_at IS NOT NULL AND artifact_uri IS NOT NULL "
            "AND length(artifact_sha256) = 64 "
            "AND requested_event_count = scored_event_count + failed_event_count "
            "+ unscorable_event_count)",
            name="ck_benchmark_evaluation_completed",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_dataset_versions.id"), nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    run_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(96), nullable=False)
    farm: Mapped[str | None] = mapped_column(String(1))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    input_identity_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_uri: Mapped[str | None] = mapped_column(String(1024))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    requested_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scored_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unscorable_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extension_data: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BenchmarkEventResult(Base):
    __tablename__ = "benchmark_event_results"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id", "event_id", name="uq_benchmark_event_result_run_event"
        ),
        UniqueConstraint("result_sha256", name="uq_benchmark_event_result_sha256"),
        Index("ix_benchmark_event_results_run_status", "evaluation_run_id", "status"),
        CheckConstraint(
            "status IN ('scored', 'failed', 'unscorable')",
            name="ck_benchmark_event_result_status",
        ),
        CheckConstraint(
            "(status = 'scored' AND scorable = TRUE) OR "
            "(status IN ('failed', 'unscorable') AND scorable = FALSE AND care_score IS NULL)",
            name="ck_benchmark_event_result_score_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_evaluation_runs.id"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_events.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    scorable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    anomaly_detected: Mapped[bool | None] = mapped_column(Boolean)
    care_score: Mapped[float | None] = mapped_column(Float)
    coverage_score: Mapped[float | None] = mapped_column(Float)
    accuracy_score: Mapped[float | None] = mapped_column(Float)
    reliability_score: Mapped[float | None] = mapped_column(Float)
    earliness_score: Mapped[float | None] = mapped_column(Float)
    prediction_artifact_uri: Mapped[str | None] = mapped_column(String(1024))
    prediction_artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(96))
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkMetricSnapshot(Base):
    __tablename__ = "benchmark_metric_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id",
            "metric_name",
            "protocol_version",
            "metric_version",
            name="uq_benchmark_metric_snapshot_identity",
        ),
        Index("ix_benchmark_metric_release", "evaluation_run_id", "is_release_metric"),
        CheckConstraint(
            "threshold_direction IS NULL OR threshold_direction IN ('gte', 'lte', 'eq')",
            name="ck_benchmark_metric_threshold_direction",
        ),
        CheckConstraint(
            "is_release_metric = FALSE OR (threshold_value IS NOT NULL "
            "AND threshold_direction IS NOT NULL AND passed IS NOT NULL)",
            name="ck_benchmark_metric_release_structure",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_evaluation_runs.id"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(96), nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(96), nullable=False)
    metric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    numerator: Mapped[float | None] = mapped_column(Float)
    denominator: Mapped[float | None] = mapped_column(Float)
    is_release_metric: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    threshold_value: Mapped[float | None] = mapped_column(Float)
    threshold_direction: Mapped[str | None] = mapped_column(String(8))
    passed: Mapped[bool | None] = mapped_column(Boolean)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkReplayRun(Base):
    __tablename__ = "benchmark_replay_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["model_id", "model_version"],
            ["registered_models.id", "registered_models.version"],
            name="fk_benchmark_replay_registered_model_version",
        ),
        UniqueConstraint("online_turbine_id", name="uq_benchmark_replay_online_turbine"),
        Index("ix_benchmark_replay_event_status", "event_id", "status"),
        CheckConstraint("farm IN ('A', 'B', 'C')", name="ck_benchmark_replay_farm"),
        CheckConstraint(
            "source_event_number >= 0 AND source_event_number <= 94",
            name="ck_benchmark_replay_event_number",
        ),
        CheckConstraint(
            "source_event_id_rule_version <> ''", name="ck_benchmark_replay_source_rule"
        ),
        CheckConstraint(
            "replay_mode IN ('live-relative', 'historical-fixed')",
            name="ck_benchmark_replay_mode",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'cancelling', 'cancelled', 'completed', 'failed')",
            name="ck_benchmark_replay_status",
        ),
        CheckConstraint("speed > 0", name="ck_benchmark_replay_speed"),
        CheckConstraint(
            "window_start_row_id >= 0 AND window_end_row_id >= window_start_row_id",
            name="ck_benchmark_replay_window",
        ),
        CheckConstraint("checkpoint_revision >= 0", name="ck_benchmark_replay_checkpoint_revision"),
        CheckConstraint(
            "(model_id IS NULL AND model_version IS NULL) OR "
            "(model_id IS NOT NULL AND model_version IS NOT NULL)",
            name="ck_benchmark_replay_model_identity",
        ),
        CheckConstraint(
            "deployment_id IS NULL OR model_id IS NOT NULL",
            name="ck_benchmark_replay_deployment_model",
        ),
        CheckConstraint(
            "status NOT IN ('cancelled', 'completed', 'failed') OR finished_at IS NOT NULL",
            name="ck_benchmark_replay_terminal_time",
        ),
    )

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_dataset_versions.id"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_events.id"), nullable=False, index=True
    )
    source_asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    online_turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False)
    farm: Mapped[str] = mapped_column(String(1), nullable=False)
    source_event_number: Mapped[int] = mapped_column(Integer, nullable=False)
    replay_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    speed: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    replay_anchor_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_variables: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    window_start_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    window_end_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    checkpoint_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkpoint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(64))
    deployment_id: Mapped[str | None] = mapped_column(ForeignKey("model_deployments.id"))
    threshold_policy_version: Mapped[str | None] = mapped_column(String(64))
    threshold_policy_sha256: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[str | None] = mapped_column(String(160))
    error: Mapped[str | None] = mapped_column(Text)


class AnomalyAlertPolicyState(Base):
    __tablename__ = "anomaly_alert_policy_states"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "turbine_id",
            "component",
            "policy_version",
            name="uq_anomaly_alert_policy_scope",
        ),
        Index("ix_anomaly_alert_policy_phase_updated", "phase", "updated_at"),
        CheckConstraint(
            "phase IN ('normal', 'triggering', 'active', 'recovering', 'cooldown')",
            name="ck_anomaly_alert_policy_phase",
        ),
        CheckConstraint(
            "consecutive_trigger_count >= 0 AND consecutive_recovery_count >= 0 AND revision >= 0",
            name="ck_anomaly_alert_policy_counters",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("model_deployments.id"), nullable=False, index=True
    )
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    component: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(24), nullable=False, default="normal")
    consecutive_trigger_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_recovery_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_prediction_id: Mapped[str | None] = mapped_column(ForeignKey("model_predictions.id"))
    last_prediction_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedup_key: Mapped[str | None] = mapped_column(String(128))
    policy_document: Mapped[dict[str, Any]] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    state_document: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
