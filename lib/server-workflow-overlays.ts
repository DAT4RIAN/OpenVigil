import type { ServerWorkflowSnapshot } from "./server-workflow-contract";
import type { HealthAssessment, KnowledgeDocument, Mission, WindTurbine, WorkOrder } from "./types";

export function overlayWorkflowMission(
  items: readonly Mission[],
  snapshot: ServerWorkflowSnapshot,
): readonly Mission[] {
  return items.map((mission) =>
    mission.id === snapshot.mission.id
      ? {
          ...mission,
          status: snapshot.mission.status,
          progressPercent: snapshot.mission.progressPercent,
          updatedAt: snapshot.updatedAt,
        }
      : mission,
  );
}

export function overlayWorkflowWorkOrder(
  items: readonly WorkOrder[],
  snapshot: ServerWorkflowSnapshot,
): readonly WorkOrder[] {
  return items.map((workOrder) =>
    workOrder.id === snapshot.workOrder.id
      ? {
          ...workOrder,
          status: snapshot.workOrder.status,
          tasks: workOrder.tasks.map((task) => {
            const serverTask = snapshot.workOrder.tasks.find((item) => item.id === task.id);
            if (!serverTask) return task;
            return {
              ...task,
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
