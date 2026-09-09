import type { ApprovalAction, DecisionStatus, MissionStatus, WorkOrderStatus } from "./types";
import {
  getServerWorkflowAlternativePlan as getRuntimeAlternativePlan,
  isServerWorkflowAlternativeId as isRuntimeAlternativeId,
  SERVER_WORKFLOW_ALTERNATIVE_IDS as runtimeAlternativeIds,
  serverWorkflowAlternativePlans as runtimeAlternativePlans,
} from "./server-workflow-plans.js";

export const SERVER_WORKFLOW_TURBINE_ID = "WT-023" as const;
export const SERVER_WORKFLOW_MISSION_ID = "MISSION-2026-0823" as const;
export const SERVER_WORKFLOW_DECISION_ID = "DECISION-2026-0823" as const;
export const SERVER_WORKFLOW_WORK_ORDER_ID = "WO-20260823-017" as const;
export const SERVER_WORKFLOW_KNOWLEDGE_CASE_ID = "KB-CASE-2026-WT023-CLOSED" as const;

export type ServerWorkflowAlternativeId = "ALT-0823-A" | "ALT-0823-B" | "ALT-0823-C";

export interface ServerWorkflowAlternativePlan {
  readonly id: ServerWorkflowAlternativeId;
  readonly label: string;
  readonly title: string;
  readonly description: string;
  readonly workOrderIssue: string;
  readonly workOrderDescription: string;
  readonly assignedTeam: string;
  readonly estimatedDurationHours: number;
  readonly taskTitles: readonly [string, string, string, string, string];
  readonly requiredTools: readonly string[];
  readonly ppeRequirements: readonly string[];
  readonly safetyProcedures: readonly string[];
}

export const SERVER_WORKFLOW_ALTERNATIVE_IDS = runtimeAlternativeIds as unknown as readonly [
  "ALT-0823-A",
  "ALT-0823-B",
  "ALT-0823-C",
];

/** Server-owned execution plans for the three choices shown in Decision Center. */
export const serverWorkflowAlternativePlans = runtimeAlternativePlans as unknown as Readonly<
  Record<ServerWorkflowAlternativeId, ServerWorkflowAlternativePlan>
>;

export const isServerWorkflowAlternativeId = (
  value: unknown,
): value is ServerWorkflowAlternativeId => isRuntimeAlternativeId(value);

export const getServerWorkflowAlternativePlan = (
  value: unknown,
): ServerWorkflowAlternativePlan | null =>
  getRuntimeAlternativePlan(value) as ServerWorkflowAlternativePlan | null;

export const isSupportedServerWorkflowTurbineId = (value: string): boolean =>
  value.toUpperCase() === SERVER_WORKFLOW_TURBINE_ID;

export const serverWorkflowTaskDefinitions = serverWorkflowAlternativePlans[
  "ALT-0823-B"
].taskTitles.map((title, index) => ({
  id: `${SERVER_WORKFLOW_WORK_ORDER_ID}-TASK-${String(index + 1).padStart(2, "0")}`,
  title,
}));

const fieldEvidenceFixtures = {
  "WO-20260823-017-TASK-01": {
    artifactUri: "fixture://windops-field-evidence/WO-20260823-017/task-01-lubricant-sample.json",
    artifactSha256: "8af9d27e50471d38bc2a600dc8e8179ce23992ca95d62dc7ea6a51f7b36a9d18",
    measurement: {
      metric: "lubricant-water-content",
      value: 0.041,
      unit: "%",
      observedAt: "2026-08-13T04:10:00.000Z",
    },
  },
  "WO-20260823-017-TASK-02": {
    artifactUri: "fixture://windops-field-evidence/WO-20260823-017/task-02-vibration-spectrum.csv",
    artifactSha256: "23827aaafe219486b9ebf01eadbd4a8cf91b54f3270e5ad0ad8f044ff458bca7",
    measurement: {
      metric: "main-bearing-vibration-rms",
      value: 2.71,
      unit: "mm/s",
      observedAt: "2026-08-13T04:24:00.000Z",
    },
  },
  "WO-20260823-017-TASK-03": {
    artifactUri:
      "fixture://windops-field-evidence/WO-20260823-017/task-03-bearing-temperature.json",
    artifactSha256: "eeb24b7b2a170671a591cd54e82b1d162c925486ecda89446270f611f1112a55",
    measurement: {
      metric: "main-bearing-temperature",
      value: 61.8,
      unit: "°C",
      observedAt: "2026-08-13T04:37:00.000Z",
    },
  },
  "WO-20260823-017-TASK-04": {
    artifactUri: "fixture://windops-field-evidence/WO-20260823-017/task-04-borescope.mp4",
    artifactSha256: "7df1f7378d7ff63dd1f19ff03c28948bf2aa5c190f9b0f5d921bc5ef019894aa",
    measurement: {
      metric: "raceway-defect-width",
      value: 0.18,
      unit: "mm",
      observedAt: "2026-08-13T05:02:00.000Z",
    },
  },
  "WO-20260823-017-TASK-05": {
    artifactUri:
      "fixture://windops-field-evidence/WO-20260823-017/task-05-verification-package.zip",
    artifactSha256: "63cc7ebd4df399b52ff3545d81bb21b598736a0179bec7143215005cdb9d7381",
    measurement: {
      metric: "post-maintenance-health-score",
      value: 78,
      unit: "score",
      observedAt: "2026-08-13T05:28:00.000Z",
    },
  },
} as const;

