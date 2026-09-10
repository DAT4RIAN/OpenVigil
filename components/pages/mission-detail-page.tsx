"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  TriangleAlert as AlarmTriangle,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  FileSearch,
  MessageSquareText,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  UserCheck,
  CloudSun as WeatherSun,
  Wrench,
  X,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { useWindOpsIdentity } from "@/components/providers/identity-provider";
import { PageHeader } from "@/components/layout/page-header";
import {
  downloadMissionJson,
  MissionActivityTimeline,
  type LocalComment,
} from "@/components/pages/mission-detail-support";
import { Avatar, Button, Card, CardHeader, KeyValue, Progress } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import {
  activityEvents,
  agents,
  decisions,
  evidenceItems,
  featuredDecision,
  featuredMission,
  getCurrentWorkflowAuditCycle,
  getFeaturedMissionNarrative,
  getMission,
  getTurbine,
  turbine023,
  weatherWindows,
  workOrders,
} from "@/lib";
import type { Mission } from "@/lib/types";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { overlayClientDecisions, overlayClientWorkOrders } from "@/lib/client-workflow-overlays";
import { isServerWorkflowAlternativeId } from "@/lib/server-workflow-contract";
import { cn } from "@/lib/utils";
import { agentDisplayName } from "@/lib/agent-control-meta";
import { apiGet, apiPostCommand, createIdempotencyKey } from "@/lib/api-client";
import type { WindOpsRuntimeMode } from "@/lib/production-runtime";
import {
  localizedMissionTitle,
  localizedSeverityLabel,
  localizedStatusLabel,
} from "@/lib/ui-localization";

