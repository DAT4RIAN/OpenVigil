import { turbines, windFarm } from "./farm-data";
import { alarms, workOrders } from "./operations-data";
import type {
  Alarm,
  AlarmAIStatus,
  AlarmSeverity,
  DemoDatasetCounts,
  FailureCase,
  RiskLevel,
  ScadaMeasurement,
  ScadaMeasurementPage,
  ScadaMeasurementQuery,
  ScadaMetric,
  SubsystemKey,
  WorkOrder,
  WorkOrderPriority,
} from "./types";

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;
const SNAPSHOT_MS = Date.parse(windFarm.lastUpdatedAt);

const pad = (value: number, width = 3): string => value.toString().padStart(width, "0");

const round = (value: number, precision: number): number => {
  const factor = 10 ** precision;
  return Math.round(value * factor) / factor;
};

const iso = (timestamp: number): string => new Date(timestamp).toISOString();

/**
 * The archive treats the multivariate anomaly score as model output rather
 * than a physical SCADA measurement, leaving sixteen measured variables.
 */
export const SCADA_ARCHIVE_METRICS = [
  "wind-speed",
  "wind-direction",
  "rotor-speed",
  "generator-speed",
  "active-power",
  "reactive-power",
  "generator-temperature",
  "gearbox-oil-temperature",
  "main-bearing-temperature",
  "main-bearing-vibration-rms",
  "nacelle-temperature",
  "tower-acceleration",
  "blade-pitch",
  "yaw-error",
  "grid-voltage",
  "grid-frequency",
] as const satisfies readonly ScadaMetric[];

type ArchiveScadaMetric = (typeof SCADA_ARCHIVE_METRICS)[number];

interface MetricProfile {
  readonly label: string;
  readonly unit: string;
  readonly precision: number;
  readonly baseline: number;
  readonly amplitude: number;
  readonly cycles: number;
}

const metricProfiles: Readonly<Record<ArchiveScadaMetric, MetricProfile>> = {
  "wind-speed": {
    label: "Wind Speed",
    unit: "m/s",
    precision: 1,
    baseline: 9.7,
    amplitude: 1.35,
    cycles: 2,
  },
  "wind-direction": {
    label: "Wind Direction",
    unit: "°",
    precision: 0,
    baseline: 124,
    amplitude: 23,
    cycles: 1,
  },
  "rotor-speed": {
    label: "Rotor Speed",
    unit: "rpm",
    precision: 1,
    baseline: 11.6,
    amplitude: 1.1,
    cycles: 2,
  },
  "generator-speed": {
    label: "Generator Speed",
    unit: "rpm",
    precision: 1,
    baseline: 12.4,
    amplitude: 1.2,
    cycles: 2,
  },
  "active-power": {
    label: "Active Power",
    unit: "MW",
    precision: 2,
    baseline: 5.08,
    amplitude: 0.62,
    cycles: 2,
  },
  "reactive-power": {
    label: "Reactive Power",
    unit: "Mvar",
    precision: 2,
    baseline: 0.42,
    amplitude: 0.16,
    cycles: 5,
  },
  "generator-temperature": {
    label: "Generator Temperature",
    unit: "°C",
    precision: 1,
    baseline: 67.3,
    amplitude: 3.6,
    cycles: 1,
  },
  "gearbox-oil-temperature": {
    label: "Gearbox Oil Temperature",
    unit: "°C",
    precision: 1,
    baseline: 61.8,
    amplitude: 3,
    cycles: 1,
  },
  "main-bearing-temperature": {
    label: "Main Bearing Temperature",
    unit: "°C",
    precision: 1,
    baseline: 68,
    amplitude: 1.25,
    cycles: 1,
  },
  "main-bearing-vibration-rms": {
    label: "Main Bearing Vibration RMS",
    unit: "mm/s",
    precision: 2,
    baseline: 3.79,
    amplitude: 0.12,
    cycles: 3,
  },
  "nacelle-temperature": {
    label: "Nacelle Temperature",
    unit: "°C",
    precision: 1,
    baseline: 36.4,
    amplitude: 3.2,
    cycles: 1,
  },
  "tower-acceleration": {
    label: "Tower Acceleration",
    unit: "m/s²",
    precision: 3,
    baseline: 0.12,
    amplitude: 0.028,
    cycles: 4,
  },
  "blade-pitch": {
    label: "Blade Pitch",
    unit: "°",
    precision: 1,
    baseline: 2.8,
    amplitude: 1.2,
    cycles: 2,
  },
  "yaw-error": {
    label: "Yaw Error",
    unit: "°",
    precision: 1,
    baseline: 1.9,
    amplitude: 2.5,
    cycles: 4,
  },
  "grid-voltage": {
    label: "Grid Voltage",
    unit: "kV",
    precision: 2,
    baseline: 35.1,
    amplitude: 0.2,
    cycles: 6,
  },
  "grid-frequency": {
    label: "Grid Frequency",
    unit: "Hz",
    precision: 2,
    baseline: 50.01,
    amplitude: 0.04,
    cycles: 9,
  },
};

