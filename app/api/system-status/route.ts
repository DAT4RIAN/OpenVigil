import { errorResponse, jsonResponse } from "@/app/api/_shared";
import { readWorkflowForApi } from "@/app/api/_workflow";
import { validateDomainData } from "@/lib/domain-data-validation";
import { PLATFORM_SNAPSHOT_AT, buildSystemStatusSnapshot } from "@/lib/platform-admin-data";
import { getWorkerEnv } from "@/lib/worker-env";

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const unknown = [...url.searchParams.keys()][0];
  if (unknown) {
    return errorResponse(
      "INVALID_QUERY_PARAMETER",
      `System status accepts no parameters: ${unknown}`,
    );
  }

  const workflow = await readWorkflowForApi();
  const integrityErrors = validateDomainData();
  const data = buildSystemStatusSnapshot({
    d1Bound: Boolean(getWorkerEnv().DB),
    workflowStore: workflow.persistence,
    workflowWritable: workflow.writable,
    workflowRevision: workflow.snapshot.revision,
    integrityErrorCount: integrityErrors.length,
  });

  return jsonResponse({
    data,
    meta: {
      count: data.connections.length,
      total: data.connections.length,
      deterministic: true,
      readOnly: true,
      snapshotAt: workflow.snapshot.updatedAt || PLATFORM_SNAPSHOT_AT,
      redacted: true,
    },
  });
}
