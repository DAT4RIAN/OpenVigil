"use client";

import { create } from "zustand";
import { apiGet, apiPost } from "./api-client";
import {
  canonicalDemoWorkflow,
  transitionDemoWorkflow,
  type DemoApprovalRecord,
  type DemoWorkflowAction,
  type DemoWorkflowEvent,
  type DemoWorkflowEventKind,
  type DemoWorkflowState,
} from "./demo-workflow";
import {
  buildServerWorkflowFieldEvidence,
  type ServerWorkflowAuditEvent,
  type ServerWorkflowEnvelope,
  type ServerWorkflowMutationRequest,
  type ServerWorkflowSnapshot,
} from "./server-workflow-contract";

type WorkflowSyncStatus = "idle" | "loading" | "saving" | "synced" | "error";
type WorkflowPersistence = "d1" | "ephemeral" | "offline-memory";

interface DemoWorkflowStore extends DemoWorkflowState {
  readonly syncStatus: WorkflowSyncStatus;
  readonly persistence: WorkflowPersistence;
  readonly writable: boolean;
  readonly lastSyncError: string | null;
  readonly serverRevision: number;
  dispatch: (action: DemoWorkflowAction) => void;
}

interface PendingMutation {
  readonly action: DemoWorkflowAction;
  readonly request: ServerWorkflowMutationRequest;
}

const workflowPath = "/api/workflow/WT-023";
let authoritativeState: DemoWorkflowState = canonicalDemoWorkflow;
let hydrationPromise: Promise<void> | null = null;
let processingMutations = false;
let mutationSequence = 0;
const pendingMutations: PendingMutation[] = [];

function eventTitle(action: string): string {
  const titles: Record<string, string> = {
    reset: "审批门禁已重置",
    approve: "维护方案已获人工批准",
    reject: "维护方案已被人工拒绝",
    "request-revision": "已请求 Agent 修订方案",
    escalate: "高风险决策已升级",
    "start-work-order": "现场工单开始执行",
    "set-task-completion": "现场任务状态已更新",
    "complete-work-order": "执行结果已验证并闭环",
  };
  return titles[action] ?? action;
}

function mapApproval(
  approval: ServerWorkflowSnapshot["decision"]["approval"],
): DemoApprovalRecord | null {
  if (!approval) return null;
  return {
    action: approval.action,
    selectedAlternativeId: approval.selectedAlternativeId,
    approver: approval.actor.name,
    approverRole: approval.actor.role ?? "Operator",
    timestamp: approval.timestamp,
    reason: approval.reason ?? "服务器已记录人工决策",
    comment: approval.comment ?? "—",
  };
}

function mapAuditEvent(event: ServerWorkflowAuditEvent): DemoWorkflowEvent {
  return {
    id: event.id,
    kind: (event.kind === "reset" ? "replay" : event.kind) as DemoWorkflowEventKind,
    timestamp: event.timestamp,
    actor: event.actor.name,
    title: eventTitle(event.action),
    detail: event.detail,
  };
}

function mapSnapshot(snapshot: ServerWorkflowSnapshot): DemoWorkflowState {
  const auditTrail = snapshot.auditEvents.map(mapAuditEvent);
  if (snapshot.knowledgeCaseId && !auditTrail.some((event) => event.kind === "knowledge")) {
    auditTrail.push({
      id: `KNOWLEDGE-${snapshot.revision}`,
      kind: "knowledge",
      timestamp: snapshot.updatedAt,
      actor: "Knowledge Agent",
      title: "故障案例已沉淀",
      detail: `${snapshot.knowledgeCaseId} 已关联诊断、审批、执行与复测证据。`,
    });
  }
  return {
    missionStatus: snapshot.mission.status,
    missionProgress: snapshot.mission.progressPercent,
    decisionStatus: snapshot.decision.status,
    approval: mapApproval(snapshot.decision.approval),
    workOrderStatus: snapshot.workOrder.status,
    completedTaskIds: snapshot.workOrder.tasks
      .filter((task) => task.completed)
      .map((task) => task.id),
    turbineHealthScore: snapshot.health.turbineScore,
    mainBearingHealthScore: snapshot.health.mainBearingScore,
    knowledgeCaseId: snapshot.knowledgeCaseId,
    auditTrail,
  };
}

function stateOnly(store: DemoWorkflowStore): DemoWorkflowState {
  return {
    missionStatus: store.missionStatus,
    missionProgress: store.missionProgress,
    decisionStatus: store.decisionStatus,
    approval: store.approval,
    workOrderStatus: store.workOrderStatus,
    completedTaskIds: store.completedTaskIds,
    turbineHealthScore: store.turbineHealthScore,
    mainBearingHealthScore: store.mainBearingHealthScore,
    knowledgeCaseId: store.knowledgeCaseId,
    auditTrail: store.auditTrail,
  };
}

function optimisticState(base: DemoWorkflowState): DemoWorkflowState {
  return pendingMutations.reduce(
    (state, mutation) => transitionDemoWorkflow(state, mutation.action),
    base,
  );
}