export const SCADA_ARCHIVE_SAMPLES_PER_SERIES = 128;
export const SCADA_ARCHIVE_INTERVAL_MINUTES = 15;
export const SCADA_ARCHIVE_MAX_PAGE_SIZE = 1_000;
export const SCADA_ARCHIVE_TOTAL =
  turbines.length * SCADA_ARCHIVE_METRICS.length * SCADA_ARCHIVE_SAMPLES_PER_SERIES;

const SCADA_ARCHIVE_START_MS =
  SNAPSHOT_MS - (SCADA_ARCHIVE_SAMPLES_PER_SERIES - 1) * SCADA_ARCHIVE_INTERVAL_MINUTES * MINUTE_MS;

const normalizedTurbineIndex = new Map(
  turbines.map((turbine, index) => [turbine.id.toUpperCase(), index]),
);

const normalizedMetricIndex = new Map(
  SCADA_ARCHIVE_METRICS.map((metric, index) => [metric, index]),
);

function archiveValue(turbineIndex: number, metricIndex: number, sampleIndex: number): number {
  const metric = SCADA_ARCHIVE_METRICS[metricIndex];
  const profile = metricProfiles[metric];
  const turbineNumber = turbineIndex + 1;
  const phase =
    (Math.PI * 2 * profile.cycles * sampleIndex) / (SCADA_ARCHIVE_SAMPLES_PER_SERIES - 1) +
    turbineNumber * 0.173 +
    metricIndex * 0.071;
  const secondaryPhase = sampleIndex * 0.41 + turbineNumber * 0.29;
  let value =
    profile.baseline +
    profile.amplitude * Math.sin(phase) +
    profile.amplitude * 0.17 * Math.cos(secondaryPhase) +
    profile.amplitude * 0.06 * Math.sin(turbineNumber * 0.61);

  const anomalyRamp = Math.max(0, (sampleIndex - 83) / (SCADA_ARCHIVE_SAMPLES_PER_SERIES - 1 - 83));

  if (
    turbineNumber === 23 &&
    (metric === "main-bearing-temperature" || metric === "main-bearing-vibration-rms")
  ) {
    const finalSampleIndex = SCADA_ARCHIVE_SAMPLES_PER_SERIES - 1;
    const finalPhase = Math.PI * 2 * profile.cycles + turbineNumber * 0.173 + metricIndex * 0.071;
    const finalSecondaryPhase = finalSampleIndex * 0.41 + turbineNumber * 0.29;
    const finalBaseline =
      profile.baseline +
      profile.amplitude * Math.sin(finalPhase) +
      profile.amplitude * 0.17 * Math.cos(finalSecondaryPhase) +
      profile.amplitude * 0.06 * Math.sin(turbineNumber * 0.61);
    const featuredCurrentValue = metric === "main-bearing-temperature" ? 76.4 : 4.81;
    value += (featuredCurrentValue - finalBaseline) * anomalyRamp;
  }
  if (turbineNumber === 41 && metric === "gearbox-oil-temperature") {
    value += 5.2 * anomalyRamp;
  }

  if (metric === "wind-direction") value = (value + 360) % 360;
  if (metric === "active-power") value = Math.max(0, Math.min(6, value));
  if (metric === "blade-pitch") value = Math.max(-1, value);

  return round(value, profile.precision);
}

