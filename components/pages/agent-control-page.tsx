"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Box,
  BrainCircuit,
  BookOpen,
  CheckCircle2,
  Clock3,
  Cpu,
  Filter,
  FileClock,
  Gauge,
  Layers3,
  MoreHorizontal,
  Play,
  Search,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Avatar, Button, KeyValue } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import {
  activityEvents,
  agents,
  featuredMission,
  getCurrentWorkflowAuditCycle,
  knowledgeDocuments,
} from "@/lib";
import { apiPost } from "@/lib/api-client";
import type { AgentToolExecution } from "@/lib/agent-tool-runtime";
import type { DemoWorkflowEvent, DemoWorkflowState } from "@/lib/demo-workflow";
import type { ActivityEvent, Agent, AgentLayer, AgentStatus } from "@/lib/types";
import { useRealtimeChannel } from "@/lib/use-realtime-channel";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { cn } from "@/lib/utils";

const layerMeta: Record<
  AgentLayer,
  { label: string; description: string; icon: typeof BrainCircuit; tone: string }
> = {
  decision: {
    label: "Decision Layer",
    description: "发现、分析与策略生成",
    icon: BrainCircuit,
    tone: "teal",
  },
  review: {
    label: "Review Layer",
    description: "安全、工程与经济审核",
    icon: ShieldCheck,
    tone: "amber",
  },
  execution: {
    label: "Execution Layer",
    description: "资源编排与现场执行",
    icon: Wrench,
    tone: "blue",
  },
};

const statusLabel: Record<AgentStatus, string> = {
  idle: "IDLE",
  thinking: "THINKING",
  working: "WORKING",
  waiting: "WAITING",
  reviewing: "REVIEWING",
  failed: "FAILED",
  offline: "OFFLINE",
};

type ToolTestResponse = {
  ok: true;
  data: { execution: AgentToolExecution };
  error: null;
};

type AgentLedgerResponse = {
  ok: true;
  data: {
    catalog: readonly unknown[];
    executionHistory: readonly AgentToolExecution[];
  };
  error: null;
  meta: {
    persistence: "d1" | "runtime-memory";
    persisted: boolean;
    historyCount: number;
    totalHistoryCount: number;
  };
};

const workflowActivityKinds: Record<DemoWorkflowEvent["kind"], ActivityEvent["kind"]> = {
  replay: "system",
  approval: "approval",
  execution: "execution",
  verification: "review",
  knowledge: "retrieval",
};

const postHitlActivityKinds = new Set<ActivityEvent["kind"]>([
  "approval",
  "work-order",
  "execution",
]);

function isFeaturedPostHitlActivity(missionId: string, kind: string): boolean {
  return (
    missionId === featuredMission.id && postHitlActivityKinds.has(kind as ActivityEvent["kind"])
  );
}

function currentWorkflowActivity(events: readonly DemoWorkflowEvent[]): ActivityEvent[] {
  return getCurrentWorkflowAuditCycle(events).map((event) => ({
    id: event.id,
    missionId: featuredMission.id,
    timestamp: event.timestamp,
    agentId: event.kind === "knowledge" ? "agent-knowledge" : null,
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
  }));
}

