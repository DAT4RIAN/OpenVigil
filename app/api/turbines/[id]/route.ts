import { getTurbine, windFarm } from "@/lib/farm-data";
import { getAlarmsForTurbine, missions, workOrders } from "@/lib/operations-data";
import { subsystemHealth } from "@/lib/telemetry-data";
import { overlayWorkflowTurbine } from "@/lib/server-workflow-overlays";

import { jsonResponse, turbineNotFoundResponse } from "../../_shared";
import { readWorkflowForApi } from "../../_workflow";

interface TurbineRouteContext {
  readonly params: Promise<{ readonly id: string }>;
}

export async function GET(_request: Request, context: TurbineRouteContext): Promise<Response> {
  const { id } = await context.params;
  const turbine = getTurbine(id);

  if (!turbine) return turbineNotFoundResponse(id);
  const workflow = await readWorkflowForApi();
  const currentTurbine = overlayWorkflowTurbine([turbine], workflow.snapshot)[0] ?? turbine;

  const alarmIds = getAlarmsForTurbine(turbine.id).map((alarm) => alarm.id);
  const missionIds = missions
    .filter((mission) => mission.turbineId === turbine.id)
    .map((mission) => mission.id);
  const workOrderIds = workOrders
    .filter((workOrder) => workOrder.turbineId === turbine.id)
    .map((workOrder) => workOrder.id);
  const subsystemIds = subsystemHealth
    .filter((subsystem) => subsystem.turbineId === turbine.id)
    .map((subsystem) => subsystem.id);

  return jsonResponse({
    data: currentTurbine,
    relationships: {
      alarmIds,
      missionIds,
      workOrderIds,
      subsystemIds,
    },
    meta: {
      snapshotAt:
        currentTurbine.id === workflow.snapshot.turbineId
          ? workflow.snapshot.updatedAt
          : windFarm.lastUpdatedAt,
      workflowPersistence: workflow.persistence,
      workflowRevision: workflow.snapshot.revision,
    },
  });
}
