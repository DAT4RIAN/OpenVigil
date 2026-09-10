import { readWorkflowForApi } from "@/app/api/_workflow";
import {
  createReportDocx,
  createReportPdf,
  reportExportFilename,
  reportExportMimeTypes,
  type ReportExportFormat,
} from "@/lib/report-export";
import { buildReportCatalog, findReport } from "@/lib/report-data";
import type { WindOpsReport } from "@/lib/report-data";
import {
  getProductionBackendConfig,
  proxyProductionBackendRequest,
} from "@/lib/production-runtime";

import { jsonResponse } from "../../../_shared";

interface ReportExportRouteContext {
  readonly params: Promise<{ readonly id: string }>;
}

const formats = ["pdf", "docx"] as const;

const exportError = (
  code: string,
  message: string,
  status: number,
  details: Readonly<Record<string, unknown>> | null = null,
): Response =>
  jsonResponse(
    {
      ok: false,
      data: null,
      error: { code, message, details },
      meta: {
        deterministic: true,
        persisted: false,
        source: "fixtures-plus-server-workflow",
      },
    },
    status,
  );

export async function GET(request: Request, context: ReportExportRouteContext): Promise<Response> {
  const params = new URL(request.url).searchParams;
  const parameterNames = [...new Set(params.keys())];
  const allowedParameters = new Set(["format", "expectedRevision", "expectedDigest"]);
  if (parameterNames.some((parameter) => !allowedParameters.has(parameter))) {
    return exportError(
      "UNKNOWN_PARAMETERS",
      "Export accepts only format and version-check parameters.",
      400,
      {
        parameters: parameterNames.filter((parameter) => !allowedParameters.has(parameter)).sort(),
        allowed: [...allowedParameters],
      },
    );
  }
  if (params.getAll("format").length !== 1) {
    return exportError("INVALID_EXPORT_FORMAT", "Exactly one format value is required.", 400, {
      argument: "format",
      allowed: formats,
    });
  }
  const format = (params.get("format") ?? "").trim().toLowerCase();
  if (!formats.includes(format as ReportExportFormat)) {
    return exportError("INVALID_EXPORT_FORMAT", `Unsupported export format: ${format}.`, 400, {
      argument: "format",
      allowed: formats,
    });
  }
  const { id } = await context.params;
  if (getProductionBackendConfig().mode === "production") {
    if (params.getAll("expectedDigest").length !== 1) {
      return exportError(
        "INVALID_REPORT_DIGEST",
        "Exactly one expectedDigest value is required for a production export.",
        400,
        { argument: "expectedDigest" },
      );
    }
    const expectedDigest = params.get("expectedDigest") ?? "";
    if (!/^[0-9a-f]{64}$/i.test(expectedDigest)) {
      return exportError("INVALID_REPORT_DIGEST", "expectedDigest must be a SHA-256 digest.", 400, {
        argument: "expectedDigest",
      });
    }
    const upstreamRequest = new Request(
      new URL("/api/reports/" + encodeURIComponent(id), request.url),
      { headers: request.headers },
    );
    const upstream = await proxyProductionBackendRequest(
      upstreamRequest,
      "/api/v1/reports/" + encodeURIComponent(id),
    );
    if (!upstream.ok) return upstream;
    const payload = (await upstream.json()) as { data?: WindOpsReport };
    const report =
      payload.data && typeof payload.data === "object" && payload.data.id === id
        ? payload.data
        : null;
    if (report === null) {
      return exportError("REPORT_NOT_FOUND", `Report ${id} was not found.`, 404, {
        reportId: id,
      });
    }
    if (report.contentDigest !== expectedDigest.toLowerCase()) {
      return exportError(
        "REPORT_DIGEST_CONFLICT",
        "The production report preview does not match the immutable snapshot.",
        409,
        { expectedDigest, currentDigest: report.contentDigest ?? null },
      );
    }
    const resolvedFormat = format as ReportExportFormat;
    const bytes = resolvedFormat === "pdf" ? createReportPdf(report) : createReportDocx(report);
    const filename = reportExportFilename(report, resolvedFormat);
    return new Response(bytes.buffer as ArrayBuffer, {
      status: 200,
      headers: {
        "cache-control": "no-store",
        "content-disposition": `attachment; filename="${filename}"`,
        "content-length": bytes.byteLength.toString(),
        "content-type": reportExportMimeTypes[resolvedFormat],
        "x-content-type-options": "nosniff",
        "x-windops-report-id": report.id,
        "x-windops-report-sha256": expectedDigest.toLowerCase(),
        "x-windops-report-source": "python-fastapi",
      },
    });
  }
  if (params.getAll("expectedRevision").length !== 1) {
    return exportError(
      "INVALID_WORKFLOW_REVISION",
      "Exactly one expectedRevision value is required.",
      400,
      { argument: "expectedRevision" },
    );
  }
  const expectedRevisionRaw = params.get("expectedRevision") ?? "";
  if (!/^\d+$/.test(expectedRevisionRaw)) {
    return exportError(
      "INVALID_WORKFLOW_REVISION",
      "expectedRevision must be a non-negative integer.",
      400,
      { argument: "expectedRevision" },
    );
  }
  const workflow = await readWorkflowForApi();
  const expectedRevision = Number(expectedRevisionRaw);
  if (expectedRevision !== workflow.snapshot.revision) {
    return exportError(
      "REPORT_REVISION_CONFLICT",
      "The report preview is stale. Refresh it before exporting.",
      409,
      { expectedRevision, currentRevision: workflow.snapshot.revision },
    );
  }
  const report = findReport(buildReportCatalog(workflow.snapshot), id);
  if (!report) {
    return exportError("REPORT_NOT_FOUND", `Report ${id} was not found.`, 404, {
      reportId: id,
    });
  }

  const resolvedFormat = format as ReportExportFormat;
  const bytes = resolvedFormat === "pdf" ? createReportPdf(report) : createReportDocx(report);
  const filename = reportExportFilename(report, resolvedFormat);
  return new Response(bytes.buffer as ArrayBuffer, {
    status: 200,
    headers: {
      "cache-control": "no-store",
      "content-disposition": `attachment; filename="${filename}"`,
      "content-length": bytes.byteLength.toString(),
      "content-type": reportExportMimeTypes[resolvedFormat],
      "x-content-type-options": "nosniff",
      "x-windops-report-id": report.id,
      "x-windops-workflow-revision": workflow.snapshot.revision.toString(),
    },
  });
}
