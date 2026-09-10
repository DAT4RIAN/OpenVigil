from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import (
    Float,
    String,
    and_,
    case,
    cast,
    func,
    literal,
    literal_column,
    or_,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.models import (
    Alarm,
    Decision,
    Mission,
    Turbine,
    WindFarm,
    WorkOrder,
)
from windops_backend.services.operational_contracts import (
    DiagnosisQueryPlan,
    OperationalPage,
    _diagnosis_related_data_boundaries,
    _diagnosis_status,
    _public_output_text,
    _risk,
    _safe_number,
)
from windops_backend.services.operational_related import (
    _bounded_evidence_by_mission,
    _bounded_executions_by_mission,
)

# Operational pages are summaries, not ledger exports.  Keep the default page
# useful while ensuring pathological per-parent fan-out cannot turn one bounded
# page into an unbounded response.  Full ledgers remain available from their
# dedicated mission/work-order APIs.
DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT = 1
DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT = 1
MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT = 1
MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT = 1
DIAGNOSIS_RISK_PRIORITY = ("critical", "high", "medium", "low")


def _diagnosis_risk_expression(
    alarm_severity: Any = Alarm.severity,
    health_score: Any = Turbine.health_score,
) -> Any:
    return case(
        (or_(alarm_severity == "critical", health_score < 60), "critical"),
        (or_(alarm_severity.in_(("major", "high")), health_score < 75), "high"),
        (
            or_(alarm_severity.in_(("minor", "warning")), health_score < 90),
            "medium",
        ),
        else_="low",
    )


def _diagnosis_status_expression(work_order_status: Any = WorkOrder.status) -> Any:
    return case(
        (work_order_status.in_(("completed", "closed")), "closed"),
        (work_order_status.in_(("in_progress", "in-progress")), "in-progress"),
        (work_order_status.in_(("scheduled", "ready")), "scheduled"),
        (Mission.status.in_(("under_review", "under-review")), "awaiting-review"),
        (
            Mission.status.in_(("revision_requested", "revision-requested")),
            "revision-needed",
        ),
        (Mission.status == "rejected", "rejected"),
        (Mission.status.in_(("diagnosed", "decision_pending", "decision-pending")), "analyzed"),
        (Mission.status == "investigating", "triage"),
        else_="monitoring",
    )


def _diagnosis_risk_weight_expression(
    alarm_severity: Any = Alarm.severity,
    health_score: Any = Turbine.health_score,
) -> Any:
    """Numeric priority without repeatedly nesting the public risk CASE."""

    return case(
        (or_(alarm_severity == "critical", health_score < 60), 4),
        (or_(alarm_severity.in_(("major", "high")), health_score < 75), 3),
        (
            or_(alarm_severity.in_(("minor", "warning")), health_score < 90),
            2,
        ),
        else_=1,
    )


def _diagnosis_priority_bucket_predicates(
    alarm_severity: Any,
    health_score: Any,
) -> dict[str, tuple[Any, ...]]:
    """Return disjoint predicates for the public diagnosis risk buckets.

    Splitting each cross-table OR into mutually exclusive branches lets
    PostgreSQL limit each ordered branch before merging at most ``2 * page``
    candidates.  Literal fixed-vocabulary values also avoid a generic prepared
    plan that cannot estimate the alarm-severity selectivity.
    """

    critical: Any = literal_column("'critical'")
    major: Any = literal_column("'major'")
    high: Any = literal_column("'high'")
    minor: Any = literal_column("'minor'")
    warning: Any = literal_column("'warning'")
    critical_or_higher = (critical,)
    high_or_higher = (critical, major, high)
    medium_or_higher = (critical, major, high, minor, warning)
    return {
        "critical": (
            alarm_severity == critical,
            and_(alarm_severity.not_in(critical_or_higher), health_score < 60),
        ),
        "high": (
            and_(alarm_severity.in_((major, high)), health_score >= 60),
            and_(
                alarm_severity.not_in(high_or_higher),
                health_score >= 60,
                health_score < 75,
            ),
        ),
        "medium": (
            and_(alarm_severity.in_((minor, warning)), health_score >= 75),
            and_(
                alarm_severity.not_in(medium_or_higher),
                health_score >= 75,
                health_score < 90,
            ),
        ),
        "low": (and_(alarm_severity.not_in(medium_or_higher), health_score >= 90),),
    }


def build_diagnosis_query(
    *,
    query: str = "",
    tenant_id: str | None = None,
    wind_farm_id: str | None = None,
    turbine_id: str | None = None,
    status_filter: str | None = None,
    risk: str | None = None,
    sort_mode: str = "priority-desc",
    offset: int = 0,
    limit: int = 64,
) -> DiagnosisQueryPlan:
    """Build the production diagnosis page query used by the API service.

    Keeping this builder public lets the PostgreSQL performance gate EXPLAIN
    the same joins, computed predicates, ordering, filters, and pagination as
    the real request instead of a hand-written substitute query.
    """

    # Mission is the authoritative scoped row for this page.  The related
    # tables are deliberately Core aliases: applying the same correlated
    # asset-scope loader criterion independently to Mission, Alarm, Turbine,
    # WorkOrder, and WindFarm makes one bounded page perform several redundant
    # scope probes. Mission retains the ORM loader criterion; related rows are
    # joined only through its authoritative foreign keys.
    alarm_table = Alarm.__table__.alias("diagnosis_alarm")
    turbine_table = Turbine.__table__.alias("diagnosis_turbine")
    work_order_table = WorkOrder.__table__.alias("diagnosis_work_order")
    wind_farm_table = WindFarm.__table__.alias("diagnosis_wind_farm")
    risk_expression = _diagnosis_risk_expression(
        alarm_table.c.severity,
        turbine_table.c.health_score,
    )
    priority_bucket_predicates = _diagnosis_priority_bucket_predicates(
        alarm_table.c.severity,
        turbine_table.c.health_score,
    )
    status_expression = _diagnosis_status_expression(work_order_table.c.status)
    confidence_expression = func.coalesce(
        cast(Mission.public_state["diagnosis"]["confidence"].as_string(), Float),
        0.0,
    )
    base_statement = (
        select(Mission.id)
        .join(alarm_table, alarm_table.c.id == Mission.alarm_id)
        .join(turbine_table, turbine_table.c.id == Mission.turbine_id)
    )
    if status_filter:
        base_statement = base_statement.outerjoin(
            work_order_table,
            work_order_table.c.mission_id == Mission.id,
        )
    if tenant_id is not None or wind_farm_id is not None:
        base_statement = base_statement.join(
            wind_farm_table,
            wind_farm_table.c.id == turbine_table.c.wind_farm_id,
        )
    filters: list[Any] = []
    if tenant_id:
        filters.append(wind_farm_table.c.tenant_id == tenant_id)
    if wind_farm_id:
        filters.append(turbine_table.c.wind_farm_id == wind_farm_id)
    if turbine_id:
        filters.append(Mission.turbine_id == turbine_id)
    if status_filter:
        filters.append(status_expression == status_filter)
    if risk:
        filters.append(risk_expression == risk)
    normalized_query = query.strip().lower()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        filters.append(
            or_(
                func.lower(literal("DX-") + Mission.id).like(pattern),
                func.lower(Mission.id).like(pattern),
                func.lower(Mission.turbine_id).like(pattern),
                func.lower(Mission.title).like(pattern),
                func.lower(alarm_table.c.title).like(pattern),
                func.lower(cast(Mission.public_state, String)).like(pattern),
            )
        )
    filtered_statement = base_statement.where(*filters)
    filtered_count_statement = select(func.count(Mission.id)).select_from(Mission)
    if risk or normalized_query:
        filtered_count_statement = filtered_count_statement.join(
            alarm_table,
            alarm_table.c.id == Mission.alarm_id,
        )
    if risk or tenant_id is not None or wind_farm_id is not None:
        filtered_count_statement = filtered_count_statement.join(
            turbine_table,
            turbine_table.c.id == Mission.turbine_id,
        )
    if status_filter:
        filtered_count_statement = filtered_count_statement.outerjoin(
            work_order_table,
            work_order_table.c.mission_id == Mission.id,
        )
    if tenant_id is not None or wind_farm_id is not None:
        filtered_count_statement = filtered_count_statement.join(
            wind_farm_table,
            wind_farm_table.c.id == turbine_table.c.wind_farm_id,
        )
    filtered_count_statement = filtered_count_statement.where(*filters)
    risk_weight = _diagnosis_risk_weight_expression(
        alarm_table.c.severity,
        turbine_table.c.health_score,
    )
    if sort_mode == "updated-desc":
        ordering: tuple[Any, ...] = (Mission.updated_at.desc(), Mission.id.desc())
    elif sort_mode == "confidence-desc":
        ordering = (confidence_expression.desc(), Mission.updated_at.desc(), Mission.id.desc())
    elif sort_mode == "turbine-asc":
        ordering = (Mission.turbine_id.asc(), Mission.id.asc())
    else:
        ordering = (
            risk_weight.desc(),
            Mission.updated_at.desc(),
            Mission.id.desc(),
        )
    return DiagnosisQueryPlan(
        filtered=filtered_statement,
        filtered_count=filtered_count_statement,
        page=filtered_statement.order_by(*ordering).offset(offset).limit(limit),
        risk_expression=risk_expression,
        priority_bucket_predicates=priority_bucket_predicates,
        status_expression=status_expression,
        confidence_expression=confidence_expression,
    )


def build_diagnosis_priority_bucket_query(
    query_plan: DiagnosisQueryPlan,
    *,
    risk_bucket: str,
    fetch_limit: int,
) -> Any:
    """Build one bounded priority bucket from the shared filtered query.

    A global computed-risk sort must evaluate and sort every matching Mission.
    Each mutually exclusive branch keeps only its top candidates; the final
    merge therefore sorts at most twice the requested page while preserving
    the exact risk and updated-at ordering.
    """

    if risk_bucket not in DIAGNOSIS_RISK_PRIORITY:
        raise ValueError("unsupported diagnosis risk bucket")
    if fetch_limit < 1:
        raise ValueError("diagnosis priority fetch limit must be positive")
    branch_statements = []
    for index, predicate in enumerate(query_plan.priority_bucket_predicates[risk_bucket]):
        limited_branch = (
            query_plan.filtered.add_columns(Mission.updated_at.label("priority_updated_at"))
            .where(predicate)
            .order_by(Mission.updated_at.desc(), Mission.id.desc())
            .limit(fetch_limit)
            .subquery(f"diagnosis_priority_branch_{index}")
        )
        branch_statements.append(select(limited_branch.c.id, limited_branch.c.priority_updated_at))
    candidates = union_all(*branch_statements).subquery("diagnosis_priority_candidates")
    return (
        select(candidates.c.id)
        .order_by(candidates.c.priority_updated_at.desc(), candidates.c.id.desc())
        .limit(fetch_limit)
    )


async def _diagnosis_priority_page_ids(
    session: AsyncSession,
    query_plan: DiagnosisQueryPlan,
    *,
    offset: int,
    limit: int,
    requested_risk: str | None,
) -> list[str]:
    buckets = (
        (requested_risk,) if requested_risk in DIAGNOSIS_RISK_PRIORITY else DIAGNOSIS_RISK_PRIORITY
    )
    remaining_offset = offset
    page_ids: list[str] = []
    for risk_bucket in buckets:
        needed = limit - len(page_ids)
        candidates = list(
            (
                await session.scalars(
                    build_diagnosis_priority_bucket_query(
                        query_plan,
                        risk_bucket=risk_bucket,
                        fetch_limit=remaining_offset + needed,
                    )
                )
            ).all()
        )
        if len(candidates) <= remaining_offset:
            remaining_offset -= len(candidates)
            continue
        page_ids.extend(candidates[remaining_offset : remaining_offset + needed])
        remaining_offset = 0
        if len(page_ids) == limit:
            break
    return page_ids


async def diagnosis_rows(
    session: AsyncSession,
    *,
    query: str = "",
    tenant_id: str | None = None,
    wind_farm_id: str | None = None,
    turbine_id: str | None = None,
    status_filter: str | None = None,
    risk: str | None = None,
    sort_mode: str = "priority-desc",
    offset: int = 0,
    limit: int = 64,
    _query_builder: Callable[..., DiagnosisQueryPlan] | None = None,
) -> OperationalPage:
    query_plan = (_query_builder or build_diagnosis_query)(
        query=query,
        tenant_id=tenant_id,
        wind_farm_id=wind_farm_id,
        turbine_id=turbine_id,
        status_filter=status_filter,
        risk=risk,
        sort_mode=sort_mode,
        offset=offset,
        limit=limit,
    )
    total = int(await session.scalar(select(func.count(Mission.id))) or 0)
    filtered_total = int(await session.scalar(query_plan.filtered_count) or 0)
    if sort_mode == "priority-desc":
        mission_ids = await _diagnosis_priority_page_ids(
            session,
            query_plan,
            offset=offset,
            limit=limit,
            requested_risk=risk,
        )
    else:
        mission_ids = list((await session.scalars(query_plan.page)).all())
    if not mission_ids:
        return OperationalPage(
            rows=[],
            total=total,
            filtered_total=filtered_total,
            related_data_boundaries=_diagnosis_related_data_boundaries(),
        )
    mission_order = {mission_id: index for index, mission_id in enumerate(mission_ids)}
    page_turbine_table = Turbine.__table__.alias("diagnosis_page_turbine")
    page_alarm_table = Alarm.__table__.alias("diagnosis_page_alarm")
    page_decision_table = Decision.__table__.alias("diagnosis_page_decision")
    page_work_order_table = WorkOrder.__table__.alias("diagnosis_page_work_order")
    # Mission remains the authoritative scoped ORM entity. Its one-to-one
    # turbine/alarm/decision/work-order data can be hydrated in the same query
    # through Core aliases without repeating four access-policy compilations.
    mission_records = list(
        (
            await session.execute(
                select(
                    Mission,
                    page_turbine_table.c.id.label("page_turbine_id"),
                    page_turbine_table.c.status.label("page_turbine_status"),
                    page_turbine_table.c.health_score.label("page_health_score"),
                    page_alarm_table.c.id.label("page_alarm_id"),
                    page_alarm_table.c.severity.label("page_alarm_severity"),
                    page_alarm_table.c.status.label("page_alarm_status"),
                    page_alarm_table.c.evidence.label("page_alarm_evidence"),
                    page_alarm_table.c.subsystem.label("page_alarm_subsystem"),
                    page_alarm_table.c.title.label("page_alarm_title"),
                    page_alarm_table.c.code.label("page_alarm_code"),
                    page_alarm_table.c.triggered_at.label("page_alarm_triggered_at"),
                    page_decision_table.c.status.label("page_decision_status"),
                    page_work_order_table.c.status.label("page_work_order_status"),
                )
                .join(
                    page_turbine_table,
                    page_turbine_table.c.id == Mission.turbine_id,
                )
                .join(
                    page_alarm_table,
                    page_alarm_table.c.id == Mission.alarm_id,
                )
                .outerjoin(
                    page_decision_table,
                    page_decision_table.c.mission_id == Mission.id,
                )
                .outerjoin(
                    page_work_order_table,
                    page_work_order_table.c.mission_id == Mission.id,
                )
                .where(Mission.id.in_(mission_ids))
            )
        ).all()
    )
    mission_records.sort(key=lambda record: mission_order[record[0].id])
    if not mission_records:
        return OperationalPage(
            rows=[],
            total=total,
            filtered_total=filtered_total,
            related_data_boundaries=_diagnosis_related_data_boundaries(),
        )
    loaded_mission_ids = [record[0].id for record in mission_records]
    evidence_by_mission, evidence_truncated = await _bounded_evidence_by_mission(
        session, loaded_mission_ids
    )
    executions_by_mission, execution_truncated = await _bounded_executions_by_mission(
        session, loaded_mission_ids
    )
    rows: list[dict[str, Any]] = []
    for (
        mission,
        page_turbine_id,
        page_turbine_status,
        page_health_score,
        page_alarm_id,
        page_alarm_severity,
        page_alarm_status,
        page_alarm_evidence,
        page_alarm_subsystem,
        page_alarm_title,
        page_alarm_code,
        page_alarm_triggered_at,
        page_decision_status,
        page_work_order_status,
    ) in mission_records:
        diagnosis = mission.public_state.get("diagnosis", {})
        if not isinstance(diagnosis, dict):
            diagnosis = {}
        if not isinstance(page_alarm_evidence, dict):
            page_alarm_evidence = {}
        evidences = evidence_by_mission.get(mission.id, [])
        confidence = _safe_number(diagnosis.get("confidence"))
        health_score = _safe_number(page_health_score)
        evidence_ids = [row.id for row in evidences]
        component = str(diagnosis.get("component") or page_alarm_subsystem)
        failure_mode = str(diagnosis.get("failure_mode") or page_alarm_title)
        conclusion = str(diagnosis.get("conclusion") or page_alarm_title)
        alarm_attributes = page_alarm_evidence.get("attributes", {})
        if not isinstance(alarm_attributes, dict):
            alarm_attributes = {}
        alarm_value = _safe_number(page_alarm_evidence.get("value"))
        anomaly_score = _safe_number(alarm_attributes.get("anomaly_score"))
        signals = [
            {
                "id": f"{page_alarm_id}:primary",
                "label": str(page_alarm_evidence.get("variable") or page_alarm_code),
                "value": alarm_value,
                "baseline": alarm_value,
                "unit": str(page_alarm_evidence.get("unit") or ""),
                "deltaPercent": 0,
                "abnormal": True,
            }
        ]
        citations = [
            {
                "id": evidence.id,
                "title": evidence.source_key,
                "sourceLabel": evidence.evidence_type,
                "sourceType": evidence.evidence_type,
                "observedAt": evidence.created_at,
                "summary": evidence.summary,
                "href": evidence.citation_uri or f"/missions/{mission.id}#evidence",
                "deepLink": True,
            }
            for evidence in evidences
        ]
        collaboration = [
            {
                "id": execution.id,
                "sequence": index,
                "agentId": execution.agent_role,
                "agentName": execution.agent_role.replace("_", " ").title(),
                "role": execution.node,
                "status": "complete" if execution.status == "succeeded" else "monitoring",
                "publicOutput": _public_output_text(execution.public_output),
                "evaluation": execution.evaluation_result,
                "degradationPolicy": execution.degradation_policy,
                "evidenceIds": evidence_ids,
                "toolResults": [
                    {
                        "tool": str(call.get("tool", call.get("name", "governed_tool"))),
                        "result": str(call.get("status", "recorded")),
                    }
                    for call in execution.tool_calls
                    if isinstance(call, dict)
                ],
                "completedAt": execution.completed_at,
            }
            for index, execution in enumerate(executions_by_mission.get(mission.id, []), start=1)
        ]
        gate_state = "review-required"
        if page_work_order_status in {"completed", "closed"}:
            gate_state = "verified"
        elif page_work_order_status in {"in_progress", "in-progress"}:
            gate_state = "active"
        elif page_decision_status == "approved":
            gate_state = "authorized"
        elif page_decision_status is None:
            gate_state = "locked"
        rows.append(
            {
                "id": f"DX-{mission.id}",
                "turbineId": page_turbine_id,
                "turbineStatus": page_turbine_status,
                "healthScore": health_score,
                "risk": _risk(str(page_alarm_severity), health_score),
                "status": _diagnosis_status(mission.status, page_work_order_status),
                "headline": conclusion,
                "overallConfidencePercent": round(confidence * 100),
                "missionId": mission.id,
                "activeAlarmCount": 0 if page_alarm_status == "resolved" else 1,
                "updatedAt": mission.updated_at,
                "anomaly": {
                    "source": "alarm-correlation",
                    "detectedAt": page_alarm_triggered_at,
                    "anomalyScore": anomaly_score,
                    "threshold": _safe_number(alarm_attributes.get("threshold")),
                    "summary": page_alarm_title,
                    "signals": signals,
                },
                "candidates": [
                    {
                        "id": f"{mission.id}:candidate:1",
                        "faultMode": failure_mode,
                        "subsystem": component,
                        "probabilityPercent": round(confidence * 100),
                        "confidencePercent": round(confidence * 100),
                        "supportingEvidenceIds": evidence_ids,
                        "supportingSummary": [row.summary for row in evidences],
                        "counterEvidence": [],
                        "recommendedNextStep": (
                            "Complete human review before any controlled maintenance action."
                        ),
                    }
                ],
                "citations": citations,
                "collaboration": collaboration,
                "gate": {
                    "state": gate_state,
                    "humanReviewRequired": gate_state in {"locked", "review-required"},
                    "title": "Governed human approval gate",
                    "explanation": (
                        "Execution remains controlled by the persisted decision and approval state."
                    ),
                    "allowedActions": ["review evidence", "record approval"],
                    "blockedActions": (
                        ["create work order", "dispatch field work"]
                        if gate_state in {"locked", "review-required"}
                        else []
                    ),
                    "decisionStatus": page_decision_status,
                    "workOrderStatus": page_work_order_status,
                },
            }
        )
    return OperationalPage(
        rows=rows,
        total=total,
        filtered_total=filtered_total,
        related_data_boundaries=_diagnosis_related_data_boundaries(
            evidence_truncated_missions=len(evidence_truncated),
            execution_truncated_missions=len(execution_truncated),
        ),
    )