function workflowAwareTask(
  agent: Agent,
  workflow: Pick<DemoWorkflowState, "approval" | "decisionStatus" | "workOrderStatus">,
): string | null {
  if (agent.currentMissionId !== featuredMission.id) return agent.currentTask;

  if (workflow.decisionStatus === "under-review") {
    const gate = workflow.approval?.action === "escalate" ? "升级审批" : "人工审批";
    const pendingTasks: Readonly<Record<string, string>> = {
      "agent-maintenance-strategy": `等待 WT-023 ${gate}结论`,
      "agent-work-order": `WT-023 等待${gate}，工单保持草案`,
      "agent-crew-scheduling": `WT-023 等待${gate}，海维二组尚未排班`,
      "agent-vessel-scheduling": `WT-023 等待${gate}，CTV-03 航次尚未确认`,
    };
    return pendingTasks[agent.id] ?? agent.currentTask;
  }

  if (["rejected", "revision-requested"].includes(workflow.decisionStatus)) {
    const reason = workflow.decisionStatus === "rejected" ? "方案已拒绝" : "方案待修订";
    const pausedTasks: Readonly<Record<string, string>> = {
      "agent-maintenance-strategy": `WT-023 ${reason}，等待新方案`,
      "agent-work-order": `WT-023 ${reason}，工单保持草案`,
      "agent-crew-scheduling": `WT-023 ${reason}，班组排班暂停`,
      "agent-vessel-scheduling": `WT-023 ${reason}，航次确认暂停`,
    };
    return pausedTasks[agent.id] ?? agent.currentTask;
  }

  if (workflow.workOrderStatus === "in-progress") {
    const activeTasks: Readonly<Record<string, string>> = {
      "agent-maintenance-strategy": "等待 WT-023 现场复测结果",
      "agent-work-order": "跟踪 WO-20260823-017 现场执行",
      "agent-crew-scheduling": "跟踪海维二组 WT-023 现场任务",
      "agent-vessel-scheduling": "保障 CTV-03 WT-023 作业航次",
    };
    return activeTasks[agent.id] ?? agent.currentTask;
  }

  if (workflow.workOrderStatus === "completed") {
    const closingTasks: Readonly<Record<string, string>> = {
      "agent-maintenance-strategy": "复核 WT-023 闭环健康恢复",
      "agent-work-order": "同步 WO-20260823-017 闭环记录",
      "agent-crew-scheduling": "释放海维二组后续作业资源",
      "agent-vessel-scheduling": "释放 CTV-03 后续航次资源",
    };
    return closingTasks[agent.id] ?? agent.currentTask;
  }

  return agent.currentTask;
}

