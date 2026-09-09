import { canonicalDemoWorkflow } from "./demo-workflow";
import { turbines } from "./farm-data";
import { workOrders } from "./operations-data";
import { maintenanceCrews, maintenanceTools, serviceVessels, spareParts } from "./resource-data";
import { weatherWindows } from "./telemetry-data";
import type {
  MaintenanceCrew,
  MaintenanceTool,
  RiskLevel,
  ServiceVessel,
  WeatherSuitability,
  WeatherWindow,
  WorkOrder,
  WorkOrderPart,
  WorkOrderStatus,
} from "./types";

export const maintenancePlanStatuses = [
  "approval-gated",
  "ready",
  "at-risk",
  "in-progress",
  "paused",
  "completed",
] as const;
export type MaintenancePlanStatus = (typeof maintenancePlanStatuses)[number];

export const maintenancePlanWindowStates = [
  "suitable",
  "conditional",
  "unsafe",
  "unmatched",
  "not-required",
] as const;
export type MaintenancePlanWindowState = (typeof maintenancePlanWindowStates)[number];

export const maintenancePlanRiskLevels = ["critical", "high", "medium", "low"] as const;
export const maintenancePlanSortModes = [
  "start-asc",
  "risk-desc",
  "readiness-desc",
  "deadline-asc",
] as const;
export type MaintenancePlanSortMode = (typeof maintenancePlanSortModes)[number];

export type MaintenanceResourceState =
  "confirmed" | "reserved" | "available" | "conflict" | "untracked";

export interface MaintenanceResourceRef {
  readonly id: string;
  readonly label: string;
  readonly state: MaintenanceResourceState;
  readonly detail: string;
}

export interface MaintenanceWeatherMatch {
  readonly id: string | null;
  readonly state: MaintenancePlanWindowState;
  readonly coverage: "full" | "partial" | "none" | "not-required";
  readonly startsAt: string | null;
  readonly endsAt: string | null;
  readonly windSpeedMps: number | null;
  readonly waveHeightM: number | null;
  readonly visibilityKm: number | null;
  readonly reason: string;
}

export interface MaintenancePlanConflict {
  readonly code:
    | "APPROVAL_GATE"
    | "HIGH_OPERATIONAL_RISK"
    | "WEATHER_CONDITIONAL"
    | "WEATHER_UNSAFE"
    | "WEATHER_UNMATCHED"
    | "CREW_CONFLICT"
    | "CREW_UNTRACKED"
    | "VESSEL_CONFLICT"
    | "TOOL_CONFLICT"
    | "TOOL_UNTRACKED"
    | "PART_SHORTAGE"
    | "PART_UNTRACKED"
    | "RESOURCE_OVERLAP";
  readonly severity: "critical" | "warning" | "info";
  readonly message: string;
}

export interface MaintenancePlan {
  readonly id: string;
  readonly workOrderId: string;
  readonly turbineId: string;
  readonly turbineHealthScore: number;
  readonly issue: string;
  readonly description: string;
  readonly assignedTeam: string;
  readonly teamKey: string;
  readonly priority: WorkOrder["priority"];
  readonly risk: RiskLevel;
  readonly workOrderStatus: WorkOrderStatus;
  readonly status: MaintenancePlanStatus;
  readonly startsAt: string;
  readonly endsAt: string;
  readonly deadline: string;
  readonly dayKey: string;
  readonly durationHours: number;
  readonly taskProgressPercent: number;
  readonly weather: MaintenanceWeatherMatch;
  readonly crew: MaintenanceResourceRef;
  readonly vessels: readonly MaintenanceResourceRef[];
  readonly spareParts: readonly MaintenanceResourceRef[];
  readonly tools: readonly MaintenanceResourceRef[];
  readonly readinessPercent: number;
  readonly conflicts: readonly MaintenancePlanConflict[];
  readonly relatedMissionId: string | null;
  readonly readOnly: true;
  readonly source: "deterministic-demo-fixtures";
}

export interface CreateMaintenancePlansOptions {
  readonly featuredWorkOrderStatus?: WorkOrderStatus;
  readonly featuredCompletedTaskIds?: readonly string[];
}

