import { getFeaturedMissionNarrative } from "./demo-workflow";
import {
  getServerWorkflowAlternativePlan,
  type ServerWorkflowSnapshot,
} from "./server-workflow-contract";
import type {
  Agent,
  AgentStatus,
  Alarm,
  Decision,
  HealthAssessment,
  KnowledgeDocument,
  Mission,
  WindTurbine,
  WorkOrder,
} from "./types";

const workflowMissionNarrative = (
  snapshot: ServerWorkflowSnapshot,
): Pick<Mission, "summary" | "nextAction"> =>
  getFeaturedMissionNarrative({
    missionStatus: snapshot.mission.status,
    decisionStatus: snapshot.decision.status,
    workOrderStatus: snapshot.workOrder.status,
    knowledgeCaseId: snapshot.knowledgeCaseId,
    approval: snapshot.decision.approval
      ? {
          action: snapshot.decision.approval.action,
          selectedAlternativeId: snapshot.decision.approval.selectedAlternativeId,
          approver: snapshot.decision.approval.actor.name,
          approverRole: snapshot.decision.approval.actor.role ?? "",
          timestamp: snapshot.decision.approval.timestamp,
          reason: snapshot.decision.approval.reason,
          comment: snapshot.decision.approval.comment,
        }
      : null,
  });

export function overlayWorkflowMission(
  items: readonly Mission[],
  snapshot: ServerWorkflowSnapshot,
): readonly Mission[] {
  return items.map((mission) =>
    mission.id === snapshot.mission.id
      ? {
          ...mission,
          ...workflowMissionNarrative(snapshot),
          status: snapshot.mission.status,
          progressPercent: snapshot.mission.progressPercent,
          updatedAt: snapshot.updatedAt,
        }
      : mission,
  );
}

export function overlayWorkflowDecision(
  items: readonly Decision[],
  snapshot: ServerWorkflowSnapshot,
): readonly Decision[] {
  return items.map((decision) => {
    if (decision.id !== snapshot.decision.id) return decision;
    const approval = snapshot.decision.approval;
    return {
      ...decision,
      status: snapshot.decision.status,
      approval: {
        required: snapshot.decision.approvalRequired,
        action: approval?.action ?? null,
        selectedAlternativeId: approval?.selectedAlternativeId ?? null,
        approver: approval?.actor.name ?? null,
        approverRole: approval?.actor.role ?? null,
        timestamp: approval?.timestamp ?? null,
        reason: approval?.reason ?? null,
        comment: approval?.comment ?? null,
      },
      updatedAt: snapshot.updatedAt,
    };
  });
}

export function overlayWorkflowAlarms(
  items: readonly Alarm[],
  snapshot: ServerWorkflowSnapshot,
): readonly Alarm[] {
  if (snapshot.workOrder.status !== "completed") return items;
  return items.map((alarm) =>
    alarm.missionId === snapshot.mission.id
      ? {
          ...alarm,
          status: "resolved",
          aiStatus: "action-created",
          acknowledgedAt: alarm.acknowledgedAt ?? snapshot.updatedAt,
          resolvedAt: snapshot.updatedAt,
        }
      : alarm,
  );
}

const workflowAgentState = (
  agent: Agent,
  snapshot: ServerWorkflowSnapshot,
): { readonly status: AgentStatus; readonly currentTask: string | null } => {
  if (snapshot.mission.status === "completed") {
    return { status: "idle", currentTask: null };
  }

  if (snapshot.workOrder.status === "in-progress") {
    const progress = `${snapshot.workOrder.completedTaskCount}/${snapshot.workOrder.totalTaskCount}`;
    if (agent.layer === "review") {
      return {
        status: "reviewing",
        currentTask: `复核 WT-023 现场执行中的${agent.role}约束（${progress}）`,
      };
    }
    return {
      status: "working",
      currentTask:
        agent.layer === "execution"
          ? `执行 WT-023 ${agent.role}任务（${progress}）`
          : `监测 WT-023 现场执行并更新${agent.role}结论（${progress}）`,
    };
  }

  if (snapshot.decision.status === "approved" || snapshot.workOrder.status === "scheduled") {
    return agent.layer === "review"
      ? {
          status: "waiting",
          currentTask: `WT-023 方案已批准，等待${agent.role}执行复核`,
        }
      : {
          status: agent.layer === "execution" ? "working" : "waiting",
          currentTask:
            agent.layer === "execution"
              ? `准备 WT-023 已批准的${agent.role}任务`
              : `跟踪 WT-023 已批准方案的${agent.role}边界`,
        };
  }

  if (
    snapshot.decision.status === "rejected" ||
    snapshot.decision.status === "revision-requested"
  ) {
    return agent.layer === "execution"
      ? {
          status: "waiting",
          currentTask: `等待 WT-023 方案修订与重新审批后执行${agent.role}任务`,
        }
      : {
          status: agent.layer === "review" ? "reviewing" : "thinking",
          currentTask: `修订 WT-023 ${agent.role}结论并准备重新审核`,
        };
  }

  return agent.layer === "review"
    ? {
        status: "reviewing",
        currentTask: `审核 WT-023 高风险方案的${agent.role}要求`,
      }
    : {
        status: agent.layer === "decision" ? "thinking" : "waiting",
        currentTask:
          agent.layer === "decision"
            ? `支持 WT-023 高风险方案的${agent.role}人工复核`
            : `等待 WT-023 人工审批后执行${agent.role}任务`,
      };
};

