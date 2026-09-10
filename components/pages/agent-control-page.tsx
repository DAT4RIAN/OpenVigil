"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Box,
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
  Sparkles,
  TerminalSquare,
  X,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { AgentControlTable } from "@/components/pages/agent-control-table";
import { Avatar, Button, KeyValue } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import {
  activityEvents,
  agents,
  featuredMission,
  getCurrentWorkflowAuditCycle,
  knowledgeDocuments,
  missions,
} from "@/lib";
import { apiGet, apiPost } from "@/lib/api-client";
import type { AgentToolExecution } from "@/lib/agent-tool-runtime";
import { buildAgentToolPreviewRequest } from "@/lib/agent-tool-preview";
import type { DemoWorkflowEvent, DemoWorkflowState } from "@/lib/demo-workflow";
import type { ActivityEvent, Agent, AgentLayer, AgentStatus } from "@/lib/types";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";
import { useRealtimeChannel } from "@/lib/use-realtime-channel";
import { useProductionEvents } from "@/lib/use-production-events";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { asText, cn } from "@/lib/utils";
import { overlayClientAgents } from "@/lib/client-workflow-overlays";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";
import {
  agentDisplayName,
  agentLayerMeta as layerMeta,
  agentSkillLabel,
  agentStatusLabel as statusLabel,
} from "@/lib/agent-control-meta";

// The durable backend ledger executes deterministic SQL tools with no provider
// token usage, so its executions may carry a null `tokenEstimate`.
type LedgerToolExecution = Omit<AgentToolExecution, "tokenEstimate"> & {
  readonly tokenEstimate: AgentToolExecution["tokenEstimate"] | null;
};

type ToolTestResponse = {
  ok: true;
  data: { execution: LedgerToolExecution };
  error: null;
};

type AgentLedgerResponse = {
  ok: true;
  data: {
    catalog: readonly unknown[];
    executionHistory: readonly LedgerToolExecution[];
  };
  error: null;
  meta: {
    persistence: "d1" | "runtime-memory" | "postgresql";
    persisted: boolean;
    historyCount: number;
    totalHistoryCount?: number;
  };
};

type AgentCollectionResponse = {
  data: readonly Agent[];
  meta: {
    count: number;
    runtimeMode?: OpenVigilRuntimeMode;
    fixtureFallback?: boolean;
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

type AgentQueueItem = {
  readonly id: string;
  readonly sequence: number;
  readonly title: string;
  readonly association: string;
  readonly status: "working" | "reviewing" | "waiting" | "queued" | "completed";
  readonly statusLabel: string;
  readonly href: string;
};

function currentQueueStatus(agent: Agent): Pick<AgentQueueItem, "status" | "statusLabel"> {
  if (agent.status === "reviewing") return { status: "reviewing", statusLabel: "审核中" };
  if (agent.status === "waiting" || agent.status === "idle") {
    return { status: "waiting", statusLabel: "等待中" };
  }
  if (agent.status === "failed" || agent.status === "offline") {
    return { status: "waiting", statusLabel: "已暂停" };
  }
  return { status: "working", statusLabel: "执行中" };
}

function deriveAgentTaskQueue(
  agent: Agent,
  currentTask: string | null,
  publicEvents: readonly ActivityEvent[],
): readonly AgentQueueItem[] {
  const candidates: Omit<AgentQueueItem, "sequence">[] = [];
  const linkedMissionIds = new Set<string>();

  if (currentTask && agent.currentMissionId) {
    const currentMission = missions.find((mission) => mission.id === agent.currentMissionId);
    candidates.push({
      id: `current-${agent.currentMissionId}`,
      title: currentTask,
      association: currentMission
        ? `${currentMission.id} · ${currentMission.turbineId}`
        : agent.currentMissionId,
      ...currentQueueStatus(agent),
      href: `/missions/${agent.currentMissionId}`,
    });
    linkedMissionIds.add(agent.currentMissionId);
  }

  missions
    .filter(
      (mission) =>
        mission.status !== "completed" &&
        mission.id !== agent.currentMissionId &&
        (mission.leadAgentId === agent.id || mission.agentIds.includes(agent.id)),
    )
    .sort(
      (left, right) => Date.parse(left.targetResolutionAt) - Date.parse(right.targetResolutionAt),
    )
    .forEach((mission) => {
      candidates.push({
        id: `mission-${mission.id}`,
        title: mission.nextAction,
        association: `${mission.id} · ${mission.turbineId}`,
        status: mission.status === "under-review" ? "reviewing" : "queued",
        statusLabel: mission.status === "under-review" ? "待审核" : "已排队",
        href: `/missions/${mission.id}`,
      });
      linkedMissionIds.add(mission.id);
    });

  publicEvents
    .filter((event) => event.agentId === agent.id && !linkedMissionIds.has(event.missionId))
    .sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp))
    .forEach((event) => {
      candidates.push({
        id: `activity-${event.id}`,
        title: event.title,
        association: `${event.missionId} · 最近完成`,
        status: "completed",
        statusLabel: "已完成",
        href: `/missions/${event.missionId}`,
      });
      linkedMissionIds.add(event.missionId);
    });

  return candidates
    .slice(0, Math.max(agent.queueDepth, currentTask ? 1 : 0))
    .map((item, index) => ({
      ...item,
      sequence: index + 1,
    }));
}

