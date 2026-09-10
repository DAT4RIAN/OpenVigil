from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from sqlalchemy import and_, event, exists, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria
from sqlalchemy.sql.elements import ColumnElement

from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    AgentDefinition,
    AgentExecution,
    AgentSkillLink,
    AgentToolInvocation,
    AgentToolLink,
    Alarm,
    Approval,
    AssetHealthEvent,
    AssetTwinProfile,
    CatalogVersion,
    DataContractDefinition,
    Decision,
    DomainEvent,
    Evidence,
    ExternalWorkOrderLink,
    GeneratedReport,
    IngestSource,
    KnowledgeCase,
    KnowledgeDocument,
    Mission,
    MissionComment,
    ModelDeployment,
    ModelPrediction,
    PlatformConfigurationRevision,
    PlatformConfigurationSecurityAudit,
    ReadAccessAudit,
    RegisteredModel,
    Resource,
    ResourceReservation,
    ScadaSample,
    SkillDefinition,
    Tenant,
    ToolDefinition,
    Turbine,
    WeatherWindow,
    WindFarm,
    WorkOrder,
    WorkOrderTask,
)

ACCESS_POLICY_SESSION_KEY = "windops_access_policy"

_DATA_SCOPE_ALIASES: dict[str, frozenset[str]] = {
    "agent": frozenset({"agent", "agents", "automation"}),
    "alarm": frozenset({"alarm", "alarms"}),
    "asset": frozenset({"asset", "assets", "turbine", "turbines", "wind_farm", "wind_farms"}),
    "benchmark": frozenset({"benchmark", "benchmarks", "benchmark_dataset", "benchmark_datasets"}),
    "benchmark_export": frozenset(
        {"benchmark_export", "benchmark_exports", "benchmark_artifact_export"}
    ),
    "benchmark_truth": frozenset(
        {"benchmark_truth", "benchmark_truths", "benchmark_evaluation_truth"}
    ),
    "decision": frozenset({"decision", "decisions"}),
    "knowledge": frozenset(
        {"knowledge", "knowledges", "knowledge_document", "knowledge_documents"}
    ),
    "mission": frozenset({"mission", "missions", "diagnosis", "diagnoses"}),
    "model": frozenset({"model", "models", "prediction", "predictions", "predictive_assessment"}),
    "platform": frozenset({"platform", "configuration", "configurations", "data_catalog"}),
    "report": frozenset({"report", "reports"}),
    "resource": frozenset({"resource", "resources", "inventory"}),
    "telemetry": frozenset({"telemetry", "scada", "measurement", "measurements"}),
    "work_order": frozenset({"work_order", "work_orders", "workorder", "workorders"}),
}


def attach_access_policy(session: AsyncSession, policy: GraphAccessPolicy) -> None:
    """Bind a server-created policy to every ORM read performed by this request session."""

    session.sync_session.info[ACCESS_POLICY_SESSION_KEY] = policy


def access_scope_audit(policy: GraphAccessPolicy) -> dict[str, object]:
    return {
        "tenant_ids": sorted(policy.tenant_ids),
        "wind_farm_ids": sorted(policy.wind_farm_ids),
        "turbine_ids": sorted(policy.turbine_ids),
        "entity_ids": sorted(policy.entity_ids),
        "data_scopes": sorted(policy.data_scopes),
        "allow_global": policy.allow_global,
        "unrestricted": policy.unrestricted,
    }


def has_asset_grant(policy: GraphAccessPolicy) -> bool:
    return bool(
        policy.tenant_ids or policy.wind_farm_ids or policy.turbine_ids or policy.entity_ids
    )


def has_business_scope(policy: GraphAccessPolicy) -> bool:
    return policy.unrestricted or policy.allow_global or has_asset_grant(policy)


def data_scope_allowed(policy: GraphAccessPolicy, scopes: str | Sequence[str]) -> bool:
    if policy.unrestricted or not policy.data_scopes or "*" in policy.data_scopes:
        return True
    requested = (scopes,) if isinstance(scopes, str) else scopes
    aliases: set[str] = set()
    for scope in requested:
        normalized = scope.strip().casefold()
        aliases.update(_DATA_SCOPE_ALIASES.get(normalized, {normalized, f"{normalized}s"}))
    return bool(aliases.intersection(policy.data_scopes))


