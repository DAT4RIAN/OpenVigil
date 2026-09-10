import { errorResponse, jsonResponse, parseBoundedInteger } from "@/app/api/_shared";
import { productionDataCatalogResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";
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

const allowedParameters = new Set(["q", "category", "status", "offset", "limit"]);

export function GET(request: Request): Response | Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionDataCatalogResponse(request);
  }
  const url = new URL(request.url);
  const unknown = [...url.searchParams.keys()].find((key) => !allowedParameters.has(key));
  if (unknown) {
    return errorResponse("INVALID_QUERY_PARAMETER", `Unknown data catalog parameter: ${unknown}`);
  }

  const query = url.searchParams.get("q")?.trim() ?? "";
  const category = url.searchParams.get("category")?.trim().toLowerCase() ?? null;
  const status = url.searchParams.get("status")?.trim().toLowerCase() ?? null;
  const offsetValue = url.searchParams.get("offset")?.trim() ?? "0";
  const limitValue = url.searchParams.get("limit")?.trim() ?? "64";
  const offset = parseBoundedInteger(offsetValue, 0, 0, 10_000);
  const limit = parseBoundedInteger(limitValue, 64, 1, 64);

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
  if (offset === null) {
    return errorResponse("INVALID_OFFSET", "offset must be an integer within 0..10000.");
  }
  if (limit === null) {
    return errorResponse("INVALID_LIMIT", "limit must be an integer within 1..64.");
  }

  const entries = queryDataCatalog({
    query,
    category: category as DataCatalogCategory | null,
    status: status as DataCatalogStatus | null,
  });

  const page = entries.slice(offset, offset + limit);
  return jsonResponse({
    data: page,
    meta: {
      count: page.length,
      total: dataCatalog.length,
      filteredTotal: entries.length,
      offset,
      limit,
      hasMore: offset + page.length < entries.length,
      nextOffset: offset + page.length < entries.length ? offset + page.length : null,
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
