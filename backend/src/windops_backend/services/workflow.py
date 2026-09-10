from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.agents.graph import WindOpsWorkflowGraph
from windops_backend.agents.reasoning import build_reasoning_provider
from windops_backend.agents.state import PublicWorkflowState
from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.config import Settings
from windops_backend.enums import ApprovalAction, DecisionStatus, MissionStatus
from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import Alarm, Approval, Decision, Mission, Turbine, WindFarm, WorkOrder
from windops_backend.outbox import enqueue_knowledge_graph_projection, enqueue_mission_analysis
from windops_backend.schemas import ApprovalRequest
from windops_backend.services.eam import enqueue_eam_work_order_publish
from windops_backend.services.events import append_domain_event


def _persistable_state(state: PublicWorkflowState) -> dict[str, Any]:
    value = dict(state)
    value.pop("resume_from", None)
    return value


async def _mission_knowledge_policy(session: AsyncSession, turbine_id: str) -> GraphAccessPolicy:
    row = (
        await session.execute(
            select(Turbine, WindFarm)
            .join(WindFarm, WindFarm.id == Turbine.wind_farm_id)
            .where(Turbine.id == turbine_id)
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError(f"turbine {turbine_id} was not found")
    _, farm = row
    # Knowledge documents created with a farm or turbine target are resolved
    # to their authoritative tenant as well. The workflow therefore carries
    # the mission tenant boundary, while the relational case query below
    # still narrows evidence to the mission turbine.
    return GraphAccessPolicy.from_values(
        tenant_ids=[farm.tenant_id],
        data_scopes=["knowledge"],
        allow_global=True,
    )


async def advance_mission_to_review(
    session: AsyncSession, settings: Settings, mission_id: str
) -> Mission:
    mission = await session.get(Mission, mission_id)
    if mission is None:
        raise NotFoundError(f"mission {mission_id} was not found")
    if mission.status == MissionStatus.UNDER_REVIEW.value:
        return mission
    is_revision = mission.status == MissionStatus.INVESTIGATING.value
    if mission.status not in {
        MissionStatus.DETECTED.value,
        MissionStatus.INVESTIGATING.value,
    }:
        raise InvalidTransitionError(
            f"mission {mission_id} cannot enter analysis from {mission.status}"
        )

    if is_revision:
        decision = await session.scalar(select(Decision).where(Decision.mission_id == mission.id))
        if decision is None or decision.status != DecisionStatus.REVISION_REQUESTED.value:
            raise InvalidTransitionError("revision analysis requires a revision-requested decision")
        # Re-open the proposal inside the graph transaction. If the graph fails,
        # this reset rolls back with the rest of the revised analysis.
        decision.status = DecisionStatus.PENDING_APPROVAL.value
        decision.approval_id = None
        decision.updated_at = datetime.now(UTC)

    state: PublicWorkflowState = {
        "mission_id": mission.id,
        "turbine_id": mission.turbine_id,
        "alarm_id": mission.alarm_id,
        "analysis_profile": mission.public_state.get("analysis_profile", {}),
        "workflow_status": (
            MissionStatus.INVESTIGATING.value if is_revision else MissionStatus.DETECTED.value
        ),
        "evidence": [],
    }
    graph = WindOpsWorkflowGraph(
        session,
        SQLToolAdapter(
            session,
            settings=settings,
            knowledge_policy=await _mission_knowledge_policy(session, mission.turbine_id),
        ),
        build_reasoning_provider(settings),
    )
    final_state = await graph.invoke(state)
    if final_state.get("workflow_status") != MissionStatus.UNDER_REVIEW.value:
        raise RuntimeError("workflow did not reach the human-review boundary")
    mission.status = MissionStatus.UNDER_REVIEW.value
    mission.public_state = _persistable_state(final_state)
    mission.revision += 1
    mission.updated_at = datetime.now(UTC)
    alarm = await session.get(Alarm, mission.alarm_id)
    if alarm is not None:
        alarm.ai_status = "awaiting_human_approval"
    enqueue_knowledge_graph_projection(
        session,
        aggregate_type="mission",
        aggregate_id=mission.id,
        reason="mission-analysis-completed",
    )
    append_domain_event(
        session,
        event_type="mission.review_ready",
        aggregate_type="mission",
        aggregate_id=mission.id,
        payload={
            "mission_id": mission.id,
            "turbine_id": mission.turbine_id,
            "decision_id": final_state.get("decision_id"),
            "status": mission.status,
            "revision": mission.revision,
        },
    )
    await session.flush()
    return mission


async def record_approval(
    session: AsyncSession,
    settings: Settings,
    mission_id: str,
    request: ApprovalRequest,
) -> tuple[Mission, Approval, WorkOrder | None]:
    mission = await session.scalar(
        select(Mission).where(Mission.id == mission_id).with_for_update()
    )
    if mission is None:
        raise NotFoundError(f"mission {mission_id} was not found")
    if mission.status != MissionStatus.UNDER_REVIEW.value:
        raise InvalidTransitionError(f"mission {mission_id} is not waiting for human approval")
    if mission.revision != request.expected_revision:
        raise ConflictError(
            f"mission revision is {mission.revision}, not {request.expected_revision}"
        )
    decision = await session.scalar(select(Decision).where(Decision.mission_id == mission.id))
    if decision is None:
        raise RuntimeError("mission reached approval without a persisted decision")
    selected_alternative_id: str | None = None
    if request.action is ApprovalAction.APPROVE:
        selected_alternative_id = (
            request.selected_alternative_id or decision.recommended_alternative_id
        )
        if selected_alternative_id not in {
            str(item.get("alternative_id")) for item in decision.alternatives
        }:
            raise InvalidTransitionError(
                "the selected alternative does not belong to this decision"
            )
        decision.selected_alternative_id = selected_alternative_id
    elif request.selected_alternative_id is not None:
        raise InvalidTransitionError("only approval may select a maintenance alternative")

    approval = Approval(
        id=str(uuid4()),
        mission_id=mission.id,
        mission_revision=mission.revision,
        action=request.action.value,
        selected_alternative_id=selected_alternative_id,
        approver=request.approver,
        reason=request.reason,
        comment=request.comment,
    )
    session.add(approval)
    await session.flush()

    work_order: WorkOrder | None = None
    if request.action is ApprovalAction.APPROVE:
        mission.status = MissionStatus.APPROVED.value
        mission.updated_at = datetime.now(UTC)
        await session.flush()  # approval gate reads this state before any execution write
        resume_state = cast(
            PublicWorkflowState,
            {
                **mission.public_state,
                "mission_id": mission.id,
                "turbine_id": mission.turbine_id,
                "alarm_id": mission.alarm_id,
                "approved": True,
                "approval_id": approval.id,
                "resume_from": "workorder",
            },
        )
        graph = WindOpsWorkflowGraph(
            session,
            SQLToolAdapter(
                session,
                settings=settings,
                knowledge_policy=await _mission_knowledge_policy(session, mission.turbine_id),
            ),
            build_reasoning_provider(settings),
        )
        final_state = await graph.invoke(resume_state)
        work_order_id = final_state.get("work_order_id")
        if not work_order_id:
            raise RuntimeError("approved workflow did not create a work order")
        work_order = await session.get(WorkOrder, work_order_id)
        mission.status = MissionStatus.EXECUTING.value
        mission.public_state = _persistable_state(final_state)
    elif request.action is ApprovalAction.REJECT:
        decision.status = DecisionStatus.REJECTED.value
        decision.approval_id = approval.id
        decision.updated_at = datetime.now(UTC)
        mission.status = MissionStatus.REJECTED.value
        mission.public_state = {**mission.public_state, "workflow_status": "rejected"}
    elif request.action is ApprovalAction.REQUEST_REVISION:
        decision.status = DecisionStatus.REVISION_REQUESTED.value
        decision.approval_id = approval.id
        decision.updated_at = datetime.now(UTC)
        mission.status = MissionStatus.INVESTIGATING.value
        mission.public_state = {
            **mission.public_state,
            "workflow_status": "revision_requested",
        }
        enqueue_mission_analysis(session, mission.id)
        alarm = await session.get(Alarm, mission.alarm_id)
        if alarm is not None:
            alarm.ai_status = "revision_queued"
    else:
        # Escalation is an approval event, not the approval that authorizes a
        # work order. Keep the Decision open so a later revision-guarded approve
        # can supply the actual approval id.
        decision.status = DecisionStatus.PENDING_APPROVAL.value
        decision.updated_at = datetime.now(UTC)
        mission.status = MissionStatus.UNDER_REVIEW.value
        mission.public_state = {
            **mission.public_state,
            "workflow_status": "under_review",
            "escalation": {
                "approval_id": approval.id,
                "reason": request.reason,
                "comment": request.comment,
            },
        }

    mission.revision += 1
    mission.updated_at = datetime.now(UTC)
    append_domain_event(
        session,
        event_type=f"mission.approval.{request.action.value}",
        aggregate_type="mission",
        aggregate_id=mission.id,
        payload={
            "mission_id": mission.id,
            "approval_id": approval.id,
            "action": request.action.value,
            "selected_alternative_id": selected_alternative_id,
            "status": mission.status,
            "revision": mission.revision,
            "recorded_by": approval.approver,
        },
    )
    if work_order is not None:
        append_domain_event(
            session,
            event_type="work_order.created",
            aggregate_type="work_order",
            aggregate_id=work_order.id,
            payload={
                "work_order_id": work_order.id,
                "mission_id": mission.id,
                "turbine_id": work_order.turbine_id,
                "status": work_order.status,
                "selected_alternative_id": work_order.selected_alternative_id,
            },
        )
        if settings.eam_enabled:
            enqueue_eam_work_order_publish(session, work_order.id)
    enqueue_knowledge_graph_projection(
        session,
        aggregate_type="mission",
        aggregate_id=mission.id,
        reason=f"approval-{request.action.value}",
    )
    await session.flush()
    return mission, approval, work_order
