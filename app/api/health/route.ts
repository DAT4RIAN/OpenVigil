import {
  activityEvents,
  agentToolCatalog,
  agents,
  alarmArchive,
  alarms,
  decisions,
  demoDatasetCounts,
  evidenceItems,
  failureCases,
  historicalWorkOrders,
  knowledgeDocuments,
  maintenanceCrews,
  maintenanceTools,
  missions,
  scadaSeries,
  serviceVessels,
  spareParts,
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
          unresolvedAlarms: alarms.filter((alarm) => alarm.status !== "resolved").length,
          missions: missions.length,
          activeMissions: missions.filter((mission) => mission.status !== "completed").length,
          decisions: decisions.length,
          evidence: evidenceItems.length,
          agents: agents.length,
          workOrders: workOrders.length,
          knowledgeDocuments: knowledgeDocuments.length,
          weatherWindows: weatherWindows.length,
          agentEvents: activityEvents.length,
          agentTools: agentToolCatalog.length,
          spareParts: spareParts.length,
          maintenanceCrews: maintenanceCrews.length,
          serviceVessels: serviceVessels.length,
          maintenanceTools: maintenanceTools.length,
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
