import { failureCases, historicalWorkOrders } from "./archive-data";
import { turbines, windFarm } from "./farm-data";
import { healthAssessments } from "./health-data";
import { alarms, evidenceItems, missions, workOrders } from "./operations-data";
import {
  overlayWorkflowHealth,
  overlayWorkflowMission,
  overlayWorkflowWorkOrder,
} from "./server-workflow-overlays";
import type { ServerWorkflowSnapshot } from "./server-workflow-contract";

export const reportTypes = [
  "daily-operations",
  "alarm-analysis",
  "ai-diagnosis",
  "maintenance",
  "asset-health",
  "weekly-wind-farm",
] as const;

export type ReportType = (typeof reportTypes)[number];
export type ReportPeriod = "daily" | "weekly" | "incident" | "snapshot";

export interface ReportMetric {
  readonly label: string;
  readonly value: string;
  readonly context: string;
  readonly tone: "neutral" | "positive" | "attention" | "critical";
}

export interface ReportSection {
  readonly heading: string;
  readonly summary: string;
  readonly findings: readonly string[];
}

export interface WindOpsReport {
  readonly id: string;
  readonly type: ReportType;
  readonly typeLabel: string;
  readonly title: string;
  readonly subtitle: string;
  readonly period: ReportPeriod;
  readonly periodLabel: string;
  readonly periodStart: string;
  readonly periodEnd: string;
  readonly generatedAt: string;
  readonly status: "ready";
  readonly ownerAgent: string;
  readonly assetScope: string;
  readonly highlight: string;
  readonly tags: readonly string[];
  readonly metrics: readonly ReportMetric[];
  readonly sections: readonly ReportSection[];
  readonly linkedEntityIds: readonly string[];
  readonly workflow: {
    readonly turbineId: "WT-023";
    readonly missionStatus: ServerWorkflowSnapshot["mission"]["status"];
    readonly decisionStatus: ServerWorkflowSnapshot["decision"]["status"];
    readonly workOrderStatus: ServerWorkflowSnapshot["workOrder"]["status"];
    readonly completedTaskCount: number;
    readonly totalTaskCount: number;
    readonly healthScore: number;
    readonly mainBearingHealthScore: number;
    readonly revision: number;
    readonly knowledgeCaseId: string | null;
  };
}

const countBy = <T extends string>(values: readonly T[]): Readonly<Record<T, number>> =>
  values.reduce(
    (counts, value) => ({ ...counts, [value]: (counts[value] ?? 0) + 1 }),
    {} as Record<T, number>,
  );

const percentage = (part: number, total: number): string =>
  `${((part / Math.max(1, total)) * 100).toFixed(1)}%`;

const workflowForReport = (snapshot: ServerWorkflowSnapshot): WindOpsReport["workflow"] => ({
  turbineId: snapshot.turbineId,
  missionStatus: snapshot.mission.status,
  decisionStatus: snapshot.decision.status,
  workOrderStatus: snapshot.workOrder.status,
  completedTaskCount: snapshot.workOrder.completedTaskCount,
  totalTaskCount: snapshot.workOrder.totalTaskCount,
  healthScore: snapshot.health.turbineScore,
  mainBearingHealthScore: snapshot.health.mainBearingScore,
  revision: snapshot.revision,
  knowledgeCaseId: snapshot.knowledgeCaseId,
});

