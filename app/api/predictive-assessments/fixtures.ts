import { turbines, windFarm } from "@/lib/farm-data";
import { healthAssessments } from "@/lib/health-data";
import { subsystemHealth } from "@/lib/telemetry-data";
import type { HealthAssessment, RiskLevel, TrendDirection, TurbineStatus } from "@/lib/types";

export const predictiveRiskLevels = ["critical", "high", "medium", "low"] as const;

export type PredictiveRiskLevel = (typeof predictiveRiskLevels)[number];

export interface PredictiveAssessment extends HealthAssessment {
  readonly component: string;
  readonly componentHealth: number;
  readonly turbineStatus: TurbineStatus;
  readonly activeAlarmCount: number;
  readonly evidenceBand: number;
  readonly consequenceBand: number;
  readonly matrixRisk: RiskLevel;
  readonly riskScore: number;
  readonly priorityScore: number;
}

export const predictiveModelMeta = Object.freeze({
  id: "windops-condition-evidence-fixture-v2.0.0",
  label: "OpenVigil 状态证据演示评估器",
  mode: "deterministic-evidence-fixture",
  observationWindowHours: 24,
  evaluatedAt: windFarm.lastUpdatedAt,
  deterministic: true,
  readOnly: true,
  performsRealInference: false,
  notice: "Demo 隔离的确定性状态演示；不生成寿命或故障概率，不参与真实检修与现场控制。",
});

const clamp = (value: number, minimum: number, maximum: number): number =>
  Math.max(minimum, Math.min(maximum, value));

export const evidenceBandFor = (
  anomalyScore: number,
  componentHealth: number,
  activeAlarmCount: number,
): number => {
  const anomalyBand =
    anomalyScore >= 0.9
      ? 5
      : anomalyScore >= 0.75
        ? 4
        : anomalyScore >= 0.6
          ? 3
          : anomalyScore >= 0.4
            ? 2
            : 1;
  const healthBand =
    componentHealth < 50
      ? 5
      : componentHealth < 65
        ? 4
        : componentHealth < 75
          ? 3
          : componentHealth < 90
            ? 2
            : 1;
  return clamp(Math.max(anomalyBand, healthBand, activeAlarmCount), 1, 5);
};

const consequenceBandFor = (status: TurbineStatus, activeAlarmCount: number): number =>
  clamp(
    2 +
      (status === "critical" ? 2 : status === "warning" || status === "offline" ? 1 : 0) +
      (activeAlarmCount >= 3 ? 1 : 0),
    1,
    5,
  );

export const matrixRiskFor = (evidenceBand: number, consequenceBand: number): RiskLevel => {
  const product = evidenceBand * consequenceBand;
  if (product >= 20) return "critical";
  if (product >= 12) return "high";
  if (product >= 6) return "medium";
  return "low";
};

const componentNames = subsystemHealth.map((subsystem) => subsystem.name);
const featuredBearing = subsystemHealth.find((subsystem) => subsystem.key === "main-bearing")!;

export const predictiveAssessments: readonly PredictiveAssessment[] = Object.freeze(
  healthAssessments
    .map((assessment): PredictiveAssessment => {
      const turbine = turbines.find((candidate) => candidate.id === assessment.turbineId)!;
      const number = Number(assessment.turbineId.slice(3));
      const isFeatured = assessment.turbineId === "WT-023";
      const consequenceBand = isFeatured
        ? 4
        : consequenceBandFor(turbine.status, turbine.activeAlarmCount);
      const component = isFeatured
        ? featuredBearing.name
        : (componentNames[(number * 7 + 3) % componentNames.length] ?? "传动链");
      const componentHealth = isFeatured
        ? featuredBearing.healthScore
        : clamp(assessment.healthScore - ((number * 3) % 5), 45, 99);
      const evidenceBand = evidenceBandFor(
        assessment.anomalyScore,
        componentHealth,
        turbine.activeAlarmCount,
      );
      const riskScore = evidenceBand * consequenceBand;
      const matrixRisk = matrixRiskFor(evidenceBand, consequenceBand);

      return Object.freeze({
        ...assessment,
        component,
        componentHealth,
        turbineStatus: turbine.status,
        activeAlarmCount: turbine.activeAlarmCount,
        evidenceBand,
        consequenceBand,
        matrixRisk,
        riskScore,
        priorityScore: Number(
          (
            (100 - componentHealth) * consequenceBand +
            assessment.anomalyScore * 10 +
            turbine.activeAlarmCount * 5
          ).toFixed(2),
        ),
      });
    })
    .sort(
      (left, right) =>
        right.priorityScore - left.priorityScore || left.turbineId.localeCompare(right.turbineId),
    ),
);

export const predictiveTrends: readonly TrendDirection[] = [
  "improving",
  "stable",
  "declining",
] as const;
