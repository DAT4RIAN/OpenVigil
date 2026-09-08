import {
  SCADA_ARCHIVE_METRICS,
  alarmArchive,
  failureCases,
  historicalWorkOrders,
  queryScadaMeasurements,
} from "./archive-data";
import { agents } from "./agent-data";
import { turbines, windFarm } from "./farm-data";
import { knowledgeDocuments } from "./knowledge-data";
import { alarms, decisions, missions, workOrders } from "./operations-data";
import { maintenanceCrews, serviceVessels, spareParts } from "./resource-data";
import { scadaSeries, subsystemHealth, weatherWindows } from "./telemetry-data";
import type {
  AlarmSeverity,
  AlarmStatus,
  KnowledgeDocumentType,
  ResourceAvailability,
  ScadaMetric,
  SubsystemKey,
  WeatherSuitability,
  WorkOrderPriority,
  WorkOrderStatus,
} from "./types";

export const AGENT_TOOL_NAMES = [
  "get_turbine_status",
  "query_scada",
  "query_alarm_history",
  "query_vibration",
  "query_weather",
  "query_maintenance_history",
  "query_similar_failures",
  "calculate_health_score",
  "predict_rul",
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

const subsystemValues = [
  "blades",
  "hub",
  "main-shaft",
  "main-bearing",
  "gearbox",
  "generator",
  "converter",
  "yaw",
  "pitch",
  "tower",
  "foundation",
  "electrical",
] as const satisfies readonly SubsystemKey[];

const severityValues = [
  "critical",
  "major",
  "minor",
  "warning",
  "info",
] as const satisfies readonly AlarmSeverity[];

const alarmStatusValues = [
  "active",
  "acknowledged",
  "suppressed",
  "resolved",
] as const satisfies readonly AlarmStatus[];

const weatherSuitabilityValues = [
  "suitable",
  "conditional",
  "unsafe",
] as const satisfies readonly WeatherSuitability[];

const priorityValues = [
  "critical",
  "high",
  "medium",
  "low",
] as const satisfies readonly WorkOrderPriority[];

const workOrderStatusValues = [
  "draft",
  "pending-approval",
  "scheduled",
  "in-progress",
  "paused",
  "completed",
  "closed",
] as const satisfies readonly WorkOrderStatus[];

const knowledgeDocumentTypeValues = [
  "equipment-manual",
  "maintenance-procedure",
  "incident-case",
  "failure-case",
  "technical-standard",
  "manufacturer-bulletin",
  "historical-work-order",
  "inspection-report",
  "scada-analysis-report",
] as const satisfies readonly KnowledgeDocumentType[];

const resourceAvailabilityValues = [
  "available",
  "reserved",
  "assigned",
  "maintenance",
] as const satisfies readonly ResourceAvailability[];

const sparePartStatusValues = ["in-stock", "low-stock", "out-of-stock"] as const;
const vesselTypeValues = ["ctv", "sov", "jack-up"] as const;

const parameter = (
  name: string,
  type: AgentToolParameter["type"],
  required: boolean,
  description: string,
  options: Pick<AgentToolParameter, "values" | "minimum" | "maximum"> = {},
): AgentToolParameter => Object.freeze({ name, type, required, description, ...options });

export const agentToolCatalog: readonly AgentToolCatalogEntry[] = Object.freeze([
  {
    name: "get_turbine_status",
    description: "Read the current asset, subsystem, alarm, and mission snapshot for one turbine.",
    category: "asset",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 18,
    parameters: [parameter("turbineId", "string", true, "Canonical turbine ID, e.g. WT-023.")],
    fixtureSources: ["farm-data", "telemetry-data", "operations-data"],
  },
  {
    name: "query_scada",
    description: "Query a deterministic page from the generated SCADA measurement archive.",
    category: "telemetry",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 42,
    parameters: [
      parameter("turbineId", "string", true, "Canonical turbine ID."),
      parameter("metric", "string", false, "SCADA metric filter.", {
        values: SCADA_ARCHIVE_METRICS,
      }),
      parameter("limit", "integer", false, "Number of measurements to return.", {
        minimum: 1,
        maximum: 200,
      }),
      parameter("offset", "integer", false, "Archive offset; latest records are used by default.", {
        minimum: 0,
      }),
    ],
    fixtureSources: ["archive-data"],
  },
  {
    name: "query_alarm_history",
    description: "Read live and resolved alarm history for a turbine.",
    category: "operations",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 31,
    parameters: [
      parameter("turbineId", "string", true, "Canonical turbine ID."),
      parameter("subsystem", "string", false, "Subsystem filter.", { values: subsystemValues }),
      parameter("severity", "string", false, "Alarm severity filter.", { values: severityValues }),
      parameter("status", "string", false, "Alarm status filter.", {
        values: alarmStatusValues,
      }),
      parameter("limit", "integer", false, "Maximum alarm rows.", { minimum: 1, maximum: 100 }),
    ],
    fixtureSources: ["operations-data", "archive-data"],
  },
  {
    name: "query_vibration",
    description: "Read main-bearing vibration RMS measurements and their configured thresholds.",
    category: "telemetry",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 47,
    parameters: [
      parameter("turbineId", "string", true, "Canonical turbine ID."),
      parameter("limit", "integer", false, "Number of recent RMS measurements.", {
        minimum: 2,
        maximum: 128,
      }),
    ],
    fixtureSources: ["telemetry-data", "archive-data"],
  },
  {
    name: "query_weather",
    description: "Read deterministic marine weather access windows for a wind farm.",
    category: "weather",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 23,
    parameters: [
      parameter("farmId", "string", true, "Canonical wind-farm ID."),
      parameter("suitability", "string", false, "Suitability filter.", {
        values: weatherSuitabilityValues,
      }),
      parameter("limit", "integer", false, "Maximum weather windows.", {
        minimum: 1,
        maximum: 20,
      }),
    ],
    fixtureSources: ["telemetry-data"],
  },
  {
    name: "query_maintenance_history",
    description: "Read current and historical maintenance work orders for a turbine.",
    category: "operations",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 36,
    parameters: [
      parameter("turbineId", "string", true, "Canonical turbine ID."),
      parameter("limit", "integer", false, "Maximum maintenance records.", {
        minimum: 1,
        maximum: 100,
      }),
    ],
    fixtureSources: ["operations-data", "archive-data"],
  },
  {
    name: "query_similar_failures",
    description: "Rank closed-loop historical failure cases by deterministic fixture similarity.",
    category: "knowledge",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 54,
    parameters: [
      parameter("turbineId", "string", true, "Canonical turbine ID."),
      parameter("subsystem", "string", false, "Target subsystem.", { values: subsystemValues }),
      parameter("limit", "integer", false, "Maximum similar cases.", {
        minimum: 1,
        maximum: 20,
      }),
    ],
    fixtureSources: ["archive-data", "telemetry-data"],
  },
  {
    name: "calculate_health_score",
    description:
      "Calculate a reproducible asset or subsystem health score from snapshot penalties.",
    category: "prediction",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 28,
    parameters: [
      parameter("turbineId", "string", true, "Canonical turbine ID."),
      parameter("subsystem", "string", false, "Optional subsystem scope.", {
        values: subsystemValues,
      }),
    ],
    fixtureSources: ["farm-data", "telemetry-data"],
  },
  {
    name: "predict_rul",
    description: "Read the fixture-backed remaining-useful-life estimate for a turbine subsystem.",
    category: "prediction",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 61,
    parameters: [
      parameter("turbineId", "string", true, "Canonical turbine ID."),
      parameter("subsystem", "string", true, "Subsystem to assess.", {
        values: subsystemValues,
      }),
    ],
    fixtureSources: ["telemetry-data"],
  },
  {
    name: "create_decision",
    description: "Generate a non-persisted decision draft from an existing mission.",
    category: "action",
    readOnly: false,
    dryRun: true,
    deterministicLatencyMs: 39,
    parameters: [
      parameter("missionId", "string", true, "Existing mission ID."),
      parameter("recommendedAction", "string", false, "Optional draft action override."),
      parameter("dryRun", "boolean", false, "Must be true when supplied."),
    ],
    fixtureSources: ["operations-data"],
  },
  {
    name: "create_work_order",
    description: "Generate a non-persisted work-order draft linked to a mission and decision.",
    category: "action",
    readOnly: false,
    dryRun: true,
    deterministicLatencyMs: 44,
    parameters: [
      parameter("missionId", "string", true, "Existing mission ID."),
      parameter("decisionId", "string", false, "Existing decision ID; inferred when omitted."),
      parameter("priority", "string", false, "Draft work-order priority.", {
        values: priorityValues,
      }),
      parameter("dryRun", "boolean", false, "Must be true when supplied."),
    ],
    fixtureSources: ["operations-data"],
  },
  {
    name: "query_manual",
    description:
      "Search citation-ready equipment manuals, procedures, standards, and reports by deterministic metadata relevance.",
    category: "knowledge",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 34,
    parameters: [
      parameter("query", "string", false, "Search phrase or source identifier."),
      parameter("documentId", "string", false, "Exact knowledge document ID."),
      parameter("turbineId", "string", false, "Optional related turbine scope."),
      parameter("type", "string", false, "Knowledge document type filter.", {
        values: knowledgeDocumentTypeValues,
      }),
      parameter("limit", "integer", false, "Maximum matching documents.", {
        minimum: 1,
        maximum: 20,
      }),
    ],
    fixtureSources: ["knowledge-data"],
  },
  {
    name: "query_work_orders",
    description: "Query live or archived work orders using canonical asset and workflow filters.",
    category: "operations",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 33,
    parameters: [
      parameter("workOrderId", "string", false, "Exact work-order ID."),
      parameter("turbineId", "string", false, "Canonical turbine ID."),
      parameter("status", "string", false, "Work-order status filter.", {
        values: workOrderStatusValues,
      }),
      parameter("priority", "string", false, "Work-order priority filter.", {
        values: priorityValues,
      }),
      parameter("includeHistorical", "boolean", false, "Include the 30-row archive."),
      parameter("limit", "integer", false, "Maximum work-order rows.", {
        minimum: 1,
        maximum: 100,
      }),
    ],
    fixtureSources: ["operations-data", "archive-data"],
  },
  {
    name: "query_spare_parts",
    description:
      "Query independent spare-parts inventory and reservations for an asset or work order.",
    category: "operations",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 25,
    parameters: [
      parameter("workOrderId", "string", false, "Optional linked work-order ID."),
      parameter(
        "turbineId",
        "string",
        false,
        "Optional turbine scope resolved through work orders.",
      ),
      parameter("partNumber", "string", false, "Exact part number."),
      parameter("status", "string", false, "Inventory status filter.", {
        values: sparePartStatusValues,
      }),
      parameter("limit", "integer", false, "Maximum inventory rows.", {
        minimum: 1,
        maximum: 50,
      }),
    ],
    fixtureSources: ["resource-data", "operations-data"],
  },
  {
    name: "query_crew",
    description: "Query maintenance crews, certifications, and work-order assignments.",
    category: "operations",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 27,
    parameters: [
      parameter("workOrderId", "string", false, "Optional linked work-order ID."),
      parameter(
        "turbineId",
        "string",
        false,
        "Optional turbine scope resolved through work orders.",
      ),
      parameter("availability", "string", false, "Crew availability filter.", {
        values: resourceAvailabilityValues,
      }),
      parameter("specialty", "string", false, "Case-insensitive specialty phrase."),
      parameter("limit", "integer", false, "Maximum crew rows.", {
        minimum: 1,
        maximum: 50,
      }),
    ],
    fixtureSources: ["resource-data", "operations-data"],
  },
  {
    name: "query_vessels",
    description: "Query service vessels and work-order assignments under marine constraints.",
    category: "operations",
    readOnly: true,
    dryRun: false,
    deterministicLatencyMs: 29,
    parameters: [
      parameter("workOrderId", "string", false, "Optional linked work-order ID."),
      parameter(
        "turbineId",
        "string",
        false,
        "Optional turbine scope resolved through work orders.",
      ),
      parameter("availability", "string", false, "Vessel availability filter.", {
        values: resourceAvailabilityValues,
      }),
      parameter("vesselType", "string", false, "Vessel type filter.", {
        values: vesselTypeValues,
      }),
      parameter("limit", "integer", false, "Maximum vessel rows.", {
        minimum: 1,
        maximum: 50,
      }),
    ],
    fixtureSources: ["resource-data", "operations-data"],
  },
  {
    name: "update_work_order",
    description:
      "Validate and return a non-persisted scheduling draft for an existing live work order.",
    category: "action",
    readOnly: false,
    dryRun: true,
    deterministicLatencyMs: 37,
    parameters: [
      parameter("workOrderId", "string", true, "Existing live work-order ID."),
      parameter("assignedTeam", "string", false, "Proposed assigned team."),
      parameter("plannedStart", "string", false, "Proposed ISO 8601 start time."),
      parameter("deadline", "string", false, "Proposed ISO 8601 deadline."),
      parameter("note", "string", false, "Bounded scheduling note for the draft."),
      parameter("dryRun", "boolean", false, "Must be true when supplied."),
    ],
    fixtureSources: ["operations-data"],
  },
]);

const declaredAgentToolNames = Object.freeze([...new Set(agents.flatMap((agent) => agent.tools))]);
const uncoveredDeclaredTools = declaredAgentToolNames.filter(
  (name) => !AGENT_TOOL_NAMES.includes(name as AgentToolName),
);
if (uncoveredDeclaredTools.length > 0) {
  throw new Error(
    `Agent tool catalog is missing declared tools: ${uncoveredDeclaredTools.join(", ")}`,
  );
}

const catalogByName = new Map(agentToolCatalog.map((entry) => [entry.name, entry]));
const toolNameSet = new Set<string>(AGENT_TOOL_NAMES);
const history: AgentToolExecution[] = [];
const HISTORY_LIMIT = 100;
const BASE_EXECUTION_TIME_MS = Date.parse(windFarm.lastUpdatedAt);
let executionSequence = 0;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const isAgentToolName = (value: string): value is AgentToolName => toolNameSet.has(value);

const invalidArguments = (
  tool: AgentToolName,
  message: string,
  details: Readonly<Record<string, unknown>> | null = null,
): never => {
  throw new AgentToolRuntimeError("INVALID_TOOL_ARGUMENTS", `${tool}: ${message}`, 422, details);
};

const assertOnlyKeys = (
  tool: AgentToolName,
  args: Record<string, unknown>,
  allowed: readonly string[],
): void => {
  const unknownKeys = Object.keys(args).filter((key) => !allowed.includes(key));
  if (unknownKeys.length > 0) {
    invalidArguments(tool, `unknown argument(s): ${unknownKeys.join(", ")}`, { unknownKeys });
  }
};

const stringValue = (
  tool: AgentToolName,
  args: Record<string, unknown>,
  key: string,
  required: boolean,
): string | undefined => {
  const value = args[key];
  if (value === undefined && !required) return undefined;
  if (typeof value !== "string" || value.trim().length === 0) {
    invalidArguments(tool, `${key} must be a non-empty string`, { argument: key });
  }
  return (value as string).trim();
};

const integerValue = (
  tool: AgentToolName,
  args: Record<string, unknown>,
  key: string,
  fallback: number,
  minimum: number,
  maximum: number,
): number => {
  const value = args[key];
  if (value === undefined) return fallback;
  if (!Number.isInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    invalidArguments(tool, `${key} must be an integer between ${minimum} and ${maximum}`, {
      argument: key,
      minimum,
      maximum,
    });
  }
  return value as number;
};

const booleanValue = (
  tool: AgentToolName,
  args: Record<string, unknown>,
  key: string,
  fallback: boolean,
): boolean => {
  const value = args[key];
  if (value === undefined) return fallback;
  if (typeof value !== "boolean") {
    invalidArguments(tool, `${key} must be a boolean`, { argument: key });
  }
  return value as boolean;
};

const boundedStringValue = (
  tool: AgentToolName,
  args: Record<string, unknown>,
  key: string,
  maximumLength: number,
): string | undefined => {
  const value = stringValue(tool, args, key, false);
  if (value !== undefined && value.length > maximumLength) {
    invalidArguments(tool, `${key} must contain at most ${maximumLength} characters`, {
      argument: key,
      maximumLength,
    });
  }
  return value;
};

const isoDateTimeValue = (
  tool: AgentToolName,
  args: Record<string, unknown>,
  key: string,
): string | undefined => {
  const value = stringValue(tool, args, key, false);
  if (value === undefined) return undefined;
  const hasExplicitTimezone = /(Z|[+-]\d{2}:\d{2})$/i.test(value);
  if (!hasExplicitTimezone || Number.isNaN(Date.parse(value))) {
    invalidArguments(tool, `${key} must be an ISO 8601 date-time with an explicit timezone`, {
      argument: key,
    });
  }
  return value;
};

const enumValue = <T extends string>(
  tool: AgentToolName,
  args: Record<string, unknown>,
  key: string,
  values: readonly T[],
  required = false,
): T | undefined => {
  const raw = stringValue(tool, args, key, required);
  if (raw === undefined) return undefined;
  const normalized = raw.toLowerCase();
  if (!values.includes(normalized as T)) {
    invalidArguments(tool, `${key} must be one of: ${values.join(", ")}`, {
      argument: key,
      values,
    });
  }
  return normalized as T;
};

const dryRunValue = (
  tool: "create_decision" | "create_work_order" | "update_work_order",
  args: Record<string, unknown>,
): true => {
  if (args.dryRun !== undefined && args.dryRun !== true) {
    invalidArguments(tool, "dryRun must be true; this demo runtime never persists create actions", {
      argument: "dryRun",
      acceptedValue: true,
    });
  }
  return true;
};

const normalizeArgs = (tool: AgentToolName, rawArgs: unknown): AgentToolArguments => {
  if (!isRecord(rawArgs)) {
    invalidArguments(tool, "args must be a JSON object");
  }
  const args = rawArgs as Record<string, unknown>;

  switch (tool) {
    case "get_turbine_status": {
      assertOnlyKeys(tool, args, ["turbineId"]);
      return Object.freeze({
        turbineId: stringValue(tool, args, "turbineId", true)?.toUpperCase(),
      });
    }
    case "query_scada": {
      assertOnlyKeys(tool, args, ["turbineId", "metric", "limit", "offset"]);
      const metric = enumValue(tool, args, "metric", SCADA_ARCHIVE_METRICS);
      const offset =
        args.offset === undefined ? undefined : integerValue(tool, args, "offset", 0, 0, 131_072);
      return Object.freeze({
        turbineId: stringValue(tool, args, "turbineId", true)?.toUpperCase(),
        ...(metric ? { metric } : {}),
        limit: integerValue(tool, args, "limit", 48, 1, 200),
        ...(offset === undefined ? {} : { offset }),
      });
    }
    case "query_alarm_history": {
      assertOnlyKeys(tool, args, ["turbineId", "subsystem", "severity", "status", "limit"]);
      const subsystem = enumValue(tool, args, "subsystem", subsystemValues);
      const severity = enumValue(tool, args, "severity", severityValues);
      const status = enumValue(tool, args, "status", alarmStatusValues);
      return Object.freeze({
        turbineId: stringValue(tool, args, "turbineId", true)?.toUpperCase(),
        ...(subsystem ? { subsystem } : {}),
        ...(severity ? { severity } : {}),
        ...(status ? { status } : {}),
        limit: integerValue(tool, args, "limit", 20, 1, 100),
      });
    }
    case "query_vibration": {
      assertOnlyKeys(tool, args, ["turbineId", "limit"]);
      return Object.freeze({
        turbineId: stringValue(tool, args, "turbineId", true)?.toUpperCase(),
        limit: integerValue(tool, args, "limit", 24, 2, 128),
      });
    }
    case "query_weather": {
      assertOnlyKeys(tool, args, ["farmId", "suitability", "limit"]);
      const suitability = enumValue(tool, args, "suitability", weatherSuitabilityValues);
      return Object.freeze({
        farmId: stringValue(tool, args, "farmId", true)?.toUpperCase(),
        ...(suitability ? { suitability } : {}),
        limit: integerValue(tool, args, "limit", 5, 1, 20),
      });
    }
    case "query_maintenance_history": {
      assertOnlyKeys(tool, args, ["turbineId", "limit"]);
      return Object.freeze({
        turbineId: stringValue(tool, args, "turbineId", true)?.toUpperCase(),
        limit: integerValue(tool, args, "limit", 10, 1, 100),
      });
    }
    case "query_similar_failures": {
      assertOnlyKeys(tool, args, ["turbineId", "subsystem", "limit"]);
      const subsystem = enumValue(tool, args, "subsystem", subsystemValues);
      return Object.freeze({
        turbineId: stringValue(tool, args, "turbineId", true)?.toUpperCase(),
        ...(subsystem ? { subsystem } : {}),
        limit: integerValue(tool, args, "limit", 5, 1, 20),
      });
    }
    case "calculate_health_score": {
      assertOnlyKeys(tool, args, ["turbineId", "subsystem"]);
      const subsystem = enumValue(tool, args, "subsystem", subsystemValues);
      return Object.freeze({
        turbineId: stringValue(tool, args, "turbineId", true)?.toUpperCase(),
        ...(subsystem ? { subsystem } : {}),
      });
    }
    case "predict_rul": {
      assertOnlyKeys(tool, args, ["turbineId", "subsystem"]);
      return Object.freeze({
        turbineId: stringValue(tool, args, "turbineId", true)?.toUpperCase(),
        subsystem: enumValue(tool, args, "subsystem", subsystemValues, true),
      });
    }
    case "create_decision": {
      assertOnlyKeys(tool, args, ["missionId", "recommendedAction", "dryRun"]);
      const recommendedAction = stringValue(tool, args, "recommendedAction", false);
      return Object.freeze({
        missionId: stringValue(tool, args, "missionId", true)?.toUpperCase(),
        ...(recommendedAction ? { recommendedAction } : {}),
        dryRun: dryRunValue(tool, args),
      });
    }
    case "create_work_order": {
      assertOnlyKeys(tool, args, ["missionId", "decisionId", "priority", "dryRun"]);
      const decisionId = stringValue(tool, args, "decisionId", false)?.toUpperCase();
      const priority = enumValue(tool, args, "priority", priorityValues);
      return Object.freeze({
        missionId: stringValue(tool, args, "missionId", true)?.toUpperCase(),
        ...(decisionId ? { decisionId } : {}),
        ...(priority ? { priority } : {}),
        dryRun: dryRunValue(tool, args),
      });
    }
    case "query_manual": {
      assertOnlyKeys(tool, args, ["query", "documentId", "turbineId", "type", "limit"]);
      const query = boundedStringValue(tool, args, "query", 200);
      const documentId = stringValue(tool, args, "documentId", false)?.toUpperCase();
      const turbineId = stringValue(tool, args, "turbineId", false)?.toUpperCase();
      const type = enumValue(tool, args, "type", knowledgeDocumentTypeValues);
      return Object.freeze({
        ...(query ? { query } : {}),
        ...(documentId ? { documentId } : {}),
        ...(turbineId ? { turbineId } : {}),
        ...(type ? { type } : {}),
        limit: integerValue(tool, args, "limit", 8, 1, 20),
      });
    }
    case "query_work_orders": {
      assertOnlyKeys(tool, args, [
        "workOrderId",
        "turbineId",
        "status",
        "priority",
        "includeHistorical",
        "limit",
      ]);
      const workOrderId = stringValue(tool, args, "workOrderId", false)?.toUpperCase();
      const turbineId = stringValue(tool, args, "turbineId", false)?.toUpperCase();
      const status = enumValue(tool, args, "status", workOrderStatusValues);
      const priority = enumValue(tool, args, "priority", priorityValues);
      return Object.freeze({
        ...(workOrderId ? { workOrderId } : {}),
        ...(turbineId ? { turbineId } : {}),
        ...(status ? { status } : {}),
        ...(priority ? { priority } : {}),
        includeHistorical: booleanValue(tool, args, "includeHistorical", false),
        limit: integerValue(tool, args, "limit", 20, 1, 100),
      });
    }
    case "query_spare_parts": {
      assertOnlyKeys(tool, args, ["workOrderId", "turbineId", "partNumber", "status", "limit"]);
      const workOrderId = stringValue(tool, args, "workOrderId", false)?.toUpperCase();
      const turbineId = stringValue(tool, args, "turbineId", false)?.toUpperCase();
      const partNumber = stringValue(tool, args, "partNumber", false)?.toUpperCase();
      const status = enumValue(tool, args, "status", sparePartStatusValues);
      return Object.freeze({
        ...(workOrderId ? { workOrderId } : {}),
        ...(turbineId ? { turbineId } : {}),
        ...(partNumber ? { partNumber } : {}),
        ...(status ? { status } : {}),
        limit: integerValue(tool, args, "limit", 20, 1, 50),
      });
    }
    case "query_crew": {
      assertOnlyKeys(tool, args, [
        "workOrderId",
        "turbineId",
        "availability",
        "specialty",
        "limit",
      ]);
      const workOrderId = stringValue(tool, args, "workOrderId", false)?.toUpperCase();
      const turbineId = stringValue(tool, args, "turbineId", false)?.toUpperCase();
      const availability = enumValue(tool, args, "availability", resourceAvailabilityValues);
      const specialty = boundedStringValue(tool, args, "specialty", 100)?.toLowerCase();
      return Object.freeze({
        ...(workOrderId ? { workOrderId } : {}),
        ...(turbineId ? { turbineId } : {}),
        ...(availability ? { availability } : {}),
        ...(specialty ? { specialty } : {}),
        limit: integerValue(tool, args, "limit", 20, 1, 50),
      });
    }
    case "query_vessels": {
      assertOnlyKeys(tool, args, [
        "workOrderId",
        "turbineId",
        "availability",
        "vesselType",
        "limit",
      ]);
      const workOrderId = stringValue(tool, args, "workOrderId", false)?.toUpperCase();
      const turbineId = stringValue(tool, args, "turbineId", false)?.toUpperCase();
      const availability = enumValue(tool, args, "availability", resourceAvailabilityValues);
      const vesselType = enumValue(tool, args, "vesselType", vesselTypeValues);
      return Object.freeze({
        ...(workOrderId ? { workOrderId } : {}),
        ...(turbineId ? { turbineId } : {}),
        ...(availability ? { availability } : {}),
        ...(vesselType ? { vesselType } : {}),
        limit: integerValue(tool, args, "limit", 20, 1, 50),
      });
    }
    case "update_work_order": {
      assertOnlyKeys(tool, args, [
        "workOrderId",
        "assignedTeam",
        "plannedStart",
        "deadline",
        "note",
        "dryRun",
      ]);
      const assignedTeam = boundedStringValue(tool, args, "assignedTeam", 120);
      const plannedStart = isoDateTimeValue(tool, args, "plannedStart");
      const deadline = isoDateTimeValue(tool, args, "deadline");
      const note = boundedStringValue(tool, args, "note", 500);
      if (!assignedTeam && !plannedStart && !deadline && !note) {
        invalidArguments(
          tool,
          "at least one of assignedTeam, plannedStart, deadline, or note must be provided",
        );
      }
      return Object.freeze({
        workOrderId: stringValue(tool, args, "workOrderId", true)?.toUpperCase(),
        ...(assignedTeam ? { assignedTeam } : {}),
        ...(plannedStart ? { plannedStart } : {}),
        ...(deadline ? { deadline } : {}),
        ...(note ? { note } : {}),
        dryRun: dryRunValue(tool, args),
      });
    }
  }
};

const requiredTurbine = (turbineId: string) => {
  const turbine = turbines.find((item) => item.id === turbineId);
  if (!turbine) {
    throw new AgentToolRuntimeError(
      "TURBINE_NOT_FOUND",
      `Wind turbine ${turbineId} was not found.`,
      404,
      { turbineId },
    );
  }
  return turbine;
};

const round = (value: number, precision = 2): number => {
  const factor = 10 ** precision;
  return Math.round(value * factor) / factor;
};

const aggregateNumbers = (values: readonly number[]) => ({
  minimum: values.length === 0 ? null : Math.min(...values),
  maximum: values.length === 0 ? null : Math.max(...values),
  average:
    values.length === 0
      ? null
      : round(values.reduce((sum, value) => sum + value, 0) / values.length),
});

const getTurbineStatus = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  const turbine = requiredTurbine(turbineId);
  const assetSubsystems = subsystemHealth.filter((item) => item.turbineId === turbineId);
  const activeAlarms = alarms.filter(
    (alarm) => alarm.turbineId === turbineId && alarm.status !== "resolved",
  );
  const activeMissions = missions.filter(
    (mission) => mission.turbineId === turbineId && mission.status !== "completed",
  );
  const lowestSubsystem = [...assetSubsystems].sort(
    (left, right) => left.healthScore - right.healthScore || left.id.localeCompare(right.id),
  )[0];

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    turbine,
    subsystemSummary: {
      count: assetSubsystems.length,
      degradedCount: assetSubsystems.filter(
        (item) => item.state === "degraded" || item.state === "critical",
      ).length,
      lowest: lowestSubsystem
        ? {
            subsystem: lowestSubsystem.key,
            healthScore: lowestSubsystem.healthScore,
            state: lowestSubsystem.state,
            finding: lowestSubsystem.primaryFinding,
          }
        : null,
    },
    activeAlarms: activeAlarms.map((alarm) => ({
      id: alarm.id,
      code: alarm.code,
      severity: alarm.severity,
      subsystem: alarm.subsystem,
      status: alarm.status,
      missionId: alarm.missionId,
    })),
    activeMissionIds: activeMissions.map((mission) => mission.id),
  };
};

