import { agents } from "./agent-data";
import { validateArchiveData } from "./archive-data";
import { turbines, windFarm } from "./farm-data";
import { healthAssessments } from "./health-data";
import { knowledgeDocuments } from "./knowledge-data";
import { alarms, decisions, evidenceItems, missions, workOrders } from "./operations-data";
import { maintenanceCrews, maintenanceTools, serviceVessels, spareParts } from "./resource-data";
import { weatherWindows } from "./telemetry-data";

/**
 * Lightweight referential-integrity audit for fixture tests and future edits.
 * An empty array means every checked cross-domain link is valid.
 */
export const validateDomainData = (): readonly string[] => {
  const errors: string[] = [...validateArchiveData()];
  const turbineIds = new Set(turbines.map((turbine) => turbine.id));
  const agentIds = new Set(agents.map((agent) => agent.id));
  const missionIds = new Set(missions.map((mission) => mission.id));
  const alarmIds = new Set(alarms.map((alarm) => alarm.id));
  const evidenceIds = new Set(evidenceItems.map((evidence) => evidence.id));
  const decisionIds = new Set(decisions.map((decision) => decision.id));
  const workOrderIds = new Set(workOrders.map((workOrder) => workOrder.id));
  const weatherWindowIds = new Set(weatherWindows.map((window) => window.id));
  const knowledgeIds = new Set(knowledgeDocuments.map((document) => document.id));

  const activeMissionCount = missions.filter((mission) => mission.status !== "completed").length;
  if (windFarm.activeMissionCount !== activeMissionCount) {
    errors.push(
      `${windFarm.id}: active mission summary ${windFarm.activeMissionCount} != ${activeMissionCount}`,
    );
  }
  const unresolvedAlarmCount = alarms.filter((alarm) => alarm.status !== "resolved").length;
  if (windFarm.activeAlarmCount !== unresolvedAlarmCount) {
    errors.push(
      `${windFarm.id}: active alarm summary ${windFarm.activeAlarmCount} != ${unresolvedAlarmCount}`,
    );
  }

  for (const assessment of healthAssessments) {
    if (!turbineIds.has(assessment.turbineId)) {
      errors.push(`${assessment.id}: unknown turbine ${assessment.turbineId}`);
    }
    if (assessment.healthScore < 0 || assessment.healthScore > 100) {
      errors.push(`${assessment.id}: health score is outside 0..100`);
    }
    if (assessment.anomalyScore < 0 || assessment.anomalyScore > 1) {
      errors.push(`${assessment.id}: anomaly score is outside 0..1`);
    }
  }

  for (const mission of missions) {
    if (!turbineIds.has(mission.turbineId)) {
      errors.push(`${mission.id}: unknown turbine ${mission.turbineId}`);
    }
    if (!agentIds.has(mission.leadAgentId)) {
      errors.push(`${mission.id}: unknown lead agent ${mission.leadAgentId}`);
    }
    for (const agentId of mission.agentIds) {
      if (!agentIds.has(agentId)) errors.push(`${mission.id}: unknown agent ${agentId}`);
    }
    for (const alarmId of mission.alarmIds) {
      if (!alarmIds.has(alarmId)) errors.push(`${mission.id}: unknown alarm ${alarmId}`);
      const alarm = alarms.find((candidate) => candidate.id === alarmId);
      if (alarm && alarm.missionId !== mission.id) {
        errors.push(`${mission.id}: alarm ${alarmId} does not reciprocate mission link`);
      }
    }
    for (const evidenceId of mission.evidenceIds) {
      if (!evidenceIds.has(evidenceId)) {
        errors.push(`${mission.id}: unknown evidence ${evidenceId}`);
      }
    }
    if (mission.decisionId && !decisionIds.has(mission.decisionId)) {
      errors.push(`${mission.id}: unknown decision ${mission.decisionId}`);
    }
    if (mission.workOrderId && !workOrderIds.has(mission.workOrderId)) {
      errors.push(`${mission.id}: unknown work order ${mission.workOrderId}`);
    }
  }

  for (const alarm of alarms) {
    if (!turbineIds.has(alarm.turbineId)) {
      errors.push(`${alarm.id}: unknown turbine ${alarm.turbineId}`);
    }
    if (alarm.missionId && !missionIds.has(alarm.missionId)) {
      errors.push(`${alarm.id}: unknown mission ${alarm.missionId}`);
    }
    if (alarm.missionId) {
      const mission = missions.find((candidate) => candidate.id === alarm.missionId);
      if (mission && !mission.alarmIds.includes(alarm.id)) {
        errors.push(`${alarm.id}: mission ${alarm.missionId} does not reciprocate alarm link`);
      }
    }
    for (const evidenceId of alarm.evidenceIds) {
      if (!evidenceIds.has(evidenceId)) {
        errors.push(`${alarm.id}: unknown evidence ${evidenceId}`);
      }
    }
  }

  for (const decision of decisions) {
    if (!missionIds.has(decision.missionId)) {
      errors.push(`${decision.id}: unknown mission ${decision.missionId}`);
    }
    if (!decision.alternatives.some((item) => item.id === decision.recommendedAlternativeId)) {
      errors.push(`${decision.id}: recommended alternative is missing`);
    }
    if (decision.weatherWindowId && !weatherWindowIds.has(decision.weatherWindowId)) {
      errors.push(`${decision.id}: unknown weather window ${decision.weatherWindowId}`);
    }
    for (const evidenceId of decision.evidenceIds) {
      if (!evidenceIds.has(evidenceId)) {
        errors.push(`${decision.id}: unknown evidence ${evidenceId}`);
      }
    }
  }

  for (const workOrder of workOrders) {
    if (!turbineIds.has(workOrder.turbineId)) {
      errors.push(`${workOrder.id}: unknown turbine ${workOrder.turbineId}`);
    }
    if (workOrder.relatedMissionId && !missionIds.has(workOrder.relatedMissionId)) {
      errors.push(`${workOrder.id}: unknown mission ${workOrder.relatedMissionId}`);
    }
    if (workOrder.decisionId && !decisionIds.has(workOrder.decisionId)) {
      errors.push(`${workOrder.id}: unknown decision ${workOrder.decisionId}`);
    }
  }

  for (const agent of agents) {
    if (agent.currentMissionId && !missionIds.has(agent.currentMissionId)) {
      errors.push(`${agent.id}: unknown current mission ${agent.currentMissionId}`);
    }
    for (const documentId of agent.knowledgeSourceIds) {
      if (!knowledgeIds.has(documentId)) {
        errors.push(`${agent.id}: unknown knowledge source ${documentId}`);
      }
    }
  }

  for (const evidence of evidenceItems) {
    if (!missionIds.has(evidence.missionId)) {
      errors.push(`${evidence.id}: unknown mission ${evidence.missionId}`);
    }
    if (!turbineIds.has(evidence.turbineId)) {
      errors.push(`${evidence.id}: unknown turbine ${evidence.turbineId}`);
    }
  }

  for (const part of spareParts) {
    if (part.onHand !== part.available + part.reserved) {
      errors.push(`${part.id}: inventory balance is invalid`);
    }
    for (const workOrderId of part.reservedForWorkOrderIds) {
      if (!workOrderIds.has(workOrderId)) {
        errors.push(`${part.id}: unknown reserved work order ${workOrderId}`);
      }
    }
  }

  for (const resource of [...maintenanceCrews, ...serviceVessels, ...maintenanceTools]) {
    if (resource.assignedWorkOrderId && !workOrderIds.has(resource.assignedWorkOrderId)) {
      errors.push(`${resource.id}: unknown assigned work order ${resource.assignedWorkOrderId}`);
    }
  }

  return errors;
};