/** Build the explicit, inspectable field fixture used by the demo completion UI. */
export function buildServerWorkflowFieldEvidence(
  taskId: string,
  verifiedBy: ServerWorkflowActor,
): ServerWorkflowFieldEvidence {
  const fixture = fieldEvidenceFixtures[taskId as keyof typeof fieldEvidenceFixtures];
  if (!fixture) {
    throw new ServerWorkflowTransitionError(
      "TASK_NOT_FOUND",
      `Task ${taskId} is not part of the WT-023 work order.`,
      404,
    );
  }
  return {
    verificationMode: "deterministic-fixture",
    ...fixture,
    measurement: { ...fixture.measurement },
    verifiedBy,
  };
}

export type ServerWorkflowAction =
  ApprovalAction | "start-work-order" | "set-task-completion" | "complete-work-order" | "reset";

export type ServerWorkflowAuditKind =
  "approval" | "execution" | "verification" | "knowledge" | "reset";

export interface ServerWorkflowActor {
  readonly id: string;
  readonly name: string;
  readonly role?: string;
}

/**
 * Server-owned identities for the local workflow demo. These are an
 * authorization allow-list, not a replacement for production SSO/RBAC. The
 * route discards caller-supplied display names and records these canonical
 * identities so the audit trail cannot be relabelled by request JSON.
 */
export const serverWorkflowDemoPrincipals = {
  "demo-duty-chief": {
    id: "demo-duty-chief",
    name: "李明远",
    role: "duty-chief-engineer",
  },
  "demo-maintenance-team": {
    id: "demo-maintenance-team",
    name: "海维二组",
    role: "maintenance-execution",
  },
  "demo-verification-engineer": {
    id: "demo-verification-engineer",
    name: "林工",
    role: "maintenance-verification",
  },
  "demo-operator": {
    id: "demo-operator",
    name: "Demo Operator",
    role: "system-demo-controller",
  },
} as const satisfies Readonly<Record<string, ServerWorkflowActor>>;

const demoPrincipalActions: Readonly<Record<string, readonly ServerWorkflowAction[]>> = {
  "demo-duty-chief": ["approve", "reject", "request-revision", "escalate"],
  "demo-maintenance-team": ["start-work-order", "set-task-completion"],
  "demo-verification-engineer": ["complete-work-order"],
  "demo-operator": ["reset"],
};

export function authorizeServerWorkflowDemoActor(
  actorId: string,
  action: ServerWorkflowAction,
): ServerWorkflowActor {
  const principal =
    serverWorkflowDemoPrincipals[actorId as keyof typeof serverWorkflowDemoPrincipals];
  const allowed = demoPrincipalActions[actorId]?.includes(action) ?? false;
  if (!principal || !allowed) {
    throw new ServerWorkflowTransitionError(
      "WORKFLOW_ACTOR_UNAUTHORIZED",
      `Demo principal ${actorId} is not authorized for ${action}.`,
      403,
      { actorId, action },
    );
  }
  return principal;
}

export interface ServerWorkflowApproval {
  readonly action: ApprovalAction;
  readonly selectedAlternativeId: ServerWorkflowAlternativeId;
  readonly actor: ServerWorkflowActor;
  readonly reason: string;
  readonly comment: string;
  readonly timestamp: string;
  readonly correlationId: string;
}