const queryScada = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const metric = args.metric as ScadaMetric | undefined;
  const limit = args.limit as number;
  const summary = queryScadaMeasurements({ turbineId, metric, limit: 0 });
  const offset = (args.offset as number | undefined) ?? Math.max(0, summary.total - limit);
  const page = queryScadaMeasurements({ turbineId, metric, limit, offset });
  const values = page.items.map((item) => item.value);

  return {
    snapshotAt: page.snapshotAt,
    turbineId,
    metric: metric ?? null,
    page: { offset: page.offset, limit: page.limit, count: page.items.length, total: page.total },
    aggregate: {
      ...aggregateNumbers(values),
      anomalyCount: page.items.filter((item) => item.isAnomaly).length,
      badOrUncertainQualityCount: page.items.filter((item) => item.quality !== "good").length,
    },
    measurements: page.items,
  };
};

const queryAlarmHistory = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const subsystem = args.subsystem as SubsystemKey | undefined;
  const severity = args.severity as AlarmSeverity | undefined;
  const status = args.status as AlarmStatus | undefined;
  const limit = args.limit as number;
  const filtered = alarmArchive
    .filter(
      (alarm) =>
        alarm.turbineId === turbineId &&
        (!subsystem || alarm.subsystem === subsystem) &&
        (!severity || alarm.severity === severity) &&
        (!status || alarm.status === status),
    )
    .sort(
      (left, right) =>
        Date.parse(right.triggeredAt) - Date.parse(left.triggeredAt) ||
        left.id.localeCompare(right.id),
    );
  const items = filtered.slice(0, limit);

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    turbineId,
    filters: { subsystem: subsystem ?? null, severity: severity ?? null, status: status ?? null },
    total: filtered.length,
    returned: items.length,
    counts: {
      active: filtered.filter((alarm) => alarm.status === "active").length,
      acknowledged: filtered.filter((alarm) => alarm.status === "acknowledged").length,
      resolved: filtered.filter((alarm) => alarm.status === "resolved").length,
      criticalOrMajor: filtered.filter(
        (alarm) => alarm.severity === "critical" || alarm.severity === "major",
      ).length,
    },
    alarms: items,
  };
};