export function buildReportCatalog(snapshot: ServerWorkflowSnapshot): readonly WindOpsReport[] {
  const currentMissions = overlayWorkflowMission(missions, snapshot);
  const currentWorkOrders = overlayWorkflowWorkOrder(workOrders, snapshot);
  const currentHealth = overlayWorkflowHealth(healthAssessments, snapshot);
  const workflow = workflowForReport(snapshot);
  const unresolvedAlarms = alarms.filter((alarm) => alarm.status !== "resolved");
  const alarmSeverities = countBy(alarms.map((alarm) => alarm.severity));
  const missionStatuses = countBy(currentMissions.map((mission) => mission.status));
  const workOrderStatuses = countBy(currentWorkOrders.map((workOrder) => workOrder.status));
  const diagnosedMissions = currentMissions.filter((mission) => mission.diagnosis !== null);
  const confidenceValues = diagnosedMissions.flatMap((mission) =>
    mission.confidencePercent === null ? [] : [mission.confidencePercent],
  );
  const averageConfidence =
    confidenceValues.reduce((sum, value) => sum + value, 0) / Math.max(1, confidenceValues.length);
  const completedOrders = [...currentWorkOrders, ...historicalWorkOrders].filter(
    (order) => order.status === "completed" || order.status === "closed",
  );
  const elevatedHealthRisk = currentHealth.filter(
    (assessment) => assessment.riskLevel === "high" || assessment.riskLevel === "critical",
  );
  const decliningHealth = currentHealth.filter((assessment) => assessment.trend === "declining");
  const averageAvailability =
    turbines.reduce((sum, turbine) => sum + turbine.availabilityPercent, 0) / turbines.length;
  const activeMissions = currentMissions.filter((mission) => mission.status !== "completed");
  const featuredMission = currentMissions.find((mission) => mission.id === snapshot.mission.id)!;
  const featuredWorkOrder = currentWorkOrders.find(
    (workOrder) => workOrder.id === snapshot.workOrder.id,
  )!;
  const generatedAt = snapshot.updatedAt;
  const workflowHeadline =
    snapshot.workOrder.status === "completed"
      ? "WT-023 field work is closed and health verification is recorded"
      : snapshot.workOrder.status === "in-progress"
        ? `WT-023 field work is in progress (${snapshot.workOrder.completedTaskCount}/${snapshot.workOrder.totalTaskCount} tasks)`
        : snapshot.workOrder.status === "scheduled"
          ? "WT-023 is approved and scheduled for field execution"
          : snapshot.decision.status === "rejected"
            ? "WT-023 recommendation was rejected and remains locked"
            : snapshot.decision.status === "revision-requested"
              ? "WT-023 recommendation requires revision before execution"
              : snapshot.decision.status === "approved"
                ? "WT-023 recommendation is approved; the work order is awaiting execution"
                : "WT-023 remains at the human-review gate";

  const common = {
    generatedAt,
    status: "ready" as const,
    workflow,
  };

  return [
    {
      ...common,
      id: "RPT-DAILY-20260813",
      type: "daily-operations",
      typeLabel: "Daily Operations",
      title: "Daily Operations Report",
      subtitle: "Fleet output, availability, alarms, and active operational work",
      period: "daily",
      periodLabel: "13 Aug 2026",
      periodStart: "2026-08-13T00:00:00+08:00",
      periodEnd: "2026-08-13T23:59:59+08:00",
      ownerAgent: "Operations Coordinator Agent",
      assetScope: windFarm.nameEn,
      highlight: `${windFarm.operatingTurbines}/${windFarm.turbineCount} turbines are producing ${windFarm.currentPowerMW.toFixed(1)} MW; ${workflowHeadline}.`,
      tags: ["operations", "generation", "availability", "WT-023"],
      metrics: [
        {
          label: "Current power",
          value: `${windFarm.currentPowerMW.toFixed(1)} MW`,
          context: `${windFarm.totalCapacityMW} MW installed`,
          tone: "positive",
        },
        {
          label: "Today generation",
          value: `${windFarm.todayGenerationGWh.toFixed(2)} GWh`,
          context: "Deterministic SCADA snapshot",
          tone: "positive",
        },
        {
          label: "Operating fleet",
          value: `${windFarm.operatingTurbines}/${windFarm.turbineCount}`,
          context: `${windFarm.maintenanceTurbines} maintenance / ${windFarm.offlineTurbines} offline`,
          tone: "neutral",
        },
        {
          label: "Open attention",
          value: `${unresolvedAlarms.length} alarms`,
          context: `${activeMissions.length} active missions`,
          tone: "attention",
        },
      ],
      sections: [
        {
          heading: "Fleet operating position",
          summary: "The wind farm is operational with the majority of assets producing normally.",
          findings: [
            `${percentage(windFarm.operatingTurbines, windFarm.turbineCount)} of turbines are in an operating state.`,
            `Fleet average health is ${windFarm.averageHealthScore.toFixed(1)} and mean availability is ${averageAvailability.toFixed(1)}%.`,
            `Current output is ${windFarm.currentPowerMW.toFixed(1)} MW against ${windFarm.totalCapacityMW} MW installed capacity.`,
          ],
        },
        {
          heading: "Operational attention",
          summary: "Agent missions concentrate operational signals into reviewable work packages.",
          findings: [
            `${unresolvedAlarms.length} unresolved alarms are linked to ${activeMissions.length} active missions.`,
            `${missionStatuses["under-review"] ?? 0} missions are at human review and ${missionStatuses.executing ?? 0} are executing.`,
            `WT-023 workflow is ${snapshot.mission.status}; decision ${snapshot.decision.status}; work order ${snapshot.workOrder.status}.`,
          ],
        },
      ],
      linkedEntityIds: [
        windFarm.id,
        snapshot.turbineId,
        snapshot.mission.id,
        snapshot.workOrder.id,
      ],
    },
    {
      ...common,
      id: "RPT-ALARM-20260813",
      type: "alarm-analysis",
      typeLabel: "Alarm Analysis",
      title: "Alarm Analysis Report",
      subtitle: "Severity distribution, unresolved queue, and alarm-to-mission traceability",
      period: "daily",
      periodLabel: "13 Aug 2026",
      periodStart: "2026-08-13T00:00:00+08:00",
      periodEnd: "2026-08-13T23:59:59+08:00",
      ownerAgent: "SCADA Analysis Agent",
      assetScope: `${windFarm.code} / fleet alarms`,
      highlight: `${unresolvedAlarms.length} unresolved alarms remain; WT-023 has three correlated signals consolidated into one mission.`,
      tags: ["alarms", "severity", "correlation", "WT-023"],
      metrics: [
        {
          label: "Unresolved",
          value: `${unresolvedAlarms.length}`,
          context: `${alarms.length} live alarm records`,
          tone: "attention",
        },
        {
          label: "Critical / major",
          value: `${(alarmSeverities.critical ?? 0) + (alarmSeverities.major ?? 0)}`,
          context: "Priority response queue",
          tone: "critical",
        },
        {
          label: "AI action created",
          value: `${alarms.filter((alarm) => alarm.aiStatus === "action-created").length}`,
          context: "Alarm-to-action conversion",
          tone: "positive",
        },
        {
          label: "WT-023 evidence",
          value: `${evidenceItems.filter((item) => item.turbineId === "WT-023").length}`,
          context: "Traceable evidence items",
          tone: "neutral",
        },
      ],
      sections: [
        {
          heading: "Severity and queue",
          summary: "The live queue is dominated by actionable warning and major signals.",
          findings: [
            `Severity counts: critical ${alarmSeverities.critical ?? 0}, major ${alarmSeverities.major ?? 0}, minor ${alarmSeverities.minor ?? 0}, warning ${alarmSeverities.warning ?? 0}.`,
            `${alarms.filter((alarm) => alarm.status === "acknowledged").length} alarms have been acknowledged.`,
            `${alarms.filter((alarm) => alarm.missionId !== null).length} alarm records retain a mission link.`,
          ],
        },
        {
          heading: "WT-023 correlation case",
          summary:
            "Vibration, temperature, and power fluctuation were correlated before a mission was opened.",
          findings: [
            "Main-bearing vibration reached 4.81 mm/s against a 4.50 mm/s threshold.",
            "Temperature was 8.4 C above its normalized operating baseline.",
            `The correlated case is controlled by ${snapshot.mission.id} at ${snapshot.mission.status}.`,
          ],
        },
      ],
      linkedEntityIds: ["ALARM-0031", "ALARM-0032", "ALARM-0033", snapshot.mission.id],
    },
    {
      ...common,
      id: "RPT-AI-WT023-20260813",
      type: "ai-diagnosis",
      typeLabel: "AI Diagnosis",
      title: "AI Diagnosis Report",
      subtitle: "Evidence-backed multi-agent diagnosis and guarded recommendation",
      period: "incident",
      periodLabel: "WT-023 incident / 13 Aug 2026",
      periodStart: featuredMission.createdAt,
      periodEnd: generatedAt,
      ownerAgent: "Failure Diagnosis Agent",
      assetScope: `WT-023 / ${snapshot.mission.id}`,
      highlight: `Main-bearing early degradation is assessed at ${featuredMission.confidencePercent ?? 0}% confidence; high-risk execution remains bound to human approval.`,
      tags: ["AI", "diagnosis", "evidence", "HITL", "WT-023"],
      metrics: [
        {
          label: "Diagnosis confidence",
          value: `${featuredMission.confidencePercent ?? 0}%`,
          context: "Featured mission assessment",
          tone: "attention",
        },
        {
          label: "Supporting evidence",
          value: `${featuredMission.evidenceIds.length}`,
          context: "SCADA, CMS, model, history, resources",
          tone: "positive",
        },
        {
          label: "Diagnosed missions",
          value: `${diagnosedMissions.length}`,
          context: `${averageConfidence.toFixed(1)}% mean confidence`,
          tone: "neutral",
        },
        {
          label: "Human gate",
          value: snapshot.decision.status,
          context: snapshot.decision.approval ? "Approval recorded" : "Approval pending",
          tone: snapshot.decision.approval ? "positive" : "attention",
        },
      ],
      sections: [
        {
          heading: "Evidence synthesis",
          summary:
            "Independent signal, spectral, history, and resource evidence supports the diagnosis.",
          findings: [
            "Main-bearing (主轴承) vibration RMS rose 27% from 3.79 to 4.81 mm/s across 44 consecutive samples.",
            "BPFO-band energy increased 19%, consistent with an outer-race degradation pattern.",
            "The closest historical case match scored 0.91 and the RUL model estimates 47 days before intervention.",
          ],
        },
        {
          heading: "Guarded recommendation",
          summary:
            "The recommended response balances deterioration risk, safe access, and energy loss.",
          findings: [
            "Recommended action: derate to 70%, increase sampling, and inspect within the weather window.",
            `Decision status is ${snapshot.decision.status}; no high-risk field execution occurs without the recorded gate.`,
            `Workflow revision ${snapshot.revision} is the authoritative report overlay.`,
          ],
        },
      ],
      linkedEntityIds: [snapshot.mission.id, snapshot.decision.id, ...featuredMission.evidenceIds],
    },
    {
      ...common,
      id: "RPT-MAINT-20260813",
      type: "maintenance",
      typeLabel: "Maintenance",
      title: "Maintenance Report",
      subtitle: "Work-order readiness, execution state, resources, and historical completion",
      period: "snapshot",
      periodLabel: "Maintenance snapshot / 13 Aug 2026",
      periodStart: "2026-08-13T00:00:00+08:00",
      periodEnd: generatedAt,
      ownerAgent: "Work Order Agent",
      assetScope: `${windFarm.code} / maintenance portfolio`,
      highlight: `${currentWorkOrders.length} live work orders and ${historicalWorkOrders.length} historical orders are traceable; WT-023 is ${snapshot.workOrder.status}.`,
      tags: ["maintenance", "work-order", "resources", "safety", "WT-023"],
      metrics: [
        {
          label: "Live work orders",
          value: `${currentWorkOrders.length}`,
          context: `${workOrderStatuses["in-progress"] ?? 0} in progress`,
          tone: "neutral",
        },
        {
          label: "Historical ledger",
          value: `${historicalWorkOrders.length}`,
          context: `${completedOrders.length} completed or closed`,
          tone: "positive",
        },
        {
          label: "WT-023 tasks",
          value: `${snapshot.workOrder.completedTaskCount}/${snapshot.workOrder.totalTaskCount}`,
          context: `Work order ${snapshot.workOrder.status}`,
          tone: snapshot.workOrder.status === "completed" ? "positive" : "attention",
        },
        {
          label: "Reserved package",
          value: "Crew + CTV + tools",
          context: "Weather-gated execution",
          tone: "positive",
        },
      ],
      sections: [
        {
          heading: "Portfolio position",
          summary:
            "The live work-order portfolio remains linked to missions, decisions, safety, and resources.",
          findings: [
            `Status counts include ${workOrderStatuses.draft ?? 0} draft, ${workOrderStatuses.scheduled ?? 0} scheduled, and ${workOrderStatuses["in-progress"] ?? 0} in progress.`,
            `${currentWorkOrders.filter((order) => order.createdByAgentId !== null).length} live orders were created by an Agent.`,
            `${failureCases.length} closed-loop failure cases support similarity-based planning.`,
          ],
        },
        {
          heading: "WT-023 field package",
          summary:
            "The main-bearing inspection package preserves the human gate and five explicit tasks.",
          findings: [
            `Work order ${featuredWorkOrder.id} is ${snapshot.workOrder.status} with ${snapshot.workOrder.completedTaskCount}/${snapshot.workOrder.totalTaskCount} tasks complete.`,
            `Assigned team: ${featuredWorkOrder.assignedTeam}; estimated duration ${featuredWorkOrder.estimatedDurationHours} hours.`,
            `${featuredWorkOrder.ppeRequirements.length} PPE controls, ${featuredWorkOrder.requiredTools.length} tools, and ${featuredWorkOrder.safetyProcedures.length} safety procedures are recorded.`,
          ],
        },
      ],
      linkedEntityIds: [snapshot.workOrder.id, snapshot.mission.id, snapshot.decision.id],
    },
    {
      ...common,
      id: "RPT-HEALTH-20260813",
      type: "asset-health",
      typeLabel: "Asset Health",
      title: "Asset Health Report",
      subtitle: "Fleet health distribution, trend signals, and intervention priority",
      period: "snapshot",
      periodLabel: "Health snapshot / 13 Aug 2026",
      periodStart: "2026-08-13T00:00:00+08:00",
      periodEnd: generatedAt,
      ownerAgent: "Predictive Maintenance Agent",
      assetScope: `${windFarm.code} / ${turbines.length} turbines`,
      highlight: `${elevatedHealthRisk.length} turbines have high or critical 30-day risk; WT-023 health is ${snapshot.health.turbineScore}.`,
      tags: ["health", "risk", "RUL", "trend", "WT-023"],
      metrics: [
        {
          label: "Fleet health",
          value: `${windFarm.averageHealthScore.toFixed(1)}`,
          context: "Average score / 100",
          tone: "positive",
        },
        {
          label: "Elevated risk",
          value: `${elevatedHealthRisk.length}`,
          context: "High or critical 30-day risk",
          tone: "critical",
        },
        {
          label: "Declining trend",
          value: `${decliningHealth.length}`,
          context: "Assets requiring trend review",
          tone: "attention",
        },
        {
          label: "WT-023 bearing",
          value: `${snapshot.health.mainBearingScore}`,
          context: `Turbine health ${snapshot.health.turbineScore}`,
          tone: snapshot.health.mainBearingScore >= 75 ? "positive" : "critical",
        },
      ],
      sections: [
        {
          heading: "Fleet health distribution",
          summary: "Health scores and 30-day risk are calculated for all 64 turbines.",
          findings: [
            `${currentHealth.filter((item) => item.state === "healthy").length} assets are healthy and ${currentHealth.filter((item) => item.state === "degraded" || item.state === "critical").length} are degraded or critical.`,
            `${decliningHealth.length} assets show a declining trend across the deterministic snapshot.`,
            `The highest modeled failure probability is ${Math.max(...currentHealth.map((item) => item.failureProbability30d))}%.`,
          ],
        },
        {
          heading: "WT-023 health overlay",
          summary:
            "The report reflects the current server workflow, including post-maintenance recovery when closed.",
          findings: [
            `Turbine health is ${snapshot.health.turbineScore}; main-bearing health is ${snapshot.health.mainBearingScore}.`,
            `Mission ${snapshot.mission.id} is ${snapshot.mission.status}; work order ${snapshot.workOrder.id} is ${snapshot.workOrder.status}.`,
            snapshot.knowledgeCaseId
              ? `Closed-loop knowledge case ${snapshot.knowledgeCaseId} is available.`
              : "Knowledge capture remains pending until the field workflow is completed.",
          ],
        },
      ],
      linkedEntityIds: [snapshot.turbineId, snapshot.mission.id, snapshot.workOrder.id],
    },
    {
      ...common,
      id: "RPT-WEEKLY-2026W33",
      type: "weekly-wind-farm",
      typeLabel: "Weekly Wind Farm",
      title: "Weekly Wind Farm Report",
      subtitle: "Executive operating summary for East China Offshore Wind Farm",
      period: "weekly",
      periodLabel: "10-16 Aug 2026 / W33",
      periodStart: "2026-08-10T00:00:00+08:00",
      periodEnd: "2026-08-16T23:59:59+08:00",
      ownerAgent: "Operations Coordinator Agent",
      assetScope: windFarm.nameEn,
      highlight: `The 384 MW fleet remains operational at ${averageAvailability.toFixed(1)}% mean availability, with WT-023 the featured governed intervention.`,
      tags: ["weekly", "executive", "wind-farm", "KPI", "WT-023"],
      metrics: [
        {
          label: "Installed capacity",
          value: `${windFarm.totalCapacityMW} MW`,
          context: `${windFarm.turbineCount} x 6.0 MW`,
          tone: "neutral",
        },
        {
          label: "Mean availability",
          value: `${averageAvailability.toFixed(1)}%`,
          context: "Deterministic fleet mean",
          tone: "positive",
        },
        {
          label: "Active missions",
          value: `${activeMissions.length}`,
          context: `${currentMissions.length} mission records`,
          tone: "attention",
        },
        {
          label: "Closed-loop cases",
          value: `${failureCases.length}`,
          context: "Historical failure knowledge",
          tone: "positive",
        },
      ],
      sections: [
        {
          heading: "Executive summary",
          summary:
            "Fleet output and availability remain stable while AI-guided attention is focused on a small asset subset.",
          findings: [
            `${windFarm.operatingTurbines} turbines are operating, ${windFarm.maintenanceTurbines} is in maintenance, and ${windFarm.offlineTurbines} is offline.`,
            `Current power is ${windFarm.currentPowerMW.toFixed(1)} MW and daily generation at snapshot is ${windFarm.todayGenerationGWh.toFixed(2)} GWh.`,
            `${activeMissions.length} missions are active and retain links to their underlying alarms and work orders.`,
          ],
        },
        {
          heading: "Risk and intervention focus",
          summary:
            "The weekly review highlights governed intervention rather than autonomous high-risk execution.",
          findings: [
            `${elevatedHealthRisk.length} turbines are in the high or critical modeled-risk bands.`,
            `WT-023 is at mission ${snapshot.mission.status}, decision ${snapshot.decision.status}, and work order ${snapshot.workOrder.status}.`,
            `Audit revision ${snapshot.revision} and ${snapshot.auditEvents.length} workflow events support the report trace.`,
          ],
        },
      ],
      linkedEntityIds: [
        windFarm.id,
        snapshot.turbineId,
        snapshot.mission.id,
        snapshot.workOrder.id,
      ],
    },
  ];
}

