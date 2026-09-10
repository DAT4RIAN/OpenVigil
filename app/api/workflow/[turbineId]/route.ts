import { mutateServerWorkflow, readServerWorkflow } from "@/db/runtime-store";
import {
  authorizeServerWorkflowDemoActor,
  isServerWorkflowAlternativeId,
  isSupportedServerWorkflowTurbineId,
  SERVER_WORKFLOW_TURBINE_ID,
  ServerWorkflowTransitionError,
  type ServerWorkflowAction,
  type ServerWorkflowEnvelope,
  type ServerWorkflowErrorEnvelope,
  type ServerWorkflowFieldEvidence,
  type ServerWorkflowMeta,
  type ServerWorkflowMutationRequest,
} from "@/lib/server-workflow-contract";
import { getWorkerEnv } from "@/lib/worker-env";

import { isNonEmptyString, isRecord, jsonResponse } from "../../_shared";

interface WorkflowRouteContext {
  readonly params: Promise<{ readonly turbineId: string }>;
}

const actions = new Set<ServerWorkflowAction>([
  "approve",
  "reject",
  "request-revision",
  "escalate",
  "start-work-order",
  "set-task-completion",
  "complete-work-order",
  "reset",
]);

const meta = (
  persistence: "d1" | "ephemeral",
  writable: boolean,
  replayed: boolean,
  correlationId: string | null,
): ServerWorkflowMeta => ({
  version: 1,
  turbineId: SERVER_WORKFLOW_TURBINE_ID,
  persistence,
  ephemeral: persistence === "ephemeral",
  writable,
  replayed,
  correlationId,
  identityMode: "server-demo-principal",
  authenticated: false,
});

const errorResponse = (
  code: string,
  message: string,
  status: number,
  persistence: "d1" | "ephemeral",
  writable: boolean,
  correlationId: string | null,
  details?: Readonly<Record<string, unknown>>,
): Response => {
  const body: ServerWorkflowErrorEnvelope = {
    data: null,
    error: { code, message, ...(details ? { details } : {}) },
    meta: meta(persistence, writable, false, correlationId),
  };
  return jsonResponse(body, status);
};

function parseFieldEvidence(
  value: unknown,
  verifiedBy: ServerWorkflowMutationRequest["actor"],
): ServerWorkflowFieldEvidence {
  if (!isRecord(value) || !isRecord(value.measurement)) {
    throw new ServerWorkflowTransitionError(
      "INVALID_FIELD_EVIDENCE",
      "fieldEvidence requires artifactUri, artifactSha256, measurement, and verifiedBy.",
      400,
    );
  }
  const artifactUri = isNonEmptyString(value.artifactUri) ? value.artifactUri.trim() : "";
  const artifactSha256 = isNonEmptyString(value.artifactSha256)
    ? value.artifactSha256.trim().toLowerCase()
    : "";
  const measurement = value.measurement;
  const observedAt = isNonEmptyString(measurement.observedAt) ? measurement.observedAt.trim() : "";
  if (
    value.verificationMode !== "deterministic-fixture" ||
    !/^fixture:\/\/windops-field-evidence\/\S+$/i.test(artifactUri) ||
    !/^[a-f0-9]{64}$/.test(artifactSha256) ||
    !isNonEmptyString(measurement.metric) ||
    typeof measurement.value !== "number" ||
    !Number.isFinite(measurement.value) ||
    !isNonEmptyString(measurement.unit) ||
    !observedAt ||
    Number.isNaN(Date.parse(observedAt)) ||
    !isRecord(value.verifiedBy) ||
    !isNonEmptyString(value.verifiedBy.id)
  ) {
    throw new ServerWorkflowTransitionError(
      "INVALID_FIELD_EVIDENCE",
      "Field evidence must contain a durable URI, lowercase/uppercase SHA-256, finite measurement, timestamp, and verifier identity.",
      400,
    );
  }
  return {
    verificationMode: "deterministic-fixture",
    artifactUri,
    artifactSha256,
    measurement: {
      metric: measurement.metric.trim(),
      value: measurement.value,
      unit: measurement.unit.trim(),
      observedAt: new Date(observedAt).toISOString(),
    },
    verifiedBy,
  };
}