def _ci_match(column: Any, allowed: frozenset[str]) -> ColumnElement[bool]:
    if "*" in allowed:
        return true()
    return func.lower(column).in_(tuple(sorted(allowed)))


def _entity_match(policy: GraphAccessPolicy, columns: Sequence[Any]) -> ColumnElement[bool]:
    if not policy.entity_ids:
        return true()
    if not columns:
        return false()
    return or_(*(_ci_match(column, policy.entity_ids) for column in columns))


def turbine_scope_clause(
    policy: GraphAccessPolicy,
    turbine_id_column: Any,
    *,
    entity_columns: Sequence[Any] = (),
    data_scopes: str | Sequence[str] = "asset",
) -> ColumnElement[bool]:
    """Authorize a row through its authoritative turbine -> farm -> tenant chain."""

    if policy.unrestricted:
        return true()
    if not data_scope_allowed(policy, data_scopes) or not has_asset_grant(policy):
        return false()

    turbine_table = Turbine.__table__.alias("scope_turbine")
    farm_table = WindFarm.__table__.alias("scope_wind_farm")
    conditions: list[ColumnElement[bool]] = [
        turbine_table.c.id == turbine_id_column,
    ]
    if policy.tenant_ids:
        conditions.append(_ci_match(farm_table.c.tenant_id, policy.tenant_ids))
    if policy.wind_farm_ids:
        conditions.append(_ci_match(turbine_table.c.wind_farm_id, policy.wind_farm_ids))
    if policy.turbine_ids:
        conditions.append(_ci_match(turbine_table.c.id, policy.turbine_ids))
    conditions.append(
        _entity_match(
            policy,
            (
                turbine_table.c.id,
                turbine_table.c.wind_farm_id,
                farm_table.c.tenant_id,
                *entity_columns,
            ),
        )
    )
    return exists(
        select(1)
        .select_from(
            turbine_table.join(
                farm_table,
                farm_table.c.id == turbine_table.c.wind_farm_id,
            )
        )
        .where(*conditions)
    )


def wind_farm_scope_clause(
    policy: GraphAccessPolicy,
    wind_farm_id_column: Any,
    *,
    entity_columns: Sequence[Any] = (),
    data_scopes: str | Sequence[str] = "asset",
) -> ColumnElement[bool]:
    if policy.unrestricted:
        return true()
    if not data_scope_allowed(policy, data_scopes) or not has_asset_grant(policy):
        return false()
    # A turbine-only grant does not implicitly grant sibling farm data.
    if policy.turbine_ids:
        return false()

    farm_table = WindFarm.__table__.alias("scope_wind_farm")
    conditions: list[ColumnElement[bool]] = [farm_table.c.id == wind_farm_id_column]
    if policy.tenant_ids:
        conditions.append(_ci_match(farm_table.c.tenant_id, policy.tenant_ids))
    if policy.wind_farm_ids:
        conditions.append(_ci_match(farm_table.c.id, policy.wind_farm_ids))
    conditions.append(
        _entity_match(
            policy,
            (farm_table.c.id, farm_table.c.tenant_id, *entity_columns),
        )
    )
    return exists(select(1).select_from(farm_table).where(*conditions))


def tenant_scope_clause(
    policy: GraphAccessPolicy,
    tenant_id_column: Any,
    *,
    entity_columns: Sequence[Any] = (),
    data_scopes: str | Sequence[str] = "asset",
) -> ColumnElement[bool]:
    if policy.unrestricted:
        return true()
    if not data_scope_allowed(policy, data_scopes) or not has_asset_grant(policy):
        return false()
    # Narrower grants do not reveal tenant-wide metadata.
    if policy.wind_farm_ids or policy.turbine_ids:
        return false()
    if policy.tenant_ids and not _is_wildcard(policy.tenant_ids):
        scope = _ci_match(tenant_id_column, policy.tenant_ids)
    elif policy.tenant_ids:
        scope = true()
    else:
        scope = false()
    return and_(scope, _entity_match(policy, (tenant_id_column, *entity_columns)))


def _is_wildcard(values: frozenset[str]) -> bool:
    return "*" in values


def mission_scope_clause(
    policy: GraphAccessPolicy,
    mission_id_column: Any,
    *,
    entity_columns: Sequence[Any] = (),
    data_scopes: str | Sequence[str] = "mission",
) -> ColumnElement[bool]:
    mission_table = Mission.__table__.alias("scope_mission")
    return exists(
        select(1)
        .select_from(mission_table)
        .where(
            mission_table.c.id == mission_id_column,
            turbine_scope_clause(
                policy,
                mission_table.c.turbine_id,
                entity_columns=(mission_table.c.id, mission_table.c.alarm_id, *entity_columns),
                data_scopes=data_scopes,
            ),
        )
    )


