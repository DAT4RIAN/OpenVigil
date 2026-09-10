from __future__ import annotations

import json
from collections import Counter, deque
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from windops_backend.knowledge_graph.domain import (
    GraphAccessPolicy,
    GraphNode,
    GraphPath,
    GraphProperties,
    GraphRelationship,
    GraphSnapshot,
    GraphSubgraph,
    GraphSummary,
    NodeType,
    RelationshipType,
    graph_summary_for_snapshot,
)


class KnowledgeGraphStore(Protocol):
    backend_name: str

    async def verify_connectivity(self) -> None: ...

    async def replace_projection(self, snapshot: GraphSnapshot) -> None: ...

    async def summary(
        self, projection_id: str, policy: GraphAccessPolicy | None = None
    ) -> GraphSummary: ...

    async def resolve_uid(
        self,
        projection_id: str,
        entity_id: str,
        policy: GraphAccessPolicy | None = None,
    ) -> str | None: ...

    async def subgraph(
        self,
        projection_id: str,
        root_uid: str,
        *,
        depth: int,
        path_limit: int = 100,
        policy: GraphAccessPolicy | None = None,
    ) -> GraphSubgraph: ...

    async def identity_sets(
        self, projection_id: str, policy: GraphAccessPolicy | None = None
    ) -> tuple[set[str], set[str]]: ...

    async def unsupported_failure_mode_uids(
        self, projection_id: str, policy: GraphAccessPolicy | None = None
    ) -> set[str]: ...

    async def snapshot(self, projection_id: str) -> GraphSnapshot | None: ...

    async def close(self) -> None: ...


def _orphan_count(
    nodes: Mapping[str, GraphNode], relationships: Mapping[str, GraphRelationship]
) -> int:
    connected: set[str] = set()
    for relationship in relationships.values():
        connected.add(relationship.source_uid)
        connected.add(relationship.target_uid)
    return sum(uid not in connected for uid in nodes)


def _subgraph_from_snapshot(
    snapshot: GraphSnapshot | None,
    root_uid: str,
    *,
    depth: int,
    path_limit: int,
) -> GraphSubgraph:
    if snapshot is None:
        return GraphSubgraph(root_uid=root_uid, nodes=(), relationships=(), paths=())
    nodes = {node.uid: node for node in snapshot.nodes}
    if root_uid not in nodes:
        return GraphSubgraph(root_uid=root_uid, nodes=(), relationships=(), paths=())
    relationships = {relationship.uid: relationship for relationship in snapshot.relationships}
    adjacency: dict[str, list[tuple[str, str]]] = {uid: [] for uid in nodes}
    for relationship in relationships.values():
        adjacency[relationship.source_uid].append((relationship.target_uid, relationship.uid))
        adjacency[relationship.target_uid].append((relationship.source_uid, relationship.uid))

    selected_nodes = {root_uid}
    selected_relationships: set[str] = set()
    paths: list[GraphPath] = []
    queue: deque[tuple[str, tuple[str, ...], tuple[str, ...]]] = deque(
        [(root_uid, (root_uid,), ())]
    )
    while queue and len(paths) < path_limit:
        current, node_path, relationship_path = queue.popleft()
        if relationship_path:
            paths.append(GraphPath(node_uids=node_path, relationship_uids=relationship_path))
        if len(relationship_path) >= depth:
            continue
        for neighbor, relationship_uid in sorted(adjacency[current]):
            if neighbor in node_path:
                continue
            selected_nodes.add(neighbor)
            selected_relationships.add(relationship_uid)
            queue.append(
                (
                    neighbor,
                    (*node_path, neighbor),
                    (*relationship_path, relationship_uid),
                )
            )

    return GraphSubgraph(
        root_uid=root_uid,
        nodes=tuple(nodes[uid] for uid in sorted(selected_nodes)),
        relationships=tuple(relationships[uid] for uid in sorted(selected_relationships)),
        paths=tuple(paths),
    )


