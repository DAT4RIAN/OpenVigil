import type { ApprovalAction, DecisionStatus, MissionStatus, WorkOrderStatus } from "./types";

export type DemoWorkflowEventKind =
  "replay" | "approval" | "execution" | "verification" | "knowledge";

export interface DemoApprovalRecord {
  readonly action: ApprovalAction;
  readonly approver: string;
  readonly approverRole: string;
  readonly timestamp: string;
  readonly reason: string;
  readonly comment: string;
}

export interface DemoWorkflowEvent {
  readonly id: string;
  readonly kind: DemoWorkflowEventKind;
  readonly timestamp: string;
  readonly actor: string;
  readonly title: string;
  readonly detail: string;
}

export interface DemoWorkflowState {
  readonly missionStatus: MissionStatus;
  readonly missionProgress: number;
  readonly decisionStatus: DecisionStatus;
  readonly approval: DemoApprovalRecord | null;
  readonly workOrderStatus: WorkOrderStatus;
  readonly completedTaskIds: readonly string[];
  readonly turbineHealthScore: number;
  readonly mainBearingHealthScore: number;
  readonly knowledgeCaseId: string | null;
  readonly auditTrail: readonly DemoWorkflowEvent[];
}

export type DemoWorkflowAction =
  | { readonly type: "replay-approval"; readonly timestamp: string }
  | { readonly type: "reset-canonical" }
  | {
      readonly type: "submit-approval";
      readonly action: ApprovalAction;
      readonly approver: string;
      readonly approverRole: string;
      readonly timestamp: string;
      readonly reason: string;
      readonly comment: string;
    }
  | { readonly type: "start-work-order"; readonly timestamp: string; readonly actor: string }
  | {
      readonly type: "toggle-task";
      readonly taskId: string;
      readonly timestamp: string;
      readonly actor: string;
    }
  | { readonly type: "complete-work-order"; readonly timestamp: string; readonly actor: string };

const canonicalApproval: DemoApprovalRecord = {
  action: "approve",
  approver: "李明远",
  approverRole: "值班总工程师",
  timestamp: "2026-08-13T09:02:00+08:00",
  reason: "方案 B 在安全风险、停机损失与作业窗口之间取得最佳平衡。",
  comment: "同意降载运行，并于 8 月 14 日窗口执行主轴承检查。",
};

export const featuredWorkOrderTaskIds = [
  "WO-20260823-017-TASK-01",
  "WO-20260823-017-TASK-02",
  "WO-20260823-017-TASK-03",
  "WO-20260823-017-TASK-04",
  "WO-20260823-017-TASK-05",
] as const;

export const canonicalDemoWorkflow: DemoWorkflowState = {
  missionStatus: "executing",
  missionProgress: 84,
  decisionStatus: "approved",
  approval: canonicalApproval,
  workOrderStatus: "scheduled",
  completedTaskIds: [],
  turbineHealthScore: 68,
  mainBearingHealthScore: 63,
  knowledgeCaseId: null,
  auditTrail: [
    {
      id: "DEMO-EVENT-APPROVED",
      kind: "approval",
      timestamp: canonicalApproval.timestamp,
      actor: canonicalApproval.approver,
      title: "方案 B 已获人工批准",
      detail: "审批门禁解除，WO-20260823-017 已创建并排程。",
    },
  ],
};

const eventId = (kind: DemoWorkflowEventKind, timestamp: string): string =>
  `DEMO-${kind.toUpperCase()}-${timestamp.replace(/\D/g, "").slice(-14)}`;

const appendEvent = (
  state: DemoWorkflowState,
  event: Omit<DemoWorkflowEvent, "id">,
): readonly DemoWorkflowEvent[] => [
  ...state.auditTrail,
  { ...event, id: eventId(event.kind, event.timestamp) },
];

