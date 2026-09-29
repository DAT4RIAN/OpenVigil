import { proxyProductionBackendRequest } from "../production-runtime.ts";
import { type JsonRecord, isRecord, text, number, list, record, jsonError } from "./shared.ts";

function assignedWorkOrder(row: JsonRecord): string | null {
  const reservation = list(row.reservations).find(isRecord);
  return reservation ? text(reservation.work_order_id) || null : null;
}

function assignedMission(row: JsonRecord): string | null {
  const reservation = list(row.reservations).find(isRecord);
  return reservation ? text(reservation.mission_id) || null : null;
}

function resourceAvailability(value: unknown): string {
  if (value === "reserved") return "reserved";
  if (value === "maintenance") return "maintenance";
  return "available";
}

export async function productionResourcesResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const category = (sourceUrl.searchParams.get("category") ?? "all").trim().toLowerCase();
  const resourceTypes: Record<string, string | null> = {
    all: null,
    "spare-parts": "spare_part",
    crews: "crew",
    vessels: "vessel",
    tools: "tool",
    weather: "__weather_only__",
  };
  if (!(category in resourceTypes)) {
    return jsonError("INVALID_RESOURCE_CATEGORY", "The resource category is invalid.", 400);
  }
  const backendUrl = new URL(request.url);
  backendUrl.search = "";
  const resourceType = resourceTypes[category];
  if (resourceType) backendUrl.searchParams.set("resource_type", resourceType);
  for (const [sourceKey, backendKey] of [
    ["q", "q"],
    ["workOrderId", "workOrderId"],
    ["cursor", "cursor"],
    ["limit", "limit"],
    ["weatherCursor", "weather_cursor"],
    ["weatherLimit", "weather_limit"],
  ] as const) {
    const value = sourceUrl.searchParams.get(sourceKey)?.trim();
    if (value) backendUrl.searchParams.set(backendKey, value);
  }
  const upstream = await proxyProductionBackendRequest(
    new Request(backendUrl, request),
    "/api/v1/resources",
  );
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production backend returned invalid JSON.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.resources)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend response did not contain a valid resources collection.",
    );
  }
  const resources = payload.resources.filter(isRecord);
  const spareParts = resources
    .filter((row) => row.resource_type === "spare_part")
    .map((row) => {
      const attributes = record(row.attributes);
      const reserved = list(row.reservations)
        .filter(isRecord)
        .reduce((sum, item) => sum + number(item.quantity), 0);
      const onHand = number(row.quantity);
      const available = Math.max(0, onHand - reserved);
      const reorderPoint = number(attributes.reorder_point);
      return {
        id: text(row.resource_id),
        partNumber: text(attributes.part_number, text(row.resource_id)),
        name: text(row.name),
        category: text(attributes.category, "uncategorized"),
        warehouse: text(attributes.warehouse),
        onHand,
        reserved,
        available,
        reorderPoint,
        unit: text(attributes.unit, "item"),
        status:
          available === 0 ? "out-of-stock" : available <= reorderPoint ? "low-stock" : "in-stock",
        reservedForWorkOrderIds: list(row.reservations)
          .filter(isRecord)
          .map((item) => text(item.work_order_id))
          .filter(Boolean),
        compatibleTurbineModels: list(attributes.compatible_turbine_models).map(String),
        updatedAt: text(row.updated_at),
      };
    });
  const crews = resources
    .filter((row) => row.resource_type === "crew")
    .map((row) => {
      const attributes = record(row.attributes);
      return {
        id: text(row.resource_id),
        name: text(row.name),
        specialties: list(attributes.specialties).map(String),
        memberCount: number(attributes.member_count, number(row.quantity)),
        availability: resourceAvailability(row.status),
        assignedWorkOrderId: assignedWorkOrder(row),
        assignedMissionId: assignedMission(row),
        certifications: list(attributes.certifications).map(String),
        currentLocation: text(attributes.current_location),
      };
    });
  const vessels = resources
    .filter((row) => row.resource_type === "vessel")
    .map((row) => {
      const attributes = record(row.attributes);
      return {
        id: text(row.resource_id),
        name: text(row.name),
        vesselType: text(attributes.vessel_type),
        availability: resourceAvailability(row.status),
        assignedWorkOrderId: assignedWorkOrder(row),
        assignedMissionId: assignedMission(row),
        capacity: number(attributes.capacity),
        maxWaveHeightM: number(attributes.max_wave_height_m),
        berth: text(attributes.berth),
        eta: text(attributes.eta) || null,
      };
    });
  const tools = resources
    .filter((row) => row.resource_type === "tool")
    .map((row) => {
      const attributes = record(row.attributes);
      return {
        id: text(row.resource_id),
        name: text(row.name),
        category: text(attributes.category),
        availability: resourceAvailability(row.status),
        assignedWorkOrderId: assignedWorkOrder(row),
        assignedMissionId: assignedMission(row),
        calibrationDueAt: text(attributes.calibration_due_at),
        location: text(attributes.location),
      };
    });
  const weatherWindows = list(payload.weather_windows)
    .filter(isRecord)
    .map((row) => {
      const attributes = record(row.attributes);
      return {
        id: text(row.window_id),
        farmId: text(row.wind_farm_id),
        startsAt: text(row.starts_at),
        endsAt: text(row.ends_at),
        suitability: row.suitable === true ? "suitable" : "unsuitable",
        windSpeedMps: number(row.wind_speed_ms),
        gustSpeedMps: number(attributes.gust_speed_mps),
        waveHeightM: number(row.wave_height_m),
        visibilityKm: number(attributes.visibility_km),
        precipitationMm: number(attributes.precipitation_mm),
        lightningRisk: text(attributes.lightning_risk),
        temperatureC: number(attributes.temperature_c),
        reason: text(attributes.reason),
        recommendedFor: list(attributes.recommended_for).map(String),
      };
    });
  const data = { spareParts, crews, vessels, tools, weatherWindows };
  const count = Object.values(data).reduce((sum, rows) => sum + rows.length, 0);
  const resourceTotal = number(payload.total, resources.length);
  const weatherCount = number(payload.weather_count, weatherWindows.length);
  return Response.json(
    {
      data,
      meta: {
        count,
        total: resourceTotal + weatherCount,
        resourceTotal,
        nextCursor: text(payload.next_cursor) || null,
        weatherNextCursor: text(payload.weather_next_cursor) || null,
        hasMore: Boolean(payload.next_cursor || payload.weather_next_cursor),
        snapshotAt: new Date().toISOString(),
        deterministic: false,
        runtimeMode: "production",
        source: "python-fastapi",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}
