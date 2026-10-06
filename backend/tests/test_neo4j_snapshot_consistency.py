"""Controlled revision races; actual Neo4j is also exercised by the service suite."""

from datetime import UTC, datetime

import pytest

from windops_backend.knowledge_graph.store import Neo4jKnowledgeGraphStore


def metadata(revision):
    return {
        "source_revision": revision,
        "projection_sequence": "sequence-" + revision,
        "generated_at": datetime(2026, 10, 1, tzinfo=UTC).isoformat(),
        "node_count": 2,
        "relationship_count": 1,
    }


def rows(revision, *, missing=False):
    tags = {"sourceRevision": revision, "projectionSequence": "sequence-" + revision}
    nodes = [
        {"properties": {"uid": uid, "entityId": uid, "nodeType": "Turbine", **tags}}
        for uid in ("a", "b" if revision == "old" else "c")
    ]
    relationships = [
        {
            "properties": {
                "uid": "edge",
                "sourceUid": "a",
                "targetUid": "b" if revision == "old" else "c",
                "relationshipType": "HAS_SUBSYSTEM",
                **tags,
            }
        }
    ]
    return nodes[:1] if missing else nodes, relationships


class Result:
    def __init__(self, value):
        self.value = value

    async def single(self):
        return self.value

    async def data(self):
        return self.value


class Session:
    def __init__(self, before, node_rows, relationship_rows, after):
        self.before, self.after = before, after
        self.node_rows, self.relationship_rows = node_rows, relationship_rows
        self.metadata_reads = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def run(self, query, **kwargs):
        if "projection.sourceRevision" in query:
            self.metadata_reads += 1
            return Result(self.before if self.metadata_reads == 1 else self.after)
        if "properties(node)" in query:
            return Result(self.node_rows)
        if "properties(relationship)" in query:
            return Result(self.relationship_rows)
        raise AssertionError("unexpected query")


class Driver:
    def __init__(self, sessions):
        self.sessions = sessions
        self.reads = 0

    def session(self, **kwargs):
        result = self.sessions[self.reads]
        self.reads += 1
        return result


async def test_rebuild_between_node_and_relationship_reads_returns_only_coherent_revision():
    old_nodes, _ = rows("old")
    new_nodes, new_relationships = rows("new")
    driver = Driver(
        [
            Session(metadata("old"), old_nodes, new_relationships, metadata("new")),
            Session(metadata("new"), new_nodes, new_relationships, metadata("new")),
        ]
    )
    snapshot = await Neo4jKnowledgeGraphStore(driver, "neo4j").snapshot("test")
    assert snapshot.source_revision == "new"
    assert {node.uid for node in snapshot.nodes} == {"a", "c"}
    assert snapshot.relationships[0].target_uid == "c"
    assert driver.reads == 2


@pytest.mark.parametrize("conflict", ["row_version", "missing_row", "changed_metadata"])
async def test_persistent_snapshot_conflict_is_bounded_and_never_returns_partial_graph(conflict):
    nodes, relationships = rows("old", missing=conflict == "missing_row")
    before = metadata("old")
    after = metadata("new") if conflict == "changed_metadata" else before
    if conflict == "row_version":
        _, relationships = rows("new")
    driver = Driver(
        [
            Session(before, nodes, relationships, after)
            for _ in range(Neo4jKnowledgeGraphStore.MAX_SNAPSHOT_READ_ATTEMPTS)
        ]
    )
    with pytest.raises(RuntimeError, match="bounded snapshot reads"):
        await Neo4jKnowledgeGraphStore(driver, "neo4j").snapshot("test")
    assert driver.reads == Neo4jKnowledgeGraphStore.MAX_SNAPSHOT_READ_ATTEMPTS


async def test_missing_projection_still_returns_none():
    driver = Driver([Session(None, [], [], None)])
    assert await Neo4jKnowledgeGraphStore(driver, "neo4j").snapshot("missing") is None
    assert driver.reads == 1
