import { fleetSummary, turbines, windFarm } from "@/lib";
import { overlayWorkflowTurbine } from "@/lib/server-workflow-overlays";

import { collectionResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(): Promise<Response> {
  const workflow = await readWorkflowForApi();
  const currentTurbines = overlayWorkflowTurbine(turbines, workflow.snapshot);
  const averageHealthScore = Number(
    (
      currentTurbines.reduce((total, turbine) => total + turbine.healthScore, 0) /
      currentTurbines.length
    ).toFixed(1),
  );
  return collectionResponse(currentTurbines, {
    farmId: windFarm.id,
    fleet: { ...fleetSummary, averageHealthScore },
    snapshotAt: workflow.snapshot.updatedAt,
    workflowPersistence: workflow.persistence,
    workflowRevision: workflow.snapshot.revision,
  });
}