export const findReport = (
  catalog: readonly WindOpsReport[],
  reportId: string,
): WindOpsReport | undefined =>
  catalog.find((report) => report.id === reportId.trim().toUpperCase());

export function reportToPlainText(report: WindOpsReport): readonly string[] {
  return [
    report.title,
    report.subtitle,
    "",
    `Report ID: ${report.id}`,
    `Type: ${report.typeLabel}`,
    `Period: ${report.periodLabel}`,
    `Generated: ${report.generatedAt}`,
    `Owner: ${report.ownerAgent}`,
    `Asset scope: ${report.assetScope}`,
    "",
    "EXECUTIVE HIGHLIGHT",
    report.highlight,
    "",
    "KEY METRICS",
    ...report.metrics.map((metric) => `${metric.label}: ${metric.value} - ${metric.context}`),
    "",
    ...report.sections.flatMap((section) => [
      section.heading.toUpperCase(),
      section.summary,
      ...section.findings.map((finding) => `- ${finding}`),
      "",
    ]),
    "WORKFLOW TRACE",
    `WT-023 mission=${report.workflow.missionStatus}; decision=${report.workflow.decisionStatus}; workOrder=${report.workflow.workOrderStatus}`,
    `Tasks=${report.workflow.completedTaskCount}/${report.workflow.totalTaskCount}; health=${report.workflow.healthScore}; bearing=${report.workflow.mainBearingHealthScore}; revision=${report.workflow.revision}`,
    `Linked entities: ${report.linkedEntityIds.join(", ")}`,
    "",
    "Generated from deterministic WindOps fixtures with the authoritative server workflow overlay.",
  ];
}
