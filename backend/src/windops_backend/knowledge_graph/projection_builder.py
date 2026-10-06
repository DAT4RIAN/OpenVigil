"""Budgeted node/relationship construction and stable snapshot revision hashing."""

from __future__ import annotations

import hashlib
import heapq
from datetime import UTC, datetime

from windops_backend.knowledge_graph.domain import (
    GraphNode,
    GraphProperties,
    GraphRelationship,
    GraphSnapshot,
    NodeType,
    RelationshipType,
    graph_data_scope,
    graph_uid,
)
from windops_backend.knowledge_graph.projection_budget import (
    ProjectionLimitExceeded,
    ProjectionLimits,
    _conservative_memory_bytes,
    _ProjectionBudget,
)
from windops_backend.knowledge_graph.projection_values import KNOWLEDGE_GRAPH_PROJECTION_ID, _json

_SNAPSHOT_HANDOFF_BYTES_PER_ITEM = 160


class _ProjectionBuilder:
    def __init__(self, limits: ProjectionLimits, budget: _ProjectionBudget) -> None:
        self.limits = limits
        self.budget = budget
        self.nodes: dict[str, GraphNode] = {}
        self.relationships: dict[str, GraphRelationship] = {}
        self._largest_write_rows: list[int] = []
        self.budget.reserve_memory(
            _conservative_memory_bytes(self.nodes)
            + _conservative_memory_bytes(self.relationships)
            + _conservative_memory_bytes([0] * min(self.limits.batch_size, self.limits.max_nodes))
        )
        self.estimated_memory_bytes = 0

    def _remember_write_row_size(self, size: int) -> None:
        if len(self._largest_write_rows) < self.limits.batch_size:
            heapq.heappush(self._largest_write_rows, size)
        elif size > self._largest_write_rows[0]:
            heapq.heapreplace(self._largest_write_rows, size)

    def _reserve_memory(
        self,
        *,
        previous_graph_size: int,
        next_graph_size: int,
        previous_memory_size: int,
        next_memory_size: int,
    ) -> None:
        self.budget.reserve_graph(next_graph_size - previous_graph_size)
        self.budget.reserve_memory(next_memory_size - previous_memory_size)
        self.estimated_memory_bytes = self.budget.estimated_memory_bytes

    def node(
        self, node_type: NodeType, entity_id: str, **properties: str | int | float | bool | None
    ) -> str:
        uid = graph_uid(node_type, entity_id)
        properties.setdefault("dataScope", graph_data_scope(node_type))
        clean: GraphProperties = {
            key: value
            for key, value in properties.items()
            if value is None or isinstance(value, str | int | float | bool)
        }
        node = GraphNode(
            uid=uid,
            node_type=node_type,
            entity_id=entity_id,
            properties=clean,
        )
        previous = self.nodes.get(uid)
        previous_graph_size = (
            len(_json(previous.as_dict()).encode("utf-8")) + 128 if previous is not None else 0
        )
        next_graph_size = len(_json(node.as_dict()).encode("utf-8")) + 128
        previous_memory_size = (
            _conservative_memory_bytes((uid, previous), entry_overhead=64)
            if previous is not None
            else 0
        )
        next_memory_size = _conservative_memory_bytes((uid, node), entry_overhead=64)
        self._reserve_memory(
            previous_graph_size=previous_graph_size,
            next_graph_size=next_graph_size,
            previous_memory_size=previous_memory_size,
            next_memory_size=next_memory_size,
        )
        self.nodes[uid] = node
        self._remember_write_row_size(
            _conservative_memory_bytes(node.as_dict(), entry_overhead=384)
        )
        self.budget.check_actual_memory()
        if len(self.nodes) > self.limits.max_nodes:
            raise ProjectionLimitExceeded("knowledge graph projection node budget exceeded")
        return uid

    def relationship(
        self,
        relationship_type: RelationshipType,
        source_uid: str,
        target_uid: str,
        *,
        qualifier: str = "",
        **properties: str | int | float | bool | None,
    ) -> str:
        identity = f"{relationship_type.value}:{source_uid}->{target_uid}"
        if qualifier:
            identity = f"{identity}:{qualifier}"
        clean: GraphProperties = {
            key: value
            for key, value in properties.items()
            if value is None or isinstance(value, str | int | float | bool)
        }
        relationship = GraphRelationship(
            uid=identity,
            relationship_type=relationship_type,
            source_uid=source_uid,
            target_uid=target_uid,
            properties=clean,
        )
        previous = self.relationships.get(identity)
        previous_graph_size = (
            len(_json(previous.as_dict()).encode("utf-8")) + 128 if previous is not None else 0
        )
        next_graph_size = len(_json(relationship.as_dict()).encode("utf-8")) + 128
        previous_memory_size = (
            _conservative_memory_bytes((identity, previous), entry_overhead=64)
            if previous is not None
            else 0
        )
        next_memory_size = _conservative_memory_bytes((identity, relationship), entry_overhead=64)
        self._reserve_memory(
            previous_graph_size=previous_graph_size,
            next_graph_size=next_graph_size,
            previous_memory_size=previous_memory_size,
            next_memory_size=next_memory_size,
        )
        self.relationships[identity] = relationship
        self._remember_write_row_size(
            _conservative_memory_bytes(relationship.as_dict(), entry_overhead=512)
        )
        self.budget.check_actual_memory()
        if len(self.relationships) > self.limits.max_relationships:
            raise ProjectionLimitExceeded("knowledge graph projection relationship budget exceeded")
        return identity

    def snapshot(self, projection_sequence: str | None = None) -> GraphSnapshot:
        item_count = len(self.nodes) + len(self.relationships)
        handoff_headroom = item_count * _SNAPSHOT_HANDOFF_BYTES_PER_ITEM
        serialization_headroom = sum(self._largest_write_rows)
        self.budget.reserve_memory(handoff_headroom + serialization_headroom)
        try:
            nodes = tuple(self.nodes[uid] for uid in sorted(self.nodes))
            relationships = tuple(self.relationships[uid] for uid in sorted(self.relationships))
            self.budget.check_actual_memory()
            revision_hasher = hashlib.sha256()
            for node in nodes:
                revision_hasher.update(b"node\0")
                revision_hasher.update(_json(node.as_dict()).encode("utf-8"))
                revision_hasher.update(b"\n")
            for relationship in relationships:
                revision_hasher.update(b"relationship\0")
                revision_hasher.update(_json(relationship.as_dict()).encode("utf-8"))
                revision_hasher.update(b"\n")
            revision = revision_hasher.hexdigest()
            generated_at = datetime.now(UTC)
            snapshot = GraphSnapshot(
                projection_id=KNOWLEDGE_GRAPH_PROJECTION_ID,
                projection_sequence=projection_sequence or f"{generated_at.isoformat()}:direct",
                source_revision=revision,
                generated_at=generated_at,
                nodes=nodes,
                relationships=relationships,
            )
            self.budget.check_actual_memory()
            return snapshot
        finally:
            self.budget.reserve_memory(-(handoff_headroom + serialization_headroom))
