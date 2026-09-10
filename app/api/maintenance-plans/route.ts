import { errorResponse, jsonResponse } from "@/app/api/_shared";
import { productionMaintenancePlansResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";
import { readWorkflowForApi } from "@/app/api/_workflow";
import {
  createMaintenancePlans,
  maintenancePlanMeta,
  maintenancePlanRiskLevels,
  maintenancePlanSortModes,
  maintenancePlanStatuses,
  maintenancePlanTeamFacets,
  maintenancePlanWindowStates,
  sortMaintenancePlans,
  type MaintenancePlanSortMode,
} from "@/lib/maintenance-plan-data";

const allowedParameters = new Set([
  "q",
  "status",
  "risk",
  "team",
  "window",
  "sort",
  "offset",
  "limit",
]);

const integerParameter = (
  value: string | null,
  fallback: number,
  minimum: number,
  maximum: number,
): number | null => {
  if (value === null) return fallback;
  if (!/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return parsed >= minimum && parsed <= maximum ? parsed : null;
};

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionMaintenancePlansResponse(request);
  }
  const url = new URL(request.url);
  const unknownParameter = [...url.searchParams.keys()].find((key) => !allowedParameters.has(key));
  if (unknownParameter) {
    return errorResponse(
      "INVALID_QUERY_PARAMETER",
      `Unknown maintenance plan query parameter: ${unknownParameter}`,
    );
  }

  const query = url.searchParams.get("q")?.trim().toLowerCase() ?? "";
  const status = url.searchParams.get("status")?.trim().toLowerCase() ?? null;
  const risk = url.searchParams.get("risk")?.trim().toLowerCase() ?? null;
  const team = url.searchParams.get("team")?.trim() ?? null;
  const windowState = url.searchParams.get("window")?.trim().toLowerCase() ?? null;
  const sort = url.searchParams.get("sort")?.trim().toLowerCase() ?? "start-asc";
  const offset = integerParameter(url.searchParams.get("offset"), 0, 0, 500);
  const limit = integerParameter(url.searchParams.get("limit"), 50, 1, 50);

  if (query.length > 100) {
    return errorResponse("INVALID_QUERY", "q must contain at most 100 characters.");
  }
  if (
    status &&
    !maintenancePlanStatuses.includes(status as (typeof maintenancePlanStatuses)[number])
  ) {
    return errorResponse("INVALID_STATUS", `Unknown maintenance plan status: ${status}`);
  }
  if (
    risk &&
    !maintenancePlanRiskLevels.includes(risk as (typeof maintenancePlanRiskLevels)[number])
  ) {
    return errorResponse("INVALID_RISK", `Unknown maintenance plan risk: ${risk}`);
  }
  if (
    windowState &&
    !maintenancePlanWindowStates.includes(
      windowState as (typeof maintenancePlanWindowStates)[number],
    )
  ) {
    return errorResponse("INVALID_WINDOW", `Unknown weather window state: ${windowState}`);
  }
  if (!maintenancePlanSortModes.includes(sort as MaintenancePlanSortMode)) {
    return errorResponse("INVALID_SORT", `Unknown maintenance plan sort mode: ${sort}`);
  }
  if (offset === null || limit === null) {
    return errorResponse("INVALID_PAGINATION", "offset must be 0–500 and limit must be 1–50.");
  }

  const workflow = await readWorkflowForApi();
  const plans = createMaintenancePlans({
    featuredWorkOrderStatus: workflow.snapshot.workOrder.status,
    featuredCompletedTaskIds: workflow.snapshot.workOrder.tasks
      .filter((task) => task.completed)
      .map((task) => task.id),
  });
  const teamFacets = maintenancePlanTeamFacets(plans);
  if (team && !teamFacets.some((facet) => facet.value.toLowerCase() === team.toLowerCase())) {
    return errorResponse("INVALID_TEAM", `Unknown maintenance team: ${team}`);
  }

  const filtered = plans.filter(
    (plan) =>
      (!query ||
        `${plan.id} ${plan.workOrderId} ${plan.turbineId} ${plan.issue} ${plan.assignedTeam}`
          .toLowerCase()
          .includes(query)) &&
      (!status || plan.status === status) &&
      (!risk || plan.risk === risk) &&
      (!team || plan.teamKey.toLowerCase() === team.toLowerCase()) &&
      (!windowState || plan.weather.state === windowState),
  );
  const sorted = sortMaintenancePlans(filtered, sort as MaintenancePlanSortMode);
  const data = sorted.slice(offset, offset + limit);

  return jsonResponse({
    data,
    meta: {
      count: data.length,
      total: plans.length,
      filteredTotal: filtered.length,
      offset,
      limit,
      filters: {
        query: query || null,
        status,
        risk,
        team,
        window: windowState,
      },
      sort,
      model: maintenancePlanMeta,
      facets: {
        statuses: maintenancePlanStatuses,
        risks: maintenancePlanRiskLevels,
        teams: teamFacets,
        windows: maintenancePlanWindowStates,
      },
      snapshotAt: workflow.snapshot.updatedAt,
      workflowPersistence: workflow.persistence,
      workflowRevision: workflow.snapshot.revision,
    },
  });
}