function parseMutation(value: unknown): ServerWorkflowMutationRequest {
  if (!isRecord(value)) {
    throw new ServerWorkflowTransitionError(
      "INVALID_REQUEST",
      "The request body must be a JSON object.",
      400,
    );
  }
  if (!isNonEmptyString(value.action) || !actions.has(value.action as ServerWorkflowAction)) {
    throw new ServerWorkflowTransitionError(
      "INVALID_ACTION",
      "The workflow action is not supported.",
      400,
    );
  }
  if (
    !isRecord(value.actor) ||
    !isNonEmptyString(value.actor.id) ||
    !isNonEmptyString(value.actor.name)
  ) {
    throw new ServerWorkflowTransitionError(
      "INVALID_ACTOR",
      "actor.id and actor.name are required.",
      400,
    );
  }
  if (value.actor.role !== undefined && !isNonEmptyString(value.actor.role)) {
    throw new ServerWorkflowTransitionError(
      "INVALID_ACTOR",
      "actor.role must be a non-empty string when supplied.",
      400,
    );
  }
  if (!isNonEmptyString(value.correlationId) || !isNonEmptyString(value.idempotencyKey)) {
    throw new ServerWorkflowTransitionError(
      "INVALID_REQUEST_IDENTITY",
      "correlationId and idempotencyKey are required.",
      400,
    );
  }
  if (!Number.isInteger(value.expectedRevision) || Number(value.expectedRevision) < 0) {
    throw new ServerWorkflowTransitionError(
      "INVALID_REVISION",
      "expectedRevision must be a non-negative integer.",
      400,
    );
  }

  const action = value.action as ServerWorkflowAction;
  const actor = authorizeServerWorkflowDemoActor(value.actor.id, action);
  const isApprovalAction = ["approve", "reject", "request-revision", "escalate"].includes(action);
  if (isApprovalAction && (!isNonEmptyString(value.reason) || !isNonEmptyString(value.comment))) {
    throw new ServerWorkflowTransitionError(
      "APPROVAL_CONTEXT_REQUIRED",
      "Approval actions require non-empty reason and comment fields.",
      400,
    );
  }
  if (isApprovalAction && !isServerWorkflowAlternativeId(value.selectedAlternativeId)) {
    throw new ServerWorkflowTransitionError(
      "APPROVAL_ALTERNATIVE_REQUIRED",
      "Approval actions require selectedAlternativeId to be ALT-0823-A, ALT-0823-B, or ALT-0823-C.",
      400,
    );
  }
  if (
    action === "set-task-completion" &&
    (!isNonEmptyString(value.taskId) || typeof value.completed !== "boolean")
  ) {
    throw new ServerWorkflowTransitionError(
      "INVALID_TASK_MUTATION",
      "set-task-completion requires taskId and a boolean completed value.",
      400,
    );
  }
  const fieldEvidence =
    action === "set-task-completion" && value.completed === true
      ? parseFieldEvidence(value.fieldEvidence, actor)
      : undefined;

  return {
    action,
    actor,
    correlationId: value.correlationId,
    idempotencyKey: value.idempotencyKey,
    expectedRevision: Number(value.expectedRevision),
    ...(isServerWorkflowAlternativeId(value.selectedAlternativeId)
      ? { selectedAlternativeId: value.selectedAlternativeId }
      : {}),
    ...(isNonEmptyString(value.reason) ? { reason: value.reason } : {}),
    ...(isNonEmptyString(value.comment) ? { comment: value.comment } : {}),
    ...(isNonEmptyString(value.taskId) ? { taskId: value.taskId } : {}),
    ...(typeof value.completed === "boolean" ? { completed: value.completed } : {}),
    ...(fieldEvidence ? { fieldEvidence } : {}),
  };
}

const getDatabase = (): D1Database | undefined => getWorkerEnv().DB;

async function rejectUnsupportedTurbine(context: WorkflowRouteContext): Promise<Response | null> {
  const { turbineId } = await context.params;
  if (isSupportedServerWorkflowTurbineId(turbineId)) return null;
  return errorResponse(
    "WORKFLOW_NOT_FOUND",
    `No server workflow is available for turbine ${turbineId}.`,
    404,
    getDatabase() ? "d1" : "ephemeral",
    Boolean(getDatabase()),
    null,
  );
}

export async function GET(_request: Request, context: WorkflowRouteContext): Promise<Response> {
  const unsupported = await rejectUnsupportedTurbine(context);
  if (unsupported) return unsupported;

  try {
    const result = await readServerWorkflow(getDatabase());
    const body: ServerWorkflowEnvelope = {
      data: result.snapshot,
      meta: meta(result.persistence, result.writable, false, null),
    };
    return jsonResponse(body);
  } catch (error) {
    const workflowError =
      error instanceof ServerWorkflowTransitionError
        ? error
        : new ServerWorkflowTransitionError(
            "WORKFLOW_STORAGE_ERROR",
            "The workflow snapshot could not be loaded.",
            503,
          );
    return errorResponse(
      workflowError.code,
      workflowError.message,
      workflowError.status,
      "d1",
      true,
      null,
      workflowError.details,
    );
  }
}

export async function POST(request: Request, context: WorkflowRouteContext): Promise<Response> {
  const unsupported = await rejectUnsupportedTurbine(context);
  if (unsupported) return unsupported;

  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return errorResponse(
      "INVALID_JSON",
      "The request body must contain valid JSON.",
      400,
      getDatabase() ? "d1" : "ephemeral",
      Boolean(getDatabase()),
      null,
    );
  }

  const correlationId =
    isRecord(raw) && isNonEmptyString(raw.correlationId) ? raw.correlationId : null;
  try {
    const mutation = parseMutation(raw);
    const result = await mutateServerWorkflow(getDatabase(), mutation);
    const body: ServerWorkflowEnvelope = {
      data: result.snapshot,
      meta: meta("d1", true, result.replayed, mutation.correlationId),
    };
    return jsonResponse(body);
  } catch (error) {
    const workflowError =
      error instanceof ServerWorkflowTransitionError
        ? error
        : new ServerWorkflowTransitionError(
            "WORKFLOW_STORAGE_ERROR",
            "The workflow mutation could not be committed.",
            503,
          );
    const databaseAvailable = Boolean(getDatabase());
    return errorResponse(
      workflowError.code,
      workflowError.message,
      workflowError.status,
      databaseAvailable ? "d1" : "ephemeral",
      databaseAvailable,
      correlationId,
      workflowError.details,
    );
  }
}