const queryVibration = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const limit = args.limit as number;
  const metric: ScadaMetric = "main-bearing-vibration-rms";
  const summary = queryScadaMeasurements({ turbineId, metric, limit: 0 });
  const page = queryScadaMeasurements({
    turbineId,
    metric,
    limit,
    offset: Math.max(0, summary.total - limit),
  });
  const configuredSeries = scadaSeries.find(
    (series) => series.turbineId === turbineId && series.metric === metric,
  );
  const first = page.items[0]?.value ?? null;
  const latest = page.items.at(-1)?.value ?? null;

  return {
    snapshotAt: page.snapshotAt,
    turbineId,
    metric,
    measurementType: "RMS time-series archive",
    unit: page.items[0]?.unit ?? configuredSeries?.unit ?? "mm/s",
    currentRms: latest,
    changeFromWindowStartPercent:
      first === null || latest === null || first === 0
        ? null
        : round(((latest - first) / first) * 100, 1),
    normalRange: configuredSeries?.normalRange ?? null,
    thresholds: configuredSeries?.thresholds ?? [],
    anomalyCount: page.items.filter((item) => item.isAnomaly).length,
    measurements: page.items,
  };
};

const queryWeather = (args: AgentToolArguments): unknown => {
  const farmId = args.farmId as string;
  if (farmId !== windFarm.id) {
    throw new AgentToolRuntimeError(
      "WIND_FARM_NOT_FOUND",
      `Wind farm ${farmId} was not found.`,
      404,
      {
        farmId,
      },
    );
  }
  const suitability = args.suitability as WeatherSuitability | undefined;
  const limit = args.limit as number;
  const matching = weatherWindows
    .filter(
      (window) => window.farmId === farmId && (!suitability || window.suitability === suitability),
    )
    .sort(
      (left, right) =>
        Date.parse(left.startsAt) - Date.parse(right.startsAt) || left.id.localeCompare(right.id),
    );

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    farmId,
    suitability: suitability ?? null,
    total: matching.length,
    recommendedWindowId: matching.find((window) => window.suitability === "suitable")?.id ?? null,
    windows: matching.slice(0, limit),
  };
};