export interface ServerWorkflowTask {
  readonly id: string;
  readonly sequence: number;
  readonly title: string;
  readonly completed: boolean;
  readonly completedAt: string | null;
  readonly completedBy: string | null;
  readonly fieldEvidence: ServerWorkflowFieldEvidence | null;
}

export interface ServerWorkflowFieldMeasurement {
  readonly metric: string;
  readonly value: number;
  readonly unit: string;
  readonly observedAt: string;
}

/**
 * Structured evidence required before a field task may be marked complete.
 * The route replaces `verifiedBy` with the canonical server-owned principal,
 * so callers cannot relabel the verifier in the persisted audit record.
 */
export interface ServerWorkflowFieldEvidence {
  readonly verificationMode: "deterministic-fixture";
  readonly artifactUri: string;
  readonly artifactSha256: string;
  readonly measurement: ServerWorkflowFieldMeasurement;
  readonly verifiedBy: ServerWorkflowActor;
}

export interface ServerWorkflowAuditEvent {
  readonly id: string;
  readonly missionId: typeof SERVER_WORKFLOW_MISSION_ID;
  readonly revision: number;
  readonly eventSequence: number;
  readonly action: ServerWorkflowAction;
  readonly kind: ServerWorkflowAuditKind;
  readonly actor: ServerWorkflowActor;
  readonly correlationId: string;
  readonly idempotencyKey: string;
  readonly fromState: ServerWorkflowStateSummary;
  readonly toState: ServerWorkflowStateSummary;
  readonly detail: string;
  readonly fieldEvidence: ServerWorkflowFieldEvidence | null;
  readonly timestamp: string;
}

export interface ServerWorkflowStateSummary {
  readonly missionStatus: MissionStatus;
  readonly decisionStatus: DecisionStatus;
  readonly selectedAlternativeId: ServerWorkflowAlternativeId | null;
  readonly workOrderStatus: WorkOrderStatus;
  readonly workOrderAlternativeId: ServerWorkflowAlternativeId | null;
  readonly completedTaskCount: number;
}

export interface ServerWorkflowSnapshot {
  readonly turbineId: typeof SERVER_WORKFLOW_TURBINE_ID;
  readonly mission: {
    readonly id: typeof SERVER_WORKFLOW_MISSION_ID;
    readonly status: MissionStatus;
    readonly progressPercent: number;
  };
  readonly decision: {
    readonly id: typeof SERVER_WORKFLOW_DECISION_ID;
    readonly risk: "high";
    readonly status: DecisionStatus;
    readonly approvalRequired: true;
    readonly selectedAlternativeId: ServerWorkflowAlternativeId | null;
    readonly approval: ServerWorkflowApproval | null;
  };
  readonly workOrder: {
    readonly id: typeof SERVER_WORKFLOW_WORK_ORDER_ID;
    readonly status: WorkOrderStatus;
    readonly alternativeId: ServerWorkflowAlternativeId | null;
    readonly tasks: readonly ServerWorkflowTask[];
    readonly completedTaskCount: number;
    readonly totalTaskCount: number;
  };
  readonly health: {
    readonly turbineScore: number;
    readonly mainBearingScore: number;
  };
  readonly knowledgeCaseId: string | null;
  readonly auditEvents: readonly ServerWorkflowAuditEvent[];
  readonly revision: number;
  readonly updatedAt: string;
}

interface ServerWorkflowMutationBase {
  readonly action: ServerWorkflowAction;
  readonly actor: ServerWorkflowActor;
  readonly correlationId: string;
  readonly idempotencyKey: string;
  readonly expectedRevision: number;
}

export type ServerWorkflowMutationRequest = ServerWorkflowMutationBase & {
  readonly selectedAlternativeId?: ServerWorkflowAlternativeId;
  readonly reason?: string;
  readonly comment?: string;
  readonly taskId?: string;
  readonly completed?: boolean;
  readonly fieldEvidence?: ServerWorkflowFieldEvidence;
};

export interface ServerWorkflowMeta {
  readonly version: 1;
  readonly turbineId: typeof SERVER_WORKFLOW_TURBINE_ID;
  readonly persistence: "d1" | "ephemeral";
  readonly ephemeral: boolean;
  readonly writable: boolean;
  readonly replayed: boolean;
  readonly correlationId: string | null;
  readonly identityMode: "server-demo-principal";
  readonly authenticated: false;
}

export interface ServerWorkflowEnvelope {
  readonly data: ServerWorkflowSnapshot;
  readonly meta: ServerWorkflowMeta;
}

