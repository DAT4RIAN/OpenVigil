from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

type GraphScalar = str | int | float | bool | None
type GraphProperty = GraphScalar | list[GraphScalar]
type GraphProperties = dict[str, GraphProperty]


class NodeType(StrEnum):
    WIND_FARM = "WindFarm"
    TURBINE = "Turbine"
    SUBSYSTEM = "Subsystem"
    SENSOR = "Sensor"
    ALARM = "Alarm"
    ANOMALY = "Anomaly"
    FAILURE_MODE = "FailureMode"
    EVIDENCE = "Evidence"
    MISSION = "Mission"
    DECISION = "Decision"
    WORK_ORDER = "WorkOrder"
    PROCEDURE = "Procedure"
    PART = "Part"
    RESOURCE = "Resource"
    KNOWLEDGE_DOCUMENT = "KnowledgeDocument"
    KNOWLEDGE_PASSAGE = "KnowledgePassage"
    KNOWLEDGE_CASE = "KnowledgeCase"


class RelationshipType(StrEnum):
    HAS_TURBINE = "HAS_TURBINE"
    HAS_SUBSYSTEM = "HAS_SUBSYSTEM"
    MONITORED_BY = "MONITORED_BY"
    TRIGGERED = "TRIGGERED"
    INDICATES = "INDICATES"
    AFFECTS = "AFFECTS"
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    RESOLVED_BY = "RESOLVED_BY"
    REQUIRES_PART = "REQUIRES_PART"
    EXECUTED_BY = "EXECUTED_BY"
    SIMILAR_TO = "SIMILAR_TO"
    HAS_PASSAGE = "HAS_PASSAGE"
    HAS_DECISION = "HAS_DECISION"
    HAS_WORK_ORDER = "HAS_WORK_ORDER"
    HAS_PROCEDURE = "HAS_PROCEDURE"
    RECORDED_FOR = "RECORDED_FOR"
    ASSIGNED_TO = "ASSIGNED_TO"


def graph_uid(node_type: NodeType, entity_id: str) -> str:
    return f"{node_type.value}:{entity_id}"


@dataclass(frozen=True, slots=True)
class GraphNode:
    uid: str
    node_type: NodeType
    entity_id: str
    properties: GraphProperties = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "uid": self.uid,
            "type": self.node_type.value,
            "entityId": self.entity_id,
            "properties": dict(self.properties),
        }


@dataclass(frozen=True, slots=True)
class GraphRelationship:
    uid: str
    relationship_type: RelationshipType
    source_uid: str
    target_uid: str
    properties: GraphProperties = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "uid": self.uid,
            "type": self.relationship_type.value,
            "sourceUid": self.source_uid,
            "targetUid": self.target_uid,
            "properties": dict(self.properties),
        }


@dataclass(frozen=True, slots=True)
class GraphPath:
    node_uids: tuple[str, ...]
    relationship_uids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "nodeUids": list(self.node_uids),
            "relationshipUids": list(self.relationship_uids),
        }


@dataclass(frozen=True, slots=True)
class GraphSubgraph:
    root_uid: str
    nodes: tuple[GraphNode, ...]
    relationships: tuple[GraphRelationship, ...]
    paths: tuple[GraphPath, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "rootUid": self.root_uid,
            "nodes": [node.as_dict() for node in self.nodes],
            "relationships": [relationship.as_dict() for relationship in self.relationships],
            "paths": [path.as_dict() for path in self.paths],
        }


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    projection_id: str
    projection_sequence: str
    source_revision: str
    generated_at: datetime
    nodes: tuple[GraphNode, ...]
    relationships: tuple[GraphRelationship, ...]

    def __post_init__(self) -> None:
        known_nodes: set[str] = set()
        for node in self.nodes:
            if node.uid in known_nodes:
                raise ValueError("knowledge graph snapshot contains duplicate node identities")
            known_nodes.add(node.uid)

        known_relationships: set[str] = set()
        first_dangling: str | None = None
        for relationship in self.relationships:
            if relationship.uid in known_relationships:
                raise ValueError(
                    "knowledge graph snapshot contains duplicate relationship identities"
                )
            known_relationships.add(relationship.uid)
            if first_dangling is None and (
                relationship.source_uid not in known_nodes
                or relationship.target_uid not in known_nodes
            ):
                first_dangling = relationship.uid
        if first_dangling is not None:
            raise ValueError(
                f"knowledge graph snapshot contains dangling relationship: {first_dangling}"
            )