function nextOperationId(): string {
  mutationSequence += 1;
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${mutationSequence.toString(36)}`;
}

function actorId(name: string): string {
  const demoActorIds: Readonly<Record<string, string>> = {
    李明远: "demo-duty-chief",
    海维二组: "demo-maintenance-team",
    林工: "demo-verification-engineer",
    "Demo Operator": "demo-operator",
  };
  if (demoActorIds[name]) return demoActorIds[name];
  const normalized = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-");
  return normalized || `operator-${mutationSequence + 1}`;
}

function mutationRequest(
  action: DemoWorkflowAction,
  expectedRevision: number,
  currentState: DemoWorkflowState,
): ServerWorkflowMutationRequest {
  const operationId = nextOperationId();
  const common = {
    correlationId: `workflow-${operationId}`,
    idempotencyKey: `workflow-WT-023-${operationId}`,
    expectedRevision,
  };
  switch (action.type) {
    case "submit-approval":
      return {
        ...common,
        action: action.action,
        actor: {
          id: actorId(action.approver),
          name: action.approver,
          role: action.approverRole,
        },
        reason: action.reason,
        comment: action.comment,
        selectedAlternativeId: action.selectedAlternativeId,
      };
    case "start-work-order":
    case "complete-work-order":
      return {
        ...common,
        action: action.type,
        actor: {
          id: actorId(action.actor),
          name: action.actor,
          role: "maintenance-execution",
        },
      };
    case "toggle-task": {
      const taskActor = {
        id: actorId(action.actor),
        name: action.actor,
        role: "maintenance-execution",
      };
      const completed = !currentState.completedTaskIds.includes(action.taskId);
      return {
        ...common,
        action: "set-task-completion",
        actor: taskActor,
        taskId: action.taskId,
        completed,
        ...(completed
          ? { fieldEvidence: buildServerWorkflowFieldEvidence(action.taskId, taskActor) }
          : {}),
      };
    }
    case "replay-approval":
    case "reset-canonical":
      return {
        ...common,
        action: "reset",
        actor: {
          id: "demo-operator",
          name: "Demo Operator",
          role: "system-demo-controller",
        },
      };
  }
}

export const useDemoWorkflow = create<DemoWorkflowStore>()((set, get) => ({
  ...canonicalDemoWorkflow,
  syncStatus: "idle",
  persistence: "offline-memory",
  writable: false,
  lastSyncError: null,
  serverRevision: 0,
  dispatch: (action) => {
    if (!get().writable) {
      set({
        syncStatus: "error",
        lastSyncError: "D1 持久化当前不可用；服务器已将闭环动作切换为只读。",
      });
      return;
    }
    const currentState = stateOnly(get());
    pendingMutations.push({
      action,
      request: mutationRequest(
        action,
        get().serverRevision + pendingMutations.length,
        currentState,
      ),
    });
    set((store) => ({
      ...transitionDemoWorkflow(stateOnly(store), action),
      syncStatus: "saving",
      lastSyncError: null,
    }));
    void processMutationQueue();
  },
}));

async function processMutationQueue(): Promise<void> {
  if (processingMutations) return;
  processingMutations = true;

  while (pendingMutations.length > 0) {
    const mutation = pendingMutations[0];
    try {
      const envelope = await apiPost<ServerWorkflowEnvelope>(workflowPath, mutation.request);
      authoritativeState = mapSnapshot(envelope.data);
      pendingMutations.shift();
      useDemoWorkflow.setState({
        ...optimisticState(authoritativeState),
        syncStatus: pendingMutations.length > 0 ? "saving" : "synced",
        persistence: envelope.meta.persistence,
        writable: envelope.meta.writable,
        lastSyncError: null,
        serverRevision: envelope.data.revision,
      });
    } catch (error) {
      pendingMutations.shift();
      pendingMutations.splice(0);
      const message =
        error instanceof Error ? error.message : "服务器状态同步失败，已回滚到最近快照。";
      try {
        const envelope = await apiGet<ServerWorkflowEnvelope>(workflowPath);
        authoritativeState = mapSnapshot(envelope.data);
        useDemoWorkflow.setState({
          ...authoritativeState,
          syncStatus: "error",
          persistence: envelope.meta.persistence,
          writable: envelope.meta.writable,
          lastSyncError: message,
          serverRevision: envelope.data.revision,
        });
      } catch {
        useDemoWorkflow.setState({
          ...authoritativeState,
          syncStatus: "error",
          persistence: "offline-memory",
          writable: false,
          lastSyncError: message,
        });
      }
    }
  }

  processingMutations = false;
}

export const hydrateDemoWorkflow = (): void => {
  if (hydrationPromise) return;
  useDemoWorkflow.setState({ syncStatus: "loading", lastSyncError: null });
  hydrationPromise = apiGet<ServerWorkflowEnvelope>(workflowPath)
    .then((envelope) => {
      authoritativeState = mapSnapshot(envelope.data);
      useDemoWorkflow.setState({
        ...optimisticState(authoritativeState),
        syncStatus: pendingMutations.length > 0 ? "saving" : "synced",
        persistence: envelope.meta.persistence,
        writable: envelope.meta.writable,
        lastSyncError: null,
        serverRevision: envelope.data.revision,
      });
    })
    .catch((error: unknown) => {
      authoritativeState = stateOnly(useDemoWorkflow.getState());
      useDemoWorkflow.setState({
        syncStatus: "error",
        persistence: "offline-memory",
        writable: false,
        lastSyncError:
          error instanceof Error ? error.message : "服务器工作流暂不可用；当前页面使用内存状态。",
      });
    })
    .finally(() => {
      hydrationPromise = null;
    });
};
