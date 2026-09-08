"use client";

import { useMemo, useState } from "react";
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
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Avatar, Button, Card, Progress } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { agents, getFeaturedMissionNarrative, missions } from "@/lib";
import type { Mission, MissionStatus } from "@/lib/types";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { cn } from "@/lib/utils";

const columns: { status: MissionStatus; label: string; description: string }[] = [
  { status: "detected", label: "Detected", description: "新发现事件" },
  { status: "investigating", label: "Investigating", description: "收集与分析证据" },
  { status: "diagnosed", label: "Diagnosed", description: "已形成故障判断" },
  { status: "decision-pending", label: "Decision Pending", description: "生成候选方案" },
  { status: "under-review", label: "Under Review", description: "专业审核中" },
  { status: "approved", label: "Approved", description: "等待执行资源" },
  { status: "executing", label: "Executing", description: "现场任务进行中" },
  { status: "completed", label: "Completed", description: "已完成闭环" },
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
          label={mission.severity.toUpperCase()}
          tone={severityTone(mission.severity)}
          compact
        />
      </div>
      <div className="kanban-card__copy">
        <strong>{mission.title}</strong>
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
          <small>Progress</small>
          <strong>{mission.progressPercent}%</strong>
        </span>
        <Progress
          value={mission.progressPercent}
          tone={mission.severity === "critical" || mission.severity === "high" ? "warning" : "info"}
        />
      </div>
      <div className="kanban-card__meta">
        <span>
          <Avatar label={lead?.shortName ?? "AI"} tone="teal" size="sm" />
          <span>
            <small>Lead Agent</small>
            <strong>{lead?.shortName ?? "Unassigned"}</strong>
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

function MissionList({ items }: { items: readonly Mission[] }) {
  return (
    <Card className="data-table-card">
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Mission</th>
              <th>状态</th>
              <th>严重度</th>
              <th>机组</th>
              <th>Lead Agent</th>
              <th>进度</th>
              <th>更新时间</th>
              <th>
                <span className="sr-only">操作</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((mission) => {
              const lead = agents.find((agent) => agent.id === mission.leadAgentId);
              return (
                <tr key={mission.id}>
                  <td>
                    <strong>{mission.title}</strong>
                    <span className="mono">{mission.id}</span>
                  </td>
                  <td>
                    <StatusBadge
                      value={mission.status}
                      label={statusLabel(mission.status)}
                      compact
                    />
                  </td>
                  <td>
                    <StatusBadge
                      value={mission.severity}
                      label={mission.severity.toUpperCase()}
                      tone={severityTone(mission.severity)}
                      compact
                    />
                  </td>
                  <td className="mono">{mission.turbineId}</td>
                  <td>{lead?.shortName ?? "Unassigned"}</td>
                  <td>
                    <strong>{mission.progressPercent}%</strong>
                    <Progress value={mission.progressPercent} />
                  </td>
                  <td className="mono">{formatUpdatedAt(mission.updatedAt)}</td>
                  <td>
                    <a href={`/missions/${mission.id}`} aria-label={`查看 ${mission.id}`}>
                      <ArrowRight size={15} />
                    </a>
                  </td>
                </tr>
              );
            })}
            {items.length === 0 ? (
              <tr>
                <td colSpan={8}>没有符合当前筛选条件的 Mission。</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Card>
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
                    <Avatar label={lead?.shortName ?? "AI"} tone="teal" size="sm" />
                    <span>
                      <strong>{lead?.shortName ?? "Unassigned"}</strong>
                      <small>{statusLabel(mission.status)}</small>
                    </span>
                  </span>
                  <StatusBadge value={mission.status} label={statusLabel(mission.status)} compact />
                </div>
                <a href={`/missions/${mission.id}`}>
                  <h3>
                    {mission.id} · {mission.title}
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

export function MissionCenterPage() {
  const workflow = useDemoWorkflow();
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"active" | "all">("active");
  const [view, setView] = useState<MissionView>("kanban");
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [leadAgentId, setLeadAgentId] = useState("all");
  const featuredNarrative = getFeaturedMissionNarrative(workflow);
  const displayMissions = useMemo(
    () =>
      missions.map((mission) =>
        mission.id === "MISSION-2026-0823"
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
    ],
  );
  const leadOptions = useMemo(
    () =>
      agents.filter((agent) => displayMissions.some((mission) => mission.leadAgentId === agent.id)),
    [displayMissions],
  );
  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return displayMissions.filter(
      (mission) =>
        (scope === "all" || mission.status !== "completed") &&
        (severity === "all" || mission.severity === severity) &&
        (leadAgentId === "all" || mission.leadAgentId === leadAgentId) &&
        `${mission.id} ${mission.title} ${mission.turbineId} ${mission.summary}`
          .toLowerCase()
          .includes(normalizedQuery),
    );
  }, [displayMissions, leadAgentId, query, scope, severity]);
  const activeCount = displayMissions.filter((mission) => mission.status !== "completed").length;
  const reviewCount = displayMissions.filter((mission) => mission.status === "under-review").length;
  const executionCount = displayMissions.filter((mission) => mission.status === "executing").length;
  const completedCount = displayMissions.filter((mission) => mission.status === "completed").length;

  return (
    <AppShell activePath="/missions">
      <PageHeader
        eyebrow="AI Operations"
        title="Mission Center"
        description="跟踪多 Agent 从异常发现、诊断决策到运维执行的完整生命周期"
        breadcrumb={["AI Operations", "Mission Center"]}
        meta={
          <>
            <StatusBadge
              value="working"
              label={`${activeCount} ACTIVE MISSIONS`}
              tone="info"
              pulse
            />
            <span className="page-meta-text">
              {reviewCount} 待审核 · {executionCount} 执行中 · {completedCount} 今日完成
            </span>
          </>
        }
        actions={
          <>
            <Button
              variant={view === "timeline" ? "primary" : "secondary"}
              onClick={() => setView("timeline")}
              aria-pressed={view === "timeline"}
            >
              <CalendarDays size={15} /> Timeline
            </Button>
            <span title="演示环境未连接 Mission 写入后端">
              <Button variant="primary" disabled aria-describedby="create-mission-help">
                <Plus size={15} /> Create Mission
              </Button>
            </span>
            <span id="create-mission-help" className="sr-only">
              创建 Mission 在当前只读演示环境中不可用，因为尚未连接写入后端。
            </span>
          </>
        }
      />

      <section className="mission-summary">
        <div>
          <span className="mission-summary__icon mission-summary__icon--info">
            <GitBranch size={16} />
          </span>
          <span>
            <small>ACTIVE</small>
            <strong>{activeCount}</strong>
          </span>
        </div>
        <div>
          <span className="mission-summary__icon mission-summary__icon--warning">
            <ShieldCheck size={16} />
          </span>
          <span>
            <small>AWAITING REVIEW</small>
            <strong>{reviewCount}</strong>
          </span>
        </div>
        <div>
          <span className="mission-summary__icon mission-summary__icon--maintenance">
            <Bot size={16} />
          </span>
          <span>
            <small>AGENTS ENGAGED</small>
            <strong>{agents.filter((agent) => agent.currentMissionId).length}</strong>
          </span>
        </div>
        <div>
          <span className="mission-summary__icon mission-summary__icon--success">
            <CheckCircle2 size={16} />
          </span>
          <span>
            <small>COMPLETED TODAY</small>
            <strong>{completedCount}</strong>
          </span>
        </div>
        <div className="mission-throughput">
          <span>
            <small>AVG. RESOLUTION</small>
            <strong>4h 18m</strong>
          </span>
          <em>-12% vs 7d avg</em>
        </div>
      </section>

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
        <div className="agent-filter-tabs">
          <button className={cn(scope === "active" && "active")} onClick={() => setScope("active")}>
            Active
          </button>
          <button className={cn(scope === "all" && "active")} onClick={() => setScope("all")}>
            All Missions
          </button>
        </div>
        <label>
          <span className="sr-only">按严重程度筛选</span>
          <select
            className="select-field"
            value={severity}
            onChange={(event) => setSeverity(event.target.value as SeverityFilter)}
          >
            <option value="all">Severity · All</option>
            {severityOptions.map((option) => (
              <option value={option} key={option}>
                Severity · {option.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">按 Lead Agent 筛选</span>
          <select
            className="select-field"
            value={leadAgentId}
            onChange={(event) => setLeadAgentId(event.target.value)}
          >
            <option value="all">Lead Agent · All</option>
            {leadOptions.map((agent) => (
              <option value={agent.id} key={agent.id}>
                Lead Agent · {agent.shortName}
              </option>
            ))}
          </select>
        </label>
        <span className="toolbar-result">{filtered.length} Missions</span>
        <div className="view-switcher" aria-label="Mission 视图切换">
          <button
            className={cn(view === "kanban" && "active")}
            onClick={() => setView("kanban")}
            aria-label="看板视图"
            aria-pressed={view === "kanban"}
          >
            <LayoutGrid size={15} />
          </button>
          <button
            className={cn(view === "list" && "active")}
            onClick={() => setView("list")}
            aria-label="列表视图"
            aria-pressed={view === "list"}
          >
            <List size={15} />
          </button>
          <button
            className={cn(view === "timeline" && "active")}
            onClick={() => setView("timeline")}
            aria-label="时间线视图"
            aria-pressed={view === "timeline"}
          >
            <CalendarDays size={15} />
          </button>
        </div>
      </section>

      {view === "kanban" ? (
        <section className="mission-kanban" aria-label="Mission 状态看板">
          {columns.map((column) => {
            const columnMissions = filtered.filter((mission) => mission.status === column.status);
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
        <MissionList items={filtered} />
      ) : (
        <MissionTimeline items={filtered} />
      )}
    </AppShell>
  );
}
