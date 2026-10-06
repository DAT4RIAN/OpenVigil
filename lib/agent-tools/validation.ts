import type {
  AgentToolArguments,
  AgentToolExecutionRequest,
  AgentToolName,
  AgentToolRequest,
} from "./contracts";
import { AGENT_TOOL_NAMES, AgentToolRuntimeError, isRecord } from "./contracts";
import { SCADA_ARCHIVE_METRICS } from "../archive-data";
import {
  alarmStatusValues,
  isAgentToolName,
  knowledgeDocumentTypeValues,
  priorityValues,
  resourceAvailabilityValues,
  severityValues,
  sparePartStatusValues,
  subsystemValues,
  vesselTypeValues,
  weatherSuitabilityValues,
  workOrderStatusValues,
} from "./catalog";

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

/** Validate and normalize one tool request without running its handler. */
export const normalizeAgentToolExecutionRequest = (
  request: AgentToolExecutionRequest,
): AgentToolRequest => {
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
  return Object.freeze({ tool, args });
};