const queryMaintenanceHistory = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const limit = args.limit as number;
  const matching = [...workOrders, ...historicalWorkOrders]
    .filter((workOrder) => workOrder.turbineId === turbineId)
    .sort(
      (left, right) =>
        Date.parse(right.updatedAt) - Date.parse(left.updatedAt) || left.id.localeCompare(right.id),
    );

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    turbineId,
    total: matching.length,
    returned: Math.min(limit, matching.length),
    records: matching.slice(0, limit).map((workOrder) => ({
      id: workOrder.id,
      issue: workOrder.issue,
      status: workOrder.status,
      priority: workOrder.priority,
      plannedStart: workOrder.plannedStart,
      deadline: workOrder.deadline,
      updatedAt: workOrder.updatedAt,
      relatedMissionId: workOrder.relatedMissionId,
      decisionId: workOrder.decisionId,
      tasksCompleted: workOrder.tasks.filter((task) => task.completed).length,
      taskCount: workOrder.tasks.length,
    })),
  };
};

const querySimilarFailures = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const requestedSubsystem = args.subsystem as SubsystemKey | undefined;
  const inferredSubsystem = [...subsystemHealth]
    .filter((item) => item.turbineId === turbineId)
    .sort(
      (left, right) => left.healthScore - right.healthScore || left.id.localeCompare(right.id),
    )[0]?.key;
  const subsystem = requestedSubsystem ?? inferredSubsystem ?? "main-bearing";
  const limit = args.limit as number;
  const ranked = failureCases
    .map((failure) => {
      const subsystemMatch = failure.subsystem === subsystem;
      const sameTurbine = failure.turbineId === turbineId;
      const highRiskMatch = failure.severity === "high" || failure.severity === "critical";
      const similarityScore = round(
        Math.min(
          0.99,
          0.51 +
            (subsystemMatch ? 0.34 : 0) +
            (sameTurbine ? 0.06 : 0) +
            (highRiskMatch ? 0.04 : 0),
        ),
        2,
      );
      return { failure, similarityScore, subsystemMatch, sameTurbine };
    })
    .sort(
      (left, right) =>
        right.similarityScore - left.similarityScore ||
        Date.parse(right.failure.detectedAt) - Date.parse(left.failure.detectedAt) ||
        left.failure.id.localeCompare(right.failure.id),
    )
    .slice(0, limit);

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    turbineId,
    targetSubsystem: subsystem,
    rankingMethod: "fixture subsystem + turbine + severity weighted match",
    cases: ranked.map(({ failure, similarityScore, subsystemMatch, sameTurbine }) => ({
      ...failure,
      similarityScore,
      matchReasons: [
        ...(subsystemMatch ? ["same-subsystem"] : []),
        ...(sameTurbine ? ["same-turbine"] : []),
        ...(failure.severity === "high" || failure.severity === "critical"
          ? ["high-risk-case"]
          : []),
      ],
    })),
  };
};