function AgentDrawer({
  agent,
  onClose,
  executions,
  publicEvents,
  currentTask,
  runtimeMode,
  onChanged,
}: {
  agent: Agent;
  onClose: () => void;
  executions: readonly LedgerToolExecution[];
  publicEvents: readonly ActivityEvent[];
  currentTask: string | null;
  runtimeMode: OpenVigilRuntimeMode;
  onChanged: () => Promise<unknown>;
}) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose);
  const layer = layerMeta[agent.layer];
  const LayerIcon = layer.icon;
  const [configOpen, setConfigOpen] = useState(false);
  const knowledgeSources = knowledgeDocuments.filter((document) =>
    agent.knowledgeSourceIds.includes(document.id),
  );
  const publicActivityHistory = publicEvents
    .filter((event) => event.agentId === agent.id)
    .slice(0, 5);
  const taskQueue = deriveAgentTaskQueue(agent, currentTask, publicEvents);
  const safeTool = buildAgentToolPreviewRequest(
    agent,
    missions.find((mission) => mission.id === agent.currentMissionId) ?? null,
  );
  const toolTest = useMutation({
    mutationFn: () => {
      if (!safeTool) throw new Error("该 Agent 没有可安全预览的只读工具。");
      return apiPost<ToolTestResponse>("/api/agent-tools", {
        tool: safeTool.tool,
        args: safeTool.args,
        agentId: agent.id,
        missionId: agent.currentMissionId ?? undefined,
        idempotencyKey: `agent-control-${agent.id}-${Date.now()}`,
      });
    },
  });
  const runtimeCommand = useMutation({
    mutationFn: ({ action, reason }: { action: "start" | "stop"; reason: string }) => {
      if (!agent.agentKey || !agent.definitionId) {
        throw new Error("当前 Agent 缺少可并发校验的生产定义标识。");
      }
      return apiPost(`/api/backend/agents/${encodeURIComponent(agent.agentKey)}/commands`, {
        action,
        expected_definition_id: agent.definitionId,
        reason,
      });
    },
    onSuccess: async () => {
      await onChanged();
      onClose();
    },
  });
  const deployRelease = useMutation({
    mutationFn: ({ version, reason }: { version: string; reason: string }) => {
      if (!agent.agentKey || !agent.definitionId) {
        throw new Error("当前 Agent 缺少可发布的生产定义标识。");
      }
      return apiPost(`/api/backend/agents/${encodeURIComponent(agent.agentKey)}/releases`, {
        source_definition_id: agent.definitionId,
        version,
        display_name: agent.name,
        role: agent.agentKey,
        description: agent.description,
        reason,
      });
    },
    onSuccess: async () => {
      await onChanged();
      onClose();
    },
  });
  const requestRuntimeCommand = (action: "start" | "stop") => {
    const reason = window.prompt(
      action === "start" ? "请输入启动原因或变更单号" : "请输入停止原因或变更单号",
    );
    if (!reason?.trim()) return;
    runtimeCommand.mutate({ action, reason: reason.trim() });
  };
  const requestRelease = () => {
    const version = window.prompt("请输入新版本号", `${agent.promptVersion}.1`);
    if (!version?.trim()) return;
    const reason = window.prompt("请输入发布原因或变更单号");
    if (!reason?.trim()) return;
    deployRelease.mutate({ version: version.trim(), reason: reason.trim() });
  };
  return (
    <>
      <button className="drawer-backdrop" onClick={onClose} aria-label="关闭 Agent 详情" />
      <aside
        ref={dialogRef}
        tabIndex={-1}
        className="detail-drawer agent-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`${agentDisplayName(agent.id, agent.name)} 详情`}
      >
        <header className="detail-drawer__header">
          <div>
            <span className="eyebrow">AGENT 档案</span>
            <h2>{agentDisplayName(agent.id, agent.shortName)}</h2>
            <p>{agent.role}</p>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </Button>
        </header>
        <div className="agent-profile-banner">
          <Avatar label={agentDisplayName(agent.id, agent.shortName)} tone={layer.tone} />
          <span>
            <strong>{agentDisplayName(agent.id, agent.name)}</strong>
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
            <KeyValue label="队列深度" value={`${agent.queueDepth} 个任务`} />
            <KeyValue label="当前 Mission" value={agent.currentMissionId ?? "—"} mono />
          </div>
        </section>
        {currentTask ? (
          <section className="current-agent-task">
            <span>
              <Activity size={15} />
            </span>
            <div>
              <small>当前任务</small>
              <strong>{currentTask}</strong>
              <em>
                执行中 · 最后活动{" "}
                {agent.lastActiveAt
                  ? new Date(agent.lastActiveAt).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                      hour12: false,
                    })
                  : "暂无执行记录"}
              </em>
            </div>
            <a href={agent.currentMissionId ? `/missions/${agent.currentMissionId}` : "/missions"}>
              <ArrowRight size={14} />
            </a>
          </section>
        ) : null}
        <section className="drawer-section">
          <div className="drawer-section__title">
            <h3>任务队列</h3>
            <strong>{taskQueue.length} 项可追溯任务</strong>
          </div>
          {taskQueue.length ? (
            <ol className="agent-task-queue">
              {taskQueue.map((task) => (
                <li key={task.id}>
                  <span className="agent-task-queue__sequence">
                    {String(task.sequence).padStart(2, "0")}
                  </span>
                  <span className="agent-task-queue__copy">
                    <strong>{task.title}</strong>
                    <small>{task.association}</small>
                  </span>
                  <StatusBadge
                    value={task.status}
                    label={task.statusLabel}
                    tone={
                      task.status === "completed"
                        ? "success"
                        : task.status === "working"
                          ? "info"
                          : task.status === "reviewing" || task.status === "waiting"
                            ? "warning"
                            : "neutral"
                    }
                    pulse={task.status === "working"}
                    compact
                  />
                  <Link href={task.href} aria-label={`打开 ${task.association}`}>
                    <ArrowRight size={13} />
                  </Link>
                </li>
              ))}
            </ol>
          ) : (
            <p className="agent-history-empty">当前没有可追溯任务，Agent 正在等待调度。</p>
          )}
        </section>
        <section className="drawer-section">
          <h3>Agent 工具</h3>
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
          <h3>技能</h3>
          <div className="skill-list">
            {agent.skills.map((skill) => (
              <span key={skill}>
                <Sparkles size={11} /> {agentSkillLabel(skill)}
              </span>
            ))}
          </div>
        </section>
        <section className="drawer-section">
          <h3>知识来源</h3>
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
              <small>请求数</small>
              <strong>{agent.metrics.requests24h}</strong>
            </div>
            <div>
              <small>工具调用</small>
              <strong>{agent.metrics.toolCalls24h}</strong>
            </div>
            <div>
              <small>成功率</small>
              <strong>{agent.metrics.successRate}%</strong>
            </div>
            <div>
              <small>平均延迟</small>
              <strong>{agent.metrics.averageLatencySeconds}s</strong>
            </div>
            <div>
              <small>Token 用量</small>
              <strong>{agent.metrics.tokenUsage24h.toLocaleString("zh-CN")}</strong>
            </div>
            <div>
              <small>已完成 Mission</small>
              <strong>{agent.metrics.missionsCompleted}</strong>
            </div>
          </div>
        </section>
        <section className="drawer-section" id={`agent-history-${agent.id}`}>
          <h3>执行历史</h3>
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
                        {execution.missionId ?? "无关联 Mission"} · {execution.latencyMs} ms
                        {execution.tokenEstimate
                          ? ` · ${execution.tokenEstimate.total} 个 Token`
                          : ""}
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
              {agent.model} · {agent.promptVersion} · {agent.tools.length} 个工具 ·{" "}
              {agent.knowledgeSourceIds.length} 个来源
            </p>
            <small>演示环境不允许在浏览器中修改生产 Agent 配置。</small>
          </section>
        ) : null}
        {toolTest.data || toolTest.error || runtimeCommand.error || deployRelease.error ? (
          <section className="drawer-section agent-tool-test-result" aria-live="polite">
            <h3>可审计工具预览</h3>
            {runtimeCommand.error || deployRelease.error ? (
              <p className="critical-text">
                生产命令未完成：
                {(runtimeCommand.error ?? deployRelease.error) instanceof Error
                  ? (runtimeCommand.error ?? deployRelease.error)?.message
                  : "未知错误"}
              </p>
            ) : toolTest.data ? (
              <p>
                <CheckCircle2 size={13} /> {toolTest.data.data.execution.request.tool} ·{" "}
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
          {runtimeMode === "production" ? (
            <>
              <Button
                variant={agent.status === "offline" ? "primary" : "danger"}
                loading={runtimeCommand.isPending}
                onClick={() => requestRuntimeCommand(agent.status === "offline" ? "start" : "stop")}
              >
                {agent.status === "offline" ? "启动" : "停止"}
              </Button>
              <Button
                variant="secondary"
                loading={deployRelease.isPending}
                onClick={requestRelease}
              >
                发布新版本
              </Button>
            </>
          ) : null}
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
          <Button
            variant="primary"
            loading={toolTest.isPending}
            disabled={!safeTool}
            title={safeTool ? `只读预览 ${safeTool.tool}` : "没有可安全预览的只读工具"}
            onClick={() => toolTest.mutate()}
          >
            <Play size={14} /> {safeTool ? `预览 ${safeTool.tool}` : "无可预览工具"}
          </Button>
        </footer>
      </aside>
    </>
  );
}

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