function AgentDrawer({
  agent,
  onClose,
  executions,
  publicEvents,
  currentTask,
}: {
  agent: Agent;
  onClose: () => void;
  executions: readonly AgentToolExecution[];
  publicEvents: readonly ActivityEvent[];
  currentTask: string | null;
}) {
  const layer = layerMeta[agent.layer];
  const LayerIcon = layer.icon;
  const [configOpen, setConfigOpen] = useState(false);
  const knowledgeSources = knowledgeDocuments.filter((document) =>
    agent.knowledgeSourceIds.includes(document.id),
  );
  const publicActivityHistory = publicEvents
    .filter((event) => event.agentId === agent.id)
    .slice(0, 5);
  const toolTest = useMutation({
    mutationFn: () =>
      apiPost<ToolTestResponse>("/api/agent-tools", {
        tool: "get_turbine_status",
        args: { turbineId: "WT-023" },
        agentId: agent.id,
        missionId: agent.currentMissionId ?? undefined,
        idempotencyKey: `agent-control-${agent.id}-${Date.now()}`,
      }),
  });
  return (
    <>
      <button className="drawer-backdrop" onClick={onClose} aria-label="关闭 Agent 详情" />
      <aside
        className="detail-drawer agent-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`${agent.name} 详情`}
      >
        <header className="detail-drawer__header">
          <div>
            <span className="eyebrow">AGENT PROFILE</span>
            <h2>{agent.shortName}</h2>
            <p>{agent.role}</p>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </Button>
        </header>
        <div className="agent-profile-banner">
          <Avatar label={agent.shortName} tone={layer.tone} />
          <span>
            <strong>{agent.name}</strong>
            <small>{agent.description}</small>
          </span>
          <StatusBadge
            value={agent.status}
            label={statusLabel[agent.status]}
            pulse={["working", "thinking", "reviewing"].includes(agent.status)}
          />
        </div>
        <section className="drawer-section">
          <h3>运行配置</h3>
          <div className="key-value-list">
            <KeyValue
              label="组织层级"
              value={
                <span className="inline-icon">
                  <LayerIcon size={13} /> {layer.label}
                </span>
              }
            />
            <KeyValue label="模型" value={agent.model} mono />
            <KeyValue label="Prompt 版本" value={agent.promptVersion} mono />
            <KeyValue label="队列深度" value={`${agent.queueDepth} tasks`} />
            <KeyValue label="当前 Mission" value={agent.currentMissionId ?? "—"} mono />
          </div>
        </section>
        {currentTask ? (
          <section className="current-agent-task">
            <span>
              <Activity size={15} />
            </span>
            <div>
              <small>CURRENT TASK</small>
              <strong>{currentTask}</strong>
              <em>
                执行中 · 最后活动{" "}
                {new Date(agent.lastActiveAt).toLocaleTimeString("zh-CN", {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                  hour12: false,
                })}
              </em>
            </div>
            <a href={agent.currentMissionId ? `/missions/${agent.currentMissionId}` : "/missions"}>
              <ArrowRight size={14} />
            </a>
          </section>
        ) : null}
        <section className="drawer-section">
          <h3>Agent Tools</h3>
          <div className="tool-chip-grid">
            {agent.tools.map((tool) => (
              <span key={tool}>
                <TerminalSquare size={12} />
                {tool}
              </span>
            ))}
          </div>
        </section>
        <section className="drawer-section">
          <h3>Skills</h3>
          <div className="skill-list">
            {agent.skills.map((skill) => (
              <span key={skill}>
                <Sparkles size={11} /> {skill}
              </span>
            ))}
          </div>
        </section>
        <section className="drawer-section">
          <h3>Knowledge Sources</h3>
          <div className="agent-knowledge-list">
            {knowledgeSources.map((document) => (
              <Link href={`/knowledge?document=${document.id}`} key={document.id}>
                <BookOpen size={13} />
                <span>
                  <strong>{document.title}</strong>
                  <small>
                    {document.id} · {document.version}
                  </small>
                </span>
                <ArrowRight size={12} />
              </Link>
            ))}
          </div>
        </section>
        <section className="drawer-section">
          <h3>过去 24 小时</h3>
          <div className="agent-metrics-grid">
            <div>
              <small>Requests</small>
              <strong>{agent.metrics.requests24h}</strong>
            </div>
            <div>
              <small>Tool Calls</small>
              <strong>{agent.metrics.toolCalls24h}</strong>
            </div>
            <div>
              <small>Success</small>
              <strong>{agent.metrics.successRate}%</strong>
            </div>
            <div>
              <small>Avg Latency</small>
              <strong>{agent.metrics.averageLatencySeconds}s</strong>
            </div>
            <div>
              <small>Token Usage</small>
              <strong>{agent.metrics.tokenUsage24h.toLocaleString("zh-CN")}</strong>
            </div>
            <div>
              <small>Missions Completed</small>
              <strong>{agent.metrics.missionsCompleted}</strong>
            </div>
          </div>
        </section>
        <section className="drawer-section" id={`agent-history-${agent.id}`}>
          <h3>Execution History</h3>
          <div className="agent-execution-history">
            {executions.length ? (
              executions
                .slice(-5)
                .reverse()
                .map((execution) => (
                  <div key={execution.executionId}>
                    <span className="agent-execution-history__icon">
                      {execution.status === "succeeded" ? (
                        <CheckCircle2 size={13} />
                      ) : (
                        <FileClock size={13} />
                      )}
                    </span>
                    <span>
                      <strong>{execution.request.tool}</strong>
                      <small>
                        {execution.missionId ?? "No mission"} · {execution.latencyMs} ms ·{" "}
                        {execution.tokenEstimate.total} tokens
                      </small>
                    </span>
                    <time>
                      {new Date(execution.completedAt).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                        hour12: false,
                      })}
                    </time>
                  </div>
                ))
            ) : publicActivityHistory.length ? (
              publicActivityHistory.map((event) => (
                <div key={event.id}>
                  <span className="agent-execution-history__icon">
                    {event.outcome === "success" ? (
                      <CheckCircle2 size={13} />
                    ) : (
                      <FileClock size={13} />
                    )}
                  </span>
                  <span>
                    <strong>{event.title}</strong>
                    <small>{event.detail}</small>
                  </span>
                  <time>
                    {new Date(event.timestamp).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: false,
                    })}
                  </time>
                </div>
              ))
            ) : (
              <p className="agent-history-empty">过去 24 小时没有公开执行事件。</p>
            )}
          </div>
        </section>
        {configOpen ? (
          <section className="drawer-section agent-config-preview">
            <h3>只读配置快照</h3>
            <p>
              {agent.model} · {agent.promptVersion} · {agent.tools.length} tools ·{" "}
              {agent.knowledgeSourceIds.length} sources
            </p>
            <small>演示环境不允许在浏览器中修改生产 Agent 配置。</small>
          </section>
        ) : null}
        {toolTest.data || toolTest.error ? (
          <section className="drawer-section agent-tool-test-result" aria-live="polite">
            <h3>Sandbox Tool Test</h3>
            {toolTest.data ? (
              <p>
                <CheckCircle2 size={13} /> get_turbine_status ·{" "}
                {toolTest.data.data.execution.status} · {toolTest.data.data.execution.latencyMs} ms
                · {toolTest.data.data.execution.correlationId}
              </p>
            ) : (
              <p className="critical-text">
                测试未完成：{toolTest.error instanceof Error ? toolTest.error.message : "未知错误"}
              </p>
            )}
          </section>
        ) : null}
        <footer className="detail-drawer__footer">
          <Button
            variant="secondary"
            onClick={() =>
              document
                .getElementById(`agent-history-${agent.id}`)
                ?.scrollIntoView({ behavior: "smooth" })
            }
          >
            <TerminalSquare size={14} /> 查看日志
          </Button>
          <Button variant="secondary" onClick={() => setConfigOpen((value) => !value)}>
            <Cpu size={14} /> 配置
          </Button>
          <Button variant="primary" loading={toolTest.isPending} onClick={() => toolTest.mutate()}>
            <Play size={14} /> 运行测试
          </Button>
        </footer>
      </aside>
    </>
  );
}

