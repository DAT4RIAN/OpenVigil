import { errorResponse, jsonResponse } from "@/app/api/_shared";
import { readWorkflowForApi } from "@/app/api/_workflow";
import {
  createDiagnosisRecords,
  diagnosisModelMeta,
  diagnosisRiskLevels,
  diagnosisSortModes,
  diagnosisStatuses,
  sortDiagnosisRecords,
  type DiagnosisSortMode,
} from "@/lib/diagnosis-data";

const allowedParameters = new Set(["q", "turbineId", "status", "risk", "sort", "offset", "limit"]);

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
  const url = new URL(request.url);
  const unknownParameter = [...url.searchParams.keys()].find((key) => !allowedParameters.has(key));
  if (unknownParameter) {
    return errorResponse(
      "INVALID_QUERY_PARAMETER",
      `Unknown diagnosis query parameter: ${unknownParameter}`,
    );
  }

  const query = url.searchParams.get("q")?.trim().toLowerCase() ?? "";
  const turbineId = url.searchParams.get("turbineId")?.trim().toUpperCase() ?? null;
  const status = url.searchParams.get("status")?.trim().toLowerCase() ?? null;
  const risk = url.searchParams.get("risk")?.trim().toLowerCase() ?? null;
  const sort = url.searchParams.get("sort")?.trim().toLowerCase() ?? "priority-desc";
  const offset = integerParameter(url.searchParams.get("offset"), 0, 0, 64);
  const limit = integerParameter(url.searchParams.get("limit"), 64, 1, 64);

  if (query.length > 100) {
    return errorResponse("INVALID_QUERY", "q must contain at most 100 characters.");
  }
  if (turbineId && !/^WT-\d{3}$/.test(turbineId)) {
    return errorResponse("INVALID_TURBINE_ID", "turbineId must use the WT-000 format.");
  }
  if (status && !diagnosisStatuses.includes(status as (typeof diagnosisStatuses)[number])) {
    return errorResponse("INVALID_STATUS", `Unknown diagnosis status: ${status}`);
  }
  if (risk && !diagnosisRiskLevels.includes(risk as (typeof diagnosisRiskLevels)[number])) {
    return errorResponse("INVALID_RISK", `Unknown diagnosis risk: ${risk}`);
  }
  if (!diagnosisSortModes.includes(sort as DiagnosisSortMode)) {
    return errorResponse("INVALID_SORT", `Unknown diagnosis sort mode: ${sort}`);
  }
  if (offset === null || limit === null) {
    return errorResponse("INVALID_PAGINATION", "offset must be 0–64 and limit must be 1–64.");
  }

  const workflow = await readWorkflowForApi();
  const records = createDiagnosisRecords({
    missionStatus: workflow.snapshot.mission.status,
    decisionStatus: workflow.snapshot.decision.status,
    workOrderStatus: workflow.snapshot.workOrder.status,
  });

  if (turbineId && !records.some((record) => record.turbineId === turbineId)) {
    return errorResponse("TURBINE_NOT_FOUND", `Wind turbine ${turbineId} was not found.`, 404);
  }

  const filtered = records.filter(
    (record) =>
      (!query ||
        `${record.id} ${record.turbineId} ${record.headline} ${record.candidates
          .map((candidate) => candidate.faultMode)
          .join(" ")}`
          .toLowerCase()
          .includes(query)) &&
      (!turbineId || record.turbineId === turbineId) &&
      (!status || record.status === status) &&
      (!risk || record.risk === risk),
  );
  const sorted = sortDiagnosisRecords(filtered, sort as DiagnosisSortMode);
  const data = sorted.slice(offset, offset + limit);

  return jsonResponse({
    data,
    meta: {
      count: data.length,
      total: records.length,
      filteredTotal: filtered.length,
      offset,
      limit,
      filters: {
        query: query || null,
        turbineId,
        status,
        risk,
      },
      sort,
      model: diagnosisModelMeta,
      facets: {
        statuses: diagnosisStatuses,
        risks: diagnosisRiskLevels,
      },
      snapshotAt: workflow.snapshot.updatedAt,
      workflowPersistence: workflow.persistence,
      workflowRevision: workflow.snapshot.revision,
    },
  });
}