const FEATURED_WORK_ORDER_ID = "WO-20260823-017";
const SNAPSHOT_AT = "2026-08-13T10:30:00+08:00";

export const maintenancePlanMeta = Object.freeze({
  mode: "derived-demo-schedule" as const,
  deterministic: true as const,
  readOnly: true as const,
  snapshotAt: SNAPSHOT_AT,
  notice: "计划由演示工单、资源台账与天气窗口确定性派生；页面不执行真实调度。",
  provenance: ["workOrders", "weatherWindows", "resources", "turbines"] as const,
});

const normalize = (value: string): string =>
  value
    .toLowerCase()
    .replace(/[·\s()（）\-_/]/g, "")
    .replace(/\d+(?:\.\d+)?(?:mw|kg|m)?/g, "");

const commonPrefixLength = (left: string, right: string): number => {
  let index = 0;
  while (index < left.length && index < right.length && left[index] === right[index]) index += 1;
  return index;
};

const fuzzyMatch = (left: string, right: string): boolean => {
  const normalizedLeft = normalize(left);
  const normalizedRight = normalize(right);
  if (!normalizedLeft || !normalizedRight) return false;
  return (
    normalizedLeft.includes(normalizedRight) ||
    normalizedRight.includes(normalizedLeft) ||
    commonPrefixLength(normalizedLeft, normalizedRight) >= 4 ||
    (normalizedLeft.includes("红外") && normalizedRight.includes("红外")) ||
    (normalizedLeft.includes("内窥镜") && normalizedRight.includes("内窥镜")) ||
    (normalizedLeft.includes("振动") && normalizedRight.includes("振动"))
  );
};

const overlaps = (leftStart: string, leftEnd: string, rightStart: string, rightEnd: string) =>
  Date.parse(leftStart) < Date.parse(rightEnd) && Date.parse(rightStart) < Date.parse(leftEnd);

const isClosed = (status: WorkOrderStatus): boolean =>
  status === "completed" || status === "closed";

const isRemote = (workOrder: WorkOrder): boolean =>
  workOrder.assignedTeam.includes("远程") ||
  workOrder.requiredTools.some((tool) => tool.toUpperCase().includes("SCADA"));

const estimatedEnd = (workOrder: WorkOrder): string =>
  new Date(
    Date.parse(workOrder.plannedStart) + workOrder.estimatedDurationHours * 3_600_000,
  ).toISOString();

const suitabilityRank: Readonly<Record<WeatherSuitability, number>> = {
  suitable: 3,
  conditional: 2,
  unsafe: 1,
};

function matchWeather(workOrder: WorkOrder, endsAt: string): MaintenanceWeatherMatch {
  if (isRemote(workOrder)) {
    return {
      id: null,
      state: "not-required",
      coverage: "not-required",
      startsAt: null,
      endsAt: null,
      windSpeedMps: null,
      waveHeightM: null,
      visibilityKm: null,
      reason: "远程诊断任务不需要海上人员转运窗口。",
    };
  }

  const candidates = weatherWindows
    .filter((window) => overlaps(workOrder.plannedStart, endsAt, window.startsAt, window.endsAt))
    .sort(
      (left, right) =>
        suitabilityRank[right.suitability] - suitabilityRank[left.suitability] ||
        left.startsAt.localeCompare(right.startsAt),
    );
  const match = candidates[0];
  if (!match) {
    return {
      id: null,
      state: "unmatched",
      coverage: "none",
      startsAt: null,
      endsAt: null,
      windSpeedMps: null,
      waveHeightM: null,
      visibilityKm: null,
      reason: isClosed(workOrder.status)
        ? "历史执行窗口未保留在当前天气快照中。"
        : "当前天气快照中没有覆盖该计划时段的作业窗口。",
    };
  }

  const fullCoverage =
    Date.parse(match.startsAt) <= Date.parse(workOrder.plannedStart) &&
    Date.parse(match.endsAt) >= Date.parse(endsAt);
  return {
    id: match.id,
    state: match.suitability,
    coverage: fullCoverage ? "full" : "partial",
    startsAt: match.startsAt,
    endsAt: match.endsAt,
    windSpeedMps: match.windSpeedMps,
    waveHeightM: match.waveHeightM,
    visibilityKm: match.visibilityKm,
    reason: fullCoverage ? match.reason : `仅部分覆盖计划时段；${match.reason}`,
  };
}

