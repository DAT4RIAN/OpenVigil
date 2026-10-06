"""Independent health review of actual post-work retest; no handwritten scores or restart."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from windops_backend.config import Settings
from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.model_structural_workflow import (
    StructuralCaseReview,
    StructuralHealthReview,
    StructuralRetestHandoff,
)
from windops_backend.models import (
    Alarm,
    HealthBaseline,
    KnowledgeCase,
    Mission,
    ModalObservation,
    PrestressObservation,
    Resource,
    ResourceReservation,
    StructuralAnalysisRun,
    WaveformRecord,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.schema_engineering_claim import EngineeringEvidenceReference
from windops_backend.schema_structural import aware
from windops_backend.schema_structural_workflow import (
    StructuralCaseReviewRequest,
    StructuralHealthReviewRequest,
)
from windops_backend.services.engineering_claims import build_evidence_card, verify_card_sources
from windops_backend.services.events import append_domain_event
from windops_backend.services.structural import related, serialize, verified_input
from windops_backend.services.structural_missions import (
    require_reviewed_structural_claim,
    structural_mission_detail,
)
from windops_backend.storage import ArtifactVerifier, FieldTaskEvidence
from windops_backend.structural_baseline import compare_to_baseline


def reviewed_case_clause() -> ColumnElement[bool]:
    """Legacy cases remain readable; structural cases require independent retrieval approval."""
    table = StructuralCaseReview.__table__
    attached = exists(select(1).where(table.c.case_id == KnowledgeCase.id))
    approved = exists(
        select(1).where(table.c.case_id == KnowledgeCase.id, table.c.status == "approved")
    )
    return or_(~attached, approved)


async def assess_retest(session: AsyncSession, order: WorkOrder, source_id: str) -> dict[str, Any]:
    context = await structural_mission_detail(session, order.mission_id)
    frozen = context["request"]
    if source_id == frozen["source_id"]:
        raise InvalidTransitionError(
            "an original observation cannot be reused as the post-work retest"
        )
    kind: Literal["modal", "prestress"] = (
        "modal" if context["scenario"] == "modal_frequency_review" else "prestress"
    )
    card = await build_evidence_card(
        session,
        EngineeringEvidenceReference(kind=kind, source_id=source_id, relation="supports"),
        turbine_id=order.turbine_id,
        component_id=context["component_id"],
    )
    window = card["time_window"]
    if aware(datetime.fromisoformat(window["start"])) < aware(order.created_at) or aware(
        datetime.fromisoformat(window["end"])
    ) > datetime.now(UTC):
        raise InvalidTransitionError(
            "retest must be acquired after the work order was created and cannot be future dated"
        )
    original = context["evidence_cards"][0]
    if card["source"]["source_kind"] != original["source"]["source_kind"]:
        raise InvalidTransitionError("retest source kind differs from the frozen mission")
    reasons: list[str] = []
    if not card["quality"].get("usable"):
        reasons.append("retest_quality_unusable")
    if card["valid_until"] and aware(datetime.fromisoformat(card["valid_until"])) <= datetime.now(
        UTC
    ):
        reasons.append("retest_calibration_expired")
    comparison: dict[str, Any] = {"status": "not_applicable", "damage_probability": None}
    if kind == "modal":
        mode = await related(session, ModalObservation, source_id, order.turbine_id)
        run = await related(session, StructuralAnalysisRun, mode.run_id, order.turbine_id)
        record = await related(session, WaveformRecord, run.record_id, order.turbine_id)
        if card["method"] != original["method"]:
            reasons.append("method_channel_or_calibration_changed")
        baseline_id = frozen.get("baseline_id")
        if baseline_id:
            baseline = await related(session, HealthBaseline, baseline_id, order.turbine_id)
            if aware(baseline.valid_until) <= datetime.now(UTC):
                reasons.append("baseline_expired")
            else:
                comparison = compare_to_baseline(baseline.model, serialize(run), serialize(record))
                if comparison["status"] != "within_screening_range":
                    reasons.extend(comparison.get("exclusions", []))
                    reasons.append("modal_comparison_not_within_screening_range")
        else:
            reasons.append("confirmed_environmental_baseline_missing")
    else:
        observation = await related(session, PrestressObservation, source_id, order.turbine_id)
        origin = await related(session, PrestressObservation, frozen["source_id"], order.turbine_id)
        if (
            observation.sensor_id != origin.sensor_id
            or observation.tendon_id != origin.tendon_id
            or observation.calibration_version != origin.calibration_version
            or card["method"] != original["method"]
        ):
            reasons.append("force_sensor_tendon_or_calibration_changed")
        acceptance = frozen.get("force_acceptance")
        if acceptance:
            # The exact quoted source and numeric bounds were frozen in the independently
            # reviewed proposal, then approved as part of this execution plan.
            within = acceptance["minimum_kn"] <= observation.value_kn <= acceptance["maximum_kn"]
            comparison = {
                "status": "within_reviewed_force_bounds" if within else "requires_review",
                "value_kn": observation.value_kn,
                "change_kn": observation.value_kn - origin.value_kn,
                "acceptance": acceptance,
                "damage_probability": None,
            }
            if not within:
                reasons.append("force_outside_reviewed_acceptance_bounds")
        else:
            reasons.append("human_reviewed_force_acceptance_procedure_missing")
    return {
        "retest_source_id": source_id,
        "evidence_card": card,
        "comparison": comparison,
        "eligible_to_resolve_review": not reasons,
        "exclusions": list(dict.fromkeys(reasons)),
        "field_qualification": "unverified",
        "authorizes_operation": False,
        "damage_probability": None,
    }


async def health_review(
    session: AsyncSession,
    work_order_id: str,
    payload: StructuralHealthReviewRequest,
    subject: str,
    verifier: ArtifactVerifier,
    settings: Settings,
) -> dict[str, Any]:
    # Match task completion's work-order-first lock order to avoid a deadlock.
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
        raise ConflictError("mission revision changed; refresh the health review")
    if order.status != "awaiting_health_review" or mission.status != "executing":
        raise InvalidTransitionError(
            "all registered field tasks must be completed before health review"
        )
    await require_reviewed_structural_claim(session, mission.id, verifier, settings)
    tasks = list(
        (
            await session.scalars(
                select(WorkOrderTask)
                .where(WorkOrderTask.work_order_id == order.id)
                .order_by(WorkOrderTask.sequence)
            )
        ).all()
    )
    evidence: list[FieldTaskEvidence | StructuralRetestHandoff] = list(
        (
            await session.scalars(
                select(FieldTaskEvidence)
                .join(WorkOrderTask, WorkOrderTask.id == FieldTaskEvidence.task_id)
                .where(WorkOrderTask.work_order_id == order.id)
                .order_by(FieldTaskEvidence.verified_at, FieldTaskEvidence.id)
            )
        ).all()
    )
    evidence.extend(
        (
            await session.scalars(
                select(StructuralRetestHandoff).where(
                    StructuralRetestHandoff.work_order_id == order.id
                )
            )
        ).all()
    )
    evidence.sort(key=lambda item: (aware(item.verified_at), item.id))
    by_task = {row.task_id: row for row in evidence}
    if not tasks or any(task.status != "completed" or task.id not in by_task for task in tasks):
        raise InvalidTransitionError("field task evidence is incomplete")
    if any(row.verified_by == subject for row in evidence):
        raise InvalidTransitionError(
            "health reviewer must be independent of the field evidence authors"
        )
    for row in evidence:
        try:
            await verifier.verify(
                row.artifact_uri, row.artifact_sha256, work_order_id=order.id, task_id=row.task_id
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
    assessment = await assess_retest(
        session, order, str(by_task[tasks[-1].id].measurement["retest_source_id"])
    )
    card = assessment["evidence_card"]
    await verified_input(
        verifier,
        settings.minio_field_evidence_bucket,
        order.turbine_id,
        card["source"]["artifact_uri"],
        card["source"]["sha256"],
    )
    if payload.action == "resolve_review" and not assessment["eligible_to_resolve_review"]:
        raise InvalidTransitionError(
            "retest cannot resolve review: " + "; ".join(assessment["exclusions"])
        )
    now = datetime.now(UTC)
    review = StructuralHealthReview(
        **{name: card[name] for name in ("tenant_id", "wind_farm_id", "turbine_id")},
        mission_id=mission.id,
        work_order_id=order.id,
        mission_revision=mission.revision,
        action=payload.action,
        reason=payload.reason,
        hypothesis_outcome=payload.hypothesis_outcome,
        assessment=assessment,
        reviewed_by=subject,
    )
    session.add(review)
    await session.flush()
    previous_revision = mission.revision
    updated = await session.execute(
        update(Mission)
        .where(Mission.id == mission.id, Mission.revision == previous_revision)
        .values(revision=previous_revision + 1, updated_at=now)
        .returning(Mission.id)
        .execution_options(synchronize_session="fetch")
    )
    if updated.scalar_one_or_none() is None:
        raise ConflictError("a concurrent health review already changed this mission")
    case_id = None
    if payload.action == "resolve_review":
        order.status, order.completed_at, order.updated_at = "completed", now, now
        mission.status = "completed"
        mission.public_state = {
            **mission.public_state,
            "workflow_status": "completed",
            "structural_health_review_id": review.id,
        }
        alarm = await session.get(Alarm, mission.alarm_id)
        if alarm:
            alarm.status, alarm.ai_status, alarm.resolved_at = "resolved", "review_completed", now
            alarm.revision += 1
            alarm.updated_at = now
        # Close the review workflow only. Turbine score/status and restart authority are unchanged.
        case_id = f"CASE-{now:%Y%m%d}-{uuid4().hex[:6].upper()}"
        case = KnowledgeCase(
            id=case_id,
            mission_id=mission.id,
            work_order_id=order.id,
            turbine_id=order.turbine_id,
            title=f"{mission.title}: structural retest reviewed",
            diagnosis=mission.public_state.get("diagnosis", {}),
            resolution={
                "health_review_id": review.id,
                "hypothesis_outcome": payload.hypothesis_outcome,
                "assessment": assessment,
                "responsible_reviewer": subject,
                "review_reason": payload.reason,
                "completed_tasks": [
                    {
                        "sequence": task.sequence,
                        "title": task.title,
                        "result": by_task[task.id].measurement.get("handoff_result", task.result),
                        "evidence": serialize(by_task[task.id]),
                    }
                    for task in tasks
                ],
                "field_evidence_history": [serialize(item) for item in evidence],
                "initial_case_review_status": "pending",
                "closed_at": now.isoformat(),
                "authorizes_operation": False,
            },
        )
        session.add(case)
        await session.flush()
        session.add(
            StructuralCaseReview(
                case_id=case_id,
                health_review_id=review.id,
                **{name: card[name] for name in ("tenant_id", "wind_farm_id", "turbine_id")},
            )
        )
        reservations = (
            await session.scalars(
                select(ResourceReservation).where(ResourceReservation.mission_id == mission.id)
            )
        ).all()
        for reservation in reservations:
            resource = await session.get(Resource, reservation.resource_id)
            if resource:
                resource.status, resource.updated_at = "available", now
    append_domain_event(
        session,
        event_type="structural.health.reviewed",
        aggregate_type="work_order",
        aggregate_id=order.id,
        payload={
            "work_order_id": order.id,
            "mission_id": mission.id,
            "turbine_id": order.turbine_id,
            "review_id": review.id,
            "action": payload.action,
            "knowledge_case_id": case_id,
            "reviewed_by": subject,
        },
    )
    await session.flush()
    return {
        "review": serialize(review),
        "work_order_status": order.status,
        "mission_revision": mission.revision,
        "knowledge_case_id": case_id,
        "case_review_status": "pending" if case_id else None,
    }


async def review_case(
    session: AsyncSession,
    case_id: str,
    payload: StructuralCaseReviewRequest,
    subject: str,
    verifier: ArtifactVerifier,
    settings: Settings,
) -> dict[str, Any]:
    row = await session.scalar(
        select(StructuralCaseReview)
        .where(StructuralCaseReview.case_id == case_id)
        .with_for_update()
    )
    if row is None:
        raise NotFoundError("structural case was not found")
    health = await session.get(StructuralHealthReview, row.health_review_id)
    if health is None or health.reviewed_by == subject:
        raise InvalidTransitionError("case publication requires an independent reviewer")
    if row.status != "pending" or row.revision != payload.expected_revision:
        raise ConflictError("case review changed; refresh the case")
    if payload.action == "approve":
        frozen = health.assessment["evidence_card"]
        current = await build_evidence_card(
            session,
            EngineeringEvidenceReference.model_validate(frozen["reference"]),
            turbine_id=row.turbine_id,
            component_id=frozen["component_id"],
        )
        if current["source_fingerprint"] != frozen["source_fingerprint"]:
            raise InvalidTransitionError("case retest source changed after its health review")
        context = await structural_mission_detail(session, health.mission_id)
        await verify_card_sources(
            [current, *context["evidence_cards"]], row.turbine_id, verifier, settings
        )
    now = datetime.now(UTC)
    changed = await session.execute(
        update(StructuralCaseReview)
        .where(
            StructuralCaseReview.case_id == case_id,
            StructuralCaseReview.revision == payload.expected_revision,
            StructuralCaseReview.status == "pending",
        )
        .values(
            status="approved" if payload.action == "approve" else "rejected",
            revision=payload.expected_revision + 1,
            reviewed_by=subject,
            review_reason=payload.reason,
            reviewed_at=now,
        )
        .returning(StructuralCaseReview.case_id)
        .execution_options(synchronize_session="fetch")
    )
    if changed.scalar_one_or_none() is None:
        raise ConflictError("a concurrent case review already changed this case")
    append_domain_event(
        session,
        event_type="structural.case.reviewed",
        aggregate_type="knowledge_case",
        aggregate_id=case_id,
        payload={
            "case_id": case_id,
            "turbine_id": row.turbine_id,
            "status": row.status,
            "reviewed_by": subject,
        },
    )
    return serialize(row)
