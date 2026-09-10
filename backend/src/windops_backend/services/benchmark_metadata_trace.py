from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import InvalidTransitionError, NotFoundError
from windops_backend.models import (
    Alarm,
    BenchmarkEvaluationRun,
    BenchmarkEvent,
    BenchmarkMetricSnapshot,
    BenchmarkReplayRun,
    ModelPrediction,
)
from windops_backend.schemas import (
    BenchmarkTraceResponse,
)


async def build_benchmark_trace(
    session: AsyncSession,
    *,
    alarm_id: str,
) -> BenchmarkTraceResponse:
    alarm = await session.get(Alarm, alarm_id)
    if alarm is None:
        raise NotFoundError(f"alarm {alarm_id} was not found")
    if alarm.model_prediction_id is None:
        raise InvalidTransitionError("alarm is not linked to a model prediction")
    prediction = await session.get(ModelPrediction, alarm.model_prediction_id)
    if prediction is None:  # pragma: no cover - protected by the foreign key
        raise NotFoundError("alarm model prediction was not found")
    if prediction.benchmark_replay_run_id is None or prediction.benchmark_evaluation_run_id is None:
        raise InvalidTransitionError("prediction lacks benchmark replay/evaluation provenance")
    replay = await session.get(BenchmarkReplayRun, prediction.benchmark_replay_run_id)
    evaluation = await session.get(BenchmarkEvaluationRun, prediction.benchmark_evaluation_run_id)
    if replay is None or evaluation is None:
        raise NotFoundError("benchmark replay or evaluation provenance was not found")
    event = await session.get(BenchmarkEvent, replay.event_id)
    if event is None:  # pragma: no cover - protected by the foreign key
        raise NotFoundError("benchmark event provenance was not found")
    if (
        evaluation.dataset_version_id != replay.dataset_version_id
        or evaluation.model_id != prediction.model_id
        or replay.online_turbine_id != prediction.turbine_id
    ):
        raise InvalidTransitionError("benchmark trace crosses dataset/model/replay identities")
    metric_ids = list(
        await session.scalars(
            select(BenchmarkMetricSnapshot.id)
            .where(BenchmarkMetricSnapshot.evaluation_run_id == evaluation.id)
            .order_by(BenchmarkMetricSnapshot.id)
        )
    )
    return BenchmarkTraceResponse(
        dataset_version_id=replay.dataset_version_id,
        event_id=event.id,
        model_id=prediction.model_id,
        model_version=evaluation.model_version,
        evaluation_run_id=evaluation.id,
        replay_run_id=replay.id,
        prediction_id=prediction.id,
        alarm_id=alarm.id,
        source_event_id=alarm.source_event_id,
        metric_snapshot_ids=metric_ids,
    )