export interface ServerWorkflowErrorEnvelope {
  readonly data: null;
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly details?: Readonly<Record<string, unknown>>;
  };
  readonly meta: ServerWorkflowMeta;
}

export class ServerWorkflowTransitionError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: Readonly<Record<string, unknown>>;

  constructor(
    code: string,
    message: string,
    status: number,
    details?: Readonly<Record<string, unknown>>,
  ) {
    super(message);
    this.name = "ServerWorkflowTransitionError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export function requireServerWorkflowPersistence(available: boolean): asserts available {
  if (!available) {
    throw new ServerWorkflowTransitionError(
      "PERSISTENCE_UNAVAILABLE",
      "Workflow mutations require the Cloudflare D1 DB binding; the fallback snapshot is read-only.",
      503,
    );
  }
}

const INITIAL_UPDATED_AT = "2026-08-13T02:14:51+08:00";

const initialTasks = (): readonly ServerWorkflowTask[] =>
  serverWorkflowTaskDefinitions.map((task, index) => ({
    ...task,
    sequence: index + 1,
    completed: false,
    completedAt: null,
    completedBy: null,
    fieldEvidence: null,
  }));

export const initialServerWorkflowSnapshot = (): ServerWorkflowSnapshot => ({
  turbineId: SERVER_WORKFLOW_TURBINE_ID,
  mission: {
    id: SERVER_WORKFLOW_MISSION_ID,
    status: "under-review",
    progressPercent: 72,
  },
  decision: {
    id: SERVER_WORKFLOW_DECISION_ID,
    risk: "high",
    status: "under-review",
    approvalRequired: true,
    selectedAlternativeId: null,
    approval: null,
  },
  workOrder: {
    id: SERVER_WORKFLOW_WORK_ORDER_ID,
    status: "draft",
    alternativeId: null,
    tasks: initialTasks(),
    completedTaskCount: 0,
    totalTaskCount: serverWorkflowTaskDefinitions.length,
  },
  health: {
    turbineScore: 68,
    mainBearingScore: 63,
  },
  knowledgeCaseId: null,
  auditEvents: [],
  revision: 0,
  updatedAt: INITIAL_UPDATED_AT,
});

const summarize = (snapshot: ServerWorkflowSnapshot): ServerWorkflowStateSummary => ({
  missionStatus: snapshot.mission.status,
  decisionStatus: snapshot.decision.status,
  selectedAlternativeId: snapshot.decision.selectedAlternativeId,
  workOrderStatus: snapshot.workOrder.status,
  workOrderAlternativeId: snapshot.workOrder.alternativeId,
  completedTaskCount: snapshot.workOrder.completedTaskCount,
});

const requireReview = (snapshot: ServerWorkflowSnapshot): void => {
  if (snapshot.decision.status !== "under-review") {
    throw new ServerWorkflowTransitionError(
      "ILLEGAL_TRANSITION",
      `Action requires an under-review decision; current status is ${snapshot.decision.status}.`,
      409,
    );
  }
};

const approvalActions = new Set<ServerWorkflowAction>([
  "approve",
  "reject",
  "request-revision",
  "escalate",
]);

const eventDetail = (
  action: ServerWorkflowAction,
  taskId?: string,
  selectedAlternativeId?: ServerWorkflowAlternativeId,
): string => {
  const selectedPlan = getServerWorkflowAlternativePlan(selectedAlternativeId);
  const selectedPlanLabel = selectedPlan
    ? `${selectedPlan.label}「${selectedPlan.title}」(${selectedPlan.id})`
    : "未记录方案";
  const descriptions: Record<ServerWorkflowAction, string> = {
    approve: `${selectedPlanLabel}已通过人工审批，工单按所选方案进入计划状态。`,
    reject: `${selectedPlanLabel}被人工驳回。`,
    "request-revision": `审批人针对${selectedPlanLabel}要求补充证据并修订处置方案。`,
    escalate: `${selectedPlanLabel}的审批已升级至更高权限人员，执行门禁保持锁定。`,
    "start-work-order": "现场班组完成安全确认并开始执行工单。",
    "set-task-completion": `现场任务状态已更新：${taskId ?? "unknown"}。`,
    "complete-work-order": "五项现场任务通过门禁，工单完成并回写健康状态。",
    reset: "工作流已恢复至待人工审批的基线状态。",
  };
  return descriptions[action];
};

