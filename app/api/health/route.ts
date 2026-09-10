import { agents } from "@/lib/agent-data";
import { agentToolCatalog } from "@/lib/agent-tool-runtime";
import {
  alarmArchive,
  demoDatasetCounts,
  failureCases,
  historicalWorkOrders,
} from "@/lib/archive-data";
import { validateDomainData } from "@/lib/domain-data-validation";
import { turbines } from "@/lib/farm-data";
import { knowledgeDocuments } from "@/lib/knowledge-data";
import {
  activityEvents,
  alarms,
  decisions,
  evidenceItems,
  missions,
  workOrders,
} from "@/lib/operations-data";
import {
  maintenanceCrews,
  maintenanceTools,
  serviceVessels,
  spareParts,
} from "@/lib/resource-data";
import { scadaSeries, subsystemHealth, weatherWindows } from "@/lib/telemetry-data";

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
