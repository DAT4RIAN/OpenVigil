"use client";

import { useState } from "react";
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

import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import {
  downloadMissionJson,
  MissionActivityTimeline,
  type LocalComment,
} from "@/components/pages/mission-detail-support";
import { Avatar, Button, Card, CardHeader, KeyValue, Progress } from "@/components/ui/primitives";
import { agentDisplayName } from "@/lib/agent-control-meta";
import { agents } from "@/lib/agent-data";
import { overlayClientDecisions, overlayClientWorkOrders } from "@/lib/client-workflow-overlays";
import { getCurrentWorkflowAuditCycle, getFeaturedMissionNarrative } from "@/lib/demo-workflow";
import { turbine023 } from "@/lib/farm-data";
import {
  activityEvents,
  evidenceItems,
  featuredDecision,
  featuredMission,
  workOrders,
} from "@/lib/operations-data";
import { isServerWorkflowAlternativeId } from "@/lib/server-workflow-contract";
import { weatherWindows } from "@/lib/telemetry-data";
import {
  localizedMissionTitle,
  localizedSeverityLabel,
  localizedStatusLabel,
} from "@/lib/ui-localization";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { cn } from "@/lib/utils";

import { missionProgressSteps } from "./mission-detail-shared";

export function FeaturedMissionDetailPage() {
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
        breadcrumb={["AI 运营", { label: "Mission 中心", href: "/missions" }, featuredMission.id]}
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

      <section className="mission-stage-bar" tabIndex={0} aria-label="Mission 阶段，可横向滚动">
        {missionProgressSteps.map((step, index) => {
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
              {index < missionProgressSteps.length - 1 ? <i /> : null}
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