function createScadaMeasurement(
  turbineIndex: number,
  metricIndex: number,
  sampleIndex: number,
): ScadaMeasurement {
  const turbine = turbines[turbineIndex];
  const metric = SCADA_ARCHIVE_METRICS[metricIndex];
  const profile = metricProfiles[metric];
  const sequence =
    (sampleIndex * turbines.length + turbineIndex) * SCADA_ARCHIVE_METRICS.length + metricIndex;
  const sparseQualityKey = sequence + 1 + turbineIndex * 31 + metricIndex * 17;
  const quality =
    sparseQualityKey % 997 === 0 ? "bad" : sparseQualityKey % 149 === 0 ? "uncertain" : "good";
  const isFeaturedBearingAnomaly =
    turbine.id === "WT-023" &&
    (metric === "main-bearing-temperature" || metric === "main-bearing-vibration-rms") &&
    sampleIndex >= 84;
  const isGearboxAnomaly =
    turbine.id === "WT-041" && metric === "gearbox-oil-temperature" && sampleIndex >= 108;

  return {
    id: `SCADA-ARCHIVE-${pad(sequence + 1, 6)}`,
    sequence,
    turbineId: turbine.id,
    metric,
    label: profile.label,
    timestamp: iso(
      SCADA_ARCHIVE_START_MS + sampleIndex * SCADA_ARCHIVE_INTERVAL_MINUTES * MINUTE_MS,
    ),
    value: archiveValue(turbineIndex, metricIndex, sampleIndex),
    unit: profile.unit,
    quality,
    isAnomaly: isFeaturedBearingAnomaly || isGearboxAnomaly || sparseQualityKey % 701 === 0,
  };
}

function pageInteger(value: number | undefined, fallback: number, maximum: number): number {
  if (value === undefined || !Number.isFinite(value)) return fallback;
  return Math.min(maximum, Math.max(0, Math.trunc(value)));
}

/**
 * Query the 131,072-row logical SCADA archive without allocating the archive.
 * Only the requested page is generated, so importing this module remains cheap
 * for both server and client consumers.
 */
export function queryScadaMeasurements(query: ScadaMeasurementQuery = {}): ScadaMeasurementPage {
  const requestedTurbine = (query.turbineId ?? query.turbine)?.trim().toUpperCase();
  const requestedMetric = query.metric?.trim().toLowerCase();
  const turbineIndex = requestedTurbine ? normalizedTurbineIndex.get(requestedTurbine) : undefined;
  const metricIndex = requestedMetric
    ? normalizedMetricIndex.get(requestedMetric as ArchiveScadaMetric)
    : undefined;
  const invalidTurbine = requestedTurbine !== undefined && turbineIndex === undefined;
  const invalidMetric = requestedMetric !== undefined && metricIndex === undefined;
  const selectedTurbineCount = requestedTurbine ? 1 : turbines.length;
  const selectedMetricCount = requestedMetric ? 1 : SCADA_ARCHIVE_METRICS.length;
  const total =
    invalidTurbine || invalidMetric
      ? 0
      : selectedTurbineCount * selectedMetricCount * SCADA_ARCHIVE_SAMPLES_PER_SERIES;
  const offset = Math.min(pageInteger(query.offset, 0, Number.MAX_SAFE_INTEGER), total);
  const limit = pageInteger(query.limit, 100, SCADA_ARCHIVE_MAX_PAGE_SIZE);
  const pageSize = Math.min(limit, total - offset);
  const combinationsPerSample = selectedTurbineCount * selectedMetricCount;

  const items = Object.freeze(
    Array.from({ length: pageSize }, (_, pageIndex) => {
      const relativeIndex = offset + pageIndex;
      const sampleIndex = Math.floor(relativeIndex / combinationsPerSample);
      const remainder = relativeIndex % combinationsPerSample;
      const selectedTurbineIndex = Math.floor(remainder / selectedMetricCount);
      const selectedMetricIndex = remainder % selectedMetricCount;
      return createScadaMeasurement(
        turbineIndex ?? selectedTurbineIndex,
        metricIndex ?? selectedMetricIndex,
        sampleIndex,
      );
    }),
  );

  return Object.freeze({
    items,
    total,
    offset,
    limit,
    snapshotAt: windFarm.lastUpdatedAt,
  });
}

