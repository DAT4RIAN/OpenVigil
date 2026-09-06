export type * from "./types";

export { agentLayers, agents } from "./agent-data";
export { fleetSummary, turbine023, turbines, windFarm } from "./farm-data";
export { knowledgeDocuments } from "./knowledge-data";
export {
  activityEvents,
  alarms,
  decisions,
  evidenceItems,
  featuredDecision,
  featuredMission,
  missions,
  workOrders,
} from "./operations-data";
export {
  scadaSeries,
  subsystemHealth,
  weatherWindows,
} from "./telemetry-data";

import { agents } from "./agent-data";
import { turbines } from "./farm-data";
import { knowledgeDocuments } from "./knowledge-data";
import {
  activityEvents,
  alarms,
  decisions,
  evidenceItems,
  missions,
  workOrders,
} from "./operations-data";
import { scadaSeries, weatherWindows } from "./telemetry-data";
import type {
  ActivityEvent,
  Agent,
  Alarm,
  Decision,
  EvidenceItem,
  KnowledgeDocument,
  Mission,
  ScadaMetric,
  ScadaSeries,
  WindTurbine,
  WorkOrder,
} from "./types";

const normalizeAssetId = (id: string): string => id.trim().toUpperCase();

/** Return a turbine by canonical ID (for example, `WT-023`). */
export const getTurbine = (id: string): WindTurbine | undefined => {
  const normalized = normalizeAssetId(id);
  return turbines.find((turbine) => turbine.id === normalized);
};

/** Return a mission by canonical ID (for example, `MISSION-2026-0823`). */
export const getMission = (id: string): Mission | undefined => {
  const normalized = normalizeAssetId(id);
  return missions.find((mission) => mission.id === normalized);
};

export const getAgent = (id: string): Agent | undefined =>
  agents.find((agent) => agent.id === id.trim().toLowerCase());

export const getAlarm = (id: string): Alarm | undefined => {
  const normalized = normalizeAssetId(id);
  return alarms.find((alarm) => alarm.id === normalized);
};

export const getWorkOrder = (id: string): WorkOrder | undefined => {
  const normalized = normalizeAssetId(id);
  return workOrders.find((workOrder) => workOrder.id === normalized);
};

export const getDecision = (id: string): Decision | undefined => {
  const normalized = normalizeAssetId(id);
  return decisions.find((decision) => decision.id === normalized);
};

export const getKnowledgeDocument = (
  id: string,
): KnowledgeDocument | undefined => {
  const normalized = normalizeAssetId(id);
  return knowledgeDocuments.find((document) => document.id === normalized);
};

export const getEvidenceForMission = (
  missionId: string,
): readonly EvidenceItem[] => {
  const normalized = normalizeAssetId(missionId);
  return evidenceItems.filter((evidence) => evidence.missionId === normalized);
};

export const getActivityForMission = (
  missionId: string,
): readonly ActivityEvent[] => {
  const normalized = normalizeAssetId(missionId);
  return activityEvents.filter((event) => event.missionId === normalized);
};

export const getAlarmsForTurbine = (
  turbineId: string,
): readonly Alarm[] => {
  const normalized = normalizeAssetId(turbineId);
  return alarms.filter((alarm) => alarm.turbineId === normalized);
};

export const getScadaSeries = (
  metric: ScadaMetric,
  turbineId = "WT-023",
): ScadaSeries | undefined => {
  const normalized = normalizeAssetId(turbineId);
  return scadaSeries.find(
    (series) => series.turbineId === normalized && series.metric === metric,
  );
};

/**
 * Lightweight referential-integrity audit for fixture tests and future edits.
 * An empty array means every checked cross-domain link is valid.
 */
export const validateDomainData = (): readonly string[] => {
  const errors: string[] = [];
  const turbineIds = new Set(turbines.map((turbine) => turbine.id));
  const agentIds = new Set(agents.map((agent) => agent.id));
  const missionIds = new Set(missions.map((mission) => mission.id));
  const alarmIds = new Set(alarms.map((alarm) => alarm.id));
  const evidenceIds = new Set(evidenceItems.map((evidence) => evidence.id));
  const decisionIds = new Set(decisions.map((decision) => decision.id));
  const workOrderIds = new Set(workOrders.map((workOrder) => workOrder.id));
  const weatherWindowIds = new Set(weatherWindows.map((window) => window.id));
  const knowledgeIds = new Set(knowledgeDocuments.map((document) => document.id));

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

  return errors;
};

