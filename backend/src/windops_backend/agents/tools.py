from __future__ import annotations

import asyncio
import hashlib
import math
import struct
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol, cast
from uuid import uuid4

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.config import Settings, get_settings
from windops_backend.enums import (
    ApprovalAction,
    DecisionStatus,
    Environment,
    MissionStatus,
    ResourceStatus,
)
from windops_backend.errors import ApprovalGateError, ConflictError, NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.models import (
    Alarm,
    Approval,
    AssetHealthEvent,
    Decision,
    KnowledgeCase,
    KnowledgeDocument,
    Mission,
    Resource,
    ResourceReservation,
    ScadaSample,
    Turbine,
    WeatherWindow,
    WindFarm,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.schemas import MissionAnalysisProfile
from windops_backend.services.knowledge_access import (
    knowledge_document_query,
    knowledge_scope_clause,
)
from windops_backend.work_order_templates import default_work_order_plan

EMBEDDING_DIMENSIONS = 1536
# text-embedding-3-small accepts a much larger token window, but keeping each
# request near 3k tokens leaves room for non-ASCII tokenization and provider
# envelope differences.  The body extractor has a separate document limit.
EMBEDDING_MAX_INPUT_CHARACTERS = 12_000
EMBEDDING_CHUNK_OVERLAP_CHARACTERS = 1_000
MAX_EMBEDDING_CHUNKS_PER_DOCUMENT = 512
MAX_QUERY_AUTO_INDEX_DOCUMENTS = 8
TOOL_CATALOG_VERSION = "2026.08.1"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


TOOL_CATALOG: tuple[dict[str, str], ...] = (
    {"name": "get_turbine_status", "mode": "read"},
    {"name": "query_scada", "mode": "read"},
    {"name": "query_alarm_history", "mode": "read"},
    {"name": "query_vibration", "mode": "read"},
    {"name": "query_weather", "mode": "read"},
    {"name": "query_maintenance_history", "mode": "read"},
    {"name": "query_similar_failures", "mode": "vector-read"},
    {"name": "calculate_health_score", "mode": "compute"},
    {"name": "predict_rul", "mode": "compute"},
    {"name": "create_decision", "mode": "draft-write-gated"},
    {"name": "create_work_order", "mode": "human-approval-gated-write"},
    {"name": "query_manual", "mode": "read"},
    {"name": "query_work_orders", "mode": "read"},
    {"name": "query_spare_parts", "mode": "read"},
    {"name": "query_crew", "mode": "read"},
    {"name": "query_vessels", "mode": "read"},
    {"name": "update_work_order", "mode": "governed-write"},
)


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    production_ready: bool

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicTestEmbeddingProvider:
    """Offline-only embedding used by tests; never represented as production RAG."""

    provider_name = "deterministic_test"
    model_name = "sha256-token-projection-v1"
    production_ready = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_deterministic_embedding(text) for text in texts]


class LiteLLMEmbeddingProvider:
    """Production embedding adapter with provider-reported vectors via LiteLLM."""

    provider_name = "litellm"
    production_ready = True

    def __init__(self, model: str) -> None:
        if not model.strip():
            raise ValueError("an explicit embedding model is required")
        self.model_name = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import litellm

        response = await litellm.aembedding(model=self.model_name, input=texts)
        ordered = sorted(response.data, key=lambda item: int(item["index"]))
        vectors = [list(map(float, item["embedding"])) for item in ordered]
        if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
            raise RuntimeError(
                f"embedding model {self.model_name} must return {EMBEDDING_DIMENSIONS} dimensions"
            )
        return vectors


def chunk_embedding_text(title: str, body: str) -> list[str]:
    """Split one document into bounded, overlapping model inputs."""

    title_prefix = title.strip()
    normalized_body = body.strip()
    if not title_prefix and not normalized_body:
        raise ValueError("knowledge document has no text to embed")

    prefix = f"{title_prefix}\n" if title_prefix and normalized_body else title_prefix
    available_body_characters = EMBEDDING_MAX_INPUT_CHARACTERS - len(prefix)
    if available_body_characters <= EMBEDDING_CHUNK_OVERLAP_CHARACTERS:
        raise ValueError("knowledge document title leaves no room for an embedding chunk")
    if not normalized_body:
        return [prefix[:EMBEDDING_MAX_INPUT_CHARACTERS]]
    if len(normalized_body) <= available_body_characters:
        return [f"{prefix}{normalized_body}"]

    chunks: list[str] = []
    start = 0
    while start < len(normalized_body):
        end = min(start + available_body_characters, len(normalized_body))
        chunks.append(f"{prefix}{normalized_body[start:end]}")
        if len(chunks) > MAX_EMBEDDING_CHUNKS_PER_DOCUMENT:
            raise ValueError(
                "knowledge document exceeds the maximum number of safe embedding chunks"
            )
        if end == len(normalized_body):
            break
        start = end - EMBEDDING_CHUNK_OVERLAP_CHARACTERS
    return chunks


