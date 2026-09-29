import {
  evidenceBandFor,
  matrixRiskFor,
  type PredictiveAssessment,
} from "@/app/api/predictive-assessments/fixtures";
import { type TimeSeriesPoint } from "@/components/charts/time-series-chart";
import { scadaSeries } from "@/lib/telemetry-data";
import type { DemoWorkflowState } from "@/lib/demo-workflow";
import type { RiskLevel, TrendDirection } from "@/lib/types";

export const windows = ["24H", "7D", "30D", "90D"] as const;

export type TimeWindow = (typeof windows)[number];

export type RiskFilter = "all" | RiskLevel;

export type TrendFilter = "all" | TrendDirection;

export type PredictiveAssessmentView = PredictiveAssessment & {
  readonly modelId?: string;
  readonly deploymentId?: string;
  readonly featureObservedAt?: string;
  readonly latencyMs?: number;
};

export type PredictiveResponse = {
  data: PredictiveAssessmentView[];
  meta: {
    count: number;
    total: number;
    filteredTotal: number;
    model: {
      id: string;
      label: string;
      mode: string;
      observationWindowHours: number;
      evaluatedAt: string;
      deterministic: boolean;
      readOnly: boolean;
      performsRealInference: boolean;
      notice: string;
    };
  };
};

export const riskLabels: Record<RiskLevel, string> = {
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
};

export const trendLabels: Record<TrendDirection, string> = {
  improving: "改善",
  stable: "稳定",
  declining: "下降",
};

export const riskTone = (risk: RiskLevel): "critical" | "warning" | "info" | "success" =>
  risk === "critical"
    ? "critical"
    : risk === "high"
      ? "warning"
      : risk === "medium"
        ? "info"
        : "success";

export const byPriority = (left: PredictiveAssessment, right: PredictiveAssessment): number =>
  right.priorityScore - left.priorityScore || left.turbineId.localeCompare(right.turbineId);

export const dateLabel = (date: Date, window: TimeWindow): string =>
  window === "24H"
    ? date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })
    : `${date.getMonth() + 1}/${date.getDate()}`;

export function withWorkflowState<T extends PredictiveAssessment>(
  assessment: T,
  workflow: DemoWorkflowState,
): T {
  if (assessment.turbineId !== "WT-023" || workflow.workOrderStatus !== "completed") {
    return assessment;
  }

  const evidenceBand = evidenceBandFor(0.42, workflow.mainBearingHealthScore, 0);
  const riskScore = evidenceBand * assessment.consequenceBand;
  return {
    ...assessment,
    healthScore: workflow.turbineHealthScore,
    componentHealth: workflow.mainBearingHealthScore,
    state: "watch",
    trend: "improving",
    riskLevel: "medium",
    anomalyScore: 0.42,
    primaryFinding: "现场复测后振动与温升回落，进入趋势观察",
    evidenceBand,
    riskScore,
    matrixRisk: matrixRiskFor(evidenceBand, assessment.consequenceBand),
    priorityScore: Number(
      ((100 - workflow.mainBearingHealthScore) * assessment.consequenceBand + 4.2).toFixed(2),
    ),
  };
}

