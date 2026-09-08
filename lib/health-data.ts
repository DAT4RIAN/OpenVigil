import { turbines, windFarm } from "./farm-data";
import type { HealthAssessment, HealthState, RiskLevel, TrendDirection } from "./types";

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.max(minimum, Math.min(maximum, value));

const stateForScore = (score: number, status: string): HealthState => {
  if (status === "maintenance") return "maintenance";
  if (status === "offline" || status === "communication-lost") return "offline";
  if (score < 60) return "critical";
  if (score < 75) return "degraded";
  if (score < 90) return "watch";
  return "healthy";
};

const riskFor = (failureProbability: number, status: string): RiskLevel => {
  if (status === "critical" || failureProbability >= 45) return "critical";
  if (failureProbability >= 25) return "high";
  if (failureProbability >= 12) return "medium";
  return "low";
};

const findingFor = (number: number, status: string): string => {
  if (number === 23) return "主轴承振动与温升联合异常";
  if (number === 41) return "齿轮箱磨粒计数持续升高";
  if (number === 18) return "塔筒一阶频率偏移待复核";
  if (status === "maintenance") return "计划维护窗口执行中";
  if (status === "offline") return "停机状态，等待恢复确认";
  if (status === "communication-lost") return "通信中断，健康评估已降级";
  if (status === "warning") return "趋势偏离基线，建议持续观察";
  return "关键子系统运行稳定";
};

export const healthAssessments: readonly HealthAssessment[] = Object.freeze(
  turbines.map((turbine) => {
    const number = Number(turbine.id.slice(3));
    const isFeatured = turbine.id === "WT-023";
    const failureProbability30d = isFeatured
      ? 34
      : clamp(
          Math.round((100 - turbine.healthScore) * 1.25 + turbine.activeAlarmCount * 2.8),
          2,
          58,
        );
    const trend: TrendDirection = isFeatured
      ? "declining"
      : number % 11 === 0
        ? "declining"
        : number % 4 === 0
          ? "improving"
          : "stable";

    return Object.freeze({
      id: `HEALTH-${turbine.id}-20260813`,
      turbineId: turbine.id,
      healthScore: turbine.healthScore,
      state: stateForScore(turbine.healthScore, turbine.status),
      trend,
      riskLevel: riskFor(failureProbability30d, turbine.status),
      failureProbability30d,
      remainingUsefulLifeDays: isFeatured
        ? 47
        : clamp(
            Math.round(turbine.healthScore * 9.5 - failureProbability30d * 1.8 + number),
            45,
            980,
          ),
      anomalyScore: isFeatured
        ? 0.86
        : Number(
            clamp(
              0.08 + (100 - turbine.healthScore) / 110 + turbine.activeAlarmCount * 0.035,
              0.05,
              0.94,
            ).toFixed(2),
          ),
      primaryFinding: findingFor(number, turbine.status),
      assessedAt: windFarm.lastUpdatedAt,
    });
  }),
);

export const getHealthAssessment = (turbineId: string) =>
  healthAssessments.find((assessment) => assessment.turbineId === turbineId.trim().toUpperCase());
