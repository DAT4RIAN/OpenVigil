"use client";

import {
  Activity,
  TriangleAlert as AlarmTriangle,
  ArrowRight,
  Bot,
  CalendarDays,
  CheckCircle2,
  CircleGauge,
  Clock3,
  Download,
  Radio,
  ShieldCheck,
  TowerControl,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";
import Link from "next/link";

import { TimeSeriesChart, type TimeSeriesPoint } from "@/components/charts/time-series-chart";
import { MetricCard } from "@/components/data-display/metric-card";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, Progress } from "@/components/ui/primitives";
import { agentDisplayName } from "@/lib/agent-control-meta";
import { agents } from "@/lib/agent-data";
import {
  deriveWorkflowKpis,
  overlayClientAgents,
  overlayClientAlarms,
  overlayClientMissions,
  overlayClientTurbines,
} from "@/lib/client-workflow-overlays";
import { getCurrentWorkflowAuditCycle } from "@/lib/demo-workflow";
import type { DemoWorkflowEvent } from "@/lib/demo-workflow";
import { turbines, windFarm } from "@/lib/farm-data";
import { activityEvents, alarms, featuredMission, missions } from "@/lib/operations-data";
import { weatherWindows, scadaSeries } from "@/lib/telemetry-data";
import type { ActivityEvent, Mission } from "@/lib/types";
import { localizedMissionTitle, localizedSeverityLabel } from "@/lib/ui-localization";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";

import { DashboardIncidentStrip, formatDurationMinutes, formatTime } from "./dashboard-shared";

const missionLabels: Record<Mission["status"], string> = {
  detected: "已发现",
  investigating: "分析中",
  diagnosed: "已诊断",
  "decision-pending": "待决策",
  "under-review": "审核中",
  approved: "已批准",
  executing: "执行中",
  rejected: "已拒绝",
  completed: "已完成",
};

const activityIcons: Record<ActivityEvent["kind"], typeof Activity> = {
  detection: AlarmTriangle,
  analysis: Activity,
  retrieval: Radio,
  diagnosis: CircleGauge,
  decision: ShieldCheck,
  review: ShieldCheck,
  approval: CheckCircle2,
  "work-order": CalendarDays,
  execution: TowerControl,
  system: Bot,
};

const workflowActivityKinds: Record<DemoWorkflowEvent["kind"], ActivityEvent["kind"]> = {
  replay: "system",
  approval: "approval",
  execution: "execution",
  verification: "review",
  knowledge: "retrieval",
};

function currentWorkflowActivity(events: readonly DemoWorkflowEvent[]): ActivityEvent[] {
  return getCurrentWorkflowAuditCycle(events)
    .map((event) => ({
      id: event.id,
      missionId: featuredMission.id,
      timestamp: event.timestamp,
      agentId: null,
      actorLabel: event.actor,
      kind: workflowActivityKinds[event.kind],
      title: event.title,
      detail: event.detail,
      evidenceIds: [],
      outcome:
        event.kind === "replay"
          ? ("attention" as const)
          : event.kind === "execution"
            ? ("in-progress" as const)
            : ("success" as const),
    }))
    .reverse();
}

const powerRanges = ["1H", "6H", "24H", "7D"] as const;

type PowerRange = (typeof powerRanges)[number];

const powerRangePointCounts: Record<Exclude<PowerRange, "7D">, number> = {
  "1H": 5,
  "6H": 25,
  "24H": 97,
};

