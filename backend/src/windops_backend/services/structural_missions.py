"""Actual structural origins and frozen, source-checked context for the eight-node workflow."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.config import Settings
from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.model_structural_workflow import StructuralMissionContext
from windops_backend.models import (
    Alarm,
    EngineeringClaim,
    HealthBaseline,
    IngestReceipt,
    Mission,
    ModalObservation,
    PrestressObservation,
    StructuralAnalysisRun,
    WaveformRecord,
)
from windops_backend.outbox_commands import enqueue_mission_analysis
from windops_backend.schema_engineering_claim import (
    EngineeringClaimCreate,
    EngineeringEvidenceReference,
)
from windops_backend.schema_operations import (
    MissionAnalysisProfile,
    WorkOrderPlan,
    WorkOrderTaskTemplate,
)
from windops_backend.schema_structural import aware
from windops_backend.schema_structural_workflow import StructuralMissionCreate
from windops_backend.services.engineering_claims import (
    build_evidence_card,
    claim_detail,
    create_claim,
)
from windops_backend.services.events import append_domain_event
from windops_backend.services.idempotency import canonical_request_hash
from windops_backend.services.structural import asset_scope, related, serialize
from windops_backend.storage import ArtifactVerifier
from windops_backend.structural_baseline import compare_to_baseline

STRUCTURAL_WORKFLOW_CONTRACT = "hybrid-tower-review-2026.10.1"
STRUCTURAL_COMPONENT = "hybrid_tower_structure"


def structural_plan(payload: StructuralMissionCreate) -> WorkOrderPlan:
    """Software acquisition template; permits and engineering limits remain human prerequisites."""
    return WorkOrderPlan(
        title=f"Controlled onshore structural retest: {payload.scenario}",
        required_resource_types=["crew", "measurement_equipment"],
        closure_kind="structural_retest",
        safety_plan={
            "template_version": STRUCTURAL_WORKFLOW_CONTRACT,
            "scenario": payload.scenario,
            "component_id": payload.component_id,
            "estimated_duration_hours": payload.planning_duration_hours,
            "duration_source": "human_planning_estimate",
            "access_method": "onshore",
            "prerequisites": [
                "responsible human approval and controlled site procedure",
                "work permit, isolation and safe access verified before exposure",
                "measurement equipment qualification and calibration",
            ],
            "operating_authority": False,
            "tensioning_authority": False,
        },
        tasks=[
            WorkOrderTaskTemplate(
                title="Verify site permit, isolation, access and measurement calibration",
                schema_version="structural-prerequisites-v1",
                measurement_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "permit_reference",
                        "isolation_reference",
                        "calibration_reference",
                    ],
                    "properties": {
                        name: {"type": "string", "minLength": 3, "maxLength": 320}
                        for name in [
                            "permit_reference",
                            "isolation_reference",
                            "calibration_reference",
                        ]
                    },
                },
            ),
            WorkOrderTaskTemplate(
                title=(
                    "Acquire calibrated retest and hand its registered source "
                    "to the health reviewer"
                ),
                schema_version="structural-retest-v1",
                measurement_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["retest_source_id", "measurement_reference"],
                    "properties": {
                        "retest_source_id": {"type": "string", "minLength": 1, "maxLength": 36},
                        "measurement_reference": {
                            "type": "string",
                            "minLength": 3,
                            "maxLength": 320,
                        },
                    },
                },
            ),
        ],
    )


def _references(payload: StructuralMissionCreate) -> list[EngineeringEvidenceReference]:
    refs = [
        EngineeringEvidenceReference(
            kind="modal" if payload.scenario == "modal_frequency_review" else "prestress",
            source_id=payload.source_id,
            relation="supports",
        )
    ]
    if payload.baseline_id:
        refs.append(
            EngineeringEvidenceReference(
                kind="baseline", source_id=payload.baseline_id, relation="context"
            )
        )
    if payload.previous_prestress_id:
        if payload.previous_prestress_id == payload.source_id:
            raise InvalidTransitionError("comparison requires two distinct force measurements")
        refs.append(
            EngineeringEvidenceReference(
                kind="prestress", source_id=payload.previous_prestress_id, relation="context"
            )
        )
    if payload.force_acceptance:
        refs.append(payload.force_acceptance.procedure)
    return refs


async def _comparison(
    session: AsyncSession, payload: StructuralMissionCreate
) -> tuple[dict[str, Any], list[str]]:
    missing: list[str] = []
    if payload.scenario == "modal_frequency_review":
        modal = await related(session, ModalObservation, payload.source_id, payload.turbine_id)
        run = await related(session, StructuralAnalysisRun, modal.run_id, payload.turbine_id)
        record = await related(session, WaveformRecord, run.record_id, payload.turbine_id)
        if run.status != "succeeded":
            raise InvalidTransitionError("modal review requires a completed source analysis")
        if payload.baseline_id is None:
            missing.append("confirmed_environmental_baseline")
            return {
                "status": "not_applicable",
                "exclusions": missing.copy(),
                "damage_probability": None,
            }, missing
        baseline = await related(session, HealthBaseline, payload.baseline_id, payload.turbine_id)
        if aware(baseline.valid_until) <= datetime.now(UTC):
            missing.append("current_baseline")
            return {
                "status": "not_applicable",
                "exclusions": ["baseline_expired"],
                "damage_probability": None,
            }, missing
        result = compare_to_baseline(baseline.model, serialize(run), serialize(record))
        if result["status"] == "not_applicable":
            missing.extend(result["exclusions"])
        return result, missing
    measurement = await related(
        session, PrestressObservation, payload.source_id, payload.turbine_id
    )
    result = {
        "status": "direct_measurement_requires_review",
        "value_kn": measurement.value_kn,
        "damage_probability": None,
    }
    if payload.previous_prestress_id:
        previous = await related(
            session, PrestressObservation, payload.previous_prestress_id, payload.turbine_id
        )
        if (
            previous.tendon_id != measurement.tendon_id
            or previous.sensor_id != measurement.sensor_id
            or previous.calibration_version != measurement.calibration_version
            or previous.source_kind != measurement.source_kind
            or aware(previous.observed_at) >= aware(measurement.observed_at)
        ):
            raise InvalidTransitionError(
                "force trend requires an earlier same-tendon, sensor, "
                "calibration and source measurement"
            )
        result.update(
            previous_value_kn=previous.value_kn,
            change_kn=measurement.value_kn - previous.value_kn,
            change_percent=100 * (measurement.value_kn / previous.value_kn - 1)
            if previous.value_kn
            else None,
        )
    else:
        missing.append("comparable_prior_direct_force")
    if payload.force_acceptance is None:
        missing.append("human_reviewed_force_acceptance_procedure")
    else:
        bounds = payload.force_acceptance
        result["acceptance"] = bounds.model_dump(mode="json")
        result["status"] = (
            "within_declared_force_bounds"
            if bounds.minimum_kn <= measurement.value_kn <= bounds.maximum_kn
            else "requires_review"
        )
        result["bounds_authority"] = "human_declared_pending_review"
    return result, missing


async def prepare_context(
    session: AsyncSession, payload: StructuralMissionCreate
) -> dict[str, Any]:
    scope = await asset_scope(session, payload.turbine_id)
    refs = _references(payload)
    cards = [
        await build_evidence_card(
            session, ref, turbine_id=payload.turbine_id, component_id=payload.component_id
        )
        for ref in refs
    ]
    comparison, missing = await _comparison(session, payload)
    now = datetime.now(UTC)
    for card in cards:
        if not card["quality"].get("usable"):
            missing.append(f"usable_source:{card['evidence_id']}")
        if card["valid_until"] and aware(datetime.fromisoformat(card["valid_until"])) <= now:
            missing.append(f"current_source:{card['evidence_id']}")
    profile = MissionAnalysisProfile(
        component=STRUCTURAL_COMPONENT,
        primary_variable="tower_modal_frequency"
        if payload.scenario == "modal_frequency_review"
        else "direct_tendon_force",
        knowledge_query=(
            f"hybrid tower {payload.scenario.replace('_', ' ')} "
            "controlled measurement calibration procedure"
        ),
        failure_mode_hint="structural_screening_requires_human_review",
        work_order_plan=structural_plan(payload),
    )
    return {
        "contract_version": STRUCTURAL_WORKFLOW_CONTRACT,
        **scope,
        "component_id": payload.component_id,
        "scenario": payload.scenario,
        "request": payload.model_dump(mode="json"),
        "source_refs": [r.model_dump(mode="json") for r in refs],
        "evidence_cards": cards,
        "comparison": comparison,
        "missing_evidence": list(dict.fromkeys(missing)),
        "analysis_profile": profile.model_dump(mode="json", exclude_none=True),
    }


async def create_structural_mission(
    session: AsyncSession, payload: StructuralMissionCreate, subject: str
) -> dict[str, Any]:
    context = await prepare_context(session, payload)
    origin = canonical_request_hash(
        {
            "contract": STRUCTURAL_WORKFLOW_CONTRACT,
            "turbine_id": payload.turbine_id,
            "component_id": payload.component_id,
            "scenario": payload.scenario,
            "source_fingerprint": context["evidence_cards"][0]["source_fingerprint"],
        }
    )
    existing = await session.scalar(
        select(StructuralMissionContext).where(
            StructuralMissionContext.turbine_id == payload.turbine_id,
            StructuralMissionContext.origin_fingerprint == origin,
        )
    )
    if existing:
        if existing.frozen_context["request"] != payload.model_dump(mode="json"):
            raise ConflictError(
                "this structural origin already has a different frozen mission; "
                "review the existing mission"
            )
        return await structural_mission_detail(session, existing.mission_id)
    mission_id = f"MISSION-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:10].upper()}"
    event_id = "structural:" + origin
    alarm_id = str(uuid4())
    try:
        async with session.begin_nested():
            session.add(
                IngestReceipt(
                    source_event_id=event_id,
                    source_id="structural-evidence",
                    payload_hash=origin,
                    disposition="accepted",
                )
            )
            await session.flush()
            session.add(
                Alarm(
                    id=alarm_id,
                    turbine_id=payload.turbine_id,
                    source_event_id=event_id,
                    code="STRUCTURAL_REVIEW_REQUIRED",
                    subsystem=STRUCTURAL_COMPONENT,
                    title=payload.title,
                    severity="warning",
                    triggered_at=datetime.now(UTC),
                    evidence={
                        "structural_origin": origin,
                        "source_refs": context["source_refs"],
                        "qualification": "unverified",
                    },
                )
            )
            await session.flush()
            session.add(
                Mission(
                    id=mission_id,
                    alarm_id=alarm_id,
                    turbine_id=payload.turbine_id,
                    title=payload.title,
                    public_state={
                        "analysis_profile": context["analysis_profile"],
                        "created_by": subject,
                        "structural": True,
                    },
                )
            )
            await session.flush()
            session.add(
                StructuralMissionContext(
                    mission_id=mission_id,
                    **{
                        key: context[key]
                        for key in (
                            "tenant_id",
                            "wind_farm_id",
                            "turbine_id",
                            "component_id",
                            "scenario",
                        )
                    },
                    origin_fingerprint=origin,
                    context_sha256=canonical_request_hash(context),
                    frozen_context=context,
                    created_by=subject,
                )
            )
            enqueue_mission_analysis(session, mission_id)
            append_domain_event(
                session,
                event_type="structural.mission.created",
                aggregate_type="mission",
                aggregate_id=mission_id,
                payload={
                    "mission_id": mission_id,
                    "turbine_id": payload.turbine_id,
                    "origin_fingerprint": origin,
                },
            )
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(StructuralMissionContext).where(
                StructuralMissionContext.turbine_id == payload.turbine_id,
                StructuralMissionContext.origin_fingerprint == origin,
            )
        )
        if existing is None:
            raise
        if existing.frozen_context["request"] != payload.model_dump(mode="json"):
            raise ConflictError(
                "concurrent structural origin has a different frozen mission"
            ) from None
        mission_id = existing.mission_id
    return await structural_mission_detail(session, mission_id)


async def structural_mission_detail(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    row = await session.get(StructuralMissionContext, mission_id)
    mission = await session.get(Mission, mission_id)
    if row is None or mission is None:
        raise NotFoundError("structural mission was not found")
    frozen = row.frozen_context
    if canonical_request_hash(frozen) != row.context_sha256:
        raise InvalidTransitionError("structural context hash does not match its frozen identity")
    if mission.public_state.get("analysis_profile") != frozen["analysis_profile"]:
        raise InvalidTransitionError(
            "structural execution profile differs from its frozen template"
        )
    cards = [
        await build_evidence_card(
            session,
            EngineeringEvidenceReference.model_validate(ref),
            turbine_id=row.turbine_id,
            component_id=row.component_id,
        )
        for ref in frozen["source_refs"]
    ]
    if [c["source_fingerprint"] for c in cards] != [
        c["source_fingerprint"] for c in frozen["evidence_cards"]
    ]:
        raise InvalidTransitionError(
            "structural source identity changed; a new scoped review is required"
        )
    return {
        "mission_id": mission.id,
        "alarm_id": mission.alarm_id,
        "status": mission.status,
        "revision": mission.revision,
        **frozen,
        "context_sha256": row.context_sha256,
        "created_at": aware(row.created_at).isoformat(),
        "claim_id": row.claim_id,
        "field_qualification": "unverified",
        "authorizes_operation": False,
    }


async def persist_screening_claim(
    session: AsyncSession, mission_id: str, output: dict[str, Any]
) -> str:
    row = await session.get(StructuralMissionContext, mission_id)
    if row is None:
        raise NotFoundError("structural context was not found")
    if row.claim_id:
        old = await session.get(EngineeringClaim, row.claim_id)
        if old and (await claim_detail(session, old))["effective_status"] == "pending":
            return old.id
    frozen = row.frozen_context
    claim = await create_claim(
        session,
        EngineeringClaimCreate(
            turbine_id=row.turbine_id,
            component_id=row.component_id,
            mission_id=mission_id,
            claim_kind="retest_recommendation",
            conclusion=output["conclusion"],
            evidence=[
                EngineeringEvidenceReference.model_validate(ref) for ref in frozen["source_refs"]
            ],
            missing_evidence=frozen["missing_evidence"],
            applicability={
                "scenario": row.scenario,
                "context_sha256": row.context_sha256,
                "force_acceptance": json.dumps(
                    {
                        "minimum_kn": frozen["request"]["force_acceptance"]["minimum_kn"],
                        "maximum_kn": frozen["request"]["force_acceptance"]["maximum_kn"],
                        "procedure_id": frozen["request"]["force_acceptance"]["procedure"][
                            "source_id"
                        ],
                    },
                    sort_keys=True,
                )
                if frozen["request"].get("force_acceptance")
                else "unavailable",
                "authority": "controlled_retest_proposal_only",
            },
            valid_until=datetime.now(UTC) + timedelta(days=7),
        ),
        "structural_workflow_agent",
    )
    row.claim_id = claim["id"]
    await session.flush()
    return str(claim["id"])


async def require_reviewed_structural_claim(
    session: AsyncSession,
    mission_id: str,
    verifier: ArtifactVerifier | None = None,
    settings: Settings | None = None,
) -> None:
    row = await session.get(StructuralMissionContext, mission_id)
    if row is None:
        return
    await structural_mission_detail(session, mission_id)
    claim = await session.get(EngineeringClaim, row.claim_id) if row.claim_id else None
    if claim is None:
        raise InvalidTransitionError(
            "structural execution requires a source-grounded reviewed claim"
        )
    detail = await claim_detail(session, claim)
    if (
        detail["effective_status"] != "approved"
        or claim.mission_id != mission_id
        or claim.claim_kind != "retest_recommendation"
        or claim.component_id != row.component_id
        or claim.applicability.get("context_sha256") != row.context_sha256
    ):
        raise InvalidTransitionError(
            "the exact structural retest claim must be current and independently approved"
        )
    if verifier is None or settings is None:
        raise InvalidTransitionError("structural execution requires a current artifact verifier")
    from windops_backend.services.engineering_claims import verify_card_sources

    await verify_card_sources(detail["evidence_cards"], row.turbine_id, verifier, settings)
