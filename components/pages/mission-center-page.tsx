"use client";

import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Bot,
  CalendarDays,
  CheckCircle2,
  CircleDot,
  Clock3,
  GitBranch,
  LayoutGrid,
  List,
  Plus,
  Search,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import { DataTable } from "@/components/data-display/data-table";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Avatar, Button, Card, EmptyState, Progress } from "@/components/ui/primitives";
import { QueryStateNotice, RuntimeHealthBadge } from "@/components/ui/query-state";
import { StatusBadge } from "@/components/data-display/status-badge";
import { agents } from "@/lib/agent-data";
import { getFeaturedMissionNarrative } from "@/lib/demo-workflow";
import { missions } from "@/lib/operations-data";
import type { Mission, MissionStatus } from "@/lib/types";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { cn } from "@/lib/utils";
import { localizedMissionTitle, localizedSeverityLabel } from "@/lib/ui-localization";
import { agentDisplayName } from "@/lib/agent-control-meta";
import { apiGet, apiPostCommand } from "@/lib/api-client";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";
import type { Alarm } from "@/lib/types";
import {
  deriveQueryViewState,
  latestValidTimestamp,
  mergeRuntimeHealth,
  queryRuntimeHealth,
} from "@/lib/query-state";

const columns: { status: MissionStatus; label: string; description: string }[] = [
  { status: "detected", label: "已发现", description: "新发现事件" },
  { status: "investigating", label: "调查中", description: "收集与分析证据" },
  { status: "diagnosed", label: "已诊断", description: "已形成故障判断" },
  { status: "decision-pending", label: "等待决策", description: "生成候选方案" },
  { status: "under-review", label: "审核中", description: "专业审核中" },
  { status: "approved", label: "已批准", description: "等待执行资源" },
  { status: "executing", label: "执行中", description: "现场任务进行中" },
  { status: "rejected", label: "已拒绝", description: "人工审核已拒绝" },
  { status: "completed", label: "已完成", description: "已完成闭环" },
];

const severityOptions: readonly Mission["severity"][] = ["critical", "high", "medium", "low"];

type MissionView = "kanban" | "list" | "timeline";
type SeverityFilter = "all" | Mission["severity"];

function severityTone(severity: Mission["severity"]) {
  if (severity === "critical") return "critical";
  if (severity === "high") return "warning";
  if (severity === "medium") return "info";
  return "neutral";
}

function statusLabel(status: MissionStatus) {
  return columns.find((column) => column.status === status)?.label ?? status;
}

