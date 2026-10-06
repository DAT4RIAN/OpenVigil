"""Append actual follow-up handoffs without overwriting prior task or review evidence."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.model_structural_workflow import (
    StructuralHealthReview,
    StructuralRetestHandoff,
)
from windops_backend.models import Mission, WorkOrder, WorkOrderTask
from windops_backend.schema_structural import aware
from windops_backend.schema_structural_workflow import StructuralRetestSubmission
from windops_backend.services.events import append_domain_event
from windops_backend.services.structural import serialize
from windops_backend.services.structural_closure import assess_retest
from windops_backend.services.structural_missions import structural_mission_detail
from windops_backend.storage import ArtifactVerifier


async def submit_followup_retest(
    session: AsyncSession,
    work_order_id: str,
    payload: StructuralRetestSubmission,
    subject: str,
    verifier: ArtifactVerifier,
) -> dict[str, Any]:
    order = await session.scalar(
        select(WorkOrder).where(WorkOrder.id == work_order_id).with_for_update()
    )
    if order is None or order.closure_policy.get("kind") != "structural_retest":
        raise NotFoundError("structural work order was not found")
    mission = await session.scalar(
        select(Mission).where(Mission.id == order.mission_id).with_for_update()
    )
    if mission is None:
        raise NotFoundError("structural mission was not found")
    if mission.revision != payload.expected_mission_revision:
        raise ConflictError("mission revision changed; refresh the follow-up retest")
    last_review = await session.scalar(
        select(StructuralHealthReview)
        .where(StructuralHealthReview.work_order_id == order.id)
        .order_by(StructuralHealthReview.created_at.desc(), StructuralHealthReview.id.desc())
        .limit(1)
    )
    if (
        order.status != "awaiting_health_review"
        or not last_review
        or last_review.action != "requires_followup"
    ):
        raise InvalidTransitionError(
            "a follow-up retest requires a recorded unresolved health review"
        )
    context = await structural_mission_detail(session, mission.id)
    task = await session.scalar(
        select(WorkOrderTask)
        .where(WorkOrderTask.work_order_id == order.id)
        .order_by(WorkOrderTask.sequence.desc())
        .limit(1)
    )
    if task is None or task.status != "completed":
        raise InvalidTransitionError("the original field handoff must be completed")
    issues = list(Draft202012Validator(task.measurement_schema).iter_errors(payload.measurement))
    if issues:
        raise InvalidTransitionError("follow-up retest measurement failed its governed schema")
    assessment = await assess_retest(session, order, str(payload.measurement["retest_source_id"]))
    window = assessment["evidence_card"]["time_window"]
    if aware(datetime.fromisoformat(window["start"])) <= aware(last_review.created_at):
        raise InvalidTransitionError(
            "follow-up retest must be newly acquired after the unresolved health review"
        )
    try:
        await verifier.verify(
            payload.artifact_uri, payload.artifact_sha256, work_order_id=order.id, task_id=task.id
        )
    except ValueError as exc:
        raise InvalidTransitionError(str(exc)) from exc
    now = datetime.now(UTC)
    card = assessment["evidence_card"]
    if await session.scalar(
        select(StructuralRetestHandoff.id).where(
            StructuralRetestHandoff.work_order_id == order.id,
            StructuralRetestHandoff.source_fingerprint == card["source_fingerprint"],
        )
    ):
        raise ConflictError("this follow-up observation already has an immutable handoff")
    row = StructuralRetestHandoff(
        id=str(uuid4()),
        **{name: card[name] for name in ("tenant_id", "wind_farm_id", "turbine_id")},
        mission_id=mission.id,
        work_order_id=order.id,
        health_review_id=last_review.id,
        modal_id=assessment["retest_source_id"] if card["reference"]["kind"] == "modal" else None,
        prestress_id=assessment["retest_source_id"]
        if card["reference"]["kind"] == "prestress"
        else None,
        source_fingerprint=card["source_fingerprint"],
        task_id=task.id,
        artifact_uri=payload.artifact_uri,
        artifact_sha256=payload.artifact_sha256.lower(),
        measurement={
            **payload.measurement,
            "schema_version": task.schema_version,
            "followup_to_health_review_id": last_review.id,
            "context_sha256": context["context_sha256"],
            "handoff_result": payload.result,
        },
        verified_by=subject,
        verified_at=now,
    )
    session.add(row)
    changed = await session.execute(
        update(Mission)
        .where(Mission.id == mission.id, Mission.revision == payload.expected_mission_revision)
        .values(revision=payload.expected_mission_revision + 1, updated_at=now)
        .returning(Mission.id)
        .execution_options(synchronize_session="fetch")
    )
    if changed.scalar_one_or_none() is None:
        raise ConflictError("a concurrent retest changed this mission")
    append_domain_event(
        session,
        event_type="structural.retest.followup_submitted",
        aggregate_type="work_order",
        aggregate_id=order.id,
        payload={
            "work_order_id": order.id,
            "mission_id": mission.id,
            "turbine_id": order.turbine_id,
            "retest_source_id": assessment["retest_source_id"],
            "evidence_id": row.id,
            "verified_by": subject,
        },
    )
    await session.flush()
    return {
        "evidence": serialize(row),
        "mission_revision": mission.revision,
        "work_order_status": order.status,
    }
