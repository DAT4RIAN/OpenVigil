"use client";

import { useMemo, useState } from "react";
import { ArrowRight, Bot, CalendarDays, CheckCircle2, ChevronDown, CircleDot, Clock3, Filter, GitBranch, LayoutGrid, List, Plus, Search, ShieldCheck, Users } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Avatar, Button, Progress } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { agents, missions } from "@/lib";
import type { Mission, MissionStatus } from "@/lib/types";
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

function MissionCard({ mission }: { mission: Mission }) {
  const lead = agents.find((agent) => agent.id === mission.leadAgentId);
  return <a className={cn("kanban-card", mission.id === "MISSION-2026-0823" && "kanban-card--featured")} href={`/missions/${mission.id}`}>
    <div className="kanban-card__header"><span className="mono">{mission.id}</span><StatusBadge value={mission.severity} label={mission.severity.toUpperCase()} tone={mission.severity === "critical" ? "critical" : mission.severity === "high" ? "warning" : mission.severity === "medium" ? "info" : "neutral"} compact /></div>
    <div className="kanban-card__copy"><strong>{mission.title}</strong><span>{mission.turbineId} · {mission.summary}</span></div>
    {mission.diagnosis ? <div className="kanban-diagnosis"><Bot size={12} /><span>{mission.diagnosis}</span>{mission.confidencePercent ? <strong>{mission.confidencePercent}%</strong> : null}</div> : null}
    <div className="kanban-card__progress"><span><small>Progress</small><strong>{mission.progressPercent}%</strong></span><Progress value={mission.progressPercent} tone={mission.severity === "critical" || mission.severity === "high" ? "warning" : "info"} /></div>
    <div className="kanban-card__meta"><span><Avatar label={lead?.shortName ?? "AI"} tone="teal" size="sm" /><span><small>Lead Agent</small><strong>{lead?.shortName ?? "Unassigned"}</strong></span></span><span><Users size={12} /> {mission.agentIds.length}</span></div>
    <div className="kanban-card__footer"><span><Clock3 size={11} /> {new Date(mission.updatedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}</span><ArrowRight size={13} /></div>
  </a>;
}

export function MissionCenterPage() {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"active" | "all">("active");
  const filtered = useMemo(() => missions.filter((mission) => (scope === "all" || mission.status !== "completed") && `${mission.id} ${mission.title} ${mission.turbineId}`.toLowerCase().includes(query.toLowerCase())), [query, scope]);
  const reviewCount = missions.filter((mission) => mission.status === "under-review").length;
  const executionCount = missions.filter((mission) => mission.status === "executing").length;
  const completedCount = missions.filter((mission) => mission.status === "completed").length;

  return <AppShell activePath="/missions">
    <PageHeader eyebrow="AI Operations" title="Mission Center" description="跟踪多 Agent 从异常发现、诊断决策到运维执行的完整生命周期" breadcrumb={["AI Operations", "Mission Center"]} meta={<><StatusBadge value="working" label={`${missions.length - completedCount} ACTIVE MISSIONS`} tone="info" pulse /><span className="page-meta-text">{reviewCount} 待审核 · {executionCount} 执行中 · {completedCount} 今日完成</span></>} actions={<><Button variant="secondary"><CalendarDays size={15} /> Timeline</Button><Button variant="primary"><Plus size={15} /> Create Mission</Button></>} />

    <section className="mission-summary"><div><span className="mission-summary__icon mission-summary__icon--info"><GitBranch size={16} /></span><span><small>ACTIVE</small><strong>{missions.length - completedCount}</strong></span></div><div><span className="mission-summary__icon mission-summary__icon--warning"><ShieldCheck size={16} /></span><span><small>AWAITING REVIEW</small><strong>{reviewCount}</strong></span></div><div><span className="mission-summary__icon mission-summary__icon--maintenance"><Bot size={16} /></span><span><small>AGENTS ENGAGED</small><strong>{agents.filter((agent) => agent.currentMissionId).length}</strong></span></div><div><span className="mission-summary__icon mission-summary__icon--success"><CheckCircle2 size={16} /></span><span><small>COMPLETED TODAY</small><strong>{completedCount}</strong></span></div><div className="mission-throughput"><span><small>AVG. RESOLUTION</small><strong>4h 18m</strong></span><em>-12% vs 7d avg</em></div></section>

    <section className="data-toolbar mission-toolbar"><div className="search-field"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 Mission、机组或故障…" aria-label="搜索 Mission" /></div><div className="agent-filter-tabs"><button className={cn(scope === "active" && "active")} onClick={() => setScope("active")}>Active</button><button className={cn(scope === "all" && "active")} onClick={() => setScope("all")}>All Missions</button></div><Button variant="secondary"><Filter size={14} /> Severity <ChevronDown size={12} /></Button><Button variant="secondary"><Bot size={14} /> Lead Agent <ChevronDown size={12} /></Button><span className="toolbar-result">{filtered.length} Missions</span><div className="view-switcher"><button className="active" aria-label="看板视图"><LayoutGrid size={15} /></button><button aria-label="列表视图"><List size={15} /></button></div></section>

    <section className="mission-kanban" aria-label="Mission 状态看板">
      {columns.map((column) => {
        const columnMissions = filtered.filter((mission) => mission.status === column.status);
        return <div className="kanban-column" key={column.status}><header><span><i className={`kanban-status-dot kanban-status-dot--${column.status}`} /><strong>{column.label}</strong><em>{columnMissions.length}</em></span><small>{column.description}</small></header><div className="kanban-column__body">{columnMissions.map((mission) => <MissionCard key={mission.id} mission={mission} />)}{columnMissions.length === 0 ? <div className="kanban-empty"><CircleDot size={15} /><span>暂无 Mission</span></div> : null}</div></div>;
      })}
    </section>
  </AppShell>;
}