interface AlarmArchiveTemplate {
  readonly code: string;
  readonly subsystem: SubsystemKey;
  readonly severity: AlarmSeverity;
  readonly title: string;
  readonly description: string;
  readonly threshold: number;
  readonly unit: string;
}

const alarmTemplates: readonly AlarmArchiveTemplate[] = [
  {
    code: "BRG-VIB-HI",
    subsystem: "main-bearing",
    severity: "major",
    title: "主轴承振动超过趋势阈值",
    description: "振动 RMS 在稳定工况下持续偏离滚动基线。",
    threshold: 4.5,
    unit: "mm/s",
  },
  {
    code: "GBX-OIL-TEMP",
    subsystem: "gearbox",
    severity: "warning",
    title: "齿轮箱油温偏高",
    description: "齿轮箱油温高于同风速和负载区间基线。",
    threshold: 75,
    unit: "°C",
  },
  {
    code: "GEN-TEMP-HI",
    subsystem: "generator",
    severity: "major",
    title: "发电机温度高",
    description: "定子或轴承温度达到高温告警边界。",
    threshold: 85,
    unit: "°C",
  },
  {
    code: "CNV-DC-RIPPLE",
    subsystem: "converter",
    severity: "minor",
    title: "直流母线纹波偏高",
    description: "变流器直流母线纹波超过动态基线。",
    threshold: 4.2,
    unit: "%",
  },
  {
    code: "PITCH-TRACK",
    subsystem: "pitch",
    severity: "warning",
    title: "变桨跟踪偏差",
    description: "叶片实际角度与控制指令之间存在持续偏差。",
    threshold: 2.5,
    unit: "°",
  },
  {
    code: "YAW-ERROR",
    subsystem: "yaw",
    severity: "minor",
    title: "偏航误差持续偏高",
    description: "机舱方向与来流方向偏差超过关注阈值。",
    threshold: 8,
    unit: "°",
  },
  {
    code: "TWR-ACC-HI",
    subsystem: "tower",
    severity: "major",
    title: "塔架加速度异常",
    description: "塔顶加速度在当前风况下超过结构监测基线。",
    threshold: 0.35,
    unit: "m/s²",
  },
  {
    code: "GRID-VOLT-DEV",
    subsystem: "electrical",
    severity: "info",
    title: "并网电压短时偏差",
    description: "并网点电压短时偏离正常运行区间。",
    threshold: 36.8,
    unit: "kV",
  },
];

const archiveAssignees = ["SCADA 值班组", "海维一组", "海维二组", "电气诊断组"] as const;

export const ALARM_ARCHIVE_TOTAL = 100;

function createArchivedAlarm(index: number): Alarm {
  const ordinal = alarms.length + index + 1;
  const template = alarmTemplates[index % alarmTemplates.length];
  const turbine = turbines[(ordinal * 17 + 3) % turbines.length];
  const triggeredAtMs = SNAPSHOT_MS - (ordinal * 19 + 7) * HOUR_MS;
  const durationMinutes = 34 + ((ordinal * 23) % 287);
  const acknowledgedAtMs = triggeredAtMs + (4 + (ordinal % 17)) * MINUTE_MS;
  const resolvedAtMs = triggeredAtMs + durationMinutes * MINUTE_MS;
  const aiStatus: AlarmAIStatus = ordinal % 5 === 0 ? "not-required" : "diagnosed";

  return {
    id: `ALARM-ARCH-${pad(ordinal, 4)}`,
    code: `${template.code}-${pad(ordinal, 3)}`,
    turbineId: turbine.id,
    subsystem: template.subsystem,
    severity: template.severity,
    title: template.title,
    description: template.description,
    triggeredAt: iso(triggeredAtMs),
    durationMinutes,
    status: "resolved",
    aiStatus,
    assignee: archiveAssignees[ordinal % archiveAssignees.length],
    acknowledgedAt: iso(acknowledgedAtMs),
    resolvedAt: iso(resolvedAtMs),
    currentValue: round(
      template.threshold * (1.035 + (ordinal % 9) * 0.011),
      template.unit === "m/s²" ? 3 : 2,
    ),
    threshold: template.threshold,
    unit: template.unit,
    missionId: null,
    evidenceIds: [],
  };
}

