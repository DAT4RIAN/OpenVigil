import { jsonResponse } from "@/app/api/_shared";
import { readWorkflowForApi } from "@/app/api/_workflow";
import { productionPredictiveAssessmentsResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";

import {
  predictiveAssessments,
  predictiveModelMeta,
  matrixRiskFor,
  probabilityBandFor,
  predictiveRiskLevels,
  predictiveTrends,
  type PredictiveAssessment,
} from "./fixtures";

const sortModes = ["risk-desc", "probability-desc", "rul-asc", "health-asc"] as const;
type SortMode = (typeof sortModes)[number];

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

const sortAssessments = (
  data: readonly PredictiveAssessment[],
  sort: SortMode,
): PredictiveAssessment[] =>
  [...data].sort((left, right) => {
    if (sort === "probability-desc") {
      return (
        right.failureProbability30d - left.failureProbability30d ||
        left.turbineId.localeCompare(right.turbineId)
      );
    }
    if (sort === "rul-asc") {
      return (
        left.remainingUsefulLifeDays - right.remainingUsefulLifeDays ||
        left.turbineId.localeCompare(right.turbineId)
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
  const offset = integerParameter(url.searchParams.get("offset"), 0, 0, 64);
  const limit = integerParameter(url.searchParams.get("limit"), 64, 1, 64);

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
    const failureProbability30d = closed ? 12 : assessment.failureProbability30d;
    const probabilityBand = probabilityBandFor(failureProbability30d);
    const consequenceBand = closed ? 3 : assessment.consequenceBand;
    const riskScore = probabilityBand * consequenceBand;
    return {
      ...assessment,
      healthScore: workflow.snapshot.health.turbineScore,
      componentHealth: workflow.snapshot.health.mainBearingScore,
      trend: closed ? ("improving" as const) : assessment.trend,
      failureProbability30d,
      remainingUsefulLifeDays: closed ? 126 : assessment.remainingUsefulLifeDays,
      anomalyScore: closed ? 0.42 : assessment.anomalyScore,
      primaryFinding: closed ? "主轴承检查与复测已完成，健康趋势恢复" : assessment.primaryFinding,
      probabilityBand,
      consequenceBand,
      matrixRisk: matrixRiskFor(probabilityBand, consequenceBand),
      riskScore,
      priorityScore: Number(
        (
          failureProbability30d * consequenceBand +
          (closed ? 0.42 : assessment.anomalyScore) * 10
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
