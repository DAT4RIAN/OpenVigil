from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.knowledge_graph.domain import (
    GraphProperties,
    GraphSnapshot,
    NodeType,
    RelationshipType,
    graph_uid,
)
from windops_backend.knowledge_graph.projection_budget import (
    ProjectionLimitExceeded as ProjectionLimitExceeded,
)
from windops_backend.knowledge_graph.projection_budget import ProjectionLimits as ProjectionLimits
from windops_backend.knowledge_graph.projection_budget import _BudgetedDict as _BudgetedDict
from windops_backend.knowledge_graph.projection_budget import (
    _conservative_memory_bytes as _conservative_memory_bytes,
)
from windops_backend.knowledge_graph.projection_budget import _deep_sizeof as _deep_sizeof
from windops_backend.knowledge_graph.projection_budget import _ProjectionBudget as _ProjectionBudget
from windops_backend.knowledge_graph.projection_budget import (
    _PythonPeakMemorySampler as _PythonPeakMemorySampler,
)
from windops_backend.knowledge_graph.projection_builder import (
    _ProjectionBuilder as _ProjectionBuilder,
)
from windops_backend.knowledge_graph.projection_rows import (
    _estimated_row_bytes as _estimated_row_bytes,
)
from windops_backend.knowledge_graph.projection_rows import (
    _iter_bounded_scalar_rows as _iter_bounded_scalar_rows,
)
from windops_backend.knowledge_graph.projection_rows import (
    _iter_bounded_sensor_rows as _iter_bounded_sensor_rows,
)
from windops_backend.knowledge_graph.projection_values import (
    KNOWLEDGE_GRAPH_MODEL_VERSION as KNOWLEDGE_GRAPH_MODEL_VERSION,
)
from windops_backend.knowledge_graph.projection_values import (
    KNOWLEDGE_GRAPH_PROJECTION_ID as KNOWLEDGE_GRAPH_PROJECTION_ID,
)
from windops_backend.knowledge_graph.projection_values import _iso as _iso
from windops_backend.knowledge_graph.projection_values import _json as _json
from windops_backend.knowledge_graph.projection_values import _slug as _slug
from windops_backend.knowledge_graph.projection_values import (
    _subsystem_for_variable as _subsystem_for_variable,
)
from windops_backend.models import (
    Alarm,
    Decision,
    Evidence,
    KnowledgeCase,
    KnowledgeDocument,
    KnowledgePassage,
    Mission,
    Resource,
    ResourceReservation,
    Turbine,
    WindFarm,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.storage import FieldTaskEvidence

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _MissionContext:
    mission_id: str
    mission_uid: str
    turbine_id: str
    alarm_id: str
    revision: int
    failure_uid: str | None
    confidence: float | None


@dataclass(frozen=True, slots=True)
class _WorkOrderContext:
    work_order_uid: str
    turbine_id: str
    mission_id: str


@dataclass(frozen=True, slots=True)
class _TaskContext:
    work_order_id: str


@dataclass(frozen=True, slots=True)
class _ResourceContext:
    resource_uid: str
    resource_type: str


def _knowledge_owner(properties: GraphProperties, key: str) -> str | None:
    value = properties.get(key)
    if value is None or isinstance(value, str):
        return value
    raise ValueError("knowledge document graph ownership must be a string or null")


async def build_knowledge_graph_snapshot(
    session: AsyncSession,
    *,
    projection_sequence: str | None = None,
    limits: ProjectionLimits | None = None,
) -> GraphSnapshot:
    """Build a graph with conservative accounting and measured Python peak memory."""

    effective_limits = limits or ProjectionLimits()
    budget = _ProjectionBudget(effective_limits)
    outcome = "succeeded"
    try:
        return await _build_knowledge_graph_snapshot(
            session,
            projection_sequence=projection_sequence,
            effective_limits=effective_limits,
            budget=budget,
        )
    except Exception:
        outcome = "failed"
        raise
    finally:
        budget.close()
        logger.info(
            "knowledge graph projection memory outcome=%s actual_peak_bytes=%d "
            "accounted_peak_bytes=%d configured_limit_bytes=%d python_limit_bytes=%d",
            outcome,
            budget.actual_peak_memory_bytes,
            budget.peak_memory_bytes,
            effective_limits.max_estimated_memory_bytes,
            budget.python_memory_limit_bytes,
        )


async def _build_knowledge_graph_snapshot(
    session: AsyncSession,
    *,
    projection_sequence: str | None,
    effective_limits: ProjectionLimits,
    budget: _ProjectionBudget,
) -> GraphSnapshot:
    """Retain bounded indexes while source ORM partitions are promptly released.

    Each source table is consumed in a key-ordered cursor partition.  ORM rows
    are released after the partition is processed; only the scalar foreign-key
    indexes required by later phases remain.  The shared budget accounts for
    partition bytes, graph objects, and those indexes together.
    """

    builder = _ProjectionBuilder(effective_limits, budget)

    farm_tenants = _BudgetedDict[str, str](budget)
    farm_uids = _BudgetedDict[str, str](budget)
    async for farm in _iter_bounded_scalar_rows(
        session,
        select(WindFarm).order_by(WindFarm.id),
        budget=budget,
        key_column=WindFarm.id,
        key_attribute="id",
    ):
        farm_tenants[farm.id] = farm.tenant_id
        farm_uids[farm.id] = builder.node(
            NodeType.WIND_FARM,
            farm.id,
            tenantId=farm.tenant_id,
            name=farm.name,
            capacityMw=farm.capacity_mw,
            source="postgresql",
            createdAt=_iso(farm.created_at),
        )

    turbine_scope = _BudgetedDict[str, tuple[str | None, str]](budget)
    turbine_uids = _BudgetedDict[str, str](budget)
    subsystem_uids = _BudgetedDict[tuple[str, str], str](budget)

    def ensure_subsystem(turbine_id: str, subsystem: str) -> str:
        key = (turbine_id, _slug(subsystem))
        existing = subsystem_uids.get(key)
        if existing is not None:
            return existing
        tenant_id, wind_farm_id = turbine_scope.get(turbine_id, (None, ""))
        uid = builder.node(
            NodeType.SUBSYSTEM,
            f"{turbine_id}:{key[1]}",
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=turbine_id,
            subsystemKey=key[1],
            name=key[1].replace("_", " ").title(),
            source="derived-from-authoritative-domain",
        )
        subsystem_uids[key] = uid
        turbine_uid = turbine_uids.get(turbine_id)
        if turbine_uid is not None:
            builder.relationship(RelationshipType.HAS_SUBSYSTEM, turbine_uid, uid)
        return uid

    async for turbine in _iter_bounded_scalar_rows(
        session,
        select(Turbine).order_by(Turbine.id),
        budget=budget,
        key_column=Turbine.id,
        key_attribute="id",
    ):
        tenant_id = farm_tenants.get(turbine.wind_farm_id)
        turbine_scope[turbine.id] = (tenant_id, turbine.wind_farm_id)
        turbine_uid = builder.node(
            NodeType.TURBINE,
            turbine.id,
            tenantId=tenant_id,
            windFarmId=turbine.wind_farm_id,
            model=turbine.model,
            status=turbine.status,
            healthScore=turbine.health_score,
            source="postgresql",
            updatedAt=_iso(turbine.updated_at),
        )
        turbine_uids[turbine.id] = turbine_uid
        if turbine.wind_farm_id in farm_uids:
            builder.relationship(
                RelationshipType.HAS_TURBINE,
                farm_uids[turbine.wind_farm_id],
                turbine_uid,
            )
        ensure_subsystem(turbine.id, "main_bearing")

    farm_tenants.release()
    farm_uids.release()

    async for turbine_id, variable, unit in _iter_bounded_sensor_rows(session, budget=budget):
        subsystem_uid = ensure_subsystem(turbine_id, _subsystem_for_variable(variable))
        tenant_id, wind_farm_id = turbine_scope.get(turbine_id, (None, None))
        sensor_uid = builder.node(
            NodeType.SENSOR,
            f"{turbine_id}:{variable}",
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=turbine_id,
            variable=variable,
            unit=unit,
            source="postgresql-distinct-scada-identity",
        )
        builder.relationship(RelationshipType.MONITORED_BY, subsystem_uid, sensor_uid)

    mission_context = _BudgetedDict[str, _MissionContext](budget)
    mission_by_alarm = _BudgetedDict[str, _MissionContext](budget)
    failure_mode_uids = _BudgetedDict[str, str](budget)
    async for mission in _iter_bounded_scalar_rows(
        session,
        select(Mission).order_by(Mission.id),
        budget=budget,
        key_column=Mission.id,
        key_attribute="id",
    ):
        tenant_id, wind_farm_id = turbine_scope.get(mission.turbine_id, (None, None))
        diagnosis_value = mission.public_state.get("diagnosis", {})
        diagnosis = diagnosis_value if isinstance(diagnosis_value, dict) else {}
        failure_uid: str | None = None
        if diagnosis.get("failure_mode") and not mission.public_state.get("structural_context"):
            failure_mode_id = _slug(str(diagnosis["failure_mode"]))
            failure_uid = failure_mode_uids.get(failure_mode_id)
            if failure_uid is None:
                failure_uid = builder.node(
                    NodeType.FAILURE_MODE,
                    failure_mode_id,
                    name=str(diagnosis["failure_mode"]).replace("_", " ").title(),
                    severity=str(diagnosis.get("severity", "unknown")),
                    source="mission-public-diagnosis",
                    modelVersion=KNOWLEDGE_GRAPH_MODEL_VERSION,
                )
                failure_mode_uids[failure_mode_id] = failure_uid
        mission_uid = builder.node(
            NodeType.MISSION,
            mission.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=mission.turbine_id,
            alarmId=mission.alarm_id,
            title=mission.title,
            status=mission.status,
            revision=mission.revision,
            source="postgresql",
            createdAt=_iso(mission.created_at),
            updatedAt=_iso(mission.updated_at),
        )
        confidence = diagnosis.get("confidence")
        confidence = float(confidence) if isinstance(confidence, int | float) else None
        context = _MissionContext(
            mission.id,
            mission_uid,
            mission.turbine_id,
            mission.alarm_id,
            mission.revision,
            failure_uid,
            confidence,
        )
        mission_context[mission.id] = context
        mission_by_alarm[mission.alarm_id] = context
        if failure_uid is not None:
            builder.relationship(
                RelationshipType.INDICATES,
                mission_uid,
                failure_uid,
                qualifier=mission.id,
                confidence=confidence,
                source="postgresql-mission-public-state",
                observedAt=_iso(mission.updated_at),
                validFrom=_iso(mission.updated_at),
                validTo=None,
                modelVersion=KNOWLEDGE_GRAPH_MODEL_VERSION,
                revision=mission.revision,
            )

    failure_mode_uids.release()

    async for alarm in _iter_bounded_scalar_rows(
        session,
        select(Alarm).order_by(Alarm.id),
        budget=budget,
        key_column=Alarm.id,
        key_attribute="id",
    ):
        tenant_id, wind_farm_id = turbine_scope.get(alarm.turbine_id, (None, None))
        alarm_uid = builder.node(
            NodeType.ALARM,
            alarm.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=alarm.turbine_id,
            code=alarm.code,
            title=alarm.title,
            severity=alarm.severity,
            status=alarm.status,
            aiStatus=alarm.ai_status,
            source="postgresql",
            triggeredAt=_iso(alarm.triggered_at),
        )
        subsystem_uid = ensure_subsystem(alarm.turbine_id, alarm.subsystem)
        builder.relationship(RelationshipType.AFFECTS, alarm_uid, subsystem_uid)
        anomaly_uid = builder.node(
            NodeType.ANOMALY,
            f"{alarm.id}:semantic-anomaly",
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            alarmId=alarm.id,
            turbineId=alarm.turbine_id,
            kind=alarm.code,
            summary=alarm.title,
            observedAt=_iso(alarm.triggered_at),
            source="persisted-alarm-evidence",
            evidenceJson=_json(alarm.evidence),
        )
        builder.relationship(
            RelationshipType.TRIGGERED,
            anomaly_uid,
            alarm_uid,
            observedAt=_iso(alarm.triggered_at),
            source="postgresql",
        )
        linked_mission_context = mission_by_alarm.get(alarm.id)
        if linked_mission_context is not None:
            builder.relationship(
                RelationshipType.TRIGGERED,
                alarm_uid,
                linked_mission_context.mission_uid,
                observedAt=_iso(alarm.triggered_at),
                source="postgresql-foreign-key",
            )
            if linked_mission_context.failure_uid is not None:
                builder.relationship(
                    RelationshipType.INDICATES,
                    anomaly_uid,
                    linked_mission_context.failure_uid,
                    qualifier=alarm.id,
                    confidence=linked_mission_context.confidence,
                    evidenceId=alarm.id,
                    source="persisted-alarm-and-mission-diagnosis",
                    observedAt=_iso(alarm.triggered_at),
                    validFrom=_iso(alarm.triggered_at),
                    validTo=None,
                    modelVersion=KNOWLEDGE_GRAPH_MODEL_VERSION,
                    revision=linked_mission_context.revision,
                )

    mission_by_alarm.release()
    subsystem_uids.release()

    passage_uids = _BudgetedDict[str, str](budget)
    async for document in _iter_bounded_scalar_rows(
        session,
        select(KnowledgeDocument).order_by(KnowledgeDocument.id),
        budget=budget,
        key_column=KnowledgeDocument.id,
        key_attribute="id",
    ):
        document_uid = builder.node(
            NodeType.KNOWLEDGE_DOCUMENT,
            document.id,
            tenantId=document.tenant_id,
            windFarmId=document.wind_farm_id,
            turbineId=document.turbine_id,
            title=document.title,
            documentType=document.document_type,
            documentVersion=document.document_version,
            artifactSha256=document.artifact_sha256,
            citationUri=document.citation_uri,
            vectorized=document.vectorized,
            source="postgresql",
            updatedAt=_iso(document.updated_at),
        )
        passage_uids[document.citation_uri] = document_uid

    async for passage in _iter_bounded_scalar_rows(
        session,
        select(KnowledgePassage).order_by(KnowledgePassage.id),
        budget=budget,
        key_column=KnowledgePassage.id,
        key_attribute="id",
    ):
        document_uid = graph_uid(NodeType.KNOWLEDGE_DOCUMENT, passage.document_id)
        parent = builder.nodes.get(document_uid)
        if parent is None:
            continue
        citation_uri = f"windops://knowledge/passages/{passage.id}"
        passage_uid = builder.node(
            NodeType.KNOWLEDGE_PASSAGE,
            passage.id,
            tenantId=_knowledge_owner(parent.properties, "tenantId"),
            windFarmId=_knowledge_owner(parent.properties, "windFarmId"),
            turbineId=_knowledge_owner(parent.properties, "turbineId"),
            documentId=passage.document_id,
            documentVersion=passage.document_version,
            ordinal=passage.ordinal,
            pageNumber=passage.page_number,
            section=passage.section,
            body=passage.text,
            charStart=passage.char_start,
            charEnd=passage.char_end,
            nativeLocator=_json(passage.native_locator),
            sourceSha256=passage.source_sha256,
            textSha256=passage.text_sha256,
            parserVersion=passage.parser_version,
            citationUri=citation_uri,
            source="postgresql-knowledge-passage",
            updatedAt=_iso(passage.indexed_at or passage.created_at),
        )
        passage_uids[citation_uri] = passage_uid
        builder.relationship(RelationshipType.HAS_PASSAGE, document_uid, passage_uid)

    # Preserve access to historical aggregate text without inventing a file page.
    has_passages = exists(select(1).where(KnowledgePassage.document_id == KnowledgeDocument.id))
    async for document in _iter_bounded_scalar_rows(
        session,
        select(KnowledgeDocument).where(~has_passages).order_by(KnowledgeDocument.id),
        budget=budget,
        key_column=KnowledgeDocument.id,
        key_attribute="id",
    ):
        document_uid = graph_uid(NodeType.KNOWLEDGE_DOCUMENT, document.id)
        passage_uid = builder.node(
            NodeType.KNOWLEDGE_PASSAGE,
            f"{document.id}#body",
            tenantId=document.tenant_id,
            windFarmId=document.wind_farm_id,
            turbineId=document.turbine_id,
            documentId=document.id,
            documentVersion=document.document_version,
            pageNumber=None,
            nativeLocator='{"kind":"database_text","source_verified":false}',
            section="body",
            body=document.body,
            tokenEstimate=max(1, len(document.body.encode("utf-8")) // 4),
            citationUri=document.citation_uri,
            source="postgresql-knowledge-document",
            updatedAt=_iso(document.updated_at),
        )
        builder.relationship(RelationshipType.HAS_PASSAGE, document_uid, passage_uid)

    async for evidence in _iter_bounded_scalar_rows(
        session,
        select(Evidence).order_by(Evidence.id),
        budget=budget,
        key_column=Evidence.id,
        key_attribute="id",
    ):
        linked_mission = mission_context.get(evidence.mission_id)
        tenant_id, wind_farm_id = (
            turbine_scope.get(linked_mission.turbine_id, (None, None))
            if linked_mission is not None
            else (None, None)
        )
        stance = str(evidence.metrics.get("stance", "supporting")).strip().lower()
        relationship_type = (
            RelationshipType.CONTRADICTED_BY
            if stance == "contradicting"
            else RelationshipType.SUPPORTED_BY
        )
        evidence_uid = builder.node(
            NodeType.EVIDENCE,
            evidence.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=linked_mission.turbine_id if linked_mission is not None else None,
            missionId=evidence.mission_id,
            sourceKey=evidence.source_key,
            evidenceType=evidence.evidence_type,
            summary=evidence.summary,
            citationUri=evidence.citation_uri,
            retrievalMethod=evidence.retrieval_method,
            metricsJson=_json(evidence.metrics),
            sourceRefsJson=_json(evidence.source_refs),
            source="postgresql",
            createdAt=_iso(evidence.created_at),
        )
        if linked_mission is not None:
            builder.relationship(
                relationship_type, linked_mission.mission_uid, evidence_uid, stance=stance
            )
            if linked_mission.failure_uid is not None:
                builder.relationship(
                    relationship_type,
                    linked_mission.failure_uid,
                    evidence_uid,
                    qualifier=evidence.id,
                    evidenceId=evidence.id,
                    source="postgresql-evidence",
                    observedAt=_iso(evidence.created_at),
                    stance=stance,
                )
        if evidence.citation_uri:
            for uri in set(
                re.findall(
                    r"windops://knowledge/(?:documents|passages)/[A-Za-z0-9._-]+",
                    evidence.citation_uri,
                )
            ):
                citation_node_uid = passage_uids.get(uri)
                if citation_node_uid is not None:
                    builder.relationship(
                        RelationshipType.DERIVED_FROM,
                        evidence_uid,
                        citation_node_uid,
                        citationUri=evidence.citation_uri,
                        retrievalMethod=evidence.retrieval_method,
                    )

    passage_uids.release()

    async for decision in _iter_bounded_scalar_rows(
        session,
        select(Decision).order_by(Decision.id),
        budget=budget,
        key_column=Decision.id,
        key_attribute="id",
    ):
        linked_mission = mission_context.get(decision.mission_id)
        tenant_id, wind_farm_id = (
            turbine_scope.get(linked_mission.turbine_id, (None, None))
            if linked_mission is not None
            else (None, None)
        )
        decision_uid = builder.node(
            NodeType.DECISION,
            decision.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=linked_mission.turbine_id if linked_mission is not None else None,
            missionId=decision.mission_id,
            status=decision.status,
            recommendedAlternativeId=decision.recommended_alternative_id,
            recommendationReason=decision.recommendation_reason,
            alternativesJson=_json(decision.alternatives),
            risksJson=_json(decision.risks),
            source="postgresql",
            createdAt=_iso(decision.created_at),
            updatedAt=_iso(decision.updated_at),
        )
        if linked_mission is not None:
            builder.relationship(
                RelationshipType.HAS_DECISION,
                linked_mission.mission_uid,
                decision_uid,
            )

    work_order_context = _BudgetedDict[str, _WorkOrderContext](budget)
    work_order_by_mission = _BudgetedDict[str, _WorkOrderContext](budget)
    async for work_order in _iter_bounded_scalar_rows(
        session,
        select(WorkOrder).order_by(WorkOrder.id),
        budget=budget,
        key_column=WorkOrder.id,
        key_attribute="id",
    ):
        tenant_id, wind_farm_id = turbine_scope.get(work_order.turbine_id, (None, None))
        work_order_uid = builder.node(
            NodeType.WORK_ORDER,
            work_order.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            missionId=work_order.mission_id,
            turbineId=work_order.turbine_id,
            title=work_order.title,
            status=work_order.status,
            priority=work_order.priority,
            assignedTeam=work_order.assigned_team,
            source="postgresql",
            createdAt=_iso(work_order.created_at),
            completedAt=_iso(work_order.completed_at),
        )
        work_order_context_value = _WorkOrderContext(
            work_order_uid,
            work_order.turbine_id,
            work_order.mission_id,
        )
        work_order_context[work_order.id] = work_order_context_value
        work_order_by_mission[work_order.mission_id] = work_order_context_value
        linked_mission = mission_context.get(work_order.mission_id)
        if linked_mission is not None:
            builder.relationship(
                RelationshipType.HAS_WORK_ORDER,
                linked_mission.mission_uid,
                work_order_uid,
            )
            if linked_mission.failure_uid is not None:
                builder.relationship(
                    RelationshipType.RESOLVED_BY,
                    linked_mission.failure_uid,
                    work_order_uid,
                )

    task_context = _BudgetedDict[str, _TaskContext](budget)
    async for task in _iter_bounded_scalar_rows(
        session,
        select(WorkOrderTask).order_by(WorkOrderTask.id),
        budget=budget,
        key_column=WorkOrderTask.id,
        key_attribute="id",
    ):
        linked_work_order = work_order_context.get(task.work_order_id)
        tenant_id, wind_farm_id = (
            turbine_scope.get(linked_work_order.turbine_id, (None, None))
            if linked_work_order is not None
            else (None, None)
        )
        procedure_uid = builder.node(
            NodeType.PROCEDURE,
            task.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=linked_work_order.turbine_id if linked_work_order is not None else None,
            workOrderId=task.work_order_id,
            sequence=task.sequence,
            title=task.title,
            status=task.status,
            result=task.result,
            completedBy=task.completed_by,
            completedAt=_iso(task.completed_at),
            source="postgresql-work-order-task",
        )
        task_context[task.id] = _TaskContext(task.work_order_id)
        if linked_work_order is not None:
            builder.relationship(
                RelationshipType.HAS_PROCEDURE,
                linked_work_order.work_order_uid,
                procedure_uid,
            )

    async for item in _iter_bounded_scalar_rows(
        session,
        select(FieldTaskEvidence).order_by(FieldTaskEvidence.id),
        budget=budget,
        key_column=FieldTaskEvidence.id,
        key_attribute="id",
    ):
        linked_task = task_context.get(item.task_id)
        linked_work_order = (
            work_order_context.get(linked_task.work_order_id) if linked_task is not None else None
        )
        tenant_id, wind_farm_id = (
            turbine_scope.get(linked_work_order.turbine_id, (None, None))
            if linked_work_order is not None
            else (None, None)
        )
        evidence_id = f"FIELD:{item.id}"
        evidence_uid = builder.node(
            NodeType.EVIDENCE,
            evidence_id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=linked_work_order.turbine_id if linked_work_order is not None else None,
            taskId=item.task_id,
            evidenceType="field-task-evidence",
            summary="Verified field task evidence",
            artifactUri=item.artifact_uri,
            artifactSha256=item.artifact_sha256,
            measurementJson=_json(item.measurement),
            verifiedBy=item.verified_by,
            source="postgresql-field-evidence",
            createdAt=_iso(item.verified_at),
        )
        if linked_task is not None:
            procedure_uid = graph_uid(NodeType.PROCEDURE, item.task_id)
            builder.relationship(RelationshipType.SUPPORTED_BY, procedure_uid, evidence_uid)
            if linked_work_order is not None:
                linked_mission = mission_context.get(linked_work_order.mission_id)
                if linked_mission is not None and linked_mission.failure_uid is not None:
                    builder.relationship(
                        RelationshipType.SUPPORTED_BY,
                        linked_mission.failure_uid,
                        evidence_uid,
                        qualifier=evidence_id,
                        evidenceId=evidence_id,
                        source="verified-field-task",
                        observedAt=_iso(item.verified_at),
                        stance="supporting",
                    )

    task_context.release()
    work_order_context.release()

    resource_scope_values = _BudgetedDict[
        str, frozenset[tuple[str | None, str | None, str | None]]
    ](budget)
    async for reservation in _iter_bounded_scalar_rows(
        session,
        select(ResourceReservation).order_by(ResourceReservation.id),
        budget=budget,
        key_column=ResourceReservation.id,
        key_attribute="id",
    ):
        reserved_work_order = work_order_by_mission.get(reservation.mission_id)
        if reserved_work_order is not None:
            tenant_id, wind_farm_id = turbine_scope.get(
                reserved_work_order.turbine_id, (None, None)
            )
            scopes = resource_scope_values.get(reservation.resource_id, frozenset())
            resource_scope_values[reservation.resource_id] = scopes | frozenset(
                {(tenant_id, wind_farm_id, reserved_work_order.turbine_id)}
            )

    resource_context = _BudgetedDict[str, _ResourceContext](budget)
    async for resource in _iter_bounded_scalar_rows(
        session,
        select(Resource).order_by(Resource.id),
        budget=budget,
        key_column=Resource.id,
        key_attribute="id",
    ):
        scopes = resource_scope_values.get(resource.id, frozenset())
        tenant_ids = {scope[0] for scope in scopes if scope[0] is not None}
        wind_farm_ids = {scope[1] for scope in scopes if scope[1] is not None}
        turbine_ids = {scope[2] for scope in scopes if scope[2] is not None}
        node_type = NodeType.PART if resource.resource_type == "spare_part" else NodeType.RESOURCE
        resource_uid = builder.node(
            node_type,
            resource.id,
            tenantId=next(iter(tenant_ids)) if len(tenant_ids) == 1 else None,
            windFarmId=next(iter(wind_farm_ids)) if len(wind_farm_ids) == 1 else None,
            turbineId=next(iter(turbine_ids)) if len(turbine_ids) == 1 else None,
            resourceType=resource.resource_type,
            name=resource.name,
            quantity=resource.quantity,
            status=resource.status,
            source="postgresql",
        )
        resource_context[resource.id] = _ResourceContext(
            resource_uid=resource_uid,
            resource_type=resource.resource_type,
        )

    resource_scope_values.release()

    # A second bounded pass emits relationships after resource nodes exist. It
    # intentionally trades bounded database reads for eliminating the complete
    # in-memory reservation list that previously lived through serialization.
    async for reservation in _iter_bounded_scalar_rows(
        session,
        select(ResourceReservation).order_by(ResourceReservation.id),
        budget=budget,
        key_column=ResourceReservation.id,
        key_attribute="id",
    ):
        reserved_work_order = work_order_by_mission.get(reservation.mission_id)
        reserved_resource = resource_context.get(reservation.resource_id)
        if reserved_work_order is None or reserved_resource is None:
            continue
        relationship_type = (
            RelationshipType.REQUIRES_PART
            if reserved_resource.resource_type == "spare_part"
            else RelationshipType.EXECUTED_BY
            if reserved_resource.resource_type == "crew"
            else RelationshipType.ASSIGNED_TO
        )
        builder.relationship(
            relationship_type,
            reserved_work_order.work_order_uid,
            reserved_resource.resource_uid,
            quantity=reservation.quantity,
            source="postgresql-resource-reservation",
            createdAt=_iso(reservation.created_at),
        )

    resource_context.release()

    from windops_backend.services.structural_closure import reviewed_case_clause

    async for case in _iter_bounded_scalar_rows(
        session,
        select(KnowledgeCase).where(reviewed_case_clause()).order_by(KnowledgeCase.id),
        budget=budget,
        key_column=KnowledgeCase.id,
        key_attribute="id",
    ):
        tenant_id, wind_farm_id = turbine_scope.get(case.turbine_id, (None, None))
        case_uid = builder.node(
            NodeType.KNOWLEDGE_CASE,
            case.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            missionId=case.mission_id,
            workOrderId=case.work_order_id,
            turbineId=case.turbine_id,
            title=case.title,
            diagnosisJson=_json(case.diagnosis),
            resolutionJson=_json(case.resolution),
            source="postgresql",
            createdAt=_iso(case.created_at),
        )
        linked_turbine_uid = turbine_uids.get(case.turbine_id)
        if linked_turbine_uid is not None:
            builder.relationship(RelationshipType.RECORDED_FOR, case_uid, linked_turbine_uid)
        linked_work_order = work_order_by_mission.get(case.mission_id)
        if linked_work_order is not None:
            builder.relationship(
                RelationshipType.RESOLVED_BY,
                case_uid,
                linked_work_order.work_order_uid,
            )
        linked_mission = mission_context.get(case.mission_id)
        if linked_mission is not None and linked_mission.failure_uid is not None:
            builder.relationship(
                RelationshipType.SIMILAR_TO,
                linked_mission.failure_uid,
                case_uid,
                source="closed-loop-knowledge-case",
                confidence=case.diagnosis.get("confidence"),
            )

    from windops_backend.knowledge_graph.structural_projection import project_structural_nodes

    await project_structural_nodes(session, builder, budget)

    work_order_by_mission.release()
    mission_context.release()
    turbine_uids.release()
    turbine_scope.release()
    return builder.snapshot(projection_sequence)