/** Existing live rows remain the first records consumed by current UI tables. */
export const alarmArchive: readonly Alarm[] = Object.freeze([
  ...alarms,
  ...Array.from({ length: Math.max(0, ALARM_ARCHIVE_TOTAL - alarms.length) }, (_, index) =>
    createArchivedAlarm(index),
  ),
]);

interface WorkOrderArchiveTemplate {
  readonly subsystem: SubsystemKey;
  readonly issue: string;
  readonly description: string;
  readonly priority: WorkOrderPriority;
  readonly riskLevel: RiskLevel;
  readonly durationHours: number;
  readonly tasks: readonly string[];
  readonly tools: readonly string[];
  readonly partName: string | null;
}

const workOrderTemplates: readonly WorkOrderArchiveTemplate[] = [
  {
    subsystem: "main-bearing",
    issue: "主轴承润滑与振动复核",
    description: "复核润滑状态、温度趋势和三向振动频谱。",
    priority: "high",
    riskLevel: "high",
    durationHours: 6,
    tasks: ["执行 LOTO", "采集润滑脂样本", "采集三向振动", "复核温度并归档"],
    tools: ["便携式振动分析仪", "红外测温仪", "润滑脂取样套件"],
    partName: "主轴承专用润滑脂",
  },
  {
    subsystem: "gearbox",
    issue: "齿轮箱油样与内窥镜检查",
    description: "针对磨粒趋势执行油样检测及齿面内窥镜检查。",
    priority: "high",
    riskLevel: "high",
    durationHours: 7.5,
    tasks: ["采集齿轮油样", "检查磁性堵塞指示器", "内窥镜检查", "上传影像"],
    tools: ["工业内窥镜", "油样套件", "颗粒度检测仪"],
    partName: "齿轮箱滤芯",
  },
  {
    subsystem: "converter",
    issue: "变流器冷却回路维护",
    description: "检查冷却泵、阀位、过滤器和 IGBT 温差。",
    priority: "medium",
    riskLevel: "medium",
    durationHours: 4,
    tasks: ["隔离冷却回路", "检查泵与阀位", "更换滤芯", "试运行并复测"],
    tools: ["万用表", "压差计", "绝缘工具套装"],
    partName: "冷却回路滤芯",
  },
  {
    subsystem: "pitch",
    issue: "变桨编码器校准",
    description: "校准叶片角度编码器并测试液压驱动响应。",
    priority: "medium",
    riskLevel: "medium",
    durationHours: 3.5,
    tasks: ["锁定轮毂", "检查编码器", "执行零位校准", "完成动态测试"],
    tools: ["角度校准仪", "液压压力表"],
    partName: "变桨角度编码器",
  },
  {
    subsystem: "yaw",
    issue: "偏航制动器间隙检查",
    description: "检查制动器间隙、摩擦片磨损与偏航驱动状态。",
    priority: "low",
    riskLevel: "low",
    durationHours: 3,
    tasks: ["检查制动间隙", "测量摩擦片厚度", "复核驱动扭矩", "功能测试"],
    tools: ["塞尺", "扭矩扳手"],
    partName: "偏航制动摩擦片",
  },
  {
    subsystem: "tower",
    issue: "塔筒法兰螺栓复检",
    description: "复核塔筒法兰外观、预紧力和结构振动记录。",
    priority: "high",
    riskLevel: "high",
    durationHours: 8,
    tasks: ["检查法兰外观", "超声抽检预紧力", "标记偏差", "工程复核"],
    tools: ["超声螺栓检测仪", "液压扭矩扳手"],
    partName: "高强度法兰螺栓",
  },
  {
    subsystem: "blades",
    issue: "叶片前缘与防雷系统巡检",
    description: "通过无人机和登塔检查叶片前缘、防雷接闪器与引下线。",
    priority: "medium",
    riskLevel: "medium",
    durationHours: 5,
    tasks: ["无人机影像采集", "检查接闪器", "测试引下线", "归档缺陷"],
    tools: ["巡检无人机", "低阻测试仪"],
    partName: "叶片前缘保护膜",
  },
  {
    subsystem: "electrical",
    issue: "箱变绝缘油与电气连接检查",
    description: "采集绝缘油样并检查母排、电缆端子及接地连接。",
    priority: "medium",
    riskLevel: "medium",
    durationHours: 5.5,
    tasks: ["执行电气隔离", "采集绝缘油样", "热成像检查", "复测接地电阻"],
    tools: ["绝缘油取样套件", "红外热像仪", "接地电阻测试仪"],
    partName: "箱变密封组件",
  },
];

