import type {
  ScadaMetric,
  ScadaPoint,
  ScadaSeries,
  ScadaThreshold,
  SubsystemHealth,
  WeatherWindow,
} from "./types";

const SERIES_START_MS = Date.parse("2026-08-12T10:30:00+08:00");
const INTERVAL_MS = 15 * 60 * 1000;
const POINT_COUNT = 97;
const LAST_INDEX = POINT_COUNT - 1;

const round = (value: number, precision: number): number => {
  const factor = 10 ** precision;
  return Math.round(value * factor) / factor;
};

const cycle = (index: number, cycles: number, amplitude: number): number =>
  amplitude * Math.sin((Math.PI * 2 * cycles * index) / LAST_INDEX);

const anomalyRamp = (index: number): number =>
  Math.max(0, Math.min(1, (index - 48) / (LAST_INDEX - 48)));

interface SeriesDefinition {
  readonly metric: ScadaMetric;
  readonly label: string;
  readonly unit: string;
  readonly precision: number;
  readonly normalRange: readonly [number, number];
  readonly thresholds: readonly ScadaThreshold[];
  readonly valueAt: (index: number) => number;
  readonly isAnomalyAt?: (index: number) => boolean;
  readonly aiEvents?: Readonly<Record<number, string>>;
  readonly uncertainAt?: readonly number[];
}

const upperThresholds = (
  metric: string,
  warning: number,
  critical: number,
): readonly ScadaThreshold[] => [
  {
    id: `${metric}-warning`,
    label: "Warning",
    value: warning,
    direction: "above",
    severity: "warning",
  },
  {
    id: `${metric}-critical`,
    label: "Critical",
    value: critical,
    direction: "above",
    severity: "critical",
  },
];

const createSeries = (definition: SeriesDefinition): ScadaSeries => {
  const points: readonly ScadaPoint[] = Array.from(
    { length: POINT_COUNT },
    (_, index): ScadaPoint => ({
      timestamp: new Date(SERIES_START_MS + index * INTERVAL_MS).toISOString(),
      value: round(definition.valueAt(index), definition.precision),
      quality: definition.uncertainAt?.includes(index) ? "uncertain" : "good",
      isAnomaly: definition.isAnomalyAt?.(index) ?? false,
      aiEvent: definition.aiEvents?.[index] ?? null,
    }),
  );

  return {
    id: `SCADA-WT-023-${definition.metric}`,
    turbineId: "WT-023",
    metric: definition.metric,
    label: definition.label,
    unit: definition.unit,
    precision: definition.precision,
    currentValue: points[points.length - 1]?.value ?? 0,
    normalRange: definition.normalRange,
    thresholds: definition.thresholds,
    points,
  };
};