def work_order_scope_clause(
    policy: GraphAccessPolicy,
    work_order_id_column: Any,
    *,
    entity_columns: Sequence[Any] = (),
    data_scopes: str | Sequence[str] = "work_order",
) -> ColumnElement[bool]:
    work_order_table = WorkOrder.__table__.alias("scope_work_order")
    return exists(
        select(1)
        .select_from(work_order_table)
        .where(
            work_order_table.c.id == work_order_id_column,
            turbine_scope_clause(
                policy,
                work_order_table.c.turbine_id,
                entity_columns=(
                    work_order_table.c.id,
                    work_order_table.c.mission_id,
                    *entity_columns,
                ),
                data_scopes=data_scopes,
            ),
        )
    )


def global_scope_clause(
    policy: GraphAccessPolicy,
    *,
    entity_columns: Sequence[Any] = (),
    data_scopes: str | Sequence[str],
) -> ColumnElement[bool]:
    if policy.unrestricted:
        return true()
    if not policy.allow_global or not data_scope_allowed(policy, data_scopes):
        return false()
    return _entity_match(policy, entity_columns)


def nullable_asset_scope_clause(
    policy: GraphAccessPolicy,
    *,
    tenant_column: Any,
    wind_farm_column: Any,
    turbine_column: Any,
    entity_columns: Sequence[Any] = (),
    data_scopes: str | Sequence[str],
) -> ColumnElement[bool]:
    if policy.unrestricted:
        return true()
    if not data_scope_allowed(policy, data_scopes):
        return false()

    has_asset = or_(
        tenant_column.is_not(None),
        wind_farm_column.is_not(None),
        turbine_column.is_not(None),
    )
    asset_conditions: list[ColumnElement[bool]] = [has_asset]
    if policy.tenant_ids:
        asset_conditions.append(
            and_(tenant_column.is_not(None), _ci_match(tenant_column, policy.tenant_ids))
        )
    if policy.wind_farm_ids:
        asset_conditions.append(
            and_(
                wind_farm_column.is_not(None),
                _ci_match(wind_farm_column, policy.wind_farm_ids),
            )
        )
    if policy.turbine_ids:
        asset_conditions.append(
            and_(turbine_column.is_not(None), _ci_match(turbine_column, policy.turbine_ids))
        )
    asset_conditions.append(
        _entity_match(
            policy,
            (tenant_column, wind_farm_column, turbine_column, *entity_columns),
        )
    )
    asset_visibility = and_(*asset_conditions) if has_asset_grant(policy) else false()

    global_visibility: ColumnElement[bool] = false()
    if policy.allow_global:
        global_visibility = and_(
            tenant_column.is_(None),
            wind_farm_column.is_(None),
            turbine_column.is_(None),
            _entity_match(policy, entity_columns),
        )
    return or_(asset_visibility, global_visibility)


def resource_scope_clause(
    policy: GraphAccessPolicy,
    resource_id_column: Any,
) -> ColumnElement[bool]:
    global_visibility = global_scope_clause(
        policy,
        entity_columns=(resource_id_column,),
        data_scopes="resource",
    )
    if policy.unrestricted:
        return true()
    if not data_scope_allowed(policy, "resource") or not has_asset_grant(policy):
        return global_visibility
    reservation_table = ResourceReservation.__table__.alias("scope_resource_reservation")
    scoped_reservation = exists(
        select(1)
        .select_from(reservation_table)
        .where(
            reservation_table.c.resource_id == resource_id_column,
            mission_scope_clause(
                policy,
                reservation_table.c.mission_id,
                entity_columns=(reservation_table.c.id, resource_id_column),
                data_scopes="resource",
            ),
        )
    )
    return or_(global_visibility, scoped_reservation)


