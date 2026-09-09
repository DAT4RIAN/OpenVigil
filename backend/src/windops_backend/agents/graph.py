from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.agents.reasoning import (
    AlternativeBundle,
    PublicReasoningProvider,
    ReviewBundle,
)
from windops_backend.agents.state import PublicWorkflowState
from windops_backend.agents.tools import SQLToolAdapter
from windops_backend.enums import ExecutionStatus
from windops_backend.models import AgentDefinition, AgentExecution, Evidence
from windops_backend.schemas import PublicDiagnosis, PublicEvidence

NodeOperation = Callable[[PublicWorkflowState], Awaitable[dict[str, Any]]]


class WindOpsWorkflowGraph:
    """LangGraph orchestration that emits public artifacts, never model chain-of-thought."""

    def __init__(
        self,
        session: AsyncSession,
        tools: SQLToolAdapter,
        reasoning: PublicReasoningProvider,
    ) -> None:
        self.session = session
        self.tools = tools
        self.reasoning = reasoning
        self.graph = self._build()

    async def _recorded(
        self,
        state: PublicWorkflowState,
        node: str,
        agent_role: str,
        operation: NodeOperation,
    ) -> dict[str, Any]:
        started = perf_counter()
        self.tools.reset_tool_calls()
        self.reasoning.reset_usage()
        agent_definition = await self.session.scalar(
            select(AgentDefinition)
            .where(
                AgentDefinition.agent_key == agent_role,
                AgentDefinition.active.is_(True),
            )
            .order_by(AgentDefinition.version.desc())
            .limit(1)
        )
        execution = AgentExecution(
            id=str(uuid4()),
            mission_id=state["mission_id"],
            catalog_version_id=(
                agent_definition.catalog_version_id if agent_definition is not None else None
            ),
            agent_definition_id=(agent_definition.id if agent_definition is not None else None),
            node=node,
            agent_role=agent_role,
            status=ExecutionStatus.RUNNING.value,
            input_refs={
                "mission_id": state["mission_id"],
                "alarm_id": state["alarm_id"],
                "evidence_refs": [item["evidence_id"] for item in state.get("evidence", [])],
            },
        )
        self.session.add(execution)
        await self.session.flush()
        try:
            output = await operation(state)
        except Exception as exc:
            execution.status = ExecutionStatus.FAILED.value
            execution.error_code = type(exc).__name__
            execution.completed_at = datetime.now(UTC)
            execution.latency_ms = max(0, round((perf_counter() - started) * 1000))
            execution.tool_calls = self.tools.consume_tool_calls()
            usage = self.reasoning.consume_usage()
            execution.provider = str(usage.get("provider", "sqlalchemy"))
            execution.model = usage.get("model")
            execution.token_usage = usage.get(
                "token_usage",
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "source": "not_applicable",
                },
            )
            execution.public_output = {
                "failure": {
                    "node": node,
                    "error_code": type(exc).__name__,
                    "message": "Public node execution failed; inspect secured provider logs.",
                }
            }
            exc.__dict__["windops_public_context"] = {
                "node": node,
                "agent_role": agent_role,
                "catalog_version_id": execution.catalog_version_id,
                "agent_definition_id": execution.agent_definition_id,
                "input_refs": execution.input_refs,
                "public_output": execution.public_output,
                "tool_calls": execution.tool_calls,
                "latency_ms": execution.latency_ms,
                "provider": execution.provider,
                "model": execution.model,
                "token_usage": execution.token_usage,
                "error_code": execution.error_code,
            }
            await self.session.flush()
            raise
        execution.status = ExecutionStatus.SUCCEEDED.value
        execution.public_output = output
        execution.completed_at = datetime.now(UTC)
        execution.latency_ms = max(0, round((perf_counter() - started) * 1000))
        execution.tool_calls = self.tools.consume_tool_calls()
        usage = self.reasoning.consume_usage()
        execution.provider = str(usage.get("provider", "sqlalchemy"))
        execution.model = usage.get("model")
        execution.token_usage = usage.get(
            "token_usage",
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "source": "not_applicable",
            },
        )
        await self.session.flush()
        return output

    async def _persist_evidence(
        self,
        state: PublicWorkflowState,
        draft: dict[str, Any],
        *,
        citation_uri: str | None = None,
        retrieval_method: str | None = None,
    ) -> dict[str, Any]:
        source_key = str(draft["evidence_id"])
        evidence_id = f"EVD-{state['mission_id']}-{source_key}"
        entity = await self.session.get(Evidence, evidence_id)
        if entity is None:
            entity = Evidence(
                id=evidence_id,
                mission_id=state["mission_id"],
                source_key=source_key,
                evidence_type=str(draft["evidence_type"]),
                summary=str(draft["summary"]),
                source_refs=[str(value) for value in draft.get("source_refs", [])],
                metrics=draft.get("metrics", {}),
                citation_uri=citation_uri,
                retrieval_method=retrieval_method,
            )
            self.session.add(entity)
        else:
            entity.evidence_type = str(draft["evidence_type"])
            entity.summary = str(draft["summary"])
            entity.source_refs = [str(value) for value in draft.get("source_refs", [])]
            entity.metrics = draft.get("metrics", {})
            entity.citation_uri = citation_uri
            entity.retrieval_method = retrieval_method
            entity.created_at = datetime.now(UTC)
        await self.session.flush()
        return {**draft, "evidence_id": entity.id}

    async def scada(self, state: PublicWorkflowState) -> dict[str, Any]:
        async def operation(current: PublicWorkflowState) -> dict[str, Any]:
            alarms = await self.tools.query_alarm_history(current["turbine_id"], limit=100)
            alarm = next(item for item in alarms if item["alarm_id"] == current["alarm_id"])
            alarm_attributes = alarm["evidence"].get("attributes", {})
            samples = await self.tools.query_scada(
                current["turbine_id"],
                [
                    "main_bearing_vibration_rms",
                    "main_bearing_temperature",
                    "active_power",
                ],
                limit=24,
            )
            draft = PublicEvidence(
                evidence_id="SCADA-WT023",
                evidence_type="scada_anomaly",
                summary=(
                    "Main-bearing vibration crossed the threshold with +8.4 °C temperature "
                    "and 6% power-fluctuation context."
                ),
                source_refs=[alarm["alarm_id"]]
                + [str(row["source_event_id"]) for row in samples[:5]],
                metrics={
                    "vibration_rms_mm_s": float(alarm["evidence"]["value"]),
                    "threshold_mm_s": 4.5,
                    "temperature_delta_c": float(alarm_attributes.get("temperature_delta_c", 0)),
                    "power_fluctuation_pct": float(
                        alarm_attributes.get("power_fluctuation_pct", 0)
                    ),
                    "anomaly_score": float(alarm_attributes.get("anomaly_score", 0)),
                },
            ).model_dump()
            evidence = await self._persist_evidence(current, draft)
            return {"evidence": [*current.get("evidence", []), evidence]}

        return await self._recorded(state, "scada", "scada_analysis_agent", operation)

    async def vibration(self, state: PublicWorkflowState) -> dict[str, Any]:
        async def operation(current: PublicWorkflowState) -> dict[str, Any]:
            analysis = await self.tools.query_vibration(current["turbine_id"])
            draft = PublicEvidence(
                evidence_id="VIB-WT023",
                evidence_type="vibration_spectrum",
                summary="RMS is 27% above baseline with a bearing-fault spectral marker.",
                source_refs=[
                    str(row["source_event_id"]) for row in analysis.get("samples", [])[:5]
                ],
                metrics={
                    "rms_mm_s": float(analysis.get("rms_mm_s", 0)),
                    "trend_pct": float(analysis.get("trend_pct", 0)),
                    "anomaly_score": float(analysis.get("anomaly_score", 0)),
                    "spectrum_marker": str(analysis.get("spectrum_marker", "none")),
                },
            ).model_dump()
            evidence = await self._persist_evidence(current, draft)
            return {"evidence": [*current.get("evidence", []), evidence]}

        return await self._recorded(state, "vibration", "vibration_diagnosis_agent", operation)

    async def knowledge(self, state: PublicWorkflowState) -> dict[str, Any]:
        async def operation(current: PublicWorkflowState) -> dict[str, Any]:
            documents = await self.tools.query_similar_failures(
                "main bearing rising RMS temperature inspection", current["turbine_id"]
            )
            source_refs = [str(document["citation_href"]) for document in documents]
            draft = PublicEvidence(
                evidence_id="KB-MB-GW165-001",
                evidence_type="knowledge_citation",
                summary=(
                    "The controlled GW165 procedure links rising RMS and temperature to inspection."
                ),
                source_refs=source_refs,
                metrics={"documents_retrieved": float(len(documents))},
            ).model_dump()
            first_document = next(
                (item for item in documents if item["match_type"] == "knowledge_document"),
                None,
            )
            evidence = await self._persist_evidence(
                current,
                draft,
                citation_uri=(
                    str(first_document["citation_href"]) if first_document is not None else None
                ),
                retrieval_method=(
                    str(first_document["retrieval_method"]) if first_document is not None else None
                ),
            )
            return {"evidence": [*current.get("evidence", []), evidence]}

        return await self._recorded(state, "knowledge", "knowledge_agent", operation)

    async def diagnosis(self, state: PublicWorkflowState) -> dict[str, Any]:
        async def operation(current: PublicWorkflowState) -> dict[str, Any]:
            diagnosis = await self.reasoning.generate(
                PublicDiagnosis,
                "Produce the public diagnosis for WT-023 from the cited evidence.",
                {"evidence": current.get("evidence", [])},
            )
            return {
                "diagnosis": diagnosis.model_dump(),
                "workflow_status": "diagnosed",
            }

        return await self._recorded(state, "diagnosis", "failure_diagnosis_agent", operation)

    async def alternatives(self, state: PublicWorkflowState) -> dict[str, Any]:
        async def operation(current: PublicWorkflowState) -> dict[str, Any]:
            weather = await self.tools.query_weather("WF-EAST-01")
            rul = await self.tools.predict_rul(current["turbine_id"], "main_bearing")
            bundle = await self.reasoning.generate(
                AlternativeBundle,
                "Generate three public maintenance alternatives and exactly one recommendation.",
                {
                    "diagnosis": current.get("diagnosis", {}),
                    "weather": weather,
                    "rul": rul,
                },
            )
            alternatives = [item.model_dump() for item in bundle.alternatives]
            recommended = next(item for item in alternatives if item["recommended"])
            decision = await self.tools.create_decision(
                current["mission_id"],
                alternatives,
                str(recommended["alternative_id"]),
                (
                    "Engineering, safety, RUL, weather, and production impact favor "
                    "controlled derating."
                ),
                [
                    {
                        "risk": "bearing degradation accelerates before inspection",
                        "mitigation": "70% derating and 15-minute vibration monitoring",
                    },
                    {
                        "risk": "marine weather window closes",
                        "mitigation": "reserve the first suitable vessel window",
                    },
                ],
            )
            return {"alternatives": alternatives, "decision_id": decision["decision_id"]}

        return await self._recorded(state, "alternatives", "maintenance_strategy_agent", operation)

    async def reviews(self, state: PublicWorkflowState) -> dict[str, Any]:
        async def operation(current: PublicWorkflowState) -> dict[str, Any]:
            turbine_status = await self.tools.get_turbine_status(current["turbine_id"])
            resources = turbine_status["maintenance_resources"]
            weather = await self.tools.query_weather("WF-EAST-01")
            bundle = await self.reasoning.generate(
                ReviewBundle,
                "Publish engineering, safety, economic, resource, and compliance reviews.",
                {
                    "diagnosis": current.get("diagnosis", {}),
                    "alternatives": current.get("alternatives", []),
                    "resources": resources,
                    "weather": weather,
                },
            )
            return {"reviews": [review.model_dump() for review in bundle.reviews]}

        return await self._recorded(state, "reviews", "review_committee", operation)

    async def hitl(self, state: PublicWorkflowState) -> dict[str, Any]:
        async def operation(current: PublicWorkflowState) -> dict[str, Any]:
            del current
            return {
                "requires_human_approval": True,
                "approved": False,
                "workflow_status": "under_review",
            }

        return await self._recorded(state, "hitl", "human_approval_gate", operation)

    async def workorder(self, state: PublicWorkflowState) -> dict[str, Any]:
        async def operation(current: PublicWorkflowState) -> dict[str, Any]:
            approval_id = current.get("approval_id")
            if not approval_id:
                raise ValueError("approval_id is required at the work-order node")
            work_order = await self.tools.create_work_order(
                current["mission_id"], approval_id, current["turbine_id"]
            )
            return {
                "work_order_id": work_order["work_order_id"],
                "workflow_status": "executing",
                "requires_human_approval": False,
                "approved": True,
                "resource_reservation_ids": work_order["resource_reservation_ids"],
            }

        return await self._recorded(state, "workorder", "work_order_agent", operation)

    def _build(
        self,
    ) -> CompiledStateGraph[PublicWorkflowState, None, PublicWorkflowState, PublicWorkflowState]:
        builder = StateGraph(PublicWorkflowState)
        builder.add_node("scada", self.scada)
        builder.add_node("vibration", self.vibration)
        builder.add_node("knowledge", self.knowledge)
        builder.add_node("diagnosis", self.diagnosis)
        builder.add_node("alternatives", self.alternatives)
        builder.add_node("reviews", self.reviews)
        builder.add_node("hitl", self.hitl)
        builder.add_node("workorder", self.workorder)
        builder.add_conditional_edges(
            START,
            lambda state: "workorder" if state.get("resume_from") == "workorder" else "scada",
            {"scada": "scada", "workorder": "workorder"},
        )
        builder.add_edge("scada", "vibration")
        builder.add_edge("vibration", "knowledge")
        builder.add_edge("knowledge", "diagnosis")
        builder.add_edge("diagnosis", "alternatives")
        builder.add_edge("alternatives", "reviews")
        builder.add_edge("reviews", "hitl")
        builder.add_conditional_edges(
            "hitl",
            lambda state: "workorder" if state.get("approved") else "end",
            {"workorder": "workorder", "end": END},
        )
        builder.add_edge("workorder", END)
        return builder.compile()

    async def invoke(self, state: PublicWorkflowState) -> PublicWorkflowState:
        return cast(PublicWorkflowState, await self.graph.ainvoke(state))
