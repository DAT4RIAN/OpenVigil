from __future__ import annotations

from windops_backend.access_control import data_scope_allowed
from windops_backend.api.deps import Principal

VIEW_CAPABILITIES: tuple[tuple[str, str], ...] = (
    ("view.dashboard", "dashboard"),
    ("view.assets", "asset"),
    ("view.telemetry", "telemetry"),
    ("view.alarms", "alarm"),
    ("view.missions", "mission"),
    ("view.decisions", "decision"),
    ("view.work_orders", "work_order"),
    ("view.resources", "resource"),
    ("view.knowledge", "knowledge"),
    ("view.models", "model"),
    ("view.reports", "report"),
    ("view.agents", "agent"),
    ("view.platform", "platform"),
)

SCOPED_ACTION_CAPABILITIES: tuple[tuple[str, frozenset[str], str], ...] = (
    ("alarm.command", frozenset({"operations_manager", "operations_approver"}), "alarm"),
    ("mission.create", frozenset({"operations_manager"}), "mission"),
    (
        "mission.comment",
        frozenset({"operations_manager", "operations_approver", "field_technician"}),
        "mission",
    ),
    ("mission.approve", frozenset({"operations_approver"}), "mission"),
    ("mission.reject", frozenset({"operations_approver"}), "mission"),
    ("mission.request_revision", frozenset({"maintenance_reviewer"}), "mission"),
    ("mission.escalate", frozenset({"operations_manager"}), "mission"),
    ("work_order.schedule", frozenset({"operations_manager"}), "work_order"),
    ("work_order.task.complete", frozenset({"field_technician"}), "work_order"),
    ("resource.manage", frozenset({"operations_manager"}), "resource"),
)

GLOBAL_ACTION_CAPABILITIES: tuple[tuple[str, frozenset[str], str], ...] = (
    ("agent.manage", frozenset({"operations_manager"}), "agent"),
    ("model.manage", frozenset({"operations_manager"}), "model"),
    ("platform.manage", frozenset({"operations_manager"}), "platform"),
    ("report.generate", frozenset({"operations_manager"}), "report"),
)


def _has_global_scope(principal: Principal, data_scope: str) -> bool:
    policy = principal.graph_access_policy()
    restricted_entities = bool(policy.entity_ids and "*" not in policy.entity_ids)
    return principal.unrestricted or (
        policy.allow_global and not restricted_entities and data_scope_allowed(policy, data_scope)
    )


def capabilities_for_principal(principal: Principal) -> tuple[str, ...]:
    """Return a minimal server-owned UX capability set; route authorization remains final."""

    policy = principal.graph_access_policy()
    roles = set(principal.roles)
    capabilities = {
        capability
        for capability, data_scope in VIEW_CAPABILITIES
        if data_scope_allowed(policy, data_scope)
    }
    capabilities.update(
        capability
        for capability, allowed_roles, data_scope in SCOPED_ACTION_CAPABILITIES
        if roles.intersection(allowed_roles) and data_scope_allowed(policy, data_scope)
    )
    capabilities.update(
        capability
        for capability, allowed_roles, data_scope in GLOBAL_ACTION_CAPABILITIES
        if roles.intersection(allowed_roles) and _has_global_scope(principal, data_scope)
    )
    return tuple(sorted(capabilities))
