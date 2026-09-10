import { readWorkflowForApi } from "@/app/api/_workflow";
import { productionReportsResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";
import {
  buildReportCatalog,
  reportTypes,
  type ReportPeriod,
  type OpenVigilReport,
} from "@/lib/report-data";

import { jsonResponse } from "../_shared";

const reportPeriods = ["daily", "weekly", "incident", "snapshot"] as const;
const sortableFields = ["generatedAt", "title", "type"] as const;
const allowedParameters = new Set(["q", "type", "period", "sort", "order", "page", "pageSize"]);

type SortField = (typeof sortableFields)[number];
type SortOrder = "asc" | "desc";

const responseMeta = (extra: Readonly<Record<string, unknown>> = {}) => ({
  deterministic: true,
  persisted: false,
  source: "fixtures-plus-server-workflow",
  ...extra,
});

const errorResponse = (
  code: string,
  message: string,
  details: Readonly<Record<string, unknown>> | null = null,
): Response =>
  jsonResponse(
    {
      ok: false,
      data: null,
      error: { code, message, details },
      meta: responseMeta(),
    },
    400,
  );

const parseInteger = (
  value: string | null,
  name: "page" | "pageSize",
  fallback: number,
  maximum: number,
): number | Response => {
  if (value === null) return fallback;
  if (!/^\d+$/.test(value)) {
    return errorResponse("INVALID_PAGINATION", `${name} must be an integer from 1 to ${maximum}.`, {
      argument: name,
      received: value,
    });
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 1 || parsed > maximum) {
    return errorResponse("INVALID_PAGINATION", `${name} must be an integer from 1 to ${maximum}.`, {
      argument: name,
      received: value,
    });
  }
  return parsed;
};

const compareReports = (
  left: OpenVigilReport,
  right: OpenVigilReport,
  sort: SortField,
  order: SortOrder,
): number => {
  const direction = order === "asc" ? 1 : -1;
  return left[sort].localeCompare(right[sort], "en") * direction;
};

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionReportsResponse(request);
  }
  const params = new URL(request.url).searchParams;
  const unknownParameters = [...new Set(params.keys())]
    .filter((key) => !allowedParameters.has(key))
    .sort();
  if (unknownParameters.length > 0) {
    return errorResponse("UNKNOWN_PARAMETERS", "Query contains unsupported parameters.", {
      parameters: unknownParameters,
      allowed: [...allowedParameters].sort(),
    });
  }

  const query = (params.get("q") ?? "").trim();
  const type = (params.get("type") ?? "all").trim().toLowerCase();
  const period = (params.get("period") ?? "all").trim().toLowerCase();
  const sort = (params.get("sort") ?? "generatedAt").trim();
  const order = (params.get("order") ?? "desc").trim();

  if (query.length > 120) {
    return errorResponse("INVALID_QUERY", "q must contain at most 120 characters.", {
      argument: "q",
      maxLength: 120,
    });
  }
  if (type !== "all" && !reportTypes.includes(type as (typeof reportTypes)[number])) {
    return errorResponse("INVALID_REPORT_TYPE", `Unknown report type: ${type}.`, {
      argument: "type",
      allowed: ["all", ...reportTypes],
    });
  }
  if (period !== "all" && !reportPeriods.includes(period as ReportPeriod)) {
    return errorResponse("INVALID_REPORT_PERIOD", `Unknown report period: ${period}.`, {
      argument: "period",
      allowed: ["all", ...reportPeriods],
    });
  }
  if (!sortableFields.includes(sort as SortField)) {
    return errorResponse("INVALID_SORT", `Unknown report sort field: ${sort}.`, {
      argument: "sort",
      allowed: sortableFields,
    });
  }
  if (order !== "asc" && order !== "desc") {
    return errorResponse("INVALID_SORT_ORDER", "order must be asc or desc.", {
      argument: "order",
      allowed: ["asc", "desc"],
    });
  }

  const page = parseInteger(params.get("page"), "page", 1, 100);
  if (page instanceof Response) return page;
  const pageSize = parseInteger(params.get("pageSize"), "pageSize", 12, 24);
  if (pageSize instanceof Response) return pageSize;

  const workflow = await readWorkflowForApi();
  const reports = buildReportCatalog(workflow.snapshot);
  const normalizedQuery = query.toLocaleLowerCase("en");
  const filtered = reports.filter((report) => {
    if (type !== "all" && report.type !== type) return false;
    if (period !== "all" && report.period !== period) return false;
    if (!normalizedQuery) return true;
    return [
      report.id,
      report.typeLabel,
      report.title,
      report.subtitle,
      report.assetScope,
      report.highlight,
      ...report.tags,
      ...report.linkedEntityIds,
    ]
      .join(" ")
      .toLocaleLowerCase("en")
      .includes(normalizedQuery);
  });
  const sorted = [...filtered].sort((left, right) =>
    compareReports(left, right, sort as SortField, order),
  );
  const offset = (page - 1) * pageSize;
  const pageReports = sorted.slice(offset, offset + pageSize);
  const typeCounts = Object.fromEntries(
    reportTypes.map((reportType) => [
      reportType,
      reports.filter((report) => report.type === reportType).length,
    ]),
  );

  return jsonResponse({
    ok: true,
    data: {
      reports: pageReports,
      facets: {
        reportTypes: typeCounts,
        periods: Object.fromEntries(
          reportPeriods.map((reportPeriod) => [
            reportPeriod,
            reports.filter((report) => report.period === reportPeriod).length,
          ]),
        ),
      },
    },
    error: null,
    meta: responseMeta({
      count: pageReports.length,
      total: sorted.length,
      catalogTotal: reports.length,
      page,
      pageSize,
      totalPages: Math.max(1, Math.ceil(sorted.length / pageSize)),
      query: query || null,
      type,
      period,
      sort,
      order,
      snapshotAt: workflow.snapshot.updatedAt,
      persisted: workflow.persistence === "d1",
      workflowPersistence: workflow.persistence,
      workflowRevision: workflow.snapshot.revision,
    }),
  });
}