const statusPenalty: Readonly<Record<string, number>> = Object.freeze({
  running: 0,
  warning: 8,
  critical: 20,
  maintenance: 12,
  offline: 30,
  "communication-lost": 25,
});

const calculateHealthScore = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  const turbine = requiredTurbine(turbineId);
  const subsystem = args.subsystem as SubsystemKey | undefined;
  const matchingSubsystems = subsystemHealth.filter((item) => item.turbineId === turbineId);

  if (subsystem) {
    const assessment = matchingSubsystems.find((item) => item.key === subsystem);
    if (!assessment) {
      throw new AgentToolRuntimeError(
        "SUBSYSTEM_HEALTH_NOT_FOUND",
        `No subsystem health snapshot exists for ${turbineId}/${subsystem}.`,
        404,
        { turbineId, subsystem },
      );
    }
    return {
      snapshotAt: assessment.assessedAt,
      turbineId,
      scope: "subsystem",
      subsystem,
      healthScore: assessment.healthScore,
      state: assessment.state,
      trend: assessment.trend,
      anomalyScore: assessment.anomalyScore,
      formula: "fixture subsystem health snapshot",
    };
  }

  const lowestSubsystemScore =
    matchingSubsystems.length > 0
      ? Math.min(...matchingSubsystems.map((item) => item.healthScore))
      : 100;
  const penalties = {
    status: statusPenalty[turbine.status] ?? 0,
    activeAlarms: Math.min(20, turbine.activeAlarmCount * 5),
    weakestSubsystem: Math.round((100 - lowestSubsystemScore) / 4),
  };
  const calculatedScore = Math.max(
    0,
    100 - penalties.status - penalties.activeAlarms - penalties.weakestSubsystem,
  );

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    turbineId,
    scope: "asset",
    healthScore: calculatedScore,
    fixtureHealthScore: turbine.healthScore,
    penalties,
    weakestSubsystemScore: matchingSubsystems.length > 0 ? lowestSubsystemScore : null,
    formula: "100 - status penalty - alarm penalty - weakest-subsystem penalty",
  };
};