_NODE_DATA_SCOPES: dict[NodeType, str] = {
    NodeType.WIND_FARM: "asset",
    NodeType.TURBINE: "asset",
    NodeType.SUBSYSTEM: "asset",
    NodeType.SENSOR: "telemetry",
    NodeType.ALARM: "alarm",
    NodeType.ANOMALY: "diagnosis",
    NodeType.FAILURE_MODE: "diagnosis",
    NodeType.EVIDENCE: "evidence",
    NodeType.MISSION: "mission",
    NodeType.DECISION: "decision",
    NodeType.WORK_ORDER: "work_order",
    NodeType.PROCEDURE: "work_order",
    NodeType.PART: "resource",
    NodeType.RESOURCE: "resource",
    NodeType.KNOWLEDGE_DOCUMENT: "knowledge",
    NodeType.KNOWLEDGE_PASSAGE: "knowledge",
    NodeType.KNOWLEDGE_CASE: "knowledge",
}


def graph_data_scope(node_type: NodeType) -> str:
    return _NODE_DATA_SCOPES[node_type]


@dataclass(frozen=True, slots=True)
class GraphAccessPolicy:
    """Backend-enforced visibility policy for a graph read.

    A policy is intentionally narrower than an RBAC role.  Empty asset sets
    do not mean "all"; the caller must be explicitly marked unrestricted (only
    the test system gets that marker) or receive a configured tenant/farm/
    turbine/entity/data grant.  Global nodes such as generic failure modes or
    manuals are visible only when ``allow_global`` is granted.
    """

    tenant_ids: frozenset[str] = frozenset()
    wind_farm_ids: frozenset[str] = frozenset()
    turbine_ids: frozenset[str] = frozenset()
    entity_ids: frozenset[str] = frozenset()
    data_scopes: frozenset[str] = frozenset()
    allow_global: bool = False
    unrestricted: bool = False

    @classmethod
    def from_values(
        cls,
        *,
        tenant_ids: tuple[str, ...] | list[str] = (),
        wind_farm_ids: tuple[str, ...] | list[str] = (),
        turbine_ids: tuple[str, ...] | list[str] = (),
        entity_ids: tuple[str, ...] | list[str] = (),
        data_scopes: tuple[str, ...] | list[str] = (),
        allow_global: bool = False,
        unrestricted: bool = False,
    ) -> GraphAccessPolicy:
        def normalize(values: tuple[str, ...] | list[str]) -> frozenset[str]:
            return frozenset(value.strip().casefold() for value in values if value.strip())

        return cls(
            tenant_ids=normalize(tenant_ids),
            wind_farm_ids=normalize(wind_farm_ids),
            turbine_ids=normalize(turbine_ids),
            entity_ids=normalize(entity_ids),
            data_scopes=normalize(data_scopes),
            allow_global=allow_global,
            unrestricted=unrestricted,
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.unrestricted
            or self.tenant_ids
            or self.wind_farm_ids
            or self.turbine_ids
            or self.entity_ids
            or self.data_scopes
            or self.allow_global
        )

    @staticmethod
    def _matches(value: object, allowed: frozenset[str]) -> bool:
        if not allowed:
            return True
        normalized = str(value).strip().casefold()
        return "*" in allowed or normalized in allowed

    @staticmethod
    def _candidate_values(node: GraphNode) -> set[str]:
        candidates = {node.entity_id.casefold()}
        for key in (
            "tenantId",
            "windFarmId",
            "turbineId",
            "alarmId",
            "missionId",
            "workOrderId",
            "documentId",
            "taskId",
            "sourceKey",
        ):
            value = node.properties.get(key)
            if value is not None:
                candidates.add(str(value).strip().casefold())
        return candidates

    def allows(self, node: GraphNode) -> bool:
        if self.unrestricted:
            return True

        tenant_id = node.properties.get("tenantId")
        wind_farm_id = node.properties.get("windFarmId")
        turbine_id = node.properties.get("turbineId")
        if node.node_type is NodeType.WIND_FARM and wind_farm_id is None:
            wind_farm_id = node.entity_id
        if node.node_type is NodeType.TURBINE and turbine_id is None:
            turbine_id = node.entity_id
        has_asset_scope = any(value is not None for value in (tenant_id, wind_farm_id, turbine_id))
        has_asset_grant = bool(
            self.tenant_ids or self.wind_farm_ids or self.turbine_ids or self.entity_ids
        )

        if has_asset_scope and not has_asset_grant:
            return False

        if (
            self.tenant_ids
            and tenant_id is not None
            and not self._matches(tenant_id, self.tenant_ids)
        ):
            return False
        if (
            self.wind_farm_ids
            and wind_farm_id is not None
            and not self._matches(wind_farm_id, self.wind_farm_ids)
        ):
            return False
        if (
            self.turbine_ids
            and turbine_id is not None
            and not self._matches(turbine_id, self.turbine_ids)
        ):
            return False
        if self.tenant_ids and tenant_id is None and has_asset_scope:
            return False
        if self.wind_farm_ids and wind_farm_id is None and has_asset_scope:
            return False
        if self.turbine_ids and turbine_id is None and has_asset_scope:
            return False
        if self.entity_ids and not self._candidate_values(node).intersection(self.entity_ids):
            return False

        if self.data_scopes:
            node_scope = graph_data_scope(node.node_type).casefold()
            aliases = {
                node_scope,
                f"{node_scope}s",
                "workorders" if node_scope == "work_order" else node_scope,
            }
            if not aliases.intersection(self.data_scopes):
                return False

        if not has_asset_scope and not self.allow_global:
            return False
        return True

    def filter_snapshot(self, snapshot: GraphSnapshot) -> GraphSnapshot:
        if self.unrestricted:
            return snapshot
        visible_nodes = tuple(node for node in snapshot.nodes if self.allows(node))
        visible_uids = {node.uid for node in visible_nodes}
        visible_relationships = tuple(
            relationship
            for relationship in snapshot.relationships
            if relationship.source_uid in visible_uids and relationship.target_uid in visible_uids
        )
        return GraphSnapshot(
            projection_id=snapshot.projection_id,
            projection_sequence=snapshot.projection_sequence,
            source_revision=snapshot.source_revision,
            generated_at=snapshot.generated_at,
            nodes=visible_nodes,
            relationships=visible_relationships,
        )


