"""Compatibility and shared-state regressions for the current refactor."""

import tracemalloc

from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend import outbox, outbox_commands
from windops_backend.agents import reasoning, reasoning_contracts
from windops_backend.knowledge_graph import (
    projection,
    projection_budget,
    projection_builder,
    projection_rows,
    projection_values,
)
from windops_backend.services import knowledge, knowledge_contracts


def test_existing_imports_resolve_to_the_same_contract_objects() -> None:
    assert outbox.enqueue_mission_analysis is outbox_commands.enqueue_mission_analysis
    assert (
        outbox.enqueue_knowledge_graph_projection
        is outbox_commands.enqueue_knowledge_graph_projection
    )
    assert reasoning.AlternativeBundle is reasoning_contracts.AlternativeBundle
    assert reasoning.ReviewBundle is reasoning_contracts.ReviewBundle
    assert reasoning.ReasoningEvaluationError is reasoning_contracts.ReasoningEvaluationError
    assert reasoning._review_target is reasoning_contracts._review_target
    assert projection.ProjectionLimits is projection_budget.ProjectionLimits
    assert projection.ProjectionLimitExceeded is projection_budget.ProjectionLimitExceeded
    assert projection._ProjectionBudget is projection_budget._ProjectionBudget
    assert projection._ProjectionBuilder is projection_builder._ProjectionBuilder
    assert projection._iter_bounded_scalar_rows is projection_rows._iter_bounded_scalar_rows
    assert projection._json is projection_values._json
    assert (
        knowledge.ALLOWED_KNOWLEDGE_CONTENT_TYPES
        is knowledge_contracts.ALLOWED_KNOWLEDGE_CONTENT_TYPES
    )


async def test_outbox_commands_remain_in_the_callers_transaction() -> None:
    async with AsyncSession() as session:
        mission = outbox_commands.enqueue_mission_analysis(session, "mission-contract")
        graph = outbox.enqueue_knowledge_graph_projection(
            session,
            aggregate_type="mission",
            aggregate_id="mission-contract",
            reason="structural.reviewed",
        )
        assert set(session.new) == {mission, graph}
        assert mission.event_type == outbox.MISSION_ANALYSIS_REQUESTED
        assert graph.event_type == outbox.KNOWLEDGE_GRAPH_PROJECTION_REQUESTED
        assert graph.payload == {
            "aggregate_type": "mission",
            "aggregate_id": "mission-contract",
            "reason": "structural.reviewed",
        }
        await session.rollback()
        assert not session.new
        assert mission not in session
        assert graph not in session


def test_shared_projection_samplers_do_not_stop_a_live_or_external_trace() -> None:
    external_trace = tracemalloc.is_tracing()
    first = projection._PythonPeakMemorySampler()
    second = projection_budget._PythonPeakMemorySampler()
    try:
        first.close()
        first.close()
        assert tracemalloc.is_tracing()
        second.sample()
    finally:
        first.close()
        second.close()
    assert tracemalloc.is_tracing() == external_trace

    if external_trace:
        return
    tracemalloc.start(1)
    try:
        sampler = projection_budget._PythonPeakMemorySampler()
        sampler.close()
        assert tracemalloc.is_tracing()
    finally:
        tracemalloc.stop()
