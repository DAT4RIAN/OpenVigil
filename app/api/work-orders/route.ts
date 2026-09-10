import { historicalWorkOrders, windFarm, workOrders } from "@/lib";
import { productionWorkOrdersResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";
import { overlayWorkflowWorkOrder } from "@/lib/server-workflow-overlays";

import { collectionResponse, errorResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionWorkOrdersResponse(request);
  }
  const requestedScope = new URL(request.url).searchParams.get("scope");

  if (requestedScope !== null && requestedScope !== "live" && requestedScope !== "archive") {
    return errorResponse(
      "INVALID_SCOPE",
      'The scope query parameter must be either "live" or "archive".',
    );
  }

  const scope = requestedScope ?? "live";
  const workflow = await readWorkflowForApi();
  const data =
    scope === "archive"
      ? historicalWorkOrders
      : overlayWorkflowWorkOrder(workOrders, workflow.snapshot);

  return collectionResponse(data, {
    scope,
    snapshotAt: scope === "archive" ? windFarm.lastUpdatedAt : workflow.snapshot.updatedAt,
    workflowPersistence: workflow.persistence,
    workflowRevision: workflow.snapshot.revision,
  });
}
