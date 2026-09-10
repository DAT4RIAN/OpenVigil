import { SCADA_ARCHIVE_MAX_PAGE_SIZE, queryScadaMeasurements } from "@/lib/archive-data";
import type { ScadaMetric } from "@/lib/types";
import { productionScadaMeasurementsResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";

import { collectionResponse, errorResponse } from "../_shared";

const parseInteger = (
  rawValue: string | null,
  name: "offset" | "limit",
  minimum: number,
  maximum: number,
): number | undefined | Response => {
  if (rawValue === null) return undefined;

  const value = Number(rawValue);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    return errorResponse(
      "INVALID_PAGINATION",
      `${name} must be an integer between ${minimum} and ${maximum}.`,
    );
  }

  return value;
};

export function GET(request: Request): Response | Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionScadaMeasurementsResponse(request);
  }
  const searchParams = new URL(request.url).searchParams;
  const offset = parseInteger(searchParams.get("offset"), "offset", 0, Number.MAX_SAFE_INTEGER);
  if (offset instanceof Response) return offset;

  const limit = parseInteger(searchParams.get("limit"), "limit", 1, SCADA_ARCHIVE_MAX_PAGE_SIZE);
  if (limit instanceof Response) return limit;

  const turbineId = searchParams.get("turbineId")?.trim() || undefined;
  const metric = searchParams.get("metric")?.trim() || undefined;
  const page = queryScadaMeasurements({
    offset,
    limit,
    turbineId,
    metric: metric as ScadaMetric | undefined,
  });

  return collectionResponse(page.items, {
    total: page.total,
    offset: page.offset,
    limit: page.limit,
    turbineId: turbineId?.toUpperCase() ?? null,
    metric: metric?.toLowerCase() ?? null,
    snapshotAt: page.snapshotAt,
  });
}
