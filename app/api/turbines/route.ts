import { fleetSummary, turbines, windFarm } from "@/lib/farm-data";
import { overlayWorkflowTurbine } from "@/lib/server-workflow-overlays";
import { productionTurbinesResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";

import { collectionResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionTurbinesResponse(request);
  }
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
