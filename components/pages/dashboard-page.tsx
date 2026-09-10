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
import { useQuery } from "@tanstack/react-query";
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
import {
  deriveWorkflowKpis,
  overlayClientAgents,
  overlayClientAlarms,
  overlayClientMissions,
  overlayClientTurbines,
} from "@/lib/client-workflow-overlays";
import { agentDisplayName } from "@/lib/agent-control-meta";
import { localizedMissionTitle, localizedSeverityLabel } from "@/lib/ui-localization";
import { apiGet } from "@/lib/api-client";
import type { WindOpsRuntimeMode } from "@/lib/production-runtime";

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

function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

type ProductionDashboardEnvelope = {
  readonly data: {
    readonly snapshot_at: string;
    readonly source: string;
    readonly farm: {
      readonly id: string;
      readonly name: string;
      readonly capacity_mw: number;
    } | null;
    readonly fleet: {
      readonly asset_count: number;
      readonly status_counts: Readonly<Record<string, number>>;
      readonly operating_count: number;
      readonly average_health_score: number | null;
      readonly current_power_mw: number;
      readonly energy_24h_gwh: number | null;
      readonly energy_coverage_percent: number;
      readonly average_availability_percent: number | null;
      readonly telemetry_asset_count: number;
      readonly latest_telemetry_at: string | null;
      readonly open_alarm_count: number;
      readonly high_priority_alarm_count: number;
      readonly active_mission_count: number;
    };
    readonly power_trend: readonly {
      readonly timestamp: string;
      readonly power_mw: number;
      readonly asset_count: number;
    }[];
    readonly alarms: readonly {
      readonly id: string;
      readonly turbine_id: string;
      readonly code: string;
      readonly title: string;
      readonly severity: string;
      readonly status: string;
      readonly triggered_at: string;
    }[];
    readonly missions: readonly {
      readonly id: string;
      readonly turbine_id: string;
      readonly title: string;
      readonly status: string;
      readonly revision: number;
      readonly updated_at: string;
    }[];
    readonly agents: {
      readonly active_definition_count: number;
      readonly execution_count_24h: number;
      readonly succeeded_24h: number;
      readonly failed_24h: number;
    };
    readonly activity: readonly {
      readonly sequence: number;
      readonly event_type: string;
      readonly aggregate_type: string;
      readonly aggregate_id: string;
      readonly occurred_at: string;
      readonly summary: string;
    }[];
  };
};

const productionMissionLabel = (status: string): string =>
  ({
    detected: "已发现",
    investigating: "分析中",
    diagnosed: "已诊断",
    decision_pending: "待决策",
    "decision-pending": "待决策",
    under_review: "审核中",
    "under-review": "审核中",
    approved: "已批准",
    executing: "执行中",
    completed: "已完成",
  })[status] ?? status;