const predictRul = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const subsystem = args.subsystem as SubsystemKey;
  const assessment = subsystemHealth.find(
    (item) => item.turbineId === turbineId && item.key === subsystem,
  );
  if (!assessment || assessment.remainingUsefulLifeDays === null) {
    throw new AgentToolRuntimeError(
      "RUL_ESTIMATE_NOT_FOUND",
      `No remaining-useful-life estimate exists for ${turbineId}/${subsystem}.`,
      404,
      { turbineId, subsystem },
    );
  }
  const estimate = assessment.remainingUsefulLifeDays;
  const confidencePercent = Math.max(50, Math.round(100 - assessment.anomalyScore * 15));

  return {
    snapshotAt: assessment.assessedAt,
    turbineId,
    subsystem,
    predictedRulDays: estimate,
    predictionIntervalDays: [Math.floor(estimate * 0.8), Math.ceil(estimate * 1.2)],
    confidencePercent,
    failureProbability30d: assessment.failureProbability30d,
    healthScore: assessment.healthScore,
    anomalyScore: assessment.anomalyScore,
    method: "fixture-backed subsystem health estimate; no live model inference",
  };
};

const createDecision = (args: AgentToolArguments): unknown => {
  const missionId = args.missionId as string;
  const mission = missions.find((item) => item.id === missionId);
  if (!mission) {
    throw new AgentToolRuntimeError(
      "MISSION_NOT_FOUND",
      `Mission ${missionId} was not found.`,
      404,
      {
        missionId,
      },
    );
  }
  const sourceDecision = decisions.find((decision) => decision.id === mission.decisionId);
  const recommendedAlternative = sourceDecision?.alternatives.find(
    (alternative) => alternative.id === sourceDecision.recommendedAlternativeId,
  );
  const recommendedAction =
    (args.recommendedAction as string | undefined) ??
    sourceDecision?.recommendedAction ??
    mission.nextAction;

  return {
    dryRun: true,
    persisted: false,
    draft: {
      id: `DRAFT-DECISION-${mission.id}`,
      status: "draft",
      missionId: mission.id,
      turbineId: mission.turbineId,
      incident: mission.title,
      diagnosis: mission.diagnosis,
      confidencePercent: mission.confidencePercent,
      risk: mission.severity,
      recommendedAction,
      recommendedAlternative: recommendedAlternative ?? null,
      evidenceIds: mission.evidenceIds,
      humanApprovalRequired: true,
      sourceDecisionId: sourceDecision?.id ?? null,
      generatedAt: windFarm.lastUpdatedAt,
    },
    notice: "Dry-run draft only. No decision was persisted and no approval state was changed.",
  };
};

const createWorkOrder = (args: AgentToolArguments): unknown => {
  const missionId = args.missionId as string;
  const mission = missions.find((item) => item.id === missionId);
  if (!mission) {
    throw new AgentToolRuntimeError(
      "MISSION_NOT_FOUND",
      `Mission ${missionId} was not found.`,
      404,
      {
        missionId,
      },
    );
  }
  const decisionId = (args.decisionId as string | undefined) ?? mission.decisionId;
  if (!decisionId) {
    throw new AgentToolRuntimeError(
      "DECISION_REQUIRED",
      `Mission ${missionId} has no linked decision; provide decisionId.`,
      422,
      { missionId },
    );
  }
  const decision = decisions.find((item) => item.id === decisionId);
  if (!decision) {
    throw new AgentToolRuntimeError(
      "DECISION_NOT_FOUND",
      `Decision ${decisionId} was not found.`,
      404,
      {
        decisionId,
      },
    );
  }
  if (decision.missionId !== missionId) {
    throw new AgentToolRuntimeError(
      "DECISION_MISSION_MISMATCH",
      `Decision ${decisionId} does not belong to mission ${missionId}.`,
      422,
      { missionId, decisionId, decisionMissionId: decision.missionId },
    );
  }
  const template = workOrders.find((workOrder) => workOrder.id === mission.workOrderId);
  const priority =
    (args.priority as WorkOrderPriority | undefined) ?? template?.priority ?? mission.severity;

  return {
    dryRun: true,
    persisted: false,
    draft: {
      id: `DRAFT-WO-${mission.id}`,
      status: "draft",
      turbineId: mission.turbineId,
      relatedMissionId: mission.id,
      decisionId: decision.id,
      issue: template?.issue ?? mission.title,
      description: template?.description ?? decision.recommendedAction,
      priority,
      riskLevel: decision.risk,
      assignedTeam: template?.assignedTeam ?? "Unassigned",
      plannedStart: template?.plannedStart ?? null,
      deadline: template?.deadline ?? mission.targetResolutionAt,
      estimatedDurationHours: template?.estimatedDurationHours ?? null,
      tasks: template?.tasks ?? [],
      ppeRequirements: template?.ppeRequirements ?? [],
      requiredTools: template?.requiredTools ?? [],
      spareParts: template?.spareParts ?? [],
      safetyProcedures: template?.safetyProcedures ?? [],
      generatedAt: windFarm.lastUpdatedAt,
      sourceWorkOrderId: template?.id ?? null,
    },
    notice: "Dry-run draft only. No work order was persisted, scheduled, or dispatched.",
  };
};