def domain_event_scope_clause(policy: GraphAccessPolicy) -> ColumnElement[bool]:
    if policy.unrestricted:
        return true()

    event = DomainEvent
    branches: list[ColumnElement[bool]] = [
        and_(
            event.aggregate_type == "turbine",
            turbine_scope_clause(
                policy,
                event.aggregate_id,
                entity_columns=(event.aggregate_id,),
                data_scopes=("asset", "telemetry"),
            ),
        ),
        and_(
            event.aggregate_type == "alarm",
            _alarm_id_scope_clause(policy, event.aggregate_id, event.aggregate_id),
        ),
        and_(
            event.aggregate_type == "mission",
            mission_scope_clause(
                policy,
                event.aggregate_id,
                entity_columns=(event.aggregate_id,),
                data_scopes="mission",
            ),
        ),
        and_(
            event.aggregate_type == "decision",
            _decision_id_scope_clause(policy, event.aggregate_id),
        ),
        and_(
            event.aggregate_type == "work_order",
            work_order_scope_clause(
                policy,
                event.aggregate_id,
                entity_columns=(event.aggregate_id,),
                data_scopes="work_order",
            ),
        ),
        and_(
            event.aggregate_type == "model_prediction",
            _model_prediction_id_scope_clause(policy, event.aggregate_id),
        ),
        and_(
            event.aggregate_type == "knowledge_document",
            _knowledge_document_id_scope_clause(policy, event.aggregate_id),
        ),
        and_(
            event.aggregate_type == "resource",
            resource_scope_clause(policy, event.aggregate_id),
        ),
    ]

    global_types = {
        "agent_definition": "agent",
        "agent_tool_invocation": "agent",
        "benchmark_cleanup": "benchmark_export",
        "benchmark_dataset": "benchmark",
        "benchmark_evaluation": "benchmark",
        "benchmark_event": "benchmark",
        "benchmark_export": "benchmark_export",
        "benchmark_replay": "benchmark",
        "data_contract": "platform",
        "ingest_source": "platform",
        "knowledge_graph": "knowledge",
        "model": "model",
        "model_deployment": "model",
        "platform_configuration": "platform",
        "report": "report",
    }
    for aggregate_type, data_scope in global_types.items():
        branches.append(
            and_(
                event.aggregate_type == aggregate_type,
                global_scope_clause(
                    policy,
                    entity_columns=(event.aggregate_id,),
                    data_scopes=data_scope,
                ),
            )
        )
    return or_(*branches)


async def ensure_turbine_access(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    turbine_id: str,
    *,
    data_scopes: str | Sequence[str] = "asset",
) -> None:
    visible_id = await session.scalar(
        select(Turbine.id).where(
            Turbine.id == turbine_id,
            turbine_scope_clause(
                policy,
                Turbine.id,
                entity_columns=(Turbine.id,),
                data_scopes=data_scopes,
            ),
        )
    )
    if visible_id is None:
        from windops_backend.errors import NotFoundError

        raise NotFoundError(f"turbine {turbine_id} was not found")


async def ensure_work_order_task_access(
    session: AsyncSession,
    policy: GraphAccessPolicy,
    work_order_id: str,
    task_id: str | None = None,
) -> None:
    statement = select(WorkOrder.id).where(
        WorkOrder.id == work_order_id,
        work_order_scope_clause(
            policy,
            WorkOrder.id,
            entity_columns=(WorkOrder.id,),
            data_scopes="work_order",
        ),
    )
    if task_id is not None:
        task_table = WorkOrderTask.__table__.alias("authorized_task")
        statement = statement.where(
            exists(
                select(1)
                .select_from(task_table)
                .where(
                    task_table.c.id == task_id,
                    task_table.c.work_order_id == WorkOrder.id,
                )
            )
        )
    if await session.scalar(statement) is None:
        from windops_backend.errors import NotFoundError

        raise NotFoundError(f"work order {work_order_id} or task {task_id} was not found")


def _alarm_id_scope_clause(
    policy: GraphAccessPolicy,
    alarm_id_column: Any,
    *entity_columns: Any,
) -> ColumnElement[bool]:
    alarm_table = Alarm.__table__.alias("scope_alarm")
    return exists(
        select(1)
        .select_from(alarm_table)
        .where(
            alarm_table.c.id == alarm_id_column,
            turbine_scope_clause(
                policy,
                alarm_table.c.turbine_id,
                entity_columns=(alarm_table.c.id, *entity_columns),
                data_scopes="alarm",
            ),
        )
    )


