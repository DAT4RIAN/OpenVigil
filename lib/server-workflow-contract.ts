import type { ApprovalAction, DecisionStatus, MissionStatus, WorkOrderStatus } from "./types";

export const SERVER_WORKFLOW_TURBINE_ID = "WT-023" as const;
export const SERVER_WORKFLOW_MISSION_ID = "MISSION-2026-0823" as const;
export const SERVER_WORKFLOW_DECISION_ID = "DECISION-2026-0823" as const;
export const SERVER_WORKFLOW_WORK_ORDER_ID = "WO-20260823-017" as const;
export const SERVER_WORKFLOW_KNOWLEDGE_CASE_ID = "KB-CASE-2026-WT023-CLOSED" as const;

export const isSupportedServerWorkflowTurbineId = (value: string): boolean =>
  value.toUpperCase() === SERVER_WORKFLOW_TURBINE_ID;

export const serverWorkflowTaskDefinitions = [
  { id: "WO-20260823-017-TASK-01", title: "检查主轴承润滑状态并采集润滑脂样本" },
  { id: "WO-20260823-017-TASK-02", title: "使用便携式分析仪采集三向振动数据" },
  { id: "WO-20260823-017-TASK-03", title: "复核驱动端与非驱动端轴承温度" },
  { id: "WO-20260823-017-TASK-04", title: "执行滚道与滚子内窥镜检查" },
  { id: "WO-20260823-017-TASK-05", title: "上传现场照片、频谱和检查结论" },
] as const;

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
  readonly timestamp: string;
}

export interface ServerWorkflowStateSummary {
  readonly missionStatus: MissionStatus;
  readonly decisionStatus: DecisionStatus;
  readonly workOrderStatus: WorkOrderStatus;
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
    readonly approval: ServerWorkflowApproval | null;
  };
  readonly workOrder: {
    readonly id: typeof SERVER_WORKFLOW_WORK_ORDER_ID;
    readonly status: WorkOrderStatus;
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
  readonly reason?: string;
  readonly comment?: string;
  readonly taskId?: string;
  readonly completed?: boolean;
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
    approval: null,
  },
  workOrder: {
    id: SERVER_WORKFLOW_WORK_ORDER_ID,
    status: "draft",
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
  workOrderStatus: snapshot.workOrder.status,
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

const eventDetail = (action: ServerWorkflowAction, taskId?: string): string => {
  const descriptions: Record<ServerWorkflowAction, string> = {
    approve: "高风险处置方案已通过人工审批，工单进入计划状态。",
    reject: "高风险处置方案被人工驳回。",
    "request-revision": "审批人要求补充证据并修订处置方案。",
    escalate: "审批已升级至更高权限人员，执行门禁保持锁定。",
    "start-work-order": "现场班组完成安全确认并开始执行工单。",
    "set-task-completion": `现场任务状态已更新：${taskId ?? "unknown"}。`,
    "complete-work-order": "五项现场任务通过门禁，工单完成并回写健康状态。",
    reset: "工作流已恢复至待人工审批的基线状态。",
  };
  return descriptions[action];
};

const auditKinds = (
  action: ServerWorkflowAction,
): readonly { readonly kind: ServerWorkflowAuditKind; readonly detail: string }[] => {
  if (action === "complete-work-order") {
    return [
      { kind: "verification", detail: "复测验证通过：机组健康度 82，主轴承健康度 78。" },
      { kind: "knowledge", detail: "诊断、审批、执行与复测证据已沉淀为可检索知识案例。" },
    ];
  }
  if (approvalActions.has(action)) return [{ kind: "approval", detail: eventDetail(action) }];
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
      const approval: ServerWorkflowApproval = {
        action: request.action,
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
        decision: { ...current.decision, status: outcome.decisionStatus, approval },
        workOrder: { ...current.workOrder, status: outcome.workOrderStatus },
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
  const events = auditKinds(request.action).map((event, index): ServerWorkflowAuditEvent => ({
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
    timestamp,
  }));

  return { ...next, auditEvents: [...current.auditEvents, ...events] };
}
