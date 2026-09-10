import { jsonResponse } from "@/app/api/_shared";
import { readWorkflowForApi } from "@/app/api/_workflow";
import { buildDigitalTwinSnapshot } from "@/lib/digital-twin-data";
import { productionDigitalTwinResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionDigitalTwinResponse(request);
  }
  const url = new URL(request.url);
  const turbineId = url.searchParams.get("turbineId")?.trim().toUpperCase() ?? "WT-023";

  if (!/^WT-\d{3}$/.test(turbineId)) {
    return jsonResponse(
      { error: { code: "INVALID_TURBINE_ID", message: "turbineId must match WT-001..WT-064." } },
      400,
    );
  }

  const workflow = await readWorkflowForApi();
  const snapshot = buildDigitalTwinSnapshot(turbineId, workflow.snapshot, workflow.persistence);
  if (!snapshot) {
    return jsonResponse(
      { error: { code: "TURBINE_NOT_FOUND", message: `Wind turbine ${turbineId} was not found.` } },
      404,
    );
  }

  return jsonResponse({
    data: snapshot,
    meta: {
      turbineId,
      snapshotAt: snapshot.snapshotAt,
      deterministic: true,
      readOnly: true,
      workflowPersistence: workflow.persistence,
      workflowRevision: workflow.snapshot.revision,
    },
  });
}
