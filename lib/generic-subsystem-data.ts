import type { HealthState, WindTurbine } from "./types";

export interface GenericSubsystemAssessment {
  readonly key: string;
  readonly name: string;
  readonly healthScore: number;
  readonly state: HealthState;
  readonly alertCount: number;
}

const subsystemProfiles = [
  { key: "blades", name: "叶片", healthOffset: 3 },
  { key: "hub", name: "轮毂", healthOffset: 1 },
  { key: "main-shaft", name: "主轴", healthOffset: 0 },
  { key: "main-bearing", name: "主轴承", healthOffset: -5 },
  { key: "gearbox", name: "齿轮箱", healthOffset: 2 },
  { key: "generator", name: "发电机", healthOffset: 5 },
  { key: "converter", name: "变流器", healthOffset: -3 },
  { key: "yaw", name: "偏航系统", healthOffset: -1 },
  { key: "pitch", name: "变桨系统", healthOffset: -2 },
  { key: "tower", name: "塔架", healthOffset: 2 },
  { key: "foundation", name: "基础", healthOffset: 4 },
  { key: "electrical", name: "电气系统", healthOffset: 6 },
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
    return { profile, healthScore };
  });

  const priority = estimates
    .map((estimate, index) => ({ estimate, index }))
    .sort(
      (left, right) =>
        left.estimate.healthScore - right.estimate.healthScore ||
        left.estimate.profile.key.localeCompare(right.estimate.profile.key),
    );
  const alertCounts = Array.from({ length: subsystemProfiles.length }, () => 0);
  const totalAlerts = Math.max(0, Math.trunc(turbine.activeAlarmCount));
  for (let alertIndex = 0; alertIndex < totalAlerts; alertIndex += 1) {
    const target = priority[alertIndex % priority.length];
    if (target) alertCounts[target.index] += 1;
  }

  return estimates.map(({ profile, healthScore }, index) => {
    const alertCount = alertCounts[index] ?? 0;

    return Object.freeze({
      key: profile.key,
      name: profile.name,
      healthScore,
      state: assessmentState(turbine, healthScore),
      alertCount,
    });
  });
}
