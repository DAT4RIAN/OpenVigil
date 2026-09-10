import {
  AgentExecutionStoreError,
  executeAgentToolWithLedger,
  readAgentToolLedger,
  type AgentExecutionFilters,
  type AgentExecutionPersistence,
} from "@/db/agent-execution-store";
import {
  AGENT_TOOL_NAMES,
  AgentToolRuntimeError,
  agentToolCatalog,
  agents,
  decisions,
  getAgentToolExecutionHistory,
  getDefaultAgentIdForTool,
  historicalWorkOrders,
  isAgentToolName,
  missions,
  normalizeAgentToolExecutionRequest,
  windFarm,
  workOrders,
  type AgentToolExecution,
  type AgentToolRequest,
} from "@/lib";
import { getWorkerEnv } from "@/lib/worker-env";
import {
  getProductionBackendConfig,
  proxyProductionBackendRequest,
} from "@/lib/production-runtime";

import { jsonResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

type ApiPersistence = AgentExecutionPersistence | "unavailable";

interface ParsedPostRequest {
  readonly request: AgentToolRequest;
  readonly agentId: string;
  readonly missionId: string | null;
  readonly idempotencyKey?: string;
  readonly persist: boolean;
}

const POST_KEYS = new Set(["tool", "args", "agentId", "missionId", "idempotencyKey", "persist"]);
const GET_KEYS = new Set(["agentId", "missionId", "status", "toolName", "limit"]);
const EXECUTION_STATUSES = new Set<AgentToolExecution["status"]>(["succeeded", "failed"]);
const IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const meta = (persistence: ApiPersistence, extra: Readonly<Record<string, unknown>> = {}) => ({
  snapshotAt: windFarm.lastUpdatedAt,
  deterministic: true,
  persisted: persistence === "d1",
  persistence,
  historyScope:
    persistence === "d1"
      ? "durable-d1"
      : persistence === "runtime-memory"
        ? "runtime-memory-demo-only"
        : "none",
  writable: Boolean(getWorkerEnv().DB),
  catalogCount: agentToolCatalog.length,
  ...extra,
});

const errorResponse = (
  code: string,
  message: string,
  status: number,
  persistence: ApiPersistence,
  details: Readonly<Record<string, unknown>> | null = null,
  data: unknown = null,
  extraMeta: Readonly<Record<string, unknown>> = {},
): Response =>
  jsonResponse(
    {
      ok: false,
      data,
      error: { code, message, details },
      meta: meta(persistence, extraMeta),
    },
    status,
  );

function validationError(
  code: string,
  message: string,
  details: Readonly<Record<string, unknown>> | null = null,
): never {
  throw new AgentExecutionStoreError(code, message, 422, details);
}

function optionalIdentifier(
  value: unknown,
  field: "agentId" | "missionId" | "idempotencyKey",
): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string" || value.trim().length === 0) {
    validationError("INVALID_EXECUTION_CONTEXT", `${field} must be a non-empty string.`, {
      field,
    });
  }
  const normalized = value.trim();
  if (normalized.length > 128) {
    validationError("INVALID_EXECUTION_CONTEXT", `${field} must contain at most 128 characters.`, {
      field,
      maximum: 128,
    });
  }
  return normalized;
}