const auditKinds = (
  request: ServerWorkflowMutationRequest,
): readonly { readonly kind: ServerWorkflowAuditKind; readonly detail: string }[] => {
  const { action } = request;
  if (action === "complete-work-order") {
    return [
      { kind: "verification", detail: "复测验证通过：机组健康度 82，主轴承健康度 78。" },
      { kind: "knowledge", detail: "诊断、审批、执行与复测证据已沉淀为可检索知识案例。" },
    ];
  }
  if (approvalActions.has(action)) {
    return [
      {
        kind: "approval",
        detail: eventDetail(action, undefined, request.selectedAlternativeId),
      },
    ];
  }
  if (action === "reset") return [{ kind: "reset", detail: eventDetail(action) }];
  return [{ kind: "execution", detail: eventDetail(action) }];
};

export function applyServerWorkflowMutation(
  current: ServerWorkflowSnapshot,
  request: ServerWorkflowMutationRequest,
  timestamp: string,
): ServerWorkflowSnapshot {
  if (request.expectedRevision !== current.revision) {
    throw new ServerWorkflowTransitionError(
      "REVISION_CONFLICT",
      `Expected revision ${request.expectedRevision}, but current revision is ${current.revision}.`,
      409,
      { expectedRevision: request.expectedRevision, currentRevision: current.revision },
    );
  }

  const revision = current.revision + 1;
  let next: ServerWorkflowSnapshot;

  switch (request.action) {
    case "approve":
    case "reject":
    case "request-revision":
    case "escalate": {
      requireReview(current);
      if (!isServerWorkflowAlternativeId(request.selectedAlternativeId)) {
        throw new ServerWorkflowTransitionError(
          "APPROVAL_ALTERNATIVE_REQUIRED",
          "Approval actions require selectedAlternativeId to be ALT-0823-A, ALT-0823-B, or ALT-0823-C.",
          400,
        );
      }
      const selectedPlan = serverWorkflowAlternativePlans[request.selectedAlternativeId];
      const approval: ServerWorkflowApproval = {
        action: request.action,
        selectedAlternativeId: request.selectedAlternativeId,
        actor: request.actor,
        reason: request.reason ?? "",
        comment: request.comment ?? "",
        timestamp,
        correlationId: request.correlationId,
      };
      const outcome = {
        approve: {
          missionStatus: "approved" as const,
          progress: 84,
          decisionStatus: "approved" as const,
          workOrderStatus: "scheduled" as const,
        },
        reject: {
          missionStatus: "decision-pending" as const,
          progress: 62,
          decisionStatus: "rejected" as const,
          workOrderStatus: "draft" as const,
        },
        "request-revision": {
          missionStatus: "diagnosed" as const,
          progress: 58,
          decisionStatus: "revision-requested" as const,
          workOrderStatus: "draft" as const,
        },
        escalate: {
          missionStatus: "under-review" as const,
          progress: 74,
          decisionStatus: "under-review" as const,
          workOrderStatus: "draft" as const,
        },
      }[request.action];
      next = {
        ...current,
        mission: {
          ...current.mission,
          status: outcome.missionStatus,
          progressPercent: outcome.progress,
        },
        decision: {
          ...current.decision,
          status: outcome.decisionStatus,
          selectedAlternativeId: request.selectedAlternativeId,
          approval,
        },
        workOrder: {
          ...current.workOrder,
          status: outcome.workOrderStatus,
          alternativeId:
            request.action === "approve"
              ? request.selectedAlternativeId
              : current.workOrder.alternativeId,
          tasks:
            request.action === "approve"
              ? current.workOrder.tasks.map((task, index) => ({
                  ...task,
                  title: selectedPlan.taskTitles[index] ?? task.title,
                }))
              : current.workOrder.tasks,
        },
        revision,
        updatedAt: timestamp,
      };
      break;
    }
    case "start-work-order":
      if (
        current.decision.risk === "high" &&
        (current.decision.status !== "approved" || current.decision.approval?.action !== "approve")
      ) {
        throw new ServerWorkflowTransitionError(
          "HUMAN_APPROVAL_REQUIRED",
          "A recorded human approval is required before this high-risk work order can start.",
          409,
        );
      }
      if (current.workOrder.status !== "scheduled") {
        throw new ServerWorkflowTransitionError(
          "ILLEGAL_TRANSITION",
          `A scheduled work order is required; current status is ${current.workOrder.status}.`,
          409,
        );
      }
      next = {
        ...current,
        mission: { ...current.mission, status: "executing", progressPercent: 90 },
        workOrder: { ...current.workOrder, status: "in-progress" },
        revision,
        updatedAt: timestamp,
      };
      break;
    case "set-task-completion": {
      if (current.workOrder.status !== "in-progress") {
        throw new ServerWorkflowTransitionError(
          "ILLEGAL_TRANSITION",
          "Tasks can only change while the work order is in progress.",
          409,
        );
      }
      const taskIndex = current.workOrder.tasks.findIndex((task) => task.id === request.taskId);
      if (taskIndex < 0) {
        throw new ServerWorkflowTransitionError(
          "TASK_NOT_FOUND",
          `Task ${request.taskId ?? ""} is not part of the WT-023 work order.`,
          404,
        );
      }
      if (typeof request.completed !== "boolean") {
        throw new ServerWorkflowTransitionError(
          "INVALID_REQUEST",
          "set-task-completion requires a boolean completed value.",
          400,
        );
      }
      const currentTask = current.workOrder.tasks[taskIndex];
      if (request.completed && !request.fieldEvidence) {
        throw new ServerWorkflowTransitionError(
          "FIELD_EVIDENCE_REQUIRED",
          "Completing a field task requires artifact URI, SHA-256, measurement, and verifier evidence.",
          400,
          { taskId: currentTask.id },
        );
      }
      if (currentTask.completed === request.completed) {
        throw new ServerWorkflowTransitionError(
          "NO_STATE_CHANGE",
          `Task ${currentTask.id} is already ${request.completed ? "completed" : "open"}.`,
          409,
        );
      }
      const tasks = current.workOrder.tasks.map((task, index) =>
        index === taskIndex
          ? {
              ...task,
              completed: request.completed as boolean,
              completedAt: request.completed ? timestamp : null,
              completedBy: request.completed ? request.actor.name : null,
              fieldEvidence: request.completed ? (request.fieldEvidence ?? null) : null,
            }
          : task,
      );
      const completedTaskCount = tasks.filter((task) => task.completed).length;
      next = {
        ...current,
        mission: {
          ...current.mission,
          progressPercent: Math.min(
            98,
            90 + Math.round((completedTaskCount / serverWorkflowTaskDefinitions.length) * 8),
          ),
        },
        workOrder: { ...current.workOrder, tasks, completedTaskCount },
        revision,
        updatedAt: timestamp,
      };
      break;
    }
    case "complete-work-order":
      if (current.workOrder.status !== "in-progress") {
        throw new ServerWorkflowTransitionError(
          "ILLEGAL_TRANSITION",
          "Only an in-progress work order can be completed.",
          409,
        );
      }
      if (current.workOrder.completedTaskCount !== current.workOrder.totalTaskCount) {
        throw new ServerWorkflowTransitionError(
          "TASK_GATE_BLOCKED",
          "All five work-order tasks must be completed before verification and closure.",
          409,
          {
            completedTaskCount: current.workOrder.completedTaskCount,
            totalTaskCount: current.workOrder.totalTaskCount,
          },
        );
      }
      next = {
        ...current,
        mission: { ...current.mission, status: "completed", progressPercent: 100 },
        workOrder: { ...current.workOrder, status: "completed" },
        health: { turbineScore: 82, mainBearingScore: 78 },
        knowledgeCaseId: SERVER_WORKFLOW_KNOWLEDGE_CASE_ID,
        revision,
        updatedAt: timestamp,
      };
      break;
    case "reset": {
      const baseline = initialServerWorkflowSnapshot();
      next = {
        ...baseline,
        auditEvents: current.auditEvents,
        revision,
        updatedAt: timestamp,
      };
      break;
    }
  }

  const fromState = summarize(current);
  const toState = summarize(next);
  const events = auditKinds(request).map((event, index): ServerWorkflowAuditEvent => ({
    id: `${SERVER_WORKFLOW_MISSION_ID}-R${revision}-E${index + 1}`,
    missionId: SERVER_WORKFLOW_MISSION_ID,
    revision,
    eventSequence: index + 1,
    action: request.action,
    kind: event.kind,
    actor: request.actor,
    correlationId: request.correlationId,
    idempotencyKey: request.idempotencyKey,
    fromState,
    toState,
    detail: event.detail,
    fieldEvidence:
      request.action === "set-task-completion" && request.completed
        ? (request.fieldEvidence ?? null)
        : null,
    timestamp,
  }));

  return { ...next, auditEvents: [...current.auditEvents, ...events] };
}
