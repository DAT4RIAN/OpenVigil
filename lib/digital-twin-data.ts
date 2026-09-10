import { buildGenericSubsystemAssessments } from "./generic-subsystem-data";
import { healthAssessments } from "./health-data";
import { alarms, missions, workOrders } from "./operations-data";
import { scadaSeries, subsystemHealth, weatherWindows } from "./telemetry-data";
import { turbines, windFarm } from "./farm-data";
import type { ServerWorkflowSnapshot } from "./server-workflow-contract";
import type { HealthState, MissionStatus, TurbineStatus, WorkOrderStatus } from "./types";

export interface DigitalTwinSubsystem {
  readonly key: string;
  readonly name: string;
  readonly healthScore: number;
  readonly state: HealthState;
  readonly alertCount: number;
  readonly anomalyScore: number;
  readonly primaryFinding: string;
}

export interface DigitalTwinSignal {
  readonly metric: string;
  readonly label: string;
  readonly value: number;
  readonly unit: string;
  readonly quality: string;
  readonly isAnomaly: boolean;
}

export interface DigitalTwinSnapshot {
  readonly turbine: {
    readonly id: string;
    readonly model: string;
    readonly manufacturer: string;
    readonly status: TurbineStatus;
    readonly powerMW: number;
    readonly windSpeedMps: number;
    readonly healthScore: number;
    readonly latitude: number | null;
    readonly longitude: number | null;
  };
  readonly subsystems: readonly DigitalTwinSubsystem[];
  readonly signals: readonly DigitalTwinSignal[];
  readonly context: {
    readonly activeAlarmCount: number;
    readonly missionId: string | null;
    readonly missionStatus: MissionStatus | null;
    readonly workOrderId: string | null;
    readonly workOrderStatus: WorkOrderStatus | null;
    readonly nextWeatherWindowId: string | null;
    readonly nextWeatherWindowSuitability: string | null;
  };
  readonly model: {
    readonly mode: "deterministic-operational-twin" | "operational-state-twin" | "unavailable";
    readonly realPhysicsSimulation: false;
    readonly readOnly: true;
    readonly source:
      | "fixture"
      | "ephemeral-workflow-overlay"
      | "d1-workflow-overlay"
      | "postgresql-timescaledb"
      | "unavailable";
    readonly geometryConfigured?: boolean;
    readonly gisConfigured?: boolean;
    readonly geometryUri?: string | null;
    readonly geometrySha256?: string | null;
    readonly coordinateReferenceSystem?: string | null;
    readonly elevationM?: number | null;
    readonly profileUpdatedAt?: string | null;
  };
  readonly snapshotAt: string;
}

const clamp = (value: number, minimum: number, maximum: number): number =>
  Math.min(maximum, Math.max(minimum, value));

const normalizedTurbineId = (value: string): string => value.trim().toUpperCase();

function featuredSubsystems(workflow?: ServerWorkflowSnapshot): readonly DigitalTwinSubsystem[] {
  const completed = workflow?.workOrder.status === "completed";
  return subsystemHealth.map((subsystem) => {
    if (subsystem.key !== "main-bearing" || !workflow) {
      return Object.freeze({
        key: subsystem.key,
        name: subsystem.name,
        healthScore: subsystem.healthScore,
        state: subsystem.state,
        alertCount: subsystem.activeAlarmCount,
        anomalyScore: subsystem.anomalyScore,
        primaryFinding: subsystem.primaryFinding,
      });
    }

    return Object.freeze({
      key: subsystem.key,
      name: subsystem.name,
      healthScore: workflow.health.mainBearingScore,
      state: completed ? ("watch" as const) : subsystem.state,
      alertCount: completed ? 0 : subsystem.activeAlarmCount,
      anomalyScore: completed ? 0.42 : subsystem.anomalyScore,
      primaryFinding: completed
        ? "现场维护与复测完成，振动和温升回落，保持趋势观察"
        : subsystem.primaryFinding,
    });
  });
}

function genericSubsystems(turbineId: string): readonly DigitalTwinSubsystem[] {
  const turbine = turbines.find((candidate) => candidate.id === turbineId)!;
  return buildGenericSubsystemAssessments(turbine).map((assessment) =>
    Object.freeze({
      key: assessment.key,
      name: assessment.name,
      healthScore: assessment.healthScore,
      state: assessment.state,
      alertCount: assessment.alertCount,
      anomalyScore: Number(clamp((100 - assessment.healthScore) / 80, 0.05, 0.96).toFixed(2)),
      primaryFinding:
        assessment.alertCount > 0
          ? "确定性资产模型提示该子系统存在关联告警，建议核验"
          : "确定性资产模型未发现超阈值趋势",
    }),
  );
}

