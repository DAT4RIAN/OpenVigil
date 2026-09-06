import {
  getAlarmsForTurbine,
  getTurbine,
  missions,
  subsystemHealth,
  windFarm,
  workOrders,
} from "@/lib";

import { jsonResponse, turbineNotFoundResponse } from "../../_shared";

interface TurbineRouteContext {
  readonly params: Promise<{ readonly id: string }>;
}

export async function GET(
  _request: Request,
  context: TurbineRouteContext,
): Promise<Response> {
  const { id } = await context.params;
  const turbine = getTurbine(id);

  if (!turbine) return turbineNotFoundResponse(id);

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
    data: turbine,
    relationships: {
      alarmIds,
      missionIds,
      workOrderIds,
      subsystemIds,
    },
    meta: {
      snapshotAt: windFarm.lastUpdatedAt,
    },
  });
}