function parsePostRequest(value: unknown): ParsedPostRequest {
  if (!isRecord(value)) {
    throw new AgentExecutionStoreError(
      "INVALID_REQUEST",
      "Request body must be an object with tool and args.",
      400,
    );
  }
  const unknownKeys = Object.keys(value).filter((key) => !POST_KEYS.has(key));
  if (unknownKeys.length > 0) {
    validationError("INVALID_EXECUTION_CONTEXT", "Unknown top-level request field(s).", {
      unknownKeys,
    });
  }
  if (value.persist !== undefined && typeof value.persist !== "boolean") {
    validationError("INVALID_EXECUTION_CONTEXT", "persist must be a boolean when supplied.", {
      field: "persist",
    });
  }

  const request = normalizeAgentToolExecutionRequest({
    tool: typeof value.tool === "string" ? value.tool.trim() : String(value.tool),
    args: value.args,
  });
  const requestedAgentId = optionalIdentifier(value.agentId, "agentId")?.toLowerCase();
  const agentId = requestedAgentId ?? getDefaultAgentIdForTool(request.tool);
  const agent = agents.find((candidate) => candidate.id === agentId);
  if (!agent) {
    validationError("AGENT_NOT_FOUND", `Agent ${agentId} was not found.`, { agentId });
  }
  if (!agent.tools.includes(request.tool)) {
    validationError(
      "AGENT_TOOL_NOT_ALLOWED",
      `Agent ${agentId} does not declare tool ${request.tool}.`,
      { agentId, toolName: request.tool },
    );
  }

  const explicitMissionId = optionalIdentifier(value.missionId, "missionId")?.toUpperCase();
  const argumentMissionId =
    typeof request.args.missionId === "string" ? request.args.missionId.toUpperCase() : null;
  const decisionId =
    typeof request.args.decisionId === "string" ? request.args.decisionId.toUpperCase() : null;
  const decision = decisionId ? decisions.find((candidate) => candidate.id === decisionId) : null;
  if (decisionId && !decision) {
    validationError("EXECUTION_ENTITY_NOT_FOUND", `Decision ${decisionId} was not found.`, {
      entity: "decision",
      decisionId,
    });
  }
  const workOrderId =
    typeof request.args.workOrderId === "string" ? request.args.workOrderId.toUpperCase() : null;
  const workOrder = workOrderId
    ? [...workOrders, ...historicalWorkOrders].find((candidate) => candidate.id === workOrderId)
    : null;
  if (workOrderId && !workOrder) {
    validationError("EXECUTION_ENTITY_NOT_FOUND", `Work order ${workOrderId} was not found.`, {
      entity: "work-order",
      workOrderId,
    });
  }
  const referencedMissionIds = [
    argumentMissionId,
    decision?.missionId,
    workOrder?.relatedMissionId,
  ].filter((candidate): candidate is string => Boolean(candidate));
  const uniqueReferencedMissionIds = [...new Set(referencedMissionIds)];
  if (uniqueReferencedMissionIds.length > 1) {
    validationError(
      "MISSION_CONTEXT_MISMATCH",
      "Referenced execution entities do not belong to the same mission.",
      { missionIds: uniqueReferencedMissionIds, decisionId, workOrderId },
    );
  }
  const inferredMissionId = uniqueReferencedMissionIds[0] ?? null;
  const missionId = explicitMissionId ?? inferredMissionId;
  const mission = missionId ? missions.find((candidate) => candidate.id === missionId) : undefined;
  if (missionId && !mission) {
    validationError("MISSION_NOT_FOUND", `Mission ${missionId} was not found.`, { missionId });
  }
  if (explicitMissionId && argumentMissionId && explicitMissionId !== argumentMissionId) {
    validationError("MISSION_CONTEXT_MISMATCH", "missionId does not match args.missionId.", {
      missionId: explicitMissionId,
      argumentMissionId,
    });
  }
  if (explicitMissionId && inferredMissionId && explicitMissionId !== inferredMissionId) {
    validationError(
      "MISSION_CONTEXT_MISMATCH",
      "missionId does not own the referenced decision or work order.",
      {
        missionId: explicitMissionId,
        referencedMissionId: inferredMissionId,
        decisionId,
        workOrderId,
      },
    );
  }
  const argumentTurbineId =
    typeof request.args.turbineId === "string" ? request.args.turbineId.toUpperCase() : null;
  if (mission && argumentTurbineId && mission.turbineId !== argumentTurbineId) {
    validationError("MISSION_CONTEXT_MISMATCH", "missionId does not match args.turbineId.", {
      missionId,
      missionTurbineId: mission.turbineId,
      argumentTurbineId,
    });
  }
  if (mission && workOrder && mission.turbineId !== workOrder.turbineId) {
    validationError("MISSION_CONTEXT_MISMATCH", "missionId does not own the work order turbine.", {
      missionId,
      workOrderId,
      missionTurbineId: mission.turbineId,
      workOrderTurbineId: workOrder.turbineId,
    });
  }

  const idempotencyKey = optionalIdentifier(value.idempotencyKey, "idempotencyKey");
  if (idempotencyKey && !IDEMPOTENCY_KEY.test(idempotencyKey)) {
    validationError(
      "INVALID_IDEMPOTENCY_KEY",
      "idempotencyKey may contain only letters, digits, dot, underscore, colon, slash, or hyphen.",
      { field: "idempotencyKey" },
    );
  }

  return {
    request,
    agentId,
    missionId,
    ...(idempotencyKey ? { idempotencyKey } : {}),
    persist: value.persist !== false,
  };
}

function singleQueryValue(parameters: URLSearchParams, key: string): string | null {
  const values = parameters.getAll(key);
  if (values.length > 1) {
    validationError("INVALID_FILTER", `${key} may be supplied only once.`, { field: key });
  }
  return values[0]?.trim() || null;
}

