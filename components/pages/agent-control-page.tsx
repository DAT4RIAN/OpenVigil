"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Box,
  CheckCircle2,
  Clock3,
  Filter,
  Gauge,
  Layers3,
  MoreHorizontal,
  Search,
  Sparkles,
  TerminalSquare,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { AgentControlTable } from "@/components/pages/agent-control-table";
import { Avatar, Button } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { agents } from "@/lib/agent-data";
import { activityEvents } from "@/lib/operations-data";
import { apiGet } from "@/lib/api-client";
import type { Agent, AgentLayer, AgentStatus } from "@/lib/types";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";
import { useRealtimeChannel } from "@/lib/use-realtime-channel";
import { useProductionEvents } from "@/lib/use-production-events";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { asText, cn } from "@/lib/utils";
import { overlayClientAgents } from "@/lib/client-workflow-overlays";
import {
  agentDisplayName,
  agentLayerMeta as layerMeta,
  agentStatusLabel as statusLabel,
} from "@/lib/agent-control-meta";
import { AgentDrawer } from "./agent-control-drawer";
import {
  currentWorkflowActivity,
  isFeaturedPostHitlActivity,
  workflowAwareTask,
  type AgentCollectionResponse,
  type AgentLedgerResponse,
} from "./agent-control-support";

