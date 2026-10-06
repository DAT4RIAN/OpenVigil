import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.model_base import utcnow
from windops_backend.model_structural import (
    ModalObservation,
    StructuralAnalysisRun,
    WaveformRecord,
)
from windops_backend.outbox import OutboxLeaseLostError, assert_current_claim, claim_event
from windops_backend.services.events import append_domain_event
from windops_backend.services.idempotency import canonical_request_hash
from windops_backend.services.structural import (
    STRUCTURAL_ANALYSIS_REQUESTED,
    serialize,
    verified_input,
)
from windops_backend.storage import ArtifactVerifier, OutboxEvent
from windops_backend.structural_process import StructuralComputationFailure, compute_waveform
from windops_backend.structural_provenance import deployment_identity, execution_provenance
from windops_backend.structural_result_identity import RESULT_HASH_CONTRACT, structural_result_hash

if TYPE_CHECKING:
    from windops_backend.config import Settings

logger = logging.getLogger(__name__)
MAX_STRUCTURAL_ATTEMPTS = 3


class StructuralAlgorithmVersionMismatch(RuntimeError):
    pass


async def expired_structural_events(
    factory: async_sessionmaker[AsyncSession], limit: int = 50
) -> list[tuple[str, str]]:
    # A worker killed after a claim leaves a processing row without a retry
    # message. Recover only this queue's expired claims, without changing the
    # existing business relay's visibility semantics.
    async with factory() as session:
        rows = (
            await session.execute(
                select(OutboxEvent.id, OutboxEvent.event_type)
                .where(
                    OutboxEvent.event_type == STRUCTURAL_ANALYSIS_REQUESTED,
                    OutboxEvent.status == "processing",
                    OutboxEvent.lease_expires_at <= utcnow(),
                )
                .order_by(OutboxEvent.created_at)
                .limit(limit)
            )
        ).all()
        return [(str(identity), str(event_type)) for identity, event_type in rows]


