import { resourceCenterSnapshot } from "@/lib/resource-data";
import { productionResourcesResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";

import { errorResponse, jsonResponse } from "../_shared";

const categories = ["all", "spare-parts", "crews", "vessels", "tools", "weather"] as const;
type ResourceCategory = (typeof categories)[number];

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionResourcesResponse(request);
  }
  const url = new URL(request.url);
  const category = (url.searchParams.get("category") ?? "all").trim().toLowerCase();
  const query = (url.searchParams.get("q") ?? "").trim().toLowerCase();
  const workOrderId = (url.searchParams.get("workOrderId") ?? "").trim().toUpperCase();

  if (!categories.includes(category as ResourceCategory)) {
    return errorResponse(
      "INVALID_RESOURCE_CATEGORY",
      `category must be one of ${categories.join(", ")}.`,
    );
  }

  const includesQuery = (...values: readonly string[]) =>
    !query || values.some((value) => value.toLowerCase().includes(query));
  const matchesWorkOrder = (ids: readonly (string | null)[]) =>
    !workOrderId || ids.some((id) => id === workOrderId);

  const spareParts = resourceCenterSnapshot.spareParts.filter(
    (item) =>
      includesQuery(item.name, item.partNumber, item.category, item.warehouse) &&
      matchesWorkOrder(item.reservedForWorkOrderIds),
  );
  const crews = resourceCenterSnapshot.crews.filter(
    (item) =>
      includesQuery(item.name, item.currentLocation, ...item.specialties) &&
      matchesWorkOrder([item.assignedWorkOrderId]),
  );
  const vessels = resourceCenterSnapshot.vessels.filter(
    (item) =>
      includesQuery(item.name, item.id, item.vesselType, item.berth) &&
      matchesWorkOrder([item.assignedWorkOrderId]),
  );
  const tools = resourceCenterSnapshot.tools.filter(
    (item) =>
      includesQuery(item.name, item.id, item.category, item.location) &&
      matchesWorkOrder([item.assignedWorkOrderId]),
  );
  const weatherWindows = resourceCenterSnapshot.weatherWindows.filter(
    (item) =>
      (!workOrderId || workOrderId === "WO-20260823-017") &&
      includesQuery(item.id, item.suitability, item.reason, ...item.recommendedFor),
  );

  const data = {
    spareParts: category === "all" || category === "spare-parts" ? spareParts : [],
    crews: category === "all" || category === "crews" ? crews : [],
    vessels: category === "all" || category === "vessels" ? vessels : [],
    tools: category === "all" || category === "tools" ? tools : [],
    weatherWindows: category === "all" || category === "weather" ? weatherWindows : [],
  };
  const counts = {
    spareParts: data.spareParts.length,
    crews: data.crews.length,
    vessels: data.vessels.length,
    tools: data.tools.length,
    weatherWindows: data.weatherWindows.length,
  };

  return jsonResponse({
    data,
    meta: {
      ...counts,
      count: Object.values(counts).reduce((sum, count) => sum + count, 0),
      total:
        resourceCenterSnapshot.spareParts.length +
        resourceCenterSnapshot.crews.length +
        resourceCenterSnapshot.vessels.length +
        resourceCenterSnapshot.tools.length +
        resourceCenterSnapshot.weatherWindows.length,
      category,
      query: query || null,
      workOrderId: workOrderId || null,
      snapshotAt: resourceCenterSnapshot.snapshotAt,
      deterministic: true,
    },
  });
}