function chartData(range: PowerRange): TimeSeriesPoint[] {
  const power = scadaSeries.find((series) => series.metric === "active-power");
  if (!power) return [];

  const allPoints = power.points.map((point, index) => ({
    timestamp: new Date(point.timestamp).toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }),
    value: Number((point.value * (58.4 + Math.sin(index / 5) * 0.7)).toFixed(1)),
    anomaly: point.isAnomaly,
    aiEvent: Boolean(point.aiEvent),
  }));

  if (range !== "7D") {
    return allPoints.slice(-powerRangePointCounts[range]);
  }

  const bucketSize = Math.ceil(allPoints.length / 7);
  const endDate = new Date(power.points.at(-1)?.timestamp ?? windFarm.lastUpdatedAt);

  return Array.from({ length: 7 }, (_, index) => {
    const bucket = allPoints.slice(
      index * bucketSize,
      Math.min((index + 1) * bucketSize, allPoints.length),
    );
    const bucketDate = new Date(endDate);
    bucketDate.setDate(endDate.getDate() - (6 - index));

    return {
      timestamp: bucketDate.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }),
      value: Number(
        (bucket.reduce((total, point) => total + point.value, 0) / bucket.length).toFixed(1),
      ),
      anomaly: bucket.some((point) => point.anomaly),
      aiEvent: bucket.some((point) => point.aiEvent),
    };
  });
}

