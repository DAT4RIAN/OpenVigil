import { decisions } from "@/lib";
import { overlayWorkflowDecision } from "@/lib/server-workflow-overlays";

import { collectionResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(): Promise<Response> {
  const workflow = await readWorkflowForApi();
  return collectionResponse(overlayWorkflowDecision(decisions, workflow.snapshot), {
    snapshotAt: workflow.snapshot.updatedAt,
    workflowPersistence: workflow.persistence,
    workflowRevision: workflow.snapshot.revision,
  });
}
