import { healthAssessments, subsystemHealth, turbines, windFarm } from "@/lib";
import type { HealthAssessment, RiskLevel, TrendDirection, TurbineStatus } from "@/lib/types";

export const predictiveRiskLevels = ["critical", "high", "medium", "low"] as const;

export type PredictiveRiskLevel = (typeof predictiveRiskLevels)[number];

export interface PredictiveAssessment extends HealthAssessment {
  readonly component: string;
  readonly componentHealth: number;
  readonly turbineStatus: TurbineStatus;
  readonly activeAlarmCount: number;
  readonly probabilityBand: number;
  readonly consequenceBand: number;
  readonly matrixRisk: RiskLevel;
  readonly riskScore: number;
  readonly priorityScore: number;
}

export const predictiveModelMeta = Object.freeze({
  id: "windops-rul-fixture-v1.4.2",
  label: "WindOps RUL 演示模型",
  mode: "deterministic-fixture",
  horizonDays: 30,
  evaluatedAt: windFarm.lastUpdatedAt,
  deterministic: true,
  readOnly: true,
  performsRealInference: false,
  notice: "作品集演示用确定性评估，不执行真实模型推理，不应用于现场控制。",
});

const clamp = (value: number, minimum: number, maximum: number): number =>
  Math.max(minimum, Math.min(maximum, value));

export const probabilityBandFor = (probability: number): number => {
  if (probability > 40) return 5;
  if (probability > 25) return 4;
  if (probability > 12) return 3;
  if (probability > 5) return 2;
  return 1;
};

const consequenceBandFor = (status: TurbineStatus, activeAlarmCount: number): number =>
  clamp(
    2 +
      (status === "critical" ? 2 : status === "warning" || status === "offline" ? 1 : 0) +
      (activeAlarmCount >= 3 ? 1 : 0),
    1,
    5,
  );

export const matrixRiskFor = (probabilityBand: number, consequenceBand: number): RiskLevel => {
  const product = probabilityBand * consequenceBand;
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
      const probabilityBand = probabilityBandFor(assessment.failureProbability30d);
      const consequenceBand = isFeatured
        ? 4
        : consequenceBandFor(turbine.status, turbine.activeAlarmCount);
      const riskScore = probabilityBand * consequenceBand;
      const matrixRisk = matrixRiskFor(probabilityBand, consequenceBand);
      const component = isFeatured
        ? featuredBearing.name
        : (componentNames[(number * 7 + 3) % componentNames.length] ?? "传动链");
      const componentHealth = isFeatured
        ? featuredBearing.healthScore
        : clamp(assessment.healthScore - ((number * 3) % 5), 45, 99);

      return Object.freeze({
        ...assessment,
        component,
        componentHealth,
        turbineStatus: turbine.status,
        activeAlarmCount: turbine.activeAlarmCount,
        probabilityBand,
        consequenceBand,
        matrixRisk,
        riskScore,
        priorityScore: Number(
          (
            assessment.failureProbability30d * consequenceBand +
            assessment.anomalyScore * 10
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
