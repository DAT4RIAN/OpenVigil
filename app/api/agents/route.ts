import { agents } from "@/lib/agent-data";
import { productionAgentsResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";
import { overlayWorkflowAgents } from "@/lib/server-workflow-overlays";

import { collectionResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionAgentsResponse(request);
  }
  const workflow = await readWorkflowForApi();
  return collectionResponse(overlayWorkflowAgents(agents, workflow.snapshot), {
    snapshotAt: workflow.snapshot.updatedAt,
    workflowPersistence: workflow.persistence,
    workflowRevision: workflow.snapshot.revision,
  });
}