function crewCandidate(workOrder: WorkOrder): MaintenanceCrew | undefined {
  const direct = maintenanceCrews.find(
    (crew) =>
      crew.assignedWorkOrderId === workOrder.id || fuzzyMatch(crew.name, workOrder.assignedTeam),
  );
  if (direct) return direct;
  return maintenanceCrews.find((crew) =>
    crew.specialties.some(
      (specialty) =>
        fuzzyMatch(specialty, workOrder.assignedTeam) ||
        fuzzyMatch(specialty, workOrder.issue) ||
        fuzzyMatch(specialty, workOrder.description),
    ),
  );
}

function crewResource(workOrder: WorkOrder): MaintenanceResourceRef {
  if (isRemote(workOrder)) {
    return {
      id: `TEAM-${normalize(workOrder.assignedTeam).toUpperCase()}`,
      label: workOrder.assignedTeam,
      state: "untracked",
      detail: "远程支持班组来自工单执行记录，不占用海上班组资源。",
    };
  }
  const crew = crewCandidate(workOrder);
  if (!crew) {
    return {
      id: `TEAM-${normalize(workOrder.assignedTeam).toUpperCase()}`,
      label: workOrder.assignedTeam,
      state: "untracked",
      detail: "工单已指定班组，但当前资源台账没有对应实体。",
    };
  }
  const assignedElsewhere =
    crew.assignedWorkOrderId !== null && crew.assignedWorkOrderId !== workOrder.id;
  return {
    id: crew.id,
    label: crew.name,
    state: assignedElsewhere
      ? "conflict"
      : crew.assignedWorkOrderId === workOrder.id || crew.availability === "reserved"
        ? "reserved"
        : crew.availability === "available"
          ? "available"
          : "confirmed",
    detail: assignedElsewhere
      ? `当前关联 ${crew.assignedWorkOrderId}`
      : `${crew.memberCount} 人 · ${crew.currentLocation} · ${crew.specialties.join(" / ")}`,
  };
}

function vesselResources(workOrder: WorkOrder): readonly MaintenanceResourceRef[] {
  if (isRemote(workOrder) || isClosed(workOrder.status)) return [];
  const vessel =
    serviceVessels.find((item) => item.assignedWorkOrderId === workOrder.id) ??
    serviceVessels.find((item) => item.availability === "available");
  if (!vessel) {
    return [
      {
        id: "VESSEL-UNASSIGNED",
        label: "未分配船舶",
        state: "conflict",
        detail: "海上作业需要人员转运船舶。",
      },
    ];
  }
  const assignedElsewhere =
    vessel.assignedWorkOrderId !== null && vessel.assignedWorkOrderId !== workOrder.id;
  return [
    {
      id: vessel.id,
      label: vessel.name,
      state: assignedElsewhere
        ? "conflict"
        : vessel.assignedWorkOrderId === workOrder.id || vessel.availability === "reserved"
          ? "reserved"
          : "available",
      detail: assignedElsewhere
        ? `当前关联 ${vessel.assignedWorkOrderId}`
        : `${vessel.vesselType} · 最大浪高 ${vessel.maxWaveHeightM} m · ${vessel.berth}`,
    },
  ];
}

