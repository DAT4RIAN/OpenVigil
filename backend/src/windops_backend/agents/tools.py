from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol, cast
from uuid import uuid4

from sqlalchemy import Table, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

import windops_backend.agents.embeddings as _embeddings
from windops_backend.agents.embeddings import (
    MAX_QUERY_AUTO_INDEX_DOCUMENTS,
)
from windops_backend.agents.embeddings import (
    DeterministicTestEmbeddingProvider as DeterministicTestEmbeddingProvider,
)
from windops_backend.agents.embeddings import (
    EmbeddingProvider as EmbeddingProvider,
)
from windops_backend.agents.embeddings import (
    LiteLLMEmbeddingProvider as LiteLLMEmbeddingProvider,
)
from windops_backend.agents.embeddings import (
    aggregate_embedding_vectors as aggregate_embedding_vectors,
)
from windops_backend.agents.embeddings import (
    chunk_embedding_text as chunk_embedding_text,
)
from windops_backend.agents.embeddings import (
    embed_texts_with_controls as embed_texts_with_controls,
)
from windops_backend.agents.embeddings import (
    pack_embedding_vector as pack_embedding_vector,
)
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
from windops_backend.storage import ArtifactVerifier
from windops_backend.work_order_templates import default_work_order_plan
from windops_backend.work_plan_binding import describe_execution_plan, validate_execution_binding

EMBEDDING_DIMENSIONS = _embeddings.EMBEDDING_DIMENSIONS
EMBEDDING_MAX_INPUT_CHARACTERS = _embeddings.EMBEDDING_MAX_INPUT_CHARACTERS
EMBEDDING_CHUNK_OVERLAP_CHARACTERS = _embeddings.EMBEDDING_CHUNK_OVERLAP_CHARACTERS
MAX_EMBEDDING_CHUNKS_PER_DOCUMENT = _embeddings.MAX_EMBEDDING_CHUNKS_PER_DOCUMENT
TOOL_CATALOG_VERSION = "2026.10.1"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


TOOL_CATALOG: tuple[dict[str, str], ...] = (
    {"name": "query_structural_context", "mode": "read"},
    {"name": "get_turbine_status", "mode": "read"},
    {"name": "query_scada", "mode": "read"},
    {"name": "query_alarm_history", "mode": "read"},
    {"name": "query_vibration", "mode": "read"},
    {"name": "query_weather", "mode": "read"},
    {"name": "query_maintenance_history", "mode": "read"},
    {"name": "query_similar_failures", "mode": "vector-read"},
    {"name": "calculate_health_score", "mode": "compute"},
    {"name": "assess_condition_evidence", "mode": "compute"},
    {"name": "create_decision", "mode": "draft-write-gated"},
    {"name": "create_work_order", "mode": "human-approval-gated-write"},
    {"name": "query_manual", "mode": "read"},
    {"name": "query_work_orders", "mode": "read"},
    {"name": "query_spare_parts", "mode": "read"},
    {"name": "query_crew", "mode": "read"},
    {"name": "query_vessels", "mode": "read"},
    {"name": "update_work_order", "mode": "governed-write"},
)


