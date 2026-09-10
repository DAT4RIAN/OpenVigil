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
import { localizedStatusLabel } from "./ui-localization";

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

export interface OpenVigilReport {
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
  readonly contentDigest?: string;
  readonly generationReason?: string;
  readonly createdBy?: string;
  readonly persisted?: boolean;
  readonly workflow: {
    readonly turbineId: string;
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

const workflowForReport = (snapshot: ServerWorkflowSnapshot): OpenVigilReport["workflow"] => ({
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

export function buildReportCatalog(snapshot: ServerWorkflowSnapshot): readonly OpenVigilReport[] {
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
  const missionStatusLabel = localizedStatusLabel(snapshot.mission.status);
  const decisionStatusLabel = localizedStatusLabel(snapshot.decision.status);
  const workOrderStatusLabel = localizedStatusLabel(snapshot.workOrder.status);
  const workflowHeadline =
    snapshot.workOrder.status === "completed"
      ? "WT-023 现场作业已闭环并记录健康验证结果"
      : snapshot.workOrder.status === "in-progress"
        ? `WT-023 现场作业执行中（${snapshot.workOrder.completedTaskCount}/${snapshot.workOrder.totalTaskCount} 项任务）`
        : snapshot.workOrder.status === "scheduled"
          ? "WT-023 已批准并排入现场执行计划"
          : snapshot.decision.status === "rejected"
            ? "WT-023 建议已拒绝，执行保持锁定"
            : snapshot.decision.status === "revision-requested"
              ? "WT-023 建议须修订后方可执行"
              : snapshot.decision.status === "approved"
                ? "WT-023 建议已批准；工单等待执行"
                : "WT-023 当前处于人工审核门禁";

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
      typeLabel: "运营日报",
      title: "运营日报",
      subtitle: "全场出力、可利用率、告警与活动作业",
      period: "daily",
      periodLabel: "2026 年 8 月 13 日",
      periodStart: "2026-08-13T00:00:00+08:00",
      periodEnd: "2026-08-13T23:59:59+08:00",
      ownerAgent: "运营协调 Agent",
      assetScope: windFarm.name,
      highlight: `${windFarm.operatingTurbines}/${windFarm.turbineCount} 台风机正在发电，当前出力 ${windFarm.currentPowerMW.toFixed(1)} MW；${workflowHeadline}。`,
      tags: ["运营", "发电", "可利用率", "WT-023"],
      metrics: [
        {
          label: "当前功率",
          value: `${windFarm.currentPowerMW.toFixed(1)} MW`,
          context: `装机容量 ${windFarm.totalCapacityMW} MW`,
          tone: "positive",
        },
        {
          label: "今日发电量",
          value: `${windFarm.todayGenerationGWh.toFixed(2)} GWh`,
          context: "确定性 SCADA 快照",
          tone: "positive",
        },
        {
          label: "运行机组",
          value: `${windFarm.operatingTurbines}/${windFarm.turbineCount}`,
          context: `${windFarm.maintenanceTurbines} 台维护 / ${windFarm.offlineTurbines} 台离线`,
          tone: "neutral",
        },
        {
          label: "待关注事项",
          value: `${unresolvedAlarms.length} 条告警`,
          context: `${activeMissions.length} 个活动 Mission`,
          tone: "attention",
        },
      ],
      sections: [
        {
          heading: "全场运行态势",
          summary: "风场保持运行，多数资产正常发电。",
          findings: [
            `${percentage(windFarm.operatingTurbines, windFarm.turbineCount)} 的风机处于运行状态。`,
            `全场平均健康度为 ${windFarm.averageHealthScore.toFixed(1)}，平均可利用率为 ${averageAvailability.toFixed(1)}%。`,
            `当前出力 ${windFarm.currentPowerMW.toFixed(1)} MW，装机容量 ${windFarm.totalCapacityMW} MW。`,
          ],
        },
        {
          heading: "运营关注事项",
          summary: "Agent Mission 将运行信号汇总为可审核的作业包。",
          findings: [
            `${unresolvedAlarms.length} 条未解决告警关联 ${activeMissions.length} 个活动 Mission。`,
            `${missionStatuses["under-review"] ?? 0} 个 Mission 等待人工审核，${missionStatuses.executing ?? 0} 个正在执行。`,
            `WT-023 工作流状态为 ${missionStatusLabel}；决策 ${decisionStatusLabel}；工单 ${workOrderStatusLabel}。`,
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
      typeLabel: "告警分析",
      title: "告警分析报告",
      subtitle: "严重度分布、未解决队列与告警到 Mission 的追溯关系",
      period: "daily",
      periodLabel: "2026 年 8 月 13 日",
      periodStart: "2026-08-13T00:00:00+08:00",
      periodEnd: "2026-08-13T23:59:59+08:00",
      ownerAgent: "SCADA 分析 Agent",
      assetScope: `${windFarm.code} / 全场告警`,
      highlight: `仍有 ${unresolvedAlarms.length} 条未解决告警；WT-023 的三项关联信号已汇总到一个 Mission。`,
      tags: ["告警", "严重度", "关联分析", "WT-023"],
      metrics: [
        {
          label: "未解决",
          value: `${unresolvedAlarms.length}`,
          context: `${alarms.length} 条实时告警记录`,
          tone: "attention",
        },
        {
          label: "严重 / 重要",
          value: `${(alarmSeverities.critical ?? 0) + (alarmSeverities.major ?? 0)}`,
          context: "优先响应队列",
          tone: "critical",
        },
        {
          label: "AI 已创建行动",
          value: `${alarms.filter((alarm) => alarm.aiStatus === "action-created").length}`,
          context: "告警到行动的转化",
          tone: "positive",
        },
        {
          label: "WT-023 证据",
          value: `${evidenceItems.filter((item) => item.turbineId === "WT-023").length}`,
          context: "可追溯证据项",
          tone: "neutral",
        },
      ],
      sections: [
        {
          heading: "严重度与队列",
          summary: "实时队列主要由需要采取行动的警告和重要信号构成。",
          findings: [
            `严重度统计：严重 ${alarmSeverities.critical ?? 0}，重要 ${alarmSeverities.major ?? 0}，次要 ${alarmSeverities.minor ?? 0}，警告 ${alarmSeverities.warning ?? 0}。`,
            `${alarms.filter((alarm) => alarm.status === "acknowledged").length} 条告警已确认。`,
            `${alarms.filter((alarm) => alarm.missionId !== null).length} 条告警记录保留 Mission 关联。`,
          ],
        },
        {
          heading: "WT-023 关联案例",
          summary: "创建 Mission 前已关联振动、温度与功率波动。",
          findings: [
            "主轴承振动达到 4.81 mm/s，超过 4.50 mm/s 阈值。",
            "温度较归一化运行基线高 8.4°C。",
            `关联案例由 ${snapshot.mission.id} 管理，当前状态为 ${missionStatusLabel}。`,
          ],
        },
      ],
      linkedEntityIds: ["ALARM-0031", "ALARM-0032", "ALARM-0033", snapshot.mission.id],
    },
    {
      ...common,
      id: "RPT-AI-WT023-20260813",
      type: "ai-diagnosis",
      typeLabel: "AI 诊断",
      title: "AI 诊断报告",
      subtitle: "基于证据的多 Agent 诊断与受控建议",
      period: "incident",
      periodLabel: "WT-023 事件 / 2026 年 8 月 13 日",
      periodStart: featuredMission.createdAt,
      periodEnd: generatedAt,
      ownerAgent: "故障诊断 Agent",
      assetScope: `WT-023 / ${snapshot.mission.id}`,
      highlight: `主轴承早期退化诊断置信度为 ${featuredMission.confidencePercent ?? 0}%；高风险执行仍受人工审批约束。`,
      tags: ["AI", "诊断", "证据", "人工门禁", "WT-023"],
      metrics: [
        {
          label: "诊断置信度",
          value: `${featuredMission.confidencePercent ?? 0}%`,
          context: "重点 Mission 评估",
          tone: "attention",
        },
        {
          label: "支持证据",
          value: `${featuredMission.evidenceIds.length}`,
          context: "SCADA、CMS、模型、历史与资源",
          tone: "positive",
        },
        {
          label: "已诊断 Mission",
          value: `${diagnosedMissions.length}`,
          context: `平均置信度 ${averageConfidence.toFixed(1)}%`,
          tone: "neutral",
        },
        {
          label: "人工门禁",
          value: decisionStatusLabel,
          context: snapshot.decision.approval ? "已记录审批" : "等待审批",
          tone: snapshot.decision.approval ? "positive" : "attention",
        },
      ],
      sections: [
        {
          heading: "证据汇总",
          summary: "独立的信号、频谱、历史与资源证据支持该诊断。",
          findings: [
            "主轴承振动 RMS 在连续 44 个采样点中从 3.79 升至 4.81 mm/s，增幅 27%。",
            "BPFO 频带能量增加 19%，符合外圈退化模式。",
            "最相似历史案例匹配分为 0.91；厂家规程要求告警后 72 小时内完成人工复检。",
          ],
        },
        {
          heading: "受控建议",
          summary: "推荐措施综合权衡退化风险、安全通行与发电损失。",
          findings: [
            "推荐行动：降载至 70%，提高采样频率，并在天气窗口内检查。",
            `决策状态为 ${decisionStatusLabel}；未记录人工门禁前不得执行高风险现场作业。`,
            `工作流修订 ${snapshot.revision} 是报告的权威状态来源。`,
          ],
        },
      ],
      linkedEntityIds: [snapshot.mission.id, snapshot.decision.id, ...featuredMission.evidenceIds],
    },
    {
      ...common,
      id: "RPT-MAINT-20260813",
      type: "maintenance",
      typeLabel: "维护",
      title: "维护报告",
      subtitle: "工单准备度、执行状态、资源与历史完工记录",
      period: "snapshot",
      periodLabel: "维护快照 / 2026年8月13日",
      periodStart: "2026-08-13T00:00:00+08:00",
      periodEnd: generatedAt,
      ownerAgent: "工单 Agent",
      assetScope: `${windFarm.code} / 维护工单组合`,
      highlight: `可追溯 ${currentWorkOrders.length} 条当前工单与 ${historicalWorkOrders.length} 条历史工单；WT-023 当前为 ${workOrderStatusLabel}。`,
      tags: ["maintenance", "work-order", "resources", "safety", "WT-023"],
      metrics: [
        {
          label: "当前工单",
          value: `${currentWorkOrders.length}`,
          context: `${workOrderStatuses["in-progress"] ?? 0} 条执行中`,
          tone: "neutral",
        },
        {
          label: "历史台账",
          value: `${historicalWorkOrders.length}`,
          context: `${completedOrders.length} 条已完成或关闭`,
          tone: "positive",
        },
        {
          label: "WT-023 任务",
          value: `${snapshot.workOrder.completedTaskCount}/${snapshot.workOrder.totalTaskCount}`,
          context: `工单状态：${workOrderStatusLabel}`,
          tone: snapshot.workOrder.status === "completed" ? "positive" : "attention",
        },
        {
          label: "预留资源包",
          value: "班组 + CTV + 工具",
          context: "受天气窗口约束",
          tone: "positive",
        },
      ],
      sections: [
        {
          heading: "工单组合态势",
          summary: "当前工单持续关联 Mission、决策、安全要求与资源。",
          findings: [
            `状态分布：${workOrderStatuses.draft ?? 0} 条草稿、${workOrderStatuses.scheduled ?? 0} 条已排程、${workOrderStatuses["in-progress"] ?? 0} 条执行中。`,
            `${currentWorkOrders.filter((order) => order.createdByAgentId !== null).length} 条当前工单由 Agent 创建。`,
            `${failureCases.length} 个闭环故障案例支持相似性规划。`,
          ],
        },
        {
          heading: "WT-023 现场作业包",
          summary: "主轴承检查作业包保留人工门禁与五项明确任务。",
          findings: [
            `工单 ${featuredWorkOrder.id} 当前为 ${workOrderStatusLabel}，已完成 ${snapshot.workOrder.completedTaskCount}/${snapshot.workOrder.totalTaskCount} 项任务。`,
            `执行班组：${featuredWorkOrder.assignedTeam}；预计工期 ${featuredWorkOrder.estimatedDurationHours} 小时。`,
            `已记录 ${featuredWorkOrder.ppeRequirements.length} 项 PPE 要求、${featuredWorkOrder.requiredTools.length} 项工具和 ${featuredWorkOrder.safetyProcedures.length} 项安全程序。`,
          ],
        },
      ],
      linkedEntityIds: [snapshot.workOrder.id, snapshot.mission.id, snapshot.decision.id],
    },
    {
      ...common,
      id: "RPT-HEALTH-20260813",
      type: "asset-health",
      typeLabel: "资产健康",
      title: "资产健康报告",
      subtitle: "全场健康分布、趋势信号与干预优先级",
      period: "snapshot",
      periodLabel: "健康快照 / 2026年8月13日",
      periodStart: "2026-08-13T00:00:00+08:00",
      periodEnd: generatedAt,
      ownerAgent: "预测维护 Agent",
      assetScope: `${windFarm.code} / ${turbines.length} 台风机`,
      highlight: `${elevatedHealthRisk.length} 台风机的状态风险为高或严重；WT-023 健康度为 ${snapshot.health.turbineScore}。`,
      tags: ["health", "risk", "anomaly", "trend", "WT-023"],
      metrics: [
        {
          label: "全场健康度",
          value: `${windFarm.averageHealthScore.toFixed(1)}`,
          context: "平均分 / 100",
          tone: "positive",
        },
        {
          label: "较高风险",
          value: `${elevatedHealthRisk.length}`,
          context: "状态证据高风险或严重风险",
          tone: "critical",
        },
        {
          label: "下降趋势",
          value: `${decliningHealth.length}`,
          context: "需要趋势复核的资产",
          tone: "attention",
        },
        {
          label: "WT-023 主轴承",
          value: `${snapshot.health.mainBearingScore}`,
          context: `机组健康度 ${snapshot.health.turbineScore}`,
          tone: snapshot.health.mainBearingScore >= 75 ? "positive" : "critical",
        },
      ],
      sections: [
        {
          heading: "全场健康分布",
          summary: "已汇总全部 64 台风机的健康评分、异常分数与告警状态。",
          findings: [
            `${currentHealth.filter((item) => item.state === "healthy").length} 台资产健康，${currentHealth.filter((item) => item.state === "degraded" || item.state === "critical").length} 台处于退化或严重状态。`,
            `${decliningHealth.length} 台资产在确定性快照中呈下降趋势。`,
            `全场最高异常分数为 ${Math.max(...currentHealth.map((item) => item.anomalyScore)).toFixed(2)}。`,
          ],
        },
        {
          heading: "WT-023 健康状态叠加",
          summary: "报告反映当前服务端工作流，包括闭环后的维护恢复。",
          findings: [
            `机组健康度为 ${snapshot.health.turbineScore}；主轴承健康度为 ${snapshot.health.mainBearingScore}。`,
            `Mission ${snapshot.mission.id} 当前为 ${missionStatusLabel}；工单 ${snapshot.workOrder.id} 当前为 ${workOrderStatusLabel}。`,
            snapshot.knowledgeCaseId
              ? `闭环知识案例 ${snapshot.knowledgeCaseId} 已可用。`
              : "现场工作流完成前，知识沉淀保持待处理。",
          ],
        },
      ],
      linkedEntityIds: [snapshot.turbineId, snapshot.mission.id, snapshot.workOrder.id],
    },
    {
      ...common,
      id: "RPT-WEEKLY-2026W33",
      type: "weekly-wind-farm",
      typeLabel: "风场周报",
      title: "风场运营周报",
      subtitle: "华东海上风场管理层运营摘要",
      period: "weekly",
      periodLabel: "2026年8月10日–16日 / 第33周",
      periodStart: "2026-08-10T00:00:00+08:00",
      periodEnd: "2026-08-16T23:59:59+08:00",
      ownerAgent: "运营协调 Agent",
      assetScope: windFarm.name,
      highlight: `384 MW 风场保持运行，平均可利用率为 ${averageAvailability.toFixed(1)}%；WT-023 为本周重点受控干预案例。`,
      tags: ["weekly", "executive", "wind-farm", "KPI", "WT-023"],
      metrics: [
        {
          label: "装机容量",
          value: `${windFarm.totalCapacityMW} MW`,
          context: `${windFarm.turbineCount} × 6.0 MW`,
          tone: "neutral",
        },
        {
          label: "平均可利用率",
          value: `${averageAvailability.toFixed(1)}%`,
          context: "确定性全场均值",
          tone: "positive",
        },
        {
          label: "活动 Mission",
          value: `${activeMissions.length}`,
          context: `共 ${currentMissions.length} 条 Mission 记录`,
          tone: "attention",
        },
        {
          label: "闭环案例",
          value: `${failureCases.length}`,
          context: "历史故障知识",
          tone: "positive",
        },
      ],
      sections: [
        {
          heading: "管理层摘要",
          summary: "全场出力与可利用率保持稳定，AI 辅助关注集中在少量重点资产。",
          findings: [
            `${windFarm.operatingTurbines} 台风机运行中，${windFarm.maintenanceTurbines} 台维护中，${windFarm.offlineTurbines} 台离线。`,
            `当前功率 ${windFarm.currentPowerMW.toFixed(1)} MW，快照时今日发电量 ${windFarm.todayGenerationGWh.toFixed(2)} GWh。`,
            `${activeMissions.length} 个 Mission 处于活动状态，并保留与底层告警及工单的关联。`,
          ],
        },
        {
          heading: "风险与干预重点",
          summary: "周度复盘强调受控干预，不允许自主执行高风险操作。",
          findings: [
            `${elevatedHealthRisk.length} 台风机处于模型高风险或严重风险区间。`,
            `WT-023 的 Mission 状态为 ${missionStatusLabel}，决策状态为 ${decisionStatusLabel}，工单状态为 ${workOrderStatusLabel}。`,
            `审计修订 ${snapshot.revision} 与 ${snapshot.auditEvents.length} 条工作流事件支撑报告追溯。`,
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
  catalog: readonly OpenVigilReport[],
  reportId: string,
): OpenVigilReport | undefined =>
  catalog.find((report) => report.id === reportId.trim().toUpperCase());

export function reportToPlainText(report: OpenVigilReport): readonly string[] {
  return [
    report.title,
    report.subtitle,
    "",
    `报告编号：${report.id}`,
    `类型：${report.typeLabel}`,
    `周期：${report.periodLabel}`,
    `生成时间：${report.generatedAt}`,
    `负责人：${report.ownerAgent}`,
    `资产范围：${report.assetScope}`,
    "",
    "执行摘要",
    report.highlight,
    "",
    "关键指标",
    ...report.metrics.map((metric) => `${metric.label}: ${metric.value} - ${metric.context}`),
    "",
    ...report.sections.flatMap((section) => [
      section.heading.toUpperCase(),
      section.summary,
      ...section.findings.map((finding) => `- ${finding}`),
      "",
    ]),
    "工作流追溯",
    `WT-023 Mission=${localizedStatusLabel(report.workflow.missionStatus)}；决策=${localizedStatusLabel(report.workflow.decisionStatus)}；工单=${localizedStatusLabel(report.workflow.workOrderStatus)}`,
    `任务=${report.workflow.completedTaskCount}/${report.workflow.totalTaskCount}；健康度=${report.workflow.healthScore}；主轴承=${report.workflow.mainBearingHealthScore}；修订=${report.workflow.revision}`,
    `关联实体：${report.linkedEntityIds.join(", ")}`,
    "",
    "基于 OpenVigil 确定性演示数据生成，并叠加权威服务端工作流状态。",
  ];
}