const steps = ["已发现", "调查中", "已诊断", "决策", "审核", "已批准", "执行中", "已完成"];
function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function GenericMissionDetailPage({ mission }: { mission: Mission }) {
  const [isCommenting, setIsCommenting] = useState(false);
  const [localComments, setLocalComments] = useState<LocalComment[]>([]);
  const turbine = getTurbine(mission.turbineId);
  const lead = agents.find((item) => item.id === mission.leadAgentId);
  const team = agents.filter((item) => mission.agentIds.includes(item.id));
  const relatedEvidence = evidenceItems.filter((item) => mission.evidenceIds.includes(item.id));
  const events = activityEvents.filter((item) => item.missionId === mission.id);
  const decision = decisions.find((item) => item.id === mission.decisionId);
  const workOrder = workOrders.find((item) => item.id === mission.workOrderId);
  const activeIndex = {
    detected: 0,
    investigating: 1,
    diagnosed: 2,
    "decision-pending": 3,
    "under-review": 4,
    approved: 5,
    executing: 6,
    rejected: 7,
    completed: 7,
  }[mission.status];

  function exportMissionLog() {
    downloadMissionJson(`${mission.id}-mission-log.json`, {
      schemaVersion: "windops.mission-log.v1",
      mission,
      turbine: turbine ?? null,
      leadAgent: lead ?? null,
      participatingAgents: team,
      evidence: relatedEvidence,
      decision: decision ?? null,
      workOrder: workOrder ?? null,
      activity: events,
      sessionComments: {
        persistence: "page-session-only",
        items: localComments,
      },
    });
  }

  return (
    <AppShell runtimeMode="demo" activePath={`/missions/${mission.id}`}>
      <PageHeader
        eyebrow="MISSION 详情"
        title={mission.id}
        description={`${mission.turbineId} · ${localizedMissionTitle(mission.title)} · 结构化协作与执行记录`}
        breadcrumb={["AI 运营", "Mission 中心", mission.id]}
        meta={
          <>
            <StatusBadge
              value={mission.status}
              label={localizedStatusLabel(mission.status)}
              tone={
                mission.status === "completed"
                  ? "success"
                  : mission.status === "under-review"
                    ? "warning"
                    : "info"
              }
              pulse={!(["completed", "approved"] as string[]).includes(mission.status)}
            />
            <StatusBadge
              value={mission.severity}
              label={localizedSeverityLabel(mission.severity)}
              tone={
                mission.severity === "critical"
                  ? "critical"
                  : mission.severity === "high"
                    ? "warning"
                    : "info"
              }
            />
            <span className="page-meta-text">更新于 {formatTime(mission.updatedAt)}</span>
          </>
        }
        actions={
          <>
            <a
              className="button button--secondary button--md"
              href={`/turbines/${mission.turbineId}`}
            >
              <TerminalSquare size={15} /> 查看资产
            </a>
            <Button variant="secondary" onClick={exportMissionLog}>
              <TerminalSquare size={15} /> 导出 JSON
            </Button>
            <Button
              variant="primary"
              onClick={() => setIsCommenting((current) => !current)}
              aria-expanded={isCommenting}
            >
              <MessageSquareText size={15} /> 添加评论
            </Button>
          </>
        }
      />
      <section className="mission-stage-bar">
        {steps.map((step, index) => (
          <div
            className={cn(
              "mission-stage",
              (index < activeIndex || mission.status === "completed") && "mission-stage--complete",
              index === activeIndex && "mission-stage--active",
            )}
            key={step}
          >
            <span>
              {index < activeIndex || mission.status === "completed" ? (
                <Check size={11} />
              ) : (
                index + 1
              )}
            </span>
            <strong>{step}</strong>
            {index < steps.length - 1 ? <i /> : null}
          </div>
        ))}
        <div className="mission-stage-progress">
          <strong>{mission.progressPercent}%</strong>
          <Progress
            value={mission.progressPercent}
            tone={mission.status === "completed" ? "success" : "info"}
          />
        </div>
      </section>
      <section className="mission-detail-grid">
        <div className="mission-context-column">
          <Card className="mission-overview-card">
            <CardHeader eyebrow="MISSION 概览" title={localizedMissionTitle(mission.title)} />
            <div className="mission-overview-hero">
              <span className="mission-overview-icon">
                <AlarmTriangle size={20} />
              </span>
              <div>
                <span className="mono">
                  {mission.turbineId} · {mission.severity.toUpperCase()}
                </span>
                <p>{mission.summary}</p>
              </div>
            </div>
            <div className="mission-overview-facts">
              <KeyValue
                label="主导 Agent"
                value={lead ? agentDisplayName(lead.id, lead.shortName) : "未指派"}
              />
              <KeyValue label="参与 Agent" value={`${team.length} 个`} />
              <KeyValue label="证据" value={`${relatedEvidence.length} 项`} />
              <KeyValue
                label="目标解决时间"
                value={new Date(mission.targetResolutionAt).toLocaleString("zh-CN")}
              />
            </div>
            <div className="mission-next-action">
              <small>下一步行动</small>
              <strong>{mission.nextAction}</strong>
            </div>
          </Card>
          <Card className="mission-agent-list">
            <CardHeader eyebrow="MISSION 团队" title={`${team.length} 个参与 Agent`} />
            <div>
              {team.map((agent) => (
                <a href={`/agents?agent=${encodeURIComponent(agent.id)}`} key={agent.id}>
                  <Avatar
                    label={agentDisplayName(agent.id, agent.shortName)}
                    tone={
                      agent.layer === "decision"
                        ? "teal"
                        : agent.layer === "review"
                          ? "amber"
                          : "blue"
                    }
                    size="sm"
                  />
                  <span>
                    <strong>{agentDisplayName(agent.id, agent.shortName)}</strong>
                    <small>{agent.role}</small>
                  </span>
                  <StatusBadge value={agent.status} compact />
                </a>
              ))}
            </div>
          </Card>
        </div>
        <MissionActivityTimeline
          events={events}
          agents={agents}
          description="公开结构化摘要，不展示隐藏推理"
          isCommenting={isCommenting}
          onCommentingChange={setIsCommenting}
          localComments={localComments}
          onCommentsChange={setLocalComments}
        />
        <div className="decision-column">
          <Card className="current-decision-card">
            <CardHeader
              eyebrow="当前诊断"
              title={mission.diagnosis ?? "等待诊断"}
              description={
                mission.confidencePercent
                  ? `综合置信度 ${mission.confidencePercent}%`
                  : "证据收集中"
              }
            />
            <div className="decision-recommendation">
              <p>{mission.summary}</p>
              <div className="decision-evidence-summary">
                <span>
                  <FileSearch size={15} />
                </span>
                <div>
                  <strong>{relatedEvidence.length} 项结构化证据</strong>
                  <small>
                    {relatedEvidence
                      .map((item) => item.type.replaceAll("-", " "))
                      .slice(0, 3)
                      .join(" · ") || "等待 Agent 采集"}
                  </small>
                </div>
              </div>
            </div>
          </Card>
          <Card className="weather-resource-card">
            <CardHeader eyebrow="关联对象" title="业务关联" />
            <div className="key-value-list">
              <KeyValue label="风机" value={turbine?.id ?? mission.turbineId} mono />
              <KeyValue label="决策" value={decision?.id ?? "—"} mono />
              <KeyValue label="工单" value={workOrder?.id ?? "—"} mono />
              <KeyValue label="审计事件" value={String(events.length)} />
            </div>
          </Card>
        </div>
      </section>
    </AppShell>
  );
}