class InMemoryKnowledgeGraphStore:
    """Deterministic test double. Production must use Neo4j."""

    backend_name = "memory-test-double"

    def __init__(self) -> None:
        self._snapshots: dict[str, GraphSnapshot] = {}

    async def verify_connectivity(self) -> None:
        return None

    async def replace_projection(self, snapshot: GraphSnapshot) -> None:
        current = self._snapshots.get(snapshot.projection_id)
        if current is not None and current.projection_sequence > snapshot.projection_sequence:
            return
        self._snapshots[snapshot.projection_id] = snapshot

    async def snapshot(self, projection_id: str) -> GraphSnapshot | None:
        return self._snapshots.get(projection_id)

    async def summary(
        self, projection_id: str, policy: GraphAccessPolicy | None = None
    ) -> GraphSummary:
        snapshot = self._snapshots.get(projection_id)
        if snapshot is None:
            return GraphSummary(
                backend=self.backend_name,
                projection_id=projection_id,
                projection_sequence=None,
                source_revision=None,
                generated_at=None,
                node_count=0,
                relationship_count=0,
                orphan_node_count=0,
                node_type_counts={},
                relationship_type_counts={},
            )
        if policy is not None:
            snapshot = policy.filter_snapshot(snapshot)
            return graph_summary_for_snapshot(snapshot, backend=self.backend_name)
        nodes = {node.uid: node for node in snapshot.nodes}
        relationships = {relationship.uid: relationship for relationship in snapshot.relationships}
        return GraphSummary(
            backend=self.backend_name,
            projection_id=projection_id,
            projection_sequence=snapshot.projection_sequence,
            source_revision=snapshot.source_revision,
            generated_at=snapshot.generated_at.isoformat(),
            node_count=len(nodes),
            relationship_count=len(relationships),
            orphan_node_count=_orphan_count(nodes, relationships),
            node_type_counts=dict(Counter(node.node_type.value for node in nodes.values())),
            relationship_type_counts=dict(
                Counter(
                    relationship.relationship_type.value for relationship in relationships.values()
                )
            ),
        )

    async def resolve_uid(
        self,
        projection_id: str,
        entity_id: str,
        policy: GraphAccessPolicy | None = None,
    ) -> str | None:
        snapshot = self._snapshots.get(projection_id)
        if snapshot is None:
            return None
        if policy is not None:
            snapshot = policy.filter_snapshot(snapshot)
        normalized = entity_id.casefold()
        for node in snapshot.nodes:
            if node.uid.casefold() == normalized or node.entity_id.casefold() == normalized:
                return node.uid
        return None

    async def subgraph(
        self,
        projection_id: str,
        root_uid: str,
        *,
        depth: int,
        path_limit: int = 100,
        policy: GraphAccessPolicy | None = None,
    ) -> GraphSubgraph:
        if policy is not None:
            snapshot = self._snapshots.get(projection_id)
            return _subgraph_from_snapshot(
                policy.filter_snapshot(snapshot) if snapshot is not None else None,
                root_uid,
                depth=depth,
                path_limit=path_limit,
            )
        snapshot = self._snapshots.get(projection_id)
        if snapshot is None:
            return GraphSubgraph(root_uid=root_uid, nodes=(), relationships=(), paths=())
        nodes = {node.uid: node for node in snapshot.nodes}
        if root_uid not in nodes:
            return GraphSubgraph(root_uid=root_uid, nodes=(), relationships=(), paths=())
        relationships = {relationship.uid: relationship for relationship in snapshot.relationships}
        adjacency: dict[str, list[tuple[str, str]]] = {uid: [] for uid in nodes}
        for relationship in relationships.values():
            adjacency[relationship.source_uid].append((relationship.target_uid, relationship.uid))
            adjacency[relationship.target_uid].append((relationship.source_uid, relationship.uid))

        selected_nodes = {root_uid}
        selected_relationships: set[str] = set()
        paths: list[GraphPath] = []
        queue: deque[tuple[str, tuple[str, ...], tuple[str, ...]]] = deque(
            [(root_uid, (root_uid,), ())]
        )
        while queue and len(paths) < path_limit:
            current, node_path, relationship_path = queue.popleft()
            if relationship_path:
                paths.append(GraphPath(node_uids=node_path, relationship_uids=relationship_path))
            if len(relationship_path) >= depth:
                continue
            for neighbor, relationship_uid in sorted(adjacency[current]):
                if neighbor in node_path:
                    continue
                selected_nodes.add(neighbor)
                selected_relationships.add(relationship_uid)
                queue.append(
                    (
                        neighbor,
                        (*node_path, neighbor),
                        (*relationship_path, relationship_uid),
                    )
                )

        return GraphSubgraph(
            root_uid=root_uid,
            nodes=tuple(nodes[uid] for uid in sorted(selected_nodes)),
            relationships=tuple(relationships[uid] for uid in sorted(selected_relationships)),
            paths=tuple(paths),
        )

    async def identity_sets(
        self, projection_id: str, policy: GraphAccessPolicy | None = None
    ) -> tuple[set[str], set[str]]:
        snapshot = self._snapshots.get(projection_id)
        if snapshot is None:
            return set(), set()
        if policy is not None:
            snapshot = policy.filter_snapshot(snapshot)
        return (
            {node.uid for node in snapshot.nodes},
            {relationship.uid for relationship in snapshot.relationships},
        )

    async def unsupported_failure_mode_uids(
        self, projection_id: str, policy: GraphAccessPolicy | None = None
    ) -> set[str]:
        snapshot = self._snapshots.get(projection_id)
        if snapshot is None:
            return set()
        if policy is not None:
            snapshot = policy.filter_snapshot(snapshot)
        supported = {
            relationship.source_uid
            for relationship in snapshot.relationships
            if relationship.relationship_type is RelationshipType.SUPPORTED_BY
        }
        return {
            node.uid
            for node in snapshot.nodes
            if node.node_type is NodeType.FAILURE_MODE and node.uid not in supported
        }

    async def close(self) -> None:
        return None


