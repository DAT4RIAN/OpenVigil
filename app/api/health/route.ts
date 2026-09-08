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
  workOrders,
} from "@/lib";

import { jsonResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(): Promise<Response> {
  const errors = validateDomainData();
  const healthy = errors.length === 0;
  const workflow = await readWorkflowForApi();
  const workflowCompleted = workflow.snapshot.mission.status === "completed";

  return jsonResponse(
    {
      status: healthy ? "healthy" : "degraded",
      service: "windops-worker-api",
      version: 1,
      snapshotAt: workflow.snapshot.updatedAt,
      deterministic: true,
      readOnly: !workflow.writable,
      persistence: {
        workflow: workflow.persistence,
        workflowWritable: workflow.writable,
        workflowRevision: workflow.snapshot.revision,
        fixtureCatalog: "read-only",
      },
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
          activeMissions:
            missions.filter((mission) => mission.status !== "completed").length -
            (workflowCompleted ? 1 : 0),
          decisions: decisions.length,
          evidence: evidenceItems.length,
          agents: agents.length,
          workOrders: workOrders.length,
          knowledgeDocuments:
            knowledgeDocuments.length + (workflow.snapshot.knowledgeCaseId ? 1 : 0),
          weatherWindows: weatherWindows.length,
          agentEvents: activityEvents.length,
          agentTools: agentToolCatalog.length,
          spareParts: spareParts.length,
          maintenanceCrews: maintenanceCrews.length,
          serviceVessels: serviceVessels.length,
          maintenanceTools: maintenanceTools.length,
          workflowAuditEvents: workflow.snapshot.auditEvents.length,
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
