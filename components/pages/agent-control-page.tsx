"use client";

import { useMemo, useState } from "react";
import { Activity, ArrowRight, Box, BrainCircuit, Clock3, Cpu, Filter, Gauge, Layers3, MoreHorizontal, Play, Search, ShieldCheck, Sparkles, TerminalSquare, Wrench, X, Zap } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Avatar, Button, KeyValue } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { agents } from "@/lib";
import type { Agent, AgentLayer, AgentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const layerMeta: Record<AgentLayer, { label: string; description: string; icon: typeof BrainCircuit; tone: string }> = {
  decision: { label: "Decision Layer", description: "发现、分析与策略生成", icon: BrainCircuit, tone: "teal" },
  review: { label: "Review Layer", description: "安全、工程与经济审核", icon: ShieldCheck, tone: "amber" },
  execution: { label: "Execution Layer", description: "资源编排与现场执行", icon: Wrench, tone: "blue" },
};

const statusLabel: Record<AgentStatus, string> = { idle: "IDLE", thinking: "THINKING", working: "WORKING", waiting: "WAITING", reviewing: "REVIEWING", failed: "FAILED", offline: "OFFLINE" };

function AgentDrawer({ agent, onClose }: { agent: Agent; onClose: () => void }) {
  const layer = layerMeta[agent.layer];
  const LayerIcon = layer.icon;
  return <><button className="drawer-backdrop" onClick={onClose} aria-label="关闭 Agent 详情" /><aside className="detail-drawer agent-drawer" aria-label={`${agent.name} 详情`}>
    <header className="detail-drawer__header"><div><span className="eyebrow">AGENT PROFILE</span><h2>{agent.shortName}</h2><p>{agent.role}</p></div><Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭"><X size={18} /></Button></header>
    <div className="agent-profile-banner"><Avatar label={agent.shortName} tone={layer.tone} /><span><strong>{agent.name}</strong><small>{agent.description}</small></span><StatusBadge value={agent.status} label={statusLabel[agent.status]} pulse={["working", "thinking", "reviewing"].includes(agent.status)} /></div>
    <section className="drawer-section"><h3>运行配置</h3><div className="key-value-list"><KeyValue label="组织层级" value={<span className="inline-icon"><LayerIcon size={13} /> {layer.label}</span>} /><KeyValue label="模型" value={agent.model} mono /><KeyValue label="Prompt 版本" value={agent.promptVersion} mono /><KeyValue label="队列深度" value={`${agent.queueDepth} tasks`} /><KeyValue label="当前 Mission" value={agent.currentMissionId ?? "—"} mono /></div></section>
    {agent.currentTask ? <section className="current-agent-task"><span><Activity size={15} /></span><div><small>CURRENT TASK</small><strong>{agent.currentTask}</strong><em>执行中 · 最后活动 {new Date(agent.lastActiveAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</em></div><a href={agent.currentMissionId ? `/missions/${agent.currentMissionId}` : "/missions"}><ArrowRight size={14} /></a></section> : null}
    <section className="drawer-section"><h3>Agent Tools</h3><div className="tool-chip-grid">{agent.tools.map((tool) => <span key={tool}><TerminalSquare size={12} />{tool}</span>)}</div></section>
    <section className="drawer-section"><h3>Skills</h3><div className="skill-list">{agent.skills.map((skill) => <span key={skill}><Sparkles size={11} /> {skill}</span>)}</div></section>
    <section className="drawer-section"><h3>过去 24 小时</h3><div className="agent-metrics-grid"><div><small>Requests</small><strong>{agent.metrics.requests24h}</strong></div><div><small>Tool Calls</small><strong>{agent.metrics.toolCalls24h}</strong></div><div><small>Success</small><strong>{agent.metrics.successRate}%</strong></div><div><small>Avg Latency</small><strong>{agent.metrics.averageLatencySeconds}s</strong></div></div></section>
    <footer className="detail-drawer__footer"><Button variant="secondary"><TerminalSquare size={14} /> 查看日志</Button><Button variant="secondary"><Cpu size={14} /> 配置</Button><Button variant="primary"><Play size={14} /> 运行测试</Button></footer>
  </aside></>;
}

export function AgentControlPage() {
  const [layer, setLayer] = useState<"all" | AgentLayer>("all");
  const [status, setStatus] = useState<"all" | AgentStatus>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Agent | null>(null);
  const active = agents.filter((agent) => ["working", "thinking", "reviewing"].includes(agent.status)).length;
  const filtered = useMemo(() => agents.filter((agent) => (layer === "all" || agent.layer === layer) && (status === "all" || agent.status === status) && `${agent.name} ${agent.role} ${agent.currentTask}`.toLowerCase().includes(query.toLowerCase())), [layer, query, status]);
  const totalRequests = agents.reduce((sum, agent) => sum + agent.metrics.requests24h, 0);
  const totalTools = agents.reduce((sum, agent) => sum + agent.metrics.toolCalls24h, 0);
  const avgSuccess = agents.reduce((sum, agent) => sum + agent.metrics.successRate, 0) / agents.length;
  const avgLatency = agents.reduce((sum, agent) => sum + agent.metrics.averageLatencySeconds, 0) / agents.length;

  return <AppShell activePath="/agents">
    <PageHeader eyebrow="AI Operations" title="Agent Control Center" description="15 个风电运维专业 Agent 的实时状态、任务队列与运行可观测性" breadcrumb={["AI Operations", "Agent Control"]} meta={<><StatusBadge value="working" label={`${active} AGENTS ACTIVE`} tone="info" pulse /><span className="page-meta-text">15 / 15 Online · Orchestrator healthy</span></>} actions={<><Button variant="secondary"><TerminalSquare size={15} /> Live Logs</Button><Button variant="secondary"><Layers3 size={15} /> Organization</Button><Button variant="primary"><Play size={15} /> Run Agent</Button></>} />

    <section className="agent-observability"><div><span className="observability-icon"><Activity size={15} /></span><span><small>REQUESTS · 24H</small><strong>{totalRequests.toLocaleString("zh-CN")}</strong></span><em>+12.4%</em></div><div><span className="observability-icon"><TerminalSquare size={15} /></span><span><small>TOOL CALLS</small><strong>{totalTools.toLocaleString("zh-CN")}</strong></span><em>3.1 / request</em></div><div><span className="observability-icon"><Gauge size={15} /></span><span><small>SUCCESS RATE</small><strong>{avgSuccess.toFixed(1)}%</strong></span><em>目标 ≥ 95%</em></div><div><span className="observability-icon"><Clock3 size={15} /></span><span><small>AVG LATENCY</small><strong>{avgLatency.toFixed(1)}s</strong></span><em>-0.8s WoW</em></div><div><span className="observability-icon"><Zap size={15} /></span><span><small>TOKEN USAGE · 24H</small><strong>1.28M</strong></span><em>预算 63%</em></div></section>

    <section className="data-toolbar"><div className="search-field"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 Agent、技能或任务…" aria-label="搜索 Agent" /></div><div className="agent-filter-tabs"><button className={cn(status === "all" && "active")} onClick={() => setStatus("all")}>All <span>{agents.length}</span></button><button className={cn(status === "working" && "active")} onClick={() => setStatus("working")}>Working <span>{agents.filter((item) => item.status === "working").length}</span></button><button className={cn(status === "idle" && "active")} onClick={() => setStatus("idle")}>Idle <span>{agents.filter((item) => item.status === "idle").length}</span></button><button className={cn(status === "failed" && "active")} onClick={() => setStatus("failed")}>Failed <span>{agents.filter((item) => item.status === "failed").length}</span></button></div><span className="toolbar-result">{filtered.length} Agents</span><Button variant="secondary"><Filter size={14} /> Filters</Button></section>

    <section className="agent-organization">
      {(["decision", "review", "execution"] as AgentLayer[]).map((agentLayer) => {
        const meta = layerMeta[agentLayer]; const LayerIcon = meta.icon; const layerAgents = filtered.filter((agent) => agent.layer === agentLayer);
        if (layer !== "all" && layer !== agentLayer) return null;
        return <div className="agent-layer" key={agentLayer}><button className="agent-layer__header" onClick={() => setLayer(layer === agentLayer ? "all" : agentLayer)}><span className={`layer-icon layer-icon--${meta.tone}`}><LayerIcon size={16} /></span><span><strong>{meta.label}</strong><small>{meta.description}</small></span><em>{layerAgents.length} AGENTS</em></button><div className="agent-card-grid">{layerAgents.map((agent) => <button className="agent-card" onClick={() => setSelected(agent)} key={agent.id}><span className="agent-card__top"><Avatar label={agent.shortName} tone={meta.tone} /><span><strong>{agent.shortName}</strong><small>{agent.role}</small></span><MoreHorizontal size={15} /></span><span className="agent-card__status"><StatusBadge value={agent.status} label={statusLabel[agent.status]} pulse={["working", "thinking", "reviewing"].includes(agent.status)} compact /><small>{new Date(agent.lastActiveAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}</small></span><span className="agent-card__task"><small>CURRENT TASK</small><strong>{agent.currentTask ?? "等待新任务"}</strong><em>{agent.currentMissionId ?? "No active mission"}</em></span><span className="agent-card__metrics"><span><small>Queue</small><strong>{agent.queueDepth}</strong></span><span><small>Success</small><strong>{agent.metrics.successRate}%</strong></span><span><small>Latency</small><strong>{agent.metrics.averageLatencySeconds}s</strong></span></span><span className="agent-card__footer"><span><Box size={12} /> {agent.tools.length} tools</span><span>View details <ArrowRight size={12} /></span></span></button>)}</div></div>;
      })}
    </section>
    {selected ? <AgentDrawer agent={selected} onClose={() => setSelected(null)} /> : null}
  </AppShell>;
}