export function DemoDashboardPage() {
  const workflow = useDemoWorkflow();
  const [powerRange, setPowerRange] = useState<PowerRange>("24H");
  const powerChartData = useMemo(() => chartData(powerRange), [powerRange]);
  const displayTurbines = useMemo(() => overlayClientTurbines(turbines, workflow), [workflow]);
  const displayAlarms = useMemo(() => overlayClientAlarms(alarms, workflow), [workflow]);
  const displayMissions = useMemo(() => overlayClientMissions(missions, workflow), [workflow]);
  const displayAgents = useMemo(() => overlayClientAgents(agents, workflow), [workflow]);
  const workflowKpis = useMemo(
    () => deriveWorkflowKpis(displayTurbines, displayAlarms, displayMissions, displayAgents),
    [displayAgents, displayAlarms, displayMissions, displayTurbines],
  );
  const running = displayTurbines.filter((turbine) => turbine.status === "running").length;
  const operating = displayTurbines.filter(
    (turbine) => !["maintenance", "offline", "communication-lost"].includes(turbine.status),
  ).length;
  const offline = displayTurbines.filter(
    (turbine) => turbine.status === "offline" || turbine.status === "communication-lost",
  ).length;
  const faulted = displayTurbines.filter((turbine) => turbine.status === "critical").length;
  const activeAgents = workflowKpis.activeAgentCount;
  const criticalAlarms = displayAlarms
    .filter(
      (alarm) =>
        alarm.status !== "resolved" &&
        (alarm.severity === "critical" || alarm.severity === "major"),
    )
    .sort(
      (left, right) =>
        (left.severity === "critical" ? 0 : 1) - (right.severity === "critical" ? 0 : 1) ||
        right.durationMinutes - left.durationMinutes ||
        left.id.localeCompare(right.id),
    )
    .slice(0, 4);
  const activeMissions = displayMissions
    .filter((mission) => mission.status !== "completed")
    .slice(0, 4);
  const baselineActivity = activityEvents.filter(
    (event) =>
      event.missionId === featuredMission.id &&
      event.kind !== "approval" &&
      event.kind !== "work-order" &&
      event.kind !== "execution",
  );
  const latestActivity = [
    ...currentWorkflowActivity(workflow.auditTrail),
    ...baselineActivity.slice(-6).reverse(),
  ].slice(0, 6);
  const statusSummary = [
    { label: "运行", value: running, tone: "success" },
    {
      label: "预警",
      value: displayTurbines.filter((turbine) => turbine.status === "warning").length,
      tone: "warning",
    },
    { label: "故障", value: faulted, tone: "critical" },
    {
      label: "维护",
      value: displayTurbines.filter((turbine) => turbine.status === "maintenance").length,
      tone: "maintenance",
    },
    { label: "离线", value: offline, tone: "offline" },
  ];
  const highestPriorityAlarm = criticalAlarms[0];
  const incidentTurbine = highestPriorityAlarm
    ? displayTurbines.find((turbine) => turbine.id === highestPriorityAlarm.turbineId)
    : undefined;
  const incidentMission = highestPriorityAlarm?.missionId
    ? displayMissions.find((mission) => mission.id === highestPriorityAlarm.missionId)
    : undefined;

  const downloadDailyReport = () => {
    const unresolvedAlarms = displayAlarms.filter((alarm) => alarm.status !== "resolved").length;
    const reportRows = [
      ["OpenVigil 华东海上风电场运行日报", "2026-08-13", "白班"],
      ["指标", "数值", "单位"],
      ["当前功率", windFarm.currentPowerMW.toFixed(1), "MW"],
      ["今日发电量", windFarm.todayGenerationGWh.toFixed(2), "GWh"],
      ["并网运行机组", String(operating), "台"],
      ["未闭环告警", String(unresolvedAlarms), "条"],
      ["活跃 Missions", String(workflowKpis.activeMissionCount), "个"],
      ["平均健康度", workflowKpis.averageHealth.toFixed(1), "%"],
      ["重点事件", "WT-023 主轴承振动异常", missionLabels[workflow.missionStatus]],
    ];
    const csv = reportRows
      .map((row) => row.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(","))
      .join("\r\n");
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "openvigil-daily-report-2026-08-13.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AppShell runtimeMode="demo" activePath="/">
      <PageHeader
        eyebrow="实时运行态势"
        title="运营指挥中心"
        description="华东海上风电场 · 64 台机组的实时状态、风险事件与 AI 运维进程"
        meta={
          <>
            <StatusBadge value="running" label="全场数据正常" tone="success" pulse />
            <span className="page-meta-text">2026年8月13日 星期四 · 白班</span>
            <Link className="page-meta-text" href="/wind-farms">
              查看风场
            </Link>
          </>
        }
        actions={
          <>
            <Button
              type="button"
              variant="secondary"
              title="打开工单排程"
              onClick={() => window.location.assign("/work-orders")}
            >
              <CalendarDays size={15} /> 运行日历
            </Button>
            <Button type="button" variant="primary" onClick={downloadDailyReport}>
              <Download size={15} /> 生成日报
            </Button>
          </>
        }
      />

      <DashboardIncidentStrip
        stable={!highestPriorityAlarm}
        priority={highestPriorityAlarm?.severity === "critical" ? "P1" : "P2"}
        eyebrow={highestPriorityAlarm ? "最高优先级 · 需要处置" : "当前稳定 · 无高优事件"}
        title={highestPriorityAlarm?.title ?? "当前没有需要立即处置的事件"}
        context={
          highestPriorityAlarm
            ? `${highestPriorityAlarm.turbineId} · ${highestPriorityAlarm.code} · 已持续 ${formatDurationMinutes(Math.max(1, Math.round(highestPriorityAlarm.durationMinutes)))}`
            : `截至 ${new Date(windFarm.lastUpdatedAt).toLocaleString("zh-CN")}，当前范围没有高优先级告警`
        }
        aiStatus={incidentMission ? missionLabels[incidentMission.status] : "尚未关联 Mission"}
        healthValue={incidentTurbine ? `${incidentTurbine.healthScore.toFixed(1)}%` : "—"}
        anomalyValue={
          highestPriorityAlarm?.currentValue != null && highestPriorityAlarm.unit
            ? `${highestPriorityAlarm.currentValue.toFixed(2)} ${highestPriorityAlarm.unit}`
            : "—"
        }
        freshness={formatTime(windFarm.lastUpdatedAt)}
        actionHref={incidentMission ? `/missions/${incidentMission.id}` : "/alarms"}
        actionLabel={incidentMission ? "进入 Mission" : "查看全部告警"}
      />

      <section className="metrics-grid" aria-label="关键运行指标">
        <MetricCard
          label="当前功率"
          value={windFarm.currentPowerMW.toFixed(1)}
          unit="MW"
          change={4.8}
          changeLabel="较上一小时"
          icon={<Zap size={15} />}
          tone="info"
        />
        <MetricCard
          label="24h 电量"
          value={windFarm.todayGenerationGWh.toFixed(2)}
          unit="GWh"
          change={2.1}
          changeLabel="较昨日同期"
          icon={<Activity size={15} />}
        />
        <MetricCard
          label="运行机组"
          value={`${operating} / 64`}
          detail={`${running} 台正常 · ${displayTurbines.length - operating - offline} 台维护`}
          icon={<TowerControl size={15} />}
          tone="success"
        />
        <MetricCard
          label="平均健康度"
          value={workflowKpis.averageHealth.toFixed(1)}
          unit="%"
          change={-0.6}
          changeLabel="过去 7 日"
          icon={<CircleGauge size={15} />}
          tone="warning"
        />
        <MetricCard
          label="活跃告警"
          value={String(workflowKpis.activeAlarmCount)}
          detail={`${criticalAlarms.length} 条高优先级`}
          icon={<AlarmTriangle size={15} />}
          tone="critical"
        />
        <MetricCard
          label="活跃 Missions"
          value={String(workflowKpis.activeMissionCount)}
          detail={`${activeAgents} 个 Agent 活跃`}
          icon={<Bot size={15} />}
          tone="info"
        />
      </section>

      <section className="dashboard-main-grid">
        <Card className="panel panel--power">
          <CardHeader
            eyebrow={`SCADA · ${powerRange}`}
            title="全场有功功率"
            description="汇总功率曲线与 WT-023 AI 事件标记"
            action={
              <div className="segmented" aria-label="功率趋势时间窗口">
                {powerRanges.map((range) => (
                  <button
                    type="button"
                    className={powerRange === range ? "active" : undefined}
                    aria-pressed={powerRange === range}
                    onClick={() => setPowerRange(range)}
                    key={range}
                  >
                    {range}
                  </button>
                ))}
              </div>
            }
          />
          <div className="chart-stat-row">
            <span>
              <small>当前输出</small>
              <strong>{windFarm.currentPowerMW.toFixed(1)} MW</strong>
            </span>
            <span>
              <small>预测偏差</small>
              <strong className="positive">+1.7%</strong>
            </span>
            <span>
              <small>可利用率</small>
              <strong>96.8%</strong>
            </span>
            <span className="chart-legend">
              <i className="legend-dot legend-dot--anomaly" />
              异常点 <i className="legend-dot legend-dot--ai" />
              AI 事件
            </span>
          </div>
          <TimeSeriesChart
            data={powerChartData}
            height={250}
            primaryName="全场有功功率"
            unit="MW"
            threshold={365}
          />
        </Card>

        <Card className="panel panel--priority">
          <CardHeader
            eyebrow="需要关注"
            title="优先处置队列"
            description="按风险与持续时间排序"
            action={
              <a className="text-link" href="/alarms">
                告警中心 <ArrowRight size={12} />
              </a>
            }
          />
          <div className="compact-list">
            {criticalAlarms.map((alarm) => (
              <a className="compact-row alarm-row" href="/alarms" key={alarm.id}>
                <span className={`severity-rail severity-rail--${alarm.severity}`} />
                <span className="compact-row__main">
                  <strong>{alarm.title}</strong>
                  <small>
                    <span className="mono">{alarm.turbineId}</span> · {alarm.code}
                  </small>
                  <small>
                    负责人：{alarm.assignee ?? (alarm.missionId ? "关联 Mission 团队" : "值班调度")}
                  </small>
                </span>
                <span className="compact-row__meta">
                  <StatusBadge value={alarm.severity} compact />
                  <small>{Math.max(1, Math.round(alarm.durationMinutes / 60))}h</small>
                </span>
              </a>
            ))}
          </div>
          <div className="priority-fleet-context">
            <span>{statusSummary.map((item) => `${item.label} ${item.value}`).join(" · ")}</span>
            <span>可利用率 96.8%</span>
          </div>
        </Card>
      </section>

      <section className="dashboard-lower-grid">
        <Card className="panel panel--missions">
          <CardHeader
            eyebrow="多 Agent 协作"
            title="活跃 Missions"
            description="诊断、审核与执行进度"
            action={
              <Link className="text-link" href="/missions">
                Mission 中心 <ArrowRight size={12} />
              </Link>
            }
          />
          <div className="mission-list">
            {activeMissions.map((mission) => (
              <a className="mission-list-row" href={`/missions/${mission.id}`} key={mission.id}>
                <span className="mission-priority" data-risk={mission.severity}>
                  {localizedSeverityLabel(mission.severity).slice(0, 1)}
                </span>
                <span className="mission-list-row__copy">
                  <strong>{localizedMissionTitle(mission.title)}</strong>
                  <small>
                    <span className="mono">{mission.turbineId}</span> ·{" "}
                    {missionLabels[mission.status]}
                  </small>
                </span>
                <span className="mission-list-row__progress">
                  <span>{mission.progressPercent}%</span>
                  <Progress
                    value={mission.progressPercent}
                    tone={
                      mission.severity === "critical" || mission.severity === "high"
                        ? "warning"
                        : "info"
                    }
                  />
                </span>
              </a>
            ))}
          </div>
        </Card>

        <Card className="panel panel--activity">
          <CardHeader
            eyebrow="Agent 实时活动"
            title="WT-023 协作时间线"
            description="仅显示结构化执行摘要，不展示隐藏推理"
            action={
              <StatusBadge
                value="working"
                label={`${activeAgents} 个 Agent 活跃`}
                tone="info"
                pulse
                compact
              />
            }
          />
          <div className="activity-stream">
            {latestActivity.map((event) => {
              const Icon = activityIcons[event.kind];
              const agent = event.agentId ? agents.find((item) => item.id === event.agentId) : null;
              return (
                <div className="activity-event" key={event.id}>
                  <span className={`activity-event__icon activity-event__icon--${event.outcome}`}>
                    <Icon size={14} />
                  </span>
                  <span className="activity-event__copy">
                    <strong>{event.title}</strong>
                    <small>{event.detail}</small>
                    <span>
                      {agent
                        ? agentDisplayName(agent.id, agent.shortName)
                        : agentDisplayName(event.agentId ?? "", event.actorLabel)}
                    </span>
                  </span>
                  <time>{formatTime(event.timestamp)}</time>
                </div>
              );
            })}
          </div>
          <a className="panel-footer-link" href={`/missions/${featuredMission.id}`}>
            查看完整协作过程 <ArrowRight size={13} />
          </a>
        </Card>

        <Card className="panel panel--window">
          <CardHeader
            eyebrow="海上作业窗口"
            title="下一可用作业窗口"
            description="气象与船舶作业条件"
          />
          {weatherWindows.slice(0, 2).map((window) => (
            <div className="weather-window" key={window.id}>
              <span className="weather-window__date">
                <strong>
                  {new Date(window.startsAt).toLocaleDateString("zh-CN", {
                    month: "short",
                    day: "numeric",
                  })}
                </strong>
                <small>
                  {new Date(window.startsAt).toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  })}
                  –
                  {new Date(window.endsAt).toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  })}
                </small>
              </span>
              <span className="weather-window__conditions">
                <strong>{window.windSpeedMps} m/s</strong>
                <small>浪高 {window.waveHeightM} m</small>
              </span>
              <StatusBadge
                value={window.suitability}
                label={
                  window.suitability === "suitable"
                    ? "适合作业"
                    : window.suitability === "conditional"
                      ? "条件作业"
                      : "不可作业"
                }
                tone={
                  window.suitability === "suitable"
                    ? "success"
                    : window.suitability === "conditional"
                      ? "warning"
                      : "critical"
                }
                compact
              />
            </div>
          ))}
          <div className="resource-check">
            <Clock3 size={14} />
            <span>
              <strong>方案 B 已匹配 8 月 14 日窗口</strong>
              <small>船舶、工程师与备件均已确认</small>
            </span>
          </div>
        </Card>
      </section>
    </AppShell>
  );
}