const definitions: readonly SeriesDefinition[] = [
  {
    metric: "wind-speed",
    label: "Wind Speed",
    unit: "m/s",
    precision: 1,
    normalRange: [3, 20],
    thresholds: upperThresholds("wind-speed", 20, 25),
    valueAt: (index) => 9.7 + cycle(index, 1, 1.25) + cycle(index, 4, 0.32),
  },
  {
    metric: "wind-direction",
    label: "Wind Direction",
    unit: "°",
    precision: 0,
    normalRange: [0, 360],
    thresholds: [],
    valueAt: (index) => 124 + cycle(index, 1, 18) + cycle(index, 3, 7),
  },
  {
    metric: "rotor-speed",
    label: "Rotor Speed",
    unit: "rpm",
    precision: 1,
    normalRange: [5.5, 13.2],
    thresholds: upperThresholds("rotor-speed", 13.4, 14.1),
    valueAt: (index) => 11.6 + cycle(index, 1, 1.05) + cycle(index, 5, 0.21),
  },
  {
    metric: "generator-speed",
    label: "Generator Speed",
    unit: "rpm",
    precision: 1,
    normalRange: [6, 14.5],
    thresholds: upperThresholds("generator-speed", 14.8, 15.5),
    valueAt: (index) => 12.4 + cycle(index, 1, 1.12) + cycle(index, 5, 0.18),
    uncertainAt: [22],
  },
  {
    metric: "active-power",
    label: "Active Power",
    unit: "MW",
    precision: 2,
    normalRange: [0, 6],
    thresholds: [
      {
        id: "active-power-rated",
        label: "Rated output",
        value: 6,
        direction: "above",
        severity: "warning",
      },
    ],
    valueAt: (index) => {
      const ramp = anomalyRamp(index);
      return (
        5.04 +
        cycle(index, 1, 0.56) +
        cycle(index, 5, 0.16) +
        ramp * 0.3024 +
        ramp * cycle(index, 12, 0.3)
      );
    },
    isAnomalyAt: (index) => index >= 56 && index % 3 !== 1,
    aiEvents: {
      72: "Maintenance Strategy Agent 评估降载运行影响",
    },
  },
  {
    metric: "reactive-power",
    label: "Reactive Power",
    unit: "Mvar",
    precision: 2,
    normalRange: [-1.2, 1.2],
    thresholds: [],
    valueAt: (index) => 0.42 + cycle(index, 3, 0.11) + cycle(index, 9, 0.03),
  },
  {
    metric: "generator-temperature",
    label: "Generator Temperature",
    unit: "°C",
    precision: 1,
    normalRange: [35, 82],
    thresholds: upperThresholds("generator-temperature", 85, 95),
    valueAt: (index) => 67.3 + cycle(index, 1, 3.4) + cycle(index, 4, 0.7),
  },
  {
    metric: "gearbox-oil-temperature",
    label: "Gearbox Oil Temperature",
    unit: "°C",
    precision: 1,
    normalRange: [35, 72],
    thresholds: upperThresholds("gearbox-oil-temperature", 75, 85),
    valueAt: (index) => 61.8 + cycle(index, 1, 2.8) + cycle(index, 5, 0.6),
  },
  {
    metric: "main-bearing-temperature",
    label: "Main Bearing Temperature",
    unit: "°C",
    precision: 1,
    normalRange: [30, 72],
    thresholds: upperThresholds("main-bearing-temperature", 75, 85),
    valueAt: (index) =>
      68 + cycle(index, 1, 1.25) + cycle(index, 5, 0.35) + 8.4 * anomalyRamp(index),
    isAnomalyAt: (index) => index >= 54,
    aiEvents: {
      60: "SCADA Analysis Agent 检出持续温升",
      70: "Failure Diagnosis Agent 将温升关联至主轴承退化",
    },
  },
  {
    metric: "main-bearing-vibration-rms",
    label: "Main Bearing Vibration RMS",
    unit: "mm/s",
    precision: 2,
    normalRange: [0, 4.5],
    thresholds: upperThresholds("main-bearing-vibration-rms", 4.5, 7.1),
    valueAt: (index) =>
      3.79 + cycle(index, 2, 0.11) + cycle(index, 9, 0.04) + 1.02 * anomalyRamp(index),
    isAnomalyAt: (index) => index >= 52,
    aiEvents: {
      60: "SCADA Analysis Agent 检出振动趋势异常",
      65: "Vibration Diagnosis Agent 启动包络谱分析",
    },
  },
  {
    metric: "nacelle-temperature",
    label: "Nacelle Temperature",
    unit: "°C",
    precision: 1,
    normalRange: [-10, 50],
    thresholds: upperThresholds("nacelle-temperature", 50, 58),
    valueAt: (index) => 36.4 + cycle(index, 1, 3.1) + cycle(index, 3, 0.5),
  },
  {
    metric: "tower-acceleration",
    label: "Tower Acceleration",
    unit: "m/s²",
    precision: 3,
    normalRange: [0, 0.35],
    thresholds: upperThresholds("tower-acceleration", 0.35, 0.5),
    valueAt: (index) => 0.12 + cycle(index, 2, 0.025) + cycle(index, 11, 0.009),
  },
  {
    metric: "blade-pitch",
    label: "Blade Pitch",
    unit: "°",
    precision: 1,
    normalRange: [-1, 25],
    thresholds: upperThresholds("blade-pitch", 27, 32),
    valueAt: (index) => 2.8 + cycle(index, 1, 1.1) + cycle(index, 6, 0.3),
  },
  {
    metric: "yaw-error",
    label: "Yaw Error",
    unit: "°",
    precision: 1,
    normalRange: [-8, 8],
    thresholds: upperThresholds("yaw-error", 8, 12),
    valueAt: (index) => 1.9 + cycle(index, 2, 2.2) + cycle(index, 7, 0.8),
  },
  {
    metric: "grid-voltage",
    label: "Grid Voltage",
    unit: "kV",
    precision: 2,
    normalRange: [33.2, 36.8],
    thresholds: upperThresholds("grid-voltage", 36.8, 37.5),
    valueAt: (index) => 35.1 + cycle(index, 3, 0.18) + cycle(index, 13, 0.05),
  },
  {
    metric: "grid-frequency",
    label: "Grid Frequency",
    unit: "Hz",
    precision: 2,
    normalRange: [49.8, 50.2],
    thresholds: upperThresholds("grid-frequency", 50.2, 50.5),
    valueAt: (index) => 50.01 + cycle(index, 6, 0.035) + cycle(index, 17, 0.009),
  },
  {
    metric: "anomaly-score",
    label: "AI Anomaly Score",
    unit: "score",
    precision: 2,
    normalRange: [0, 0.65],
    thresholds: upperThresholds("anomaly-score", 0.65, 0.9),
    valueAt: (index) => 0.18 + cycle(index, 3, 0.04) + 0.68 * anomalyRamp(index),
    isAnomalyAt: (index) => index >= 53,
    aiEvents: {
      60: "Anomaly model crossed the 0.65 warning threshold",
      68: "Predictive Maintenance Agent started RUL inference",
    },
  },
];

