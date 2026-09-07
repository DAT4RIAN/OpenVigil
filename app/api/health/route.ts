import {
  activityEvents,
  agents,
  alarmArchive,
  alarms,
  decisions,
  demoDatasetCounts,
  evidenceItems,
  failureCases,
  historicalWorkOrders,
  knowledgeDocuments,
  missions,
  scadaSeries,
  subsystemHealth,
  turbines,
  validateDomainData,
  weatherWindows,
  windFarm,
  workOrders,
} from "@/lib";

import { jsonResponse } from "../_shared";

export function GET(): Response {
  const errors = validateDomainData();
  const healthy = errors.length === 0;

  return jsonResponse(
    {
      status: healthy ? "healthy" : "degraded",
      service: "windops-mock-api",
      version: 1,
      snapshotAt: windFarm.lastUpdatedAt,
      deterministic: true,
      readOnly: true,
      integrity: {
        valid: healthy,
        errorCount: errors.length,
        errors,
      },
      counts: {
        live: {
          windFarms: 1,
          turbines: turbines.length,
          subsystems: subsystemHealth.length,
          scadaSeries: scadaSeries.length,
          scadaPoints: scadaSeries.reduce((total, series) => total + series.points.length, 0),
          alarms: alarms.length,
          missions: missions.length,
          decisions: decisions.length,
          evidence: evidenceItems.length,
          agents: agents.length,
          workOrders: workOrders.length,
          knowledgeDocuments: knowledgeDocuments.length,
          weatherWindows: weatherWindows.length,
          agentEvents: activityEvents.length,
        },
        archive: {
          scadaMeasurements: demoDatasetCounts.scadaMeasurements,
          alarms: alarmArchive.length,
          historicalWorkOrders: historicalWorkOrders.length,
          failureCases: failureCases.length,
        },
        dataset: demoDatasetCounts,
      },
    },
    healthy ? 200 : 503,
  );
}
