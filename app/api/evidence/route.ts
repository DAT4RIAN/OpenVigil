import { evidenceItems } from "@/lib/operations-data";

import { collectionResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(): Promise<Response> {
  const workflow = await readWorkflowForApi();
  return collectionResponse(evidenceItems, {
    snapshotAt: workflow.snapshot.updatedAt,
    workflowPersistence: workflow.persistence,
    workflowRevision: workflow.snapshot.revision,
  });
}