function formatUpdatedAt(timestamp: string) {
  return new Date(timestamp).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatResolutionDuration(minutes: number) {
  const rounded = Math.round(minutes);
  if (rounded < 60) return `${rounded}m`;
  return `${Math.floor(rounded / 60)}h ${rounded % 60}m`;
}

function MissionCard({ mission }: { mission: Mission }) {
  const lead = agents.find((agent) => agent.id === mission.leadAgentId);
  return (
    <a
      className={cn("kanban-card", mission.id === "MISSION-2026-0823" && "kanban-card--featured")}
      href={`/missions/${mission.id}`}
    >
      <div className="kanban-card__header">
        <span className="mono">{mission.id}</span>
        <StatusBadge
          value={mission.severity}
          label={localizedSeverityLabel(mission.severity)}
          tone={severityTone(mission.severity)}
          compact
        />
      </div>
      <div className="kanban-card__copy">
        <strong>{localizedMissionTitle(mission.title)}</strong>
        <span>
          {mission.turbineId} · {mission.summary}
        </span>
      </div>
      {mission.diagnosis ? (
        <div className="kanban-diagnosis">
          <Bot size={12} />
          <span>{mission.diagnosis}</span>
          {mission.confidencePercent ? <strong>{mission.confidencePercent}%</strong> : null}
        </div>
      ) : null}
      <div className="kanban-card__progress">
        <span>
          <small>进度</small>
          <strong>{mission.progressPercent}%</strong>
        </span>
        <Progress
          value={mission.progressPercent}
          tone={mission.severity === "critical" || mission.severity === "high" ? "warning" : "info"}
        />
      </div>
      <div className="kanban-card__meta">
        <span>
          <Avatar
            label={lead ? agentDisplayName(lead.id, lead.shortName) : "AI"}
            tone="teal"
            size="sm"
          />
          <span>
            <small>主导 Agent</small>
            <strong>{lead ? agentDisplayName(lead.id, lead.shortName) : "未指派"}</strong>
          </span>
        </span>
        <span>
          <Users size={12} /> {mission.agentIds.length}
        </span>
      </div>
      <div className="kanban-card__footer">
        <span>
          <Clock3 size={11} /> {formatUpdatedAt(mission.updatedAt)}
        </span>
        <ArrowRight size={13} />
      </div>
    </a>
  );
}

const missionListColumns: readonly LegacyColumnDef<Mission, unknown>[] = [
  {
    accessorKey: "title",
    header: "Mission",
    cell: ({ row }) => (
      <span className="alarm-title-cell">
        <strong>{localizedMissionTitle(row.original.title)}</strong>
        <small className="mono">{row.original.id}</small>
      </span>
    ),
    size: 280,
  },
  {
    accessorKey: "status",
    header: "状态",
    cell: ({ row }) => (
      <StatusBadge value={row.original.status} label={statusLabel(row.original.status)} compact />
    ),
  },
  {
    accessorKey: "severity",
    header: "严重度",
    cell: ({ row }) => (
      <StatusBadge
        value={row.original.severity}
        label={localizedSeverityLabel(row.original.severity)}
        tone={severityTone(row.original.severity)}
        compact
      />
    ),
  },
  {
    accessorKey: "turbineId",
    header: "机组",
    cell: ({ row }) => <span className="mono">{row.original.turbineId}</span>,
  },
  {
    accessorKey: "leadAgentId",
    header: "主导 Agent",
    cell: ({ row }) =>
      (() => {
        const agent = agents.find((candidate) => candidate.id === row.original.leadAgentId);
        return agent ? agentDisplayName(agent.id, agent.shortName) : "未指派";
      })(),
  },
  {
    accessorKey: "progressPercent",
    header: "进度",
    cell: ({ row }) => (
      <span>
        <strong>{row.original.progressPercent}%</strong>
        <Progress value={row.original.progressPercent} />
      </span>
    ),
  },
  {
    accessorKey: "updatedAt",
    header: "更新时间",
    cell: ({ row }) => <span className="mono">{formatUpdatedAt(row.original.updatedAt)}</span>,
  },
];

const missionCsvExport = {
  filename: "openvigil-missions.csv",
  columns: [
    { label: "Mission ID", value: (mission: Mission) => mission.id },
    { label: "标题", value: (mission: Mission) => localizedMissionTitle(mission.title) },
    { label: "状态", value: (mission: Mission) => statusLabel(mission.status) },
    { label: "严重度", value: (mission: Mission) => localizedSeverityLabel(mission.severity) },
    { label: "风机", value: (mission: Mission) => mission.turbineId },
    {
      label: "主导 Agent",
      value: (mission: Mission) => {
        const agent = agents.find((item) => item.id === mission.leadAgentId);
        return agent ? agentDisplayName(agent.id, agent.shortName) : mission.leadAgentId;
      },
    },
    { label: "Agent 数", value: (mission: Mission) => mission.agentIds.length },
    { label: "进度", value: (mission: Mission) => mission.progressPercent },
    { label: "更新时间", value: (mission: Mission) => mission.updatedAt },
  ],
} as const;

const missionSearchText = (mission: Mission): string =>
  `${mission.id} ${mission.title} ${mission.turbineId} ${mission.summary} ${mission.diagnosis ?? ""}`;

const missionRowId = (mission: Mission): string => mission.id;

function MissionList({
  items,
  filterControls,
}: {
  readonly items: readonly Mission[];
  readonly filterControls: ReactNode;
}) {
  return (
    <DataTable
      bulkActions={[
        {
          label: "打开首个所选 Mission",
          onActivate: (rows) => {
            const mission = rows[0];
            if (mission) window.location.assign(`/missions/${mission.id}`);
          },
        },
      ]}
      columns={missionListColumns}
      csvExport={missionCsvExport}
      data={items}
      emptyMessage="没有符合当前筛选条件的 Mission。"
      filterControls={filterControls}
      getRowId={missionRowId}
      initialSorting={[{ id: "updatedAt", desc: true }]}
      onRowActivate={(mission) => window.location.assign(`/missions/${mission.id}`)}
      pageSize={6}
      searchPlaceholder="搜索 Mission、机组或故障…"
      searchTextForRow={missionSearchText}
      selectedRowId="MISSION-2026-0823"
    />
  );
}

function MissionTimeline({ items }: { items: readonly Mission[] }) {
  const ordered = [...items].sort(
    (left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime(),
  );

  return (
    <Card className="mission-timeline-card" aria-label="Mission 更新时间线">
      <div className="mission-timeline">
        {ordered.map((mission, index) => {
          const lead = agents.find((agent) => agent.id === mission.leadAgentId);
          const completed = mission.status === "completed";
          const attention =
            mission.status === "under-review" || mission.status === "decision-pending";
          const nodeTone = completed ? "success" : attention ? "attention" : "in-progress";
          const EventIcon = completed ? CheckCircle2 : CircleDot;
          return (
            <div
              className={cn("timeline-event", index === 0 && "timeline-event--current")}
              key={mission.id}
            >
              <time dateTime={mission.updatedAt}>{formatUpdatedAt(mission.updatedAt)}</time>
              <span className={`timeline-event__node timeline-event__node--${nodeTone}`}>
                <EventIcon size={13} />
              </span>
              <div className="timeline-event__body">
                <div>
                  <span>
                    <Avatar
                      label={lead ? agentDisplayName(lead.id, lead.shortName) : "AI"}
                      tone="teal"
                      size="sm"
                    />
                    <span>
                      <strong>{lead ? agentDisplayName(lead.id, lead.shortName) : "未指派"}</strong>
                      <small>{statusLabel(mission.status)}</small>
                    </span>
                  </span>
                  <StatusBadge value={mission.status} label={statusLabel(mission.status)} compact />
                </div>
                <a href={`/missions/${mission.id}`}>
                  <h3>
                    {mission.id} · {localizedMissionTitle(mission.title)}
                  </h3>
                </a>
                <p>
                  {mission.turbineId} · {mission.summary} 下一步：{mission.nextAction}
                </p>
              </div>
            </div>
          );
        })}
        {ordered.length === 0 ? (
          <div className="command-empty">没有符合当前筛选条件的 Mission。</div>
        ) : null}
      </div>
    </Card>
  );
}

function CreateMissionDrawer({
  alarms,
  preferredTurbineId,
  onClose,
  onCreated,
}: {
  readonly alarms: readonly Alarm[];
  readonly preferredTurbineId: string | null;
  readonly onClose: () => void;
  readonly onCreated: () => Promise<void>;
}) {
  const eligibleAlarms = alarms.filter((alarm) => alarm.missionId === null);
  const preferred =
    eligibleAlarms.find((alarm) => alarm.turbineId === preferredTurbineId) ?? eligibleAlarms[0];
  const [alarmId, setAlarmId] = useState(preferred?.id ?? "");
  const [title, setTitle] = useState(
    preferred ? `${preferred.turbineId} ${preferred.title} Investigation` : "",
  );
  const [component, setComponent] = useState(preferred?.subsystem.replaceAll("-", "_") ?? "");
  const [primaryVariable, setPrimaryVariable] = useState(
    preferred
      ? (preferred.sourceVariable ?? `${preferred.subsystem.replaceAll("-", "_")}_condition_signal`)
      : "",
  );
  const [knowledgeQuery, setKnowledgeQuery] = useState(
    preferred ? `${preferred.subsystem.replaceAll("-", " ")} inspection failure diagnosis` : "",
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose);

  function selectAlarm(nextAlarmId: string) {
    setAlarmId(nextAlarmId);
    const alarm = eligibleAlarms.find((item) => item.id === nextAlarmId);
    if (!alarm) return;
    const nextComponent = alarm.subsystem.replaceAll("-", "_");
    setTitle(`${alarm.turbineId} ${alarm.title} Investigation`);
    setComponent(nextComponent);
    setPrimaryVariable(alarm.sourceVariable ?? `${nextComponent}_condition_signal`);
    setKnowledgeQuery(`${nextComponent.replaceAll("_", " ")} inspection failure diagnosis`);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await apiPostCommand(
        "/api/missions",
        {
          alarm_id: alarmId,
          title,
          analysis_profile: {
            component,
            primary_variable: primaryVariable,
            related_variables: [],
            knowledge_query: knowledgeQuery,
          },
        },
        `mission-create-${crypto.randomUUID()}`,
      );
      await onCreated();
      onClose();
    } catch (submissionError) {
      setError(
        submissionError instanceof Error ? submissionError.message : "Mission 创建请求失败。",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <button className="drawer-backdrop" onClick={onClose} aria-label="关闭 Mission 创建面板" />
      <aside
        ref={dialogRef}
        className="detail-drawer mission-create-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-mission-title"
        tabIndex={-1}
      >
        <header className="detail-drawer__header">
          <div>
            <span className="eyebrow">受控业务命令</span>
            <h2 id="create-mission-title">创建 Mission</h2>
            <p>任务与分析事件将在同一事务中持久化，并支持幂等重试。</p>
          </div>
          <Button variant="ghost" onClick={onClose} aria-label="关闭">
            <X size={15} />
          </Button>
        </header>
        {eligibleAlarms.length ? (
          <form className="mission-create-form" onSubmit={(event) => void submit(event)}>
            <section className="drawer-section">
              <h3>任务来源</h3>
              <label>
                <span>未关联告警</span>
                <select value={alarmId} onChange={(event) => selectAlarm(event.target.value)}>
                  {eligibleAlarms.map((alarm) => (
                    <option value={alarm.id} key={alarm.id}>
                      {alarm.id} · {alarm.turbineId} · {alarm.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Mission 标题</span>
                <input
                  required
                  minLength={3}
                  maxLength={240}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
            </section>
            <section className="drawer-section">
              <h3>可审计分析配置</h3>
              <label>
                <span>部件标识</span>
                <input
                  required
                  minLength={2}
                  maxLength={80}
                  value={component}
                  onChange={(event) => setComponent(event.target.value)}
                />
              </label>
              <label>
                <span>主信号变量</span>
                <input
                  required
                  minLength={2}
                  maxLength={96}
                  value={primaryVariable}
                  onChange={(event) => setPrimaryVariable(event.target.value)}
                />
              </label>
              <label>
                <span>知识检索查询</span>
                <textarea
                  required
                  minLength={3}
                  maxLength={400}
                  rows={4}
                  value={knowledgeQuery}
                  onChange={(event) => setKnowledgeQuery(event.target.value)}
                />
              </label>
            </section>
            {error ? (
              <div className="drawer-alert" role="alert">
                <span className="drawer-alert__icon">
                  <ShieldCheck size={15} />
                </span>
                <span>
                  <strong>创建失败</strong>
                  <small>{error}</small>
                </span>
              </div>
            ) : null}
            <footer className="detail-drawer__footer">
              <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
                取消
              </Button>
              <Button type="submit" variant="primary" disabled={submitting || !alarmId}>
                <Plus size={15} /> {submitting ? "正在提交…" : "创建并启动分析"}
              </Button>
            </footer>
          </form>
        ) : (
          <section className="drawer-section">
            <h3>没有可用告警</h3>
            <p className="muted">所有当前告警都已关联 Mission，或告警列表仍在加载。</p>
          </section>
        )}
      </aside>
    </>
  );
}

export function MissionCenterPage({ runtimeMode }: { runtimeMode: "demo" | "production" }) {
  const workflow = useDemoWorkflow();
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"active" | "all">("active");
  const [view, setView] = useState<MissionView>("kanban");
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [leadAgentId, setLeadAgentId] = useState("all");
  const [turbineScope, setTurbineScope] = useState<string | null>(null);
  const [diagnosisIntent, setDiagnosisIntent] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const missionQuery = useQuery({
    queryKey: ["missions", workflow.serverRevision, runtimeMode],
    queryFn: ({ signal }) => apiGet<{ readonly data: readonly Mission[] }>("/api/missions", signal),
    initialData: runtimeMode === "demo" ? { data: missions } : undefined,
    retry: false,
    staleTime: 60_000,
  });
  const alarmQuery = useQuery({
    queryKey: ["mission-create-alarms", runtimeMode],
    queryFn: ({ signal }) => apiGet<{ readonly data: readonly Alarm[] }>("/api/alarms", signal),
    initialData: runtimeMode === "demo" ? { data: [] } : undefined,
    enabled: runtimeMode === "production",
    retry: false,
    staleTime: 60_000,
  });
  const missionState = deriveQueryViewState({
    data: missionQuery.data?.data,
    dataUpdatedAt: missionQuery.dataUpdatedAt,
    error: missionQuery.error,
    isError: missionQuery.isError,
    isFetching: missionQuery.isFetching,
    isPending: missionQuery.isPending,
    isStale: missionQuery.isStale,
    isEmpty: (data) => data.length === 0,
    sourceUpdatedAt:
      runtimeMode === "production"
        ? latestValidTimestamp(missionQuery.data?.data.map((mission) => mission.updatedAt) ?? [])
        : null,
    staleAfterMs: 60_000,
  });
  const alarmState = deriveQueryViewState({
    data: alarmQuery.data?.data,
    dataUpdatedAt: alarmQuery.dataUpdatedAt,
    error: alarmQuery.error,
    isError: alarmQuery.isError,
    isFetching: alarmQuery.isFetching,
    isPending: alarmQuery.isPending,
    isStale: alarmQuery.isStale,
    isEmpty: (data) => data.length === 0,
  });
  const pageHealth = mergeRuntimeHealth(
    queryRuntimeHealth(missionState, "Mission 台账"),
    runtimeMode === "production"
      ? queryRuntimeHealth(alarmState, "告警选择器", { partial: true })
      : null,
  );
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search)
      .get("turbineId")
      ?.trim()
      .toUpperCase();
    const intent = new URLSearchParams(window.location.search).get("intent");
    if (!requested) return;
    const timer = window.setTimeout(() => {
      setTurbineScope(requested);
      setDiagnosisIntent(intent === "diagnosis");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const featuredNarrative = getFeaturedMissionNarrative(workflow);
  const displayMissions = useMemo(
    () =>
      (missionQuery.data?.data ?? []).map((mission) =>
        runtimeMode === "demo" && mission.id === "MISSION-2026-0823"
          ? {
              ...mission,
              status: workflow.missionStatus,
              progressPercent: workflow.missionProgress,
              summary: featuredNarrative.summary,
              nextAction: featuredNarrative.nextAction,
            }
          : mission,
      ),
    [
      featuredNarrative.nextAction,
      featuredNarrative.summary,
      workflow.missionProgress,
      workflow.missionStatus,
      missionQuery.data?.data,
      runtimeMode,
    ],
  );
  const leadOptions = useMemo<readonly { id: string; shortName: string }[]>(
    () =>
      runtimeMode === "production"
        ? [
            ...new Set(
              displayMissions.map((mission) => mission.leadAgentId).filter((id) => id !== ""),
            ),
          ].map((id) => ({ id, shortName: id }))
        : agents.filter((agent) =>
            displayMissions.some((mission) => mission.leadAgentId === agent.id),
          ),
    [displayMissions, runtimeMode],
  );
  const filteredByControls = useMemo(
    () =>
      displayMissions.filter(
        (mission) =>
          (scope === "all" || !["completed", "rejected"].includes(mission.status)) &&
          (turbineScope === null || mission.turbineId === turbineScope) &&
          (severity === "all" || mission.severity === severity) &&
          (leadAgentId === "all" || mission.leadAgentId === leadAgentId),
      ),
    [displayMissions, leadAgentId, scope, severity, turbineScope],
  );
  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return filteredByControls.filter((mission) =>
      `${mission.id} ${mission.title} ${mission.turbineId} ${mission.summary}`
        .toLowerCase()
        .includes(normalizedQuery),
    );
  }, [filteredByControls, query]);
  const activeCount = displayMissions.filter(
    (mission) => !["completed", "rejected"].includes(mission.status),
  ).length;
  const reviewCount = displayMissions.filter((mission) => mission.status === "under-review").length;
  const executionCount = displayMissions.filter((mission) => mission.status === "executing").length;
  const completedCount = displayMissions.filter((mission) => mission.status === "completed").length;
  // production 下统计真实 Mission 数据；demo 保持 fixture agents 的演示口径。
  const participatingAgentCount =
    runtimeMode === "production"
      ? new Set(
          displayMissions
            .filter((mission) => !["completed", "rejected"].includes(mission.status))
            .map((mission) => mission.leadAgentId)
            .filter((id) => id !== ""),
        ).size
      : agents.filter((agent) => agent.currentMissionId).length;
  const resolutionMinutes = displayMissions
    .filter((mission) => mission.status === "completed")
    .map(
      (mission) =>
        (new Date(mission.updatedAt).getTime() - new Date(mission.createdAt).getTime()) / 60_000,
    )
    .filter((minutes) => Number.isFinite(minutes) && minutes >= 0);
  const averageResolutionMinutes = resolutionMinutes.length
    ? resolutionMinutes.reduce((total, minutes) => total + minutes, 0) / resolutionMinutes.length
    : null;
  const selectView = (nextView: MissionView) => {
    if (nextView === "list") setQuery("");
    setView(nextView);
  };
  const missionFilterControls = (
    <>
      <div className="agent-filter-tabs">
        <button className={cn(scope === "active" && "active")} onClick={() => setScope("active")}>
          活跃
        </button>
        <button className={cn(scope === "all" && "active")} onClick={() => setScope("all")}>
          全部 Mission
        </button>
      </div>
      <label>
        <span className="sr-only">按严重程度筛选</span>
        <select
          className="select-field"
          value={severity}
          onChange={(event) => setSeverity(event.target.value as SeverityFilter)}
        >
          <option value="all">严重度 · 全部</option>
          {severityOptions.map((option) => (
            <option value={option} key={option}>
              严重度 · {localizedSeverityLabel(option)}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="sr-only">按主导 Agent 筛选</span>
        <select
          className="select-field"
          value={leadAgentId}
          onChange={(event) => setLeadAgentId(event.target.value)}
        >
          <option value="all">主导 Agent · 全部</option>
          {leadOptions.map((agent) => (
            <option value={agent.id} key={agent.id}>
              主导 Agent · {agentDisplayName(agent.id, agent.shortName)}
            </option>
          ))}
        </select>
      </label>
      <div className="view-switcher" aria-label="Mission 视图切换">
        <button
          className={cn(view === "kanban" && "active")}
          onClick={() => selectView("kanban")}
          aria-label="看板视图"
          aria-pressed={view === "kanban"}
        >
          <LayoutGrid size={15} />
        </button>
        <button
          className={cn(view === "list" && "active")}
          onClick={() => selectView("list")}
          aria-label="列表视图"
          aria-pressed={view === "list"}
        >
          <List size={15} />
        </button>
        <button
          className={cn(view === "timeline" && "active")}
          onClick={() => selectView("timeline")}
          aria-label="时间线视图"
          aria-pressed={view === "timeline"}
        >
          <CalendarDays size={15} />
        </button>
      </div>
      {turbineScope ? (
        <Button variant="secondary" onClick={() => setTurbineScope(null)}>
          机组 {turbineScope} <X size={12} />
        </Button>
      ) : null}
    </>
  );
  const queryBlocked =
    missionState.lifecycle === "initial-loading" || missionState.lifecycle === "error-no-data";
  const resetMissionFilters = () => {
    setQuery("");
    setScope("all");
    setSeverity("all");
    setLeadAgentId("all");
    setTurbineScope(null);
  };

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/missions" pageHealth={pageHealth}>
      <PageHeader
        eyebrow="AI 运营"
        title="Mission 中心"
        description="跟踪多 Agent 从异常发现、诊断决策到运维执行的完整生命周期"
        breadcrumb={["AI 运营", "Mission 中心"]}
        meta={
          <>
            <RuntimeHealthBadge health={pageHealth} />
            <span className="page-meta-text">
              {missionState.hasData
                ? `${activeCount} 活跃 · ${reviewCount} 待审核 · ${executionCount} 执行中 · ${completedCount} 已完成`
                : "等待 Mission 权威台账"}
            </span>
          </>
        }
        actions={
          <>
            <Button
              variant={view === "timeline" ? "primary" : "secondary"}
              onClick={() => selectView("timeline")}
              aria-pressed={view === "timeline"}
            >
              <CalendarDays size={15} /> 时间线
            </Button>
            <span
              title={
                runtimeMode === "production"
                  ? "创建受控 Mission"
                  : "演示环境未连接 Mission 写入后端"
              }
            >
              <Button
                variant="primary"
                disabled={
                  runtimeMode !== "production" ||
                  missionState.health !== "ready" ||
                  alarmState.health !== "ready"
                }
                aria-describedby="create-mission-help"
                onClick={() => setCreateOpen(true)}
              >
                <Plus size={15} /> 创建 Mission
              </Button>
            </span>
            <span id="create-mission-help" className="sr-only">
              {runtimeMode === "production"
                ? "创建命令将写入权威后端并启动受控分析。"
                : "创建 Mission 在当前只读演示环境中不可用，因为尚未连接写入后端。"}
            </span>
          </>
        }
      />

      {queryBlocked ? (
        <QueryStateNotice
          state={missionState}
          target="Mission 台账"
          impact="Mission 数量、阶段、筛选结果与创建入口"
          onRetry={() => void missionQuery.refetch()}
        />
      ) : (
        <>
          <QueryStateNotice
            state={missionState}
            target="Mission 台账"
            impact="现有 Mission 内容"
            onRetry={() => void missionQuery.refetch()}
          />
          {runtimeMode === "production" ? (
            <QueryStateNotice
              state={alarmState}
              target="Mission 创建所需的告警数据"
              impact="创建入口"
              onRetry={() => void alarmQuery.refetch()}
              partial
            />
          ) : null}

          {diagnosisIntent ? (
            <section className="controlled-entry-note" role="status">
              <ShieldCheck size={16} />
              <span>
                <strong>已打开受控诊断入口</strong>
                <small>
                  资产范围：{turbineScope ?? "未指定"}。
                  {runtimeMode === "production"
                    ? "可从未关联告警创建持久化 Mission，并启动受控 Agent 分析。"
                    : "演示模式只展示现有诊断 Mission，不会假启动 Agent 流程。"}
                </small>
              </span>
              <Button
                variant="ghost"
                onClick={() => setDiagnosisIntent(false)}
                aria-label="关闭受控入口提示"
              >
                <X size={14} />
              </Button>
            </section>
          ) : null}

          <section className="mission-summary">
            <div>
              <span className="mission-summary__icon mission-summary__icon--info">
                <GitBranch size={16} />
              </span>
              <span>
                <small>活跃</small>
                <strong>{activeCount}</strong>
              </span>
            </div>
            <div>
              <span className="mission-summary__icon mission-summary__icon--warning">
                <ShieldCheck size={16} />
              </span>
              <span>
                <small>等待审核</small>
                <strong>{reviewCount}</strong>
              </span>
            </div>
            <div>
              <span className="mission-summary__icon mission-summary__icon--maintenance">
                <Bot size={16} />
              </span>
              <span>
                <small>参与 AGENT</small>
                <strong>{participatingAgentCount}</strong>
              </span>
            </div>
            <div>
              <span className="mission-summary__icon mission-summary__icon--success">
                <CheckCircle2 size={16} />
              </span>
              <span>
                <small>今日完成</small>
                <strong>{completedCount}</strong>
              </span>
            </div>
            <div className="mission-throughput">
              <span>
                <small>平均解决时长</small>
                <strong>
                  {runtimeMode === "production"
                    ? averageResolutionMinutes === null
                      ? "—"
                      : formatResolutionDuration(averageResolutionMinutes)
                    : "4h 18m"}
                </strong>
              </span>
              <em>
                {runtimeMode === "production"
                  ? averageResolutionMinutes === null
                    ? "暂无已闭环 Mission，无法计算"
                    : `基于 ${resolutionMinutes.length} 个已闭环 Mission 计算`
                  : "较 7 日均值下降 12%"}
              </em>
            </div>
          </section>

          {view === "list" ? null : (
            <section className="data-toolbar mission-toolbar">
              <div className="search-field">
                <Search size={15} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索 Mission、机组或故障…"
                  aria-label="搜索 Mission"
                />
              </div>
              {missionFilterControls}
              <span className="toolbar-result">{filtered.length} 个 Mission</span>
            </section>
          )}

          {displayMissions.length === 0 ? (
            <EmptyState
              icon={<GitBranch size={22} />}
              title="当前范围内没有 Mission"
              description="权威 Mission 台账已成功返回空结果；这不是加载或服务错误。"
            />
          ) : filtered.length === 0 && view !== "list" ? (
            <EmptyState
              icon={<Search size={22} />}
              title="筛选结果为空"
              description="Mission 台账中存在记录，但当前搜索或筛选条件没有匹配项。"
              action={
                <Button variant="secondary" onClick={resetMissionFilters}>
                  清除筛选
                </Button>
              }
            />
          ) : view === "kanban" ? (
            <section className="mission-kanban" aria-label="Mission 状态看板">
              {columns.map((column) => {
                const columnMissions = filtered.filter(
                  (mission) => mission.status === column.status,
                );
                return (
                  <div className="kanban-column" key={column.status}>
                    <header>
                      <span>
                        <i className={`kanban-status-dot kanban-status-dot--${column.status}`} />
                        <strong>{column.label}</strong>
                        <em>{columnMissions.length}</em>
                      </span>
                      <small>{column.description}</small>
                    </header>
                    <div className="kanban-column__body">
                      {columnMissions.map((mission) => (
                        <MissionCard key={mission.id} mission={mission} />
                      ))}
                      {columnMissions.length === 0 ? (
                        <div className="kanban-empty">
                          <CircleDot size={15} />
                          <span>暂无 Mission</span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </section>
          ) : view === "list" ? (
            <MissionList items={filteredByControls} filterControls={missionFilterControls} />
          ) : (
            <MissionTimeline items={filtered} />
          )}
          {createOpen ? (
            <CreateMissionDrawer
              alarms={alarmQuery.data?.data ?? []}
              preferredTurbineId={turbineScope}
              onClose={() => setCreateOpen(false)}
              onCreated={async () => {
                await Promise.all([missionQuery.refetch(), alarmQuery.refetch()]);
              }}
            />
          ) : null}
        </>
      )}
    </AppShell>
  );
}
