"""Project structural business summaries; claims remain reviewed statements, not facts."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import InvalidTransitionError, NotFoundError
from windops_backend.knowledge_graph.domain import (
    GraphProperties,
    NodeType,
    RelationshipType,
    graph_uid,
)
from windops_backend.model_engineering_claim import EngineeringClaim
from windops_backend.model_structural import (
    HealthBaseline,
    ModalObservation,
    PrestressObservation,
    SensorChannel,
    StructuralAnalysisRun,
    TendonAssembly,
    TowerComponent,
    WaveformRecord,
)
from windops_backend.model_structural_workflow import (
    StructuralHealthReview,
    StructuralMissionContext,
    StructuralRetestHandoff,
)
from windops_backend.models import WorkOrder, WorkOrderTask
from windops_backend.services.engineering_claims import _effective_status, _sources
from windops_backend.storage import FieldTaskEvidence

if TYPE_CHECKING:
    from windops_backend.knowledge_graph.projection_budget import _ProjectionBudget
    from windops_backend.knowledge_graph.projection_builder import _ProjectionBuilder

logger = logging.getLogger(__name__)


def _scope_value(properties: GraphProperties, name: str) -> str | None:
    value = properties.get(name)
    if value is None or isinstance(value, str):
        return value
    raise ValueError("structural graph scope must be a string or null")


def claim_read_identity(claim: EngineeringClaim) -> str:
    return f"{claim.id}:{claim.revision}:{claim.content_sha256}"


async def project_structural_nodes(
    session: AsyncSession, builder: _ProjectionBuilder, budget: _ProjectionBudget
) -> None:
    from windops_backend.knowledge_graph.projection_budget import _BudgetedDict
    from windops_backend.knowledge_graph.projection_rows import _iter_bounded_scalar_rows
    from windops_backend.knowledge_graph.projection_values import _iso, _json

    def link(
        kind: RelationshipType,
        source: str,
        target_kind: NodeType,
        target: str | None,
        **properties: str | int | float | bool | None,
    ) -> None:
        if target is None:
            return
        target_uid = graph_uid(target_kind, target)
        if source in builder.nodes and target_uid in builder.nodes:
            builder.relationship(kind, source, target_uid, qualifier="", **properties)

    # Ordered nodes are followed by a second edge pass. No extra unbudgeted
    # foreign-key dictionaries or raw signal samples are retained in this module.
    models: tuple[tuple[Any, NodeType, dict[str, str]], ...] = (
        (
            TowerComponent,
            NodeType.TOWER_COMPONENT,
            {
                "code": "code",
                "name": "name",
                "revision": "revision",
                "component_type": "componentType",
                "design_reference": "designReference",
                "parent_id": "parentId",
            },
        ),
        (
            TendonAssembly,
            NodeType.TENDON_ASSEMBLY,
            {
                "code": "code",
                "revision": "revision",
                "component_id": "componentId",
                "effective_length_m": "effectiveLengthM",
                "line_density_kg_m": "lineDensityKgM",
            },
        ),
        (
            SensorChannel,
            NodeType.SENSOR_CHANNEL,
            {
                "code": "code",
                "revision": "revision",
                "component_id": "componentId",
                "tendon_id": "tendonId",
                "quantity": "quantity",
                "unit": "unit",
                "direction": "direction",
                "range_min": "rangeMin",
                "range_max": "rangeMax",
                "calibration_version": "calibrationVersion",
                "calibration_reference": "calibrationReference",
                "synchronization_source": "synchronizationSource",
            },
        ),
        (
            WaveformRecord,
            NodeType.WAVEFORM_RECORD,
            {
                "sample_rate_hz": "sampleRateHz",
                "sample_count": "sampleCount",
                "artifact_uri": "artifactUri",
                "artifact_sha256": "artifactSha256",
                "source_kind": "sourceKind",
                "source_reference": "sourceReference",
                "input_fingerprint": "inputFingerprint",
            },
        ),
        (
            StructuralAnalysisRun,
            NodeType.STRUCTURAL_ANALYSIS_RUN,
            {
                "record_id": "recordId",
                "input_fingerprint": "inputFingerprint",
                "method": "method",
                "status": "status",
                "error_code": "errorCode",
                "attempts": "attempts",
            },
        ),
        (
            ModalObservation,
            NodeType.MODAL_OBSERVATION,
            {"run_id": "runId", "mode_index": "modeIndex", "frequency_hz": "frequencyHz"},
        ),
        (
            PrestressObservation,
            NodeType.PRESTRESS_OBSERVATION,
            {
                "tendon_id": "tendonId",
                "sensor_id": "sensorId",
                "value_kn": "valueKn",
                "calibration_version": "calibrationVersion",
                "artifact_uri": "artifactUri",
                "artifact_sha256": "artifactSha256",
                "source_kind": "sourceKind",
                "input_fingerprint": "inputFingerprint",
            },
        ),
        (
            HealthBaseline,
            NodeType.HEALTH_BASELINE,
            {
                "component_id": "componentId",
                "code": "code",
                "revision": "revision",
                "confirmation_reference": "confirmationReference",
                "reference_modal_id": "referenceModalId",
                "source_kind": "sourceKind",
                "input_fingerprint": "inputFingerprint",
            },
        ),
        (
            StructuralHealthReview,
            NodeType.CLOSURE_ASSESSMENT,
            {
                "mission_id": "missionId",
                "work_order_id": "workOrderId",
                "mission_revision": "missionRevision",
                "action": "action",
                "reason": "reason",
                "hypothesis_outcome": "hypothesisOutcome",
                "reviewed_by": "reviewedBy",
            },
        ),
        (
            StructuralRetestHandoff,
            NodeType.FIELD_MEASUREMENT,
            {
                "mission_id": "missionId",
                "work_order_id": "workOrderId",
                "task_id": "taskId",
                "health_review_id": "healthReviewId",
                "modal_id": "modalId",
                "prestress_id": "prestressId",
                "source_fingerprint": "sourceFingerprint",
                "artifact_uri": "artifactUri",
                "artifact_sha256": "artifactSha256",
                "verified_by": "verifiedBy",
            },
        ),
    )
    for model, kind, fields in models:
        async for row in _iter_bounded_scalar_rows(
            session,
            select(model).order_by(model.id),
            budget=budget,
            key_column=model.id,
            key_attribute="id",
        ):
            props = {name: getattr(row, column) for column, name in fields.items()}
            props.update(
                tenantId=row.tenant_id,
                windFarmId=row.wind_farm_id,
                turbineId=row.turbine_id,
                source="postgresql-structural",
                recordSemantics="business_fact",
                authorizesWork=False,
                fieldQualification="unverified",
            )
            for column, name in (
                ("created_at", "createdAt"),
                ("started_at", "startedAt"),
                ("ended_at", "endedAt"),
                ("observed_at", "observedAt"),
                ("completed_at", "completedAt"),
                ("valid_until", "validUntil"),
                ("calibration_at", "calibrationAt"),
                ("calibration_valid_until", "calibrationValidUntil"),
                ("verified_at", "verifiedAt"),
            ):
                if hasattr(row, column):
                    props[name] = _iso(getattr(row, column))
            if isinstance(row, SensorChannel):
                props["sensorId"] = row.id
            elif isinstance(row, TowerComponent):
                props["componentId"] = row.id
                props["geometryJson"] = _json(row.geometry)
            elif isinstance(row, TendonAssembly):
                props["tendonId"] = row.id
                props["boundaryJson"] = _json(row.boundary)
            elif isinstance(row, WaveformRecord):
                props["recordId"] = row.id
                props["channelIdsJson"] = _json(row.channel_ids)
                props["environmentJson"] = _json(row.environment)
            elif isinstance(row, StructuralAnalysisRun):
                props["runId"] = row.id
                props["configJson"] = _json(row.config)
                props["algorithmIdentityJson"] = _json(row.algorithm_identity)
                result = row.result or {}
                props["qualityJson"] = _json(result.get("quality"))
                props["warningsJson"] = _json(result.get("warnings"))
                props["resultSha256"] = result.get("result_sha256")
            elif isinstance(row, ModalObservation):
                props.update(
                    unit="Hz",
                    dampingRatio=None,
                    absolutePrestressAvailable=False,
                    qualityJson=_json(row.quality),
                    uncertaintyJson=_json(row.uncertainty),
                )
            elif isinstance(row, PrestressObservation):
                props.update(
                    unit="kN", method="direct_force", uncertaintyJson=_json(row.uncertainty)
                )
            elif isinstance(row, HealthBaseline):
                props.update(
                    validationJson=_json(row.model.get("validation")),
                    domainJson=_json(row.model.get("domain")),
                    trainingWindowCount=len(row.training_modal_ids),
                    qualification=row.model.get("qualification"),
                )
            elif isinstance(row, StructuralHealthReview):
                props["assessmentJson"] = _json(row.assessment)
            elif isinstance(row, StructuralRetestHandoff):
                props["measurementJson"] = _json(row.measurement)
                props["measurementStage"] = "followup"
            builder.node(kind, row.id, **props)

    # Initial actual field measurement remains separate from append-only follow-ups.
    query = (
        select(FieldTaskEvidence)
        .join(WorkOrderTask, FieldTaskEvidence.task_id == WorkOrderTask.id)
        .join(WorkOrder, WorkOrderTask.work_order_id == WorkOrder.id)
        .join(StructuralMissionContext, StructuralMissionContext.mission_id == WorkOrder.mission_id)
        .order_by(FieldTaskEvidence.id)
    )
    async for evidence in _iter_bounded_scalar_rows(
        session, query, budget=budget, key_column=FieldTaskEvidence.id, key_attribute="id"
    ):
        task = builder.nodes.get(graph_uid(NodeType.PROCEDURE, evidence.task_id))
        order_id = _scope_value(task.properties, "workOrderId") if task else None
        order = builder.nodes.get(graph_uid(NodeType.WORK_ORDER, order_id)) if order_id else None
        measurement = evidence.measurement
        if order is None or not measurement.get("retest_source_id"):
            continue
        builder.node(
            NodeType.FIELD_MEASUREMENT,
            evidence.id,
            tenantId=_scope_value(order.properties, "tenantId"),
            windFarmId=_scope_value(order.properties, "windFarmId"),
            turbineId=_scope_value(order.properties, "turbineId"),
            missionId=_scope_value(order.properties, "missionId"),
            workOrderId=order_id,
            taskId=evidence.task_id,
            measurementJson=_json(measurement),
            retestSourceId=str(measurement["retest_source_id"]),
            artifactUri=evidence.artifact_uri,
            artifactSha256=evidence.artifact_sha256,
            verifiedBy=evidence.verified_by,
            verifiedAt=_iso(evidence.verified_at),
            source="postgresql-structural-field-evidence",
            recordSemantics="business_fact",
            measurementStage="initial",
            authorizesWork=False,
            fieldQualification="unverified",
        )

    async for claim in _iter_bounded_scalar_rows(
        session,
        select(EngineeringClaim)
        .where(EngineeringClaim.review_status == "approved")
        .order_by(EngineeringClaim.id),
        budget=budget,
        key_column=EngineeringClaim.id,
        key_attribute="id",
    ):
        try:
            cards, drift = await _sources(session, claim)
        except (NotFoundError, InvalidTransitionError) as exc:
            # A deleted or inaccessible reference does not establish graph knowledge.
            logger.info("structural graph omitted claim %s: %s", claim.id, type(exc).__name__)
            continue
        if _effective_status(claim, cards, drift) != "approved":
            continue
        claim_uid = builder.node(
            NodeType.ENGINEERING_CLAIM,
            claim.id,
            tenantId=claim.tenant_id,
            windFarmId=claim.wind_farm_id,
            turbineId=claim.turbine_id,
            missionId=claim.mission_id,
            componentId=claim.component_id,
            claimId=claim.id,
            claimKind=claim.claim_kind,
            conclusion=claim.conclusion,
            revision=claim.revision,
            reviewStatus=claim.review_status,
            contentSha256=claim.content_sha256,
            readIdentity=claim_read_identity(claim),
            validUntil=_iso(claim.valid_until),
            applicabilityJson=_json(claim.applicability),
            missingEvidenceJson=_json(claim.missing_evidence),
            recordSemantics="reviewed_engineering_statement",
            source="postgresql-engineering-claim",
            permittedUse="retest_proposal_only"
            if claim.claim_kind == "retest_recommendation"
            else "reviewed_source_interpretation",
            sourceVerification="required_on_governed_graph_read",
            authorizesWork=False,
            fieldQualification="unverified",
        )
        link(RelationshipType.RECORDED_FOR, claim_uid, NodeType.MISSION, claim.mission_id)
        link(RelationshipType.RECORDED_FOR, claim_uid, NodeType.TOWER_COMPONENT, claim.component_id)
        mission_uid = graph_uid(NodeType.MISSION, claim.mission_id)
        if mission_uid in builder.nodes:
            builder.relationship(RelationshipType.HAS_CLAIM, mission_uid, claim_uid)
        reference_types = {
            "analysis": NodeType.STRUCTURAL_ANALYSIS_RUN,
            "modal": NodeType.MODAL_OBSERVATION,
            "prestress": NodeType.PRESTRESS_OBSERVATION,
            "baseline": NodeType.HEALTH_BASELINE,
            "knowledge_passage": NodeType.KNOWLEDGE_PASSAGE,
        }
        for card in cards:
            ref = card["reference"]
            relation = {
                "supports": RelationshipType.SUPPORTED_BY,
                "contradicts": RelationshipType.CONTRADICTED_BY,
                "context": RelationshipType.DERIVED_FROM,
            }[ref["relation"]]
            link(
                relation,
                claim_uid,
                reference_types[ref["kind"]],
                ref["source_id"],
                sourceFingerprint=card["source_fingerprint"],
                relationshipSemantics="human_reviewed_reference",
                quote=ref.get("quote"),
                claimRevision=claim.revision,
            )

    # Link only known identities. Existing SQL composite foreign keys enforce asset
    # consistency; a scoped reconciliation can omit unrelated endpoints safely.
    measurement_sources = _BudgetedDict[tuple[str, str], tuple[str, ...]](budget)
    for node in builder.nodes.values():
        p = node.properties
        if node.node_type is NodeType.FIELD_MEASUREMENT:
            source = p.get("modalId") or p.get("prestressId") or p.get("retestSourceId")
            if source:
                key = (str(p["workOrderId"]), str(source))
                measurement_sources[key] = (*measurement_sources.get(key, ()), node.uid)
    for node in builder.nodes.values():
        p, uid = node.properties, node.uid
        match node.node_type:
            case NodeType.TOWER_COMPONENT:
                link(RelationshipType.RECORDED_FOR, uid, NodeType.TURBINE, str(p["turbineId"]))
                parent = (
                    graph_uid(NodeType.TOWER_COMPONENT, str(p["parentId"]))
                    if p.get("parentId")
                    else graph_uid(NodeType.TURBINE, str(p["turbineId"]))
                )
                if parent in builder.nodes:
                    builder.relationship(RelationshipType.HAS_COMPONENT, parent, uid)
            case NodeType.TENDON_ASSEMBLY | NodeType.SENSOR_CHANNEL | NodeType.HEALTH_BASELINE:
                component_uid = graph_uid(NodeType.TOWER_COMPONENT, str(p["componentId"]))
                if component_uid in builder.nodes:
                    relationship = {
                        NodeType.TENDON_ASSEMBLY: RelationshipType.HAS_TENDON,
                        NodeType.SENSOR_CHANNEL: RelationshipType.MONITORED_BY,
                        NodeType.HEALTH_BASELINE: RelationshipType.HAS_BASELINE,
                    }[node.node_type]
                    builder.relationship(relationship, component_uid, uid)
                if node.node_type is NodeType.SENSOR_CHANNEL and p.get("tendonId"):
                    tendon_uid = graph_uid(NodeType.TENDON_ASSEMBLY, str(p["tendonId"]))
                    if tendon_uid in builder.nodes:
                        builder.relationship(RelationshipType.MONITORED_BY, tendon_uid, uid)
                if node.node_type is NodeType.HEALTH_BASELINE:
                    link(
                        RelationshipType.DERIVED_FROM,
                        uid,
                        NodeType.MODAL_OBSERVATION,
                        str(p["referenceModalId"]),
                    )
            case NodeType.WAVEFORM_RECORD:
                for channel_id in json.loads(str(p["channelIdsJson"])):
                    link(RelationshipType.DERIVED_FROM, uid, NodeType.SENSOR_CHANNEL, channel_id)
            case NodeType.STRUCTURAL_ANALYSIS_RUN:
                record_uid = graph_uid(NodeType.WAVEFORM_RECORD, str(p["recordId"]))
                if record_uid in builder.nodes:
                    builder.relationship(RelationshipType.HAS_ANALYSIS, record_uid, uid)
                link(
                    RelationshipType.DERIVED_FROM, uid, NodeType.WAVEFORM_RECORD, str(p["recordId"])
                )
            case NodeType.MODAL_OBSERVATION:
                run_uid = graph_uid(NodeType.STRUCTURAL_ANALYSIS_RUN, str(p["runId"]))
                if run_uid in builder.nodes:
                    builder.relationship(RelationshipType.HAS_OBSERVATION, run_uid, uid)
            case NodeType.PRESTRESS_OBSERVATION:
                tendon_uid = graph_uid(NodeType.TENDON_ASSEMBLY, str(p["tendonId"]))
                if tendon_uid in builder.nodes:
                    builder.relationship(RelationshipType.HAS_OBSERVATION, tendon_uid, uid)
                link(
                    RelationshipType.DERIVED_FROM, uid, NodeType.SENSOR_CHANNEL, str(p["sensorId"])
                )
            case NodeType.FIELD_MEASUREMENT | NodeType.CLOSURE_ASSESSMENT:
                order_uid = graph_uid(NodeType.WORK_ORDER, str(p["workOrderId"]))
                if order_uid in builder.nodes:
                    builder.relationship(
                        RelationshipType.HAS_MEASUREMENT
                        if node.node_type is NodeType.FIELD_MEASUREMENT
                        else RelationshipType.HAS_ASSESSMENT,
                        order_uid,
                        uid,
                    )
                if node.node_type is NodeType.FIELD_MEASUREMENT:
                    if p.get("healthReviewId"):
                        link(
                            RelationshipType.FOLLOWUP_TO,
                            uid,
                            NodeType.CLOSURE_ASSESSMENT,
                            str(p["healthReviewId"]),
                        )
                    source = p.get("modalId") or p.get("prestressId") or p.get("retestSourceId")
                    if source:
                        for target_kind in (
                            NodeType.MODAL_OBSERVATION,
                            NodeType.PRESTRESS_OBSERVATION,
                        ):
                            link(RelationshipType.DERIVED_FROM, uid, target_kind, str(source))
                else:
                    assessment = json.loads(str(p["assessmentJson"]))
                    source = assessment.get("retest_source_id")
                    if source:
                        for measurement_uid in measurement_sources.get(
                            (str(p["workOrderId"]), str(source)), ()
                        ):
                            builder.relationship(RelationshipType.ASSESSED_BY, measurement_uid, uid)
    measurement_sources.release()