def _neo4j_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        if all(item is None or isinstance(item, str | int | float | bool) for item in value):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _neo4j_properties(properties: GraphProperties) -> dict[str, object]:
    return {key: _neo4j_value(value) for key, value in properties.items()}


class Neo4jKnowledgeGraphStore:
    backend_name = "neo4j"

    def __init__(self, driver: Any, database: str, *, write_batch_size: int = 500) -> None:
        if write_batch_size <= 0:
            raise ValueError("write_batch_size must be positive")
        self._driver = driver
        self._database = database
        self._write_batch_size = write_batch_size

    async def verify_connectivity(self) -> None:
        await self._driver.verify_connectivity()

    @staticmethod
    def _label(node_type: NodeType) -> str:
        return node_type.value

    @staticmethod
    def _relationship_type(relationship_type: RelationshipType) -> str:
        return relationship_type.value

    async def replace_projection(self, snapshot: GraphSnapshot) -> None:
        async with self._driver.session(database=self._database) as session:
            await self._ensure_schema(session)
            await session.execute_write(
                self._replace_transaction,
                snapshot,
                self._write_batch_size,
            )

    @staticmethod
    async def _ensure_schema(session: Any) -> None:
        constraint = await session.run(
            "CREATE CONSTRAINT windops_knowledge_uid IF NOT EXISTS "
            "FOR (n:WindOpsKnowledge) REQUIRE n.uid IS UNIQUE"
        )
        await constraint.consume()
        projection_constraint = await session.run(
            "CREATE CONSTRAINT windops_graph_projection_id IF NOT EXISTS "
            "FOR (projection:WindOpsGraphProjection) REQUIRE projection.projectionId IS UNIQUE"
        )
        await projection_constraint.consume()

    @classmethod
    async def _replace_transaction(
        cls,
        transaction: Any,
        snapshot: GraphSnapshot,
        write_batch_size: int = 500,
    ) -> None:
        if write_batch_size <= 0:
            raise ValueError("write_batch_size must be positive")
        guard = await transaction.run(
            "MERGE (projection:WindOpsGraphProjection {projectionId: $projection_id}) "
            "ON CREATE SET projection.projectionSequence = '' "
            "WITH projection "
            "WHERE coalesce(projection.projectionSequence, '') <= $projection_sequence "
            "SET projection.projectionWriteLock = $projection_sequence "
            "RETURN projection.projectionSequence AS previous_sequence",
            projection_id=snapshot.projection_id,
            projection_sequence=snapshot.projection_sequence,
        )
        if await guard.single() is None:
            return
        deleted = await transaction.run(
            "MATCH (n:WindOpsKnowledge {projectionId: $projection_id}) DETACH DELETE n",
            projection_id=snapshot.projection_id,
        )
        await deleted.consume()

        by_label: dict[NodeType, list[dict[str, object]]] = {}

        async def flush_node_batch() -> None:
            for node_type, rows in by_label.items():
                label = cls._label(node_type)
                result = await transaction.run(
                    f"UNWIND $rows AS row "
                    f"MERGE (n:WindOpsKnowledge:{label} {{uid: row.uid}}) "
                    "SET n = row.properties",
                    rows=rows,
                )
                await result.consume()
            by_label.clear()

        node_batch_count = 0
        for node in snapshot.nodes:
            properties = {
                **_neo4j_properties(node.properties),
                "uid": node.uid,
                "entityId": node.entity_id,
                "nodeType": node.node_type.value,
                "projectionId": snapshot.projection_id,
                "sourceRevision": snapshot.source_revision,
                "projectionSequence": snapshot.projection_sequence,
            }
            by_label.setdefault(node.node_type, []).append(
                {"uid": node.uid, "properties": properties}
            )
            node_batch_count += 1
            if node_batch_count >= write_batch_size:
                await flush_node_batch()
                node_batch_count = 0
        await flush_node_batch()

        by_type: dict[RelationshipType, list[dict[str, object]]] = {}

        async def flush_relationship_batch() -> None:
            for relationship_type, rows in by_type.items():
                type_name = cls._relationship_type(relationship_type)
                result = await transaction.run(
                    "UNWIND $rows AS row "
                    "MATCH (source:WindOpsKnowledge {uid: row.source_uid}) "
                    "MATCH (target:WindOpsKnowledge {uid: row.target_uid}) "
                    f"MERGE (source)-[relationship:{type_name} {{uid: row.uid}}]->(target) "
                    "SET relationship = row.properties",
                    rows=rows,
                )
                await result.consume()
            by_type.clear()

        relationship_batch_count = 0
        for relationship in snapshot.relationships:
            properties = {
                **_neo4j_properties(relationship.properties),
                "uid": relationship.uid,
                "relationshipType": relationship.relationship_type.value,
                "sourceUid": relationship.source_uid,
                "targetUid": relationship.target_uid,
                "projectionId": snapshot.projection_id,
                "sourceRevision": snapshot.source_revision,
                "projectionSequence": snapshot.projection_sequence,
            }
            by_type.setdefault(relationship.relationship_type, []).append(
                {
                    "uid": relationship.uid,
                    "source_uid": relationship.source_uid,
                    "target_uid": relationship.target_uid,
                    "properties": properties,
                }
            )
            relationship_batch_count += 1
            if relationship_batch_count >= write_batch_size:
                await flush_relationship_batch()
                relationship_batch_count = 0
        await flush_relationship_batch()

        metadata = await transaction.run(
            "MERGE (projection:WindOpsGraphProjection {projectionId: $projection_id}) "
            "SET projection.sourceRevision = $source_revision, "
            "projection.projectionSequence = $projection_sequence, "
            "projection.generatedAt = $generated_at, "
            "projection.nodeCount = $node_count, "
            "projection.relationshipCount = $relationship_count "
            "REMOVE projection.projectionWriteLock",
            projection_id=snapshot.projection_id,
            projection_sequence=snapshot.projection_sequence,
            source_revision=snapshot.source_revision,
            generated_at=snapshot.generated_at.isoformat(),
            node_count=len(snapshot.nodes),
            relationship_count=len(snapshot.relationships),
        )
        await metadata.consume()

    async def snapshot(self, projection_id: str) -> GraphSnapshot | None:
        """Read a projection snapshot for scoped, backend-independent filtering.

        The projection is trusted storage, but authorization is deliberately
        applied after this read and before any graph data is returned.  Keeping
        this path shared with the in-memory test store makes the tenant/farm
        boundary testable without weakening the production Neo4j path.
        """

        async with self._driver.session(database=self._database) as session:
            metadata_result = await session.run(
                "MATCH (projection:WindOpsGraphProjection {projectionId: $projection_id}) "
                "RETURN projection.sourceRevision AS source_revision, "
                "projection.projectionSequence AS projection_sequence, "
                "projection.generatedAt AS generated_at",
                projection_id=projection_id,
            )
            metadata = await metadata_result.single()
            if metadata is None:
                return None
            node_result = await session.run(
                "MATCH (node:WindOpsKnowledge {projectionId: $projection_id}) "
                "RETURN properties(node) AS properties",
                projection_id=projection_id,
            )
            node_rows = await node_result.data()
            relationship_result = await session.run(
                "MATCH ()-[relationship {projectionId: $projection_id}]->() "
                "RETURN properties(relationship) AS properties",
                projection_id=projection_id,
            )
            relationship_rows = await relationship_result.data()

        generated_raw = str(metadata["generated_at"])
        try:
            generated_at = datetime.fromisoformat(generated_raw.replace("Z", "+00:00"))
        except ValueError:
            generated_at = datetime.now(UTC)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=UTC)
        nodes = tuple(
            sorted(
                (self._node_from_properties(dict(row["properties"])) for row in node_rows),
                key=lambda node: node.uid,
            )
        )
        relationships = tuple(
            sorted(
                (
                    self._relationship_from_properties(dict(row["properties"]))
                    for row in relationship_rows
                ),
                key=lambda relationship: relationship.uid,
            )
        )
        return GraphSnapshot(
            projection_id=projection_id,
            projection_sequence=str(metadata["projection_sequence"]),
            source_revision=str(metadata["source_revision"]),
            generated_at=generated_at,
            nodes=nodes,
            relationships=relationships,
        )

    async def summary(
        self, projection_id: str, policy: GraphAccessPolicy | None = None
    ) -> GraphSummary:
        if policy is not None:
            snapshot = await self.snapshot(projection_id)
            if snapshot is None:
                return GraphSummary(
                    backend=self.backend_name,
                    projection_id=projection_id,
                    projection_sequence=None,
                    source_revision=None,
                    generated_at=None,
                    node_count=0,
                    relationship_count=0,
                    orphan_node_count=0,
                    node_type_counts={},
                    relationship_type_counts={},
                )
            return graph_summary_for_snapshot(
                policy.filter_snapshot(snapshot), backend=self.backend_name
            )
        async with self._driver.session(database=self._database) as session:
            metadata_result = await session.run(
                "MATCH (projection:WindOpsGraphProjection {projectionId: $projection_id}) "
                "RETURN projection.sourceRevision AS source_revision, "
                "projection.projectionSequence AS projection_sequence, "
                "projection.generatedAt AS generated_at",
                projection_id=projection_id,
            )
            metadata = await metadata_result.single()
            node_result = await session.run(
                "MATCH (node:WindOpsKnowledge {projectionId: $projection_id}) "
                "RETURN node.nodeType AS type, count(*) AS count",
                projection_id=projection_id,
            )
            node_rows = await node_result.data()
            relationship_result = await session.run(
                "MATCH ()-[relationship {projectionId: $projection_id}]->() "
                "RETURN relationship.relationshipType AS type, count(*) AS count",
                projection_id=projection_id,
            )
            relationship_rows = await relationship_result.data()
            orphan_result = await session.run(
                "MATCH (node:WindOpsKnowledge {projectionId: $projection_id}) "
                "WHERE NOT (node)--() RETURN count(node) AS count",
                projection_id=projection_id,
            )
            orphan = await orphan_result.single()
        node_counts = {str(row["type"]): int(row["count"]) for row in node_rows}
        relationship_counts = {str(row["type"]): int(row["count"]) for row in relationship_rows}
        return GraphSummary(
            backend=self.backend_name,
            projection_id=projection_id,
            projection_sequence=(str(metadata["projection_sequence"]) if metadata else None),
            source_revision=str(metadata["source_revision"]) if metadata else None,
            generated_at=str(metadata["generated_at"]) if metadata else None,
            node_count=sum(node_counts.values()),
            relationship_count=sum(relationship_counts.values()),
            orphan_node_count=int(orphan["count"]) if orphan else 0,
            node_type_counts=node_counts,
            relationship_type_counts=relationship_counts,
        )

    async def resolve_uid(
        self,
        projection_id: str,
        entity_id: str,
        policy: GraphAccessPolicy | None = None,
    ) -> str | None:
        if policy is not None:
            snapshot = await self.snapshot(projection_id)
            if snapshot is None:
                return None
            visible = policy.filter_snapshot(snapshot)
            normalized = entity_id.casefold()
            return next(
                (
                    node.uid
                    for node in visible.nodes
                    if node.uid.casefold() == normalized or node.entity_id.casefold() == normalized
                ),
                None,
            )
        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                "MATCH (node:WindOpsKnowledge {projectionId: $projection_id}) "
                "WHERE node.uid = $entity_id OR toLower(node.entityId) = toLower($entity_id) "
                "RETURN node.uid AS uid LIMIT 1",
                projection_id=projection_id,
                entity_id=entity_id,
            )
            record = await result.single()
        return str(record["uid"]) if record else None

    async def subgraph(
        self,
        projection_id: str,
        root_uid: str,
        *,
        depth: int,
        path_limit: int = 100,
        policy: GraphAccessPolicy | None = None,
    ) -> GraphSubgraph:
        if depth < 1 or depth > 4:
            raise ValueError("knowledge graph traversal depth must be between 1 and 4")
        if policy is not None:
            snapshot = await self.snapshot(projection_id)
            return _subgraph_from_snapshot(
                policy.filter_snapshot(snapshot) if snapshot is not None else None,
                root_uid,
                depth=depth,
                path_limit=path_limit,
            )
        query = (
            "MATCH (root:WindOpsKnowledge {projectionId: $projection_id, uid: $root_uid}) "
            f"OPTIONAL MATCH path=(root)-[*1..{depth}]-(related:WindOpsKnowledge "
            "{projectionId: $projection_id}) "
            "RETURN properties(root) AS root, "
            "CASE WHEN path IS NULL THEN [] ELSE [node IN nodes(path) | properties(node)] END "
            "AS nodes, "
            "CASE WHEN path IS NULL THEN [] ELSE [relationship IN relationships(path) | "
            "properties(relationship)] END AS relationships "
            "LIMIT $path_limit"
        )
        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                query,
                projection_id=projection_id,
                root_uid=root_uid,
                path_limit=path_limit,
            )
            rows = await result.data()
        if not rows:
            return GraphSubgraph(root_uid=root_uid, nodes=(), relationships=(), paths=())

        nodes: dict[str, GraphNode] = {}
        relationships: dict[str, GraphRelationship] = {}
        paths: list[GraphPath] = []
        for row in rows:
            raw_nodes = list(row.get("nodes") or [])
            if not raw_nodes and row.get("root"):
                raw_nodes = [row["root"]]
            node_uids: list[str] = []
            for raw_node in raw_nodes:
                node = self._node_from_properties(raw_node)
                nodes[node.uid] = node
                node_uids.append(node.uid)
            relationship_uids: list[str] = []
            for raw_relationship in list(row.get("relationships") or []):
                relationship = self._relationship_from_properties(raw_relationship)
                relationships[relationship.uid] = relationship
                relationship_uids.append(relationship.uid)
            if relationship_uids:
                paths.append(
                    GraphPath(
                        node_uids=tuple(node_uids),
                        relationship_uids=tuple(relationship_uids),
                    )
                )
        return GraphSubgraph(
            root_uid=root_uid,
            nodes=tuple(nodes[uid] for uid in sorted(nodes)),
            relationships=tuple(relationships[uid] for uid in sorted(relationships)),
            paths=tuple(paths),
        )

    @staticmethod
    def _node_from_properties(raw: Mapping[str, object]) -> GraphNode:
        reserved = {
            "uid",
            "entityId",
            "nodeType",
            "projectionId",
            "projectionSequence",
            "sourceRevision",
        }
        node_type = NodeType(str(raw["nodeType"]))
        return GraphNode(
            uid=str(raw["uid"]),
            node_type=node_type,
            entity_id=str(raw["entityId"]),
            properties={
                key: value  # type: ignore[misc]
                for key, value in raw.items()
                if key not in reserved
            },
        )

    @staticmethod
    def _relationship_from_properties(raw: Mapping[str, object]) -> GraphRelationship:
        reserved = {
            "uid",
            "relationshipType",
            "sourceUid",
            "targetUid",
            "projectionId",
            "projectionSequence",
            "sourceRevision",
        }
        return GraphRelationship(
            uid=str(raw["uid"]),
            relationship_type=RelationshipType(str(raw["relationshipType"])),
            source_uid=str(raw["sourceUid"]),
            target_uid=str(raw["targetUid"]),
            properties={
                key: value  # type: ignore[misc]
                for key, value in raw.items()
                if key not in reserved
            },
        )

    async def identity_sets(
        self, projection_id: str, policy: GraphAccessPolicy | None = None
    ) -> tuple[set[str], set[str]]:
        if policy is not None:
            snapshot = await self.snapshot(projection_id)
            if snapshot is None:
                return set(), set()
            visible = policy.filter_snapshot(snapshot)
            return (
                {node.uid for node in visible.nodes},
                {relationship.uid for relationship in visible.relationships},
            )
        async with self._driver.session(database=self._database) as session:
            node_result = await session.run(
                "MATCH (node:WindOpsKnowledge {projectionId: $projection_id}) "
                "RETURN node.uid AS uid",
                projection_id=projection_id,
            )
            node_rows = await node_result.data()
            relationship_result = await session.run(
                "MATCH ()-[relationship {projectionId: $projection_id}]->() "
                "RETURN relationship.uid AS uid",
                projection_id=projection_id,
            )
            relationship_rows = await relationship_result.data()
        return (
            {str(row["uid"]) for row in node_rows},
            {str(row["uid"]) for row in relationship_rows},
        )

    async def unsupported_failure_mode_uids(
        self, projection_id: str, policy: GraphAccessPolicy | None = None
    ) -> set[str]:
        if policy is not None:
            snapshot = await self.snapshot(projection_id)
            if snapshot is None:
                return set()
            visible = policy.filter_snapshot(snapshot)
            supported = {
                relationship.source_uid
                for relationship in visible.relationships
                if relationship.relationship_type is RelationshipType.SUPPORTED_BY
            }
            return {
                node.uid
                for node in visible.nodes
                if node.node_type is NodeType.FAILURE_MODE and node.uid not in supported
            }
        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                "MATCH (failure:WindOpsKnowledge:FailureMode "
                "{projectionId: $projection_id}) "
                "WHERE NOT (failure)-[:SUPPORTED_BY]->(:WindOpsKnowledge:Evidence) "
                "RETURN failure.uid AS uid",
                projection_id=projection_id,
            )
            rows = await result.data()
        return {str(row["uid"]) for row in rows}

    async def close(self) -> None:
        await self._driver.close()
