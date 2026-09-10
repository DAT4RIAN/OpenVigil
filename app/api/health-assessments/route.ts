import { healthAssessments } from "@/lib";
import { overlayWorkflowHealth } from "@/lib/server-workflow-overlays";
import type { HealthState, RiskLevel } from "@/lib/types";
import { productionHealthAssessmentsResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";

import { jsonResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

const healthStates: readonly HealthState[] = [
  "healthy",
  "watch",
  "degraded",
  "critical",
  "maintenance",
  "offline",
];
const riskLevels: readonly RiskLevel[] = ["critical", "high", "medium", "low"];

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionHealthAssessmentsResponse(request);
  }
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

  const workflow = await readWorkflowForApi();
  const currentAssessments = overlayWorkflowHealth(healthAssessments, workflow.snapshot);
  const data = currentAssessments.filter(
    (assessment) =>
      (!turbineId || assessment.turbineId === turbineId) &&
      (!state || assessment.state === state) &&
      (!risk || assessment.riskLevel === risk),
  );

  return jsonResponse({
    data,
    meta: {
      count: data.length,
      total: currentAssessments.length,
      turbineId,
      state,
      risk,
      snapshotAt: workflow.snapshot.updatedAt,
      deterministic: true,
      workflowPersistence: workflow.persistence,
      workflowRevision: workflow.snapshot.revision,
    },
  });
}
