import { proxyProductionBackendRequest } from "../production-runtime.ts";
import { type JsonRecord, isRecord, text, number, record, jsonError } from "./shared.ts";

async function productionOperationalView(
  request: Request,
  backendPath: string,
  options: {
    readonly model?: JsonRecord;
    readonly meta?: (meta: JsonRecord) => JsonRecord;
  } = {},
): Promise<Response> {
  const upstream = await proxyProductionBackendRequest(request, backendPath);
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production operational view was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.data) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a valid operational collection.",
    );
  }
  const sourceMeta = payload.meta;
  return Response.json(
    {
      data: payload.data,
      meta: {
        count: number(sourceMeta.count, payload.data.length),
        total: number(sourceMeta.total, payload.data.length),
        filteredTotal: number(sourceMeta.filtered_total, payload.data.length),
        offset: number(sourceMeta.offset),
        limit: number(sourceMeta.limit, payload.data.length),
        nextOffset: typeof sourceMeta.next_offset === "number" ? sourceMeta.next_offset : null,
        hasMore: sourceMeta.has_more === true,
        snapshotAt: text(sourceMeta.snapshot_at),
        runtimeMode: "production",
        fixtureFallback: false,
        source: text(sourceMeta.source, "python-fastapi"),
        ...(isRecord(sourceMeta.related_data_boundaries)
          ? { relatedDataBoundaries: sourceMeta.related_data_boundaries }
          : {}),
        ...(options.model ? { model: options.model } : {}),
        ...(options.meta ? options.meta(sourceMeta) : {}),
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export function productionDiagnosesResponse(request: Request): Promise<Response> {
  return productionOperationalView(request, "/api/v1/diagnoses", {
    model: {
      mode: "governed-mission-diagnosis",
      deterministic: false,
      readOnly: true,
      realInference: true,
      publicTraceOnly: true,
      snapshotAt: null,
      notice: "诊断来自持久化 Mission、证据和 Agent 执行；模型供应方以每条执行账本为准。",
    },
  });
}

export function productionMaintenancePlansResponse(request: Request): Promise<Response> {
  return productionOperationalView(request, "/api/v1/maintenance-plans", {
    model: {
      mode: "governed-operational-schedule",
      deterministic: false,
      readOnly: false,
      snapshotAt: null,
      notice: "计划由持久化工单、资源预留与天气窗口实时派生。",
      provenance: ["work_orders", "resource_reservations", "weather_windows", "turbines"],
    },
  });
}

export async function productionDigitalTwinResponse(request: Request): Promise<Response> {
  const upstream = await proxyProductionBackendRequest(request, "/api/v1/digital-twin");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production twin response was invalid.");
  }
  if (!isRecord(payload) || !isRecord(payload.data) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a valid digital twin snapshot.",
    );
  }
  return Response.json(
    {
      data: payload.data,
      meta: {
        turbineId: text(payload.meta.turbine_id),
        snapshotAt: text(payload.meta.snapshot_at),
        deterministic: false,
        readOnly: true,
        runtimeMode: "production",
        source: text(payload.meta.source),
        fixtureFallback: false,
        workflowPersistence: "postgresql",
        workflowRevision: 0,
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export async function productionReportsResponse(request: Request): Promise<Response> {
  const upstream = await proxyProductionBackendRequest(request, "/api/v1/reports");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production report response was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.data) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a valid report collection.",
    );
  }
  const reports = payload.data.filter(isRecord);
  const typeCounts: Record<string, number> = {};
  const periodCounts: Record<string, number> = {};
  for (const report of reports) {
    const reportType = text(report.type);
    const period = text(report.period);
    if (reportType) typeCounts[reportType] = (typeCounts[reportType] ?? 0) + 1;
    if (period) periodCounts[period] = (periodCounts[period] ?? 0) + 1;
  }
  const workflowRevision = reports.reduce(
    (maximum, report) => Math.max(maximum, number(record(report.workflow).revision)),
    0,
  );
  return Response.json(
    {
      ok: true,
      data: {
        reports,
        facets: { reportTypes: typeCounts, periods: periodCounts },
      },
      error: null,
      meta: {
        count: number(payload.meta.count, reports.length),
        total: number(payload.meta.filtered_total, reports.length),
        catalogTotal: number(payload.meta.total, reports.length),
        snapshotAt: text(payload.meta.snapshot_at),
        workflowPersistence: "postgresql",
        workflowRevision,
        persisted: payload.meta.persisted === true,
        runtimeMode: "production",
        fixtureFallback: false,
        source: text(payload.meta.source),
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export function productionDataCatalogResponse(request: Request): Promise<Response> {
  return productionOperationalView(request, "/api/v1/data-catalog", {
    meta: (meta) => ({
      scadaArchiveCount: number(meta.scada_archive_count),
      schemaObjectCount: number(meta.schema_object_count),
      hierarchy: record(meta.hierarchy),
      deterministic: false,
      readOnly: false,
    }),
  });
}
