import type { ServerWorkflowSnapshot } from "../server-workflow-contract";

export const AGENT_TOOL_NAMES = [
  "get_turbine_status",
  "query_scada",
  "query_alarm_history",
  "query_vibration",
  "query_weather",
  "query_maintenance_history",
  "query_similar_failures",
  "calculate_health_score",
  "create_decision",
  "create_work_order",
  "query_manual",
  "query_work_orders",
  "query_spare_parts",
  "query_crew",
  "query_vessels",
  "update_work_order",
] as const;

export type AgentToolName = (typeof AGENT_TOOL_NAMES)[number];

export type AgentToolArguments = Readonly<Record<string, unknown>>;

export type AgentToolExecutionStatus = "succeeded" | "failed";

export interface AgentToolParameter {
  readonly name: string;
  readonly type: "string" | "integer" | "boolean";
  readonly required: boolean;
  readonly description: string;
  readonly values?: readonly string[];
  readonly minimum?: number;
  readonly maximum?: number;
}

export interface AgentToolCatalogEntry {
  readonly name: AgentToolName;
  readonly description: string;
  readonly category:
    "asset" | "telemetry" | "operations" | "weather" | "knowledge" | "prediction" | "action";
  readonly readOnly: boolean;
  readonly dryRun: boolean;
  readonly deterministicLatencyMs: number;
  readonly parameters: readonly AgentToolParameter[];
  readonly fixtureSources: readonly string[];
}

export interface AgentToolRequest {
  readonly tool: AgentToolName;
  readonly args: AgentToolArguments;
}

export interface AgentToolTokenEstimate {
  readonly input: number;
  readonly output: number;
  readonly total: number;
  readonly method: "utf8-bytes-div-4";
}

export interface AgentToolSuccessResult {
  readonly ok: true;
  readonly dryRun: boolean;
  readonly data: unknown;
}

export interface AgentToolFailureResult {
  readonly ok: false;
  readonly dryRun: boolean;
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly details: Readonly<Record<string, unknown>> | null;
    readonly statusCode: number;
  };
}

export type AgentToolResult = AgentToolSuccessResult | AgentToolFailureResult;

export interface AgentToolExecution {
  readonly executionId: string;
  readonly agentId: string;
  readonly missionId: string | null;
  readonly idempotencyKey: string;
  readonly requestFingerprint: string;
  readonly correlationId: string;
  readonly request: AgentToolRequest;
  readonly result: AgentToolResult;
  readonly startedAt: string;
  readonly completedAt: string;
  readonly status: AgentToolExecutionStatus;
  readonly latencyMs: number;
  readonly tokenEstimate: AgentToolTokenEstimate;
  readonly deterministic: true;
}

export interface AgentToolExecutionRequest {
  readonly tool: string;
  readonly args: unknown;
}

export interface AgentToolExecutionContext {
  readonly executionId?: string;
  readonly agentId?: string;
  readonly missionId?: string | null;
  readonly idempotencyKey?: string;
  readonly requestFingerprint?: string;
  readonly correlationId?: string;
  readonly recordInMemory?: boolean;
  readonly workflowSnapshot?: ServerWorkflowSnapshot;
}

export class AgentToolRuntimeError extends Error {
  readonly code: string;
  readonly statusCode: number;
  readonly details: Readonly<Record<string, unknown>> | null;

  constructor(
    code: string,
    message: string,
    statusCode: number,
    details: Readonly<Record<string, unknown>> | null = null,
  ) {
    super(message);
    this.name = "AgentToolRuntimeError";
    this.code = code;
    this.statusCode = statusCode;
    this.details = details;
  }
}

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
