import { healthAssessments, windFarm } from "@/lib";
import type { HealthState, RiskLevel } from "@/lib/types";

import { jsonResponse } from "../_shared";

const healthStates: readonly HealthState[] = [
  "healthy",
  "watch",
  "degraded",
  "critical",
  "maintenance",
  "offline",
];
const riskLevels: readonly RiskLevel[] = ["critical", "high", "medium", "low"];

export function GET(request: Request): Response {
  const url = new URL(request.url);
  const turbineId = url.searchParams.get("turbineId")?.trim().toUpperCase() ?? null;
  const state = url.searchParams.get("state")?.trim().toLowerCase() ?? null;
  const risk = url.searchParams.get("risk")?.trim().toLowerCase() ?? null;

  if (state && !healthStates.includes(state as HealthState)) {
    return jsonResponse(
      { error: { code: "INVALID_STATE", message: `Unknown health state: ${state}` } },
      400,
    );
  }
  if (risk && !riskLevels.includes(risk as RiskLevel)) {
    return jsonResponse(
      { error: { code: "INVALID_RISK", message: `Unknown risk level: ${risk}` } },
      400,
    );
  }

  const data = healthAssessments.filter(
    (assessment) =>
      (!turbineId || assessment.turbineId === turbineId) &&
      (!state || assessment.state === state) &&
      (!risk || assessment.riskLevel === risk),
  );

  return jsonResponse({
    data,
    meta: {
      count: data.length,
      total: healthAssessments.length,
      turbineId,
      state,
      risk,
      snapshotAt: windFarm.lastUpdatedAt,
      deterministic: true,
    },
  });
}
