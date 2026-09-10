import { decisions } from "@/lib/operations-data";
import { productionDecisionsResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";
import { overlayWorkflowDecision } from "@/lib/server-workflow-overlays";

import { collectionResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionDecisionsResponse(request);
  }
  const workflow = await readWorkflowForApi();
  return collectionResponse(overlayWorkflowDecision(decisions, workflow.snapshot), {
    snapshotAt: workflow.snapshot.updatedAt,
    workflowPersistence: workflow.persistence,
    workflowRevision: workflow.snapshot.revision,
  });
}
