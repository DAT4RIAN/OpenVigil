"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import {
  AlertTriangle,
  Anchor,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleGauge,
  Clock3,
  CloudSun,
  FilterX,
  LayoutList,
  PackageCheck,
  Search,
  ShipWheel,
  UsersRound,
  Wrench,
} from "lucide-react";
import { StatusBadge, type StatusTone } from "@/components/data-display/status-badge";
import { DataTable } from "@/components/data-display/data-table";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, Progress } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import {
  createMaintenancePlans,
  maintenancePlanMeta,
  maintenancePlanTeamFacets,
  type MaintenancePlan,
  type MaintenancePlanStatus,
  type MaintenancePlanWindowState,
  type MaintenanceResourceRef,
} from "@/lib/maintenance-plan-data";
import type { RiskLevel } from "@/lib/types";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";

import styles from "./maintenance-plan-page.module.css";

type ViewMode = "calendar" | "list";
type StatusFilter = "all" | MaintenancePlanStatus;
type RiskFilter = "all" | RiskLevel;
type WindowFilter = "all" | MaintenancePlanWindowState;

interface MaintenancePlanResponse {
  readonly data: readonly MaintenancePlan[];
  readonly meta: {
    readonly count: number;
    readonly total: number;
    readonly filteredTotal: number;
    readonly model: typeof maintenancePlanMeta;
    readonly workflowPersistence?: string;
    readonly workflowRevision?: number;
  };
}

const featuredWorkOrderId = "WO-20260823-017";

const statusLabels: Readonly<Record<MaintenancePlanStatus, string>> = {
  "approval-gated": "待审批",
  ready: "可执行",
  "at-risk": "存在冲突",
  "in-progress": "执行中",
  paused: "已暂停",
  completed: "已完成",
};

const statusTones: Readonly<Record<MaintenancePlanStatus, StatusTone>> = {
  "approval-gated": "warning",
  ready: "success",
  "at-risk": "critical",
  "in-progress": "info",
  paused: "maintenance",
  completed: "success",
};

const riskLabels: Readonly<Record<RiskLevel, string>> = {
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
};

const windowLabels: Readonly<Record<MaintenancePlanWindowState, string>> = {
  suitable: "适宜窗口",
  conditional: "条件窗口",
  unsafe: "不可作业",
  unmatched: "未匹配",
  "not-required": "无需海况",
};

const windowTone = (state: MaintenancePlanWindowState): StatusTone =>
  state === "suitable" || state === "not-required"
    ? "success"
    : state === "conditional"
      ? "warning"
      : state === "unsafe"
        ? "critical"
        : "neutral";

const resourceStateLabels: Readonly<Record<MaintenanceResourceRef["state"], string>> = {
  confirmed: "已确认",
  reserved: "已预留",
  available: "可用",
  conflict: "冲突",
  untracked: "台账外",
};

const resourceTone = (state: MaintenanceResourceRef["state"]): StatusTone =>
  state === "conflict"
    ? "critical"
    : state === "untracked"
      ? "warning"
      : state === "available"
        ? "info"
        : "success";

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "short",
  day: "numeric",
  weekday: "short",
});
const dateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const timeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const formatDate = (value: string): string => dateFormatter.format(new Date(value));
const formatDateTime = (value: string): string => dateTimeFormatter.format(new Date(value));
const formatTime = (value: string): string => timeFormatter.format(new Date(value));

const planColumns: readonly LegacyColumnDef<MaintenancePlan, unknown>[] = [
  {
    id: "plan",
    header: "计划 / 工单",
    accessorFn: (plan) => `${plan.turbineId} ${plan.issue} ${plan.workOrderId}`,
    cell: ({ row }) => (
      <span>
        <strong>
          {row.original.turbineId} · {row.original.issue}
        </strong>
        <small>{row.original.workOrderId}</small>
      </span>
    ),
  },
  {
    id: "startsAt",
    header: "时段",
    accessorFn: (plan) => plan.startsAt,
    cell: ({ row }) => (
      <span>
        <strong>{formatDate(row.original.startsAt)}</strong>
        <small>
          {formatTime(row.original.startsAt)}–{formatTime(row.original.endsAt)}
        </small>
      </span>
    ),
  },
  {
    accessorKey: "status",
    header: "状态",
    cell: ({ row }) => (
      <StatusBadge
        value={row.original.status}
        label={statusLabels[row.original.status]}
        tone={statusTones[row.original.status]}
        compact
      />
    ),
  },
  {
    id: "crew",
    header: "班组",
    accessorFn: (plan) => plan.crew.label,
    cell: ({ row }) => (
      <span>
        <strong>{row.original.crew.label}</strong>
        <small>{resourceStateLabels[row.original.crew.state]}</small>
      </span>
    ),
  },
  {
    id: "weather",
    header: "天气窗口",
    accessorFn: (plan) => plan.weather.state,
    cell: ({ row }) => (
      <StatusBadge
        value={row.original.weather.state}
        label={windowLabels[row.original.weather.state]}
        tone={windowTone(row.original.weather.state)}
        compact
      />
    ),
  },
  {
    accessorKey: "readinessPercent",
    header: "就绪度",
    cell: ({ row }) => <strong>{row.original.readinessPercent}%</strong>,
  },
  {
    id: "conflicts",
    header: "提示",
    accessorFn: (plan) => plan.conflicts.length,
    cell: ({ row }) => (
      <span
        className={styles.conflictCount}
        data-critical={row.original.conflicts.some((item) => item.severity === "critical")}
      >
        <AlertTriangle size={12} /> {row.original.conflicts.length}
      </span>
    ),
  },
];