export function transitionDemoWorkflow(
  state: DemoWorkflowState,
  action: DemoWorkflowAction,
): DemoWorkflowState {
  switch (action.type) {
    case "reset-canonical":
      return canonicalDemoWorkflow;
    case "replay-approval":
      return {
        ...canonicalDemoWorkflow,
        missionStatus: "under-review",
        missionProgress: 72,
        decisionStatus: "under-review",
        approval: null,
        workOrderStatus: "draft",
        auditTrail: [
          {
            id: eventId("replay", action.timestamp),
            kind: "replay",
            timestamp: action.timestamp,
            actor: "Demo Operator",
            title: "审批门禁已重置",
            detail: "诊断与证据保持不变；高风险执行动作重新锁定。",
          },
        ],
      };
    case "submit-approval": {
      if (state.decisionStatus !== "under-review") return state;
      const approval: DemoApprovalRecord = {
        action: action.action,
        approver: action.approver,
        approverRole: action.approverRole,
        timestamp: action.timestamp,
        reason: action.reason,
        comment: action.comment,
      };
      const common = {
        ...state,
        approval,
        auditTrail: appendEvent(state, {
          kind: "approval",
          timestamp: action.timestamp,
          actor: action.approver,
          title: `人工审批：${action.action}`,
          detail: `${action.reason} · ${action.comment}`,
        }),
      };

      if (action.action === "approve") {
        return {
          ...common,
          missionStatus: "executing",
          missionProgress: 84,
          decisionStatus: "approved",
          workOrderStatus: "scheduled",
        };
      }
      if (action.action === "reject") {
        return {
          ...common,
          missionStatus: "decision-pending",
          missionProgress: 62,
          decisionStatus: "rejected",
          workOrderStatus: "draft",
        };
      }
      if (action.action === "request-revision") {
        return {
          ...common,
          missionStatus: "diagnosed",
          missionProgress: 58,
          decisionStatus: "revision-requested",
          workOrderStatus: "draft",
        };
      }
      return {
        ...common,
        missionStatus: "under-review",
        missionProgress: 74,
        decisionStatus: "under-review",
        workOrderStatus: "draft",
      };
    }
    case "start-work-order":
      if (state.decisionStatus !== "approved" || state.workOrderStatus !== "scheduled") {
        return state;
      }
      return {
        ...state,
        missionStatus: "executing",
        missionProgress: 90,
        workOrderStatus: "in-progress",
        auditTrail: appendEvent(state, {
          kind: "execution",
          timestamp: action.timestamp,
          actor: action.actor,
          title: "现场工单开始执行",
          detail: "班组已完成 LOTO 与作业前安全确认。",
        }),
      };
    case "toggle-task": {
      if (state.workOrderStatus !== "in-progress") return state;
      const completed = state.completedTaskIds.includes(action.taskId)
        ? state.completedTaskIds.filter((id) => id !== action.taskId)
        : [...state.completedTaskIds, action.taskId];
      return {
        ...state,
        missionProgress: Math.min(
          98,
          90 + Math.round((completed.length / featuredWorkOrderTaskIds.length) * 8),
        ),
        completedTaskIds: completed,
        auditTrail: appendEvent(state, {
          kind: "execution",
          timestamp: action.timestamp,
          actor: action.actor,
          title: state.completedTaskIds.includes(action.taskId)
            ? "现场任务重新打开"
            : "现场任务已完成",
          detail: action.taskId,
        }),
      };
    }
    case "complete-work-order":
      if (
        state.workOrderStatus !== "in-progress" ||
        !featuredWorkOrderTaskIds.every((id) => state.completedTaskIds.includes(id))
      ) {
        return state;
      }
      return {
        ...state,
        missionStatus: "completed",
        missionProgress: 100,
        workOrderStatus: "completed",
        turbineHealthScore: 82,
        mainBearingHealthScore: 78,
        knowledgeCaseId: "KB-CASE-2026-WT023-CLOSED",
        auditTrail: [
          ...appendEvent(state, {
            kind: "verification",
            timestamp: action.timestamp,
            actor: action.actor,
            title: "执行结果已验证",
            detail: "复测振动与温升回落，主轴承健康度由 63 提升至 78。",
          }),
          {
            id: eventId("knowledge", action.timestamp),
            kind: "knowledge",
            timestamp: action.timestamp,
            actor: "Knowledge Agent",
            title: "故障案例已沉淀",
            detail: "WT-023 诊断证据、审批记录、现场照片与复测结果已形成可检索案例。",
          },
        ],
      };
  }
}

export const canCompleteFeaturedWorkOrder = (state: DemoWorkflowState): boolean =>
  state.workOrderStatus === "in-progress" &&
  featuredWorkOrderTaskIds.every((id) => state.completedTaskIds.includes(id));
