import { readWorkflowForApi } from "@/app/api/_workflow";
import { buildReportCatalog, findReport } from "@/lib/report-data";
import type { WindOpsReport } from "@/lib/report-data";
import {
  getProductionBackendConfig,
  proxyProductionBackendRequest,
} from "@/lib/production-runtime";

import { jsonResponse } from "../../_shared";

interface ReportRouteContext {
  readonly params: Promise<{ readonly id: string }>;
}

export async function GET(request: Request, context: ReportRouteContext): Promise<Response> {
  const url = new URL(request.url);
  if ([...url.searchParams.keys()].length > 0) {
    return jsonResponse(
      {
        ok: false,
        data: null,
        error: {
          code: "UNKNOWN_PARAMETERS",
          message: "The report detail endpoint does not accept query parameters.",
          details: { parameters: [...new Set(url.searchParams.keys())].sort() },
        },
        meta: { deterministic: true, persisted: false, source: "fixtures-plus-server-workflow" },
      },
      400,
    );
  }

  const { id } = await context.params;
  if (getProductionBackendConfig().mode === "production") {
    const upstream = await proxyProductionBackendRequest(
      request,
      "/api/v1/reports/" + encodeURIComponent(id),
    );
    if (!upstream.ok) return upstream;
    const payload = (await upstream.json()) as { data?: WindOpsReport };
    const report =
      payload.data && typeof payload.data === "object" && payload.data.id === id
        ? payload.data
        : null;
    if (report === null) {
      return jsonResponse(
        {
          ok: false,
          data: null,
          error: { code: "REPORT_NOT_FOUND", message: `Report ${id} was not found.` },
          meta: { runtimeMode: "production", fixtureFallback: false },
        },
        404,
      );
    }
    return jsonResponse({
      ok: true,
      data: { report },
      error: null,
      meta: {
        deterministic: false,
        persisted: true,
        source: "python-fastapi",
        snapshotAt: report.generatedAt,
        workflowPersistence: "postgresql",
        workflowRevision: 0,
      },
    });
  }
  const workflow = await readWorkflowForApi();
  const report = findReport(buildReportCatalog(workflow.snapshot), id);
  if (!report) {
    return jsonResponse(
      {
        ok: false,
        data: null,
        error: {
          code: "REPORT_NOT_FOUND",
          message: `Report ${id} was not found.`,
          details: { reportId: id },
        },
        meta: {
          deterministic: true,
          persisted: workflow.persistence === "d1",
          source: "fixtures-plus-server-workflow",
          workflowRevision: workflow.snapshot.revision,
        },
      },
      404,
    );
  }

  return jsonResponse({
    ok: true,
    data: { report },
    error: null,
    meta: {
      deterministic: true,
      persisted: workflow.persistence === "d1",
      source: "fixtures-plus-server-workflow",
      snapshotAt: workflow.snapshot.updatedAt,
      workflowPersistence: workflow.persistence,
      workflowRevision: workflow.snapshot.revision,
    },
  });
}