function toolResource(workOrder: WorkOrder, required: string): MaintenanceResourceRef {
  const directlyReserved = maintenanceTools.find(
    (tool) => tool.assignedWorkOrderId === workOrder.id && fuzzyMatch(tool.name, required),
  );
  const tool = directlyReserved ?? maintenanceTools.find((item) => fuzzyMatch(item.name, required));
  if (!tool) {
    return {
      id: `TOOL-${normalize(required).toUpperCase()}`,
      label: required,
      state: "untracked",
      detail: "工单工具清单已记录；资源中心无可核对实体。",
    };
  }
  const assignedElsewhere =
    tool.assignedWorkOrderId !== null && tool.assignedWorkOrderId !== workOrder.id;
  return {
    id: tool.id,
    label: tool.name,
    state: assignedElsewhere
      ? "conflict"
      : tool.assignedWorkOrderId === workOrder.id || tool.availability === "reserved"
        ? "reserved"
        : tool.availability === "available"
          ? "available"
          : "confirmed",
    detail: assignedElsewhere
      ? `当前关联 ${tool.assignedWorkOrderId}`
      : `校准有效至 ${tool.calibrationDueAt.slice(0, 10)} · ${tool.location}`,
  };
}

function partResource(workOrder: WorkOrder, required: WorkOrderPart): MaintenanceResourceRef {
  const part = spareParts.find((item) => item.partNumber === required.partNumber);
  if (!part) {
    const enough = required.available >= required.quantity;
    return {
      id: `PART-${required.partNumber}`,
      label: `${required.name} × ${required.quantity}`,
      state: enough ? "confirmed" : "conflict",
      detail: enough
        ? `工单快照确认可用 ${required.available}`
        : `工单快照仅可用 ${required.available}，需求 ${required.quantity}`,
    };
  }
  const enough =
    part.available >= required.quantity || part.reservedForWorkOrderIds.includes(workOrder.id);
  return {
    id: part.id,
    label: `${part.name} × ${required.quantity} ${part.unit}`,
    state: enough
      ? part.reservedForWorkOrderIds.includes(workOrder.id)
        ? "reserved"
        : "available"
      : "conflict",
    detail: enough
      ? `可用 ${part.available} ${part.unit} · ${part.warehouse}`
      : `仅可用 ${part.available} ${part.unit}，需求 ${required.quantity}`,
  };
}

function baseConflicts(
  workOrder: WorkOrder,
  weather: MaintenanceWeatherMatch,
  crew: MaintenanceResourceRef,
  vessels: readonly MaintenanceResourceRef[],
  tools: readonly MaintenanceResourceRef[],
  parts: readonly MaintenanceResourceRef[],
): MaintenancePlanConflict[] {
  const conflicts: MaintenancePlanConflict[] = [];
  if (workOrder.status === "draft" || workOrder.status === "pending-approval") {
    conflicts.push({
      code: "APPROVAL_GATE",
      severity: "info",
      message: "人工审批门禁未解除，计划不能进入现场执行。",
    });
  }
  if (workOrder.riskLevel === "critical" || workOrder.riskLevel === "high") {
    conflicts.push({
      code: "HIGH_OPERATIONAL_RISK",
      severity: "warning",
      message: `${workOrder.riskLevel === "critical" ? "严重" : "高"}风险作业需执行作业前安全复核。`,
    });
  }
  if (!isClosed(workOrder.status) && workOrder.status !== "paused") {
    if (weather.state === "conditional") {
      conflicts.push({
        code: "WEATHER_CONDITIONAL",
        severity: "warning",
        message:
          weather.coverage === "partial"
            ? "天气窗口仅部分覆盖计划时段。"
            : "天气条件临界，需滚动复核。",
      });
    } else if (weather.state === "unsafe") {
      conflicts.push({
        code: "WEATHER_UNSAFE",
        severity: "critical",
        message: "天气窗口不满足海上作业限制。",
      });
    } else if (weather.state === "unmatched") {
      conflicts.push({
        code: "WEATHER_UNMATCHED",
        severity: "critical",
        message: "计划尚未匹配可用天气窗口。",
      });
    }
  }
  if (crew.state === "conflict") {
    conflicts.push({
      code: "CREW_CONFLICT",
      severity: "critical",
      message: `${crew.label} 与其他工单存在占用冲突。`,
    });
  } else if (crew.state === "untracked") {
    conflicts.push({
      code: "CREW_UNTRACKED",
      severity: "warning",
      message: `${crew.label} 尚未纳入资源中心可用性台账。`,
    });
  }
  if (vessels.some((item) => item.state === "conflict")) {
    conflicts.push({
      code: "VESSEL_CONFLICT",
      severity: "critical",
      message: "作业船舶未分配或已被其他计划占用。",
    });
  }
  if (tools.some((item) => item.state === "conflict")) {
    conflicts.push({
      code: "TOOL_CONFLICT",
      severity: "critical",
      message: "至少一项专业工具已被其他工单占用。",
    });
  }
  if (tools.some((item) => item.state === "untracked")) {
    conflicts.push({
      code: "TOOL_UNTRACKED",
      severity: "info",
      message: "部分工单工具仅有清单记录，未纳入资源台账。",
    });
  }
  if (parts.some((item) => item.state === "conflict")) {
    conflicts.push({
      code: "PART_SHORTAGE",
      severity: "critical",
      message: "至少一项备件库存不足。",
    });
  }
  if (parts.some((item) => item.state === "untracked")) {
    conflicts.push({
      code: "PART_UNTRACKED",
      severity: "info",
      message: "部分备件仅有工单快照，未纳入当前库存台账。",
    });
  }
  return conflicts;
}

