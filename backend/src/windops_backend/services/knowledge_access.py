from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from windops_backend.errors import KnowledgeScopeError, NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import KnowledgeDocument, Tenant, Turbine, WindFarm

KNOWLEDGE_DATA_SCOPE = "knowledge"
_KNOWLEDGE_SCOPE_ALIASES = frozenset(
    {"knowledge", "knowledges", "knowledge_document", "knowledge_documents"}
)


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentScope:
    tenant_id: str | None = None
    wind_farm_id: str | None = None
    turbine_id: str | None = None
    data_scope: str = KNOWLEDGE_DATA_SCOPE


def _allowed_values(values: frozenset[str], column: Any) -> ColumnElement[bool] | None:
    if not values:
        return None
    allowed = true() if "*" in values else column.in_(tuple(values))
    return and_(column.is_not(None), allowed)


def knowledge_scope_clause(
    policy: GraphAccessPolicy,
    *,
    tenant_column: Any,
    wind_farm_column: Any,
    turbine_column: Any,
    entity_column: Any | None = None,
    data_scope_column: Any | None = None,
) -> ColumnElement[bool]:
    """Build a SQL visibility predicate for trusted knowledge ownership fields."""

    if policy.unrestricted:
        return true()
    if not policy.configured:
        return false()

    data_scope: ColumnElement[bool] = true()
    if policy.data_scopes:
        if "*" not in policy.data_scopes:
            allowed_scopes = set(policy.data_scopes).intersection(_KNOWLEDGE_SCOPE_ALIASES)
            if not allowed_scopes:
                return false()
            if data_scope_column is not None:
                data_scope = data_scope_column == KNOWLEDGE_DATA_SCOPE

    grants: list[ColumnElement[bool]] = []
    if entity_column is not None:
        entity_grant = _allowed_values(policy.entity_ids, entity_column)
        if entity_grant is not None:
            grants.append(entity_grant)
    for values, column in (
        (policy.tenant_ids, tenant_column),
        (policy.wind_farm_ids, wind_farm_column),
        (policy.turbine_ids, turbine_column),
    ):
        grant = _allowed_values(values, column)
        if grant is not None:
            grants.append(and_(column.is_not(None), grant))

    if not grants and not policy.allow_global:
        return false()
    scoped_visibility: ColumnElement[bool] = and_(*grants) if grants else false()
    if policy.allow_global:
        scoped_visibility = or_(
            scoped_visibility,
            and_(
                tenant_column.is_(None),
                wind_farm_column.is_(None),
                turbine_column.is_(None),
            ),
        )
    return and_(data_scope, scoped_visibility)


def principal_can_access_knowledge_scope(
    policy: GraphAccessPolicy,
    *,
    document_id: str | None,
    tenant_id: str | None,
    wind_farm_id: str | None,
    turbine_id: str | None,
    data_scope: str = KNOWLEDGE_DATA_SCOPE,
) -> bool:
    if policy.unrestricted:
        return True
    if not policy.configured:
        return False
    if policy.data_scopes and "*" not in policy.data_scopes:
        normalized_scope = data_scope.strip().casefold()
        if normalized_scope not in _KNOWLEDGE_SCOPE_ALIASES:
            return False
        if not _KNOWLEDGE_SCOPE_ALIASES.intersection(policy.data_scopes):
            return False

    if tenant_id is None and wind_farm_id is None and turbine_id is None and policy.allow_global:
        return True

    def matches(value: str | None, allowed: frozenset[str]) -> bool:
        return value is not None and ("*" in allowed or value.casefold() in allowed)

    if policy.entity_ids and not matches(document_id, policy.entity_ids):
        return False
    if policy.tenant_ids and not matches(tenant_id, policy.tenant_ids):
        return False
    if policy.wind_farm_ids and not matches(wind_farm_id, policy.wind_farm_ids):
        return False
    if policy.turbine_ids and not matches(turbine_id, policy.turbine_ids):
        return False

    has_grant = bool(
        policy.entity_ids or policy.tenant_ids or policy.wind_farm_ids or policy.turbine_ids
    )
    return has_grant


async def resolve_knowledge_document_scope(
    session: AsyncSession,
    *,
    document_id: str,
    policy: GraphAccessPolicy,
    tenant_id: str | None,
    wind_farm_id: str | None,
    turbine_id: str | None,
    data_scope: str = KNOWLEDGE_DATA_SCOPE,
) -> KnowledgeDocumentScope:
    """Resolve and authorize document ownership from authoritative asset rows."""

    resolved_tenant_id = tenant_id
    resolved_wind_farm_id = wind_farm_id
    resolved_turbine_id = turbine_id

    if resolved_turbine_id:
        turbine_row = (
            await session.execute(
                select(Turbine.id, Turbine.wind_farm_id, WindFarm.tenant_id)
                .join(WindFarm, WindFarm.id == Turbine.wind_farm_id)
                .where(Turbine.id == resolved_turbine_id)
            )
        ).one_or_none()
        if turbine_row is None:
            raise NotFoundError(f"turbine {resolved_turbine_id} was not found")
        if resolved_wind_farm_id and resolved_wind_farm_id != turbine_row.wind_farm_id:
            raise KnowledgeScopeError(
                "the document turbine does not belong to the requested wind farm"
            )
        if resolved_tenant_id and resolved_tenant_id != turbine_row.tenant_id:
            raise KnowledgeScopeError(
                "the document turbine does not belong to the requested tenant"
            )
        resolved_wind_farm_id = turbine_row.wind_farm_id
        resolved_tenant_id = turbine_row.tenant_id

    if resolved_wind_farm_id:
        farm = await session.get(WindFarm, resolved_wind_farm_id)
        if farm is None:
            raise NotFoundError(f"wind farm {resolved_wind_farm_id} was not found")
        if resolved_tenant_id and resolved_tenant_id != farm.tenant_id:
            raise KnowledgeScopeError(
                "the document wind farm does not belong to the requested tenant"
            )
        resolved_tenant_id = farm.tenant_id

    if resolved_tenant_id and await session.get(Tenant, resolved_tenant_id) is None:
        raise NotFoundError(f"tenant {resolved_tenant_id} was not found")

    scope = KnowledgeDocumentScope(
        tenant_id=resolved_tenant_id,
        wind_farm_id=resolved_wind_farm_id,
        turbine_id=resolved_turbine_id,
        data_scope=data_scope,
    )
    if not principal_can_access_knowledge_scope(
        policy,
        document_id=document_id,
        tenant_id=scope.tenant_id,
        wind_farm_id=scope.wind_farm_id,
        turbine_id=scope.turbine_id,
        data_scope=scope.data_scope,
    ):
        raise KnowledgeScopeError("the requested knowledge document scope is not authorized")
    return scope


def knowledge_case_scope_clause(policy: GraphAccessPolicy) -> ColumnElement[bool]:
    """Return the same policy for cases, whose asset ownership is relational."""

    return knowledge_scope_clause(
        policy,
        tenant_column=WindFarm.tenant_id,
        wind_farm_column=WindFarm.id,
        turbine_column=Turbine.id,
        entity_column=None,
    )


def knowledge_document_query(policy: GraphAccessPolicy) -> Any:
    return select(KnowledgeDocument).where(
        knowledge_scope_clause(
            policy,
            tenant_column=KnowledgeDocument.tenant_id,
            wind_farm_column=KnowledgeDocument.wind_farm_id,
            turbine_column=KnowledgeDocument.turbine_id,
            entity_column=KnowledgeDocument.id,
            data_scope_column=KnowledgeDocument.data_scope,
        )
    )