function parseFilters(request: Request): AgentExecutionFilters {
  const parameters = new URL(request.url).searchParams;
  const unknownKeys = [...parameters.keys()].filter((key) => !GET_KEYS.has(key));
  if (unknownKeys.length > 0) {
    validationError("INVALID_FILTER", "Unknown Agent Tool ledger filter(s).", { unknownKeys });
  }

  const agentId = singleQueryValue(parameters, "agentId")?.toLowerCase();
  if (agentId && !agents.some((agent) => agent.id === agentId)) {
    validationError("AGENT_NOT_FOUND", `Agent ${agentId} was not found.`, { agentId });
  }
  const missionId = singleQueryValue(parameters, "missionId")?.toUpperCase();
  if (missionId && !missions.some((mission) => mission.id === missionId)) {
    validationError("MISSION_NOT_FOUND", `Mission ${missionId} was not found.`, { missionId });
  }
  const status = singleQueryValue(parameters, "status");
  if (status && !EXECUTION_STATUSES.has(status as AgentToolExecution["status"])) {
    validationError("INVALID_FILTER", "status must be succeeded or failed.", {
      field: "status",
      allowed: [...EXECUTION_STATUSES],
    });
  }
  const toolName = singleQueryValue(parameters, "toolName");
  if (toolName && !isAgentToolName(toolName)) {
    validationError("INVALID_FILTER", `Unknown Agent Tool: ${toolName}.`, {
      field: "toolName",
      allowed: AGENT_TOOL_NAMES,
    });
  }
  const limitValue = singleQueryValue(parameters, "limit") ?? "50";
  if (!/^\d+$/.test(limitValue)) {
    validationError("INVALID_FILTER", "limit must be an integer between 1 and 100.", {
      field: "limit",
    });
  }
  const limit = Number(limitValue);
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
    validationError("INVALID_FILTER", "limit must be an integer between 1 and 100.", {
      field: "limit",
      minimum: 1,
      maximum: 100,
    });
  }

  return {
    ...(agentId ? { agentId } : {}),
    ...(missionId ? { missionId } : {}),
    ...(status ? { status: status as AgentToolExecution["status"] } : {}),
    ...(toolName ? { toolName: toolName as AgentToolRequest["tool"] } : {}),
    limit,
  };
}

const getDatabase = (): D1Database | undefined => getWorkerEnv().DB;

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return proxyProductionBackendRequest(request, "/api/v1/agent-tools");
  }
  try {
    const filters = parseFilters(request);
    const result = await readAgentToolLedger(getDatabase(), filters);
    return jsonResponse({
      ok: true,
      data: {
        catalog: agentToolCatalog,
        executionHistory: result.executions,
      },
      error: null,
      meta: meta(result.persistence, {
        historyCount: result.executions.length,
        totalHistoryCount: result.total,
        filters,
      }),
    });
  } catch (error) {
    const ledgerError =
      error instanceof AgentExecutionStoreError
        ? error
        : new AgentExecutionStoreError(
            "AGENT_EXECUTION_STORAGE_ERROR",
            "The Agent Tool execution ledger could not be loaded.",
            503,
          );
    return errorResponse(
      ledgerError.code,
      ledgerError.message,
      ledgerError.status,
      getDatabase() ? "d1" : "runtime-memory",
      ledgerError.details,
    );
  }
}

export async function POST(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return proxyProductionBackendRequest(request, "/api/v1/agent-tools");
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse(
      "INVALID_JSON",
      "Request body must be valid JSON.",
      400,
      getDatabase() ? "d1" : "runtime-memory",
    );
  }

  const requestedRuntimeDemo = isRecord(body) && body.persist === false;
  try {
    const parsed = parsePostRequest(body);
    let workflowSnapshot;
    try {
      const workflow = await readWorkflowForApi();
      if (workflow.persistence === "d1") workflowSnapshot = workflow.snapshot;
    } catch {
      // The execution ledger may be tested or operated against a legacy D1 schema.
      // In that case execution remains valid, but no workflow overlay is claimed.
    }
    const result = await executeAgentToolWithLedger(getDatabase(), {
      ...parsed,
      ...(workflowSnapshot ? { workflowSnapshot } : {}),
    });
    const executionMeta = {
      historyCount:
        result.persistence === "runtime-memory" ? getAgentToolExecutionHistory().length : undefined,
      replayed: result.replayed,
      dryRun: result.execution.result.dryRun,
      executionId: result.execution.executionId,
    };

    if (!result.execution.result.ok) {
      return errorResponse(
        result.execution.result.error.code,
        result.execution.result.error.message,
        result.execution.result.error.statusCode,
        result.persistence,
        result.execution.result.error.details,
        { execution: result.execution },
        executionMeta,
      );
    }

    return jsonResponse({
      ok: true,
      data: { execution: result.execution },
      error: null,
      meta: meta(result.persistence, executionMeta),
    });
  } catch (error) {
    const executionError =
      error instanceof AgentExecutionStoreError || error instanceof AgentToolRuntimeError
        ? error
        : new AgentExecutionStoreError(
            "AGENT_TOOL_RUNTIME_ERROR",
            error instanceof Error ? error.message : "The Agent Tool runtime failed.",
            500,
          );
    const status =
      executionError instanceof AgentExecutionStoreError
        ? executionError.status
        : executionError.statusCode;
    const persistence: ApiPersistence = requestedRuntimeDemo
      ? "runtime-memory"
      : getDatabase()
        ? "d1"
        : "unavailable";
    return errorResponse(
      executionError.code,
      executionError.message,
      status,
      persistence,
      executionError.details,
      null,
      {
        historyCount: getAgentToolExecutionHistory().length,
      },
    );
  }
}