/** Seventeen linked 24-hour series at 15-minute resolution (97 points each). */
export const scadaSeries: readonly ScadaSeries[] = definitions.map(createSeries);

export const subsystemHealth: readonly SubsystemHealth[] = [
  {
    id: "HEALTH-WT-023-BLADES",
    turbineId: "WT-023",
    key: "blades",
    name: "叶片",
    healthScore: 88,
    state: "watch",
    trend: "stable",
    activeAlarmCount: 0,
    failureProbability30d: 7,
    remainingUsefulLifeDays: 680,
    anomalyScore: 0.21,
    primaryFinding: "前缘侵蚀处于可接受范围",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-HUB",
    turbineId: "WT-023",
    key: "hub",
    name: "轮毂",
    healthScore: 92,
    state: "healthy",
    trend: "stable",
    activeAlarmCount: 0,
    failureProbability30d: 3,
    remainingUsefulLifeDays: 940,
    anomalyScore: 0.12,
    primaryFinding: "轮毂载荷与温度正常",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-MAIN-SHAFT",
    turbineId: "WT-023",
    key: "main-shaft",
    name: "主轴",
    healthScore: 78,
    state: "watch",
    trend: "declining",
    activeAlarmCount: 1,
    failureProbability30d: 14,
    remainingUsefulLifeDays: 126,
    anomalyScore: 0.58,
    primaryFinding: "受主轴承振动耦合影响，建议联检",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-MAIN-BEARING",
    turbineId: "WT-023",
    key: "main-bearing",
    name: "主轴承",
    healthScore: 63,
    state: "degraded",
    trend: "declining",
    activeAlarmCount: 2,
    failureProbability30d: 34,
    remainingUsefulLifeDays: 47,
    anomalyScore: 0.86,
    primaryFinding: "振动 RMS 增长 27%，温度较基线升高 8.4°C",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-GEARBOX",
    turbineId: "WT-023",
    key: "gearbox",
    name: "齿轮箱",
    healthScore: 91,
    state: "healthy",
    trend: "stable",
    activeAlarmCount: 0,
    failureProbability30d: 4,
    remainingUsefulLifeDays: 812,
    anomalyScore: 0.19,
    primaryFinding: "油温与磨粒趋势正常",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-GENERATOR",
    turbineId: "WT-023",
    key: "generator",
    name: "发电机",
    healthScore: 95,
    state: "healthy",
    trend: "stable",
    activeAlarmCount: 0,
    failureProbability30d: 2,
    remainingUsefulLifeDays: 1040,
    anomalyScore: 0.14,
    primaryFinding: "绕组温度与功率因数正常",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-CONVERTER",
    turbineId: "WT-023",
    key: "converter",
    name: "变流器",
    healthScore: 94,
    state: "healthy",
    trend: "stable",
    activeAlarmCount: 0,
    failureProbability30d: 3,
    remainingUsefulLifeDays: 760,
    anomalyScore: 0.16,
    primaryFinding: "IGBT 温差与直流母线纹波正常",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-YAW",
    turbineId: "WT-023",
    key: "yaw",
    name: "偏航系统",
    healthScore: 89,
    state: "watch",
    trend: "stable",
    activeAlarmCount: 0,
    failureProbability30d: 6,
    remainingUsefulLifeDays: 410,
    anomalyScore: 0.24,
    primaryFinding: "偏航误差偶发接近关注阈值",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-PITCH",
    turbineId: "WT-023",
    key: "pitch",
    name: "变桨系统",
    healthScore: 93,
    state: "healthy",
    trend: "stable",
    activeAlarmCount: 0,
    failureProbability30d: 3,
    remainingUsefulLifeDays: 720,
    anomalyScore: 0.13,
    primaryFinding: "三支叶片角度一致性正常",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-TOWER",
    turbineId: "WT-023",
    key: "tower",
    name: "塔架",
    healthScore: 92,
    state: "healthy",
    trend: "stable",
    activeAlarmCount: 0,
    failureProbability30d: 2,
    remainingUsefulLifeDays: 1480,
    anomalyScore: 0.11,
    primaryFinding: "一阶振型与基础频率稳定",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-FOUNDATION",
    turbineId: "WT-023",
    key: "foundation",
    name: "基础",
    healthScore: 90,
    state: "healthy",
    trend: "stable",
    activeAlarmCount: 0,
    failureProbability30d: 2,
    remainingUsefulLifeDays: 1760,
    anomalyScore: 0.15,
    primaryFinding: "倾斜与冲刷监测无显著变化",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
  {
    id: "HEALTH-WT-023-ELECTRICAL",
    turbineId: "WT-023",
    key: "electrical",
    name: "电气系统",
    healthScore: 97,
    state: "healthy",
    trend: "stable",
    activeAlarmCount: 0,
    failureProbability30d: 1,
    remainingUsefulLifeDays: 1120,
    anomalyScore: 0.08,
    primaryFinding: "电压、频率及绝缘状态正常",
    assessedAt: "2026-08-13T10:25:00+08:00",
  },
] as const;

export const weatherWindows: readonly WeatherWindow[] = [
  {
    id: "WW-20260814-AM",
    farmId: "WF-EAST-CHINA-01",
    startsAt: "2026-08-14T08:00:00+08:00",
    endsAt: "2026-08-14T16:00:00+08:00",
    suitability: "suitable",
    windSpeedMps: 9.2,
    gustSpeedMps: 12.8,
    waveHeightM: 1.3,
    visibilityKm: 13.6,
    precipitationMm: 0.2,
    lightningRisk: "none",
    temperatureC: 27.4,
    reason: "风浪和能见度满足 CTV 靠泊、登塔及机舱检查限制。",
    recommendedFor: ["CTV transfer", "tower access", "nacelle inspection"],
  },
  {
    id: "WW-20260814-PM",
    farmId: "WF-EAST-CHINA-01",
    startsAt: "2026-08-14T16:00:00+08:00",
    endsAt: "2026-08-14T22:00:00+08:00",
    suitability: "conditional",
    windSpeedMps: 12.6,
    gustSpeedMps: 16.4,
    waveHeightM: 1.8,
    visibilityKm: 9.1,
    precipitationMm: 1.6,
    lightningRisk: "low",
    temperatureC: 26.1,
    reason: "接近人员转运限制，仅建议完成已开始的机舱内作业。",
    recommendedFor: ["nacelle inspection"],
  },
  {
    id: "WW-20260815-DAY",
    farmId: "WF-EAST-CHINA-01",
    startsAt: "2026-08-15T06:00:00+08:00",
    endsAt: "2026-08-15T20:00:00+08:00",
    suitability: "unsafe",
    windSpeedMps: 17.8,
    gustSpeedMps: 23.7,
    waveHeightM: 2.8,
    visibilityKm: 5.4,
    precipitationMm: 8.2,
    lightningRisk: "moderate",
    temperatureC: 25.2,
    reason: "浪高超过 2.5 m 且阵风超过人员转运限制。",
    recommendedFor: [],
  },
  {
    id: "WW-20260816-AM",
    farmId: "WF-EAST-CHINA-01",
    startsAt: "2026-08-16T07:00:00+08:00",
    endsAt: "2026-08-16T13:00:00+08:00",
    suitability: "conditional",
    windSpeedMps: 11.4,
    gustSpeedMps: 15.6,
    waveHeightM: 1.9,
    visibilityKm: 10.8,
    precipitationMm: 0.8,
    lightningRisk: "low",
    temperatureC: 26.7,
    reason: "短时可用，需在 13:00 前完成返航。",
    recommendedFor: ["CTV transfer", "visual inspection"],
  },
  {
    id: "WW-20260817-DAY",
    farmId: "WF-EAST-CHINA-01",
    startsAt: "2026-08-17T07:30:00+08:00",
    endsAt: "2026-08-17T17:30:00+08:00",
    suitability: "suitable",
    windSpeedMps: 8.6,
    gustSpeedMps: 11.9,
    waveHeightM: 1.1,
    visibilityKm: 16.2,
    precipitationMm: 0,
    lightningRisk: "none",
    temperatureC: 27.9,
    reason: "稳定高压控制，满足常规维护和小型吊装要求。",
    recommendedFor: ["CTV transfer", "tower access", "minor lifting"],
  },
] as const;