class OpenVigilToolAdapter(Protocol):
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

    async def assess_condition_evidence(
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
        artifact_verifier: ArtifactVerifier | None = None,
    ) -> None:
        self.session = session
        self.artifact_verifier = artifact_verifier
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
                    else LiteLLMEmbeddingProvider.from_settings(runtime_settings)
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

    async def query_structural_context(self, mission_id: str) -> dict[str, Any]:
        from windops_backend.services.structural_missions import structural_mission_detail

        started = perf_counter()
        result = await structural_mission_detail(self.session, mission_id)
        self._record_call(
            "query_structural_context",
            started,
            {"mission_id": mission_id},
            len(result["evidence_cards"]),
        )
        return result

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
                "spectrum_marker": "unavailable",
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
                # RMS amplitude cannot establish a frequency-domain fault signature.
                # This tool reads scalar telemetry, not a verified spectrum artifact.
                "spectrum_marker": "unavailable",
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

    def _embedding_is_current(self, document: KnowledgeDocument) -> bool:
        return (
            document.vectorized
            and document.embedding_provider == self.embedding_provider.provider_name
            and document.embedding_model == self.embedding_provider.model_name
        )

    def _stale_embedding_clause(self) -> ColumnElement[bool]:
        from windops_backend.services.knowledge_passages import stale_document_clause

        return stale_document_clause(self.embedding_provider)

    async def _ensure_document_vectors(self, documents: list[KnowledgeDocument]) -> None:
        from windops_backend.services.knowledge_passages import (
            document_passages,
            passage_current,
            passage_embedding_input,
            store_passage_vectors,
        )

        pending_documents = []
        for candidate in documents:
            document = await self.session.scalar(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.id == candidate.id)
                .with_for_update()
            )
            if document is None:
                continue
            passages = await document_passages(self.session, document, create_legacy=True)
            if self._embedding_is_current(document) and all(
                passage_current(passage, self.embedding_provider) for passage in passages
            ):
                continue
            pending_documents.append((document, passages))
        vectors = await embed_texts_with_controls(
            self.embedding_provider,
            [
                passage_embedding_input(document, passage)
                for document, passages in pending_documents
                for passage in passages
            ],
            settings=self.settings,
        )
        offset = 0
        for document, passages in pending_documents:
            store_passage_vectors(
                self.session,
                document,
                passages,
                vectors[offset : offset + len(passages)],
                self.embedding_provider,
            )
            offset += len(passages)
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
                        .where(self._stale_embedding_clause(), KnowledgeDocument.body != "")
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
                            .where(self._stale_embedding_clause())
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
        from windops_backend.services.knowledge_passages import retrieve_passages

        result = await retrieve_passages(
            self.session,
            self.knowledge_policy,
            self.embedding_provider,
            query_vector,
            limit=limit,
            minio_public_base=self.minio_public_base,
        )
        if turbine_id:
            from windops_backend.services.structural_closure import reviewed_case_clause

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
                    .where(reviewed_case_clause())
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

    async def assess_condition_evidence(
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
        evidence_band = (
            5
            if anomaly >= 0.9
            else 4
            if anomaly >= 0.75
            else 3
            if anomaly >= 0.6
            else 2
            if anomaly >= 0.4
            else 1
        )
        result = {
            "turbine_id": turbine_id,
            "component": component,
            "evidence_band": evidence_band,
            "condition": "attention" if evidence_band >= 3 else "stable",
            "inputs": {
                **({"primary_variable": selected_variable} if primary_variable is not None else {}),
                "anomaly_score": anomaly,
                "trend_pct": trend,
            },
            "assessment_version": "condition-evidence-2026.09",
            "boundary": "does not estimate remaining life or failure probability",
        }
        self._record_call(
            "assess_condition_evidence",
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
        # An approved, asset-scoped work plan may claim its required types from
        # the shared pool. Keep public resource visibility scoped; this internal
        # transaction reads only claim identities and retains locking/CAS guards.
        resource_table = cast(Table, Resource.__table__)
        statement = (
            select(resource_table.c.id, resource_table.c.resource_type)
            .where(
                resource_table.c.status == ResourceStatus.AVAILABLE.value,
                resource_table.c.quantity > 0,
                resource_table.c.resource_type.in_(required_types),
            )
            .order_by(resource_table.c.id)
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        resources = (await self.session.execute(statement)).all()
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
                update(resource_table)
                .where(
                    resource_table.c.id == resource.id,
                    resource_table.c.status == ResourceStatus.AVAILABLE.value,
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
        execution_plan = describe_execution_plan(profile, turbine_id)
        try:
            validate_execution_binding(selected_alternative, [execution_plan], require_bound=True)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        raw_weather_window_id = selected_alternative.get("weather_window_id")
        if not isinstance(raw_weather_window_id, str) or not raw_weather_window_id.strip():
            raise ConflictError("the approved alternative does not identify a weather window")
        weather_window_id = raw_weather_window_id.strip()
        # The approval gate and the scoped turbine lookup above authorize this
        # command. Resolve only the persisted decision's window for that turbine's
        # farm; do not require (or grant) visibility of the farm-wide collection.
        weather_table = WeatherWindow.__table__
        weather_window = (
            await self.session.execute(
                select(weather_table).where(
                    weather_table.c.id == weather_window_id,
                    weather_table.c.wind_farm_id == turbine.wind_farm_id,
                )
            )
        ).one_or_none()
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
        if plan.closure_kind == "structural_retest":
            from windops_backend.services.structural_missions import (
                require_reviewed_structural_claim,
            )

            await require_reviewed_structural_claim(
                self.session, mission_id, self.artifact_verifier, self.settings
            )
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
                "execution_plan_id": execution_plan["execution_plan_id"],
                "weather_window_id": weather_window_id,
            },
            closure_policy=(
                {
                    "kind": "structural_retest",
                    "component": profile.component,
                    "component_id": plan.safety_plan["component_id"],
                    "template_version": plan.safety_plan["template_version"],
                }
                if plan.closure_kind == "structural_retest"
                else {
                    "health_score_field": plan.closure_health_score_field,
                    "healthy_threshold": plan.healthy_threshold,
                    "component": profile.component,
                }
            ),
            assigned_team="Onshore structural measurement team"
            if plan.closure_kind == "structural_retest"
            else "East China Offshore Team A",
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