const maintenanceTeams = [
  "海维一组 · 4 人",
  "海维二组 · 4 人",
  "电气专业组 · 3 人",
  "叶轮机械组 · 5 人",
] as const;

export const HISTORICAL_WORK_ORDER_TOTAL = 30;

function createHistoricalWorkOrder(index: number): WorkOrder {
  const ordinal = index + 1;
  const template = workOrderTemplates[index % workOrderTemplates.length];
  const turbine = turbines[(index * 11 + 6) % turbines.length];
  const id = `WO-HIST-2026-${pad(ordinal)}`;
  const plannedStartMs = SNAPSHOT_MS - (ordinal * 4 + 9) * DAY_MS + (ordinal % 6) * HOUR_MS;
  const deadlineMs = plannedStartMs + template.durationHours * HOUR_MS;

  return {
    id,
    turbineId: turbine.id,
    issue: `${turbine.id} ${template.issue}`,
    description: template.description,
    priority: template.priority,
    status: ordinal % 3 === 0 ? "closed" : "completed",
    assignedTeam: maintenanceTeams[index % maintenanceTeams.length],
    createdByAgentId: ordinal % 2 === 0 ? "agent-work-order" : null,
    relatedMissionId: null,
    decisionId: null,
    plannedStart: iso(plannedStartMs),
    deadline: iso(deadlineMs),
    estimatedDurationHours: template.durationHours,
    riskLevel: template.riskLevel,
    tasks: template.tasks.map((title, taskIndex) => ({
      id: `${id}-TASK-${pad(taskIndex + 1, 2)}`,
      sequence: taskIndex + 1,
      title,
      completed: true,
      completionNote: "已按作业指导书完成并归档",
    })),
    ppeRequirements: ["全身式安全带", "海上救生衣", "防滑安全鞋", "护目镜"],
    requiredTools: template.tools,
    spareParts: template.partName
      ? [
          {
            partNumber: `HIST-${template.subsystem.toUpperCase()}-${pad(ordinal)}`,
            name: template.partName,
            quantity: 1,
            available: 2 + (ordinal % 5),
            reserved: 0,
          },
        ]
      : [],
    safetyProcedures: [
      "作业前完成风险分析和班前会",
      "执行停机、机械锁定与电气 LOTO",
      "确认气象和船舶返航窗口",
    ],
    createdAt: iso(plannedStartMs - 36 * HOUR_MS),
    updatedAt: iso(deadlineMs + 2 * HOUR_MS),
  };
}

export const historicalWorkOrders: readonly WorkOrder[] = Object.freeze(
  Array.from({ length: HISTORICAL_WORK_ORDER_TOTAL }, (_, index) =>
    createHistoricalWorkOrder(index),
  ),
);

interface FailureCaseTemplate {
  readonly subsystem: SubsystemKey;
  readonly title: string;
  readonly failureMode: string;
  readonly symptoms: readonly string[];
  readonly rootCause: string;
  readonly correctiveAction: string;
  readonly severity: RiskLevel;
  readonly downtimeHours: number;
  readonly repairCostCny: number;
}