export function overlayWorkflowAgents(
  items: readonly Agent[],
  snapshot: ServerWorkflowSnapshot,
): readonly Agent[] {
  return items.map((agent) =>
    agent.currentMissionId === snapshot.mission.id
      ? {
          ...agent,
          ...workflowAgentState(agent, snapshot),
          lastActiveAt: snapshot.updatedAt,
        }
      : agent,
  );
}

export function overlayWorkflowWorkOrder(
  items: readonly WorkOrder[],
  snapshot: ServerWorkflowSnapshot,
): readonly WorkOrder[] {
  const selectedPlan = getServerWorkflowAlternativePlan(snapshot.workOrder.alternativeId);
  return items.map((workOrder) =>
    workOrder.id === snapshot.workOrder.id
      ? {
          ...workOrder,
          ...(selectedPlan
            ? {
                issue: selectedPlan.workOrderIssue,
                description: selectedPlan.workOrderDescription,
                assignedTeam: selectedPlan.assignedTeam,
                estimatedDurationHours: selectedPlan.estimatedDurationHours,
                requiredTools: selectedPlan.requiredTools,
                ppeRequirements: selectedPlan.ppeRequirements,
                safetyProcedures: selectedPlan.safetyProcedures,
                spareParts: selectedPlan.id === "ALT-0823-C" ? [] : workOrder.spareParts,
              }
            : {}),
          status: snapshot.workOrder.status,
          tasks: workOrder.tasks.map((task) => {
            const serverTask = snapshot.workOrder.tasks.find((item) => item.id === task.id);
            if (!serverTask) return task;
            return {
              ...task,
              title: serverTask.title,
              completed: serverTask.completed,
              completionNote: serverTask.completed
                ? `${serverTask.completedBy ?? "现场班组"} · ${serverTask.completedAt ?? snapshot.updatedAt}`
                : null,
            };
          }),
          updatedAt: snapshot.updatedAt,
        }
      : workOrder,
  );
}

export function overlayWorkflowHealth(
  items: readonly HealthAssessment[],
  snapshot: ServerWorkflowSnapshot,
): readonly HealthAssessment[] {
  return items.map((assessment) => {
    if (assessment.turbineId !== snapshot.turbineId) return assessment;
    const closed = snapshot.workOrder.status === "completed";
    return {
      ...assessment,
      healthScore: snapshot.health.turbineScore,
      state:
        snapshot.health.turbineScore >= 90
          ? "healthy"
          : snapshot.health.turbineScore >= 75
            ? "watch"
            : snapshot.health.turbineScore >= 60
              ? "degraded"
              : "critical",
      trend: closed ? "improving" : assessment.trend,
      riskLevel: closed ? "medium" : assessment.riskLevel,
      failureProbability30d: closed ? 12 : assessment.failureProbability30d,
      remainingUsefulLifeDays: closed ? 126 : assessment.remainingUsefulLifeDays,
      anomalyScore: closed ? 0.42 : assessment.anomalyScore,
      primaryFinding: closed ? "主轴承检查与复测完成，健康趋势恢复" : assessment.primaryFinding,
      assessedAt: snapshot.updatedAt,
    };
  });
}

export function overlayWorkflowTurbine(
  items: readonly WindTurbine[],
  snapshot: ServerWorkflowSnapshot,
): readonly WindTurbine[] {
  return items.map((turbine) =>
    turbine.id === snapshot.turbineId
      ? {
          ...turbine,
          healthScore: snapshot.health.turbineScore,
        }
      : turbine,
  );
}

export function workflowKnowledgeDocument(
  snapshot: ServerWorkflowSnapshot,
): KnowledgeDocument | null {
  if (!snapshot.knowledgeCaseId) return null;
  const knowledgeEvent = [...snapshot.auditEvents]
    .reverse()
    .find((event) => event.kind === "knowledge");
  return {
    id: snapshot.knowledgeCaseId,
    title: "WT-023 主轴承检查、处置与复测闭环案例",
    type: "incident-case",
    equipment: "WT-023 / 主轴承",
    manufacturer: "WindOps D1 Workflow",
    version: "Server closed-loop v1",
    updatedAt: knowledgeEvent?.timestamp ?? snapshot.updatedAt,
    vectorized: false,
    pageCount: 14,
    language: "zh-CN",
    tags: ["WT-023", "主轴承", "闭环验证", "健康度 63→78", "D1 持久化"],
    summary:
      "人工审批、五项现场任务、复测验证与知识沉淀均已完成；主轴承健康度由 63 提升至 78，审计记录持久化在 D1。",
    relatedTurbineIds: [snapshot.turbineId],
    relatedMissionIds: [snapshot.mission.id],
  };
}

export function overlayWorkflowKnowledge(
  items: readonly KnowledgeDocument[],
  snapshot: ServerWorkflowSnapshot,
): readonly KnowledgeDocument[] {
  const generated = workflowKnowledgeDocument(snapshot);
  if (!generated) return items;
  return [generated, ...items.filter((item) => item.id !== generated.id)];
}
