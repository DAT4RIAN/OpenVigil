from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.access_control import turbine_scope_clause
from windops_backend.benchmarks.care.replay import CARE_REPLAY_SOURCE_ID
from windops_backend.errors import NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    Alarm,
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkEvent,
    BenchmarkEventResult,
    BenchmarkMetricSnapshot,
    BenchmarkQualityReport,
    BenchmarkReplayRun,
    Mission,
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
    ScadaSample,
)
from windops_backend.services.benchmark_catalog_policy import (
    BENCHMARK_DEPLOYMENTS_PER_MODEL_MAX,
    BENCHMARK_DIAGNOSIS_PAGE_MAX,
    BENCHMARK_EVALUATION_METRICS_MAX,
    BENCHMARK_EVALUATION_PAGE_MAX,
    BENCHMARK_EVENT_RESULT_PAGE_MAX,
    BENCHMARK_PREDICTIONS_PER_REPLAY_MAX,
    BENCHMARK_SIGNAL_SUMMARY_MAX,
    benchmark_dataset_scope_clause,
    benchmark_domains_allowed,
    benchmark_truth_allowed,
)


def _safe_document(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _evaluation_gate_reasons(
    evaluation: BenchmarkEvaluationRun,
    model: RegisteredModel,
    metrics: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if model.kind != "anomaly":
        reasons.append("MODEL_KIND_NOT_ANOMALY")
    if evaluation.status != "completed":
        reasons.append("EVALUATION_NOT_COMPLETED")
    if evaluation.invalidated_at is not None:
        reasons.append("EVALUATION_INVALIDATED")
    if not evaluation.artifact_uri or not evaluation.artifact_sha256:
        reasons.append("EVALUATION_ARTIFACT_MISSING")
    if evaluation.requested_event_count != (
        evaluation.scored_event_count
        + evaluation.failed_event_count
        + evaluation.unscorable_event_count
    ):
        reasons.append("EVENT_ACCOUNTING_INCOMPLETE")
    if evaluation.failed_event_count:
        reasons.append("FAILED_EVENTS_PRESENT")
    if evaluation.unscorable_event_count:
        reasons.append("UNSCORABLE_EVENTS_PRESENT")
    release_metrics = [metric for metric in metrics if metric["is_release_metric"]]
    if not release_metrics:
        reasons.append("RELEASE_METRICS_MISSING")
    elif any(metric["passed"] is not True for metric in release_metrics):
        reasons.append("RELEASE_METRIC_FAILED")
    return reasons


async def benchmark_evaluation_page(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    query: str = "",
    model_id: str | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if not 1 <= limit <= BENCHMARK_EVALUATION_PAGE_MAX:
        raise ValueError(f"limit must be within 1..{BENCHMARK_EVALUATION_PAGE_MAX}")
    if not benchmark_domains_allowed(policy, "benchmark", "model"):
        raise PermissionError("benchmark model access was not granted")
    base = (
        select(BenchmarkEvaluationRun, RegisteredModel, BenchmarkDatasetVersion)
        .join(RegisteredModel, RegisteredModel.id == BenchmarkEvaluationRun.model_id)
        .join(
            BenchmarkDatasetVersion,
            BenchmarkDatasetVersion.id == BenchmarkEvaluationRun.dataset_version_id,
        )
        .where(benchmark_dataset_scope_clause(policy))
    )
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(base.order_by(None).subquery())
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    filters: list[Any] = []
    normalized_query = query.strip().casefold()
    if normalized_query:
        filters.append(
            or_(
                func.lower(BenchmarkEvaluationRun.id).contains(normalized_query, autoescape=True),
                func.lower(BenchmarkEvaluationRun.model_id).contains(
                    normalized_query, autoescape=True
                ),
                func.lower(RegisteredModel.name).contains(normalized_query, autoescape=True),
                func.lower(BenchmarkEvaluationRun.protocol_version).contains(
                    normalized_query, autoescape=True
                ),
            )
        )
    if model_id:
        filters.append(BenchmarkEvaluationRun.model_id == model_id)
    if status:
        filters.append(BenchmarkEvaluationRun.status == status)
    filtered = base.where(*filters)
    filtered_total = int(
        await session.scalar(
            select(func.count())
            .select_from(filtered.order_by(None).subquery())
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    records = list(
        (
            await session.execute(
                filtered.order_by(
                    BenchmarkEvaluationRun.created_at.desc(), BenchmarkEvaluationRun.id.desc()
                )
                .offset(offset)
                .limit(limit)
                .execution_options(skip_windops_access_control=True)
            )
        ).all()
    )
    evaluation_ids = [record[0].id for record in records]
    model_ids = sorted({record[1].id for record in records})

    metric_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metric_totals: dict[str, int] = {}
    if evaluation_ids:
        metric_totals = {
            str(evaluation_id): int(count)
            for evaluation_id, count in (
                await session.execute(
                    select(
                        BenchmarkMetricSnapshot.evaluation_run_id,
                        func.count(BenchmarkMetricSnapshot.id),
                    )
                    .where(BenchmarkMetricSnapshot.evaluation_run_id.in_(evaluation_ids))
                    .group_by(BenchmarkMetricSnapshot.evaluation_run_id)
                    .execution_options(skip_windops_access_control=True)
                )
            ).all()
        }
        ranked_metrics = (
            select(
                BenchmarkMetricSnapshot.evaluation_run_id,
                BenchmarkMetricSnapshot.metric_name,
                BenchmarkMetricSnapshot.protocol_version,
                BenchmarkMetricSnapshot.metric_version,
                BenchmarkMetricSnapshot.value,
                BenchmarkMetricSnapshot.unit,
                BenchmarkMetricSnapshot.numerator,
                BenchmarkMetricSnapshot.denominator,
                BenchmarkMetricSnapshot.is_release_metric,
                BenchmarkMetricSnapshot.threshold_value,
                BenchmarkMetricSnapshot.threshold_direction,
                BenchmarkMetricSnapshot.passed,
                func.row_number()
                .over(
                    partition_by=BenchmarkMetricSnapshot.evaluation_run_id,
                    order_by=(
                        BenchmarkMetricSnapshot.is_release_metric.desc(),
                        BenchmarkMetricSnapshot.metric_name,
                        BenchmarkMetricSnapshot.id,
                    ),
                )
                .label("position"),
            )
            .where(BenchmarkMetricSnapshot.evaluation_run_id.in_(evaluation_ids))
            .subquery()
        )
        for metric in (
            await session.execute(
                select(ranked_metrics)
                .where(ranked_metrics.c.position <= BENCHMARK_EVALUATION_METRICS_MAX)
                .order_by(ranked_metrics.c.evaluation_run_id, ranked_metrics.c.position)
                .execution_options(skip_windops_access_control=True)
            )
        ).mappings():
            metric_rows[str(metric["evaluation_run_id"])].append(
                {
                    "name": metric["metric_name"],
                    "protocol_version": metric["protocol_version"],
                    "metric_version": metric["metric_version"],
                    "value": metric["value"],
                    "unit": metric["unit"],
                    "numerator": metric["numerator"],
                    "denominator": metric["denominator"],
                    "is_release_metric": metric["is_release_metric"],
                    "threshold_value": metric["threshold_value"],
                    "threshold_direction": metric["threshold_direction"],
                    "passed": metric["passed"],
                }
            )

    deployments_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if model_ids:
        ranked_deployments = (
            select(
                ModelDeployment.id,
                ModelDeployment.model_id,
                ModelDeployment.target_id,
                ModelDeployment.stage,
                ModelDeployment.status,
                ModelDeployment.traffic_percent,
                ModelDeployment.evaluation_gate,
                ModelDeployment.deployed_at,
                ModelDeployment.activated_at,
                ModelDeployment.retired_at,
                func.row_number()
                .over(
                    partition_by=ModelDeployment.model_id,
                    order_by=(ModelDeployment.deployed_at.desc(), ModelDeployment.id.desc()),
                )
                .label("position"),
            )
            .where(ModelDeployment.model_id.in_(model_ids))
            .subquery()
        )
        for deployment_row in (
            await session.execute(
                select(ranked_deployments)
                .where(ranked_deployments.c.position <= BENCHMARK_DEPLOYMENTS_PER_MODEL_MAX)
                .order_by(ranked_deployments.c.model_id, ranked_deployments.c.position)
                .execution_options(skip_windops_access_control=True)
            )
        ).mappings():
            gate = _safe_document(deployment_row["evaluation_gate"])
            authorization = _safe_document(gate.get("server_authorization"))
            deployments_by_model[str(deployment_row["model_id"])].append(
                {
                    "deployment_id": deployment_row["id"],
                    "target_id": deployment_row["target_id"],
                    "stage": deployment_row["stage"],
                    "status": deployment_row["status"],
                    "traffic_percent": deployment_row["traffic_percent"],
                    "authorized_evaluation_run_id": authorization.get("evaluation_run_id"),
                    "gate_policy_version": authorization.get("gate_policy_version"),
                    "authorized_at": authorization.get("authorized_at"),
                    "deployed_at": deployment_row["deployed_at"],
                    "activated_at": deployment_row["activated_at"],
                    "retired_at": deployment_row["retired_at"],
                }
            )

    rows: list[dict[str, Any]] = []
    for evaluation, model, dataset in records:
        metrics = metric_rows.get(evaluation.id, [])
        gate_reasons = _evaluation_gate_reasons(evaluation, model, metrics)
        model_metrics = _safe_document(model.metrics)
        extension = _safe_document(evaluation.extension_data)
        deployments: list[dict[str, Any]] = []
        for deployment in deployments_by_model.get(model.id, []):
            authorized_run = deployment["authorized_evaluation_run_id"]
            active = deployment["status"] == "active"
            if active and authorized_run == evaluation.id and evaluation.invalidated_at is None:
                authorization_state = "current"
            elif active:
                authorization_state = "stale"
            elif authorized_run == evaluation.id:
                authorization_state = "inactive"
            else:
                authorization_state = "not-authorized-for-run"
            deployments.append({**deployment, "authorization_state": authorization_state})
        rows.append(
            {
                "evaluation_run_id": evaluation.id,
                "dataset": {
                    "dataset_version_id": dataset.id,
                    "dataset_id": dataset.dataset_id,
                    "version": dataset.version,
                },
                "model": {
                    "model_id": model.id,
                    "name": model.name,
                    "version": model.version,
                    "kind": model.kind,
                    "status": model.status,
                    "algorithm": extension.get("algorithm") or model_metrics.get("algorithm"),
                    "evaluation_role": extension.get("evaluation_role")
                    or model_metrics.get("evaluation_role"),
                    "artifact": {
                        "uri": model.artifact_uri,
                        "sha256": model.artifact_sha256,
                        "present": bool(model.artifact_uri and model.artifact_sha256),
                    },
                },
                "run": {
                    "kind": evaluation.run_kind,
                    "status": evaluation.status,
                    "farm": evaluation.farm,
                    "protocol_version": evaluation.protocol_version,
                    "feature_set_version": evaluation.feature_set_version,
                    "quality_rule_version": evaluation.quality_rule_version,
                    "threshold_policy_version": evaluation.threshold_policy_version,
                    "threshold_policy_sha256": evaluation.threshold_policy_sha256,
                    "random_seed": evaluation.random_seed,
                    "input_identity_sha256": evaluation.input_identity_sha256,
                    "prediction_truth_used": extension.get("prediction_truth_used"),
                    "dependency_identity": extension.get("dependency_identity")
                    or model_metrics.get("dependency_identity"),
                    "created_at": evaluation.created_at,
                    "started_at": evaluation.started_at,
                    "completed_at": evaluation.completed_at,
                    "invalidated_at": evaluation.invalidated_at,
                },
                "event_accounting": {
                    "requested": evaluation.requested_event_count,
                    "scored": evaluation.scored_event_count,
                    "failed": evaluation.failed_event_count,
                    "unscorable": evaluation.unscorable_event_count,
                },
                "evaluation_artifact": {
                    "uri": evaluation.artifact_uri,
                    "sha256": evaluation.artifact_sha256,
                    "present": bool(evaluation.artifact_uri and evaluation.artifact_sha256),
                    "immutable": bool(
                        evaluation.status == "completed"
                        and evaluation.completed_at is not None
                        and evaluation.artifact_uri
                        and evaluation.artifact_sha256
                    ),
                },
                "metrics": metrics,
                "metrics_truncated": metric_totals.get(evaluation.id, 0) > len(metrics),
                "server_gate": {
                    "eligible": not gate_reasons,
                    "reasons": gate_reasons,
                    "release_metric_count": sum(
                        1 for metric in metrics if metric["is_release_metric"]
                    ),
                },
                "deployments": deployments,
            }
        )
    return {
        "data": rows,
        "meta": {
            "count": len(rows),
            "total": total,
            "filtered_total": filtered_total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(rows) < filtered_total,
            "next_offset": offset + len(rows) if offset + len(rows) < filtered_total else None,
            "bounds": {
                "evaluation_page_max": BENCHMARK_EVALUATION_PAGE_MAX,
                "metrics_per_evaluation_max": BENCHMARK_EVALUATION_METRICS_MAX,
                "deployments_per_model_max": BENCHMARK_DEPLOYMENTS_PER_MODEL_MAX,
            },
        },
    }


async def benchmark_evaluation_result_page(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    evaluation_run_id: str,
    status: str | None = None,
    reveal_truth: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if not 1 <= limit <= BENCHMARK_EVENT_RESULT_PAGE_MAX:
        raise ValueError(f"limit must be within 1..{BENCHMARK_EVENT_RESULT_PAGE_MAX}")
    if not benchmark_domains_allowed(policy, "benchmark", "model"):
        raise PermissionError("benchmark model access was not granted")
    if reveal_truth and not benchmark_truth_allowed(policy):
        raise PermissionError("benchmark truth access was not granted")
    evaluation = await session.scalar(
        select(BenchmarkEvaluationRun)
        .join(
            BenchmarkDatasetVersion,
            BenchmarkDatasetVersion.id == BenchmarkEvaluationRun.dataset_version_id,
        )
        .where(
            BenchmarkEvaluationRun.id == evaluation_run_id,
            benchmark_dataset_scope_clause(policy),
        )
    )
    if evaluation is None:
        raise NotFoundError(f"benchmark evaluation {evaluation_run_id} was not found")
    columns: list[Any] = [
        BenchmarkEventResult.id.label("result_id"),
        BenchmarkEventResult.event_id.label("benchmark_event_id"),
        BenchmarkEventResult.status,
        BenchmarkEventResult.scorable,
        BenchmarkEventResult.anomaly_detected,
        BenchmarkEventResult.care_score,
        BenchmarkEventResult.coverage_score,
        BenchmarkEventResult.accuracy_score,
        BenchmarkEventResult.reliability_score,
        BenchmarkEventResult.earliness_score,
        BenchmarkEventResult.prediction_artifact_uri,
        BenchmarkEventResult.prediction_artifact_sha256,
        BenchmarkEventResult.failure_code,
        BenchmarkEventResult.result_sha256,
        BenchmarkEventResult.details,
        BenchmarkEvent.event_id.label("event_number"),
        BenchmarkEvent.farm,
        BenchmarkEvent.logical_asset_id,
        (BenchmarkEvent.event_label if reveal_truth else literal(None)).label("event_label"),
        (BenchmarkEvent.event_interval_start if reveal_truth else literal(None)).label(
            "event_interval_start"
        ),
        (BenchmarkEvent.event_interval_end if reveal_truth else literal(None)).label(
            "event_interval_end"
        ),
        (BenchmarkEvent.truth_metadata if reveal_truth else literal(None)).label("truth_metadata"),
    ]
    base = (
        select(*columns)
        .join(BenchmarkEvent, BenchmarkEvent.id == BenchmarkEventResult.event_id)
        .where(BenchmarkEventResult.evaluation_run_id == evaluation_run_id)
    )
    total = int(
        await session.scalar(
            select(func.count(BenchmarkEventResult.id)).where(
                BenchmarkEventResult.evaluation_run_id == evaluation_run_id
            )
        )
        or 0
    )
    filtered = base.where(BenchmarkEventResult.status == status) if status else base
    filtered_total = int(
        await session.scalar(select(func.count()).select_from(filtered.order_by(None).subquery()))
        or 0
    )
    records = list(
        (
            await session.execute(
                filtered.order_by(BenchmarkEvent.farm, BenchmarkEvent.event_id)
                .offset(offset)
                .limit(limit)
            )
        ).mappings()
    )
    rows: list[dict[str, Any]] = []
    for record in records:
        details = _safe_document(record["details"])
        truth_metadata = _safe_document(record["truth_metadata"])
        rows.append(
            {
                "result_id": record["result_id"],
                "benchmark_event_id": record["benchmark_event_id"],
                "event_id": record["event_number"],
                "farm": record["farm"],
                "logical_asset_id": record["logical_asset_id"],
                "status": record["status"],
                "scorable": record["scorable"],
                "anomaly_detected": record["anomaly_detected"],
                "scores": {
                    "care": record["care_score"],
                    "coverage": record["coverage_score"],
                    "accuracy": record["accuracy_score"],
                    "reliability": record["reliability_score"],
                    "earliness": record["earliness_score"],
                },
                "failure_code": record["failure_code"],
                "result_sha256": record["result_sha256"],
                "prediction_artifact": {
                    "uri": record["prediction_artifact_uri"],
                    "sha256": record["prediction_artifact_sha256"],
                    "present": bool(
                        record["prediction_artifact_uri"] and record["prediction_artifact_sha256"]
                    ),
                },
                "evaluation_artifact": {
                    "uri": details.get("evaluation_artifact_uri"),
                    "sha256": details.get("evaluation_artifact_sha256"),
                },
                "truth": {
                    "access": "revealed" if reveal_truth else "restricted",
                    "event_label": record["event_label"],
                    "event_interval_start": record["event_interval_start"],
                    "event_interval_end": record["event_interval_end"],
                    "failure_type": details.get("failure_type") if reveal_truth else None,
                    "description": (
                        truth_metadata.get("event_description")
                        or truth_metadata.get("description")
                        or truth_metadata.get("failure_description")
                    )
                    if reveal_truth
                    else None,
                },
            }
        )
    return {
        "data": rows,
        "meta": {
            "evaluation_run_id": evaluation.id,
            "count": len(rows),
            "total": total,
            "filtered_total": filtered_total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(rows) < filtered_total,
            "next_offset": offset + len(rows) if offset + len(rows) < filtered_total else None,
            "truth_revealed": reveal_truth,
            "truth_reveal_allowed": benchmark_truth_allowed(policy),
            "bounds": {"event_result_page_max": BENCHMARK_EVENT_RESULT_PAGE_MAX},
        },
    }


def _prediction_quality_summary(prediction: ModelPrediction) -> dict[str, Any]:
    snapshot = _safe_document(prediction.input_snapshot)
    raw_signals = snapshot.get("signals")
    signals = raw_signals if isinstance(raw_signals, list) else []
    quality_counts = {"good": 0, "uncertain": 0, "bad": 0, "unknown": 0}
    mask_refs: set[str] = set()
    for value in signals[:BENCHMARK_SIGNAL_SUMMARY_MAX]:
        signal = value if isinstance(value, dict) else {}
        quality = signal.get("quality")
        key = str(quality) if quality in {"good", "uncertain", "bad"} else "unknown"
        quality_counts[key] += 1
        refs = signal.get("quality_mask_refs")
        if isinstance(refs, list):
            mask_refs.update(str(ref) for ref in refs if isinstance(ref, str))
    return {
        "signal_count": len(signals),
        "signals_inspected": min(len(signals), BENCHMARK_SIGNAL_SUMMARY_MAX),
        "signals_truncated": len(signals) > BENCHMARK_SIGNAL_SUMMARY_MAX,
        "quality_counts": quality_counts,
        "quality_mask_refs": sorted(mask_refs)[:BENCHMARK_SIGNAL_SUMMARY_MAX],
        "quality_mask_refs_truncated": len(mask_refs) > BENCHMARK_SIGNAL_SUMMARY_MAX,
    }


async def benchmark_diagnosis_page(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    *,
    query: str = "",
    status: str | None = None,
    reveal_truth: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if not 1 <= limit <= BENCHMARK_DIAGNOSIS_PAGE_MAX:
        raise ValueError(f"limit must be within 1..{BENCHMARK_DIAGNOSIS_PAGE_MAX}")
    if not benchmark_domains_allowed(policy, "benchmark", "model", "mission"):
        raise PermissionError("benchmark diagnosis access was not granted")
    if reveal_truth and not benchmark_truth_allowed(policy):
        raise PermissionError("benchmark truth access was not granted")
    columns: list[Any] = [
        BenchmarkReplayRun.id.label("replay_run_id"),
        BenchmarkReplayRun.dataset_version_id,
        BenchmarkDatasetVersion.dataset_id,
        BenchmarkDatasetVersion.version.label("dataset_version"),
        BenchmarkReplayRun.event_id.label("benchmark_event_id"),
        BenchmarkReplayRun.source_event_number.label("event_number"),
        BenchmarkReplayRun.farm,
        BenchmarkReplayRun.logical_asset_id,
        BenchmarkReplayRun.online_turbine_id,
        BenchmarkReplayRun.status.label("replay_status"),
        BenchmarkReplayRun.replay_mode,
        BenchmarkReplayRun.replay_anchor_at,
        BenchmarkReplayRun.time_rule_version,
        BenchmarkReplayRun.window_start_row_id,
        BenchmarkReplayRun.window_end_row_id,
        BenchmarkReplayRun.model_id,
        BenchmarkReplayRun.model_version,
        BenchmarkReplayRun.deployment_id,
        BenchmarkReplayRun.threshold_policy_version,
        BenchmarkReplayRun.threshold_policy_sha256,
        BenchmarkReplayRun.created_at,
        BenchmarkReplayRun.started_at,
        BenchmarkReplayRun.finished_at,
        BenchmarkReplayRun.error,
        RegisteredModel.name.label("model_name"),
        RegisteredModel.kind.label("model_kind"),
        RegisteredModel.artifact_uri.label("model_artifact_uri"),
        RegisteredModel.artifact_sha256.label("model_artifact_sha256"),
        ModelDeployment.status.label("deployment_status"),
        ModelDeployment.target_id.label("deployment_target_id"),
        (BenchmarkEvent.event_label if reveal_truth else literal(None)).label("event_label"),
        (BenchmarkEvent.event_interval_start if reveal_truth else literal(None)).label(
            "event_interval_start"
        ),
        (BenchmarkEvent.event_interval_end if reveal_truth else literal(None)).label(
            "event_interval_end"
        ),
        (BenchmarkEvent.truth_metadata if reveal_truth else literal(None)).label("truth_metadata"),
    ]
    base = (
        select(*columns)
        .join(
            BenchmarkDatasetVersion,
            BenchmarkDatasetVersion.id == BenchmarkReplayRun.dataset_version_id,
        )
        .join(BenchmarkEvent, BenchmarkEvent.id == BenchmarkReplayRun.event_id)
        .outerjoin(RegisteredModel, RegisteredModel.id == BenchmarkReplayRun.model_id)
        .outerjoin(ModelDeployment, ModelDeployment.id == BenchmarkReplayRun.deployment_id)
        .where(
            benchmark_dataset_scope_clause(policy),
            turbine_scope_clause(
                policy,
                BenchmarkReplayRun.online_turbine_id,
                entity_columns=(BenchmarkReplayRun.id, BenchmarkReplayRun.event_id),
                data_scopes="benchmark",
            ),
        )
    )
    filters: list[Any] = []
    normalized_query = query.strip().casefold()
    if normalized_query:
        filters.append(
            or_(
                func.lower(BenchmarkReplayRun.id).contains(normalized_query, autoescape=True),
                func.lower(BenchmarkReplayRun.online_turbine_id).contains(
                    normalized_query, autoescape=True
                ),
                func.lower(BenchmarkReplayRun.logical_asset_id).contains(
                    normalized_query, autoescape=True
                ),
                func.lower(BenchmarkReplayRun.model_id).contains(normalized_query, autoescape=True),
            )
        )
    if status:
        filters.append(BenchmarkReplayRun.status == status)
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(base.order_by(None).subquery())
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    filtered = base.where(*filters)
    filtered_total = int(
        await session.scalar(
            select(func.count())
            .select_from(filtered.order_by(None).subquery())
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    replay_rows = list(
        (
            await session.execute(
                filtered.order_by(
                    BenchmarkReplayRun.created_at.desc(), BenchmarkReplayRun.id.desc()
                )
                .offset(offset)
                .limit(limit)
                .execution_options(skip_windops_access_control=True)
            )
        ).mappings()
    )
    replay_ids = [str(row["replay_run_id"]) for row in replay_rows]
    event_ids = [str(row["benchmark_event_id"]) for row in replay_rows]

    prediction_totals: dict[str, int] = {}
    predictions_by_replay: dict[str, list[ModelPrediction]] = defaultdict(list)
    if replay_ids:
        prediction_totals = {
            str(replay_id): int(count)
            for replay_id, count in (
                await session.execute(
                    select(
                        ModelPrediction.benchmark_replay_run_id,
                        func.count(ModelPrediction.id),
                    )
                    .where(ModelPrediction.benchmark_replay_run_id.in_(replay_ids))
                    .group_by(ModelPrediction.benchmark_replay_run_id)
                )
            ).all()
        }
        ranked_prediction_ids = (
            select(
                ModelPrediction.id.label("prediction_id"),
                ModelPrediction.benchmark_replay_run_id.label("replay_run_id"),
                func.row_number()
                .over(
                    partition_by=ModelPrediction.benchmark_replay_run_id,
                    order_by=(ModelPrediction.created_at, ModelPrediction.id),
                )
                .label("position"),
            )
            .where(ModelPrediction.benchmark_replay_run_id.in_(replay_ids))
            .subquery()
        )
        prediction_ids = list(
            (
                await session.scalars(
                    select(ranked_prediction_ids.c.prediction_id)
                    .where(ranked_prediction_ids.c.position <= BENCHMARK_PREDICTIONS_PER_REPLAY_MAX)
                    .order_by(
                        ranked_prediction_ids.c.replay_run_id,
                        ranked_prediction_ids.c.position,
                    )
                )
            ).all()
        )
        if prediction_ids:
            predictions = list(
                (
                    await session.scalars(
                        select(ModelPrediction)
                        .where(ModelPrediction.id.in_(prediction_ids))
                        .order_by(ModelPrediction.created_at, ModelPrediction.id)
                    )
                ).all()
            )
            for prediction in predictions:
                if prediction.benchmark_replay_run_id:
                    predictions_by_replay[prediction.benchmark_replay_run_id].append(prediction)

    loaded_predictions = [
        prediction for predictions in predictions_by_replay.values() for prediction in predictions
    ]
    prediction_ids = [prediction.id for prediction in loaded_predictions]
    alarms_by_prediction: dict[str, Alarm] = {}
    missions_by_alarm: dict[str, Mission] = {}
    sample_evidence_by_prediction: dict[str, dict[str, Any]] = {}
    if prediction_ids:
        alarms = list(
            (
                await session.scalars(
                    select(Alarm).where(Alarm.model_prediction_id.in_(prediction_ids))
                )
            ).all()
        )
        alarms_by_prediction = {
            str(alarm.model_prediction_id): alarm
            for alarm in alarms
            if alarm.model_prediction_id is not None
        }
        alarm_ids = [alarm.id for alarm in alarms]
        if alarm_ids:
            missions = list(
                (
                    await session.scalars(select(Mission).where(Mission.alarm_id.in_(alarm_ids)))
                ).all()
            )
            missions_by_alarm = {mission.alarm_id: mission for mission in missions}
        ranked_samples = (
            select(
                ModelPrediction.id.label("prediction_id"),
                ScadaSample.observed_at,
                ScadaSample.source_sequence,
                ScadaSample.quality,
                ScadaSample.attributes,
                func.row_number()
                .over(
                    partition_by=ModelPrediction.id,
                    order_by=(ScadaSample.variable, ScadaSample.id),
                )
                .label("position"),
            )
            .join(
                ScadaSample,
                (ScadaSample.turbine_id == ModelPrediction.turbine_id)
                & (ScadaSample.source_sequence == ModelPrediction.feature_end_sequence)
                & (ScadaSample.source_id == CARE_REPLAY_SOURCE_ID),
            )
            .where(ModelPrediction.id.in_(prediction_ids))
            .subquery()
        )
        sample_evidence_by_prediction = {
            str(row["prediction_id"]): dict(row)
            for row in (
                await session.execute(select(ranked_samples).where(ranked_samples.c.position == 1))
            ).mappings()
        }

    quality_by_event: dict[str, dict[str, Any]] = {}
    if event_ids:
        ranked_quality = (
            select(
                BenchmarkQualityReport.id.label("quality_report_id"),
                BenchmarkQualityReport.event_id,
                BenchmarkQualityReport.status,
                BenchmarkQualityReport.quality_rule_version,
                BenchmarkQualityReport.feature_set_version,
                BenchmarkQualityReport.artifact_uri,
                BenchmarkQualityReport.artifact_sha256,
                BenchmarkQualityReport.mask_uri,
                BenchmarkQualityReport.mask_sha256,
                BenchmarkQualityReport.summary,
                func.row_number()
                .over(
                    partition_by=BenchmarkQualityReport.event_id,
                    order_by=(
                        BenchmarkQualityReport.created_at.desc(),
                        BenchmarkQualityReport.id.desc(),
                    ),
                )
                .label("position"),
            )
            .where(BenchmarkQualityReport.event_id.in_(event_ids))
            .subquery()
        )
        quality_by_event = {
            str(row["event_id"]): dict(row)
            for row in (
                await session.execute(select(ranked_quality).where(ranked_quality.c.position == 1))
            ).mappings()
        }

    rows: list[dict[str, Any]] = []
    for replay in replay_rows:
        replay_id = str(replay["replay_run_id"])
        truth_metadata = _safe_document(replay["truth_metadata"])
        prediction_payloads: list[dict[str, Any]] = []
        first_alert_payload: dict[str, Any] | None = None
        for prediction in predictions_by_replay.get(replay_id, []):
            output = _safe_document(prediction.output)
            sample = sample_evidence_by_prediction.get(prediction.id, {})
            attributes = _safe_document(sample.get("attributes"))
            alarm = alarms_by_prediction.get(prediction.id)
            mission = missions_by_alarm.get(alarm.id) if alarm is not None else None
            link = {
                "alarm_id": alarm.id if alarm is not None else None,
                "alarm_status": alarm.status if alarm is not None else None,
                "alarm_triggered_at": alarm.triggered_at if alarm is not None else None,
                "mission_id": mission.id if mission is not None else None,
                "mission_status": mission.status if mission is not None else None,
                "decision_id": (
                    _safe_document(mission.public_state).get("decision_id")
                    if mission is not None
                    else None
                ),
            }
            if alarm is not None and first_alert_payload is None:
                lead_rows = None
                if reveal_truth and prediction.feature_end_sequence is not None:
                    lead_rows = int(replay["event_interval_start"]) - int(
                        prediction.feature_end_sequence
                    )
                first_alert_payload = {
                    **link,
                    "prediction_id": prediction.id,
                    "synthetic_observed_at": prediction.feature_observed_at,
                    "anonymous_observed_at": attributes.get("anonymous_observed_at"),
                    "source_sequence": prediction.feature_end_sequence,
                    "lead_source_rows": lead_rows,
                    "lead_semantics": "source-row-offset-not-rul",
                }
            prediction_payloads.append(
                {
                    "prediction_id": prediction.id,
                    "status": prediction.status,
                    "error_code": prediction.error_code,
                    "anomaly_score": prediction.anomaly_score,
                    "binary_prediction": prediction.binary_prediction,
                    "component": prediction.component,
                    "model_id": prediction.model_id,
                    "deployment_id": prediction.deployment_id,
                    "evaluation_run_id": prediction.benchmark_evaluation_run_id,
                    "feature_window": {
                        "start": prediction.feature_window_start,
                        "end": prediction.feature_window_end,
                        "start_sequence": prediction.feature_start_sequence,
                        "end_sequence": prediction.feature_end_sequence,
                    },
                    "threshold": {
                        "value": output.get("threshold_value"),
                        "comparison": output.get("threshold_comparison"),
                        "policy_version": prediction.threshold_policy_version,
                        "policy_sha256": prediction.threshold_policy_sha256,
                    },
                    "time_evidence": {
                        "synthetic_observed_at": prediction.feature_observed_at,
                        "observed_at_is_synthetic": bool(
                            attributes.get("observed_at_is_synthetic", True)
                        ),
                        "time_claim": attributes.get("time_claim")
                        or output.get("observed_at_time_claim"),
                        "anonymous_observed_at": attributes.get("anonymous_observed_at"),
                        "source_time_stamp": attributes.get("source_time_stamp"),
                        "source_row_id": attributes.get("source_row_id"),
                    },
                    "quality": _prediction_quality_summary(prediction),
                    "evidence_artifact": {
                        "uri": prediction.evidence_artifact_uri,
                        "sha256": prediction.evidence_artifact_sha256,
                        "present": bool(
                            prediction.evidence_artifact_uri and prediction.evidence_artifact_sha256
                        ),
                    },
                    "links": link,
                    "latency_ms": prediction.latency_ms,
                    "created_at": prediction.created_at,
                }
            )
        quality = quality_by_event.get(str(replay["benchmark_event_id"]))
        quality_summary = _safe_document(quality.get("summary")) if quality else {}
        deployment_stale = bool(replay["deployment_id"] and replay["deployment_status"] != "active")
        rows.append(
            {
                "replay_run_id": replay_id,
                "dataset": {
                    "dataset_version_id": replay["dataset_version_id"],
                    "dataset_id": replay["dataset_id"],
                    "version": replay["dataset_version"],
                },
                "event": {
                    "benchmark_event_id": replay["benchmark_event_id"],
                    "event_id": replay["event_number"],
                    "farm": replay["farm"],
                    "logical_asset_id": replay["logical_asset_id"],
                    "online_turbine_id": replay["online_turbine_id"],
                },
                "replay": {
                    "status": replay["replay_status"],
                    "mode": replay["replay_mode"],
                    "anchor_at": replay["replay_anchor_at"],
                    "time_rule_version": replay["time_rule_version"],
                    "time_semantics": "synthetic-replay-time-not-field-time",
                    "window_start_row_id": replay["window_start_row_id"],
                    "window_end_row_id": replay["window_end_row_id"],
                    "created_at": replay["created_at"],
                    "started_at": replay["started_at"],
                    "finished_at": replay["finished_at"],
                    "error": replay["error"],
                },
                "model": {
                    "model_id": replay["model_id"],
                    "name": replay["model_name"],
                    "version": replay["model_version"],
                    "kind": replay["model_kind"],
                    "artifact_uri": replay["model_artifact_uri"],
                    "artifact_sha256": replay["model_artifact_sha256"],
                    "artifact_present": bool(
                        replay["model_artifact_uri"] and replay["model_artifact_sha256"]
                    ),
                },
                "deployment": {
                    "deployment_id": replay["deployment_id"],
                    "status": replay["deployment_status"],
                    "target_id": replay["deployment_target_id"],
                    "stale": deployment_stale,
                    "threshold_policy_version": replay["threshold_policy_version"],
                    "threshold_policy_sha256": replay["threshold_policy_sha256"],
                },
                "quality_report": {
                    "quality_report_id": quality.get("quality_report_id") if quality else None,
                    "status": quality.get("status") if quality else "missing",
                    "quality_rule_version": quality.get("quality_rule_version")
                    if quality
                    else None,
                    "feature_set_version": quality.get("feature_set_version") if quality else None,
                    "mask_count": int(quality_summary.get("mask_count", 0)),
                    "mask_artifact": {
                        "uri": quality.get("mask_uri") if quality else None,
                        "sha256": quality.get("mask_sha256") if quality else None,
                        "present": bool(
                            quality and quality.get("mask_uri") and quality.get("mask_sha256")
                        ),
                    },
                },
                "predictions": prediction_payloads,
                "predictions_truncated": prediction_totals.get(replay_id, 0)
                > len(prediction_payloads),
                "first_alert": first_alert_payload,
                "truth": {
                    "access": "revealed" if reveal_truth else "restricted",
                    "event_label": replay["event_label"],
                    "event_interval_start": replay["event_interval_start"],
                    "event_interval_end": replay["event_interval_end"],
                    "description": (
                        truth_metadata.get("event_description")
                        or truth_metadata.get("description")
                        or truth_metadata.get("failure_description")
                    )
                    if reveal_truth
                    else None,
                },
            }
        )
    return {
        "data": rows,
        "meta": {
            "count": len(rows),
            "total": total,
            "filtered_total": filtered_total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(rows) < filtered_total,
            "next_offset": offset + len(rows) if offset + len(rows) < filtered_total else None,
            "truth_revealed": reveal_truth,
            "truth_reveal_allowed": benchmark_truth_allowed(policy),
            "source": "postgresql-governed-benchmark-replay",
            "bounds": {
                "diagnosis_page_max": BENCHMARK_DIAGNOSIS_PAGE_MAX,
                "predictions_per_replay_max": BENCHMARK_PREDICTIONS_PER_REPLAY_MAX,
                "signals_inspected_per_prediction_max": BENCHMARK_SIGNAL_SUMMARY_MAX,
            },
        },
    }
