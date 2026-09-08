import { missions } from "@/lib";
import { overlayWorkflowMission } from "@/lib/server-workflow-overlays";

import { collectionResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(): Promise<Response> {
  const workflow = await readWorkflowForApi();
  return collectionResponse(overlayWorkflowMission(missions, workflow.snapshot), {
    snapshotAt: workflow.snapshot.updatedAt,
    workflowPersistence: workflow.persistence,
    workflowRevision: workflow.snapshot.revision,
  });
}
