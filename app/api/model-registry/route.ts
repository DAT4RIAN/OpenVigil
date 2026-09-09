import { errorResponse, jsonResponse } from "@/app/api/_shared";
import {
  PLATFORM_SNAPSHOT_AT,
  modelKinds,
  modelRegistry,
  modelStatuses,
  queryModelRegistry,
  type ModelKind,
  type ModelStatus,
} from "@/lib/platform-admin-data";

const allowedParameters = new Set(["q", "kind", "status"]);

export function GET(request: Request): Response {
  const url = new URL(request.url);
  const unknown = [...url.searchParams.keys()].find((key) => !allowedParameters.has(key));
  if (unknown) {
    return errorResponse("INVALID_QUERY_PARAMETER", `Unknown model registry parameter: ${unknown}`);
  }

  const query = url.searchParams.get("q")?.trim() ?? "";
  const kind = url.searchParams.get("kind")?.trim().toLowerCase() ?? null;
  const status = url.searchParams.get("status")?.trim().toLowerCase() ?? null;

  if (query.length > 100) {
    return errorResponse("INVALID_QUERY", "q must contain at most 100 characters.");
  }
  if (kind && !modelKinds.includes(kind as (typeof modelKinds)[number])) {
    return errorResponse("INVALID_MODEL_KIND", `Unknown model kind: ${kind}`);
  }
  if (status && !modelStatuses.includes(status as (typeof modelStatuses)[number])) {
    return errorResponse("INVALID_MODEL_STATUS", `Unknown model status: ${status}`);
  }

  const entries = queryModelRegistry({
    query,
    kind: kind as ModelKind | null,
    status: status as ModelStatus | null,
  });

  return jsonResponse({
    data: entries,
    meta: {
      count: entries.length,
      total: modelRegistry.length,
      deterministic: true,
      readOnly: true,
      snapshotAt: PLATFORM_SNAPSHOT_AT,
      filters: { query: query || null, kind, status },
      facets: { kinds: modelKinds, statuses: modelStatuses },
      realInferenceCount: modelRegistry.filter((model) => model.realInference).length,
      embeddingBackedCount: modelRegistry.filter((model) => model.usesEmbeddings).length,
      disclosure:
        "Registry availability describes demo capability, not the presence of trained weights or hosted inference.",
    },
  });
}