export function AgentControlPage() {
  const workflow = useDemoWorkflow();
  const [layer, setLayer] = useState<"all" | AgentLayer>("all");
  const [status, setStatus] = useState<"all" | AgentStatus>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Agent | null>(null);
  const agentStream = useRealtimeChannel("agent-events");
  const ledgerQuery = useQuery({
    queryKey: ["agent-tool-ledger"],
    queryFn: async () => {
      const response = await fetch("/api/agent-tools?limit=100", {
        headers: { accept: "application/json" },
      });
      if (!response.ok) throw new Error(`Agent ledger returned ${response.status}`);
      return (await response.json()) as AgentLedgerResponse;
    },
    refetchInterval: 15_000,
  });
  const executions = ledgerQuery.data?.data.executionHistory ?? [];
  const publicActivityEvents = useMemo(
    () =>
      [
        ...currentWorkflowActivity(workflow.auditTrail),
        ...activityEvents.filter(
          (event) => !isFeaturedPostHitlActivity(event.missionId, event.kind),
        ),
      ].sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp)),
    [workflow.auditTrail],
  );
  const active = agents.filter((agent) =>
    ["working", "thinking", "reviewing"].includes(agent.status),
  ).length;
  const filtered = useMemo(
    () =>
      agents.filter(
        (agent) =>
          (layer === "all" || agent.layer === layer) &&
          (status === "all" || agent.status === status) &&
          `${agent.name} ${agent.role} ${workflowAwareTask(agent, workflow)}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [layer, query, status, workflow],
  );
  const totalRequests = agents.reduce((sum, agent) => sum + agent.metrics.requests24h, 0);
  const totalTools = agents.reduce((sum, agent) => sum + agent.metrics.toolCalls24h, 0);
  const avgSuccess =
    agents.reduce((sum, agent) => sum + agent.metrics.successRate, 0) / agents.length;
  const avgLatency =
    agents.reduce((sum, agent) => sum + agent.metrics.averageLatencySeconds, 0) / agents.length;
  const totalTokens = agents.reduce((sum, agent) => sum + agent.metrics.tokenUsage24h, 0);
  const missionsCompleted = agents.reduce((sum, agent) => sum + agent.metrics.missionsCompleted, 0);
  const durableRequests = ledgerQuery.data?.meta.totalHistoryCount ?? 0;
  const durableTools = executions.length;
  const durableSuccess = durableTools
    ? (executions.filter((execution) => execution.status === "succeeded").length / durableTools) *
      100
    : null;
  const durableLatency = durableTools
    ? executions.reduce((sum, execution) => sum + execution.latencyMs, 0) / durableTools / 1_000
    : null;
  const durableTokens = executions.reduce(
    (sum, execution) => sum + execution.tokenEstimate.total,
    0,
  );
  const liveAgentEvent =
    agentStream.frame?.event === "agent-activity" &&
    !isFeaturedPostHitlActivity(
      String(agentStream.frame.data.missionId ?? ""),
      String(agentStream.frame.data.kind ?? ""),
    )
      ? {
          id: agentStream.frame.correlationId,
          actorLabel: String(agentStream.frame.data.actorLabel ?? "WindOps Agent"),
          title: String(agentStream.frame.data.title ?? "Agent activity received"),
          outcome: String(agentStream.frame.data.outcome ?? "neutral"),
          timestamp: agentStream.frame.emittedAt,
        }
      : null;

  return (
    <AppShell activePath="/agents">
      <PageHeader
        eyebrow="AI Operations"
        title="Agent Control Center"
        description="15 个风电运维专业 Agent 的实时状态、任务队列与运行可观测性"
        breadcrumb={["AI Operations", "Agent Control"]}
        meta={
          <>
            <StatusBadge
              value="working"
              label={`${active} AGENTS ACTIVE · ${agentStream.status === "connected" ? "WS LIVE" : "SNAPSHOT"}`}
              tone="info"
              pulse={agentStream.status === "connected"}
            />
            <span className="page-meta-text">
              15 / 15 Online · Ledger {ledgerQuery.data?.meta.persistence ?? "loading"}
            </span>
          </>
        }
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() =>
                document
                  .getElementById("agent-live-activity")
                  ?.scrollIntoView({ behavior: "smooth" })
              }
            >
              <TerminalSquare size={15} /> Live Logs
            </Button>
            <Button
              variant="secondary"
              onClick={() =>
                document
                  .getElementById("agent-organization")
                  ?.scrollIntoView({ behavior: "smooth" })
              }
            >
              <Layers3 size={15} /> Organization
            </Button>
            <Button variant="primary" onClick={() => setSelected(agents[0] ?? null)}>
              <Play size={15} /> Run Agent
            </Button>
          </>
        }
      />

      <section className="agent-observability">
        <div>
          <span className="observability-icon">
            <Activity size={15} />
          </span>
          <span>
            <small>REQUESTS · 24H</small>
            <strong>{(durableRequests || totalRequests).toLocaleString("zh-CN")}</strong>
          </span>
          <em>+12.4%</em>
        </div>
        <div>
          <span className="observability-icon">
            <TerminalSquare size={15} />
          </span>
          <span>
            <small>TOOL CALLS</small>
            <strong>{(durableTools || totalTools).toLocaleString("zh-CN")}</strong>
          </span>
          <em>3.1 / request</em>
        </div>
        <div>
          <span className="observability-icon">
            <Gauge size={15} />
          </span>
          <span>
            <small>SUCCESS / FAILURE</small>
            <strong>
              {(durableSuccess ?? avgSuccess).toFixed(1)} /{" "}
              {(100 - (durableSuccess ?? avgSuccess)).toFixed(1)}%
            </strong>
          </span>
          <em>目标 ≥ 95%</em>
        </div>
        <div>
          <span className="observability-icon">
            <Clock3 size={15} />
          </span>
          <span>
            <small>AVG LATENCY</small>
            <strong>{(durableLatency ?? avgLatency).toFixed(1)}s</strong>
          </span>
          <em>-0.8s WoW</em>
        </div>
        <div>
          <span className="observability-icon">
            <Zap size={15} />
          </span>
          <span>
            <small>TOKEN USAGE · 24H</small>
            <strong>
              {durableTokens
                ? durableTokens.toLocaleString("zh-CN")
                : `${(totalTokens / 1_000_000).toFixed(2)}M`}
            </strong>
          </span>
          <em>预算 63%</em>
        </div>
        <div>
          <span className="observability-icon">
            <CheckCircle2 size={15} />
          </span>
          <span>
            <small>MISSIONS COMPLETED</small>
            <strong>{missionsCompleted}</strong>
          </span>
          <em>lifetime fixture</em>
        </div>
      </section>

      <section
        className="agent-live-strip"
        id="agent-live-activity"
        aria-label="过去 24 小时 Agent Activity"
      >
        <span className="agent-live-strip__title">
          <Activity size={14} />
          <strong>24H AGENT ACTIVITY</strong>
          <small>公开结构化事件</small>
        </span>
        {liveAgentEvent ? (
          <span className="agent-live-strip__event" key={liveAgentEvent.id}>
            <i className={cn(`agent-live-strip__dot--${liveAgentEvent.outcome}`)} />
            <span>
              <strong>{liveAgentEvent.actorLabel}</strong>
              <small>{liveAgentEvent.title}</small>
            </span>
            <time>
              {new Date(liveAgentEvent.timestamp).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
              })}
            </time>
          </span>
        ) : null}
        {publicActivityEvents.slice(0, 5).map((event) => (
          <span className="agent-live-strip__event" key={event.id}>
            <i className={cn(`agent-live-strip__dot--${event.outcome}`)} />
            <span>
              <strong>{event.actorLabel}</strong>
              <small>{event.title}</small>
            </span>
            <time>
              {new Date(event.timestamp).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
              })}
            </time>
          </span>
        ))}
      </section>

      <section className="data-toolbar">
        <div className="search-field">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索 Agent、技能或任务…"
            aria-label="搜索 Agent"
          />
        </div>
        <div className="agent-filter-tabs">
          <button className={cn(status === "all" && "active")} onClick={() => setStatus("all")}>
            All <span>{agents.length}</span>
          </button>
          <button
            className={cn(status === "working" && "active")}
            onClick={() => setStatus("working")}
          >
            Working <span>{agents.filter((item) => item.status === "working").length}</span>
          </button>
          <button className={cn(status === "idle" && "active")} onClick={() => setStatus("idle")}>
            Idle <span>{agents.filter((item) => item.status === "idle").length}</span>
          </button>
          <button
            className={cn(status === "failed" && "active")}
            onClick={() => setStatus("failed")}
          >
            Failed <span>{agents.filter((item) => item.status === "failed").length}</span>
          </button>
        </div>
        <span className="toolbar-result">{filtered.length} Agents</span>
        <Button
          variant="secondary"
          disabled={layer === "all" && status === "all" && !query}
          onClick={() => {
            setLayer("all");
            setStatus("all");
            setQuery("");
          }}
        >
          <Filter size={14} /> 重置筛选
        </Button>
      </section>

      <section className="agent-organization" id="agent-organization">
        {(["decision", "review", "execution"] as AgentLayer[]).map((agentLayer) => {
          const meta = layerMeta[agentLayer];
          const LayerIcon = meta.icon;
          const layerAgents = filtered.filter((agent) => agent.layer === agentLayer);
          if (layer !== "all" && layer !== agentLayer) return null;
          return (
            <div className="agent-layer" key={agentLayer}>
              <button
                className="agent-layer__header"
                onClick={() => setLayer(layer === agentLayer ? "all" : agentLayer)}
              >
                <span className={`layer-icon layer-icon--${meta.tone}`}>
                  <LayerIcon size={16} />
                </span>
                <span>
                  <strong>{meta.label}</strong>
                  <small>{meta.description}</small>
                </span>
                <em>{layerAgents.length} AGENTS</em>
              </button>
              <div className="agent-card-grid">
                {layerAgents.map((agent) => (
                  <button className="agent-card" onClick={() => setSelected(agent)} key={agent.id}>
                    <span className="agent-card__top">
                      <Avatar label={agent.shortName} tone={meta.tone} />
                      <span>
                        <strong>{agent.shortName}</strong>
                        <small>{agent.role}</small>
                      </span>
                      <MoreHorizontal size={15} />
                    </span>
                    <span className="agent-card__status">
                      <StatusBadge
                        value={agent.status}
                        label={statusLabel[agent.status]}
                        pulse={["working", "thinking", "reviewing"].includes(agent.status)}
                        compact
                      />
                      <small>
                        {new Date(agent.lastActiveAt).toLocaleTimeString("zh-CN", {
                          hour: "2-digit",
                          minute: "2-digit",
                          hour12: false,
                        })}
                      </small>
                    </span>
                    <span className="agent-card__task">
                      <small>CURRENT TASK</small>
                      <strong>{workflowAwareTask(agent, workflow) ?? "等待新任务"}</strong>
                      <em>{agent.currentMissionId ?? "No active mission"}</em>
                    </span>
                    <span className="agent-card__metrics">
                      <span>
                        <small>Queue</small>
                        <strong>{agent.queueDepth}</strong>
                      </span>
                      <span>
                        <small>Success</small>
                        <strong>{agent.metrics.successRate}%</strong>
                      </span>
                      <span>
                        <small>Latency</small>
                        <strong>{agent.metrics.averageLatencySeconds}s</strong>
                      </span>
                    </span>
                    <span className="agent-card__footer">
                      <span>
                        <Box size={12} /> {agent.tools.length} tools
                      </span>
                      <span>
                        View details <ArrowRight size={12} />
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </section>
      {selected ? (
        <AgentDrawer
          agent={selected}
          onClose={() => setSelected(null)}
          executions={executions.filter((execution) => execution.agentId === selected.id)}
          publicEvents={publicActivityEvents}
          currentTask={workflowAwareTask(selected, workflow)}
        />
      ) : null}
    </AppShell>
  );
}