function ProductionDashboardPage() {
  const dashboardQuery = useQuery({
    queryKey: ["production-dashboard"],
    queryFn: ({ signal }) => apiGet<ProductionDashboardEnvelope>("/api/backend/dashboard", signal),
    refetchInterval: 15_000,
    retry: false,
  });
  const snapshot = dashboardQuery.data?.data;
  const fleet = snapshot?.fleet;
  const statusCounts = fleet?.status_counts ?? {};
  const powerChartData = useMemo<TimeSeriesPoint[]>(
    () =>
      (snapshot?.power_trend ?? []).map((point) => ({
        timestamp: new Date(point.timestamp).toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }),
        value: point.power_mw,
      })),
    [snapshot?.power_trend],
  );
  const assetCount = fleet?.asset_count ?? 0;
  const runningCount = statusCounts.running ?? 0;
  const offlineCount = (statusCounts.offline ?? 0) + (statusCounts["communication-lost"] ?? 0);
  const criticalCount = statusCounts.critical ?? 0;
  const availability = fleet?.average_availability_percent;
  const farmName = snapshot?.farm?.name ?? "生产风场";

  return (
    <AppShell runtimeMode="production" activePath="/">
      <PageHeader
        eyebrow="实时运行态势"
        title="运营指挥中心"
        description={`${farmName} · PostgreSQL/TimescaleDB 权威运营快照`}
        meta={
          <>
            <StatusBadge
              value={dashboardQuery.isError ? "degraded" : "running"}
              label={dashboardQuery.isError ? "生产快照不可用" : "生产数据已连接"}
              tone={dashboardQuery.isError ? "critical" : "success"}
              pulse={!dashboardQuery.isError}
            />
            <span className="page-meta-text">
              {snapshot
                ? `快照 ${new Date(snapshot.snapshot_at).toLocaleString("zh-CN")}`
                : "正在读取权威运营快照"}
            </span>
          </>
        }
        actions={
          <>
            <Link className="button button--secondary button--md" href="/work-orders">
              <CalendarDays size={15} /> 运行日历
            </Link>
            <Link className="button button--primary button--md" href="/reports">
              <Download size={15} /> 生成持久化报告
            </Link>
          </>
        }
      />

      {dashboardQuery.isError ? (
        <Card className="view-empty-state" role="alert">
          生产首页已失败关闭，不会显示演示风场、固定告警或 WT-023 故事数据。
        </Card>
      ) : null}

      <section className="metrics-grid" aria-label="生产运行指标">
        <MetricCard
          label="当前功率"
          value={fleet ? fleet.current_power_mw.toFixed(1) : "—"}
          unit={fleet ? "MW" : undefined}
          detail={`遥测覆盖 ${fleet?.telemetry_asset_count ?? 0}/${assetCount} 台`}
          icon={<Zap size={15} />}
          tone="info"
        />
        <MetricCard
          label="近 24 小时电量"
          value={fleet?.energy_24h_gwh == null ? "—" : fleet.energy_24h_gwh.toFixed(3)}
          unit={fleet?.energy_24h_gwh == null ? undefined : "GWh"}
          detail={`时间桶覆盖 ${fleet?.energy_coverage_percent ?? 0}%`}
          icon={<Activity size={15} />}
        />
        <MetricCard
          label="运行机组"
          value={`${fleet?.operating_count ?? 0} / ${assetCount}`}
          detail={`${runningCount} 台正常运行`}
          icon={<TowerControl size={15} />}
          tone="success"
        />
        <MetricCard
          label="离线机组"
          value={String(offlineCount)}
          detail="含通信中断资产"
          icon={<Radio size={15} />}
          tone={offlineCount ? "warning" : "success"}
        />
        <MetricCard
          label="故障机组"
          value={String(criticalCount)}
          detail="状态为 CRITICAL"
          icon={<AlarmTriangle size={15} />}
          tone={criticalCount ? "critical" : "success"}
        />
        <MetricCard
          label="平均健康度"
          value={fleet?.average_health_score == null ? "—" : fleet.average_health_score.toFixed(1)}
          unit={fleet?.average_health_score == null ? undefined : "%"}
          detail="来自资产健康台账"
          icon={<CircleGauge size={15} />}
        />
        <MetricCard
          label="活跃告警"
          value={String(fleet?.open_alarm_count ?? 0)}
          detail={`${fleet?.high_priority_alarm_count ?? 0} 条高优先级`}
          icon={<AlarmTriangle size={15} />}
          tone={(fleet?.high_priority_alarm_count ?? 0) ? "critical" : "success"}
        />
        <MetricCard
          label="AI Mission"
          value={String(fleet?.active_mission_count ?? 0)}
          detail={`${snapshot?.agents.active_definition_count ?? 0} 个受治理 Agent 启用`}
          icon={<Bot size={15} />}
          tone="info"
        />
        <MetricCard
          label="总装机容量"
          value={snapshot?.farm ? snapshot.farm.capacity_mw.toFixed(1) : "—"}
          unit={snapshot?.farm ? "MW" : undefined}
          detail={snapshot?.farm?.id ?? "场站未配置"}
          icon={<Wind size={15} />}
        />
      </section>

      <section className="dashboard-grid">
        <Card className="panel panel--power">
          <CardHeader
            eyebrow="SCADA · 24H"
            title="全场有功功率"
            description="按 15 分钟桶聚合实际 active_power 遥测"
          />
          {powerChartData.length ? (
            <TimeSeriesChart
              data={powerChartData}
              height={250}
              primaryName="全场有功功率"
              unit="MW"
            />
          ) : (
            <div className="view-empty-state">当前没有足够的功率遥测用于绘图。</div>
          )}
        </Card>

        <Card className="panel panel--fleet">
          <CardHeader
            eyebrow="全场健康"
            title="机组状态分布"
            description="来自资产主数据当前状态"
          />
          <div className="fleet-summary">
            {Object.entries(statusCounts).map(([status, count]) => (
              <div key={status}>
                <span>{status}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
          <div className="fleet-foot">
            <span>平均可利用率</span>
            <strong>{availability == null ? "未接入" : `${availability.toFixed(1)}%`}</strong>
            {availability == null ? null : <Progress value={availability} tone="success" />}
          </div>
        </Card>

        <Card className="panel panel--alerts">
          <CardHeader
            eyebrow="需要关注"
            title="高优先级告警"
            description="按严重性和触发时间排序"
            action={
              <Link className="text-link" href="/alarms">
                告警中心 <ArrowRight size={12} />
              </Link>
            }
          />
          <div className="compact-list">
            {(snapshot?.alarms ?? []).map((alarm) => (
              <Link className="compact-row alarm-row" href="/alarms" key={alarm.id}>
                <span className={`severity-rail severity-rail--${alarm.severity}`} />
                <span className="compact-row__main">
                  <strong>{alarm.title}</strong>
                  <small>
                    <span className="mono">{alarm.turbine_id}</span> · {alarm.code}
                  </small>
                </span>
                <span className="compact-row__meta">
                  <StatusBadge value={alarm.severity} compact />
                  <small>{formatTime(alarm.triggered_at)}</small>
                </span>
              </Link>
            ))}
            {!snapshot?.alarms.length ? (
              <div className="view-empty-state">没有未关闭告警。</div>
            ) : null}
          </div>
        </Card>

        <Card className="panel panel--missions">
          <CardHeader
            eyebrow="多 Agent 协作"
            title="活跃 Missions"
            description="来自持久化 Mission 台账"
            action={
              <Link className="text-link" href="/missions">
                Mission 中心 <ArrowRight size={12} />
              </Link>
            }
          />
          <div className="mission-list">
            {(snapshot?.missions ?? []).map((mission) => (
              <Link className="mission-list-row" href={`/missions/${mission.id}`} key={mission.id}>
                <span>
                  <strong>{mission.title}</strong>
                  <small>
                    {mission.turbine_id} · REV {mission.revision}
                  </small>
                </span>
                <StatusBadge
                  value={mission.status}
                  label={productionMissionLabel(mission.status)}
                  compact
                />
              </Link>
            ))}
            {!snapshot?.missions.length ? (
              <div className="view-empty-state">没有活跃 Mission。</div>
            ) : null}
          </div>
        </Card>

        <Card className="panel panel--activity">
          <CardHeader
            eyebrow="审计事件"
            title="最近领域事件"
            description="使用持久化 sequence 作为可重放游标"
          />
          <div className="activity-timeline">
            {(snapshot?.activity ?? []).map((event) => (
              <div className="activity-item" key={event.sequence}>
                <span className="activity-dot activity-dot--system">
                  <Bot size={12} />
                </span>
                <span>
                  <strong>{event.event_type}</strong>
                  <small>
                    {event.aggregate_type} · {event.aggregate_id} · {event.summary}
                  </small>
                </span>
                <time>{formatTime(event.occurred_at)}</time>
              </div>
            ))}
            {!snapshot?.activity.length ? (
              <div className="view-empty-state">尚无领域事件。</div>
            ) : null}
          </div>
        </Card>

        <Card className="panel panel--window">
          <CardHeader
            eyebrow="Agent 运行"
            title="近 24 小时执行"
            description="持久化 AgentExecution 账本"
          />
          <div className="resource-check">
            <ShieldCheck size={14} />
            <span>
              <strong>{snapshot?.agents.execution_count_24h ?? 0} 次执行</strong>
              <small>
                成功 {snapshot?.agents.succeeded_24h ?? 0} · 失败 {snapshot?.agents.failed_24h ?? 0}
              </small>
            </span>
          </div>
        </Card>
      </section>
    </AppShell>
  );
}

function DemoDashboardPage() {
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
    .filter((alarm) => alarm.severity === "critical" || alarm.severity === "major")
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

  const downloadDailyReport = () => {
    const unresolvedAlarms = displayAlarms.filter((alarm) => alarm.status !== "resolved").length;
    const reportRows = [
      ["WindOps 华东海上风电场运行日报", "2026-08-13", "白班"],
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
    link.download = "windops-daily-report-2026-08-13.csv";
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
            <small>全场状态</small>
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
          detail={`${running} 台正常 · ${displayTurbines.length - operating - offline} 台维护`}
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
          label="AI Mission"
          value={String(workflowKpis.activeMissionCount)}
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
            eyebrow="全场健康"
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
            eyebrow="需要关注"
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

export function DashboardPage({ runtimeMode }: { readonly runtimeMode: WindOpsRuntimeMode }) {
  return runtimeMode === "production" ? <ProductionDashboardPage /> : <DemoDashboardPage />;
}
