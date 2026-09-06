import {
  activityEvents,
  agents,
  alarms,
  decisions,
  evidenceItems,
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
        windFarms: 1,
        turbines: turbines.length,
        subsystems: subsystemHealth.length,
        scadaSeries: scadaSeries.length,
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
    },
    healthy ? 200 : 503,
  );
}
