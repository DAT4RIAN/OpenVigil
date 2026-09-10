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
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import Link from "next/link";
import { Card, CardHeader, EmptyState, Progress, Button } from "@/components/ui/primitives";
import {
  PartialFailureNotice,
  QueryStateNotice,
  RuntimeHealthBadge,
  type PartialQueryFailure,
} from "@/components/ui/query-state";
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
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";
import { deriveQueryViewState, mergeRuntimeHealth, queryRuntimeHealth } from "@/lib/query-state";

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

function formatDurationMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} 小时 ${remainder} 分钟` : `${hours} 小时`;
}

type DashboardIncidentStripProps = {
  readonly stable: boolean;
  readonly priority: "P1" | "P2" | "稳定";
  readonly eyebrow: string;
  readonly title: string;
  readonly context: string;
  readonly aiStatus: string;
  readonly healthValue: string;
  readonly anomalyValue: string;
  readonly freshness: string;
  readonly actionHref: string;
  readonly actionLabel: string;
};

function DashboardIncidentStrip({
  stable,
  priority,
  eyebrow,
  title,
  context,
  aiStatus,
  healthValue,
  anomalyValue,
  freshness,
  actionHref,
  actionLabel,
}: DashboardIncidentStripProps) {
  return (
    <section
      className={`command-strip${stable ? " command-strip--stable" : ""}`}
      aria-label={stable ? "当前稳定状态" : "当前最高优先级事件"}
      aria-live="polite"
    >
      <span className="incident-index" data-stable={stable || undefined}>
        {stable ? <CheckCircle2 size={18} aria-hidden="true" /> : priority}
      </span>
      <span className="incident-copy">
        <small>{eyebrow}</small>
        <a className="incident-title-link" href={actionHref}>
          {title}
        </a>
        <span>{context}</span>
      </span>
      <dl className="incident-signals">
        <div>
          <dt>公开 AI 状态</dt>
          <dd>{aiStatus}</dd>
        </div>
        <div>
          <dt>健康值</dt>
          <dd>{healthValue}</dd>
        </div>
        <div>
          <dt>异常强度</dt>
          <dd>{anomalyValue}</dd>
        </div>
        <div>
          <dt>数据时间</dt>
          <dd>{freshness}</dd>
        </div>
      </dl>
      <a className="incident-link" href={actionHref}>
        {actionLabel} <ArrowRight size={15} aria-hidden="true" />
      </a>
    </section>
  );
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
    staleTime: 45_000,
  });
  const snapshot = dashboardQuery.data?.data;
  const dashboardState = deriveQueryViewState({
    data: snapshot,
    dataUpdatedAt: dashboardQuery.dataUpdatedAt,
    error: dashboardQuery.error,
    isError: dashboardQuery.isError,
    isFetching: dashboardQuery.isFetching,
    isPending: dashboardQuery.isPending,
    isStale: dashboardQuery.isStale,
    isEmpty: (data) =>
      data.farm === null &&
      data.fleet.asset_count === 0 &&
      data.power_trend.length === 0 &&
      data.alarms.length === 0 &&
      data.missions.length === 0 &&
      data.activity.length === 0,
    sourceUpdatedAt: snapshot ? Date.parse(snapshot.snapshot_at) : null,
    staleAfterMs: 60_000,
  });
  const partialFailures: readonly PartialQueryFailure[] =
    snapshot && dashboardState.lifecycle === "success-data" && snapshot.fleet.asset_count > 0
      ? [
          snapshot.fleet.average_health_score === null
            ? {
                module: "资产健康",
                code: "HEALTH_SCORE_UNAVAILABLE",
                detail: "当前快照没有可计算的平均健康度",
                lastSuccessAt: Date.parse(snapshot.snapshot_at),
              }
            : null,
          snapshot.fleet.average_availability_percent === null
            ? {
                module: "可利用率遥测",
                code: "AVAILABILITY_UNAVAILABLE",
                detail: "当前快照没有良好质量的可利用率测点",
                lastSuccessAt: snapshot.fleet.latest_telemetry_at
                  ? Date.parse(snapshot.fleet.latest_telemetry_at)
                  : null,
              }
            : null,
          snapshot.fleet.energy_24h_gwh === null
            ? {
                module: "24 小时电量",
                code: "ENERGY_WINDOW_INCOMPLETE",
                detail: "有效功率时间桶不足，无法形成 24 小时电量结论",
                lastSuccessAt: snapshot.fleet.latest_telemetry_at
                  ? Date.parse(snapshot.fleet.latest_telemetry_at)
                  : null,
              }
            : null,
          snapshot.power_trend.length === 0
            ? {
                module: "功率趋势",
                code: "POWER_TREND_UNAVAILABLE",
                detail: "当前窗口没有可绘制的良好质量功率遥测",
                lastSuccessAt: snapshot.fleet.latest_telemetry_at
                  ? Date.parse(snapshot.fleet.latest_telemetry_at)
                  : null,
              }
            : null,
        ].filter((failure): failure is PartialQueryFailure => failure !== null)
      : [];
  const pageHealth = mergeRuntimeHealth(
    queryRuntimeHealth(dashboardState, "运营快照"),
    partialFailures.length > 0
      ? {
          status: "degraded",
          label: "Degraded",
          detail: `${partialFailures.map((failure) => failure.module).join("、")}数据不可用`,
          lastSuccessAt: dashboardState.lastSuccessAt,
        }
      : null,
  );
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
  const farmName = snapshot?.farm?.name ?? "生产风场";

  if (!snapshot) {
    return (
      <AppShell runtimeMode="production" activePath="/" pageHealth={pageHealth}>
        <PageHeader
          eyebrow="实时运行态势"
          title="运营指挥中心"
          description="Production · PostgreSQL/TimescaleDB 权威运营快照"
          meta={
            <>
              <RuntimeHealthBadge health={pageHealth} />
              <span className="page-meta-text">等待首个可验证快照</span>
            </>
          }
        />
        <QueryStateNotice
          state={dashboardState}
          target="运营指挥数据"
          impact="功率、机组状态、告警、Mission 与 Agent 活动"
          onRetry={() => void dashboardQuery.refetch()}
        />
      </AppShell>
    );
  }

  if (dashboardState.lifecycle === "success-empty") {
    return (
      <AppShell runtimeMode="production" activePath="/" pageHealth={pageHealth}>
        <PageHeader
          eyebrow="实时运行态势"
          title="运营指挥中心"
          description="Production · PostgreSQL/TimescaleDB 权威运营快照"
          meta={
            <>
              <RuntimeHealthBadge health={pageHealth} />
              <span className="page-meta-text">
                快照 {new Date(snapshot.snapshot_at).toLocaleString("zh-CN")}
              </span>
            </>
          }
        />
        <EmptyState
          icon={<Activity size={22} />}
          title="当前范围内没有运营数据"
          description="权威运营快照已成功返回空结果；这不是加载或服务错误。"
        />
      </AppShell>
    );
  }

  const fleet = snapshot.fleet;
  const statusCounts = fleet.status_counts;
  const assetCount = fleet.asset_count;
  const runningCount = statusCounts.running ?? 0;
  const offlineCount = (statusCounts.offline ?? 0) + (statusCounts["communication-lost"] ?? 0);
  const criticalCount = statusCounts.critical ?? 0;
  const availability = fleet.average_availability_percent;
  const highestPriorityAlarm = snapshot.alarms.find((alarm) =>
    ["critical", "major", "high"].includes(alarm.severity),
  );
  const incidentMission = highestPriorityAlarm
    ? snapshot.missions.find((mission) => mission.turbine_id === highestPriorityAlarm.turbine_id)
    : undefined;
  const incidentAgeMinutes = highestPriorityAlarm
    ? Math.max(
        1,
        Math.floor(
          (Date.parse(snapshot.snapshot_at) - Date.parse(highestPriorityAlarm.triggered_at)) /
            60_000,
        ),
      )
    : 0;

  return (
    <AppShell runtimeMode="production" activePath="/" pageHealth={pageHealth}>
      <PageHeader
        eyebrow="实时运行态势"
        title="运营指挥中心"
        description={`${farmName} · ${assetCount} 台资产 · PostgreSQL/TimescaleDB 权威运营快照`}
        meta={
          <>
            <RuntimeHealthBadge health={pageHealth} />
            <span className="page-meta-text">
              快照 {new Date(snapshot.snapshot_at).toLocaleString("zh-CN")}
            </span>
            <Link className="page-meta-text" href="/wind-farms">
              查看风场
            </Link>
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

      <QueryStateNotice
        state={dashboardState}
        target="运营指挥数据"
        impact="功率、机组状态、告警、Mission 与 Agent 活动"
        onRetry={() => void dashboardQuery.refetch()}
      />

      <PartialFailureNotice
        target="运营快照"
        failures={partialFailures}
        onRetry={() => void dashboardQuery.refetch()}
      />

      <DashboardIncidentStrip
        stable={!highestPriorityAlarm}
        priority={highestPriorityAlarm?.severity === "critical" ? "P1" : "P2"}
        eyebrow={highestPriorityAlarm ? "最高优先级 · 需要处置" : "当前稳定 · 无高优事件"}
        title={highestPriorityAlarm?.title ?? "当前没有需要立即处置的事件"}
        context={
          highestPriorityAlarm
            ? `${highestPriorityAlarm.turbine_id} · ${highestPriorityAlarm.code} · 已持续 ${formatDurationMinutes(incidentAgeMinutes)}`
            : `截至 ${new Date(snapshot.snapshot_at).toLocaleString("zh-CN")}，权威快照未返回高优先级告警`
        }
        aiStatus={
          incidentMission ? productionMissionLabel(incidentMission.status) : "尚未关联 Mission"
        }
        healthValue="—"
        anomalyValue="—"
        freshness={new Date(snapshot.snapshot_at).toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        })}
        actionHref={incidentMission ? `/missions/${incidentMission.id}` : "/alarms"}
        actionLabel={incidentMission ? "进入 Mission" : "查看全部告警"}
      />

      <section className="metrics-grid" aria-label="生产运行指标">
        <MetricCard
          label="当前功率"
          value={fleet.current_power_mw.toFixed(1)}
          unit="MW"
          detail={`遥测覆盖 ${fleet.telemetry_asset_count}/${assetCount} 台`}
          icon={<Zap size={15} />}
          tone="info"
        />
        <MetricCard
          label="近 24 小时电量"
          value={fleet.energy_24h_gwh == null ? "—" : fleet.energy_24h_gwh.toFixed(3)}
          unit={fleet.energy_24h_gwh == null ? undefined : "GWh"}
          detail={
            fleet.energy_24h_gwh == null
              ? "有效功率时间桶不足，未用零值替代"
              : `时间桶覆盖 ${fleet.energy_coverage_percent}%`
          }
          icon={<Activity size={15} />}
        />
        <MetricCard
          label="运行机组"
          value={`${fleet.operating_count} / ${assetCount}`}
          detail={`${runningCount} 台正常运行`}
          icon={<TowerControl size={15} />}
          tone="success"
        />
        <MetricCard
          label="平均健康度"
          value={fleet.average_health_score == null ? "—" : fleet.average_health_score.toFixed(1)}
          unit={fleet.average_health_score == null ? undefined : "%"}
          detail={
            fleet.average_health_score == null ? "健康模块未返回可计算值" : "来自资产健康台账"
          }
          icon={<CircleGauge size={15} />}
        />
        <MetricCard
          label="活跃告警"
          value={String(fleet.open_alarm_count)}
          detail={`${fleet.high_priority_alarm_count} 条高优先级`}
          icon={<AlarmTriangle size={15} />}
          tone={fleet.high_priority_alarm_count ? "critical" : "success"}
        />
        <MetricCard
          label="活跃 Missions"
          value={String(fleet.active_mission_count)}
          detail={`${snapshot.agents.active_definition_count} 个受治理 Agent 启用`}
          icon={<Bot size={15} />}
          tone="info"
        />
      </section>

      <section className="dashboard-main-grid">
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

        <Card className="panel panel--priority">
          <CardHeader
            eyebrow="需要关注"
            title="优先处置队列"
            description="按严重性和触发时间排序"
            action={
              <Link className="text-link" href="/alarms">
                告警中心 <ArrowRight size={12} />
              </Link>
            }
          />
          <div className="compact-list">
            {snapshot.alarms.map((alarm) => (
              <Link className="compact-row alarm-row" href="/alarms" key={alarm.id}>
                <span className={`severity-rail severity-rail--${alarm.severity}`} />
                <span className="compact-row__main">
                  <strong>{alarm.title}</strong>
                  <small>
                    <span className="mono">{alarm.turbine_id}</span> · {alarm.code}
                  </small>
                  <small>
                    负责人：
                    {snapshot.missions.some((mission) => mission.turbine_id === alarm.turbine_id)
                      ? "关联 Mission 团队"
                      : "值班调度"}
                  </small>
                </span>
                <span className="compact-row__meta">
                  <StatusBadge value={alarm.severity} compact />
                  <small>
                    {formatDurationMinutes(
                      Math.max(
                        1,
                        Math.floor(
                          (Date.parse(snapshot.snapshot_at) - Date.parse(alarm.triggered_at)) /
                            60_000,
                        ),
                      ),
                    )}
                  </small>
                </span>
              </Link>
            ))}
            {!snapshot.alarms.length ? (
              <div className="view-empty-state">没有未关闭告警。</div>
            ) : null}
          </div>
          <div className="priority-fleet-context">
            <span>
              运行 {runningCount} · 离线 {offlineCount} · 故障 {criticalCount}
            </span>
            <span>可利用率 {availability == null ? "—" : `${availability.toFixed(1)}%`}</span>
          </div>
        </Card>
      </section>

      <section className="dashboard-lower-grid">
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
            {snapshot.missions.map((mission) => (
              <Link className="mission-list-row" href={`/missions/${mission.id}`} key={mission.id}>
                <span className="mission-priority" data-risk="high">
                  M
                </span>
                <span className="mission-list-row__copy">
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
            {!snapshot.missions.length ? (
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
          <div className="activity-stream">
            {snapshot.activity.map((event) => (
              <div className="activity-event" key={event.sequence}>
                <span className="activity-event__icon">
                  <Bot size={12} />
                </span>
                <span className="activity-event__copy">
                  <strong>{event.event_type}</strong>
                  <small>
                    {event.aggregate_type} · {event.aggregate_id} · {event.summary}
                  </small>
                </span>
                <time>{formatTime(event.occurred_at)}</time>
              </div>
            ))}
            {!snapshot.activity.length ? (
              <div className="view-empty-state">尚无领域事件。</div>
            ) : null}
          </div>
        </Card>

        <Card className="panel panel--window">
          <CardHeader
            eyebrow="海上作业窗口"
            title="下一可用作业窗口"
            description="生产运营快照的天气与资源边界"
          />
          <div className="view-empty-state">
            当前运营快照未提供作业窗口；请进入运行日历核对权威天气与资源结果。
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

export function DashboardPage({ runtimeMode }: { readonly runtimeMode: OpenVigilRuntimeMode }) {
  return runtimeMode === "production" ? <ProductionDashboardPage /> : <DemoDashboardPage />;
}
