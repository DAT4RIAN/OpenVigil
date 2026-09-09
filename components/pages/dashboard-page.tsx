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
  Wind,
  Zap,
} from "lucide-react";
import { useMemo, useState, type CSSProperties } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import Link from "next/link";
import { Card, CardHeader, Progress, Button } from "@/components/ui/primitives";
import { MetricCard } from "@/components/data-display/metric-card";
import { StatusBadge } from "@/components/data-display/status-badge";
import { TimeSeriesChart, type TimeSeriesPoint } from "@/components/charts/time-series-chart";
import {
  activityEvents,
  agents,
  alarms,
  featuredMission,
  getCurrentWorkflowAuditCycle,
  missions,
  scadaSeries,
  turbines,
  weatherWindows,
  windFarm,
} from "@/lib";
import type { ActivityEvent, Mission } from "@/lib/types";
import type { DemoWorkflowEvent } from "@/lib/demo-workflow";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";

const missionLabels: Record<Mission["status"], string> = {
  detected: "已发现",
  investigating: "分析中",
  diagnosed: "已诊断",
  "decision-pending": "待决策",
  "under-review": "审核中",
  approved: "已批准",
  executing: "执行中",
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

function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function DashboardPage() {
  const workflow = useDemoWorkflow();
  const [powerRange, setPowerRange] = useState<PowerRange>("24H");
  const powerChartData = useMemo(() => chartData(powerRange), [powerRange]);
  const running = turbines.filter((turbine) => turbine.status === "running").length;
  const operating = turbines.filter(
    (turbine) => !["maintenance", "offline", "communication-lost"].includes(turbine.status),
  ).length;
  const offline = turbines.filter(
    (turbine) => turbine.status === "offline" || turbine.status === "communication-lost",
  ).length;
  const faulted = turbines.filter((turbine) => turbine.status === "critical").length;
  const activeAgents = agents.filter((agent) =>
    ["working", "thinking", "reviewing"].includes(agent.status),
  ).length;
  const criticalAlarms = alarms
    .filter((alarm) => alarm.severity === "critical" || alarm.severity === "major")
    .slice(0, 4);
  const displayMissions = missions.map((mission) =>
    mission.id === featuredMission.id
      ? { ...mission, status: workflow.missionStatus, progressPercent: workflow.missionProgress }
      : mission,
  );
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
      value: turbines.filter((turbine) => turbine.status === "warning").length,
      tone: "warning",
    },
    { label: "故障", value: faulted, tone: "critical" },
    {
      label: "维护",
      value: turbines.filter((turbine) => turbine.status === "maintenance").length,
      tone: "maintenance",
    },
    { label: "离线", value: offline, tone: "offline" },
  ];

  const downloadDailyReport = () => {
    const unresolvedAlarms = alarms.filter((alarm) => alarm.status !== "resolved").length;
    const reportRows = [
      ["WindOps 华东海上风电场运行日报", "2026-08-13", "白班"],
      ["指标", "数值", "单位"],
      ["当前功率", windFarm.currentPowerMW.toFixed(1), "MW"],
      ["今日发电量", windFarm.todayGenerationGWh.toFixed(2), "GWh"],
      ["并网运行机组", String(operating), "台"],
      ["未闭环告警", String(unresolvedAlarms), "条"],
      ["活跃 Missions", String(windFarm.activeMissionCount), "个"],
      ["平均健康度", windFarm.averageHealthScore.toFixed(1), "%"],
      ["重点事件", "WT-023 主轴承振动异常", missionLabels[workflow.missionStatus]],
    ];
    const csv = reportRows
      .map((row) => row.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(","))
      .join("\r\n");
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "windops-daily-report-2026-08-13.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AppShell activePath="/">
      <PageHeader
        eyebrow="实时运行态势"
        title="Operations Command Center"
        description="华东海上风电场 · 64 台机组的实时状态、风险事件与 AI 运维进程"
        meta={
          <>
            <StatusBadge value="running" label="全场数据正常" tone="success" pulse />
            <span className="page-meta-text">2026年8月13日 星期四 · 白班</span>
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

      <section className="command-strip" aria-label="当前重点事件">
        <div className="command-strip__status">
          <span className="command-strip__status-icon">
            <Wind size={20} />
          </span>
          <span>
            <small>FLEET STATUS</small>
            <strong>全场运行总体稳定</strong>
          </span>
          <span className="command-strip__reading">
            <strong>{operating} / 64</strong>
            <small>机组并网运行</small>
          </span>
        </div>
        <div className="command-strip__incident">
          <span className="incident-index">P1</span>
          <span className="incident-copy">
            <small>
              {workflow.missionStatus === "completed"
                ? "闭环已完成 · 结果已验证"
                : "AI 正在处理 · 02:14 触发"}
            </small>
            <strong>WT-023 主轴承振动异常</strong>
            <span>
              {workflow.missionStatus === "completed"
                ? `健康度 ${workflow.mainBearingHealthScore} · ${workflow.knowledgeCaseId} 已沉淀`
                : "振动 +27% · 温度 +8.4°C · 退化概率 87%"}
            </span>
          </span>
          <span className="incident-progress">
            <span>
              <small>{missionLabels[workflow.missionStatus]}</small>
              <strong>{workflow.missionProgress}%</strong>
            </span>
            <Progress
              value={workflow.missionProgress}
              tone={workflow.missionStatus === "completed" ? "success" : "warning"}
            />
          </span>
          <a className="incident-link" href={`/missions/${featuredMission.id}`}>
            进入 Mission <ArrowRight size={14} />
          </a>
        </div>
      </section>

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
          label="今日发电量"
          value={windFarm.todayGenerationGWh.toFixed(2)}
          unit="GWh"
          change={2.1}
          changeLabel="较昨日同期"
          icon={<Activity size={15} />}
        />
        <MetricCard
          label="运行机组"
          value={`${operating} / 64`}
          detail={`${running} 台正常 · ${turbines.length - operating - offline} 台维护`}
          icon={<TowerControl size={15} />}
          tone="success"
        />
        <MetricCard
          label="离线机组"
          value={String(offline)}
          detail="含通信中断机组"
          icon={<Radio size={15} />}
          tone={offline > 0 ? "warning" : "success"}
        />
        <MetricCard
          label="故障机组"
          value={String(faulted)}
          detail="状态为 CRITICAL"
          icon={<AlarmTriangle size={15} />}
          tone={faulted > 0 ? "critical" : "success"}
        />
        <MetricCard
          label="平均健康度"
          value={windFarm.averageHealthScore.toFixed(1)}
          unit="%"
          change={-0.6}
          changeLabel="过去 7 日"
          icon={<CircleGauge size={15} />}
          tone="warning"
        />
        <MetricCard
          label="活跃告警"
          value={String(windFarm.activeAlarmCount)}
          detail={`${criticalAlarms.length} 条高优先级`}
          icon={<AlarmTriangle size={15} />}
          tone="critical"
        />
        <MetricCard
          label="AI Missions"
          value={String(windFarm.activeMissionCount)}
          detail={`${activeAgents} 个 Agent 活跃`}
          icon={<Bot size={15} />}
          tone="info"
        />
        <MetricCard
          label="总装机容量"
          value={String(windFarm.totalCapacityMW)}
          unit="MW"
          detail="GW165-6.0MW · 64 台"
          icon={<Wind size={15} />}
        />
      </section>

      <section className="dashboard-grid">
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

        <Card className="panel panel--fleet">
          <CardHeader
            eyebrow="FLEET HEALTH"
            title="机组状态分布"
            description="基于当前在线快照"
            action={
              <a className="text-link" href="/wind-farms">
                查看全部 <ArrowRight size={12} />
              </a>
            }
          />
          <div className="fleet-donut-wrap">
            <div
              className="fleet-donut"
              style={{ "--running": `${(running / 64) * 360}deg` } as CSSProperties}
            >
              <span>
                <strong>{running}</strong>
                <small>运行机组</small>
              </span>
            </div>
            <div className="fleet-summary">
              {statusSummary.map((item) => (
                <div key={item.label}>
                  <span>
                    <i className={`summary-dot summary-dot--${item.tone}`} />
                    {item.label}
                  </span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </div>
          <div className="fleet-foot">
            <span>场站可利用率</span>
            <strong>96.8%</strong>
            <Progress value={96.8} tone="success" />
          </div>
        </Card>

        <Card className="panel panel--alerts">
          <CardHeader
            eyebrow="ATTENTION REQUIRED"
            title="高优先级告警"
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
                </span>
                <span className="compact-row__meta">
                  <StatusBadge value={alarm.severity} compact />
                  <small>{Math.max(1, Math.round(alarm.durationMinutes / 60))}h</small>
                </span>
              </a>
            ))}
          </div>
        </Card>

        <Card className="panel panel--missions">
          <CardHeader
            eyebrow="MULTI-AGENT OPERATIONS"
            title="活跃 Missions"
            description="诊断、审核与执行进度"
            action={
              <Link className="text-link" href="/missions">
                Mission Center <ArrowRight size={12} />
              </Link>
            }
          />
          <div className="mission-list">
            {activeMissions.map((mission) => (
              <a className="mission-list-row" href={`/missions/${mission.id}`} key={mission.id}>
                <span className="mission-priority" data-risk={mission.severity}>
                  {mission.severity.slice(0, 1).toUpperCase()}
                </span>
                <span className="mission-list-row__copy">
                  <strong>{mission.title}</strong>
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
            eyebrow="LIVE AGENT ACTIVITY"
            title="WT-023 协作时间线"
            description="仅显示结构化执行摘要，不展示隐藏推理"
            action={
              <StatusBadge
                value="working"
                label={`${activeAgents} AGENTS ACTIVE`}
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
                    <span>{agent?.shortName ?? event.actorLabel}</span>
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
            eyebrow="OFFSHORE WINDOW"
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