export function AgentControlPage({ runtimeMode }: { runtimeMode: OpenVigilRuntimeMode }) {
  const queryClient = useQueryClient();
  const workflow = useDemoWorkflow();
  const [layer, setLayer] = useState<"all" | AgentLayer>("all");
  const [status, setStatus] = useState<"all" | AgentStatus>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Agent | null>(null);
  const isProduction = runtimeMode === "production";
  const agentStream = useRealtimeChannel("agent-events", !isProduction);
  const productionStream = useProductionEvents({
    enabled: isProduction,
    eventTypes: [
      "agent.execution.succeeded",
      "agent.started",
      "agent.stopped",
      "agent.release.deployed",
      "agent.tool.succeeded",
      "agent.tool.failed",
    ],
    cursorKey: "windops.production-events.agents.v1",
    onReady: () => {
      void queryClient.invalidateQueries({ queryKey: ["governed-agents"] });
      void queryClient.invalidateQueries({ queryKey: ["agent-tool-ledger"] });
    },
    onEvent: () => {
      void queryClient.invalidateQueries({ queryKey: ["governed-agents"] });
      void queryClient.invalidateQueries({ queryKey: ["agent-tool-ledger"] });
    },
  });
  const agentsQuery = useQuery({
    queryKey: ["governed-agents", runtimeMode],
    queryFn: ({ signal }) => apiGet<AgentCollectionResponse>("/api/agents", signal),
    enabled: isProduction,
    refetchInterval: isProduction ? 60_000 : false,
  });
  const demoAgents = useMemo(() => overlayClientAgents(agents, workflow), [workflow]);
  const displayAgents = useMemo(
    () => (isProduction ? (agentsQuery.data?.data ?? []) : demoAgents),
    [agentsQuery.data?.data, demoAgents, isProduction],
  );
  const taskFor = useCallback(
    (agent: Agent): string | null =>
      isProduction ? agent.currentTask : workflowAwareTask(agent, workflow),
    [isProduction, workflow],
  );

  useEffect(() => {
    const requestedAgentId = new URLSearchParams(window.location.search)
      .get("agent")
      ?.trim()
      .toLowerCase();
    const requestedAgent = requestedAgentId
      ? displayAgents.find((agent) => agent.id === requestedAgentId)
      : undefined;
    if (!requestedAgent) return;

    const timer = window.setTimeout(() => setSelected(requestedAgent), 0);
    return () => window.clearTimeout(timer);
  }, [displayAgents]);

  const ledgerQuery = useQuery({
    queryKey: ["agent-tool-ledger"],
    queryFn: ({ signal }) => apiGet<AgentLedgerResponse>("/api/agent-tools?limit=100", signal),
    refetchInterval: isProduction ? 60_000 : 15_000,
  });
  const executions = ledgerQuery.data?.data.executionHistory ?? [];
  const publicActivityEvents = useMemo(
    () =>
      isProduction
        ? []
        : [
            ...currentWorkflowActivity(workflow.auditTrail),
            ...activityEvents.filter(
              (event) => !isFeaturedPostHitlActivity(event.missionId, event.kind),
            ),
          ].sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp)),
    [isProduction, workflow.auditTrail],
  );
  const active = displayAgents.filter((agent) =>
    ["working", "thinking", "reviewing"].includes(agent.status),
  ).length;
  const online = displayAgents.filter(
    (agent) => agent.status !== "offline" && agent.status !== "failed",
  ).length;
  const filtered = useMemo(
    () =>
      displayAgents.filter(
        (agent) =>
          (layer === "all" || agent.layer === layer) &&
          (status === "all" || agent.status === status) &&
          `${agent.name} ${agent.role} ${taskFor(agent)}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [displayAgents, layer, query, status, taskFor],
  );
  const totalRequests = displayAgents.reduce((sum, agent) => sum + agent.metrics.requests24h, 0);
  const totalTools = displayAgents.reduce((sum, agent) => sum + agent.metrics.toolCalls24h, 0);
  const avgSuccess =
    displayAgents.reduce((sum, agent) => sum + agent.metrics.successRate, 0) /
    Math.max(displayAgents.length, 1);
  const avgLatency =
    displayAgents.reduce((sum, agent) => sum + agent.metrics.averageLatencySeconds, 0) /
    Math.max(displayAgents.length, 1);
  const totalTokens = displayAgents.reduce((sum, agent) => sum + agent.metrics.tokenUsage24h, 0);
  const missionsCompleted = displayAgents.reduce(
    (sum, agent) => sum + agent.metrics.missionsCompleted,
    0,
  );
  const durableRequests =
    ledgerQuery.data?.meta.totalHistoryCount ?? ledgerQuery.data?.meta.historyCount ?? 0;
  const durableTools = executions.length;
  const durableSuccess = durableTools
    ? (executions.filter((execution) => execution.status === "succeeded").length / durableTools) *
      100
    : null;
  const durableLatency = durableTools
    ? executions.reduce((sum, execution) => sum + execution.latencyMs, 0) / durableTools / 1_000
    : null;
  const durableTokens = executions.reduce(
    (sum, execution) => sum + (execution.tokenEstimate?.total ?? 0),
    0,
  );
  const liveAgentEvent =
    agentStream.frame?.event === "agent-activity" &&
    !isFeaturedPostHitlActivity(
      asText(agentStream.frame.data.missionId),
      asText(agentStream.frame.data.kind),
    )
      ? {
          id: agentStream.frame.correlationId,
          agentId: asText(agentStream.frame.data.agentId),
          actorLabel: asText(agentStream.frame.data.actorLabel, "OpenVigil Agent"),
          title: asText(agentStream.frame.data.title, "收到 Agent 活动"),
          outcome: asText(agentStream.frame.data.outcome, "neutral"),
          timestamp: agentStream.frame.emittedAt,
        }
      : null;

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/agents">
      <PageHeader
        eyebrow="AI 运营"
        title="Agent 控制中心"
        description={`${displayAgents.length} 个受版本治理的风电运维专业 Agent，包含运行状态与持久化执行账本`}
        breadcrumb={["AI 运营", "Agent 控制"]}
        meta={
          <>
            <StatusBadge
              value="working"
              label={`${active} 个 Agent 活跃 · ${isProduction ? (productionStream.status === "connected" ? `SSE 实时 · 游标 ${productionStream.cursor ?? "同步中"}` : "SSE 重连中 · 60 秒对账") : agentStream.status === "connected" ? "WS 实时" : "数据快照"}`}
              tone="info"
              pulse={
                isProduction
                  ? productionStream.status === "connected"
                  : agentStream.status === "connected"
              }
            />
            <span className="page-meta-text">
              {online} / {displayAgents.length} 在线 · 执行账本{" "}
              {ledgerQuery.isError
                ? isProduction
                  ? "不可用 · 已停止展示"
                  : "不可用 · 使用快照"
                : (ledgerQuery.data?.meta.persistence ?? "加载中")}
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
              <TerminalSquare size={15} /> 实时日志
            </Button>
            <Button
              variant="secondary"
              onClick={() =>
                document
                  .getElementById("agent-organization")
                  ?.scrollIntoView({ behavior: "smooth" })
              }
            >
              <Layers3 size={15} /> 组织视图
            </Button>
            <Button variant="primary" onClick={() => setSelected(displayAgents[0] ?? null)}>
              <Sparkles size={15} /> 查看 Agent
            </Button>
          </>
        }
      />

      {isProduction && agentsQuery.isError ? (
        <section className="agent-history-empty critical-text" role="alert">
          生产 Agent 注册表不可用：
          {agentsQuery.error instanceof Error ? agentsQuery.error.message : "未知错误"}
          。演示 Agent 已禁用，不会作为降级数据展示。
        </section>
      ) : null}

      <section className="agent-observability">
        <div>
          <span className="observability-icon">
            <Activity size={15} />
          </span>
          <span>
            <small>执行记录 · 24 小时</small>
            <strong>
              {(isProduction
                ? durableRequests + totalRequests
                : durableRequests || totalRequests
              ).toLocaleString("zh-CN")}
            </strong>
          </span>
          <em>{isProduction ? "持久化执行统计" : "+12.4%"}</em>
        </div>
        <div>
          <span className="observability-icon">
            <TerminalSquare size={15} />
          </span>
          <span>
            <small>工具调用 · 24 小时 / 最近账本</small>
            <strong>
              {(isProduction
                ? durableTools + totalTools
                : durableTools || totalTools
              ).toLocaleString("zh-CN")}
            </strong>
          </span>
          <em>{isProduction ? "治理工具账本" : "每次请求 3.1 次"}</em>
        </div>
        <div>
          <span className="observability-icon">
            <Gauge size={15} />
          </span>
          <span>
            <small>成功 / 失败</small>
            <strong>
              {(durableSuccess ?? avgSuccess).toFixed(1)} /{" "}
              {(100 - (durableSuccess ?? avgSuccess)).toFixed(1)}%
            </strong>
          </span>
          <em>{isProduction ? "按已完成执行计算" : "目标 ≥ 95%"}</em>
        </div>
        <div>
          <span className="observability-icon">
            <Clock3 size={15} />
          </span>
          <span>
            <small>平均延迟</small>
            <strong>{(durableLatency ?? avgLatency).toFixed(1)}s</strong>
          </span>
          <em>{isProduction ? "端到端实测" : "周环比下降 0.8 秒"}</em>
        </div>
        <div>
          <span className="observability-icon">
            <Zap size={15} />
          </span>
          <span>
            <small>Token 用量 · 24 小时</small>
            <strong>
              {durableTokens
                ? durableTokens.toLocaleString("zh-CN")
                : `${(totalTokens / 1_000_000).toFixed(2)}M`}
            </strong>
          </span>
          <em>{isProduction ? "未接入计费时为 0" : "预算 63%"}</em>
        </div>
        <div>
          <span className="observability-icon">
            <CheckCircle2 size={15} />
          </span>
          <span>
            <small>已完成 Mission</small>
            <strong>{missionsCompleted}</strong>
          </span>
          <em>{isProduction ? "仅统计持久化闭环" : "全周期演示数据"}</em>
        </div>
      </section>

      <section
        className="agent-live-strip"
        id="agent-live-activity"
        aria-label="过去 24 小时 Agent 活动"
      >
        <span className="agent-live-strip__title">
          <Activity size={14} />
          <strong>24 小时 Agent 活动</strong>
          <small>公开结构化事件</small>
        </span>
        {liveAgentEvent ? (
          <span className="agent-live-strip__event" key={liveAgentEvent.id}>
            <i className={cn(`agent-live-strip__dot--${liveAgentEvent.outcome}`)} />
            <span>
              <strong>{agentDisplayName(liveAgentEvent.agentId, liveAgentEvent.actorLabel)}</strong>
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
        {isProduction && !executions.length ? (
          <span className="agent-live-strip__event">
            <span>
              <strong>暂无持久化工具执行</strong>
              <small>生产模式不会用演示活动补位</small>
            </span>
          </span>
        ) : null}
        {isProduction
          ? executions.slice(0, 5).map((execution) => (
              <span className="agent-live-strip__event" key={execution.executionId}>
                <i
                  className={cn(
                    `agent-live-strip__dot--${execution.status === "succeeded" ? "success" : "attention"}`,
                  )}
                />
                <span>
                  <strong>
                    {agentDisplayName(execution.agentId, execution.agentId.replaceAll("_", " "))}
                  </strong>
                  <small>
                    {execution.request.tool} · {execution.latencyMs} ms
                  </small>
                </span>
                <time>
                  {new Date(execution.completedAt).toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  })}
                </time>
              </span>
            ))
          : null}
        {publicActivityEvents.slice(0, 5).map((event) => (
          <span className="agent-live-strip__event" key={event.id}>
            <i className={cn(`agent-live-strip__dot--${event.outcome}`)} />
            <span>
              <strong>{agentDisplayName(event.agentId ?? "", event.actorLabel)}</strong>
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
            全部 <span>{displayAgents.length}</span>
          </button>
          <button
            className={cn(status === "working" && "active")}
            onClick={() => setStatus("working")}
          >
            工作中 <span>{displayAgents.filter((item) => item.status === "working").length}</span>
          </button>
          <button className={cn(status === "idle" && "active")} onClick={() => setStatus("idle")}>
            空闲 <span>{displayAgents.filter((item) => item.status === "idle").length}</span>
          </button>
          <button
            className={cn(status === "failed" && "active")}
            onClick={() => setStatus("failed")}
          >
            失败 <span>{displayAgents.filter((item) => item.status === "failed").length}</span>
          </button>
        </div>
        <span className="toolbar-result">{filtered.length} 个 Agent</span>
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
                <em>{layerAgents.length} 个 AGENT</em>
              </button>
              <div className="agent-card-grid">
                {layerAgents.map((agent) => (
                  <button className="agent-card" onClick={() => setSelected(agent)} key={agent.id}>
                    <span className="agent-card__top">
                      <Avatar
                        label={agentDisplayName(agent.id, agent.shortName)}
                        tone={meta.tone}
                      />
                      <span>
                        <strong>{agentDisplayName(agent.id, agent.shortName)}</strong>
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
                        {agent.lastActiveAt
                          ? new Date(agent.lastActiveAt).toLocaleTimeString("zh-CN", {
                              hour: "2-digit",
                              minute: "2-digit",
                              hour12: false,
                            })
                          : "暂无执行"}
                      </small>
                    </span>
                    <span className="agent-card__task">
                      <small>当前任务</small>
                      <strong>{taskFor(agent) ?? "等待新任务"}</strong>
                      <em>{agent.currentMissionId ?? "暂无活动 Mission"}</em>
                    </span>
                    <span className="agent-card__metrics">
                      <span>
                        <small>队列</small>
                        <strong>{agent.queueDepth}</strong>
                      </span>
                      <span>
                        <small>成功率</small>
                        <strong>{agent.metrics.successRate}%</strong>
                      </span>
                      <span>
                        <small>延迟</small>
                        <strong>{agent.metrics.averageLatencySeconds}s</strong>
                      </span>
                    </span>
                    <span className="agent-card__footer">
                      <span>
                        <Box size={12} /> {agent.tools.length} 个工具
                      </span>
                      <span>
                        查看详情 <ArrowRight size={12} />
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </section>

      <section aria-labelledby="agent-table-title" id="agent-table">
        <div className="page-header__copy">
          <span className="eyebrow">运营执行账本</span>
          <h2 id="agent-table-title">Agent 表格</h2>
          <p>统一的搜索、排序、列显隐、分页、行选择、批量检查与 CSV 导出视图。</p>
        </div>
        <AgentControlTable
          rows={filtered.map((agent) => ({
            agent,
            currentTask: taskFor(agent) ?? "等待新任务",
          }))}
          selectedAgentId={selected?.id ?? null}
          onInspect={setSelected}
        />
      </section>
      {selected ? (
        <AgentDrawer
          agent={selected}
          onClose={() => setSelected(null)}
          executions={executions.filter(
            (execution) =>
              execution.agentId === selected.id || execution.agentId === selected.agentKey,
          )}
          publicEvents={publicActivityEvents}
          currentTask={taskFor(selected)}
          runtimeMode={runtimeMode}
          onChanged={() => agentsQuery.refetch()}
        />
      ) : null}
    </AppShell>
  );
}