const allWorkOrders = Object.freeze([...workOrders, ...historicalWorkOrders]);

const requiredWorkOrder = (workOrderId: string) => {
  const workOrder = allWorkOrders.find((item) => item.id === workOrderId);
  if (!workOrder) {
    throw new AgentToolRuntimeError(
      "WORK_ORDER_NOT_FOUND",
      `Work order ${workOrderId} was not found.`,
      404,
      { workOrderId },
    );
  }
  return workOrder;
};

interface ResourceScope {
  readonly turbineId: string | null;
  readonly workOrderId: string | null;
  readonly linkedWorkOrderIds: readonly string[];
}

const resolveResourceScope = (args: AgentToolArguments): ResourceScope => {
  const turbineId = (args.turbineId as string | undefined) ?? null;
  const workOrderId = (args.workOrderId as string | undefined) ?? null;
  const turbine = turbineId ? requiredTurbine(turbineId) : null;
  const workOrder = workOrderId ? requiredWorkOrder(workOrderId) : null;

  if (turbine && workOrder && workOrder.turbineId !== turbine.id) {
    throw new AgentToolRuntimeError(
      "WORK_ORDER_TURBINE_MISMATCH",
      `Work order ${workOrder.id} does not belong to turbine ${turbine.id}.`,
      422,
      { workOrderId: workOrder.id, turbineId: turbine.id, actualTurbineId: workOrder.turbineId },
    );
  }

  const linkedWorkOrderIds = workOrder
    ? [workOrder.id]
    : turbine
      ? allWorkOrders.filter((item) => item.turbineId === turbine.id).map((item) => item.id)
      : [];

  return Object.freeze({
    turbineId: turbine?.id ?? null,
    workOrderId: workOrder?.id ?? null,
    linkedWorkOrderIds: Object.freeze(linkedWorkOrderIds),
  });
};

const queryManual = (args: AgentToolArguments): unknown => {
  const query = (args.query as string | undefined)?.toLowerCase() ?? null;
  const documentId = (args.documentId as string | undefined) ?? null;
  const turbineId = (args.turbineId as string | undefined) ?? null;
  const type = (args.type as KnowledgeDocumentType | undefined) ?? null;
  const limit = args.limit as number;
  if (turbineId) requiredTurbine(turbineId);

  if (documentId && !knowledgeDocuments.some((document) => document.id === documentId)) {
    throw new AgentToolRuntimeError(
      "KNOWLEDGE_DOCUMENT_NOT_FOUND",
      `Knowledge document ${documentId} was not found.`,
      404,
      { documentId },
    );
  }

  const queryTokens = query?.split(/\s+/u).filter(Boolean) ?? [];
  const ranked = knowledgeDocuments
    .filter(
      (document) =>
        (!documentId || document.id === documentId) &&
        (!turbineId || document.relatedTurbineIds.includes(turbineId)) &&
        (!type || document.type === type),
    )
    .map((document) => {
      const fields = {
        id: document.id.toLowerCase(),
        title: document.title.toLowerCase(),
        equipment: document.equipment.toLowerCase(),
        tags: document.tags.join(" ").toLowerCase(),
        summary: document.summary.toLowerCase(),
      };
      const searchable = Object.values(fields).join(" ");
      const matchedFields = Object.entries(fields)
        .filter(([, value]) => queryTokens.some((token) => value.includes(token)))
        .map(([field]) => field);
      const tokenHits = queryTokens.filter((token) => searchable.includes(token)).length;
      const exactPhraseMatch = query !== null && searchable.includes(query);
      const relevanceScore =
        (documentId === document.id ? 100 : 0) +
        (turbineId && document.relatedTurbineIds.includes(turbineId) ? 24 : 0) +
        (type === document.type ? 12 : 0) +
        (exactPhraseMatch ? 30 : 0) +
        tokenHits * 6;
      return {
        document,
        matchedFields,
        relevanceScore,
        queryMatched: exactPhraseMatch || tokenHits > 0,
      };
    })
    .filter(({ queryMatched }) => !query || queryMatched)
    .sort(
      (left, right) =>
        right.relevanceScore - left.relevanceScore ||
        Date.parse(right.document.updatedAt) - Date.parse(left.document.updatedAt) ||
        left.document.id.localeCompare(right.document.id),
    );

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    query,
    filters: { documentId, turbineId, type },
    rankingMethod: "deterministic metadata field matching",
    total: ranked.length,
    returned: Math.min(limit, ranked.length),
    documents: ranked.slice(0, limit).map(({ document, matchedFields, relevanceScore }) => ({
      ...document,
      relevanceScore,
      matchedFields,
      citation: {
        documentId: document.id,
        title: document.title,
        version: document.version,
        sourceType: document.type,
        pageCount: document.pageCount,
      },
    })),
  };
};

const queryWorkOrders = (args: AgentToolArguments): unknown => {
  const workOrderId = (args.workOrderId as string | undefined) ?? null;
  const turbineId = (args.turbineId as string | undefined) ?? null;
  const status = (args.status as WorkOrderStatus | undefined) ?? null;
  const priority = (args.priority as WorkOrderPriority | undefined) ?? null;
  const includeHistorical = args.includeHistorical as boolean;
  const limit = args.limit as number;
  if (turbineId) requiredTurbine(turbineId);
  if (workOrderId) requiredWorkOrder(workOrderId);

  const source = includeHistorical || workOrderId ? allWorkOrders : workOrders;
  const matching = source
    .filter(
      (workOrder) =>
        (!workOrderId || workOrder.id === workOrderId) &&
        (!turbineId || workOrder.turbineId === turbineId) &&
        (!status || workOrder.status === status) &&
        (!priority || workOrder.priority === priority),
    )
    .sort(
      (left, right) =>
        Date.parse(right.updatedAt) - Date.parse(left.updatedAt) || left.id.localeCompare(right.id),
    );

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    filters: { workOrderId, turbineId, status, priority, includeHistorical },
    total: matching.length,
    returned: Math.min(limit, matching.length),
    workOrders: matching.slice(0, limit),
  };
};

