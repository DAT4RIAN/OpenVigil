import type { HealthState, WindTurbine } from "./types";

export interface GenericSubsystemAssessment {
  readonly key: string;
  readonly name: string;
  readonly healthScore: number;
  readonly state: HealthState;
  readonly alertCount: number;
  readonly failureProbability30d: number;
  readonly rulDays: number;
}

const subsystemProfiles = [
  { key: "blades", name: "叶片", healthOffset: 3, riskOffset: -3, rulOffset: 48 },
  { key: "hub", name: "轮毂", healthOffset: 1, riskOffset: -1, rulOffset: 34 },
  { key: "main-shaft", name: "主轴", healthOffset: 0, riskOffset: 1, rulOffset: 21 },
  { key: "main-bearing", name: "主轴承", healthOffset: -5, riskOffset: 6, rulOffset: -18 },
  { key: "gearbox", name: "齿轮箱", healthOffset: 2, riskOffset: 0, rulOffset: 28 },
  { key: "generator", name: "发电机", healthOffset: 5, riskOffset: -4, rulOffset: 62 },
  { key: "converter", name: "变流器", healthOffset: -3, riskOffset: 4, rulOffset: 6 },
  { key: "yaw", name: "偏航系统", healthOffset: -1, riskOffset: 3, rulOffset: 17 },
  { key: "pitch", name: "变桨系统", healthOffset: -2, riskOffset: 2, rulOffset: 12 },
  { key: "tower", name: "塔架", healthOffset: 2, riskOffset: -2, rulOffset: 83 },
  { key: "foundation", name: "基础", healthOffset: 4, riskOffset: -2, rulOffset: 95 },
  { key: "electrical", name: "电气系统", healthOffset: 6, riskOffset: -5, rulOffset: 74 },
] as const;

const clamp = (value: number, minimum: number, maximum: number): number =>
  Math.min(maximum, Math.max(minimum, value));

function assessmentState(turbine: WindTurbine, score: number): HealthState {
  if (turbine.status === "offline" || turbine.status === "communication-lost") return "offline";
  if (turbine.status === "maintenance") return "maintenance";
  if (score < 65) return "critical";
  if (score < 78) return "degraded";
  if (score < 90) return "watch";
  return "healthy";
}

/**
 * Build a repeatable 12-subsystem assessment for turbines without a dedicated
 * telemetry model. Values are deterministic demo estimates derived from the
 * turbine health record; they are not predictive-model inference.
 */
export function buildGenericSubsystemAssessments(
  turbine: WindTurbine,
): readonly GenericSubsystemAssessment[] {
  const estimates = subsystemProfiles.map((profile) => {
    const healthScore = clamp(turbine.healthScore + profile.healthOffset, 42, 99);
    const failureProbability30d = clamp(
      Math.round((100 - healthScore) * 0.72 + profile.riskOffset),
      2,
      62,
    );
    const rulDays = clamp(
      Math.round(healthScore * 4.4 - failureProbability30d * 2.1 + profile.rulOffset),
      18,
      540,
    );

    return { profile, healthScore, failureProbability30d, rulDays };
  });

  const priority = estimates
    .map((estimate, index) => ({ estimate, index }))
    .sort(
      (left, right) =>
        left.estimate.healthScore - right.estimate.healthScore ||
        right.estimate.failureProbability30d - left.estimate.failureProbability30d ||
        left.estimate.profile.key.localeCompare(right.estimate.profile.key),
    );
  const alertCounts = Array.from({ length: subsystemProfiles.length }, () => 0);
  const totalAlerts = Math.max(0, Math.trunc(turbine.activeAlarmCount));
  for (let alertIndex = 0; alertIndex < totalAlerts; alertIndex += 1) {
    const target = priority[alertIndex % priority.length];
    if (target) alertCounts[target.index] += 1;
  }

  return estimates.map(({ profile, healthScore, failureProbability30d, rulDays }, index) => {
    const alertCount = alertCounts[index] ?? 0;

    return Object.freeze({
      key: profile.key,
      name: profile.name,
      healthScore,
      state: assessmentState(turbine, healthScore),
      alertCount,
      failureProbability30d,
      rulDays,
    });
  });
}
