from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.benchmarks.care.replay import CARE_REPLAY_SOURCE_ID
from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.models import (
    BenchmarkEvent,
    BenchmarkReplayRun,
    ModelDeployment,
    RegisteredModel,
    ScadaSample,
    Turbine,
)
from windops_backend.schemas import (
    BenchmarkReplayRunCreateRequest,
)
from windops_backend.services.benchmark_metadata_contracts import (
    _claim_identity,
    _document_sha256,
    _same_instant,
)
from windops_backend.services.events import append_domain_event


async def register_replay_run(
    session: AsyncSession,
    request: BenchmarkReplayRunCreateRequest,
    *,
    subject: str,
) -> tuple[BenchmarkReplayRun, bool]:
    async with _claim_identity(session, f"benchmark-replay:{request.benchmark_replay_run_id}"):
        existing = await session.get(BenchmarkReplayRun, request.benchmark_replay_run_id)
        if existing is not None:
            if _replay_run_matches_request(existing, request, subject=subject):
                return existing, True
            raise ConflictError("benchmark replay run ID already exists with different identity")
        event = await session.get(BenchmarkEvent, request.event_id)
        if event is None or event.dataset_version_id != request.dataset_version_id:
            raise InvalidTransitionError("benchmark replay event does not match its dataset")
        if (
            event.farm != request.farm
            or event.event_id != request.source_event_number
            or event.logical_asset_id != request.logical_asset_id
            or event.source_asset_id != request.source_asset_id
        ):
            raise InvalidTransitionError("benchmark replay identity does not match its event")
        if await session.get(Turbine, request.online_turbine_id) is None:
            raise NotFoundError(f"online replay turbine {request.online_turbine_id} was not found")
        if request.model_id is not None:
            model = await session.get(RegisteredModel, request.model_id)
            if model is None or model.version != request.model_version:
                raise InvalidTransitionError("benchmark replay model ID/version is not registered")
        if request.deployment_id is not None:
            deployment = await session.get(ModelDeployment, request.deployment_id)
            if deployment is None:
                raise NotFoundError(
                    f"benchmark replay deployment {request.deployment_id} was not found"
                )
            if deployment.model_id != request.model_id:
                raise InvalidTransitionError(
                    "benchmark replay deployment does not belong to the registered model"
                )
        row = BenchmarkReplayRun(
            id=request.benchmark_replay_run_id,
            dataset_version_id=request.dataset_version_id,
            event_id=request.event_id,
            source_asset_id=request.source_asset_id,
            logical_asset_id=request.logical_asset_id,
            online_turbine_id=request.online_turbine_id,
            farm=request.farm,
            source_event_number=request.source_event_number,
            replay_mode=request.replay_mode,
            speed=request.speed,
            status=request.status,
            replay_anchor_at=request.replay_anchor_at,
            time_rule_version=request.time_rule_version,
            sequence_rule_version=request.sequence_rule_version,
            source_event_id_rule_version=request.source_event_id_rule_version,
            selected_variables=request.selected_variables,
            window_start_row_id=request.window_start_row_id,
            window_end_row_id=request.window_end_row_id,
            checkpoint=request.checkpoint,
            checkpoint_revision=request.checkpoint_revision,
            checkpoint_sha256=request.checkpoint_sha256,
            model_id=request.model_id,
            model_version=request.model_version,
            deployment_id=request.deployment_id,
            threshold_policy_version=request.threshold_policy_version,
            threshold_policy_sha256=request.threshold_policy_sha256,
            created_by=subject,
            started_at=request.started_at,
            finished_at=request.finished_at,
            cancelled_by=request.cancelled_by,
            error=request.error,
        )
        session.add(row)
        await session.flush()
        append_domain_event(
            session,
            event_type="benchmark.replay.registered",
            aggregate_type="benchmark_replay",
            aggregate_id=row.id,
            payload={
                "dataset_version_id": row.dataset_version_id,
                "event_id": row.event_id,
                "online_turbine_id": row.online_turbine_id,
                "model_id": row.model_id,
                "model_version": row.model_version,
                "checkpoint_sha256": row.checkpoint_sha256,
                "requested_by": subject,
            },
        )
        return row, False


def _replay_immutable_identity(
    row: BenchmarkReplayRun,
) -> tuple[object, ...]:
    return (
        row.dataset_version_id,
        row.event_id,
        row.source_asset_id,
        row.logical_asset_id,
        row.online_turbine_id,
        row.farm,
        row.source_event_number,
        row.replay_mode,
        row.speed,
        _as_utc(row.replay_anchor_at),
        row.time_rule_version,
        row.sequence_rule_version,
        row.source_event_id_rule_version,
        row.selected_variables,
        row.window_start_row_id,
        row.window_end_row_id,
        row.model_id,
        row.model_version,
        row.deployment_id,
        row.threshold_policy_version,
        row.threshold_policy_sha256,
        row.created_by,
    )


