import type { ApprovalAction, DecisionStatus, MissionStatus, WorkOrderStatus } from "./types";
import type { ServerWorkflowAlternativeId } from "./server-workflow-contract";

export type DemoWorkflowEventKind =
  "replay" | "approval" | "execution" | "verification" | "knowledge";

export interface DemoApprovalRecord {
  readonly action: ApprovalAction;
  readonly selectedAlternativeId: ServerWorkflowAlternativeId;
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

export interface FeaturedMissionNarrative {
  readonly summary: string;
  readonly nextAction: string;
}

export type DemoWorkflowAction =
  | { readonly type: "replay-approval"; readonly timestamp: string }
  | { readonly type: "reset-canonical" }
  | {
      readonly type: "submit-approval";
      readonly action: ApprovalAction;
      readonly selectedAlternativeId: ServerWorkflowAlternativeId;
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

export const featuredWorkOrderTaskIds = [
  "WO-20260823-017-TASK-01",
  "WO-20260823-017-TASK-02",
  "WO-20260823-017-TASK-03",
  "WO-20260823-017-TASK-04",
  "WO-20260823-017-TASK-05",
] as const;

export const canonicalDemoWorkflow: DemoWorkflowState = {
  missionStatus: "under-review",
  missionProgress: 72,
  decisionStatus: "under-review",
  approval: null,
  workOrderStatus: "draft",
  completedTaskIds: [],
  turbineHealthScore: 68,
  mainBearingHealthScore: 63,
  knowledgeCaseId: null,
  auditTrail: [],
};

export function getFeaturedMissionNarrative(
  state: Pick<
    DemoWorkflowState,
    "missionStatus" | "decisionStatus" | "approval" | "workOrderStatus" | "knowledgeCaseId"
  >,
): FeaturedMissionNarrative {
  if (state.missionStatus === "completed") {
    return {
      summary: "主轴承异常已完成现场检查与复测，健康度结果和处置证据已回写闭环。",
      nextAction: state.knowledgeCaseId
        ? `复核并复用知识案例 ${state.knowledgeCaseId}`
        : "完成闭环知识案例归档",
    };
  }
  if (state.workOrderStatus === "in-progress") {
    return {
      summary: "主轴承联合异常已通过人工审批，现场检查工单正在执行。",
      nextAction: "完成现场任务并提交振动、温度与检查结果",
    };
  }
  if (state.workOrderStatus === "scheduled" || state.decisionStatus === "approved") {
    return {
      summary: "主轴承联合异常处置方案已获人工批准，现场检查工单已排程。",
      nextAction: "在 8 月 14 日安全窗口启动 WO-20260823-017",
    };
  }
  if (state.decisionStatus === "rejected") {
    return {
      summary: "主轴承联合异常证据已完成汇总，当前处置方案被人工拒绝。",
      nextAction: "生成替代处置方案并重新提交人工审批",
    };
  }
  if (state.decisionStatus === "revision-requested") {
    return {
      summary: "主轴承联合异常证据已完成汇总，人工审核要求修订处置方案。",
      nextAction: "补充降载曲线与返航预案后重新提交",
    };
  }
  if (state.approval?.action === "escalate") {
    return {
      summary: "主轴承联合异常证据已完成汇总，高风险处置方案已升级复核。",
      nextAction: "等待场站经理与值班总工程师联合决策",
    };
  }
  return {
    summary: "主轴承振动、温度和功率波动出现联合异常，方案 B 正等待人工审批。",
    nextAction: "完成高风险处置方案的人工审批",
  };
}

export function getCurrentWorkflowAuditCycle(
  events: readonly DemoWorkflowEvent[],
): readonly DemoWorkflowEvent[] {
  let currentCycleStart = 0;
  events.forEach((event, index) => {
    if (event.kind === "replay") currentCycleStart = index;
  });
  return events.slice(currentCycleStart);
}

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
        selectedAlternativeId: action.selectedAlternativeId,
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
          title: `人工审批：${action.action} · ${action.selectedAlternativeId}`,
          detail: `${action.selectedAlternativeId} · ${action.reason} · ${action.comment}`,
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