const querySpareParts = (args: AgentToolArguments): unknown => {
  const scope = resolveResourceScope(args);
  const hasScope = scope.turbineId !== null || scope.workOrderId !== null;
  const partNumber = (args.partNumber as string | undefined) ?? null;
  const status = (args.status as (typeof sparePartStatusValues)[number] | undefined) ?? null;
  const limit = args.limit as number;
  const matching = spareParts
    .filter(
      (part) =>
        (!hasScope ||
          part.reservedForWorkOrderIds.some((id) => scope.linkedWorkOrderIds.includes(id))) &&
        (!partNumber || part.partNumber.toUpperCase() === partNumber) &&
        (!status || part.status === status),
    )
    .sort(
      (left, right) =>
        left.available - right.available || left.partNumber.localeCompare(right.partNumber),
    );

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    scope,
    filters: { partNumber, status },
    total: matching.length,
    returned: Math.min(limit, matching.length),
    totals: {
      onHand: matching.reduce((sum, part) => sum + part.onHand, 0),
      reserved: matching.reduce((sum, part) => sum + part.reserved, 0),
      available: matching.reduce((sum, part) => sum + part.available, 0),
    },
    spareParts: matching.slice(0, limit),
  };
};

const queryCrew = (args: AgentToolArguments): unknown => {
  const scope = resolveResourceScope(args);
  const hasScope = scope.turbineId !== null || scope.workOrderId !== null;
  const availability = (args.availability as ResourceAvailability | undefined) ?? null;
  const specialty = (args.specialty as string | undefined) ?? null;
  const limit = args.limit as number;
  const matching = maintenanceCrews
    .filter(
      (crew) =>
        (!hasScope ||
          (crew.assignedWorkOrderId !== null &&
            scope.linkedWorkOrderIds.includes(crew.assignedWorkOrderId))) &&
        (!availability || crew.availability === availability) &&
        (!specialty || crew.specialties.some((item) => item.toLowerCase().includes(specialty))),
    )
    .sort((left, right) => left.id.localeCompare(right.id));

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    scope,
    filters: { availability, specialty },
    total: matching.length,
    returned: Math.min(limit, matching.length),
    crews: matching.slice(0, limit),
  };
};

const queryVessels = (args: AgentToolArguments): unknown => {
  const scope = resolveResourceScope(args);
  const hasScope = scope.turbineId !== null || scope.workOrderId !== null;
  const availability = (args.availability as ResourceAvailability | undefined) ?? null;
  const vesselType = (args.vesselType as (typeof vesselTypeValues)[number] | undefined) ?? null;
  const limit = args.limit as number;
  const matching = serviceVessels
    .filter(
      (vessel) =>
        (!hasScope ||
          (vessel.assignedWorkOrderId !== null &&
            scope.linkedWorkOrderIds.includes(vessel.assignedWorkOrderId))) &&
        (!availability || vessel.availability === availability) &&
        (!vesselType || vessel.vesselType.toLowerCase() === vesselType),
    )
    .sort((left, right) => left.id.localeCompare(right.id));

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    scope,
    filters: { availability, vesselType },
    total: matching.length,
    returned: Math.min(limit, matching.length),
    vessels: matching.slice(0, limit),
  };
};

const updateWorkOrder = (args: AgentToolArguments): unknown => {
  const workOrderId = args.workOrderId as string;
  const source = workOrders.find((workOrder) => workOrder.id === workOrderId);
  if (!source) {
    throw new AgentToolRuntimeError(
      "LIVE_WORK_ORDER_NOT_FOUND",
      `Live work order ${workOrderId} was not found.`,
      404,
      { workOrderId },
    );
  }

  const assignedTeam = (args.assignedTeam as string | undefined) ?? source.assignedTeam;
  const plannedStart = (args.plannedStart as string | undefined) ?? source.plannedStart;
  const deadline = (args.deadline as string | undefined) ?? source.deadline;
  const note = (args.note as string | undefined) ?? null;
  if (Date.parse(plannedStart) >= Date.parse(deadline)) {
    throw new AgentToolRuntimeError(
      "INVALID_WORK_ORDER_SCHEDULE",
      "The proposed plannedStart must be earlier than deadline.",
      422,
      { workOrderId, plannedStart, deadline },
    );
  }

  const proposedChanges = {
    ...(args.assignedTeam === undefined ? {} : { assignedTeam }),
    ...(args.plannedStart === undefined ? {} : { plannedStart }),
    ...(args.deadline === undefined ? {} : { deadline }),
    ...(note === null ? {} : { note }),
  };

  return {
    dryRun: true,
    persisted: false,
    workOrderId,
    before: {
      status: source.status,
      assignedTeam: source.assignedTeam,
      plannedStart: source.plannedStart,
      deadline: source.deadline,
      updatedAt: source.updatedAt,
    },
    proposedChanges,
    draft: {
      ...source,
      assignedTeam,
      plannedStart,
      deadline,
      status: source.status,
      schedulingNote: note,
      sourceUpdatedAt: source.updatedAt,
      generatedAt: windFarm.lastUpdatedAt,
    },
    notice:
      "Dry-run draft only. No work-order status, assignment, schedule, task, or resource record was persisted.",
  };
};

const handlers: Readonly<Record<AgentToolName, (args: AgentToolArguments) => unknown>> = {
  get_turbine_status: getTurbineStatus,
  query_scada: queryScada,
  query_alarm_history: queryAlarmHistory,
  query_vibration: queryVibration,
  query_weather: queryWeather,
  query_maintenance_history: queryMaintenanceHistory,
  query_similar_failures: querySimilarFailures,
  calculate_health_score: calculateHealthScore,
  predict_rul: predictRul,
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

const stableStringify = (value: unknown): string => JSON.stringify(stableValue(value));

const hashText = (value: string): string => {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
};

const estimatedTokens = (value: unknown): number => {
  const bytes = new TextEncoder().encode(stableStringify(value)).length;
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
 * Execute one deterministic demo tool call and append its observable record to
 * runtime-local history. Validation failures do not count as executions.
 */
export const executeAgentTool = (request: AgentToolExecutionRequest): AgentToolExecution => {
  if (typeof request.tool !== "string" || !isAgentToolName(request.tool)) {
    throw new AgentToolRuntimeError(
      "UNKNOWN_AGENT_TOOL",
      `Unknown agent tool: ${String(request.tool)}.`,
      400,
      { availableTools: AGENT_TOOL_NAMES },
    );
  }

  const tool = request.tool;
  const args = normalizeArgs(tool, request.args);
  const catalog = catalogByName.get(tool);
  if (!catalog) {
    throw new AgentToolRuntimeError("UNKNOWN_AGENT_TOOL", `Unknown agent tool: ${tool}.`, 400);
  }

  const sequence = executionSequence;
  executionSequence += 1;
  const startedAtMs = BASE_EXECUTION_TIME_MS + sequence * 1_000;
  const requestRecord: AgentToolRequest = Object.freeze({ tool, args });
  let result: AgentToolResult;
  try {
    result = Object.freeze({
      ok: true,
      dryRun: catalog.dryRun,
      data: handlers[tool](args),
    });
  } catch (error) {
    result = failedResult(error, catalog.dryRun);
  }

  const inputTokens = estimatedTokens(requestRecord);
  const outputTokens = estimatedTokens(result);
  const correlationHash = hashText(stableStringify(requestRecord));
  const execution: AgentToolExecution = Object.freeze({
    correlationId: `WOPS-${tool.toUpperCase()}-${correlationHash}-${String(sequence + 1).padStart(4, "0")}`,
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

  history.push(execution);
  if (history.length > HISTORY_LIMIT) history.splice(0, history.length - HISTORY_LIMIT);
  return execution;
};

/** Return an immutable snapshot of runtime-local, non-persisted tool executions. */
export const getAgentToolExecutionHistory = (): readonly AgentToolExecution[] =>
  Object.freeze([...history]);