async def embed_texts_with_controls(
    provider: EmbeddingProvider,
    texts: list[str],
    *,
    settings: Settings,
) -> list[list[float]]:
    """Embed bounded batches with a timeout and finite retry budget."""

    if not texts:
        return []
    if any(len(text) > EMBEDDING_MAX_INPUT_CHARACTERS for text in texts):
        raise ValueError("embedding input exceeds the configured model input limit")

    vectors: list[list[float]] = []
    for start in range(0, len(texts), settings.embedding_batch_size):
        batch = texts[start : start + settings.embedding_batch_size]
        batch_vectors: list[list[float]] | None = None
        for attempt in range(settings.embedding_max_retries + 1):
            try:
                async with asyncio.timeout(settings.embedding_timeout_seconds):
                    candidate_vectors = await provider.embed(batch)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt >= settings.embedding_max_retries:
                    raise RuntimeError(
                        f"embedding batch failed after {attempt + 1} attempts: {exc}"
                    ) from exc
                await asyncio.sleep(min(0.25 * (2**attempt), 2.0))
                continue

            if len(candidate_vectors) != len(batch):
                raise RuntimeError(
                    f"embedding provider returned {len(candidate_vectors)} vectors; "
                    f"expected {len(batch)}"
                )
            batch_vectors = []
            for vector in candidate_vectors:
                if len(vector) != EMBEDDING_DIMENSIONS:
                    raise RuntimeError(
                        f"embedding provider returned {len(vector)} dimensions; "
                        f"expected {EMBEDDING_DIMENSIONS}"
                    )
                batch_vectors.append([float(value) for value in vector])
            break
        if batch_vectors is None:  # pragma: no cover - retry loop always raises or succeeds
            raise RuntimeError("embedding batch did not return vectors")
        vectors.extend(batch_vectors)
    return vectors


def aggregate_embedding_vectors(vectors: list[list[float]]) -> list[float]:
    """Store one normalized document vector while indexing many passages."""

    if not vectors:
        raise ValueError("cannot aggregate an empty embedding result")
    if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
        raise RuntimeError("embedding vectors cannot be aggregated with mixed dimensions")
    aggregate = [0.0] * EMBEDDING_DIMENSIONS
    for vector in vectors:
        for index, value in enumerate(vector):
            aggregate[index] += value
    norm = math.sqrt(sum(value * value for value in aggregate)) or 1.0
    return [value / norm for value in aggregate]


