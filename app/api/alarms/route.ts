import { alarmArchive } from "@/lib/archive-data";
import { windFarm } from "@/lib/farm-data";
import { alarms } from "@/lib/operations-data";
import {
  mutateAlarmRuntimeState,
  overlayAlarmRuntimeState,
  type AlarmMutationAction,
} from "@/db/alarm-runtime-store";
import { overlayWorkflowAlarms } from "@/lib/server-workflow-overlays";
import { getWorkerEnv } from "@/lib/worker-env";
import { productionAlarmsResponse } from "@/lib/production-domain-adapter";
import {
  getProductionBackendConfig,
  proxyProductionBackendRequest,
} from "@/lib/production-runtime";

import {
  collectionResponse,
  errorResponse,
  isNonEmptyString,
  isRecord,
  jsonResponse,
} from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionAlarmsResponse(request);
  }
  const requestedScope = new URL(request.url).searchParams.get("scope");
  if (requestedScope !== null && requestedScope !== "live" && requestedScope !== "archive") {
    return errorResponse(
      "INVALID_SCOPE",
      'The scope query parameter must be either "live" or "archive".',
    );
  }
  const scope = requestedScope ?? "live";
  const workflow = await readWorkflowForApi();
  const base = scope === "archive" ? alarmArchive : alarms;
  const runtimeOverlay = await overlayAlarmRuntimeState(getWorkerEnv().DB, base);
  const data = overlayWorkflowAlarms(runtimeOverlay, workflow.snapshot);
  return collectionResponse(data, {
    scope,
    snapshotAt: scope === "archive" ? windFarm.lastUpdatedAt : workflow.snapshot.updatedAt,
    workflowPersistence: workflow.persistence,
    workflowRevision: workflow.snapshot.revision,
    alarmMutationPersistence: getWorkerEnv().DB ? "d1" : "unavailable",
  });
}

export async function POST(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    let raw: unknown;
    try {
      raw = await request.json();
    } catch {
      return errorResponse("INVALID_JSON", "The request body must contain valid JSON.", 400);
    }
    if (
      !isRecord(raw) ||
      !isNonEmptyString(raw.alarmId) ||
      !isNonEmptyString(raw.action) ||
      !["acknowledge", "assign"].includes(raw.action) ||
      !isNonEmptyString(raw.correlationId) ||
      !isNonEmptyString(raw.idempotencyKey) ||
      !Number.isInteger(raw.expectedRevision) ||
      Number(raw.expectedRevision) < 1 ||
      (raw.reason !== undefined && !isNonEmptyString(raw.reason))
    ) {
      return errorResponse(
        "INVALID_ALARM_COMMAND",
        "alarmId, action, correlationId, idempotencyKey, and expectedRevision are required.",
        400,
      );
    }
    const action = raw.action === "assign" && raw.assignee === null ? "unassign" : raw.action;
    const headers = new Headers(request.headers);
    headers.set("content-type", "application/json");
    headers.set("idempotency-key", raw.idempotencyKey);
    headers.set("x-correlation-id", raw.correlationId);
    const upstreamRequest = new Request(request.url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        action,
        expected_revision: raw.expectedRevision,
        ...(isNonEmptyString(raw.reason) ? { reason: raw.reason.trim() } : {}),
      }),
    });
    return proxyProductionBackendRequest(
      upstreamRequest,
      `/api/v1/alarms/${encodeURIComponent(raw.alarmId.trim())}`,
    );
  }
  const database = getWorkerEnv().DB;
  if (!database) {
    return errorResponse(
      "PERSISTENCE_UNAVAILABLE",
      "Alarm mutations require the Cloudflare D1 DB binding; no local-only write was applied.",
      503,
    );
  }
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return errorResponse("INVALID_JSON", "The request body must contain valid JSON.", 400);
  }
  if (
    !isRecord(raw) ||
    !isNonEmptyString(raw.alarmId) ||
    !isNonEmptyString(raw.action) ||
    !["acknowledge", "assign"].includes(raw.action) ||
    !isNonEmptyString(raw.correlationId) ||
    !isNonEmptyString(raw.idempotencyKey)
  ) {
    return errorResponse(
      "INVALID_ALARM_MUTATION",
      "alarmId, acknowledge|assign action, correlationId, and idempotencyKey are required.",
      400,
    );
  }
  if (raw.action === "assign" && raw.assignee !== null && !isNonEmptyString(raw.assignee)) {
    return errorResponse("INVALID_ASSIGNEE", "assign requires a non-empty assignee or null.", 400);
  }
  const alarmId = String(raw.alarmId).toUpperCase();
  const alarm = alarms.find((candidate) => candidate.id === alarmId);
  if (!alarm) return errorResponse("ALARM_NOT_FOUND", `Alarm ${raw.alarmId} was not found.`, 404);
  try {
    const result = await mutateAlarmRuntimeState(database, alarm, {
      alarmId: alarm.id,
      action: raw.action as AlarmMutationAction,
      ...(raw.action === "assign" ? { assignee: raw.assignee as string | null } : {}),
      correlationId: raw.correlationId,
      idempotencyKey: raw.idempotencyKey,
    });
    return jsonResponse({
      data: result.alarm,
      meta: {
        persistence: "d1",
        replayed: result.replayed,
        audit: result.audit,
      },
    });
  } catch (error) {
    const code = error instanceof Error ? error.message : "ALARM_MUTATION_FAILED";
    const status =
      code === "IDEMPOTENCY_KEY_REUSED" ||
      code === "ALARM_REVISION_CONFLICT" ||
      /constraint|unique/i.test(code)
        ? 409
        : 400;
    return errorResponse(
      code,
      "The alarm mutation was rejected and no local-only state was applied.",
      status,
    );
  }
}