async def process_structural_event(
    factory: async_sessionmaker[AsyncSession],
    verifier: ArtifactVerifier,
    bucket: str,
    event_id: str,
    *,
    settings: "Settings | None" = None,
) -> bool:
    async with factory() as session, session.begin():
        event = await session.get(OutboxEvent, event_id)
        if event is None or event.event_type != STRUCTURAL_ANALYSIS_REQUESTED:
            return False
        event = await claim_event(session, event_id)
        if event is None:
            return False
        token = str(event.claim_token)
        run_id = event.aggregate_id
        run = await session.get(StructuralAnalysisRun, run_id)
        if run is None:
            raise RuntimeError("structural outbox references a missing run")
        if run.status in {"succeeded", "insufficient_data", "failed"}:
            event.status = "succeeded"
            event.claim_token = None
            event.lease_expires_at = None
            event.processed_at = utcnow()
            return True
        run.status = "running"
        run.attempts = event.attempts
        if event.attempts > MAX_STRUCTURAL_ATTEMPTS:
            run.status = "failed"
            run.error_code = "StructuralAttemptsExhausted"
            run.completed_at = utcnow()
            event.status = "failed"
            event.last_error = "StructuralAttemptsExhausted"
            event.claim_token = None
            event.lease_expires_at = None
            event.processed_at = utcnow()
            append_domain_event(
                session,
                event_type="structural.analysis.failed",
                aggregate_type="turbine",
                aggregate_id=run.turbine_id,
                payload={
                    "run_id": run.id,
                    "turbine_id": run.turbine_id,
                    "status": run.status,
                    "error_code": run.error_code,
                },
            )
            return True
        record = await session.get(WaveformRecord, run.record_id)
        if record is None:
            raise RuntimeError("structural run references a missing acquisition")
        snapshot = serialize(record)
        # JSON encoding of SQLite timestamps needs an explicit UTC suffix.
        for name in ("started_at", "ended_at"):
            if not snapshot[name].endswith("Z") and "+" not in snapshot[name]:
                snapshot[name] += "+00:00"
        config = dict(run.config)
        expected_algorithm = dict(run.algorithm_identity)
    try:
        if "deployment_declared" in expected_algorithm and not isinstance(
            expected_algorithm["deployment_declared"], dict
        ):
            raise StructuralAlgorithmVersionMismatch("invalid queued deployment declaration")
        expected_deployment = expected_algorithm.pop("deployment_declared", None)
        try:
            declared = deployment_identity(settings, "structural-worker") if settings else None
        except ValueError as exc:
            raise StructuralAlgorithmVersionMismatch(
                "invalid worker deployment declaration"
            ) from exc
        if expected_deployment != declared:
            raise StructuralAlgorithmVersionMismatch(
                "worker release bundle changed after the run was queued"
            )
        content = await verified_input(
            verifier,
            bucket,
            snapshot["turbine_id"],
            snapshot["artifact_uri"],
            snapshot["artifact_sha256"],
        )
        result = await compute_waveform(content, snapshot, config)
        actual_algorithm = result.get("algorithm", {})
        if any(actual_algorithm.get(key) != value for key, value in expected_algorithm.items()):
            raise StructuralAlgorithmVersionMismatch(
                "worker implementation changed after the run was queued"
            )
        result["execution_provenance"] = execution_provenance(declared, actual_algorithm)
        if declared is not None:
            actual_algorithm["deployment_declared"] = dict(declared)
        result["input"] = {
            "record_id": snapshot["id"],
            "turbine_id": snapshot["turbine_id"],
            "artifact_sha256": snapshot["artifact_sha256"],
            "input_fingerprint": snapshot["input_fingerprint"],
            "channel_revisions": [
                {
                    "id": c["id"],
                    "revision": c["revision"],
                    "calibration_version": c["calibration_version"],
                }
                for c in snapshot["channel_snapshot"]
            ],
        }
        result["config_sha256"] = canonical_request_hash(config)
        result["result_hash_contract"] = RESULT_HASH_CONTRACT
        result["result_sha256"] = structural_result_hash(result)
        async with factory() as session, session.begin():
            await assert_current_claim(session, event_id, token)
            run = await session.get(StructuralAnalysisRun, run_id)
            if run is None:
                raise RuntimeError("structural run disappeared")
            run.status = "succeeded" if result["quality"]["usable"] else "insufficient_data"
            run.result = result
            run.error_code = None
            run.completed_at = utcnow()
            for index, mode in enumerate(result["modes"]):
                session.add(
                    ModalObservation(
                        tenant_id=run.tenant_id,
                        wind_farm_id=run.wind_farm_id,
                        turbine_id=run.turbine_id,
                        run_id=run.id,
                        mode_index=index,
                        frequency_hz=mode["frequency_hz"],
                        mode_shape=mode["mode_shape"],
                        quality=mode["quality"],
                        uncertainty=mode["uncertainty"],
                    )
                )
            append_domain_event(
                session,
                event_type="structural.analysis.completed",
                aggregate_type="turbine",
                aggregate_id=run.turbine_id,
                payload={
                    "run_id": run.id,
                    "turbine_id": run.turbine_id,
                    "status": run.status,
                    "result_sha256": result["result_sha256"],
                },
            )
            await _finish_event(session, event_id, "succeeded")
        return True
    except OutboxLeaseLostError:
        # The newer lease owns the result; stale observations never commit.
        return False
    except Exception as exc:
        logger.exception("Structural analysis failed for run %s", run_id)
        async with factory() as session, session.begin():
            try:
                await assert_current_claim(session, event_id, token)
            except OutboxLeaseLostError:
                return False
            run = await session.get(StructuralAnalysisRun, run_id)
            event = await session.get(OutboxEvent, event_id)
            if run is None or event is None:
                raise RuntimeError("structural failure ledger disappeared") from exc
            run.error_code = (
                exc.error_code
                if isinstance(exc, StructuralComputationFailure)
                else type(exc).__name__
            )
            # Invalid input cannot improve on retry. Infra errors get bounded retries
            # from the relay, with terminal exhaustion retained in both ledgers.
            terminal = (
                isinstance(exc, (ValueError, RuntimeError))
                or event.attempts >= MAX_STRUCTURAL_ATTEMPTS
            )
            run.status = "failed" if terminal else "pending"
            run.completed_at = utcnow() if terminal else None
            event.last_error = f"{type(exc).__name__}: inspect secured structural worker logs"
            await _finish_event(session, event_id, "failed" if terminal else "pending")
            append_domain_event(
                session,
                event_type="structural.analysis.failed",
                aggregate_type="turbine",
                aggregate_id=run.turbine_id,
                payload={
                    "run_id": run.id,
                    "turbine_id": run.turbine_id,
                    "status": run.status,
                    "error_code": run.error_code,
                },
            )
        return True


async def _finish_event(session: AsyncSession, event_id: str, status: str) -> None:
    event = await session.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id))
    if event is None:
        raise RuntimeError("structural outbox event disappeared")
    event.status = status
    event.claim_token = None
    event.lease_expires_at = None
    event.processed_at = utcnow() if status in {"succeeded", "failed"} else None
