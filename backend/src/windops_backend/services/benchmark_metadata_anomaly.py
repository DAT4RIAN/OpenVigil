from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.models import (
    AnomalyAlertPolicyState,
    ModelDeployment,
    ModelPrediction,
    Turbine,
)
from windops_backend.schemas import (
    AnomalyAlertPolicyStateRequest,
)
from windops_backend.services.benchmark_metadata_contracts import (
    _claim_identity,
    _same_instant,
)


async def persist_anomaly_alert_policy_state(
    session: AsyncSession,
    request: AnomalyAlertPolicyStateRequest,
) -> tuple[AnomalyAlertPolicyState, bool]:
    scope = (
        f"anomaly-alert-policy:{request.deployment_id}:{request.turbine_id}:"
        f"{request.component}:{request.policy_version}"
    )
    async with _claim_identity(session, scope):
        existing = await session.scalar(
            select(AnomalyAlertPolicyState)
            .where(
                AnomalyAlertPolicyState.deployment_id == request.deployment_id,
                AnomalyAlertPolicyState.turbine_id == request.turbine_id,
                AnomalyAlertPolicyState.component == request.component,
                AnomalyAlertPolicyState.policy_version == request.policy_version,
            )
            .with_for_update()
        )
        if existing is not None:
            same_state = (
                existing.id == request.policy_state_id
                and existing.policy_sha256 == request.policy_sha256
                and existing.phase == request.phase
                and existing.consecutive_trigger_count == request.consecutive_trigger_count
                and existing.consecutive_recovery_count == request.consecutive_recovery_count
                and _same_instant(existing.cooldown_until, request.cooldown_until)
                and existing.last_prediction_id == request.last_prediction_id
                and _same_instant(
                    existing.last_prediction_created_at,
                    request.last_prediction_created_at,
                )
                and existing.dedup_key == request.dedup_key
                and existing.policy_document == request.policy_document
                and existing.state_document == request.state_document
                and existing.revision == request.revision
            )
            if same_state:
                return existing, True
            if existing.id != request.policy_state_id:
                raise ConflictError("alert-policy scope already belongs to another state ID")
            if (
                existing.policy_sha256 != request.policy_sha256
                or existing.policy_document != request.policy_document
            ):
                raise ConflictError("alert-policy document is immutable within a policy version")
            if request.revision != existing.revision + 1:
                raise ConflictError("alert-policy state update requires the next revision")
        elif request.revision != 0:
            raise ConflictError("new alert-policy state must start at revision zero")

        deployment = await session.get(ModelDeployment, request.deployment_id)
        turbine = await session.get(Turbine, request.turbine_id)
        if deployment is None or turbine is None:
            raise NotFoundError("alert-policy deployment or turbine was not found")
        if request.last_prediction_id is not None:
            prediction = await session.get(ModelPrediction, request.last_prediction_id)
            if prediction is None:
                raise NotFoundError("alert-policy prediction was not found")
            if (
                prediction.deployment_id != request.deployment_id
                or prediction.turbine_id != request.turbine_id
            ):
                raise InvalidTransitionError(
                    "alert-policy prediction crosses deployment or turbine scope"
                )

        if existing is None:
            existing = AnomalyAlertPolicyState(
                id=request.policy_state_id,
                deployment_id=request.deployment_id,
                turbine_id=request.turbine_id,
                component=request.component,
                policy_version=request.policy_version,
                policy_sha256=request.policy_sha256,
                phase=request.phase,
                consecutive_trigger_count=request.consecutive_trigger_count,
                consecutive_recovery_count=request.consecutive_recovery_count,
                cooldown_until=request.cooldown_until,
                last_prediction_id=request.last_prediction_id,
                last_prediction_created_at=request.last_prediction_created_at,
                dedup_key=request.dedup_key,
                policy_document=request.policy_document,
                state_document=request.state_document,
                revision=request.revision,
            )
            session.add(existing)
        else:
            existing.phase = request.phase
            existing.consecutive_trigger_count = request.consecutive_trigger_count
            existing.consecutive_recovery_count = request.consecutive_recovery_count
            existing.cooldown_until = request.cooldown_until
            existing.last_prediction_id = request.last_prediction_id
            existing.last_prediction_created_at = request.last_prediction_created_at
            existing.dedup_key = request.dedup_key
            existing.state_document = request.state_document
            existing.revision = request.revision
            existing.updated_at = datetime.now(UTC)
        await session.flush()
        return existing, False