export function workflowRecommendation(workflow: DemoWorkflowState): {
  readonly title: string;
  readonly detail: string;
} {
  if (workflow.missionStatus === "completed" || workflow.workOrderStatus === "completed") {
    return {
      title: "维护闭环已验证",
      detail: `${workflow.knowledgeCaseId ?? "WT-023 闭环案例"} 已沉淀，风险由 HIGH 降至 MEDIUM。`,
    };
  }

  if (workflow.workOrderStatus === "in-progress") {
    return {
      title: "现场工单执行中",
      detail: `WO-20260823-017 已完成 ${workflow.completedTaskIds.length}/5 项任务，等待复测与结果验证。`,
    };
  }

  if (workflow.workOrderStatus === "scheduled") {
    return {
      title: "方案 B 已批准并排程",
      detail: "人工审批已记录；WO-20260823-017 等待现场班组启动。",
    };
  }

  if (workflow.decisionStatus === "rejected" || workflow.missionStatus === "decision-pending") {
    return {
      title: "方案 B 已被拒绝",
      detail: "高风险执行门禁保持锁定；等待 Agent 生成新的处置方案。",
    };
  }

  if (workflow.decisionStatus === "revision-requested" || workflow.missionStatus === "diagnosed") {
    return {
      title: "方案 B 待修订",
      detail: "审批人已请求补充证据或调整方案；WO-20260823-017 保持草稿。",
    };
  }

  if (workflow.decisionStatus === "approved") {
    return {
      title: "方案 B 已获人工批准",
      detail: "审批记录已写入；WO-20260823-017 等待排程同步。",
    };
  }

  return {
    title: "方案 B 等待人工审批",
    detail: "高风险执行门禁仍锁定；WO-20260823-017 保持草稿，尚未排程。",
  };
}

export function createTrendData(
  assessment: PredictiveAssessment,
  window: TimeWindow,
  completed: boolean,
): { health: TimeSeriesPoint[]; anomaly: TimeSeriesPoint[] } {
  const windowConfig = {
    "24H": { count: 25, intervalHours: 1 },
    "7D": { count: 28, intervalHours: 6 },
    "30D": { count: 30, intervalHours: 24 },
    "90D": { count: 30, intervalHours: 72 },
  }[window];
  const turbineNumber = Number(assessment.turbineId.slice(3));
  const end = Date.parse("2026-08-13T10:30:00+08:00");
  const scadaAnomaly = scadaSeries.find((series) => series.metric === "anomaly-score");
  const sourcePoints =
    assessment.turbineId === "WT-023" && window === "24H"
      ? scadaAnomaly?.points.slice(-windowConfig.count)
      : undefined;

  const anomaly = Array.from({ length: windowConfig.count }, (_, index): TimeSeriesPoint => {
    const timestamp = new Date(
      end - (windowConfig.count - 1 - index) * windowConfig.intervalHours * 60 * 60 * 1000,
    );
    const progress = index / Math.max(1, windowConfig.count - 1);
    const source = sourcePoints?.[index];
    const baseline = Math.max(0.08, assessment.anomalyScore - 0.2);
    const simulated =
      baseline +
      (assessment.anomalyScore - baseline) * progress +
      Math.sin((index + turbineNumber) * 0.74) * 0.025;
    const preMaintenance = 0.72 + 0.14 * progress + Math.sin(index * 0.74) * 0.018;
    const value = completed
      ? preMaintenance - Math.max(0, (progress - 0.72) / 0.28) * 0.44
      : (source?.value ?? simulated);

    return {
      timestamp: dateLabel(timestamp, window),
      value: Number(Math.max(0.04, value).toFixed(2)),
      anomaly: value >= 0.65,
      aiEvent: Boolean(source?.aiEvent) || index === Math.floor(windowConfig.count * 0.72),
    };
  });

  const health = anomaly.map((point, index): TimeSeriesPoint => {
    const progress = index / Math.max(1, anomaly.length - 1);
    const historicalOffset =
      assessment.trend === "declining" ? 9 : assessment.trend === "improving" ? -5 : 2;
    const recovery = completed ? Math.max(0, (progress - 0.72) / 0.28) * 15 : 0;
    const value =
      assessment.componentHealth +
      historicalOffset * (1 - progress) +
      recovery -
      (completed ? 15 : 0) +
      Math.sin((index + turbineNumber) * 0.52) * 0.7;
    return {
      timestamp: point.timestamp,
      value: Number(Math.max(35, Math.min(99, value)).toFixed(1)),
      anomaly: value < 75,
      aiEvent: point.aiEvent,
    };
  });

  return { health, anomaly };
}

export function matrixCellRisk(evidence: number, consequence: number): RiskLevel {
  return matrixRiskFor(evidence, consequence);
}
