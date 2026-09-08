import { fleetSummary, getTurbine, windFarm } from "@/lib";

import { collectionResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(): Promise<Response> {
  const workflow = await readWorkflowForApi();
  const baselineHealth = getTurbine(workflow.snapshot.turbineId)?.healthScore ?? 68;
  const averageHealthScore = Number(
    (
      (windFarm.averageHealthScore * windFarm.turbineCount -
        baselineHealth +
        workflow.snapshot.health.turbineScore) /
      windFarm.turbineCount
    ).toFixed(1),
  );
  const currentFarm = {
    ...windFarm,
    averageHealthScore,
    activeMissionCount:
      windFarm.activeMissionCount - (workflow.snapshot.mission.status === "completed" ? 1 : 0),
    lastUpdatedAt: workflow.snapshot.updatedAt,
  };
  return collectionResponse([currentFarm], {
    fleet: { ...fleetSummary, averageHealthScore },
    snapshotAt: workflow.snapshot.updatedAt,
    workflowPersistence: workflow.persistence,
    workflowRevision: workflow.snapshot.revision,
  });
}
