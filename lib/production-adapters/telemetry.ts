import { proxyProductionBackendRequest } from "../production-runtime.ts";
import { isRecord, text, number, list, jsonError } from "./shared.ts";

export async function productionTurbinesResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const parameters = new URLSearchParams(sourceUrl.searchParams);
  parameters.set("limit", "200");
  const proxyRequest = new Request(`${sourceUrl.origin}${sourceUrl.pathname}?${parameters}`, {
    method: "GET",
    headers: request.headers,
  });
  const upstream = await proxyProductionBackendRequest(proxyRequest, "/api/v1/turbines");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production turbine response was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.turbines)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a governed turbine collection.",
    );
  }
  const rows = payload.turbines.filter(isRecord);
  const farms = list(payload.wind_farms).filter(isRecord);
  const data = rows.map((row, index) => {
    const updatedAt = text(row.updated_at, new Date(0).toISOString());
    const latitude = typeof row.latitude === "number" ? row.latitude : null;
    const longitude = typeof row.longitude === "number" ? row.longitude : null;
    const telemetryObservedAt = text(row.telemetry_observed_at) || null;
    const availabilityAvailable = typeof row.availability_percent === "number";
    const lastMaintenanceAt = text(row.last_maintenance_at) || null;
    const nextInspectionAt = text(row.next_inspection_at) || null;
    return {
      id: text(row.turbine_id),
      farmId: text(row.wind_farm_id),
      displayName: text(row.turbine_id),
      model: text(row.model),
      manufacturer: text(row.manufacturer, "unconfigured"),
      serialNumber: "unconfigured",
      ratedPowerMW: 0,
      status: text(row.status),
      healthScore: number(row.health_score),
      powerMW: number(row.active_power_mw),
      windSpeedMps: number(row.wind_speed_ms),
      rotorSpeedRpm: number(row.rotor_speed_rpm),
      nacelleDirectionDeg: number(row.nacelle_direction_deg),
      availabilityPercent: number(row.availability_percent),
      activeAlarmCount: number(row.active_alarm_count),
      currentMissionId: text(row.current_mission_id) || null,
      lastMaintenanceAt: lastMaintenanceAt ?? updatedAt,
      nextInspectionAt: nextInspectionAt ?? updatedAt,
      coordinates: { latitude: latitude ?? 0, longitude: longitude ?? 0 },
      gridPosition: { row: Math.floor(index / 8), column: index % 8 },
      updatedAt,
      telemetryObservedAt,
      telemetryAvailable: telemetryObservedAt !== null,
      availabilityAvailable,
      coordinatesConfigured: latitude !== null && longitude !== null,
      lastMaintenanceRecorded: lastMaintenanceAt !== null,
      nextInspectionRecorded: nextInspectionAt !== null,
    };
  });
  const currentPowerMW = data.reduce((total, turbine) => total + turbine.powerMW, 0);
  const averageHealthScore = data.length
    ? data.reduce((total, turbine) => total + turbine.healthScore, 0) / data.length
    : 0;
  const availabilityRows = data.filter((turbine) => turbine.availabilityAvailable);
  const averageAvailabilityPercent = availabilityRows.length
    ? availabilityRows.reduce((total, turbine) => total + turbine.availabilityPercent, 0) /
      availabilityRows.length
    : null;
  return Response.json(
    {
      data,
      meta: {
        count: data.length,
        total: data.length,
        runtimeMode: "production",
        source: "python-fastapi",
        fixtureFallback: false,
        snapshotAt: new Date().toISOString(),
        farms: farms.map((farm) => ({
          id: text(farm.wind_farm_id),
          name: text(farm.name),
          capacityMW: number(farm.capacity_mw),
        })),
        fleet: {
          currentPowerMW,
          averageHealthScore,
          activeAlarmCount: data.reduce((total, turbine) => total + turbine.activeAlarmCount, 0),
          activeMissionCount: data.filter((turbine) => turbine.currentMissionId).length,
          generationAvailable: false,
          averageAvailabilityPercent,
          telemetryAssetCount: data.filter((turbine) => turbine.telemetryAvailable).length,
        },
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

function scadaIntervalLabel(seconds: number): string {
  if (seconds < 60) return `${seconds} sec`;
  if (seconds < 3600) return `${Math.ceil(seconds / 60)} min`;
  return `${Math.ceil(seconds / 3600)} hour`;
}

export async function productionScadaHistoryResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const parameters = new URLSearchParams();
  const turbineId = sourceUrl.searchParams.get("turbineId")?.trim();
  if (!turbineId) {
    return jsonError("TURBINE_ID_REQUIRED", "turbineId is required in production mode.", 422);
  }
  parameters.set("turbine_id", turbineId);
  parameters.set("range", sourceUrl.searchParams.get("range")?.trim() || "24H");
  const startsAt = sourceUrl.searchParams.get("from")?.trim();
  const endsAt = sourceUrl.searchParams.get("to")?.trim();
  if (startsAt) parameters.set("from", startsAt);
  if (endsAt) parameters.set("to", endsAt);
  for (const variable of sourceUrl.searchParams.getAll("metric")) {
    parameters.append("variable", variable.replaceAll("-", "_"));
  }
  parameters.set("points_per_series", "1000");
  const proxyRequest = new Request(`${sourceUrl.origin}${sourceUrl.pathname}?${parameters}`, {
    method: "GET",
    headers: request.headers,
  });
  const upstream = await proxyProductionBackendRequest(proxyRequest, "/api/v1/scada/history");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production SCADA response was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.data) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a valid SCADA history response.",
    );
  }
  const data = payload.data.filter(isRecord).map((row) => {
    const normalRange = list(row.normal_range);
    const points = list(row.points)
      .filter(isRecord)
      .map((point) => ({
        timestamp: text(point.timestamp),
        value: number(point.value),
        quality: point.quality === "bad" || point.quality === "uncertain" ? point.quality : "good",
        isAnomaly: point.is_anomaly === true,
        aiEvent: null,
        late: point.late === true,
      }));
    return {
      id: text(row.series_id),
      turbineId: text(row.turbine_id),
      sourceId: text(row.source_id),
      metric: text(row.variable).replaceAll("_", "-"),
      label: text(row.label),
      unit: text(row.unit),
      precision: number(row.precision, 2),
      currentValue: points.at(-1)?.value ?? 0,
      normalRange: [number(normalRange[0]), number(normalRange[1])],
      thresholds: list(row.thresholds)
        .filter(isRecord)
        .map((threshold) => ({
          id: text(threshold.id),
          label: text(threshold.label),
          value: number(threshold.value),
          direction: threshold.direction === "below" ? "below" : "above",
          severity: threshold.severity === "critical" ? "critical" : "warning",
        })),
      points,
    };
  });
  const intervalSeconds = number(payload.meta.interval_seconds, 1);
  return Response.json(
    {
      data,
      meta: {
        count: data.length,
        pointCount: number(payload.meta.point_count),
        turbineId: text(payload.meta.turbine_id),
        range: text(payload.meta.range, "24H"),
        interval: scadaIntervalLabel(intervalSeconds),
        startsAt: text(payload.meta.starts_at),
        endsAt: text(payload.meta.ends_at),
        snapshotAt: text(payload.meta.snapshot_at),
        deterministic: false,
        runtimeMode: "production",
        source: "python-fastapi-timescaledb",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export async function productionScadaMeasurementsResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const parameters = new URLSearchParams();
  const turbineId = sourceUrl.searchParams.get("turbineId")?.trim();
  const metric = sourceUrl.searchParams.get("metric")?.trim();
  for (const key of ["offset", "limit", "from", "to"] as const) {
    const value = sourceUrl.searchParams.get(key)?.trim();
    if (value) parameters.set(key, value);
  }
  if (turbineId) parameters.set("turbine_id", turbineId);
  if (metric) parameters.set("variable", metric.replaceAll("-", "_"));
  const proxyRequest = new Request(`${sourceUrl.origin}${sourceUrl.pathname}?${parameters}`, {
    method: "GET",
    headers: request.headers,
  });
  const upstream = await proxyProductionBackendRequest(proxyRequest, "/api/v1/scada/measurements");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production SCADA archive was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.measurements) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a valid SCADA archive page.",
    );
  }
  const data = payload.measurements.filter(isRecord).map((row) => ({
    id: text(row.sample_id),
    sequence: number(row.source_sequence),
    turbineId: text(row.turbine_id),
    sourceId: text(row.source_id),
    sourceEventId: text(row.source_event_id),
    metric: text(row.variable).replaceAll("_", "-"),
    label: text(row.label),
    timestamp: text(row.observed_at),
    receivedAt: text(row.received_at),
    value: number(row.value),
    unit: text(row.unit),
    quality: row.quality === "bad" || row.quality === "uncertain" ? row.quality : "good",
    qualityCode: text(row.quality_code) || null,
    late: row.late === true,
    isAnomaly: row.is_anomaly === true,
  }));
  return Response.json(
    {
      data,
      meta: {
        total: number(payload.meta.total),
        offset: number(payload.meta.offset),
        limit: number(payload.meta.limit, 100),
        turbineId: text(payload.meta.turbine_id) || null,
        metric: text(payload.meta.variable).replaceAll("_", "-") || null,
        from: text(payload.meta.from) || null,
        to: text(payload.meta.to) || null,
        snapshotAt: text(payload.meta.snapshot_at),
        deterministic: false,
        runtimeMode: "production",
        source: "python-fastapi-timescaledb",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export async function productionHealthAssessmentsResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const parameters = new URLSearchParams();
  const turbineId = sourceUrl.searchParams.get("turbineId")?.trim();
  if (turbineId) parameters.set("turbine_id", turbineId);
  for (const key of ["state", "risk", "cursor", "limit"] as const) {
    const value = sourceUrl.searchParams.get(key)?.trim();
    if (value) parameters.set(key, value);
  }
  const proxyRequest = new Request(`${sourceUrl.origin}${sourceUrl.pathname}?${parameters}`, {
    method: "GET",
    headers: request.headers,
  });
  const upstream = await proxyProductionBackendRequest(proxyRequest, "/api/v1/health/assessments");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production health response was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.assessments) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return valid health assessments.",
    );
  }
  const data = payload.assessments.filter(isRecord).map((row) => ({
    id: text(row.assessment_id),
    turbineId: text(row.turbine_id),
    turbineModel: text(row.turbine_model),
    healthScore: number(row.health_score),
    state: text(row.state),
    trend: text(row.trend),
    riskLevel: text(row.risk_level),
    activeAlarmCount: number(row.active_alarm_count),
    anomalyScore: number(row.anomaly_score),
    predictionAvailable: row.prediction_available === true,
    primaryFinding: text(row.primary_finding),
    missionId: text(row.mission_id) || null,
    assessedAt: text(row.assessed_at),
  }));
  return Response.json(
    {
      data,
      meta: {
        count: data.length,
        total: number(payload.meta.total),
        nextCursor: text(payload.meta.next_cursor) || null,
        hasMore: payload.meta.has_more === true,
        snapshotAt: text(payload.meta.snapshot_at),
        predictionProvider: text(payload.meta.prediction_provider) || null,
        deterministic: false,
        runtimeMode: "production",
        source: "python-fastapi",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}
