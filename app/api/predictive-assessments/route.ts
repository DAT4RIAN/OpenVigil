import { jsonResponse, parseBoundedInteger } from "@/app/api/_shared";
import { readWorkflowForApi } from "@/app/api/_workflow";
import { productionPredictiveAssessmentsResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";

import {
  predictiveAssessments,
  predictiveModelMeta,
  evidenceBandFor,
  matrixRiskFor,
  predictiveRiskLevels,
  predictiveTrends,
  type PredictiveAssessment,
} from "./fixtures";

const sortModes = ["risk-desc", "anomaly-desc", "health-asc"] as const;
type SortMode = (typeof sortModes)[number];

const sortAssessments = (
  data: readonly PredictiveAssessment[],
  sort: SortMode,
): PredictiveAssessment[] =>
  [...data].sort((left, right) => {
    if (sort === "anomaly-desc") {
      return (
        right.anomalyScore - left.anomalyScore || left.turbineId.localeCompare(right.turbineId)
      );
    }
    if (sort === "health-asc") {
      return (
        left.componentHealth - right.componentHealth ||
        left.turbineId.localeCompare(right.turbineId)
      );
    }
    return (
      right.priorityScore - left.priorityScore || left.turbineId.localeCompare(right.turbineId)
    );
  });

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionPredictiveAssessmentsResponse(request);
  }
  const url = new URL(request.url);
  const turbineId = url.searchParams.get("turbineId")?.trim().toUpperCase() ?? null;
  const risk = url.searchParams.get("risk")?.trim().toLowerCase() ?? null;
  const trend = url.searchParams.get("trend")?.trim().toLowerCase() ?? null;
  const query = url.searchParams.get("q")?.trim().toLowerCase() ?? "";
  const sort = url.searchParams.get("sort")?.trim().toLowerCase() ?? "risk-desc";
  const offset = parseBoundedInteger(url.searchParams.get("offset"), 0, 0, 64);
  const limit = parseBoundedInteger(url.searchParams.get("limit"), 64, 1, 64);

  if (risk && !predictiveRiskLevels.includes(risk as (typeof predictiveRiskLevels)[number])) {
    return jsonResponse(
      { error: { code: "INVALID_RISK", message: `Unknown predictive risk level: ${risk}` } },
      400,
    );
  }
  if (trend && !predictiveTrends.includes(trend as (typeof predictiveTrends)[number])) {
    return jsonResponse(
      { error: { code: "INVALID_TREND", message: `Unknown health trend: ${trend}` } },
      400,
    );
  }
  if (!sortModes.includes(sort as SortMode)) {
    return jsonResponse(
      { error: { code: "INVALID_SORT", message: `Unknown predictive sort mode: ${sort}` } },
      400,
    );
  }
  if (offset === null || limit === null) {
    return jsonResponse(
      {
        error: {
          code: "INVALID_PAGINATION",
          message: "offset must be 0–64 and limit must be 1–64.",
        },
      },
      400,
    );
  }

  const workflow = await readWorkflowForApi();
  const currentAssessments = predictiveAssessments.map((assessment) => {
    if (assessment.turbineId !== workflow.snapshot.turbineId) return assessment;
    const closed = workflow.snapshot.workOrder.status === "completed";
    const anomalyScore = closed ? 0.42 : assessment.anomalyScore;
    const consequenceBand = closed ? 3 : assessment.consequenceBand;
    const evidenceBand = evidenceBandFor(
      anomalyScore,
      workflow.snapshot.health.mainBearingScore,
      closed ? 0 : assessment.activeAlarmCount,
    );
    const riskScore = evidenceBand * consequenceBand;
    return {
      ...assessment,
      healthScore: workflow.snapshot.health.turbineScore,
      componentHealth: workflow.snapshot.health.mainBearingScore,
      trend: closed ? ("improving" as const) : assessment.trend,
      anomalyScore,
      primaryFinding: closed ? "主轴承检查与复测已完成，健康趋势恢复" : assessment.primaryFinding,
      evidenceBand,
      consequenceBand,
      matrixRisk: matrixRiskFor(evidenceBand, consequenceBand),
      riskScore,
      priorityScore: Number(
        (
          (100 - workflow.snapshot.health.mainBearingScore) * consequenceBand +
          anomalyScore * 10 +
          (closed ? 0 : assessment.activeAlarmCount) * 5
        ).toFixed(2),
      ),
      assessedAt: workflow.snapshot.updatedAt,
    };
  });
  const filtered = currentAssessments.filter(
    (assessment) =>
      (!turbineId || assessment.turbineId === turbineId) &&
      (!risk || assessment.matrixRisk === risk) &&
      (!trend || assessment.trend === trend) &&
      (!query ||
        `${assessment.turbineId} ${assessment.component} ${assessment.primaryFinding}`
          .toLowerCase()
          .includes(query)),
  );
  const sorted = sortAssessments(filtered, sort as SortMode);
  const data = sorted.slice(offset, offset + limit);

  return jsonResponse({
    data,
    meta: {
      count: data.length,
      total: currentAssessments.length,
      filteredTotal: filtered.length,
      offset,
      limit,
      filters: { turbineId, risk, trend, query: query || null },
      sort,
      model: predictiveModelMeta,
      snapshotAt: workflow.snapshot.updatedAt,
      workflowPersistence: workflow.persistence,
      workflowRevision: workflow.snapshot.revision,
    },
  });
}
