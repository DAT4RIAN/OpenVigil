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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from windops_backend.model_base import JSON_VALUE, Base, utcnow


class RegisteredModel(Base):
    """Immutable, content-addressed model package and its governed contracts."""

    __tablename__ = "registered_models"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_registered_model_name_version"),
        UniqueConstraint("id", "version", name="uq_registered_model_id_version"),
        Index("ix_registered_models_kind_status", "kind", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="registered")
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    content_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelDeployment(Base):
    """Auditable routing state; endpoints and credentials remain external configuration."""

    __tablename__ = "model_deployments"
    __table_args__ = (
        Index("ix_model_deployments_model_status", "model_id", "status"),
        Index("ix_model_deployments_stage_status", "stage", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(
        ForeignKey("registered_models.id"), nullable=False, index=True
    )
    target_id: Mapped[str] = mapped_column(String(96), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="production")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="staged")
    traffic_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluation_gate: Mapped[dict[str, Any]] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    rollback_from_id: Mapped[str | None] = mapped_column(String(36))
    deployed_by: Mapped[str] = mapped_column(String(160), nullable=False)
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelPrediction(Base):
    """Immutable inference ledger used by predictive views and model monitoring."""

    __tablename__ = "model_predictions"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "turbine_id",
            "feature_observed_at",
            name="uq_prediction_deployment_turbine_features",
        ),
        Index("ix_model_predictions_turbine_created", "turbine_id", "created_at"),
        Index("ix_model_predictions_deployment_created", "deployment_id", "created_at"),
        Index(
            "ix_model_predictions_benchmark_replay_created",
            "benchmark_replay_run_id",
            "created_at",
        ),
        Index(
            "ix_model_predictions_benchmark_evaluation_created",
            "benchmark_evaluation_run_id",
            "created_at",
        ),
        CheckConstraint(
            "prediction_kind IN ('predictive', 'anomaly')",
            name="ck_model_predictions_kind",
        ),
        CheckConstraint(
            "feature_window_start IS NULL OR feature_window_end IS NULL "
            "OR feature_window_start <= feature_window_end",
            name="ck_model_predictions_feature_window",
        ),
        CheckConstraint(
            "feature_start_sequence IS NULL OR feature_end_sequence IS NULL "
            "OR feature_start_sequence <= feature_end_sequence",
            name="ck_model_predictions_feature_sequence",
        ),
        CheckConstraint(
            "anomaly_score IS NULL OR (anomaly_score >= 0 AND anomaly_score <= 1)",
            name="ck_model_predictions_anomaly_score",
        ),
        CheckConstraint(
            "prediction_kind <> 'anomaly' OR status <> 'succeeded' OR ("
            "anomaly_score IS NOT NULL AND binary_prediction IS NOT NULL "
            "AND component IS NOT NULL AND threshold_policy_version IS NOT NULL "
            "AND length(threshold_policy_sha256) = 64 "
            "AND feature_window_start IS NOT NULL AND feature_window_end IS NOT NULL "
            "AND feature_start_sequence IS NOT NULL AND feature_end_sequence IS NOT NULL "
            "AND feature_set_version IS NOT NULL AND quality_rule_version IS NOT NULL "
            "AND evidence_artifact_uri IS NOT NULL "
            "AND length(evidence_artifact_sha256) = 64)",
            name="ck_model_predictions_anomaly_structure",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(
        ForeignKey("registered_models.id"), nullable=False, index=True
    )
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("model_deployments.id"), nullable=False, index=True
    )
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.id"), nullable=False, index=True)
    feature_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prediction_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="predictive")
    benchmark_replay_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("benchmark_replay_runs.id"), nullable=True
    )
    benchmark_evaluation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("benchmark_evaluation_runs.id"), nullable=True
    )
    feature_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feature_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feature_start_sequence: Mapped[int | None] = mapped_column(BigInteger)
    feature_end_sequence: Mapped[int | None] = mapped_column(BigInteger)
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    binary_prediction: Mapped[bool | None] = mapped_column(Boolean)
    component: Mapped[str | None] = mapped_column(String(80))
    threshold_policy_version: Mapped[str | None] = mapped_column(String(64))
    threshold_policy_sha256: Mapped[str | None] = mapped_column(String(64))
    feature_set_version: Mapped[str | None] = mapped_column(String(64))
    quality_rule_version: Mapped[str | None] = mapped_column(String(64))
    evidence_artifact_uri: Mapped[str | None] = mapped_column(String(1024))
    evidence_artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(96))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