def graph_summary_for_snapshot(snapshot: GraphSnapshot, *, backend: str) -> GraphSummary:
    connected = {
        uid
        for relationship in snapshot.relationships
        for uid in (relationship.source_uid, relationship.target_uid)
    }
    node_type_counts: dict[str, int] = {}
    for node in snapshot.nodes:
        node_type_counts[node.node_type.value] = node_type_counts.get(node.node_type.value, 0) + 1
    relationship_type_counts: dict[str, int] = {}
    for relationship in snapshot.relationships:
        name = relationship.relationship_type.value
        relationship_type_counts[name] = relationship_type_counts.get(name, 0) + 1
    return GraphSummary(
        backend=backend,
        projection_id=snapshot.projection_id,
        projection_sequence=snapshot.projection_sequence,
        source_revision=snapshot.source_revision,
        generated_at=snapshot.generated_at.isoformat(),
        node_count=len(snapshot.nodes),
        relationship_count=len(snapshot.relationships),
        orphan_node_count=sum(node.uid not in connected for node in snapshot.nodes),
        node_type_counts=node_type_counts,
        relationship_type_counts=relationship_type_counts,
    )


@dataclass(frozen=True, slots=True)
class GraphSummary:
    backend: str
    projection_id: str
    projection_sequence: str | None
    source_revision: str | None
    generated_at: str | None
    node_count: int
    relationship_count: int
    orphan_node_count: int
    node_type_counts: dict[str, int]
    relationship_type_counts: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "projectionId": self.projection_id,
            "projectionSequence": self.projection_sequence,
            "sourceRevision": self.source_revision,
            "generatedAt": self.generated_at,
            "nodeCount": self.node_count,
            "relationshipCount": self.relationship_count,
            "orphanNodeCount": self.orphan_node_count,
            "nodeTypeCounts": dict(self.node_type_counts),
            "relationshipTypeCounts": dict(self.relationship_type_counts),
        }


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    consistent: bool
    expected_revision: str
    actual_revision: str | None
    missing_node_uids: tuple[str, ...]
    unexpected_node_uids: tuple[str, ...]
    missing_relationship_uids: tuple[str, ...]
    unexpected_relationship_uids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "consistent": self.consistent,
            "expectedRevision": self.expected_revision,
            "actualRevision": self.actual_revision,
            "missingNodeUids": list(self.missing_node_uids),
            "unexpectedNodeUids": list(self.unexpected_node_uids),
            "missingRelationshipUids": list(self.missing_relationship_uids),
            "unexpectedRelationshipUids": list(self.unexpected_relationship_uids),
        }