function readinessFor(
  resources: readonly MaintenanceResourceRef[],
  weather: MaintenanceWeatherMatch,
): number {
  const weatherScore =
    weather.state === "not-required" || weather.state === "suitable"
      ? 1
      : weather.state === "conditional"
        ? weather.coverage === "full"
          ? 0.72
          : 0.55
        : 0;
  const scores = resources.map((resource) =>
    resource.state === "conflict" ? 0 : resource.state === "untracked" ? 0.65 : 1,
  );
  return Math.round(
    ((scores.reduce<number>((sum, value) => sum + value, 0) + weatherScore) / (scores.length + 1)) *
      100,
  );
}

function statusFor(
  workOrderStatus: WorkOrderStatus,
  conflicts: readonly MaintenancePlanConflict[],
): MaintenancePlanStatus {
  if (isClosed(workOrderStatus)) return "completed";
  if (workOrderStatus === "in-progress") return "in-progress";
  if (workOrderStatus === "paused") return "paused";
  if (workOrderStatus === "draft" || workOrderStatus === "pending-approval")
    return "approval-gated";
  return conflicts.some((conflict) => conflict.severity === "critical") ? "at-risk" : "ready";
}

function taskProgress(workOrder: WorkOrder, completedTaskIds?: readonly string[]): number {
  const completed =
    workOrder.id === FEATURED_WORK_ORDER_ID && completedTaskIds
      ? completedTaskIds.length
      : workOrder.tasks.filter((task) => task.completed).length;
  return Math.round((completed / Math.max(1, workOrder.tasks.length)) * 100);
}

function toPlan(workOrder: WorkOrder, completedTaskIds?: readonly string[]): MaintenancePlan {
  const turbine = turbines.find((item) => item.id === workOrder.turbineId);
  const endsAt = estimatedEnd(workOrder);
  const weather = matchWeather(workOrder, endsAt);
  const crew = crewResource(workOrder);
  const vessels = vesselResources(workOrder);
  const tools = workOrder.requiredTools.map((required) => toolResource(workOrder, required));
  const parts = workOrder.spareParts.map((required) => partResource(workOrder, required));
  const conflicts = baseConflicts(workOrder, weather, crew, vessels, tools, parts);
  const resources = [crew, ...vessels, ...tools, ...parts];
  return {
    id: `PLAN-${workOrder.id.slice(3)}`,
    workOrderId: workOrder.id,
    turbineId: workOrder.turbineId,
    turbineHealthScore: turbine?.healthScore ?? 0,
    issue: workOrder.issue,
    description: workOrder.description,
    assignedTeam: workOrder.assignedTeam,
    teamKey: crew.id,
    priority: workOrder.priority,
    risk: workOrder.riskLevel,
    workOrderStatus: workOrder.status,
    status: statusFor(workOrder.status, conflicts),
    startsAt: workOrder.plannedStart,
    endsAt,
    deadline: workOrder.deadline,
    dayKey: workOrder.plannedStart.slice(0, 10),
    durationHours: workOrder.estimatedDurationHours,
    taskProgressPercent: taskProgress(workOrder, completedTaskIds),
    weather,
    crew,
    vessels,
    spareParts: parts,
    tools,
    readinessPercent: readinessFor(resources, weather),
    conflicts,
    relatedMissionId: workOrder.relatedMissionId,
    readOnly: true,
    source: "deterministic-demo-fixtures",
  };
}