function FeaturedMissionDetailPage() {
  const [comment, setComment] = useState(
    "同意按方案 B 降载运行，并于 8 月 14 日窗口执行主轴承检查。",
  );
  const [isCommenting, setIsCommenting] = useState(false);
  const [localComments, setLocalComments] = useState<LocalComment[]>([]);
  const workflow = useDemoWorkflow();
  const approval = workflow.approval?.action ?? "pending";
  const featuredNarrative = getFeaturedMissionNarrative(workflow);
  const currentAuditTrail = getCurrentWorkflowAuditCycle(workflow.auditTrail);
  const relatedEvents = activityEvents.filter(
    (event) =>
      event.missionId === featuredMission.id &&
      event.kind !== "approval" &&
      event.kind !== "work-order" &&
      event.kind !== "execution",
  );
  const relatedEvidence = evidenceItems.filter((item) => item.missionId === featuredMission.id);
  const missionAgents = agents.filter((agent) => featuredMission.agentIds.includes(agent.id));
  const recommended =
    featuredDecision.alternatives.find(
      (item) =>
        item.id ===
        (workflow.approval?.selectedAlternativeId ?? featuredDecision.recommendedAlternativeId),
    ) ?? featuredDecision.alternatives[0];
  const window =
    weatherWindows.find((item) => item.id === featuredDecision.weatherWindowId) ??
    weatherWindows[0];
  const workOrder = workOrders.find((item) => item.id === featuredMission.workOrderId);
  const statusIndex = {
    detected: 0,
    investigating: 1,
    diagnosed: 2,
    "decision-pending": 3,
    "under-review": 4,
    approved: 5,
    executing: 6,
    rejected: 7,
    completed: 7,
  }[workflow.missionStatus];
  function exportMissionLog() {
    downloadMissionJson(`${featuredMission.id}-mission-log.json`, {
      schemaVersion: "windops.mission-log.v1",
      mission: {
        ...featuredMission,
        status: workflow.missionStatus,
        progressPercent: workflow.missionProgress,
        summary: featuredNarrative.summary,
        nextAction: featuredNarrative.nextAction,
      },
      turbine: turbine023,
      participatingAgents: missionAgents,
      evidence: relatedEvidence,
      decision: overlayClientDecisions([featuredDecision], workflow)[0],
      workOrder: workOrder ? overlayClientWorkOrders([workOrder], workflow)[0] : null,
      activity: relatedEvents,
      workflow: {
        missionStatus: workflow.missionStatus,
        missionProgress: workflow.missionProgress,
        decisionStatus: workflow.decisionStatus,
        workOrderStatus: workflow.workOrderStatus,
        approval: workflow.approval,
        auditTrail: currentAuditTrail,
      },
      sessionComments: {
        persistence: "page-session-only",
        items: localComments,
      },
    });
  }

  function submitApproval(action: "approve" | "reject" | "request-revision" | "escalate") {
    if (!isServerWorkflowAlternativeId(recommended.id)) return;
    workflow.dispatch({
      type: "submit-approval",
      action,
      selectedAlternativeId: recommended.id,
      approver: "李明远",
      approverRole: "值班总工程师",
      timestamp: new Date().toISOString(),
      reason:
        action === "approve"
          ? "安全、工程、资源与气象审核均已通过"
          : action === "escalate"
            ? "需要场站经理复核高风险执行边界"
            : action === "request-revision"
              ? "请补充降载曲线与返航预案"
              : "当前风险不可接受",
      comment: comment.trim() || "未填写补充意见",
    });
  }

  function replayApproval() {
    workflow.dispatch({ type: "replay-approval", timestamp: new Date().toISOString() });
  }

  return (
    <AppShell runtimeMode="demo" activePath="/missions/MISSION-2026-0823">
      <PageHeader
        eyebrow="MISSION 详情"
        title={featuredMission.id}
        description={`${turbine023.id} · ${localizedMissionTitle(featuredMission.title)} · 多 Agent 协同诊断与运维决策`}
        breadcrumb={["AI 运营", "Mission 中心", featuredMission.id]}
        meta={
          <>
            <StatusBadge
              value={workflow.missionStatus}
              label={localizedStatusLabel(workflow.missionStatus)}
              tone={
                workflow.missionStatus === "completed"
                  ? "success"
                  : workflow.missionStatus === "under-review"
                    ? "warning"
                    : "info"
              }
              pulse={workflow.missionStatus !== "completed"}
            />
            <StatusBadge
              value={featuredMission.severity}
              label={`${localizedSeverityLabel(featuredMission.severity)}严重度`}
              tone="critical"
            />
            <span className="page-meta-text">
              当前周期审计事件 {currentAuditTrail.length} 条 · 完整历史保留于 D1
            </span>
          </>
        }
        actions={
          <>
            <Button variant="secondary" onClick={exportMissionLog}>
              <TerminalSquare size={15} /> 导出 JSON
            </Button>
            <Button
              variant="primary"
              onClick={() => setIsCommenting((current) => !current)}
              aria-expanded={isCommenting}
            >
              <MessageSquareText size={15} /> 添加评论
            </Button>
          </>
        }
      />

      <section className="mission-stage-bar">
        {steps.map((step, index) => {
          const complete = index < statusIndex || workflow.missionStatus === "completed";
          const active = index === statusIndex;
          return (
            <div
              className={cn(
                "mission-stage",
                complete && "mission-stage--complete",
                active && "mission-stage--active",
              )}
              key={step}
            >
              <span>{complete ? <Check size={11} /> : index + 1}</span>
              <strong>{step}</strong>
              {index < steps.length - 1 ? <i /> : null}
            </div>
          );
        })}
        <div className="mission-stage-progress">
          <strong>{workflow.missionProgress}%</strong>
          <Progress
            value={workflow.missionProgress}
            tone={
              workflow.missionStatus === "completed"
                ? "success"
                : workflow.missionStatus === "under-review"
                  ? "warning"
                  : "info"
            }
          />
        </div>
      </section>

      <section className="mission-detail-grid">
        <div className="mission-context-column">
          <Card className="mission-overview-card">
            <CardHeader
              eyebrow="MISSION 概览"
              title={localizedMissionTitle(featuredMission.title)}
            />
            <div className="mission-overview-hero">
              <span className="mission-overview-icon">
                <AlarmTriangle size={20} />
              </span>
              <div>
                <span className="mono">{turbine023.id} · 主轴承</span>
                <p>{featuredNarrative.summary}</p>
              </div>
            </div>
            <div className="mission-overview-facts">
              <KeyValue
                label="主导 Agent"
                value={(() => {
                  const leadAgent = agents.find((item) => item.id === featuredMission.leadAgentId);
                  return leadAgent ? agentDisplayName(leadAgent.id, leadAgent.shortName) : "未指派";
                })()}
              />
              <KeyValue label="参与 Agent" value={`${featuredMission.agentIds.length} 个`} />
              <KeyValue label="证据" value={`${featuredMission.evidenceIds.length} 项`} />
              <KeyValue
                label="目标解决时间"
                value={new Date(featuredMission.targetResolutionAt).toLocaleString("zh-CN", {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                  hour12: false,
                })}
              />
            </div>
            <div className="mission-next-action">
              <small>下一步行动</small>
              <strong>{featuredNarrative.nextAction}</strong>
            </div>
          </Card>

          <Card className="collaboration-card">
            <CardHeader
              eyebrow="公开执行轨迹"
              title="Agent 协作图"
              description="结构化协作过程 · 不展示隐藏推理"
            />
            <div className="agent-graph">
              <div className="agent-graph-row">
                <span className="graph-node graph-node--done">
                  <Bot size={14} />
                  <strong>SCADA</strong>
                  <small>异常数据</small>
                </span>
                <i className="graph-edge">
                  <em>证据</em>
                  <ChevronRight size={13} />
                </i>
                <span className="graph-node graph-node--done">
                  <Activity size={14} />
                  <strong>振动分析</strong>
                  <small>频谱</small>
                </span>
              </div>
              <div className="agent-graph-row">
                <span className="graph-node graph-node--done">
                  <Sparkles size={14} />
                  <strong>诊断</strong>
                  <small>87% 置信度</small>
                </span>
                <i className="graph-edge">
                  <em>决策</em>
                  <ChevronRight size={13} />
                </i>
                <span
                  className={cn(
                    "graph-node",
                    workflow.decisionStatus === "approved"
                      ? "graph-node--done"
                      : "graph-node--active",
                  )}
                >
                  <ShieldCheck size={14} />
                  <strong>审核</strong>
                  <small>人工门禁</small>
                </span>
              </div>
              <div className="agent-graph-row">
                <span
                  className={cn(
                    "graph-node",
                    workflow.decisionStatus === "approved"
                      ? "graph-node--done"
                      : "graph-node--waiting",
                  )}
                >
                  <UserCheck size={14} />
                  <strong>审批</strong>
                  <small>
                    {approval === "approve"
                      ? "已批准"
                      : approval === "pending"
                        ? "待审批"
                        : approval === "reject"
                          ? "已拒绝"
                          : "要求修订"}
                  </small>
                </span>
                <i className="graph-edge">
                  <em>审批</em>
                  <ChevronRight size={13} />
                </i>
                <span
                  className={cn(
                    "graph-node",
                    workflow.workOrderStatus === "completed"
                      ? "graph-node--done"
                      : workflow.workOrderStatus === "in-progress"
                        ? "graph-node--active"
                        : "graph-node--waiting",
                  )}
                >
                  <Wrench size={14} />
                  <strong>工单</strong>
                  <small>
                    {workOrder
                      ? `${workOrder.id} · ${localizedStatusLabel(workflow.workOrderStatus)}`
                      : "待处理"}
                  </small>
                </span>
              </div>
            </div>
            <div className="graph-legend">
              <span>
                <i className="graph-legend-dot graph-legend-dot--done" /> 已完成
              </span>
              <span>
                <i className="graph-legend-dot graph-legend-dot--active" /> 执行中
              </span>
              <span>
                <i className="graph-legend-dot" /> 等待中
              </span>
            </div>
          </Card>

          <Card className="mission-agent-list">
            <CardHeader eyebrow="MISSION 团队" title={`${missionAgents.length} 个参与 Agent`} />
            <div>
              {missionAgents.slice(0, 7).map((agent) => (
                <a href={`/agents?agent=${encodeURIComponent(agent.id)}`} key={agent.id}>
                  <Avatar
                    label={agentDisplayName(agent.id, agent.shortName)}
                    tone={
                      agent.layer === "decision"
                        ? "teal"
                        : agent.layer === "review"
                          ? "amber"
                          : "blue"
                    }
                    size="sm"
                  />
                  <span>
                    <strong>{agentDisplayName(agent.id, agent.shortName)}</strong>
                    <small>{agent.currentTask ?? agent.role}</small>
                  </span>
                  <StatusBadge value={agent.status} compact />
                </a>
              ))}
            </div>
          </Card>
        </div>

        <MissionActivityTimeline
          events={relatedEvents}
          agents={agents}
          auditTrail={currentAuditTrail}
          missionStatus={workflow.missionStatus}
          description="按时间记录 Tool、Evidence 与状态转换"
          isCommenting={isCommenting}
          onCommentingChange={setIsCommenting}
          localComments={localComments}
          onCommentsChange={setLocalComments}
        />

        <div className="decision-column">
          <Card className="current-decision-card">
            <CardHeader
              eyebrow="当前决策"
              title={approval === "approve" ? "人工批准方案" : "AI 推荐方案"}
              description={`综合置信度 ${featuredDecision.confidencePercent}%`}
            />
            <div className="decision-recommendation">
              <span className="decision-recommendation__badge">
                <Sparkles size={14} /> {approval === "approve" ? "已批准" : "推荐"} ·{" "}
                {recommended?.label}
              </span>
              <h3>{recommended?.title}</h3>
              <p>{recommended?.description}</p>
              <div className="decision-tradeoffs">
                <div>
                  <small>安全风险</small>
                  <StatusBadge
                    value={recommended?.safetyRisk ?? "medium"}
                    label={localizedSeverityLabel(recommended?.safetyRisk ?? "medium")}
                    tone="warning"
                    compact
                  />
                </div>
                <div>
                  <small>停机时间</small>
                  <strong>{recommended?.estimatedDowntimeHours} h</strong>
                </div>
                <div>
                  <small>预计成本</small>
                  <strong>¥{((recommended?.estimatedCostCny ?? 0) / 10000).toFixed(1)}万</strong>
                </div>
                <div>
                  <small>恶化概率</small>
                  <strong>{recommended?.deteriorationRiskPercent}%</strong>
                </div>
              </div>
              <a href="/decisions">
                比较全部 {featuredDecision.alternatives.length} 个方案 <ArrowRight size={13} />
              </a>
            </div>
            <div className="decision-evidence-summary">
              <span>
                <FileSearch size={15} />
              </span>
              <div>
                <strong>{relatedEvidence.length} 项证据支持此判断</strong>
                <small>SCADA · 振动频谱 · 历史案例 · 维护记录</small>
              </div>
              <a href="#evidence">查看</a>
            </div>
          </Card>

          <Card className="weather-resource-card">
            <CardHeader eyebrow="执行就绪度" title="窗口与资源" />
            <div className="readiness-row">
              <span className="readiness-icon">
                <WeatherSun size={15} />
              </span>
              <div>
                <strong>
                  {new Date(window?.startsAt ?? "2026-08-14").toLocaleDateString("zh-CN", {
                    month: "short",
                    day: "numeric",
                  })}{" "}
                  作业窗口
                </strong>
                <small>
                  08:00–16:00 · 风速 {window?.windSpeedMps} m/s · 浪高 {window?.waveHeightM}m
                </small>
              </div>
              <StatusBadge value="suitable" label="适合" tone="success" compact />
            </div>
            <div className="resource-readiness">
              <span>
                <CheckCircle2 size={12} /> 维修班组
              </span>
              <span>
                <CheckCircle2 size={12} /> 运维船舶
              </span>
              <span>
                <CheckCircle2 size={12} /> 主轴承备件
              </span>
              <span>
                <CheckCircle2 size={12} /> 专用工具
              </span>
            </div>
          </Card>

          <Card
            className={cn("approval-card", approval !== "pending" && `approval-card--${approval}`)}
          >
            <CardHeader
              eyebrow="人工参与审批"
              title="工程师审批"
              description="高风险动作必须经过人工授权并记录理由"
            />
            {approval === "pending" ? (
              <>
                <div className="approval-gate">
                  <div className="approval-flow">
                    <span>
                      <Bot size={14} />
                      <small>AI 建议</small>
                    </span>
                    <ChevronRight size={12} />
                    <span>
                      <ShieldCheck size={14} />
                      <small>安全审核</small>
                    </span>
                    <ChevronRight size={12} />
                    <span className="active">
                      <UserCheck size={14} />
                      <small>人工审批</small>
                    </span>
                  </div>
                  <div className="approval-notice">
                    <ShieldCheck size={15} />
                    <p>
                      <strong>安全与工程审核已通过</strong>
                      <small>
                        {workflow.writable
                          ? "请确认风险、资源和天气窗口后执行；审批将写入 D1。"
                          : "D1 当前不可写；审批动作已切换为只读。"}
                      </small>
                    </p>
                  </div>
                </div>
                <textarea
                  className="approval-comment"
                  placeholder="填写审批意见（必填）…"
                  aria-label="审批意见"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  disabled={!workflow.writable}
                />
                <div className="approval-actions">
                  <Button
                    variant="secondary"
                    onClick={() => submitApproval("reject")}
                    disabled={!workflow.writable}
                  >
                    <X size={14} /> 拒绝
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => submitApproval("request-revision")}
                    disabled={!workflow.writable}
                  >
                    <RefreshCcw size={14} /> 要求修订
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => submitApproval("escalate")}
                    disabled={!workflow.writable}
                  >
                    <ArrowUpRight size={14} /> 升级处理
                  </Button>
                  <Button
                    variant="primary"
                    onClick={() => submitApproval("approve")}
                    disabled={!comment.trim() || !workflow.writable}
                  >
                    <Check size={14} /> 批准
                  </Button>
                </div>
              </>
            ) : (
              <div className="approval-result">
                <span>
                  {approval === "approve" ? (
                    <CheckCircle2 size={25} />
                  ) : approval === "request-revision" ? (
                    <RefreshCcw size={25} />
                  ) : approval === "escalate" ? (
                    <ArrowUpRight size={25} />
                  ) : (
                    <X size={25} />
                  )}
                </span>
                <h3>
                  {approval === "approve"
                    ? workflow.workOrderStatus === "in-progress"
                      ? "方案已批准并进入执行"
                      : workflow.workOrderStatus === "completed"
                        ? "方案已批准并完成闭环"
                        : "方案已批准"
                    : approval === "request-revision"
                      ? "已请求修订"
                      : approval === "escalate"
                        ? "已升级至场站经理"
                        : "方案已拒绝"}
                </h3>
                <p>
                  {approval === "approve"
                    ? workflow.workOrderStatus === "scheduled"
                      ? "审批门禁已解除；WO-20260823-017 已排程，可进入现场执行。"
                      : workflow.workOrderStatus === "in-progress"
                        ? "审批门禁已解除；WO-20260823-017 正在现场执行。"
                        : workflow.workOrderStatus === "completed"
                          ? "WO-20260823-017 已完成，复测与知识沉淀均已记录。"
                          : "审批记录已写入，等待工单状态同步。"
                    : workflow.approval?.comment}
                </p>
                <small>
                  {workflow.approval?.approver} · {workflow.approval?.approverRole} ·{" "}
                  {workflow.approval
                    ? new Date(workflow.approval.timestamp).toLocaleString("zh-CN")
                    : "—"}
                </small>
                <Button variant="secondary" onClick={replayApproval} disabled={!workflow.writable}>
                  重放审批环节
                </Button>
              </div>
            )}
          </Card>
        </div>
      </section>
    </AppShell>
  );
}

