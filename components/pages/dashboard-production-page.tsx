"use client";

import {
  Activity,
  TriangleAlert as AlarmTriangle,
  ArrowRight,
  Bot,
  CalendarDays,
  CircleGauge,
  Download,
  TowerControl,
  Zap,
} from "lucide-react";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { TimeSeriesChart, type TimeSeriesPoint } from "@/components/charts/time-series-chart";
import { MetricCard } from "@/components/data-display/metric-card";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import {
  PartialFailureNotice,
  QueryStateNotice,
  RuntimeHealthBadge,
  type PartialQueryFailure,
} from "@/components/ui/query-state";
import { apiGet } from "@/lib/api-client";
import { deriveQueryViewState, mergeRuntimeHealth, queryRuntimeHealth } from "@/lib/query-state";

import { DashboardIncidentStrip, formatDurationMinutes, formatTime } from "./dashboard-shared";

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

export function ProductionDashboardPage() {
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
