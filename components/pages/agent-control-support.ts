import type { AgentToolExecution } from "@/lib/agent-tool-runtime";
import { getCurrentWorkflowAuditCycle } from "@/lib/demo-workflow";
import type { DemoWorkflowEvent, DemoWorkflowState } from "@/lib/demo-workflow";
import { featuredMission, missions } from "@/lib/operations-data";
import type { ActivityEvent, Agent } from "@/lib/types";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";

// The durable backend ledger executes deterministic SQL tools with no provider
// token usage, so its executions may carry a null `tokenEstimate`.
export type LedgerToolExecution = Omit<AgentToolExecution, "tokenEstimate"> & {
  readonly tokenEstimate: AgentToolExecution["tokenEstimate"] | null;
};

export type ToolTestResponse = {
  ok: true;
  data: { execution: LedgerToolExecution };
  error: null;
};

export type AgentLedgerResponse = {
  ok: true;
  data: {
    catalog: readonly unknown[];
    executionHistory: readonly LedgerToolExecution[];
  };
  error: null;
  meta: {
    persistence: "d1" | "runtime-memory" | "postgresql";
    persisted: boolean;
    historyCount: number;
    totalHistoryCount?: number;
  };
};

export type AgentCollectionResponse = {
  data: readonly Agent[];
  meta: {
    count: number;
    runtimeMode?: OpenVigilRuntimeMode;
    fixtureFallback?: boolean;
  };
};

const workflowActivityKinds: Record<DemoWorkflowEvent["kind"], ActivityEvent["kind"]> = {
  replay: "system",
  approval: "approval",
  execution: "execution",
  verification: "review",
  knowledge: "retrieval",
};

const postHitlActivityKinds = new Set<ActivityEvent["kind"]>([
  "approval",
  "work-order",
  "execution",
]);

export function isFeaturedPostHitlActivity(missionId: string, kind: string): boolean {
  return (
    missionId === featuredMission.id && postHitlActivityKinds.has(kind as ActivityEvent["kind"])
  );
}

export function currentWorkflowActivity(events: readonly DemoWorkflowEvent[]): ActivityEvent[] {
  return getCurrentWorkflowAuditCycle(events).map((event) => ({
    id: event.id,
    missionId: featuredMission.id,
    timestamp: event.timestamp,
    agentId: event.kind === "knowledge" ? "agent-knowledge" : null,
    actorLabel: event.actor,
    kind: workflowActivityKinds[event.kind],
    title: event.title,
    detail: event.detail,
    evidenceIds: [],
    outcome:
      event.kind === "replay"
        ? ("attention" as const)
        : event.kind === "execution"
          ? ("in-progress" as const)
          : ("success" as const),
  }));
}

export function workflowAwareTask(
  agent: Agent,
  workflow: Pick<DemoWorkflowState, "approval" | "decisionStatus" | "workOrderStatus">,
): string | null {
  if (agent.currentMissionId !== featuredMission.id) return agent.currentTask;

  if (workflow.decisionStatus === "under-review") {
    const gate = workflow.approval?.action === "escalate" ? "升级审批" : "人工审批";
    const pendingTasks: Readonly<Record<string, string>> = {
      "agent-maintenance-strategy": `等待 WT-023 ${gate}结论`,
      "agent-work-order": `WT-023 等待${gate}，工单保持草案`,
      "agent-crew-scheduling": `WT-023 等待${gate}，海维二组尚未排班`,
      "agent-vessel-scheduling": `WT-023 等待${gate}，CTV-03 航次尚未确认`,
    };
    return pendingTasks[agent.id] ?? agent.currentTask;
  }

  if (["rejected", "revision-requested"].includes(workflow.decisionStatus)) {
    const reason = workflow.decisionStatus === "rejected" ? "方案已拒绝" : "方案待修订";
    const pausedTasks: Readonly<Record<string, string>> = {
      "agent-maintenance-strategy": `WT-023 ${reason}，等待新方案`,
      "agent-work-order": `WT-023 ${reason}，工单保持草案`,
      "agent-crew-scheduling": `WT-023 ${reason}，班组排班暂停`,
      "agent-vessel-scheduling": `WT-023 ${reason}，航次确认暂停`,
    };
    return pausedTasks[agent.id] ?? agent.currentTask;
  }

  if (workflow.workOrderStatus === "in-progress") {
    const activeTasks: Readonly<Record<string, string>> = {
      "agent-maintenance-strategy": "等待 WT-023 现场复测结果",
      "agent-work-order": "跟踪 WO-20260823-017 现场执行",
      "agent-crew-scheduling": "跟踪海维二组 WT-023 现场任务",
      "agent-vessel-scheduling": "保障 CTV-03 WT-023 作业航次",
    };
    return activeTasks[agent.id] ?? agent.currentTask;
  }

  if (workflow.workOrderStatus === "completed") {
    const closingTasks: Readonly<Record<string, string>> = {
      "agent-maintenance-strategy": "复核 WT-023 闭环健康恢复",
      "agent-work-order": "同步 WO-20260823-017 闭环记录",
      "agent-crew-scheduling": "释放海维二组后续作业资源",
      "agent-vessel-scheduling": "释放 CTV-03 后续航次资源",
    };
    return closingTasks[agent.id] ?? agent.currentTask;
  }

  return agent.currentTask;
}

