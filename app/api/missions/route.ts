import { missions } from "@/lib";
import { productionMissionsResponse } from "@/lib/production-domain-adapter";
import {
  getProductionBackendConfig,
  proxyProductionBackendRequest,
} from "@/lib/production-runtime";
import { overlayWorkflowMission } from "@/lib/server-workflow-overlays";

import { collectionResponse, errorResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionMissionsResponse(request);
  }
  const workflow = await readWorkflowForApi();
  return collectionResponse(overlayWorkflowMission(missions, workflow.snapshot), {
    snapshotAt: workflow.snapshot.updatedAt,
    workflowPersistence: workflow.persistence,
    workflowRevision: workflow.snapshot.revision,
  });
}

export async function POST(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode !== "production") {
    return errorResponse(
      "MISSION_WRITE_REQUIRES_PRODUCTION",
      "Mission creation is disabled in demo mode because it has no authoritative backend.",
      503,
    );
  }
  return proxyProductionBackendRequest(request, "/api/v1/missions");
}
