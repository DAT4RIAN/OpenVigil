import type { AgentToolArguments, AgentToolName } from "./agent-tool-runtime";
import type { Agent, Mission } from "./types";

export interface AgentToolPreviewRequest {
  readonly tool: AgentToolName;
  readonly args: AgentToolArguments;
}

const safeToolArguments: Readonly<Partial<Record<AgentToolName, AgentToolArguments>>> = {
  get_turbine_status: { turbineId: "WT-023" },
  query_scada: { turbineId: "WT-023", limit: 8 },
  query_alarm_history: { turbineId: "WT-023", limit: 8 },
  query_vibration: { turbineId: "WT-023", limit: 8 },
  query_weather: { farmId: "WF-EAST-CHINA-01", limit: 3 },
  query_maintenance_history: { turbineId: "WT-023", limit: 8 },
  query_similar_failures: { turbineId: "WT-023", subsystem: "main-bearing", limit: 3 },
  calculate_health_score: { turbineId: "WT-023" },
  query_manual: { turbineId: "WT-023", limit: 5 },
  query_work_orders: { turbineId: "WT-023", limit: 5 },
  query_spare_parts: { workOrderId: "WO-20260823-017", limit: 5 },
  query_crew: { workOrderId: "WO-20260823-017", limit: 5 },
  query_vessels: { workOrderId: "WO-20260823-017", limit: 5 },
};

/**
 * Chooses the first declared read-only preview for one Agent. Mutation tools are
 * intentionally absent so opening a profile can never draft or change work.
 */
export function buildAgentToolPreviewRequest(
  agent: Agent,
  mission: Pick<Mission, "turbineId"> | null,
): AgentToolPreviewRequest | null {
  const turbineId = mission?.turbineId ?? "WT-023";
  for (const declaredTool of agent.tools) {
    const tool = declaredTool as AgentToolName;
    const args = safeToolArguments[tool];
    if (!args) continue;
    return {
      tool,
      args: Object.hasOwn(args, "turbineId") ? { ...args, turbineId } : args,
    };
  }
  return null;
}
