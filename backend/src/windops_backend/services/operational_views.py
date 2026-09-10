from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

import windops_backend.services.operational_assets as _assets
import windops_backend.services.operational_contracts as _contracts
import windops_backend.services.operational_diagnosis as _diagnosis
import windops_backend.services.operational_maintenance as _maintenance
import windops_backend.services.operational_related as _related

__all__ = [
    "DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT",
    "DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT",
    "DIAGNOSIS_RISK_PRIORITY",
    "MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT",
    "MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT",
    "DiagnosisQueryPlan",
    "MaintenanceQueryPlan",
    "OperationalPage",
    "build_diagnosis_priority_bucket_query",
    "build_diagnosis_query",
    "build_maintenance_query",
    "build_maintenance_weather_query",
    "data_catalog_payload",
    "diagnosis_rows",
    "digital_twin_snapshot",
    "live_report_rows",
    "maintenance_plan_rows",
]

DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT = _contracts.DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT
DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT = _contracts.DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT
MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT = (
    _contracts.MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT
)
MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT = _contracts.MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT
DIAGNOSIS_RISK_PRIORITY = _contracts.DIAGNOSIS_RISK_PRIORITY

_risk = _contracts._risk
_diagnosis_status = _contracts._diagnosis_status
_public_output_text = _contracts._public_output_text
_safe_number = _contracts._safe_number
OperationalPage = _contracts.OperationalPage
DiagnosisQueryPlan = _contracts.DiagnosisQueryPlan
MaintenanceQueryPlan = _contracts.MaintenanceQueryPlan
_diagnosis_related_data_boundaries = _contracts._diagnosis_related_data_boundaries
_maintenance_related_data_boundaries = _contracts._maintenance_related_data_boundaries

_bounded_evidence_by_mission = _related._bounded_evidence_by_mission
_bounded_executions_by_mission = _related._bounded_executions_by_mission
_task_progress_by_work_order = _related._task_progress_by_work_order
_bounded_resources_by_mission = _related._bounded_resources_by_mission

_diagnosis_risk_expression = _diagnosis._diagnosis_risk_expression
_diagnosis_status_expression = _diagnosis._diagnosis_status_expression
_diagnosis_risk_weight_expression = _diagnosis._diagnosis_risk_weight_expression
_diagnosis_priority_bucket_predicates = _diagnosis._diagnosis_priority_bucket_predicates
build_diagnosis_query = _diagnosis.build_diagnosis_query
build_diagnosis_priority_bucket_query = _diagnosis.build_diagnosis_priority_bucket_query
_diagnosis_priority_page_ids = _diagnosis._diagnosis_priority_page_ids


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
) -> OperationalPage:
    return await _diagnosis.diagnosis_rows(
        session,
        query=query,
        tenant_id=tenant_id,
        wind_farm_id=wind_farm_id,
        turbine_id=turbine_id,
        status_filter=status_filter,
        risk=risk,
        sort_mode=sort_mode,
        offset=offset,
        limit=limit,
        _query_builder=build_diagnosis_query,
    )


_resource_ref = _maintenance._resource_ref
_maintenance_risk_expression = _maintenance._maintenance_risk_expression
_resource_type_exists = _maintenance._resource_type_exists
_maintenance_planned_end_expression = _maintenance._maintenance_planned_end_expression
build_maintenance_weather_query = _maintenance.build_maintenance_weather_query
_bounded_weather_by_work_order = _maintenance._bounded_weather_by_work_order
build_maintenance_query = _maintenance.build_maintenance_query


async def maintenance_plan_rows(
    session: AsyncSession,
    *,
    query: str = "",
    tenant_id: str | None = None,
    wind_farm_id: str | None = None,
    turbine_id: str | None = None,
    status_filter: str | None = None,
    risk: str | None = None,
    team: str | None = None,
    window: str | None = None,
    sort_mode: str = "start-asc",
    offset: int = 0,
    limit: int = 50,
) -> OperationalPage:
    return await _maintenance.maintenance_plan_rows(
        session,
        query=query,
        tenant_id=tenant_id,
        wind_farm_id=wind_farm_id,
        turbine_id=turbine_id,
        status_filter=status_filter,
        risk=risk,
        team=team,
        window=window,
        sort_mode=sort_mode,
        offset=offset,
        limit=limit,
        _query_builder=build_maintenance_query,
    )


digital_twin_snapshot = _assets.digital_twin_snapshot
live_report_rows = _assets.live_report_rows
data_catalog_payload = _assets.data_catalog_payload