def _decision_id_scope_clause(
    policy: GraphAccessPolicy, decision_id_column: Any
) -> ColumnElement[bool]:
    decision_table = Decision.__table__.alias("scope_decision")
    return exists(
        select(1)
        .select_from(decision_table)
        .where(
            decision_table.c.id == decision_id_column,
            mission_scope_clause(
                policy,
                decision_table.c.mission_id,
                entity_columns=(decision_table.c.id,),
                data_scopes="decision",
            ),
        )
    )


def _model_prediction_id_scope_clause(
    policy: GraphAccessPolicy, prediction_id_column: Any
) -> ColumnElement[bool]:
    prediction_table = ModelPrediction.__table__.alias("scope_model_prediction")
    return exists(
        select(1)
        .select_from(prediction_table)
        .where(
            prediction_table.c.id == prediction_id_column,
            turbine_scope_clause(
                policy,
                prediction_table.c.turbine_id,
                entity_columns=(prediction_table.c.id,),
                data_scopes="model",
            ),
        )
    )


def _knowledge_document_id_scope_clause(
    policy: GraphAccessPolicy, document_id_column: Any
) -> ColumnElement[bool]:
    document_table = KnowledgeDocument.__table__.alias("scope_knowledge_document")
    return exists(
        select(1)
        .select_from(document_table)
        .where(
            document_table.c.id == document_id_column,
            nullable_asset_scope_clause(
                policy,
                tenant_column=document_table.c.tenant_id,
                wind_farm_column=document_table.c.wind_farm_id,
                turbine_column=document_table.c.turbine_id,
                entity_columns=(document_table.c.id,),
                data_scopes="knowledge",
            ),
        )
    )


