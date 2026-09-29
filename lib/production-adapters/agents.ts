import { text, number, list, record, backendCollection, collectionResponse } from "./shared.ts";

const productionAgentIds: Readonly<Record<string, string>> = {
  scada_analysis_agent: "agent-scada-analysis",
  vibration_diagnosis_agent: "agent-vibration-diagnosis",
  failure_diagnosis_agent: "agent-failure-diagnosis",
  knowledge_agent: "agent-knowledge",
  maintenance_strategy_agent: "agent-maintenance-strategy",
  review_committee: "agent-review-committee",
  human_approval_gate: "agent-human-approval-gate",
  work_order_agent: "agent-work-order",
};

function productionAgentLayer(agentKey: string): "decision" | "review" | "execution" {
  if (agentKey === "review_committee" || agentKey === "human_approval_gate") return "review";
  if (agentKey === "work_order_agent") return "execution";
  return "decision";
}

export async function productionAgentsResponse(request: Request): Promise<Response> {
  const result = await backendCollection(request, "/api/v1/agents", "agents");
  if (result instanceof Response) return result;
  const data = result.rows.map((row) => {
    const agentKey = text(row.agent_key);
    const metrics = record(row.metrics);
    const displayName = text(row.display_name, agentKey);
    const lastActiveAt = text(metrics.last_active_at) || null;
    return {
      id: productionAgentIds[agentKey] ?? `agent-${agentKey.replaceAll("_", "-")}`,
      definitionId: text(row.definition_id),
      agentKey,
      catalogVersionId: text(row.catalog_version_id),
      name: displayName,
      shortName: displayName,
      layer: productionAgentLayer(agentKey),
      role: text(row.role, agentKey),
      description: text(row.description),
      status: row.active === true ? "idle" : "offline",
      currentTask: null,
      currentMissionId: null,
      queueDepth: 0,
      model: "LiteLLM（运维方配置）",
      promptVersion: text(row.version),
      skills: list(row.skills).map(String),
      tools: list(row.tools).map(String),
      knowledgeSourceIds: [],
      metrics: {
        successRate:
          typeof metrics.success_rate === "number"
            ? Math.round(metrics.success_rate * 10_000) / 100
            : 0,
        averageLatencySeconds:
          typeof metrics.average_latency_ms === "number"
            ? Math.round(metrics.average_latency_ms) / 1_000
            : 0,
        requests24h: number(metrics.requests),
        toolCalls24h: number(metrics.tool_calls),
        tokenUsage24h: number(metrics.token_usage),
        missionsCompleted: 0,
      },
      lastActiveAt,
    };
  });
  return collectionResponse(data, result.upstream, result);
}