function signalsFor(turbineId: string): readonly DigitalTwinSignal[] {
  if (turbineId === "WT-023") {
    return scadaSeries.slice(0, 8).map((series) => {
      const latest = series.points.at(-1)!;
      return Object.freeze({
        metric: series.metric,
        label: series.label,
        value: latest.value,
        unit: series.unit,
        quality: latest.quality,
        isAnomaly: latest.isAnomaly,
      });
    });
  }

  const turbine = turbines.find((candidate) => candidate.id === turbineId)!;
  return Object.freeze([
    {
      metric: "active-power",
      label: "有功功率",
      value: turbine.powerMW,
      unit: "MW",
      quality: "good",
      isAnomaly: false,
    },
    {
      metric: "wind-speed",
      label: "机舱风速",
      value: turbine.windSpeedMps,
      unit: "m/s",
      quality: "good",
      isAnomaly: false,
    },
    {
      metric: "rotor-speed",
      label: "转子转速",
      value: turbine.rotorSpeedRpm,
      unit: "rpm",
      quality: "good",
      isAnomaly: false,
    },
    {
      metric: "nacelle-direction",
      label: "机舱方位",
      value: turbine.nacelleDirectionDeg,
      unit: "°",
      quality: "good",
      isAnomaly: false,
    },
  ]);
}

export function buildDigitalTwinSnapshot(
  turbineId: string,
  workflow?: ServerWorkflowSnapshot,
  workflowPersistence: "d1" | "ephemeral" = "ephemeral",
): DigitalTwinSnapshot | null {
  const normalized = normalizedTurbineId(turbineId);
  const turbine = turbines.find((candidate) => candidate.id === normalized);
  if (!turbine) return null;

  const health = healthAssessments.find((assessment) => assessment.turbineId === normalized)!;
  const workflowApplies = workflow?.turbineId === normalized;
  const relatedMission = missions.find(
    (mission) => mission.id === (workflowApplies ? workflow.mission.id : turbine.currentMissionId),
  );
  const relatedWorkOrder = workflowApplies
    ? workOrders.find((workOrder) => workOrder.id === workflow.workOrder.id)
    : workOrders.find((workOrder) => workOrder.turbineId === normalized);
  const openAlarms = alarms.filter(
    (alarm) => alarm.turbineId === normalized && !["resolved", "suppressed"].includes(alarm.status),
  );
  const weather = weatherWindows[0];

  return Object.freeze({
    turbine: Object.freeze({
      id: turbine.id,
      model: turbine.model,
      manufacturer: turbine.manufacturer,
      status: turbine.status,
      powerMW: turbine.powerMW,
      windSpeedMps: turbine.windSpeedMps,
      healthScore: workflowApplies ? workflow.health.turbineScore : health.healthScore,
      latitude: turbine.coordinates.latitude,
      longitude: turbine.coordinates.longitude,
    }),
    subsystems:
      normalized === "WT-023"
        ? featuredSubsystems(workflowApplies ? workflow : undefined)
        : genericSubsystems(normalized),
    signals: signalsFor(normalized),
    context: Object.freeze({
      activeAlarmCount: openAlarms.length,
      missionId: workflowApplies ? workflow.mission.id : (relatedMission?.id ?? null),
      missionStatus: workflowApplies ? workflow.mission.status : (relatedMission?.status ?? null),
      workOrderId: workflowApplies ? workflow.workOrder.id : (relatedWorkOrder?.id ?? null),
      workOrderStatus: workflowApplies
        ? workflow.workOrder.status
        : (relatedWorkOrder?.status ?? null),
      nextWeatherWindowId: weather?.id ?? null,
      nextWeatherWindowSuitability: weather?.suitability ?? null,
    }),
    model: Object.freeze({
      mode: "deterministic-operational-twin" as const,
      realPhysicsSimulation: false as const,
      readOnly: true as const,
      source: workflowApplies
        ? workflowPersistence === "d1"
          ? ("d1-workflow-overlay" as const)
          : ("ephemeral-workflow-overlay" as const)
        : ("fixture" as const),
    }),
    snapshotAt: workflowApplies ? workflow.updatedAt : windFarm.lastUpdatedAt,
  });
}