const failureCaseTemplates: readonly FailureCaseTemplate[] = [
  {
    subsystem: "main-bearing",
    title: "主轴承外圈早期剥落",
    failureMode: "Bearing outer-race spalling",
    symptoms: ["振动 RMS 上升", "BPFO 边带增强", "轴承温度偏离基线"],
    rootCause: "驱动端润滑脂劣化导致滚道局部疲劳损伤。",
    correctiveAction: "更换润滑脂并修复受损轴承，建立高频振动复测任务。",
    severity: "high",
    downtimeHours: 28,
    repairCostCny: 438_000,
  },
  {
    subsystem: "gearbox",
    title: "齿轮箱高速级点蚀",
    failureMode: "High-speed gear pitting",
    symptoms: ["磨粒计数跃升", "啮合频率边带", "油温升高"],
    rootCause: "齿面润滑膜不足与局部载荷集中共同造成点蚀。",
    correctiveAction: "更换受损齿轮副、滤芯和润滑油，复核轴系对中。",
    severity: "critical",
    downtimeHours: 46,
    repairCostCny: 765_000,
  },
  {
    subsystem: "converter",
    title: "变流器冷却流量损失",
    failureMode: "Converter cooling-flow restriction",
    symptoms: ["冷却压差升高", "IGBT 温差扩大", "泵频率持续上升"],
    rootCause: "冷却回路滤芯堵塞并伴随入口阀开度漂移。",
    correctiveAction: "更换滤芯、校准阀位并完成满载热稳定性测试。",
    severity: "high",
    downtimeHours: 7,
    repairCostCny: 82_000,
  },
  {
    subsystem: "pitch",
    title: "叶片变桨跟踪漂移",
    failureMode: "Pitch encoder zero drift",
    symptoms: ["指令与反馈偏差", "三叶片角度不一致", "液压压力波动"],
    rootCause: "角度编码器零位漂移并叠加接插件接触电阻增加。",
    correctiveAction: "更换编码器接插件、重新标定零位并完成联动测试。",
    severity: "medium",
    downtimeHours: 5,
    repairCostCny: 56_000,
  },
  {
    subsystem: "generator",
    title: "发电机驱动端轴承过热",
    failureMode: "Generator bearing overheating",
    symptoms: ["轴承温度高", "高频振动增强", "润滑周期缩短"],
    rootCause: "自动润滑管路局部堵塞造成供脂不足。",
    correctiveAction: "疏通管路、更换分配器并补充规定型号润滑脂。",
    severity: "high",
    downtimeHours: 12,
    repairCostCny: 126_000,
  },
  {
    subsystem: "yaw",
    title: "偏航制动器滑移",
    failureMode: "Yaw brake torque loss",
    symptoms: ["偏航误差增加", "制动次数上升", "摩擦片温度不均"],
    rootCause: "摩擦片不均匀磨损导致有效制动力矩下降。",
    correctiveAction: "成组更换摩擦片、调整间隙并复测制动力矩。",
    severity: "medium",
    downtimeHours: 8,
    repairCostCny: 94_000,
  },
  {
    subsystem: "blades",
    title: "叶片前缘侵蚀扩展",
    failureMode: "Blade leading-edge erosion",
    symptoms: ["功率曲线偏移", "无人机影像缺陷", "叶片噪声增加"],
    rootCause: "长期雨蚀造成保护层脱落并向基材扩展。",
    correctiveAction: "修复基材、重涂前缘保护层并建立季度影像复核。",
    severity: "medium",
    downtimeHours: 16,
    repairCostCny: 183_000,
  },
  {
    subsystem: "tower",
    title: "塔筒法兰预紧力下降",
    failureMode: "Tower-flange bolt preload loss",
    symptoms: ["结构模态漂移", "法兰微动痕迹", "螺栓超声偏差"],
    rootCause: "多次交变载荷后部分螺栓预紧力衰减。",
    correctiveAction: "按交叉顺序复紧、替换超差螺栓并复测结构模态。",
    severity: "high",
    downtimeHours: 14,
    repairCostCny: 215_000,
  },
  {
    subsystem: "foundation",
    title: "单桩基础局部冲刷",
    failureMode: "Monopile scour development",
    symptoms: ["冲刷深度增加", "基础频率轻微下降", "海床声呐变化"],
    rootCause: "季节性强流导致原有防冲刷层局部迁移。",
    correctiveAction: "补充级配块石并更新声呐基线与结构模型。",
    severity: "high",
    downtimeHours: 20,
    repairCostCny: 510_000,
  },
  {
    subsystem: "electrical",
    title: "箱变绝缘油含水量超限",
    failureMode: "Transformer oil moisture ingress",
    symptoms: ["介损增加", "油中含水量超限", "密封处凝露"],
    rootCause: "呼吸器与检修口密封老化造成潮气进入。",
    correctiveAction: "更换密封、真空滤油并完成绝缘与油色谱复测。",
    severity: "critical",
    downtimeHours: 18,
    repairCostCny: 328_000,
  },
];

