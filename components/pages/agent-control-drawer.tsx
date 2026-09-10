"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Cpu,
  FileClock,
  Play,
  Sparkles,
  TerminalSquare,
  X,
} from "lucide-react";
import { Avatar, Button, KeyValue } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { knowledgeDocuments } from "@/lib/knowledge-data";
import { missions } from "@/lib/operations-data";
import { apiPost } from "@/lib/api-client";
import { buildAgentToolPreviewRequest } from "@/lib/agent-tool-preview";
import type { ActivityEvent, Agent } from "@/lib/types";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";
import {
  agentDisplayName,
  agentLayerMeta as layerMeta,
  agentSkillLabel,
  agentStatusLabel as statusLabel,
} from "@/lib/agent-control-meta";
import {
  deriveAgentTaskQueue,
  type LedgerToolExecution,
  type ToolTestResponse,
} from "./agent-control-support";

export function AgentDrawer({
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