def _loader_criteria(policy: GraphAccessPolicy) -> tuple[Any, ...]:
    # Endpoint dependencies enforce data-domain grants. Row criteria then
    # enforce ownership consistently across all related tables that a granted
    # endpoint must traverse (for example knowledge -> tenant topology).
    policy = replace(policy, data_scopes=frozenset())
    global_models: tuple[tuple[Any, Any, str | Sequence[str]], ...] = (
        (CatalogVersion, CatalogVersion.id, "agent"),
        (AgentDefinition, AgentDefinition.id, "agent"),
        (SkillDefinition, SkillDefinition.id, "agent"),
        (ToolDefinition, ToolDefinition.id, "agent"),
        (AgentSkillLink, AgentSkillLink.agent_definition_id, "agent"),
        (AgentToolLink, AgentToolLink.agent_definition_id, "agent"),
        (AgentToolInvocation, AgentToolInvocation.id, "agent"),
        (PlatformConfigurationRevision, PlatformConfigurationRevision.id, "platform"),
        (
            PlatformConfigurationSecurityAudit,
            PlatformConfigurationSecurityAudit.id,
            "platform",
        ),
        (DataContractDefinition, DataContractDefinition.id, "platform"),
        (IngestSource, IngestSource.id, "platform"),
        (RegisteredModel, RegisteredModel.id, "model"),
        (ModelDeployment, ModelDeployment.id, "model"),
        (GeneratedReport, GeneratedReport.id, "report"),
        (ReadAccessAudit, ReadAccessAudit.id, "platform"),
    )
    clauses: list[tuple[Any, ColumnElement[bool]]] = [
        (
            Tenant,
            tenant_scope_clause(
                policy,
                Tenant.id,
                entity_columns=(Tenant.id,),
            ),
        ),
        (
            WindFarm,
            wind_farm_scope_clause(
                policy,
                WindFarm.id,
                entity_columns=(WindFarm.id, WindFarm.tenant_id),
            ),
        ),
        (
            Turbine,
            turbine_scope_clause(
                policy,
                Turbine.id,
                entity_columns=(Turbine.id, Turbine.wind_farm_id),
            ),
        ),
        (
            ScadaSample,
            turbine_scope_clause(
                policy,
                ScadaSample.turbine_id,
                entity_columns=(ScadaSample.id,),
                data_scopes=("telemetry", "benchmark"),
            ),
        ),
        (
            Alarm,
            turbine_scope_clause(
                policy,
                Alarm.turbine_id,
                entity_columns=(Alarm.id,),
                data_scopes="alarm",
            ),
        ),
        (
            Mission,
            turbine_scope_clause(
                policy,
                Mission.turbine_id,
                entity_columns=(Mission.id, Mission.alarm_id),
                data_scopes="mission",
            ),
        ),
        (
            AgentExecution,
            mission_scope_clause(
                policy,
                AgentExecution.mission_id,
                entity_columns=(AgentExecution.id,),
                data_scopes=("mission", "agent"),
            ),
        ),
        (
            MissionComment,
            mission_scope_clause(
                policy,
                MissionComment.mission_id,
                entity_columns=(MissionComment.id,),
            ),
        ),
        (
            Approval,
            mission_scope_clause(
                policy,
                Approval.mission_id,
                entity_columns=(Approval.id,),
            ),
        ),
        (
            Evidence,
            mission_scope_clause(
                policy,
                Evidence.mission_id,
                entity_columns=(Evidence.id,),
            ),
        ),
        (
            Decision,
            mission_scope_clause(
                policy,
                Decision.mission_id,
                entity_columns=(Decision.id,),
                data_scopes="decision",
            ),
        ),
        (
            WorkOrder,
            turbine_scope_clause(
                policy,
                WorkOrder.turbine_id,
                entity_columns=(WorkOrder.id, WorkOrder.mission_id),
                data_scopes="work_order",
            ),
        ),
        (
            ExternalWorkOrderLink,
            work_order_scope_clause(
                policy,
                ExternalWorkOrderLink.work_order_id,
                data_scopes="work_order",
            ),
        ),
        (
            WorkOrderTask,
            work_order_scope_clause(
                policy,
                WorkOrderTask.work_order_id,
                entity_columns=(WorkOrderTask.id,),
                data_scopes="work_order",
            ),
        ),
        (
            AssetHealthEvent,
            turbine_scope_clause(
                policy,
                AssetHealthEvent.turbine_id,
                entity_columns=(AssetHealthEvent.id, AssetHealthEvent.mission_id),
                data_scopes="asset",
            ),
        ),
        (
            AssetTwinProfile,
            turbine_scope_clause(
                policy,
                AssetTwinProfile.turbine_id,
                entity_columns=(AssetTwinProfile.turbine_id,),
                data_scopes="asset",
            ),
        ),
        (
            KnowledgeDocument,
            nullable_asset_scope_clause(
                policy,
                tenant_column=KnowledgeDocument.tenant_id,
                wind_farm_column=KnowledgeDocument.wind_farm_id,
                turbine_column=KnowledgeDocument.turbine_id,
                entity_columns=(KnowledgeDocument.id,),
                data_scopes="knowledge",
            ),
        ),
        (
            ModelPrediction,
            turbine_scope_clause(
                policy,
                ModelPrediction.turbine_id,
                entity_columns=(ModelPrediction.id,),
                data_scopes="model",
            ),
        ),
        (
            KnowledgeCase,
            turbine_scope_clause(
                policy,
                KnowledgeCase.turbine_id,
                entity_columns=(
                    KnowledgeCase.id,
                    KnowledgeCase.mission_id,
                    KnowledgeCase.work_order_id,
                ),
                data_scopes="knowledge",
            ),
        ),
        (
            Resource,
            resource_scope_clause(policy, Resource.id),
        ),
        (
            ResourceReservation,
            mission_scope_clause(
                policy,
                ResourceReservation.mission_id,
                entity_columns=(ResourceReservation.id, ResourceReservation.resource_id),
                data_scopes="resource",
            ),
        ),
        (
            WeatherWindow,
            wind_farm_scope_clause(
                policy,
                WeatherWindow.wind_farm_id,
                entity_columns=(WeatherWindow.id,),
                data_scopes="asset",
            ),
        ),
        (DomainEvent, domain_event_scope_clause(policy)),
    ]
    clauses.extend(
        (
            model,
            global_scope_clause(
                policy,
                entity_columns=(entity_column,),
                data_scopes=data_scope,
            ),
        )
        for model, entity_column, data_scope in global_models
    )
    return tuple(
        with_loader_criteria(
            model,
            clause,
            include_aliases=True,
            propagate_to_loaders=True,
        )
        for model, clause in clauses
    )


@event.listens_for(Session, "do_orm_execute")
def _apply_request_access_policy(execute_state: ORMExecuteState) -> None:
    if (
        not execute_state.is_select
        or execute_state.is_column_load
        or execute_state.is_relationship_load
        or execute_state.execution_options.get("skip_windops_access_control", False)
    ):
        return
    policy = execute_state.session.info.get(ACCESS_POLICY_SESSION_KEY)
    if not isinstance(policy, GraphAccessPolicy):
        return
    execute_state.statement = execute_state.statement.options(*_loader_criteria(policy))