interface ProductionMissionComment {
  readonly comment_id: string;
  readonly body: string;
  readonly author_subject: string;
  readonly author_email: string | null;
  readonly created_at: string;
}

interface ProductionMissionDetail {
  readonly mission_id: string;
  readonly alarm_id: string;
  readonly turbine_id: string;
  readonly title: string;
  readonly status: string;
  readonly revision: number;
  readonly public_state: Readonly<Record<string, unknown>>;
  readonly work_order_id: string | null;
  readonly evidence: readonly {
    readonly evidence_id: string;
    readonly evidence_type: string;
    readonly summary: string;
    readonly citation_uri: string | null;
    readonly created_at: string;
  }[];
  readonly decision: {
    readonly decision_id: string;
    readonly status: string;
    readonly recommendation_reason: string;
    readonly recommended_alternative_id: string;
    readonly selected_alternative_id: string | null;
    readonly alternatives: readonly {
      readonly alternative_id: string;
      readonly title?: string;
    }[];
  } | null;
  readonly approvals: readonly {
    readonly approval_id: string;
    readonly action: string;
    readonly approver: string;
    readonly reason: string;
    readonly comment: string;
    readonly created_at: string;
  }[];
  readonly executions: readonly {
    readonly execution_id: string;
    readonly node: string;
    readonly agent_role: string;
    readonly status: string;
    readonly latency_ms: number;
    readonly provider: string;
    readonly model: string;
    readonly started_at: string;
  }[];
  readonly created_at: string;
  readonly updated_at: string;
}

