import type { AgentToolArguments, AgentToolExecutionContext } from "./contracts";
import { requiredTurbine, requiredWorkOrder, workflowSnapshotAt } from "./helpers";
import { overlayWorkflowWorkOrder } from "../server-workflow-overlays";
import { decisions, missions, workOrders } from "../operations-data";
import { historicalWorkOrders } from "../archive-data";
import { AgentToolRuntimeError } from "./contracts";
import { windFarm } from "../farm-data";
import type { WorkOrderPriority, WorkOrderStatus } from "../types";

export const queryMaintenanceHistory = (
  args: AgentToolArguments,
  context: AgentToolExecutionContext,
): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const limit = args.limit as number;
  const liveWorkOrders = context.workflowSnapshot
    ? overlayWorkflowWorkOrder(workOrders, context.workflowSnapshot)
    : workOrders;
  const matching = [...liveWorkOrders, ...historicalWorkOrders]
    .filter((workOrder) => workOrder.turbineId === turbineId)
    .sort(
      (left, right) =>
        Date.parse(right.updatedAt) - Date.parse(left.updatedAt) || left.id.localeCompare(right.id),
    );

  return {
    snapshotAt: workflowSnapshotAt(context),
    turbineId,
    total: matching.length,
    returned: Math.min(limit, matching.length),
    records: matching.slice(0, limit).map((workOrder) => ({
      id: workOrder.id,
      issue: workOrder.issue,
      status: workOrder.status,
      priority: workOrder.priority,
      plannedStart: workOrder.plannedStart,
      deadline: workOrder.deadline,
      updatedAt: workOrder.updatedAt,
      relatedMissionId: workOrder.relatedMissionId,
      decisionId: workOrder.decisionId,
      tasksCompleted: workOrder.tasks.filter((task) => task.completed).length,
      taskCount: workOrder.tasks.length,
    })),
  };
};

export const createDecision = (args: AgentToolArguments): unknown => {
  const missionId = args.missionId as string;
  const mission = missions.find((item) => item.id === missionId);
  if (!mission) {
    throw new AgentToolRuntimeError(
      "MISSION_NOT_FOUND",
      `Mission ${missionId} was not found.`,
      404,
      {
        missionId,
      },
    );
  }
  const sourceDecision = decisions.find((decision) => decision.id === mission.decisionId);
  const recommendedAlternative = sourceDecision?.alternatives.find(
    (alternative) => alternative.id === sourceDecision.recommendedAlternativeId,
  );
  const recommendedAction =
    (args.recommendedAction as string | undefined) ??
    sourceDecision?.recommendedAction ??
    mission.nextAction;

  return {
    dryRun: true,
    persisted: false,
    draft: {
      id: `DRAFT-DECISION-${mission.id}`,
      status: "draft",
      missionId: mission.id,
      turbineId: mission.turbineId,
      incident: mission.title,
      diagnosis: mission.diagnosis,
      confidencePercent: mission.confidencePercent,
      risk: mission.severity,
      recommendedAction,
      recommendedAlternative: recommendedAlternative ?? null,
      evidenceIds: mission.evidenceIds,
      humanApprovalRequired: true,
      sourceDecisionId: sourceDecision?.id ?? null,
      generatedAt: windFarm.lastUpdatedAt,
    },
    notice: "Dry-run draft only. No decision was persisted and no approval state was changed.",
  };
};

export const createWorkOrder = (args: AgentToolArguments): unknown => {
  const missionId = args.missionId as string;
  const mission = missions.find((item) => item.id === missionId);
  if (!mission) {
    throw new AgentToolRuntimeError(
      "MISSION_NOT_FOUND",
      `Mission ${missionId} was not found.`,
      404,
      {
        missionId,
      },
    );
  }
  const decisionId = (args.decisionId as string | undefined) ?? mission.decisionId;
  if (!decisionId) {
    throw new AgentToolRuntimeError(
      "DECISION_REQUIRED",
      `Mission ${missionId} has no linked decision; provide decisionId.`,
      422,
      { missionId },
    );
  }
  const decision = decisions.find((item) => item.id === decisionId);
  if (!decision) {
    throw new AgentToolRuntimeError(
      "DECISION_NOT_FOUND",
      `Decision ${decisionId} was not found.`,
      404,
      {
        decisionId,
      },
    );
  }
  if (decision.missionId !== missionId) {
    throw new AgentToolRuntimeError(
      "DECISION_MISSION_MISMATCH",
      `Decision ${decisionId} does not belong to mission ${missionId}.`,
      422,
      { missionId, decisionId, decisionMissionId: decision.missionId },
    );
  }
  const template = workOrders.find((workOrder) => workOrder.id === mission.workOrderId);
  const priority =
    (args.priority as WorkOrderPriority | undefined) ?? template?.priority ?? mission.severity;

  return {
    dryRun: true,
    persisted: false,
    draft: {
      id: `DRAFT-WO-${mission.id}`,
      status: "draft",
      turbineId: mission.turbineId,
      relatedMissionId: mission.id,
      decisionId: decision.id,
      issue: template?.issue ?? mission.title,
      description: template?.description ?? decision.recommendedAction,
      priority,
      riskLevel: decision.risk,
      assignedTeam: template?.assignedTeam ?? "Unassigned",
      plannedStart: template?.plannedStart ?? null,
      deadline: template?.deadline ?? mission.targetResolutionAt,
      estimatedDurationHours: template?.estimatedDurationHours ?? null,
      tasks: template?.tasks ?? [],
      ppeRequirements: template?.ppeRequirements ?? [],
      requiredTools: template?.requiredTools ?? [],
      spareParts: template?.spareParts ?? [],
      safetyProcedures: template?.safetyProcedures ?? [],
      generatedAt: windFarm.lastUpdatedAt,
      sourceWorkOrderId: template?.id ?? null,
    },
    notice: "Dry-run draft only. No work order was persisted, scheduled, or dispatched.",
  };
};