def _deterministic_embedding(text: str) -> list[float]:
    values = [0.0] * EMBEDDING_DIMENSIONS
    tokens = [token for token in text.lower().replace("_", " ").split() if token]
    for token in tokens or [text.lower()]:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        values[index] += 1.0 if digest[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def pack_embedding_vector(vector: list[float]) -> bytes:
    return struct.pack(f"!{len(vector)}f", *vector)


def _unpack_vector(value: bytes) -> list[float]:
    return list(struct.unpack(f"!{len(value) // 4}f", value))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _citation_href(uri: str, minio_public_base: str) -> str:
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    if uri.startswith("minio://"):
        return f"{minio_public_base.rstrip('/')}/{uri.removeprefix('minio://')}"
    if uri.startswith("windops://knowledge/documents/"):
        document_id = uri.removeprefix("windops://knowledge/documents/")
        return f"/api/v1/knowledge/documents/{document_id}"
    return uri


class WindOpsToolAdapter(Protocol):
    async def get_turbine_status(self, turbine_id: str) -> dict[str, Any]: ...

    async def query_scada(
        self, turbine_id: str, variables: list[str] | None = None, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    async def query_alarm_history(
        self, turbine_id: str, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    async def query_vibration(self, turbine_id: str) -> dict[str, Any]: ...

    async def query_weather(self, wind_farm_id: str) -> list[dict[str, Any]]: ...

    async def query_maintenance_history(self, turbine_id: str) -> list[dict[str, Any]]: ...

    async def query_similar_failures(
        self, query: str, turbine_id: str | None = None, limit: int = 5
    ) -> list[dict[str, Any]]: ...

    async def calculate_health_score(self, turbine_id: str) -> dict[str, Any]: ...

    async def predict_rul(
        self, turbine_id: str, component: str, primary_variable: str | None = None
    ) -> dict[str, Any]: ...

    async def create_decision(
        self,
        mission_id: str,
        alternatives: list[dict[str, Any]],
        recommended_alternative_id: str,
        recommendation_reason: str,
        risks: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    async def create_work_order(
        self, mission_id: str, approval_id: str, turbine_id: str
    ) -> dict[str, Any]: ...


class ApprovalGate:
    @staticmethod
    async def require_approved(
        session: AsyncSession, mission_id: str, approval_id: str
    ) -> Approval:
        approval = await session.get(Approval, approval_id)
        mission = await session.get(Mission, mission_id)
        if (
            approval is None
            or approval.mission_id != mission_id
            or approval.action != ApprovalAction.APPROVE.value
            or mission is None
            or mission.status != MissionStatus.APPROVED.value
        ):
            raise ApprovalGateError(
                "a recorded human approval for the current mission is required before execution"
            )
        return approval


class DraftDecisionGate:
    """Allows only a non-executable proposal before the human approval boundary."""

    @staticmethod
    async def require_open_mission(session: AsyncSession, mission_id: str) -> Mission:
        mission = await session.get(Mission, mission_id)
        if mission is None:
            raise NotFoundError(f"mission {mission_id} was not found")
        if mission.status not in {
            MissionStatus.DETECTED.value,
            MissionStatus.INVESTIGATING.value,
            MissionStatus.DIAGNOSED.value,
            MissionStatus.UNDER_REVIEW.value,
        }:
            raise ApprovalGateError(
                "decisions may only be created as pending-approval proposals for an open mission"
            )
        return mission


class SQLToolAdapter:
    """SQL-backed tools with a consumable, public call ledger for each graph node."""

    def __init__(
        self,
        session: AsyncSession,
        embedding_provider: EmbeddingProvider | None = None,
        settings: Settings | None = None,
        knowledge_policy: GraphAccessPolicy | None = None,
    ) -> None:
        self.session = session
        runtime_settings = settings or get_settings()
        self.settings = runtime_settings
        self.minio_public_base = runtime_settings.minio_public_base
        dialect = session.bind.dialect.name if session.bind is not None else "unknown"
        selected_provider: EmbeddingProvider
        if embedding_provider is None:
            selected_provider = cast(
                EmbeddingProvider,
                (
                    DeterministicTestEmbeddingProvider()
                    if dialect == "sqlite" or runtime_settings.environment is Environment.TEST
                    else LiteLLMEmbeddingProvider(runtime_settings.embedding_model)
                ),
            )
        else:
            selected_provider = embedding_provider
        if (
            dialect == "postgresql"
            and runtime_settings.environment is not Environment.TEST
            and not selected_provider.production_ready
        ):
            raise RuntimeError("production PostgreSQL RAG requires a production embedding provider")
        self.embedding_provider = selected_provider
        # SQLite is only used by the deterministic test double. Production
        # PostgreSQL callers must pass an explicit policy; an absent policy
        # therefore fails closed instead of becoming a global RAG read.
        self.knowledge_policy = knowledge_policy or GraphAccessPolicy.from_values(
            unrestricted=dialect == "sqlite"
        )
        self._tool_calls: list[dict[str, Any]] = []

    def reset_tool_calls(self) -> None:
        self._tool_calls = []

    def consume_tool_calls(self) -> list[dict[str, Any]]:
        calls, self._tool_calls = self._tool_calls, []
        return calls

    def _record_call(
        self, name: str, started: float, arguments: dict[str, Any], result_count: int = 1
    ) -> None:
        self._tool_calls.append(
            {
                "name": name,
                "mode": next(item["mode"] for item in TOOL_CATALOG if item["name"] == name),
                "version": TOOL_CATALOG_VERSION,
                "arguments": arguments,
                "result_count": result_count,
                "latency_ms": max(0, round((perf_counter() - started) * 1000)),
            }
        )

    async def get_turbine_status(self, turbine_id: str) -> dict[str, Any]:
        started = perf_counter()
        turbine = await self.session.get(Turbine, turbine_id)
        if turbine is None:
            raise NotFoundError(f"turbine {turbine_id} was not found")
        resources = (await self.session.scalars(select(Resource).order_by(Resource.id))).all()
        result = {
            "turbine_id": turbine.id,
            "wind_farm_id": turbine.wind_farm_id,
            "model": turbine.model,
            "status": turbine.status,
            "health_score": turbine.health_score,
            "updated_at": turbine.updated_at.isoformat(),
            "maintenance_resources": [
                {
                    "resource_id": resource.id,
                    "resource_type": resource.resource_type,
                    "name": resource.name,
                    "quantity": resource.quantity,
                    "status": resource.status,
                }
                for resource in resources
            ],
        }
        self._record_call("get_turbine_status", started, {"turbine_id": turbine_id})
        return result

    async def query_scada(
        self, turbine_id: str, variables: list[str] | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        started = perf_counter()
        statement = select(ScadaSample).where(ScadaSample.turbine_id == turbine_id)
        if variables:
            statement = statement.where(ScadaSample.variable.in_(variables))
        statement = statement.order_by(desc(ScadaSample.observed_at)).limit(limit)
        samples = (await self.session.scalars(statement)).all()
        result = [
            {
                "sample_id": row.id,
                "source_event_id": row.source_event_id,
                "source_id": row.source_id,
                "source_sequence": row.source_sequence,
                "variable": row.variable,
                "value": row.value,
                "unit": row.unit,
                "observed_at": row.observed_at.isoformat(),
                "received_at": row.received_at.isoformat(),
                "late": row.is_late,
                "quality": row.quality,
                "attributes": row.attributes,
            }
            for row in samples
        ]
        self._record_call(
            "query_scada",
            started,
            {"turbine_id": turbine_id, "variables": variables, "limit": limit},
            len(result),
        )
        return result

    async def query_alarm_history(self, turbine_id: str, limit: int = 100) -> list[dict[str, Any]]:
        started = perf_counter()
        alarms = (
            await self.session.scalars(
                select(Alarm)
                .where(Alarm.turbine_id == turbine_id)
                .order_by(desc(Alarm.triggered_at))
                .limit(limit)
            )
        ).all()
        result = [
            {
                "alarm_id": alarm.id,
                "code": alarm.code,
                "subsystem": alarm.subsystem,
                "severity": alarm.severity,
                "status": alarm.status,
                "triggered_at": alarm.triggered_at.isoformat(),
                "evidence": alarm.evidence,
            }
            for alarm in alarms
        ]
        self._record_call(
            "query_alarm_history",
            started,
            {"turbine_id": turbine_id, "limit": limit},
            len(result),
        )
        return result

    async def query_vibration(self, turbine_id: str) -> dict[str, Any]:
        started = perf_counter()
        rows = await self.query_scada(turbine_id, ["main_bearing_vibration_rms"], limit=24)
        if not rows:
            result: dict[str, Any] = {
                "turbine_id": turbine_id,
                "samples": [],
                "trend_pct": 0.0,
            }
        else:
            latest = rows[0]
            attributes = latest.get("attributes", {})
            baseline = float(attributes.get("baseline", latest["value"])) or 1.0
            trend_pct = round(((float(latest["value"]) - baseline) / baseline) * 100, 1)
            result = {
                "turbine_id": turbine_id,
                "samples": rows,
                "rms_mm_s": latest["value"],
                "trend_pct": trend_pct,
                "anomaly_score": float(attributes.get("anomaly_score", 0.0)),
                "spectrum_marker": (
                    "BPFO-sideband-pattern" if float(latest["value"]) >= 4.5 else "normal"
                ),
            }
        self._record_call("query_vibration", started, {"turbine_id": turbine_id})
        return result

    async def query_weather(self, wind_farm_id: str) -> list[dict[str, Any]]:
        started = perf_counter()
        windows = (
            await self.session.scalars(
                select(WeatherWindow)
                .where(WeatherWindow.wind_farm_id == wind_farm_id)
                .order_by(WeatherWindow.starts_at)
            )
        ).all()
        result = [
            {
                "window_id": window.id,
                "starts_at": window.starts_at.isoformat(),
                "ends_at": window.ends_at.isoformat(),
                "wind_speed_ms": window.wind_speed_ms,
                "wave_height_m": window.wave_height_m,
                "suitable": window.suitable,
            }
            for window in windows
        ]
        self._record_call("query_weather", started, {"wind_farm_id": wind_farm_id}, len(result))
        return result

    async def query_maintenance_history(self, turbine_id: str) -> list[dict[str, Any]]:
        started = perf_counter()
        work_orders = (
            await self.session.scalars(
                select(WorkOrder)
                .where(WorkOrder.turbine_id == turbine_id)
                .order_by(desc(WorkOrder.created_at))
            )
        ).all()
        result = [
            {
                "work_order_id": row.id,
                "mission_id": row.mission_id,
                "title": row.title,
                "status": row.status,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in work_orders
        ]
        self._record_call(
            "query_maintenance_history",
            started,
            {"turbine_id": turbine_id},
            len(result),
        )
        return result

    async def _ensure_document_vectors(self, documents: list[KnowledgeDocument]) -> None:
        missing = [document for document in documents if not document.vectorized]
        if not missing:
            return
        document_chunks = [
            chunk_embedding_text(document.title, document.body) for document in missing
        ]
        vectors = await embed_texts_with_controls(
            self.embedding_provider,
            [chunk for chunks in document_chunks for chunk in chunks],
            settings=self.settings,
        )
        dialect = self.session.bind.dialect.name if self.session.bind is not None else "unknown"
        vector_offset = 0
        for document, chunks in zip(missing, document_chunks, strict=True):
            chunk_vectors = vectors[vector_offset : vector_offset + len(chunks)]
            vector_offset += len(chunks)
            vector = aggregate_embedding_vectors(chunk_vectors)
            indexed_at = datetime.now(UTC)
            document.embedding = pack_embedding_vector(vector) if dialect == "sqlite" else vector
            document.vectorized = True
            document.ingestion_status = "indexed"
            document.embedding_provider = self.embedding_provider.provider_name
            document.embedding_model = self.embedding_provider.model_name
            document.indexed_at = indexed_at
            document.updated_at = indexed_at
        await self.session.flush()

    async def index_knowledge_documents(self) -> dict[str, Any]:
        """Persist embeddings for controlled documents without running a graph query."""

        document_count = int(
            await self.session.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0
        )
        indexed_count = 0
        while True:
            documents = list(
                (
                    await self.session.scalars(
                        select(KnowledgeDocument)
                        .where(KnowledgeDocument.vectorized.is_(False))
                        .order_by(KnowledgeDocument.id)
                        .limit(self.settings.embedding_batch_size)
                    )
                ).all()
            )
            if not documents:
                break
            await self._ensure_document_vectors(documents)
            indexed_count += len(documents)
        return {
            "document_count": document_count,
            "indexed_count": indexed_count,
            "embedding_provider": self.embedding_provider.provider_name,
            "embedding_model": self.embedding_provider.model_name,
        }

    async def visible_knowledge_documents(self) -> list[KnowledgeDocument]:
        return list(
            (
                await self.session.scalars(
                    knowledge_document_query(self.knowledge_policy).order_by(KnowledgeDocument.id)
                )
            ).all()
        )

    async def query_similar_failures(
        self,
        query: str,
        turbine_id: str | None = None,
        limit: int = 5,
        *,
        vectorize_missing: bool = True,
    ) -> list[dict[str, Any]]:
        started = perf_counter()
        dialect = self.session.bind.dialect.name if self.session.bind is not None else "unknown"
        if dialect == "postgresql":
            documents: list[KnowledgeDocument] = []
            if vectorize_missing:
                missing_documents = list(
                    (
                        await self.session.scalars(
                            knowledge_document_query(self.knowledge_policy)
                            .where(KnowledgeDocument.vectorized.is_(False))
                            .order_by(KnowledgeDocument.id)
                            .limit(MAX_QUERY_AUTO_INDEX_DOCUMENTS)
                        )
                    ).all()
                )
                await self._ensure_document_vectors(missing_documents)
        else:
            documents = await self.visible_knowledge_documents()
            if vectorize_missing:
                await self._ensure_document_vectors(documents[:MAX_QUERY_AUTO_INDEX_DOCUMENTS])
        query_vector = (
            await embed_texts_with_controls(
                self.embedding_provider, [query], settings=self.settings
            )
        )[0]
        if dialect == "postgresql":
            distance = KnowledgeDocument.embedding.cosine_distance(query_vector)
            ranked = (
                await self.session.execute(
                    select(KnowledgeDocument, distance.label("distance"))
                    .where(
                        KnowledgeDocument.vectorized.is_(True),
                        knowledge_scope_clause(
                            self.knowledge_policy,
                            tenant_column=KnowledgeDocument.tenant_id,
                            wind_farm_column=KnowledgeDocument.wind_farm_id,
                            turbine_column=KnowledgeDocument.turbine_id,
                            entity_column=KnowledgeDocument.id,
                            data_scope_column=KnowledgeDocument.data_scope,
                        ),
                    )
                    .order_by(distance)
                    .limit(limit)
                )
            ).all()
            doc_matches = [
                (document, 1.0 - float(distance_value)) for document, distance_value in ranked
            ]
            retrieval_method = "pgvector_hnsw_cosine"
        elif dialect == "sqlite":
            doc_matches = sorted(
                (
                    (
                        document,
                        _cosine_similarity(
                            query_vector,
                            _unpack_vector(document.embedding)
                            if isinstance(document.embedding, bytes)
                            else list(document.embedding or []),
                        ),
                    )
                    for document in documents
                    if document.vectorized and document.embedding is not None
                ),
                key=lambda item: item[1],
                reverse=True,
            )[:limit]
            retrieval_method = "deterministic_test_cosine"
        else:
            raise RuntimeError(f"unsupported RAG database dialect: {dialect}")

        result = [
            {
                "match_type": "knowledge_document",
                "document_id": document.id,
                "title": document.title,
                "excerpt": document.body[:320],
                "similarity": round(similarity, 6),
                "citation_uri": document.citation_uri,
                "citation_href": _citation_href(document.citation_uri, self.minio_public_base),
                "retrieval_method": retrieval_method,
                "embedding_provider": self.embedding_provider.provider_name,
                "embedding_model": self.embedding_provider.model_name,
            }
            for document, similarity in doc_matches
        ]
        if turbine_id:
            cases = (
                await self.session.scalars(
                    select(KnowledgeCase)
                    .join(Turbine, Turbine.id == KnowledgeCase.turbine_id)
                    .join(WindFarm, WindFarm.id == Turbine.wind_farm_id)
                    .where(
                        knowledge_scope_clause(
                            self.knowledge_policy,
                            tenant_column=WindFarm.tenant_id,
                            wind_farm_column=WindFarm.id,
                            turbine_column=Turbine.id,
                        )
                    )
                    .where(KnowledgeCase.turbine_id == turbine_id)
                    .order_by(desc(KnowledgeCase.created_at))
                    .limit(limit)
                )
            ).all()
            result.extend(
                {
                    "match_type": "resolved_case",
                    "case_id": case.id,
                    "title": case.title,
                    "similarity": None,
                    "citation_uri": f"windops://knowledge/cases/{case.id}",
                    "citation_href": f"/knowledge?caseId={case.id}",
                    "retrieval_method": "relational_asset_history",
                }
                for case in cases
            )
        self._record_call(
            "query_similar_failures",
            started,
            {
                "query": query,
                "turbine_id": turbine_id,
                "limit": limit,
                "vectorize_missing": vectorize_missing,
            },
            len(result),
        )
        return result

    async def calculate_health_score(self, turbine_id: str) -> dict[str, Any]:
        started = perf_counter()
        turbine = await self.session.get(Turbine, turbine_id)
        if turbine is None:
            raise NotFoundError(f"turbine {turbine_id} was not found")
        vibration = await self.query_vibration(turbine_id)
        samples = await self.query_scada(
            turbine_id, ["main_bearing_temperature", "active_power"], limit=24
        )
        anomaly = float(vibration.get("anomaly_score", 0.0))
        trend = max(0.0, float(vibration.get("trend_pct", 0.0)))
        poor_quality = sum(1 for row in samples if row["quality"] != "good")
        deductions = min(55.0, anomaly * 24.0 + trend * 0.25 + poor_quality * 2.0)
        score = round(max(0.0, min(100.0, 100.0 - deductions)), 1)
        result = {
            "turbine_id": turbine_id,
            "health_score": score,
            "status": "warning" if score < 80 else "healthy",
            "inputs": {
                "anomaly_score": anomaly,
                "vibration_trend_pct": trend,
                "poor_quality_samples": poor_quality,
            },
            "calculation_version": "health-formula-2026.08",
            "persisted": False,
        }
        self._record_call("calculate_health_score", started, {"turbine_id": turbine_id})
        return result

    async def predict_rul(
        self, turbine_id: str, component: str, primary_variable: str | None = None
    ) -> dict[str, Any]:
        started = perf_counter()
        selected_variable = primary_variable or "main_bearing_vibration_rms"
        if selected_variable == "main_bearing_vibration_rms":
            condition = await self.query_vibration(turbine_id)
        else:
            samples = await self.query_scada(turbine_id, [selected_variable], limit=24)
            latest: dict[str, Any]
            if samples:
                latest = samples[0]
            else:
                alarms = await self.query_alarm_history(turbine_id, limit=100)
                matching_alarm = next(
                    (
                        alarm
                        for alarm in alarms
                        if alarm.get("evidence", {}).get("variable") == selected_variable
                    ),
                    None,
                )
                latest = dict(matching_alarm.get("evidence", {})) if matching_alarm else {}
            attributes = latest.get("attributes", {})
            latest_value = float(latest.get("value", 0.0))
            baseline = float(attributes.get("baseline", latest_value)) or 1.0
            condition = {
                "anomaly_score": float(attributes.get("anomaly_score", 0.0)),
                "trend_pct": ((latest_value - baseline) / abs(baseline)) * 100,
            }
        anomaly = max(0.0, min(1.0, float(condition.get("anomaly_score", 0.0))))
        trend = max(0.0, float(condition.get("trend_pct", 0.0)))
        daily_damage = 0.15 + (anomaly * 2.2) + (trend / 35.0)
        estimated_days = max(7, round(180 / daily_damage))
        failure_probability = round(min(0.95, anomaly * 0.32 + trend / 240.0), 3)
        result = {
            "turbine_id": turbine_id,
            "component": component,
            "estimated_rul_days": estimated_days,
            "failure_probability_30d": failure_probability,
            "inputs": {
                **({"primary_variable": selected_variable} if primary_variable is not None else {}),
                "anomaly_score": anomaly,
                "trend_pct": trend,
            },
            "model_version": "physics-informed-rul-2026.08",
        }
        self._record_call(
            "predict_rul",
            started,
            {
                "turbine_id": turbine_id,
                "component": component,
                "primary_variable": selected_variable,
            },
        )
        return result

    async def create_decision(
        self,
        mission_id: str,
        alternatives: list[dict[str, Any]],
        recommended_alternative_id: str,
        recommendation_reason: str,
        risks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        started = perf_counter()
        await DraftDecisionGate.require_open_mission(self.session, mission_id)
        if len(alternatives) != 3:
            raise ConflictError("a decision must contain exactly three alternatives")
        ids = {str(item.get("alternative_id")) for item in alternatives}
        if len(ids) != 3 or recommended_alternative_id not in ids:
            raise ConflictError("the recommendation must identify one of three unique alternatives")
        recommended_ids = {
            str(item.get("alternative_id")) for item in alternatives if item.get("recommended")
        }
        if recommended_ids != {recommended_alternative_id}:
            raise ConflictError("exactly one alternative must be marked as recommended")
        existing = await self.session.scalar(
            select(Decision).where(Decision.mission_id == mission_id)
        )
        if existing is None:
            existing = Decision(
                id=f"DEC-{mission_id}",
                mission_id=mission_id,
                alternatives=alternatives,
                recommended_alternative_id=recommended_alternative_id,
                recommendation_reason=recommendation_reason,
                risks=risks,
            )
            self.session.add(existing)
        elif existing.status != DecisionStatus.PENDING_APPROVAL.value:
            raise ApprovalGateError("an approved or rejected decision is immutable")
        else:
            existing.alternatives = alternatives
            existing.recommended_alternative_id = recommended_alternative_id
            existing.recommendation_reason = recommendation_reason
            existing.risks = risks
            existing.updated_at = datetime.now(UTC)
        await self.session.flush()
        result = {
            "decision_id": existing.id,
            "status": existing.status,
            "recommended_alternative_id": existing.recommended_alternative_id,
            "requires_human_approval": True,
            "approval_id": existing.approval_id,
        }
        self._record_call("create_decision", started, {"mission_id": mission_id})
        return result

    async def update_asset_health(
        self, turbine_id: str, mission_id: str, score: float, status: str, reason: str
    ) -> dict[str, Any]:
        """Internal persistence helper; deliberately not exposed in the 11-tool agent catalog."""
        turbine = await self.session.get(Turbine, turbine_id)
        if turbine is None:
            raise NotFoundError(f"turbine {turbine_id} was not found")
        turbine.health_score = score
        turbine.status = status
        turbine.updated_at = datetime.now(UTC)
        event = AssetHealthEvent(
            id=str(uuid4()),
            turbine_id=turbine_id,
            mission_id=mission_id,
            score=score,
            status=status,
            reason=reason,
        )
        self.session.add(event)
        await self.session.flush()
        return {"health_event_id": event.id, "score": score, "status": status}

    async def _reserve_resources(self, mission_id: str, required_types: set[str]) -> list[str]:
        statement = (
            select(Resource)
            .where(
                Resource.status == ResourceStatus.AVAILABLE.value,
                Resource.resource_type.in_(required_types),
            )
            .order_by(Resource.id)
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        resources = (await self.session.scalars(statement)).all()
        if {resource.resource_type for resource in resources} != required_types:
            raise ConflictError(
                "every resource type required by the approved work plan must be "
                "available atomically"
            )
        reservation_ids: list[str] = []
        claimed_types: set[str] = set()
        for resource in resources:
            if resource.resource_type in claimed_types:
                continue
            claimed = await self.session.execute(
                update(Resource)
                .where(
                    Resource.id == resource.id,
                    Resource.status == ResourceStatus.AVAILABLE.value,
                )
                .values(status=ResourceStatus.RESERVED.value, updated_at=datetime.now(UTC))
            )
            if int(getattr(claimed, "rowcount", 0)) != 1:
                continue
            reservation = ResourceReservation(
                id=str(uuid4()), mission_id=mission_id, resource_id=resource.id, quantity=1
            )
            self.session.add(reservation)
            reservation_ids.append(reservation.id)
            claimed_types.add(resource.resource_type)
        if claimed_types != required_types:
            raise ConflictError(
                "another mission claimed a required resource during atomic reservation"
            )
        await self.session.flush()
        return reservation_ids

    async def create_work_order(
        self, mission_id: str, approval_id: str, turbine_id: str
    ) -> dict[str, Any]:
        started = perf_counter()
        await ApprovalGate.require_approved(self.session, mission_id, approval_id)
        mission = await self.session.get(Mission, mission_id)
        if mission is None:  # pragma: no cover - approval gate has already checked this
            raise NotFoundError(f"mission {mission_id} was not found")
        raw_profile = mission.public_state.get("analysis_profile", {})
        if not raw_profile:
            raw_profile = {
                "component": "main_bearing",
                "primary_variable": "main_bearing_vibration_rms",
                "related_variables": ["main_bearing_temperature", "active_power"],
                "failure_mode_hint": "main-bearing degradation",
                "knowledge_query": "main bearing rising RMS temperature inspection",
            }
        profile = MissionAnalysisProfile.model_validate(raw_profile)
        plan = profile.work_order_plan or default_work_order_plan(
            component=profile.component,
            turbine_id=turbine_id,
            primary_variable=profile.primary_variable,
        )
        decision = await self.session.scalar(
            select(Decision).where(Decision.mission_id == mission_id)
        )
        if decision is None:
            raise ApprovalGateError("an approved mission must have a persisted decision")
        if decision.approval_id not in {None, approval_id}:
            raise ApprovalGateError("the approval does not belong to the persisted decision")
        selected_alternative_id = (
            decision.selected_alternative_id or decision.recommended_alternative_id
        )
        selected_alternative = next(
            (
                item
                for item in decision.alternatives
                if str(item.get("alternative_id")) == selected_alternative_id
            ),
            None,
        )
        if selected_alternative is None:
            raise ApprovalGateError("the approved alternative is absent from the decision")
        selected_action = str(selected_alternative.get("action", "")).strip()
        if not selected_action:
            raise ApprovalGateError("the approved alternative has no executable action")
        decision.approval_id = approval_id
        decision.status = DecisionStatus.APPROVED.value
        decision.updated_at = datetime.now(UTC)

        existing = await self.session.scalar(
            select(WorkOrder).where(WorkOrder.mission_id == mission_id)
        )
        if existing is not None:
            tasks = (
                await self.session.scalars(
                    select(WorkOrderTask)
                    .where(WorkOrderTask.work_order_id == existing.id)
                    .order_by(WorkOrderTask.sequence)
                )
            ).all()
            reservations = (
                await self.session.scalars(
                    select(ResourceReservation).where(ResourceReservation.mission_id == mission_id)
                )
            ).all()
            result = {
                "work_order_id": existing.id,
                "task_ids": [task.id for task in tasks],
                "resource_reservation_ids": [row.id for row in reservations],
                "created": False,
            }
            self._record_call("create_work_order", started, {"mission_id": mission_id})
            return result

        turbine = await self.session.get(Turbine, turbine_id)
        if turbine is None:
            raise NotFoundError(f"turbine {turbine_id} was not found")
        raw_weather_window_id = selected_alternative.get("weather_window_id")
        if not isinstance(raw_weather_window_id, str) or not raw_weather_window_id.strip():
            raise ConflictError("the approved alternative does not identify a weather window")
        weather_window_id = raw_weather_window_id.strip()
        weather_window = await self.session.get(WeatherWindow, weather_window_id)
        if weather_window is None:
            raise ConflictError(f"the approved weather window {weather_window_id} was not found")
        if weather_window.wind_farm_id != turbine.wind_farm_id:
            raise ConflictError(
                f"the approved weather window {weather_window_id} is not assigned "
                "to the turbine farm"
            )

        now = datetime.now(UTC)
        window_start = _as_utc(weather_window.starts_at)
        window_end = _as_utc(weather_window.ends_at)
        if not weather_window.suitable or window_end <= now:
            raise ConflictError(
                f"the approved weather window {weather_window_id} is no longer suitable"
            )
        if window_end <= window_start:
            raise ConflictError(f"the approved weather window {weather_window_id} is invalid")
        try:
            estimated_duration_hours = float(plan.safety_plan.get("estimated_duration_hours", 0))
        except (TypeError, ValueError) as exc:
            raise ConflictError("the approved work plan has an invalid estimated duration") from exc
        if not math.isfinite(estimated_duration_hours) or estimated_duration_hours <= 0:
            raise ConflictError("the approved work plan must have a positive estimated duration")
        planned_start = max(now, window_start)
        planned_end = planned_start + timedelta(hours=estimated_duration_hours)
        if planned_end > window_end:
            raise ConflictError(
                f"the approved weather window {weather_window_id} does not cover the "
                "estimated work duration"
            )

        work_order_id = f"WO-{now:%Y%m%d}-{uuid4().hex[:6].upper()}"
        work_order = WorkOrder(
            id=work_order_id,
            mission_id=mission_id,
            approval_id=approval_id,
            turbine_id=turbine_id,
            title=plan.title,
            selected_alternative_id=selected_alternative_id,
            selected_action=selected_action,
            priority=plan.priority,
            safety_plan={
                **plan.safety_plan,
                "decision_alternative_id": selected_alternative_id,
                "approved_action": selected_action,
                "weather_window_id": weather_window_id,
            },
            closure_policy={
                "health_score_field": plan.closure_health_score_field,
                "healthy_threshold": plan.healthy_threshold,
                "component": profile.component,
            },
            planned_start=planned_start,
            deadline=planned_end,
            estimated_duration_hours=estimated_duration_hours,
        )
        self.session.add(work_order)
        tasks = [
            WorkOrderTask(
                id=str(uuid4()),
                work_order_id=work_order_id,
                sequence=index,
                title=task.title,
                schema_version=task.schema_version,
                measurement_schema=task.measurement_schema,
            )
            for index, task in enumerate(plan.tasks, start=1)
        ]
        self.session.add_all(tasks)
        reservation_ids = await self._reserve_resources(
            mission_id, set(plan.required_resource_types)
        )
        if not reservation_ids:
            raise ConflictError("no unclaimed maintenance resources are available")
        await self.session.flush()
        result = {
            "work_order_id": work_order_id,
            "task_ids": [task.id for task in tasks],
            "resource_reservation_ids": reservation_ids,
            "created": True,
        }
        self._record_call(
            "create_work_order", started, {"mission_id": mission_id, "turbine_id": turbine_id}
        )
        return result
