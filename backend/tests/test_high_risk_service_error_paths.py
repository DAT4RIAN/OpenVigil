from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from windops_backend.config import Settings
from windops_backend.enums import ApprovalAction, Environment, MissionStatus
from windops_backend.errors import ConflictError, DomainError, InvalidTransitionError, NotFoundError
from windops_backend.schemas import ApprovalRequest, MissionAnalysisProfile, MissionCreateRequest
from windops_backend.services.agent_governance import control_agent, create_agent_release
from windops_backend.services.alarms import execute_alarm_command
from windops_backend.services.missions import AlarmAlreadyAssignedError, create_mission
from windops_backend.services.workflow import advance_mission_to_review, record_approval


def _mission_payload() -> MissionCreateRequest:
    return MissionCreateRequest(
        alarm_id="ALARM-SERVICE-001",
        title="Service error-path mission",
        analysis_profile=MissionAnalysisProfile(
            component="bearing",
            primary_variable="vibration_rms",
            knowledge_query="bearing inspection evidence",
        ),
    )


@pytest.mark.asyncio
async def test_mission_service_rejects_invalid_missing_and_duplicate_inputs() -> None:
    session = AsyncMock()
    with pytest.raises(DomainError):
        await create_mission(session, _mission_payload(), idempotency_key="short", subject="tester")

    session.scalar.return_value = None
    with pytest.raises(NotFoundError):
        await create_mission(
            session,
            _mission_payload(),
            idempotency_key="mission-service-missing-001",
            subject="tester",
        )

    session.scalar.side_effect = [
        None,
        SimpleNamespace(id="ALARM-SERVICE-001", turbine_id="WT-SERVICE-001"),
        SimpleNamespace(id="MISSION-EXISTING-001"),
    ]
    session.get.return_value = SimpleNamespace(id="WT-SERVICE-001")
    with pytest.raises(AlarmAlreadyAssignedError):
        await create_mission(
            session,
            _mission_payload(),
            idempotency_key="mission-service-duplicate-001",
            subject="tester",
        )


@pytest.mark.asyncio
async def test_alarm_service_rejects_invalid_key_and_missing_alarm() -> None:
    session = AsyncMock()
    payload = SimpleNamespace(expected_revision=1, model_dump=lambda **_: {}, action="assign")
    with pytest.raises(DomainError):
        await execute_alarm_command(
            session,
            "ALARM-SERVICE-001",
            payload,
            idempotency_key="short",
            subject="tester",
        )

    session.scalar.return_value = None
    with pytest.raises(NotFoundError):
        await execute_alarm_command(
            session,
            "ALARM-SERVICE-MISSING",
            payload,
            idempotency_key="alarm-service-missing-001",
            subject="tester",
        )


@pytest.mark.asyncio
async def test_agent_governance_rejects_missing_and_stale_definitions() -> None:
    session = AsyncMock()
    session.scalar.return_value = None
    with pytest.raises(NotFoundError):
        await control_agent(
            session,
            agent_key="missing-agent",
            expected_definition_id="definition-1",
            enabled=True,
            reason="fixture",
            subject="tester",
        )

    session.scalar.return_value = SimpleNamespace(id="definition-actual")
    with pytest.raises(ConflictError):
        await control_agent(
            session,
            agent_key="agent",
            expected_definition_id="definition-stale",
            enabled=False,
            reason="fixture",
            subject="tester",
        )

    session.get.return_value = None
    with pytest.raises(NotFoundError):
        await create_agent_release(
            session,
            agent_key="agent",
            request=SimpleNamespace(source_definition_id="missing"),
            subject="tester",
        )


@pytest.mark.asyncio
async def test_workflow_rejects_missing_or_invalid_transition_states() -> None:
    settings = Settings(environment=Environment.TEST)
    session = AsyncMock()
    session.get.return_value = None
    with pytest.raises(NotFoundError):
        await advance_mission_to_review(session, settings, "MISSION-MISSING")

    under_review = SimpleNamespace(status=MissionStatus.UNDER_REVIEW.value)
    session.get.return_value = under_review
    assert await advance_mission_to_review(session, settings, "MISSION-REVIEW") is under_review

    session.scalar.return_value = None
    with pytest.raises(NotFoundError):
        await record_approval(
            session,
            settings,
            "MISSION-MISSING",
            ApprovalRequest(
                action=ApprovalAction.APPROVE,
                expected_revision=1,
                approver="tester",
                reason="fixture approval",
            ),
        )

    session.scalar.return_value = SimpleNamespace(
        id="MISSION-INVALID", status=MissionStatus.DETECTED.value, revision=1
    )
    with pytest.raises(InvalidTransitionError):
        await record_approval(
            session,
            settings,
            "MISSION-INVALID",
            ApprovalRequest(
                action=ApprovalAction.APPROVE,
                expected_revision=1,
                approver="tester",
                reason="fixture approval",
            ),
        )
