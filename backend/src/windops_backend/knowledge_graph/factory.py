from __future__ import annotations

from windops_backend.config import Settings
from windops_backend.knowledge_graph.store import (
    InMemoryKnowledgeGraphStore,
    KnowledgeGraphStore,
    Neo4jKnowledgeGraphStore,
)


def create_knowledge_graph_store(settings: Settings) -> KnowledgeGraphStore:
    if settings.knowledge_graph_backend == "memory":
        return InMemoryKnowledgeGraphStore()
    if settings.knowledge_graph_backend != "neo4j":  # pragma: no cover - validated by Settings
        raise RuntimeError(
            f"unsupported knowledge graph backend: {settings.knowledge_graph_backend}"
        )
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    return Neo4jKnowledgeGraphStore(
        driver,
        settings.neo4j_database,
        write_batch_size=settings.knowledge_graph_projection_batch_size,
    )