function ResourceRows({
  icon,
  title,
  items,
  empty,
}: {
  icon: React.ReactNode;
  title: string;
  items: readonly MaintenanceResourceRef[];
  empty: string;
}) {
  return (
    <section className={styles.resourceSection}>
      <header>
        <span>{icon}</span>
        <strong>{title}</strong>
      </header>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={`${title}-${item.id}-${item.label}`}>
              <div>
                <strong>{item.label}</strong>
                <small>{item.detail}</small>
              </div>
              <StatusBadge
                value={item.state}
                label={resourceStateLabels[item.state]}
                tone={resourceTone(item.state)}
                compact
              />
            </li>
          ))}
        </ul>
      ) : (
        <p>{empty}</p>
      )}
    </section>
  );
}

function PlanCard({
  plan,
  selected,
  onSelect,
}: {
  plan: MaintenancePlan;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={styles.planCard}
      data-selected={selected}
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`查看 ${plan.workOrderId} 维护计划`}
    >
      <span className={styles.cardHeader}>
        <strong>{plan.turbineId}</strong>
        <StatusBadge
          value={plan.status}
          label={statusLabels[plan.status]}
          tone={statusTones[plan.status]}
          compact
        />
      </span>
      <span className={styles.cardTitle}>{plan.issue}</span>
      <span className={styles.cardTime}>
        <Clock3 size={11} /> {formatTime(plan.startsAt)}–{formatTime(plan.endsAt)} ·{" "}
        {plan.durationHours}h
      </span>
      <span className={styles.cardMeta}>
        <span>{plan.crew.label}</span>
        <span>{windowLabels[plan.weather.state]}</span>
      </span>
      <span className={styles.cardFooter}>
        <span className={styles.readinessMini}>就绪 {plan.readinessPercent}%</span>
        <span data-alert={plan.conflicts.some((item) => item.severity === "critical")}>
          <AlertTriangle size={11} /> {plan.conflicts.length}
        </span>
      </span>
    </button>
  );
}

