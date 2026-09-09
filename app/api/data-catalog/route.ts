import { errorResponse, jsonResponse } from "@/app/api/_shared";
import {
  PLATFORM_SNAPSHOT_AT,
  assetCatalogHierarchy,
  dataCatalog,
  dataCatalogCategories,
  dataCatalogStatuses,
  queryDataCatalog,
  schemaObjects,
  type DataCatalogCategory,
  type DataCatalogStatus,
} from "@/lib/platform-admin-data";

const allowedParameters = new Set(["q", "category", "status"]);

export function GET(request: Request): Response {
  const url = new URL(request.url);
  const unknown = [...url.searchParams.keys()].find((key) => !allowedParameters.has(key));
  if (unknown) {
    return errorResponse("INVALID_QUERY_PARAMETER", `Unknown data catalog parameter: ${unknown}`);
  }

  const query = url.searchParams.get("q")?.trim() ?? "";
  const category = url.searchParams.get("category")?.trim().toLowerCase() ?? null;
  const status = url.searchParams.get("status")?.trim().toLowerCase() ?? null;

  if (query.length > 100) {
    return errorResponse("INVALID_QUERY", "q must contain at most 100 characters.");
  }
  if (
    category &&
    !dataCatalogCategories.includes(category as (typeof dataCatalogCategories)[number])
  ) {
    return errorResponse("INVALID_CATEGORY", `Unknown data catalog category: ${category}`);
  }
  if (status && !dataCatalogStatuses.includes(status as (typeof dataCatalogStatuses)[number])) {
    return errorResponse("INVALID_STATUS", `Unknown data catalog status: ${status}`);
  }

  const entries = queryDataCatalog({
    query,
    category: category as DataCatalogCategory | null,
    status: status as DataCatalogStatus | null,
  });

  return jsonResponse({
    data: entries,
    meta: {
      count: entries.length,
      total: dataCatalog.length,
      deterministic: true,
      readOnly: true,
      snapshotAt: PLATFORM_SNAPSHOT_AT,
      filters: { query: query || null, category, status },
      facets: { categories: dataCatalogCategories, statuses: dataCatalogStatuses },
      hierarchy: assetCatalogHierarchy,
      schemaObjects,
      schemaObjectCount: schemaObjects.length,
      scadaArchiveCount: 131_072,
    },
  });
}
