import type { DemoWorkflowState } from "./demo-workflow";
import { getServerWorkflowAlternativePlan } from "./server-workflow-plans.js";
import type { Agent, Alarm, Decision, Mission, WindTurbine, WorkOrder } from "./types";

type ClientWorkflow = Pick<
  DemoWorkflowState,
  | "missionStatus"
  | "missionProgress"
  | "decisionStatus"
  | "workOrderStatus"
  | "turbineHealthScore"
  | "approval"
>;

export const FEATURED_MISSION_ID = "MISSION-2026-0823";
export const FEATURED_TURBINE_ID = "WT-023";

export function overlayClientTurbines(
  items: readonly WindTurbine[],
  workflow: ClientWorkflow,
): readonly WindTurbine[] {
  return items.map((item) =>
    item.id === FEATURED_TURBINE_ID ? { ...item, healthScore: workflow.turbineHealthScore } : item,
  );
}

export function overlayClientAlarms(
  items: readonly Alarm[],
  workflow: ClientWorkflow,
): readonly Alarm[] {
  if (workflow.workOrderStatus !== "completed") return items;
  return items.map((item) =>
    item.missionId === FEATURED_MISSION_ID
      ? {
          ...item,
          status: "resolved" as const,
          aiStatus: "action-created" as const,
          acknowledgedAt: item.acknowledgedAt ?? item.triggeredAt,
          resolvedAt: item.resolvedAt ?? item.triggeredAt,
        }
      : item,
  );
}

export function overlayClientMissions(
  items: readonly Mission[],
  workflow: ClientWorkflow,
): readonly Mission[] {
  return items.map((item) =>
    item.id === FEATURED_MISSION_ID
      ? { ...item, status: workflow.missionStatus, progressPercent: workflow.missionProgress }
      : item,
  );
}

export function overlayClientDecisions(
  items: readonly Decision[],
  workflow: ClientWorkflow,
): readonly Decision[] {
  return items.map((item) =>
    item.missionId === FEATURED_MISSION_ID
      ? {
          ...item,
          status: workflow.decisionStatus,
          approval: workflow.approval
            ? {
                required: true,
                action: workflow.approval.action,
                selectedAlternativeId: workflow.approval.selectedAlternativeId,
                approver: workflow.approval.approver,
                approverRole: workflow.approval.approverRole,
                timestamp: workflow.approval.timestamp,
                reason: workflow.approval.reason,
                comment: workflow.approval.comment,
              }
            : {
                ...item.approval,
                action: null,
                selectedAlternativeId: null,
                approver: null,
                approverRole: null,
                timestamp: null,
                reason: null,
                comment: null,
              },
        }
      : item,
  );
}

export function overlayClientWorkOrders(
  items: readonly WorkOrder[],
  workflow: ClientWorkflow & Pick<DemoWorkflowState, "completedTaskIds">,
): readonly WorkOrder[] {
  const selectedPlan =
    workflow.approval?.action === "approve"
      ? getServerWorkflowAlternativePlan(workflow.approval.selectedAlternativeId)
      : null;
  return items.map((item) =>
    item.id === "WO-20260823-017"
      ? {
          ...item,
          ...(selectedPlan
            ? {
                issue: selectedPlan.workOrderIssue,
                description: selectedPlan.workOrderDescription,
                assignedTeam: selectedPlan.assignedTeam,
                estimatedDurationHours: selectedPlan.estimatedDurationHours,
                requiredTools: selectedPlan.requiredTools,
                ppeRequirements: selectedPlan.ppeRequirements,
                safetyProcedures: selectedPlan.safetyProcedures,
                spareParts: selectedPlan.id === "ALT-0823-C" ? [] : item.spareParts,
              }
            : {}),
          status: workflow.workOrderStatus,
          tasks: item.tasks.map((task, index) => ({
            ...task,
            title: selectedPlan?.taskTitles[index] ?? task.title,
            completed: workflow.completedTaskIds.includes(task.id),
            completionNote: workflow.completedTaskIds.includes(task.id)
              ? "已按所选方案完成并记录现场证据"
              : null,
          })),
        }
      : item,
  );
}

export function overlayClientAgents(
  items: readonly Agent[],
  workflow: ClientWorkflow,
): readonly Agent[] {
  return items.map((item) => {
    if (item.currentMissionId !== FEATURED_MISSION_ID) return item;
    if (workflow.missionStatus === "completed") {
      return { ...item, status: "idle" as const, currentTask: null };
    }
    if (workflow.workOrderStatus === "in-progress") {
      return {
        ...item,
        status: item.layer === "review" ? ("reviewing" as const) : ("working" as const),
      };
    }
    if (workflow.decisionStatus === "under-review") {
      return {
        ...item,
        status:
          item.layer === "review"
            ? ("reviewing" as const)
            : item.layer === "decision"
              ? ("thinking" as const)
              : ("waiting" as const),
      };
    }
    return item;
  });
}

export function deriveWorkflowKpis(
  turbines: readonly WindTurbine[],
  alarms: readonly Alarm[],
  missions: readonly Mission[],
  agents: readonly Agent[],
) {
  return {
    averageHealth:
      turbines.reduce((total, item) => total + item.healthScore, 0) / Math.max(1, turbines.length),
    activeAlarmCount: alarms.filter(
      (item) => item.status !== "resolved" && item.status !== "suppressed",
    ).length,
    activeMissionCount: missions.filter((item) => item.status !== "completed").length,
    activeAgentCount: agents.filter((item) =>
      ["thinking", "working", "reviewing"].includes(item.status),
    ).length,
    onlineAgentCount: agents.filter((item) => item.status !== "offline" && item.status !== "failed")
      .length,
  };
}