export type AgentQueueItem = {
  readonly id: string;
  readonly sequence: number;
  readonly title: string;
  readonly association: string;
  readonly status: "working" | "reviewing" | "waiting" | "queued" | "completed";
  readonly statusLabel: string;
  readonly href: string;
};

function currentQueueStatus(agent: Agent): Pick<AgentQueueItem, "status" | "statusLabel"> {
  if (agent.status === "reviewing") return { status: "reviewing", statusLabel: "审核中" };
  if (agent.status === "waiting" || agent.status === "idle") {
    return { status: "waiting", statusLabel: "等待中" };
  }
  if (agent.status === "failed" || agent.status === "offline") {
    return { status: "waiting", statusLabel: "已暂停" };
  }
  return { status: "working", statusLabel: "执行中" };
}

export function deriveAgentTaskQueue(
  agent: Agent,
  currentTask: string | null,
  publicEvents: readonly ActivityEvent[],
): readonly AgentQueueItem[] {
  const candidates: Omit<AgentQueueItem, "sequence">[] = [];
  const linkedMissionIds = new Set<string>();

  if (currentTask && agent.currentMissionId) {
    const currentMission = missions.find((mission) => mission.id === agent.currentMissionId);
    candidates.push({
      id: `current-${agent.currentMissionId}`,
      title: currentTask,
      association: currentMission
        ? `${currentMission.id} · ${currentMission.turbineId}`
        : agent.currentMissionId,
      ...currentQueueStatus(agent),
      href: `/missions/${agent.currentMissionId}`,
    });
    linkedMissionIds.add(agent.currentMissionId);
  }

  missions
    .filter(
      (mission) =>
        mission.status !== "completed" &&
        mission.id !== agent.currentMissionId &&
        (mission.leadAgentId === agent.id || mission.agentIds.includes(agent.id)),
    )
    .sort(
      (left, right) => Date.parse(left.targetResolutionAt) - Date.parse(right.targetResolutionAt),
    )
    .forEach((mission) => {
      candidates.push({
        id: `mission-${mission.id}`,
        title: mission.nextAction,
        association: `${mission.id} · ${mission.turbineId}`,
        status: mission.status === "under-review" ? "reviewing" : "queued",
        statusLabel: mission.status === "under-review" ? "待审核" : "已排队",
        href: `/missions/${mission.id}`,
      });
      linkedMissionIds.add(mission.id);
    });

  publicEvents
    .filter((event) => event.agentId === agent.id && !linkedMissionIds.has(event.missionId))
    .sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp))
    .forEach((event) => {
      candidates.push({
        id: `activity-${event.id}`,
        title: event.title,
        association: `${event.missionId} · 最近完成`,
        status: "completed",
        statusLabel: "已完成",
        href: `/missions/${event.missionId}`,
      });
      linkedMissionIds.add(event.missionId);
    });

  return candidates
    .slice(0, Math.max(agent.queueDepth, currentTask ? 1 : 0))
    .map((item, index) => ({
      ...item,
      sequence: index + 1,
    }));
}