export const queryWorkOrders = (
  args: AgentToolArguments,
  context: AgentToolExecutionContext,
): unknown => {
  const workOrderId = (args.workOrderId as string | undefined) ?? null;
  const turbineId = (args.turbineId as string | undefined) ?? null;
  const status = (args.status as WorkOrderStatus | undefined) ?? null;
  const priority = (args.priority as WorkOrderPriority | undefined) ?? null;
  const includeHistorical = args.includeHistorical as boolean;
  const limit = args.limit as number;
  if (turbineId) requiredTurbine(turbineId);
  if (workOrderId) requiredWorkOrder(workOrderId);

  const liveWorkOrders = context.workflowSnapshot
    ? overlayWorkflowWorkOrder(workOrders, context.workflowSnapshot)
    : workOrders;
  const source =
    includeHistorical || workOrderId
      ? [...liveWorkOrders, ...historicalWorkOrders]
      : liveWorkOrders;
  const matching = source
    .filter(
      (workOrder) =>
        (!workOrderId || workOrder.id === workOrderId) &&
        (!turbineId || workOrder.turbineId === turbineId) &&
        (!status || workOrder.status === status) &&
        (!priority || workOrder.priority === priority),
    )
    .sort(
      (left, right) =>
        Date.parse(right.updatedAt) - Date.parse(left.updatedAt) || left.id.localeCompare(right.id),
    );

  return {
    snapshotAt: workflowSnapshotAt(context),
    filters: { workOrderId, turbineId, status, priority, includeHistorical },
    total: matching.length,
    returned: Math.min(limit, matching.length),
    workOrders: matching.slice(0, limit),
  };
};

export const updateWorkOrder = (
  args: AgentToolArguments,
  context: AgentToolExecutionContext,
): unknown => {
  const workOrderId = args.workOrderId as string;
  const currentWorkOrders = context.workflowSnapshot
    ? overlayWorkflowWorkOrder(workOrders, context.workflowSnapshot)
    : workOrders;
  const source = currentWorkOrders.find((workOrder) => workOrder.id === workOrderId);
  if (!source) {
    throw new AgentToolRuntimeError(
      "LIVE_WORK_ORDER_NOT_FOUND",
      `Live work order ${workOrderId} was not found.`,
      404,
      { workOrderId },
    );
  }

  const assignedTeam = (args.assignedTeam as string | undefined) ?? source.assignedTeam;
  const plannedStart = (args.plannedStart as string | undefined) ?? source.plannedStart;
  const deadline = (args.deadline as string | undefined) ?? source.deadline;
  const note = (args.note as string | undefined) ?? null;
  if (Date.parse(plannedStart) >= Date.parse(deadline)) {
    throw new AgentToolRuntimeError(
      "INVALID_WORK_ORDER_SCHEDULE",
      "The proposed plannedStart must be earlier than deadline.",
      422,
      { workOrderId, plannedStart, deadline },
    );
  }

  const proposedChanges = {
    ...(args.assignedTeam === undefined ? {} : { assignedTeam }),
    ...(args.plannedStart === undefined ? {} : { plannedStart }),
    ...(args.deadline === undefined ? {} : { deadline }),
    ...(note === null ? {} : { note }),
  };

  return {
    dryRun: true,
    persisted: false,
    workOrderId,
    before: {
      status: source.status,
      assignedTeam: source.assignedTeam,
      plannedStart: source.plannedStart,
      deadline: source.deadline,
      updatedAt: source.updatedAt,
    },
    proposedChanges,
    draft: {
      ...source,
      assignedTeam,
      plannedStart,
      deadline,
      status: source.status,
      schedulingNote: note,
      sourceUpdatedAt: source.updatedAt,
      generatedAt: workflowSnapshotAt(context),
    },
    notice:
      "Dry-run draft only. No work-order status, assignment, schedule, task, or resource record was persisted.",
  };
};