function PlanDetail({ plan }: { plan: MaintenancePlan }) {
  const criticalConflicts = plan.conflicts.filter((item) => item.severity === "critical").length;
  return (
    <aside className={styles.detailPanel} aria-label={`${plan.workOrderId} 计划详情`}>
      <header className={styles.detailHeader}>
        <div>
          <span className={styles.detailEyebrow}>SELECTED PLAN · READ ONLY</span>
          <h2>{plan.turbineId}</h2>
          <p>{plan.issue}</p>
        </div>
        <StatusBadge
          value={plan.status}
          label={statusLabels[plan.status]}
          tone={statusTones[plan.status]}
        />
      </header>

      <div className={styles.detailSchedule}>
        <span>
          <small>计划时段</small>
          <strong>
            {formatDateTime(plan.startsAt)}–{formatTime(plan.endsAt)}
          </strong>
        </span>
        <span>
          <small>工单 / 风险</small>
          <strong>
            {plan.workOrderId} · {riskLabels[plan.risk]}风险
          </strong>
        </span>
      </div>

      <div className={styles.readinessBlock}>
        <span>
          <small>RESOURCE READINESS</small>
          <strong>{plan.readinessPercent}%</strong>
        </span>
        <Progress
          value={plan.readinessPercent}
          tone={
            criticalConflicts ? "critical" : plan.readinessPercent >= 85 ? "success" : "warning"
          }
          label={`${plan.workOrderId} 资源就绪度 ${plan.readinessPercent}%`}
        />
        <p>任务完成 {plan.taskProgressPercent}% · 数据来自演示台账，不执行真实资源预留。</p>
      </div>

      <section className={styles.weatherBlock} data-state={plan.weather.state}>
        <header>
          <span>
            <CloudSun size={15} /> 天气窗口
          </span>
          <StatusBadge
            value={plan.weather.state}
            label={windowLabels[plan.weather.state]}
            tone={windowTone(plan.weather.state)}
            compact
          />
        </header>
        {plan.weather.id ? (
          <div className={styles.weatherMetrics}>
            <span>
              <strong>{plan.weather.windSpeedMps} m/s</strong>
              <small>风速</small>
            </span>
            <span>
              <strong>{plan.weather.waveHeightM} m</strong>
              <small>浪高</small>
            </span>
            <span>
              <strong>{plan.weather.visibilityKm} km</strong>
              <small>能见度</small>
            </span>
          </div>
        ) : null}
        <p>{plan.weather.reason}</p>
      </section>

      <ResourceRows
        icon={<UsersRound size={14} />}
        title="维护班组"
        items={[plan.crew]}
        empty="未指定班组"
      />
      <ResourceRows
        icon={<ShipWheel size={14} />}
        title="作业船舶"
        items={plan.vessels}
        empty="远程任务或历史工单无需船舶"
      />
      <ResourceRows
        icon={<PackageCheck size={14} />}
        title="备件"
        items={plan.spareParts}
        empty="本次计划无备件需求"
      />
      <ResourceRows
        icon={<Wrench size={14} />}
        title="工具"
        items={plan.tools}
        empty="本次计划无专业工具需求"
      />

      <section className={styles.conflictSection}>
        <header>
          <span>
            <AlertTriangle size={14} /> 冲突与风险
          </span>
          <strong>{plan.conflicts.length}</strong>
        </header>
        {plan.conflicts.length ? (
          <ul>
            {plan.conflicts.map((conflict) => (
              <li key={`${conflict.code}-${conflict.message}`} data-severity={conflict.severity}>
                <span />
                <div>
                  <strong>{conflict.code.replaceAll("_", " ")}</strong>
                  <p>{conflict.message}</p>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.noConflict}>
            <CheckCircle2 size={14} /> 未发现资源或窗口冲突
          </p>
        )}
      </section>

      <footer className={styles.detailLinks}>
        <Link href={`/turbines/${plan.turbineId}`}>
          查看机组 <ChevronRight size={13} />
        </Link>
        <Link href="/work-orders">
          查看工单 <ChevronRight size={13} />
        </Link>
      </footer>
    </aside>
  );
}

export function MaintenancePlanPage() {
  const workflow = useDemoWorkflow();
  const [view, setView] = useState<ViewMode>("calendar");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [risk, setRisk] = useState<RiskFilter>("all");
  const [team, setTeam] = useState("all");
  const [windowState, setWindowState] = useState<WindowFilter>("all");
  const [selectedId, setSelectedId] = useState(featuredWorkOrderId);

  const currentPlans = useMemo(
    () =>
      createMaintenancePlans({
        featuredWorkOrderStatus: workflow.workOrderStatus,
        featuredCompletedTaskIds: workflow.completedTaskIds,
      }),
    [workflow.completedTaskIds, workflow.workOrderStatus],
  );
  const teamFacets = useMemo(() => maintenancePlanTeamFacets(currentPlans), [currentPlans]);

  const endpoint = useMemo(() => {
    const params = new URLSearchParams({ sort: "start-asc", limit: "50" });
    if (query.trim()) params.set("q", query.trim());
    if (status !== "all") params.set("status", status);
    if (risk !== "all") params.set("risk", risk);
    if (team !== "all") params.set("team", team);
    if (windowState !== "all") params.set("window", windowState);
    return `/api/maintenance-plans?${params.toString()}`;
  }, [query, risk, status, team, windowState]);

  const planQuery = useQuery({
    queryKey: ["maintenance-plans", endpoint],
    queryFn: ({ signal }) => apiGet<MaintenancePlanResponse>(endpoint, signal),
    initialData: {
      data: currentPlans,
      meta: {
        count: currentPlans.length,
        total: currentPlans.length,
        filteredTotal: currentPlans.length,
        model: maintenancePlanMeta,
      },
    },
    initialDataUpdatedAt: 0,
    staleTime: 0,
  });

  const visiblePlans = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const featured = currentPlans.find((plan) => plan.workOrderId === featuredWorkOrderId);
    return planQuery.data.data
      .map((plan) => (plan.workOrderId === featuredWorkOrderId && featured ? featured : plan))
      .filter(
        (plan) =>
          (!normalized ||
            `${plan.id} ${plan.workOrderId} ${plan.turbineId} ${plan.issue} ${plan.assignedTeam}`
              .toLowerCase()
              .includes(normalized)) &&
          (status === "all" || plan.status === status) &&
          (risk === "all" || plan.risk === risk) &&
          (team === "all" || plan.teamKey === team) &&
          (windowState === "all" || plan.weather.state === windowState),
      );
  }, [currentPlans, planQuery.data.data, query, risk, status, team, windowState]);

  const selectedPlan =
    visiblePlans.find((plan) => plan.workOrderId === selectedId) ?? visiblePlans[0] ?? null;
  const calendarDays = useMemo(
    () => [...new Set(visiblePlans.map((plan) => plan.dayKey))].sort(),
    [visiblePlans],
  );
  const activePlans = visiblePlans.filter((plan) =>
    ["ready", "at-risk", "in-progress"].includes(plan.status),
  ).length;
  const conflictPlans = visiblePlans.filter((plan) =>
    plan.conflicts.some((conflict) => conflict.severity === "critical"),
  ).length;
  const averageReadiness = visiblePlans.length
    ? Math.round(
        visiblePlans.reduce((total, plan) => total + plan.readinessPercent, 0) /
          visiblePlans.length,
      )
    : 0;
  const nextSafeWindow = currentPlans.find(
    (plan) => plan.weather.state === "suitable" && plan.status !== "completed",
  );
  const hasFilters =
    Boolean(query) || status !== "all" || risk !== "all" || team !== "all" || windowState !== "all";

  const resetFilters = () => {
    setQuery("");
    setStatus("all");
    setRisk("all");
    setTeam("all");
    setWindowState("all");
  };

  return (
    <AppShell activePath="/maintenance">
      <PageHeader
        eyebrow="执行与维护"
        title="维护计划"
        description="把工单、天气窗口、班组、船舶、备件与工具编排到同一份可审计计划"
        breadcrumb={["执行与维护", "维护计划"]}
        meta={
          <>
            <StatusBadge
              value={planQuery.isError ? "degraded" : "healthy"}
              label={planQuery.isError ? "FALLBACK SNAPSHOT" : "DEMO · READ ONLY"}
            />
            <span className="page-meta-text">
              {workflow.persistence.toUpperCase()} · REV {workflow.serverRevision}
            </span>
          </>
        }
        actions={
          <>
            <Link className="button button--secondary button--md" href="/resources">
              <Anchor size={15} /> 资源中心
            </Link>
            <Link className="button button--primary button--md" href="/work-orders">
              <Wrench size={15} /> 工单中心
            </Link>
          </>
        }
      />

      <section className={styles.demoNotice} aria-label="演示数据声明">
        <CircleGauge size={17} />
        <div>
          <strong>确定性演示排程</strong>
          <p>{maintenancePlanMeta.notice}</p>
        </div>
        <span>{planQuery.isFetching ? "正在核对计划快照" : "计划快照已核对"}</span>
      </section>

      <section className={styles.metricGrid} aria-label="维护计划摘要">
        <article>
          <CalendarDays size={17} />
          <span>
            <small>筛选计划</small>
            <strong>{visiblePlans.length}</strong>
          </span>
        </article>
        <article>
          <CheckCircle2 size={17} />
          <span>
            <small>可执行 / 执行中</small>
            <strong>{activePlans}</strong>
          </span>
        </article>
        <article data-tone={conflictPlans ? "critical" : "success"}>
          <AlertTriangle size={17} />
          <span>
            <small>关键冲突</small>
            <strong>{conflictPlans}</strong>
          </span>
        </article>
        <article>
          <CircleGauge size={17} />
          <span>
            <small>平均就绪度</small>
            <strong>{averageReadiness}%</strong>
          </span>
        </article>
        <article>
          <CloudSun size={17} />
          <span>
            <small>下一安全窗口</small>
            <strong>{nextSafeWindow ? formatDate(nextSafeWindow.startsAt) : "—"}</strong>
          </span>
        </article>
      </section>

      <section className={styles.toolbar} aria-label="维护计划筛选">
        <label className={styles.searchBox}>
          <Search size={14} />
          <span className={styles.visuallyHidden}>搜索维护计划</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索机组、工单、班组或作业内容"
          />
        </label>
        <label>
          <span>状态</span>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as StatusFilter)}
          >
            <option value="all">全部状态</option>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>风险</span>
          <select value={risk} onChange={(event) => setRisk(event.target.value as RiskFilter)}>
            <option value="all">全部风险</option>
            {Object.entries(riskLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>班组</span>
          <select value={team} onChange={(event) => setTeam(event.target.value)}>
            <option value="all">全部班组</option>
            {teamFacets.map((facet) => (
              <option key={facet.value} value={facet.value}>
                {facet.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>窗口</span>
          <select
            value={windowState}
            onChange={(event) => setWindowState(event.target.value as WindowFilter)}
          >
            <option value="all">全部窗口</option>
            {Object.entries(windowLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className={styles.resetButton}
          onClick={resetFilters}
          disabled={!hasFilters}
        >
          <FilterX size={14} /> 清除
        </button>
        <div className={styles.viewToggle} role="group" aria-label="计划视图">
          <button
            type="button"
            aria-pressed={view === "calendar"}
            onClick={() => setView("calendar")}
          >
            <CalendarDays size={14} /> 日历
          </button>
          <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}>
            <LayoutList size={14} /> 列表
          </button>
        </div>
      </section>

      <div className={styles.workspace}>
        <section className={styles.schedulePanel} aria-label="维护计划排程">
          <header className={styles.panelHeader}>
            <div>
              <span>MAINTENANCE SCHEDULE</span>
              <h2>{view === "calendar" ? "计划日历" : "计划清单"}</h2>
            </div>
            <small>
              {visiblePlans.length} / {currentPlans.length} 项 · Asia/Shanghai
            </small>
          </header>

          {!visiblePlans.length ? (
            <EmptyState
              icon={<Search size={20} />}
              title="没有匹配计划"
              description="调整筛选条件或清除筛选后重试。"
            />
          ) : view === "calendar" ? (
            <div className={styles.calendarScroll}>
              <div
                className={styles.calendarGrid}
                style={{
                  gridTemplateColumns: `repeat(${calendarDays.length}, minmax(190px, 1fr))`,
                }}
              >
                {calendarDays.map((day) => {
                  const dayPlans = visiblePlans.filter((plan) => plan.dayKey === day);
                  return (
                    <section key={day} className={styles.dayColumn}>
                      <header>
                        <strong>{formatDate(`${day}T12:00:00+08:00`)}</strong>
                        <span>{dayPlans.length} 项</span>
                      </header>
                      <div>
                        {dayPlans.map((plan) => (
                          <PlanCard
                            key={plan.id}
                            plan={plan}
                            selected={selectedPlan?.id === plan.id}
                            onSelect={() => setSelectedId(plan.workOrderId)}
                          />
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className={styles.tableScroll}>
              <DataTable
                data={visiblePlans}
                columns={planColumns}
                getRowId={(plan) => plan.id}
                selectedRowId={selectedPlan?.id}
                onRowActivate={(plan) => setSelectedId(plan.workOrderId)}
                initialSorting={[{ id: "startsAt", desc: false }]}
                pageSize={6}
                searchTextForRow={(plan) =>
                  `${plan.id} ${plan.workOrderId} ${plan.turbineId} ${plan.issue} ${plan.assignedTeam}`
                }
                searchPlaceholder="在当前计划清单内搜索…"
                bulkActions={[
                  {
                    label: "复制工单编号",
                    onActivate: (plans) =>
                      navigator.clipboard.writeText(
                        plans.map((plan) => plan.workOrderId).join("\n"),
                      ),
                  },
                ]}
                csvExport={{
                  filename: "windops-maintenance-plans.csv",
                  columns: [
                    { label: "计划ID", value: (plan) => plan.id },
                    { label: "工单", value: (plan) => plan.workOrderId },
                    { label: "机组", value: (plan) => plan.turbineId },
                    { label: "作业内容", value: (plan) => plan.issue },
                    { label: "开始时间", value: (plan) => plan.startsAt },
                    { label: "结束时间", value: (plan) => plan.endsAt },
                    { label: "状态", value: (plan) => statusLabels[plan.status] },
                    { label: "班组", value: (plan) => plan.crew.label },
                    { label: "就绪度", value: (plan) => plan.readinessPercent },
                  ],
                }}
              />
            </div>
          )}
        </section>

        {selectedPlan ? <PlanDetail plan={selectedPlan} /> : null}
      </div>
    </AppShell>
  );
}