export const FAILURE_CASE_TOTAL = 20;

function createFailureCase(index: number): FailureCase {
  const ordinal = index + 1;
  const template = failureCaseTemplates[index % failureCaseTemplates.length];
  const workOrder = historicalWorkOrders[index % historicalWorkOrders.length];
  const detectedAtMs = Date.parse(workOrder.plannedStart) - 14 * HOUR_MS;

  return {
    id: `FAILURE-CASE-2026-${pad(ordinal)}`,
    turbineId: workOrder.turbineId,
    subsystem: template.subsystem,
    title: template.title,
    failureMode: template.failureMode,
    symptoms: template.symptoms,
    rootCause: template.rootCause,
    correctiveAction: template.correctiveAction,
    severity: template.severity,
    detectedAt: iso(detectedAtMs),
    resolvedAt: workOrder.updatedAt,
    downtimeHours: template.downtimeHours + (ordinal % 3) * 0.5,
    energyLossMWh: round(template.downtimeHours * (4.2 + (ordinal % 5) * 0.18), 1),
    repairCostCny: template.repairCostCny + (ordinal % 4) * 7_500,
    relatedWorkOrderId: workOrder.id,
    tags: [template.subsystem, template.failureMode, "closed-loop"],
  };
}

export const failureCases: readonly FailureCase[] = Object.freeze(
  Array.from({ length: FAILURE_CASE_TOTAL }, (_, index) => createFailureCase(index)),
);

export const demoDatasetCounts: DemoDatasetCounts = Object.freeze({
  turbines: turbines.length,
  scadaMeasurements: SCADA_ARCHIVE_TOTAL,
  alarms: alarmArchive.length,
  liveAlarms: alarms.length,
  workOrders: workOrders.length + historicalWorkOrders.length,
  liveWorkOrders: workOrders.length,
  historicalWorkOrders: historicalWorkOrders.length,
  failureCases: failureCases.length,
});

export function validateArchiveData(): readonly string[] {
  const errors: string[] = [];
  const turbineIds = new Set(turbines.map((turbine) => turbine.id));
  const workOrderIds = new Set(historicalWorkOrders.map((workOrder) => workOrder.id));

  if (SCADA_ARCHIVE_TOTAL < 100_000)
    errors.push("SCADA archive must contain at least 100,000 measurements");
  if (alarmArchive.length < 100) errors.push("alarm archive must contain at least 100 alarms");
  if (historicalWorkOrders.length < 30)
    errors.push("historical work orders must contain at least 30 records");
  if (failureCases.length < 20) errors.push("failure cases must contain at least 20 records");

  for (const alarm of alarmArchive) {
    if (!turbineIds.has(alarm.turbineId))
      errors.push(`${alarm.id}: unknown turbine ${alarm.turbineId}`);
  }
  for (const workOrder of historicalWorkOrders) {
    if (!turbineIds.has(workOrder.turbineId))
      errors.push(`${workOrder.id}: unknown turbine ${workOrder.turbineId}`);
  }
  for (const failureCase of failureCases) {
    if (!turbineIds.has(failureCase.turbineId))
      errors.push(`${failureCase.id}: unknown turbine ${failureCase.turbineId}`);
    if (!workOrderIds.has(failureCase.relatedWorkOrderId))
      errors.push(`${failureCase.id}: unknown work order ${failureCase.relatedWorkOrderId}`);
  }
  return errors;
}
