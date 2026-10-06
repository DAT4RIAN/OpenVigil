"""Append command rows in the caller's transaction without importing event processors."""

from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.storage import OutboxEvent

MISSION_ANALYSIS_REQUESTED = "mission.analysis.requested"
KNOWLEDGE_GRAPH_PROJECTION_REQUESTED = "knowledge-graph.projection.requested"


def enqueue_mission_analysis(session: AsyncSession, mission_id: str) -> OutboxEvent:
    event = OutboxEvent(
        event_type=MISSION_ANALYSIS_REQUESTED,
        aggregate_type="mission",
        aggregate_id=mission_id,
        payload={"mission_id": mission_id},
    )
    session.add(event)
    return event


def enqueue_knowledge_graph_projection(
    session: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: str,
    reason: str,
) -> OutboxEvent:
    """Request an idempotent rebuild of the derived graph projection.

    The row is committed in the same PostgreSQL transaction as the authoritative
    business mutation. Replaying it is safe because the projector replaces the
    named Neo4j projection from current SQL state.
    """

    event = OutboxEvent(
        event_type=KNOWLEDGE_GRAPH_PROJECTION_REQUESTED,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload={
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "reason": reason,
        },
    )
    session.add(event)
    return event
