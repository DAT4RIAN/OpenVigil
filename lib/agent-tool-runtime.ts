import { agentToolCatalog, getDefaultAgentIdForTool } from "./agent-tools/catalog";
import type {
  AgentToolArguments,
  AgentToolExecution,
  AgentToolExecutionContext,
  AgentToolExecutionRequest,
  AgentToolFailureResult,
  AgentToolName,
  AgentToolResult,
} from "./agent-tools/contracts";
import { windFarm } from "./farm-data";
import { calculateHealthScore, getTurbineStatus } from "./agent-tools/assets";
import {
  queryAlarmHistory,
  queryScada,
  queryVibration,
  queryWeather,
} from "./agent-tools/telemetry";
import {
  createDecision,
  createWorkOrder,
  queryMaintenanceHistory,
  queryWorkOrders,
  updateWorkOrder,
} from "./agent-tools/operations";
import { queryManual, querySimilarFailures } from "./agent-tools/knowledge";
import { queryCrew, querySpareParts, queryVessels } from "./agent-tools/resources";
import { AgentToolRuntimeError, isRecord } from "./agent-tools/contracts";
import { normalizeAgentToolExecutionRequest } from "./agent-tools/validation";

export { AGENT_TOOL_NAMES } from "./agent-tools/contracts";
export type { AgentToolName } from "./agent-tools/contracts";
export type { AgentToolArguments } from "./agent-tools/contracts";
export type { AgentToolExecutionStatus } from "./agent-tools/contracts";
export type { AgentToolParameter } from "./agent-tools/contracts";
export type { AgentToolCatalogEntry } from "./agent-tools/contracts";
export type { AgentToolRequest } from "./agent-tools/contracts";
export type { AgentToolTokenEstimate } from "./agent-tools/contracts";
export type { AgentToolSuccessResult } from "./agent-tools/contracts";
export type { AgentToolFailureResult } from "./agent-tools/contracts";
export type { AgentToolResult } from "./agent-tools/contracts";
export type { AgentToolExecution } from "./agent-tools/contracts";
export type { AgentToolExecutionRequest } from "./agent-tools/contracts";
export type { AgentToolExecutionContext } from "./agent-tools/contracts";
export { AgentToolRuntimeError } from "./agent-tools/contracts";
export { agentToolCatalog } from "./agent-tools/catalog";
export { isAgentToolName } from "./agent-tools/catalog";
export { getDefaultAgentIdForTool } from "./agent-tools/catalog";
export { normalizeAgentToolExecutionRequest } from "./agent-tools/validation";

const catalogByName = new Map(agentToolCatalog.map((entry) => [entry.name, entry]));

const history: AgentToolExecution[] = [];

const HISTORY_LIMIT = 100;

const BASE_EXECUTION_TIME_MS = Date.parse(windFarm.lastUpdatedAt);

let executionSequence = 0;

const handlers: Readonly<
  Record<AgentToolName, (args: AgentToolArguments, context: AgentToolExecutionContext) => unknown>
> = {
  get_turbine_status: getTurbineStatus,
  query_scada: queryScada,
  query_alarm_history: queryAlarmHistory,
  query_vibration: queryVibration,
  query_weather: queryWeather,
  query_maintenance_history: queryMaintenanceHistory,
  query_similar_failures: querySimilarFailures,
  calculate_health_score: calculateHealthScore,
  create_decision: createDecision,
  create_work_order: createWorkOrder,
  query_manual: queryManual,
  query_work_orders: queryWorkOrders,
  query_spare_parts: querySpareParts,
  query_crew: queryCrew,
  query_vessels: queryVessels,
  update_work_order: updateWorkOrder,
};

const stableValue = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(stableValue);
  if (isRecord(value)) {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stableValue(value[key])]),
    );
  }
  return value;
};

export const stableAgentToolStringify = (value: unknown): string =>
  JSON.stringify(stableValue(value));

const hashText = (value: string): string => {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
};

const estimatedTokens = (value: unknown): number => {
  const bytes = new TextEncoder().encode(stableAgentToolStringify(value)).length;
  return Math.max(1, Math.ceil(bytes / 4));
};

const failedResult = (error: unknown, dryRun: boolean): AgentToolFailureResult => {
  const runtimeError =
    error instanceof AgentToolRuntimeError
      ? error
      : new AgentToolRuntimeError(
          "TOOL_EXECUTION_FAILED",
          error instanceof Error ? error.message : "The tool execution failed.",
          500,
        );
  return Object.freeze({
    ok: false,
    dryRun,
    error: Object.freeze({
      code: runtimeError.code,
      message: runtimeError.message,
      details: runtimeError.details,
      statusCode: runtimeError.statusCode,
    }),
  });
};

/**
 * Execute one deterministic demo tool call. Runtime-memory recording remains
 * the default for backwards-compatible local demos; the D1 ledger disables it
 * and records the returned execution only after its durable write succeeds.
 */
export const executeAgentTool = (
  request: AgentToolExecutionRequest,
  context: AgentToolExecutionContext = {},
): AgentToolExecution => {
  const requestRecord = normalizeAgentToolExecutionRequest(request);
  const { tool, args } = requestRecord;
  const catalog = catalogByName.get(tool);
  if (!catalog) {
    throw new AgentToolRuntimeError("UNKNOWN_AGENT_TOOL", `Unknown agent tool: ${tool}.`, 400);
  }

  const sequence = executionSequence;
  executionSequence += 1;
  const startedAtMs = BASE_EXECUTION_TIME_MS + sequence * 1_000;
  let result: AgentToolResult;
  try {
    result = Object.freeze({
      ok: true,
      dryRun: catalog.dryRun,
      data: handlers[tool](args, context),
    });
  } catch (error) {
    result = failedResult(error, catalog.dryRun);
  }

  const inputTokens = estimatedTokens(requestRecord);
  const outputTokens = estimatedTokens(result);
  const requestFingerprint =
    context.requestFingerprint ?? hashText(stableAgentToolStringify(requestRecord));
  const correlationHash = hashText(stableAgentToolStringify(requestRecord));
  const executionOrdinal = String(sequence + 1).padStart(4, "0");
  const executionId = context.executionId ?? `AGEXEC-RUNTIME-${executionOrdinal}`;
  const execution: AgentToolExecution = Object.freeze({
    executionId,
    agentId: context.agentId ?? getDefaultAgentIdForTool(tool),
    missionId: context.missionId ?? null,
    idempotencyKey: context.idempotencyKey ?? `runtime-${executionId}`,
    requestFingerprint,
    correlationId:
      context.correlationId ?? `WOPS-${tool.toUpperCase()}-${correlationHash}-${executionOrdinal}`,
    request: requestRecord,
    result,
    startedAt: new Date(startedAtMs).toISOString(),
    completedAt: new Date(startedAtMs + catalog.deterministicLatencyMs).toISOString(),
    status: result.ok ? "succeeded" : "failed",
    latencyMs: catalog.deterministicLatencyMs,
    tokenEstimate: Object.freeze({
      input: inputTokens,
      output: outputTokens,
      total: inputTokens + outputTokens,
      method: "utf8-bytes-div-4",
    }),
    deterministic: true,
  });

  if (context.recordInMemory !== false) {
    history.push(execution);
    if (history.length > HISTORY_LIMIT) history.splice(0, history.length - HISTORY_LIMIT);
  }
  return execution;
};

/** Return an immutable snapshot of runtime-local, non-persisted tool executions. */
export const getAgentToolExecutionHistory = (): readonly AgentToolExecution[] =>
  Object.freeze([...history]);
