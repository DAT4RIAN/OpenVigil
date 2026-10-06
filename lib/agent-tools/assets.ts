import type { AgentToolArguments, AgentToolExecutionContext } from "./contracts";
import { requiredTurbine, workflowSnapshotAt } from "./helpers";
import { overlayWorkflowMission, overlayWorkflowTurbine } from "../server-workflow-overlays";
import { subsystemHealth } from "../telemetry-data";
import { alarms, missions } from "../operations-data";
import type { SubsystemKey } from "../types";
import { AgentToolRuntimeError } from "./contracts";
import { windFarm } from "../farm-data";

export const getTurbineStatus = (
  args: AgentToolArguments,
  context: AgentToolExecutionContext,
): unknown => {
  const turbineId = args.turbineId as string;
  const fixtureTurbine = requiredTurbine(turbineId);
  const turbine = context.workflowSnapshot
    ? (overlayWorkflowTurbine([fixtureTurbine], context.workflowSnapshot)[0] ?? fixtureTurbine)
    : fixtureTurbine;
  const assetSubsystems = subsystemHealth.filter((item) => item.turbineId === turbineId);
  const activeAlarms = alarms.filter(
    (alarm) => alarm.turbineId === turbineId && alarm.status !== "resolved",
  );
  const currentMissions = context.workflowSnapshot
    ? overlayWorkflowMission(missions, context.workflowSnapshot)
    : missions;
  const activeMissions = currentMissions.filter(
    (mission) => mission.turbineId === turbineId && mission.status !== "completed",
  );
  const lowestSubsystem = [...assetSubsystems].sort(
    (left, right) => left.healthScore - right.healthScore || left.id.localeCompare(right.id),
  )[0];

  return {
    snapshotAt: workflowSnapshotAt(context),
    turbine,
    subsystemSummary: {
      count: assetSubsystems.length,
      degradedCount: assetSubsystems.filter(
        (item) => item.state === "degraded" || item.state === "critical",
      ).length,
      lowest: lowestSubsystem
        ? {
            subsystem: lowestSubsystem.key,
            healthScore:
              lowestSubsystem.key === "main-bearing" &&
              turbineId === context.workflowSnapshot?.turbineId
                ? context.workflowSnapshot.health.mainBearingScore
                : lowestSubsystem.healthScore,
            state:
              lowestSubsystem.key === "main-bearing" &&
              turbineId === context.workflowSnapshot?.turbineId &&
              context.workflowSnapshot.workOrder.status === "completed"
                ? "watch"
                : lowestSubsystem.state,
            finding:
              lowestSubsystem.key === "main-bearing" &&
              turbineId === context.workflowSnapshot?.turbineId &&
              context.workflowSnapshot.workOrder.status === "completed"
                ? "主轴承检查与复测已完成，健康趋势恢复"
                : lowestSubsystem.primaryFinding,
          }
        : null,
    },
    activeAlarms: activeAlarms.map((alarm) => ({
      id: alarm.id,
      code: alarm.code,
      severity: alarm.severity,
      subsystem: alarm.subsystem,
      status: alarm.status,
      missionId: alarm.missionId,
    })),
    activeMissionIds: activeMissions.map((mission) => mission.id),
  };
};

const statusPenalty: Readonly<Record<string, number>> = Object.freeze({
  running: 0,
  warning: 8,
  critical: 20,
  maintenance: 12,
  offline: 30,
  "communication-lost": 25,
});

export const calculateHealthScore = (
  args: AgentToolArguments,
  context: AgentToolExecutionContext,
): unknown => {
  const turbineId = args.turbineId as string;
  const turbine = requiredTurbine(turbineId);
  const subsystem = args.subsystem as SubsystemKey | undefined;
  const matchingSubsystems = subsystemHealth.filter((item) => item.turbineId === turbineId);

  if (subsystem) {
    const assessment = matchingSubsystems.find((item) => item.key === subsystem);
    if (!assessment) {
      throw new AgentToolRuntimeError(
        "SUBSYSTEM_HEALTH_NOT_FOUND",
        `No subsystem health snapshot exists for ${turbineId}/${subsystem}.`,
        404,
        { turbineId, subsystem },
      );
    }
    const workflowMainBearing =
      turbineId === context.workflowSnapshot?.turbineId && subsystem === "main-bearing";
    const closed = context.workflowSnapshot?.workOrder.status === "completed";
    return {
      snapshotAt: workflowMainBearing ? context.workflowSnapshot?.updatedAt : assessment.assessedAt,
      turbineId,
      scope: "subsystem",
      subsystem,
      healthScore: workflowMainBearing
        ? context.workflowSnapshot?.health.mainBearingScore
        : assessment.healthScore,
      state: workflowMainBearing && closed ? "watch" : assessment.state,
      trend: workflowMainBearing && closed ? "improving" : assessment.trend,
      anomalyScore: workflowMainBearing && closed ? 0.42 : assessment.anomalyScore,
      formula: workflowMainBearing
        ? "D1 workflow health feedback"
        : "fixture subsystem health snapshot",
    };
  }

  const lowestSubsystemScore =
    matchingSubsystems.length > 0
      ? Math.min(...matchingSubsystems.map((item) => item.healthScore))
      : 100;
  const penalties = {
    status: statusPenalty[turbine.status] ?? 0,
    activeAlarms: Math.min(20, turbine.activeAlarmCount * 5),
    weakestSubsystem: Math.round((100 - lowestSubsystemScore) / 4),
  };
  const calculatedScore = Math.max(
    0,
    100 - penalties.status - penalties.activeAlarms - penalties.weakestSubsystem,
  );

  return {
    snapshotAt:
      turbineId === context.workflowSnapshot?.turbineId
        ? context.workflowSnapshot.updatedAt
        : windFarm.lastUpdatedAt,
    turbineId,
    scope: "asset",
    healthScore:
      turbineId === context.workflowSnapshot?.turbineId
        ? context.workflowSnapshot.health.turbineScore
        : calculatedScore,
    fixtureHealthScore: turbine.healthScore,
    penalties,
    weakestSubsystemScore: matchingSubsystems.length > 0 ? lowestSubsystemScore : null,
    formula: "100 - status penalty - alarm penalty - weakest-subsystem penalty",
  };
};