interface ProductionMissionCommentsResponse {
  readonly comments: readonly ProductionMissionComment[];
}

async function persistMissionComment(
  missionId: string,
  body: string,
): Promise<ProductionMissionComment> {
  return apiPostCommand<ProductionMissionComment>(
    `/api/backend/missions/${encodeURIComponent(missionId)}/comments`,
    { body },
    createIdempotencyKey("mission-comment"),
  );
}

function ProductionMissionDetailPage({ missionId }: { readonly missionId: string }) {
  const { can } = useWindOpsIdentity();
  const canComment = can("mission.comment");
  const [isCommenting, setIsCommenting] = useState(false);
  const [commentDraft, setCommentDraft] = useState("");
  const [approvalReason, setApprovalReason] = useState("");
  const [approvalComment, setApprovalComment] = useState("");
  const [approvalMessage, setApprovalMessage] = useState<string | null>(null);
  const approvalInFlight = useRef(false);
  const queryClient = useQueryClient();
  const detailQuery = useQuery({
    queryKey: ["production-mission-detail", missionId],
    queryFn: ({ signal }) =>
      apiGet<ProductionMissionDetail>(
        `/api/backend/missions/${encodeURIComponent(missionId)}`,
        signal,
      ),
  });
  const commentsQuery = useQuery({
    queryKey: ["production-mission-comments", missionId],
    queryFn: ({ signal }) =>
      apiGet<ProductionMissionCommentsResponse>(
        `/api/backend/missions/${encodeURIComponent(missionId)}/comments`,
        signal,
      ),
  });
  const commentMutation = useMutation({
    mutationFn: (body: string) => {
      if (!canComment) throw new Error("当前角色没有写入 Mission 评论的权限。");
      return persistMissionComment(missionId, body);
    },
    onSuccess: async () => {
      setCommentDraft("");
      setIsCommenting(false);
      await queryClient.invalidateQueries({
        queryKey: ["production-mission-comments", missionId],
      });
    },
  });
  const mission = detailQuery.data;
  const approvalMutation = useMutation({
    mutationFn: (action: "approve" | "reject" | "request_revision" | "escalate") => {
      if (!mission) throw new Error("Mission 尚未加载完成。");
      const capability =
        action === "approve"
          ? "mission.approve"
          : action === "reject"
            ? "mission.reject"
            : action === "request_revision"
              ? "mission.request_revision"
              : "mission.escalate";
      if (!can(capability)) throw new Error("当前角色没有执行此审批动作的权限。");
      return apiPostCommand<{
        readonly mission_status: string;
        readonly work_order_id: string | null;
      }>(
        `/api/backend/missions/${encodeURIComponent(missionId)}/approvals`,
        {
          action,
          expected_revision: mission.revision,
          selected_alternative_id:
            action === "approve" ? mission.decision?.recommended_alternative_id : null,
          reason: approvalReason.trim(),
          comment: approvalComment.trim(),
        },
        createIdempotencyKey(`mission-${action}`),
      );
    },
    onSuccess: async (result) => {
      setApprovalReason("");
      setApprovalComment("");
      setApprovalMessage(
        result.work_order_id
          ? `审批已记录并创建工单 ${result.work_order_id}。`
          : `审批已记录，Mission 状态为 ${result.mission_status}。`,
      );
      await queryClient.invalidateQueries({ queryKey: ["production-mission-detail", missionId] });
    },
    onSettled: () => {
      approvalInFlight.current = false;
    },
  });
  const submitProductionApproval = (
    action: "approve" | "reject" | "request_revision" | "escalate",
  ) => {
    if (approvalInFlight.current) return;
    approvalInFlight.current = true;
    approvalMutation.mutate(action);
  };

  if (!mission) {
    return (
      <AppShell runtimeMode="production" activePath={`/missions/${missionId}`}>
        <PageHeader
          eyebrow="MISSION 详情"
          title={missionId}
          description="从权威 Mission、证据、决策、审批和 Agent 执行账本加载。"
          breadcrumb={["AI 运营", "Mission 中心", missionId]}
        />
        <Card>
          <CardHeader
            eyebrow={detailQuery.isError ? "加载失败" : "加载中"}
            title={detailQuery.isError ? "Mission 不可用" : "正在读取权威记录"}
            description={
              detailQuery.error instanceof Error
                ? detailQuery.error.message
                : "生产模式不会回退到演示 Mission。"
            }
          />
          {detailQuery.isError ? (
            <Button onClick={() => void detailQuery.refetch()}>重试</Button>
          ) : null}
        </Card>
      </AppShell>
    );
  }

  const diagnosis = mission.public_state.diagnosis;
  const diagnosisText =
    typeof diagnosis === "object" && diagnosis !== null
      ? JSON.stringify(diagnosis, null, 2)
      : "尚未形成结构化诊断。";

  return (
    <AppShell runtimeMode="production" activePath={`/missions/${mission.mission_id}`}>
      <PageHeader
        eyebrow="MISSION 详情"
        title={mission.mission_id}
        description={`${mission.turbine_id} · ${mission.title} · 权威协作与执行记录`}
        breadcrumb={["AI 运营", "Mission 中心", mission.mission_id]}
        meta={
          <>
            <StatusBadge value={mission.status} label={mission.status} tone="info" />
            <span className="page-meta-text">修订 {mission.revision}</span>
            <span className="page-meta-text">
              更新于 {new Date(mission.updated_at).toLocaleString("zh-CN")}
            </span>
          </>
        }
        actions={
          <>
            <a
              className="button button--secondary button--md"
              href={`/turbines/${mission.turbine_id}`}
            >
              <TerminalSquare size={15} /> 查看资产
            </a>
            <Button
              variant="primary"
              onClick={() => setIsCommenting((current) => !current)}
              aria-expanded={isCommenting}
              disabled={!canComment}
              title={canComment ? undefined : "当前角色没有 mission.comment capability"}
            >
              <MessageSquareText size={15} /> 添加评论
            </Button>
          </>
        }
      />

      <section className="mission-detail-grid">
        <div className="mission-context-column">
          <Card className="mission-overview-card">
            <CardHeader eyebrow="权威状态" title={mission.title} />
            <div className="mission-overview-facts">
              <KeyValue label="告警" value={mission.alarm_id} />
              <KeyValue label="资产" value={mission.turbine_id} />
              <KeyValue label="证据" value={`${mission.evidence.length} 项`} />
              <KeyValue label="工单" value={mission.work_order_id ?? "尚未创建"} />
            </div>
          </Card>
          <Card>
            <CardHeader eyebrow="结构化诊断" title="公开诊断输出" />
            <pre className="mono">{diagnosisText}</pre>
          </Card>
          <Card>
            <CardHeader eyebrow="证据链" title={`${mission.evidence.length} 项可追溯证据`} />
            <div className="mission-evidence-list">
              {mission.evidence.map((item) => (
                <div key={item.evidence_id}>
                  <strong>{item.summary}</strong>
                  <small>
                    {item.evidence_id} · {item.evidence_type}
                  </small>
                  {item.citation_uri ? <code>{item.citation_uri}</code> : null}
                </div>
              ))}
              {!mission.evidence.length ? <p>尚无持久化证据。</p> : null}
            </div>
          </Card>
        </div>

        <Card className="mission-timeline-card">
          <CardHeader
            eyebrow="持久化协作"
            title="评论与 Agent 执行"
            description="评论写入 PostgreSQL 并进入领域事件审计，不再局限于当前页面会话。"
          />
          {isCommenting && canComment ? (
            <div className="approval-gate" id="mission-comment-composer">
              <textarea
                className="approval-comment"
                aria-label="添加持久化评论"
                placeholder="输入需要保留在 Mission 审计记录中的评论"
                value={commentDraft}
                onChange={(event) => setCommentDraft(event.target.value)}
              />
              <small>评论将使用当前委派身份写入不可变活动记录。</small>
              {commentMutation.error instanceof Error ? (
                <p role="alert">{commentMutation.error.message}</p>
              ) : null}
              <div className="approval-actions">
                <Button variant="secondary" onClick={() => setIsCommenting(false)}>
                  取消
                </Button>
                <Button
                  variant="primary"
                  loading={commentMutation.isPending}
                  disabled={!commentDraft.trim()}
                  onClick={() => commentMutation.mutate(commentDraft.trim())}
                >
                  写入评论
                </Button>
              </div>
            </div>
          ) : null}
          <div className="mission-timeline">
            {mission.executions.map((execution) => (
              <div className="timeline-event" key={execution.execution_id}>
                <time>{new Date(execution.started_at).toLocaleString("zh-CN")}</time>
                <span className="timeline-event__node timeline-event__node--success">
                  <Bot size={13} />
                </span>
                <div className="timeline-event__body">
                  <h3>{execution.node}</h3>
                  <p>
                    {execution.agent_role} · {execution.provider}/{execution.model} ·{" "}
                    {execution.latency_ms} ms
                  </p>
                  <StatusBadge value={execution.status} label={execution.status} compact />
                </div>
              </div>
            ))}
            {(commentsQuery.data?.comments ?? []).map((comment) => (
              <div className="timeline-event" key={comment.comment_id}>
                <time>{new Date(comment.created_at).toLocaleString("zh-CN")}</time>
                <span className="timeline-event__node timeline-event__node--in-progress">
                  <MessageSquareText size={13} />
                </span>
                <div className="timeline-event__body">
                  <h3>{comment.author_email ?? comment.author_subject}</h3>
                  <p>{comment.body}</p>
                  <StatusBadge value="persisted" label="已持久化" tone="success" compact />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="decision-column">
          <Card>
            <CardHeader eyebrow="当前决策" title={mission.decision?.decision_id ?? "尚未形成"} />
            {mission.decision ? (
              <>
                <StatusBadge
                  value={mission.decision.status}
                  label={mission.decision.status}
                  tone="warning"
                />
                <p>{mission.decision.recommendation_reason}</p>
                <KeyValue label="推荐方案" value={mission.decision.recommended_alternative_id} />
                <KeyValue
                  label="已选方案"
                  value={mission.decision.selected_alternative_id ?? "等待人工审批"}
                />
              </>
            ) : (
              <p>Agent 分析仍在进行，尚无持久化决策。</p>
            )}
          </Card>
          <Card>
            <CardHeader eyebrow="人工门禁" title={`${mission.approvals.length} 条审批记录`} />
            {mission.status === "under_review" &&
            (can("mission.approve") ||
              can("mission.reject") ||
              can("mission.request_revision") ||
              can("mission.escalate")) ? (
              <div className="approval-gate" data-capability="mission.approval">
                <label>
                  <span>审批原因</span>
                  <input
                    value={approvalReason}
                    onChange={(event) => setApprovalReason(event.target.value)}
                    placeholder="关联风险审查或变更依据"
                  />
                </label>
                <label>
                  <span>补充意见</span>
                  <textarea
                    className="approval-comment"
                    value={approvalComment}
                    onChange={(event) => setApprovalComment(event.target.value)}
                  />
                </label>
                <div className="approval-actions">
                  {can("mission.request_revision") ? (
                    <Button
                      variant="secondary"
                      disabled={approvalMutation.isPending || approvalReason.trim().length < 3}
                      onClick={() => submitProductionApproval("request_revision")}
                    >
                      要求修订
                    </Button>
                  ) : null}
                  {can("mission.escalate") ? (
                    <Button
                      variant="secondary"
                      disabled={approvalMutation.isPending || approvalReason.trim().length < 3}
                      onClick={() => submitProductionApproval("escalate")}
                    >
                      升级处理
                    </Button>
                  ) : null}
                  {can("mission.reject") ? (
                    <Button
                      variant="secondary"
                      disabled={approvalMutation.isPending || approvalReason.trim().length < 3}
                      onClick={() => submitProductionApproval("reject")}
                    >
                      驳回
                    </Button>
                  ) : null}
                  {can("mission.approve") ? (
                    <Button
                      variant="primary"
                      loading={approvalMutation.isPending}
                      disabled={approvalMutation.isPending || approvalReason.trim().length < 3}
                      onClick={() => submitProductionApproval("approve")}
                    >
                      批准推荐方案
                    </Button>
                  ) : null}
                </div>
                {approvalMutation.error instanceof Error ? (
                  <p role="alert">{approvalMutation.error.message}</p>
                ) : null}
                {approvalMessage ? <p role="status">{approvalMessage}</p> : null}
              </div>
            ) : null}
            {mission.status === "under_review" &&
            !can("mission.approve") &&
            !can("mission.reject") &&
            !can("mission.request_revision") &&
            !can("mission.escalate") ? (
              <p role="status">当前角色可审阅此 Mission，但没有可执行的审批动作。</p>
            ) : null}
            {mission.approvals.map((approval) => (
              <div key={approval.approval_id}>
                <strong>{approval.action}</strong>
                <p>{approval.reason}</p>
                <small>
                  {approval.approver} · {new Date(approval.created_at).toLocaleString("zh-CN")}
                </small>
              </div>
            ))}
            {!mission.approvals.length ? <p>等待具备权限的人员审批。</p> : null}
          </Card>
        </div>
      </section>
    </AppShell>
  );
}

export function MissionDetailPage({
  missionId = "MISSION-2026-0823",
  runtimeMode = "demo",
}: {
  missionId?: string;
  runtimeMode?: WindOpsRuntimeMode;
}) {
  if (runtimeMode === "production") {
    return <ProductionMissionDetailPage missionId={missionId} />;
  }
  const mission = getMission(missionId);
  if (!mission) return null;
  return mission.id === featuredMission.id ? (
    <FeaturedMissionDetailPage />
  ) : (
    <GenericMissionDetailPage mission={mission} />
  );
}
