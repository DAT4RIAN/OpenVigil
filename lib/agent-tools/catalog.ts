import type {
  AlarmSeverity,
  AlarmStatus,
  KnowledgeDocumentType,
  ResourceAvailability,
  SubsystemKey,
  WeatherSuitability,
  WorkOrderPriority,
  WorkOrderStatus,
} from "../types";
import type { AgentToolCatalogEntry, AgentToolName, AgentToolParameter } from "./contracts";
import { SCADA_ARCHIVE_METRICS } from "../archive-data";
import { agents } from "../agent-data";
import { AGENT_TOOL_NAMES } from "./contracts";

export const subsystemValues = [
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

export const severityValues = [
  "critical",
  "major",
  "minor",
  "warning",
  "info",
] as const satisfies readonly AlarmSeverity[];

export const alarmStatusValues = [
  "active",
  "acknowledged",
  "suppressed",
  "resolved",
] as const satisfies readonly AlarmStatus[];

export const weatherSuitabilityValues = [
  "suitable",
  "conditional",
  "unsafe",
] as const satisfies readonly WeatherSuitability[];

export const priorityValues = [
  "critical",
  "high",
  "medium",
  "low",
] as const satisfies readonly WorkOrderPriority[];

export const workOrderStatusValues = [
  "draft",
  "pending-approval",
  "scheduled",
  "in-progress",
  "paused",
  "completed",
  "closed",
] as const satisfies readonly WorkOrderStatus[];

export const knowledgeDocumentTypeValues = [
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

export const resourceAvailabilityValues = [
  "available",
  "reserved",
  "assigned",
  "maintenance",
] as const satisfies readonly ResourceAvailability[];

export const sparePartStatusValues = ["in-stock", "low-stock", "out-of-stock"] as const;

export const vesselTypeValues = ["ctv", "sov", "jack-up"] as const;

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

const toolNameSet = new Set<string>(AGENT_TOOL_NAMES);

export const isAgentToolName = (value: string): value is AgentToolName => toolNameSet.has(value);

export const getDefaultAgentIdForTool = (tool: AgentToolName): string =>
  agents.find((agent) => agent.tools.includes(tool))?.id ?? "agent-operations-coordinator";