function addOverlapConflicts(plans: readonly MaintenancePlan[]): MaintenancePlan[] {
  return plans.map((plan) => {
    if (!["ready", "at-risk", "in-progress"].includes(plan.status)) return plan;
    const overlapping = plans.find(
      (candidate) =>
        candidate.id !== plan.id &&
        ["ready", "at-risk", "in-progress"].includes(candidate.status) &&
        overlaps(plan.startsAt, plan.endsAt, candidate.startsAt, candidate.endsAt) &&
        (candidate.crew.id === plan.crew.id ||
          candidate.vessels.some((vessel) => plan.vessels.some((item) => item.id === vessel.id))),
    );
    if (!overlapping || plan.conflicts.some((conflict) => conflict.code === "RESOURCE_OVERLAP")) {
      return plan;
    }
    const conflicts = [
      ...plan.conflicts,
      {
        code: "RESOURCE_OVERLAP" as const,
        severity: "critical" as const,
        message: `与 ${overlapping.workOrderId} 的班组或船舶时段重叠。`,
      },
    ];
    return {
      ...plan,
      status: statusFor(plan.workOrderStatus, conflicts),
      readinessPercent: Math.min(plan.readinessPercent, 62),
      conflicts,
    };
  });
}

export function createMaintenancePlans(
  options: CreateMaintenancePlansOptions = {},
): readonly MaintenancePlan[] {
  const featuredStatus = options.featuredWorkOrderStatus ?? canonicalDemoWorkflow.workOrderStatus;
  const overlaid = workOrders.map((workOrder) =>
    workOrder.id === FEATURED_WORK_ORDER_ID ? { ...workOrder, status: featuredStatus } : workOrder,
  );
  return Object.freeze(
    addOverlapConflicts(
      overlaid.map((workOrder) => toPlan(workOrder, options.featuredCompletedTaskIds)),
    ).sort(
      (left, right) =>
        left.startsAt.localeCompare(right.startsAt) || left.id.localeCompare(right.id),
    ),
  );
}

const riskRank: Readonly<Record<RiskLevel, number>> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};

export function sortMaintenancePlans(
  plans: readonly MaintenancePlan[],
  sort: MaintenancePlanSortMode,
): MaintenancePlan[] {
  return [...plans].sort((left, right) => {
    if (sort === "risk-desc") {
      return (
        riskRank[right.risk] - riskRank[left.risk] ||
        left.startsAt.localeCompare(right.startsAt) ||
        left.id.localeCompare(right.id)
      );
    }
    if (sort === "readiness-desc") {
      return (
        right.readinessPercent - left.readinessPercent ||
        left.startsAt.localeCompare(right.startsAt) ||
        left.id.localeCompare(right.id)
      );
    }
    if (sort === "deadline-asc") {
      return left.deadline.localeCompare(right.deadline) || left.id.localeCompare(right.id);
    }
    return left.startsAt.localeCompare(right.startsAt) || left.id.localeCompare(right.id);
  });
}

export function maintenancePlanTeamFacets(
  plans: readonly MaintenancePlan[],
): readonly { value: string; label: string }[] {
  return [...new Map(plans.map((plan) => [plan.teamKey, plan.crew.label] as const)).entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((left, right) => left.label.localeCompare(right.label, "zh-CN"));
}

export function findWeatherWindow(id: string | null): WeatherWindow | undefined {
  return id ? weatherWindows.find((window) => window.id === id) : undefined;
}

export function findMaintenanceTool(id: string): MaintenanceTool | undefined {
  return maintenanceTools.find((tool) => tool.id === id);
}

export function findServiceVessel(id: string): ServiceVessel | undefined {
  return serviceVessels.find((vessel) => vessel.id === id);
}