def _request_replay_immutable_identity(
    request: BenchmarkReplayRunCreateRequest,
    *,
    subject: str,
) -> tuple[object, ...]:
    return (
        request.dataset_version_id,
        request.event_id,
        request.source_asset_id,
        request.logical_asset_id,
        request.online_turbine_id,
        request.farm,
        request.source_event_number,
        request.replay_mode,
        request.speed,
        _as_utc(request.replay_anchor_at),
        request.time_rule_version,
        request.sequence_rule_version,
        request.source_event_id_rule_version,
        request.selected_variables,
        request.window_start_row_id,
        request.window_end_row_id,
        request.model_id,
        request.model_version,
        request.deployment_id,
        request.threshold_policy_version,
        request.threshold_policy_sha256,
        subject,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _replay_run_matches_request(
    row: BenchmarkReplayRun,
    request: BenchmarkReplayRunCreateRequest,
    *,
    subject: str,
) -> bool:
    return (
        _replay_immutable_identity(row)
        == _request_replay_immutable_identity(request, subject=subject)
        and row.status == request.status
        and row.checkpoint == request.checkpoint
        and row.checkpoint_revision == request.checkpoint_revision
        and row.checkpoint_sha256 == request.checkpoint_sha256
        and _same_instant(row.started_at, request.started_at)
        and _same_instant(row.finished_at, request.finished_at)
        and row.cancelled_by == request.cancelled_by
        and row.error == request.error
    )


async def persist_replay_run_progress(
    session: AsyncSession,
    request: BenchmarkReplayRunCreateRequest,
    *,
    subject: str,
) -> tuple[BenchmarkReplayRun, bool]:
    """Advance a registered replay only after every checkpoint row is durably ingested."""

    scope = f"benchmark-replay:{request.benchmark_replay_run_id}"
    async with _claim_identity(session, scope):
        row = await session.scalar(
            select(BenchmarkReplayRun)
            .where(BenchmarkReplayRun.id == request.benchmark_replay_run_id)
            .with_for_update()
        )
        if row is None:
            raise NotFoundError(
                f"benchmark replay run {request.benchmark_replay_run_id} was not found"
            )
        if _replay_run_matches_request(row, request, subject=subject):
            return row, True
        if _replay_immutable_identity(row) != _request_replay_immutable_identity(
            request, subject=subject
        ):
            raise ConflictError("benchmark replay immutable identity cannot be changed")
        status_only = (
            request.checkpoint_revision == row.checkpoint_revision
            and request.checkpoint == row.checkpoint
            and request.checkpoint_sha256 == row.checkpoint_sha256
            and request.status != row.status
        )
        if not status_only and request.checkpoint_revision != row.checkpoint_revision + 1:
            raise ConflictError("benchmark replay checkpoint requires the next revision")
        if request.checkpoint.get("revision") != request.checkpoint_revision:
            raise InvalidTransitionError("benchmark replay checkpoint revision is inconsistent")
        if request.checkpoint_sha256 != _document_sha256(request.checkpoint):
            raise InvalidTransitionError("benchmark replay checkpoint hash is invalid")
        previous_rows = row.checkpoint.get("last_confirmed_rows")
        requested_rows = request.checkpoint.get("last_confirmed_rows")
        if not isinstance(previous_rows, dict) or not isinstance(requested_rows, dict):
            raise InvalidTransitionError("benchmark replay checkpoint rows are malformed")
        variable_by_short_id = {
            str(value["short_id"]): str(value["canonical_variable"])
            for value in row.selected_variables
            if isinstance(value, dict)
        }
        if set(previous_rows) != set(requested_rows) or set(requested_rows) != set(
            variable_by_short_id
        ):
            raise InvalidTransitionError("benchmark replay checkpoint variables drifted")
        for short_id, requested_value in requested_rows.items():
            previous_value = previous_rows[short_id]
            if (
                isinstance(previous_value, bool)
                or not isinstance(previous_value, int)
                or isinstance(requested_value, bool)
                or not isinstance(requested_value, int)
                or requested_value < previous_value
                or requested_value > row.window_end_row_id
            ):
                raise InvalidTransitionError("benchmark replay checkpoint moved outside its window")
            if status_only or requested_value == previous_value:
                continue
            ingested_count = int(
                await session.scalar(
                    select(func.count(func.distinct(ScadaSample.source_sequence))).where(
                        ScadaSample.source_id == CARE_REPLAY_SOURCE_ID,
                        ScadaSample.turbine_id == row.online_turbine_id,
                        ScadaSample.variable == variable_by_short_id[short_id],
                        ScadaSample.source_sequence > previous_value,
                        ScadaSample.source_sequence <= requested_value,
                    )
                )
                or 0
            )
            if ingested_count != requested_value - previous_value:
                raise InvalidTransitionError(
                    "benchmark replay checkpoint cannot skip unconfirmed ingest rows"
                )
        allowed_transitions = {
            "pending": {"pending", "running", "cancelled", "failed"},
            "running": {"running", "cancelling", "completed", "failed"},
            "cancelling": {"cancelling", "cancelled", "failed"},
        }
        if request.status not in allowed_transitions.get(row.status, set()):
            raise InvalidTransitionError("benchmark replay status transition is invalid")
        if request.status == "completed" and any(
            value != row.window_end_row_id for value in requested_rows.values()
        ):
            raise InvalidTransitionError("completed replay requires a complete checkpoint")
        row.status = request.status
        row.checkpoint = request.checkpoint
        row.checkpoint_revision = request.checkpoint_revision
        row.checkpoint_sha256 = request.checkpoint_sha256
        row.started_at = request.started_at
        row.finished_at = request.finished_at
        row.cancelled_by = request.cancelled_by
        row.error = request.error
        append_domain_event(
            session,
            event_type="benchmark.replay.progressed",
            aggregate_type="benchmark_replay_run",
            aggregate_id=row.id,
            payload={
                "benchmark_replay_run_id": row.id,
                "status": row.status,
                "checkpoint_revision": row.checkpoint_revision,
                "checkpoint_sha256": row.checkpoint_sha256,
                "online_turbine_id": row.online_turbine_id,
            },
        )
        await session.flush()
        return row, False
