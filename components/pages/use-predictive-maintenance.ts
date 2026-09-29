"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  predictiveAssessments,
  predictiveModelMeta,
} from "@/app/api/predictive-assessments/fixtures";
import { type OperationViewState } from "@/components/ui/query-state";
import { apiGet, apiPostCommand, createIdempotencyKey, OpenVigilApiError } from "@/lib/api-client";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { deriveQueryViewState, latestValidTimestamp, queryRuntimeHealth } from "@/lib/query-state";
import {
  type TimeWindow,
  type RiskFilter,
  type TrendFilter,
  type PredictiveResponse,
  riskLabels,
  byPriority,
  withWorkflowState,
  workflowRecommendation,
  createTrendData,
  matrixCellRisk,
} from "./predictive-maintenance-support";

export function usePredictiveMaintenance({ runtimeMode }: { runtimeMode: "demo" | "production" }) {
  const workflow = useDemoWorkflow();
  const [selectedId, setSelectedId] = useState(runtimeMode === "demo" ? "WT-023" : "");
  const [timeWindow, setTimeWindow] = useState<TimeWindow>("30D");
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const [trendFilter, setTrendFilter] = useState<TrendFilter>("all");
  const [inferenceOperation, setInferenceOperation] = useState<OperationViewState>({
    lifecycle: "idle",
  });

  const endpoint = useMemo(() => {
    const params = new URLSearchParams({ limit: "64", sort: "risk-desc" });
    if (riskFilter !== "all") params.set("risk", riskFilter);
    if (trendFilter !== "all") params.set("trend", trendFilter);
    return `/api/predictive-assessments?${params.toString()}`;
  }, [riskFilter, trendFilter]);

  const assessmentsQuery = useQuery({
    queryKey: ["predictive-assessments", endpoint],
    queryFn: ({ signal }) => apiGet<PredictiveResponse>(endpoint, signal),
    initialData:
      runtimeMode === "demo"
        ? {
            data: [...predictiveAssessments],
            meta: {
              count: predictiveAssessments.length,
              total: predictiveAssessments.length,
              filteredTotal: predictiveAssessments.length,
              model: predictiveModelMeta,
            },
          }
        : undefined,
    initialDataUpdatedAt: 0,
    placeholderData: (previousData) => previousData,
    retry: false,
    staleTime: 60_000,
  });
  const assessmentState = deriveQueryViewState({
    data: assessmentsQuery.data?.data,
    dataUpdatedAt: assessmentsQuery.dataUpdatedAt,
    error: assessmentsQuery.error,
    isError: assessmentsQuery.isError,
    isFetching: assessmentsQuery.isFetching,
    isPending: assessmentsQuery.isPending,
    isStale: assessmentsQuery.isStale,
    isEmpty: (data) => data.length === 0,
    sourceUpdatedAt:
      runtimeMode === "production"
        ? latestValidTimestamp(
            assessmentsQuery.data?.data.map((assessment) => assessment.assessedAt) ?? [],
          )
        : null,
    staleAfterMs: 60_000,
  });
  const pageHealth = queryRuntimeHealth(assessmentState, "在线状态评估");

  const fleet = useMemo(() => {
    const source = assessmentsQuery.data?.data ?? [];
    return (
      runtimeMode === "demo"
        ? source.map((assessment) => withWorkflowState(assessment, workflow))
        : [...source]
    ).sort(byPriority);
  }, [assessmentsQuery.data?.data, runtimeMode, workflow]);

  useEffect(() => {
    if (!fleet.length) return;
    const requested = new URLSearchParams(window.location.search).get("turbineId")?.toUpperCase();
    const next =
      (requested && fleet.some((item) => item.turbineId === requested) ? requested : null) ??
      (fleet.some((item) => item.turbineId === selectedId) ? selectedId : fleet[0].turbineId);
    if (next === selectedId) return;
    const timer = window.setTimeout(() => setSelectedId(next), 0);
    return () => window.clearTimeout(timer);
  }, [fleet, selectedId]);

  const visible = useMemo(() => {
    return fleet
      .filter(
        (assessment) =>
          (riskFilter === "all" || assessment.matrixRisk === riskFilter) &&
          (trendFilter === "all" || assessment.trend === trendFilter),
      )
      .sort(byPriority);
  }, [fleet, riskFilter, trendFilter]);
  const selected =
    fleet.find((assessment) => assessment.turbineId === selectedId) ?? fleet[0] ?? null;
  const closedLoop = Boolean(
    runtimeMode === "demo" &&
    selected?.turbineId === "WT-023" &&
    workflow.workOrderStatus === "completed",
  );
  const recommendation = selected
    ? runtimeMode === "demo" && selected.turbineId === "WT-023"
      ? workflowRecommendation(workflow)
      : {
          title: "按风险优先级安排维护",
          detail: `${selected.component} 当前为 ${riskLabels[selected.matrixRisk]}风险，建议结合异常、健康、告警与资源窗口持续评估。`,
        }
    : null;
  const trendData = useMemo(
    () =>
      selected ? createTrendData(selected, timeWindow, closedLoop) : { health: [], anomaly: [] },
    [closedLoop, selected, timeWindow],
  );
  const matrix = useMemo(
    () =>
      Array.from({ length: 5 }, (_, consequenceIndex) => {
        const consequence = 5 - consequenceIndex;
        return Array.from({ length: 5 }, (_, evidenceIndex) => {
          const evidence = evidenceIndex + 1;
          return {
            consequence,
            evidence,
            risk: matrixCellRisk(evidence, consequence),
            records: fleet.filter(
              (assessment) =>
                assessment.evidenceBand === evidence && assessment.consequenceBand === consequence,
            ),
          };
        });
      }),
    [fleet],
  );

  const fleetHighRisk = fleet.filter((assessment) =>
    ["critical", "high"].includes(assessment.matrixRisk),
  ).length;
  const modelMeta = assessmentsQuery.data?.meta.model ?? predictiveModelMeta;

  const runOnlineInference = async (
    operationKey = createIdempotencyKey("predictive-assessment-run"),
  ) => {
    if (!selected) return;
    const turbineId = selected.turbineId;
    const startedAt = Date.now();
    setInferenceOperation({ lifecycle: "running", operationKey, startedAt });
    try {
      const result = await apiPostCommand<{
        readonly count: number;
        readonly failed: number;
        readonly predictions: readonly { readonly error_code?: string }[];
      }>("/api/backend/predictive-assessments/run", { turbine_ids: [turbineId] }, operationKey);
      if (result.failed > 0) {
        setInferenceOperation({
          lifecycle: "failed",
          operationKey,
          startedAt,
          completedAt: Date.now(),
          code:
            result.predictions.find((prediction) => prediction.error_code)?.error_code ??
            "PREDICTION_PARTIAL_FAILURE",
          message: `${result.failed} / ${result.count} 个在线评估未完成；已完成结果不受影响。`,
        });
        return;
      }
      const refreshed = await assessmentsQuery.refetch();
      setInferenceOperation({
        lifecycle: "success",
        operationKey,
        startedAt,
        completedAt: Date.now(),
        message: refreshed.isError
          ? "权威命令已确认完成，但最新读取失败；请按页面 Stale 状态恢复。"
          : "权威服务已确认完成，最新在线预测读取已刷新。",
      });
    } catch (error) {
      const apiError = error instanceof OpenVigilApiError ? error : null;
      setInferenceOperation({
        lifecycle: apiError?.code === "COMMAND_RESULT_UNKNOWN" ? "result-unknown" : "failed",
        operationKey: apiError?.operationKey ?? operationKey,
        startedAt,
        completedAt: Date.now(),
        code: apiError?.code ?? "PREDICTION_RUN_FAILED",
        message: error instanceof Error ? error.message : "在线评估失败。",
      });
    }
  };
  return {
    selectedId,
    setSelectedId,
    timeWindow,
    setTimeWindow,
    riskFilter,
    setRiskFilter,
    trendFilter,
    setTrendFilter,
    inferenceOperation,
    assessmentsQuery,
    assessmentState,
    pageHealth,
    fleet,
    visible,
    selected,
    closedLoop,
    recommendation,
    trendData,
    matrix,
    fleetHighRisk,
    modelMeta,
    runOnlineInference,
  };
}
