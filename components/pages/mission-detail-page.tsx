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
  MoreHorizontal,
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
  getMission,
  getTurbine,
  turbine023,
  weatherWindows,
  workOrders,
} from "@/lib";
import type { Mission } from "@/lib/types";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { cn } from "@/lib/utils";

const steps = [
  "Detected",
  "Investigating",
  "Diagnosed",
  "Decision",
  "Review",
  "Approved",
  "Executing",
  "Completed",
];
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
    <AppShell activePath={`/missions/${mission.id}`}>
      <PageHeader
        eyebrow="MISSION DETAIL"
        title={mission.id}
        description={`${mission.turbineId} · ${mission.title} · 结构化协作与执行记录`}
        breadcrumb={["AI Operations", "Mission Center", mission.id]}
        meta={
          <>
            <StatusBadge
              value={mission.status}
              label={mission.status.replaceAll("-", " ").toUpperCase()}
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
              label={mission.severity.toUpperCase()}
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
              <TerminalSquare size={15} /> Export JSON
            </Button>
            <Button
              variant="primary"
              onClick={() => setIsCommenting((current) => !current)}
              aria-expanded={isCommenting}
            >
              <MessageSquareText size={15} /> Add Comment
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
            <CardHeader eyebrow="MISSION OVERVIEW" title={mission.title} />
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
              <KeyValue label="Lead Agent" value={lead?.shortName ?? "Unassigned"} />
              <KeyValue label="Participating Agents" value={`${team.length} Agents`} />
              <KeyValue label="Evidence" value={`${relatedEvidence.length} items`} />
              <KeyValue
                label="Target Resolution"
                value={new Date(mission.targetResolutionAt).toLocaleString("zh-CN")}
              />
            </div>
            <div className="mission-next-action">
              <small>NEXT ACTION</small>
              <strong>{mission.nextAction}</strong>
            </div>
          </Card>
          <Card className="mission-agent-list">
            <CardHeader eyebrow="MISSION TEAM" title={`${team.length} Participating Agents`} />
            <div>
              {team.map((agent) => (
                <button key={agent.id}>
                  <Avatar
                    label={agent.shortName}
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
                    <strong>{agent.shortName}</strong>
                    <small>{agent.role}</small>
                  </span>
                  <StatusBadge value={agent.status} compact />
                </button>
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
              eyebrow="CURRENT DIAGNOSIS"
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
            <CardHeader eyebrow="RELATED OBJECTS" title="业务关联" />
            <div className="key-value-list">
              <KeyValue label="Wind Turbine" value={turbine?.id ?? mission.turbineId} mono />
              <KeyValue label="Decision" value={decision?.id ?? "—"} mono />
              <KeyValue label="Work Order" value={workOrder?.id ?? "—"} mono />
              <KeyValue label="Audit Events" value={String(events.length)} />
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
  const relatedEvents = activityEvents.filter((event) => event.missionId === featuredMission.id);
  const relatedEvidence = evidenceItems.filter((item) => item.missionId === featuredMission.id);
  const missionAgents = agents.filter((agent) => featuredMission.agentIds.includes(agent.id));
  const recommended =
    featuredDecision.alternatives.find(
      (item) => item.id === featuredDecision.recommendedAlternativeId,
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
    completed: 7,
  }[workflow.missionStatus];
  function exportMissionLog() {
    downloadMissionJson(`${featuredMission.id}-mission-log.json`, {
      schemaVersion: "windops.mission-log.v1",
      mission: featuredMission,
      turbine: turbine023,
      participatingAgents: missionAgents,
      evidence: relatedEvidence,
      decision: featuredDecision,
      workOrder: workOrder ?? null,
      activity: relatedEvents,
      workflow: {
        missionStatus: workflow.missionStatus,
        missionProgress: workflow.missionProgress,
        decisionStatus: workflow.decisionStatus,
        workOrderStatus: workflow.workOrderStatus,
        approval: workflow.approval,
        auditTrail: workflow.auditTrail,
      },
      sessionComments: {
        persistence: "page-session-only",
        items: localComments,
      },
    });
  }

  function submitApproval(action: "approve" | "reject" | "request-revision" | "escalate") {
    workflow.dispatch({
      type: "submit-approval",
      action,
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
    <AppShell activePath="/missions/MISSION-2026-0823">
      <PageHeader
        eyebrow="MISSION DETAIL"
        title={featuredMission.id}
        description={`${turbine023.id} · ${featuredMission.title} · 多 Agent 协同诊断与运维决策`}
        breadcrumb={["AI Operations", "Mission Center", featuredMission.id]}
        meta={
          <>
            <StatusBadge
              value={workflow.missionStatus}
              label={workflow.missionStatus.replaceAll("-", " ").toUpperCase()}
              tone={
                workflow.missionStatus === "completed"
                  ? "success"
                  : workflow.missionStatus === "under-review"
                    ? "warning"
                    : "info"
              }
              pulse={workflow.missionStatus !== "completed"}
            />
            <StatusBadge value={featuredMission.severity} label="HIGH SEVERITY" tone="critical" />
            <span className="page-meta-text">
              审计事件 {workflow.auditTrail.length} 条 · 状态跨页面同步
            </span>
          </>
        }
        actions={
          <>
            <Button variant="secondary" onClick={exportMissionLog}>
              <TerminalSquare size={15} /> Export JSON
            </Button>
            <Button variant="secondary" disabled title="当前版本暂无更多操作">
              <MoreHorizontal size={15} /> More
            </Button>
            <Button
              variant="primary"
              onClick={() => setIsCommenting((current) => !current)}
              aria-expanded={isCommenting}
            >
              <MessageSquareText size={15} /> Add Comment
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
            <CardHeader eyebrow="MISSION OVERVIEW" title={featuredMission.title} />
            <div className="mission-overview-hero">
              <span className="mission-overview-icon">
                <AlarmTriangle size={20} />
              </span>
              <div>
                <span className="mono">{turbine023.id} · MAIN BEARING</span>
                <p>{featuredMission.summary}</p>
              </div>
            </div>
            <div className="mission-overview-facts">
              <KeyValue
                label="Lead Agent"
                value={agents.find((item) => item.id === featuredMission.leadAgentId)?.shortName}
              />
              <KeyValue
                label="Participating Agents"
                value={`${featuredMission.agentIds.length} Agents`}
              />
              <KeyValue label="Evidence" value={`${featuredMission.evidenceIds.length} items`} />
              <KeyValue
                label="Target Resolution"
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
              <small>NEXT ACTION</small>
              <strong>
                {workflow.missionStatus === "completed"
                  ? "闭环验证完成，案例已沉淀"
                  : workflow.workOrderStatus === "in-progress"
                    ? "完成现场任务并提交复测结果"
                    : workflow.workOrderStatus === "scheduled"
                      ? "启动 WO-20260823-017"
                      : featuredMission.nextAction}
              </strong>
            </div>
          </Card>

          <Card className="collaboration-card">
            <CardHeader
              eyebrow="PUBLIC EXECUTION TRACE"
              title="Agent Collaboration Graph"
              description="结构化协作过程 · 不展示隐藏推理"
            />
            <div className="agent-graph">
              <div className="agent-graph-row">
                <span className="graph-node graph-node--done">
                  <Bot size={14} />
                  <strong>SCADA</strong>
                  <small>anomaly data</small>
                </span>
                <i className="graph-edge">
                  <em>evidence</em>
                  <ChevronRight size={13} />
                </i>
                <span className="graph-node graph-node--done">
                  <Activity size={14} />
                  <strong>Vibration</strong>
                  <small>spectrum</small>
                </span>
              </div>
              <div className="agent-graph-row">
                <span className="graph-node graph-node--done">
                  <Sparkles size={14} />
                  <strong>Diagnosis</strong>
                  <small>87% confidence</small>
                </span>
                <i className="graph-edge">
                  <em>decision</em>
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
                  <strong>Review</strong>
                  <small>human gate</small>
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
                  <strong>Approval</strong>
                  <small>{approval}</small>
                </span>
                <i className="graph-edge">
                  <em>approval</em>
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
                  <strong>Work Order</strong>
                  <small>
                    {workOrder ? `${workOrder.id} · ${workflow.workOrderStatus}` : "pending"}
                  </small>
                </span>
              </div>
            </div>
            <div className="graph-legend">
              <span>
                <i className="graph-legend-dot graph-legend-dot--done" /> Complete
              </span>
              <span>
                <i className="graph-legend-dot graph-legend-dot--active" /> Active
              </span>
              <span>
                <i className="graph-legend-dot" /> Waiting
              </span>
            </div>
          </Card>

          <Card className="mission-agent-list">
            <CardHeader
              eyebrow="MISSION TEAM"
              title={`${missionAgents.length} Participating Agents`}
            />
            <div>
              {missionAgents.slice(0, 7).map((agent) => (
                <button key={agent.id}>
                  <Avatar
                    label={agent.shortName}
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
                    <strong>{agent.shortName}</strong>
                    <small>{agent.currentTask ?? agent.role}</small>
                  </span>
                  <StatusBadge value={agent.status} compact />
                </button>
              ))}
            </div>
          </Card>
        </div>

        <MissionActivityTimeline
          events={relatedEvents}
          agents={agents}
          auditTrail={workflow.auditTrail}
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
              eyebrow="CURRENT DECISION"
              title="AI 推荐方案"
              description={`综合置信度 ${featuredDecision.confidencePercent}%`}
            />
            <div className="decision-recommendation">
              <span className="decision-recommendation__badge">
                <Sparkles size={14} /> RECOMMENDED · {recommended?.label}
              </span>
              <h3>{recommended?.title}</h3>
              <p>{recommended?.description}</p>
              <div className="decision-tradeoffs">
                <div>
                  <small>安全风险</small>
                  <StatusBadge
                    value={recommended?.safetyRisk ?? "medium"}
                    label={(recommended?.safetyRisk ?? "medium").toUpperCase()}
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
            <CardHeader eyebrow="EXECUTION READINESS" title="窗口与资源" />
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
              eyebrow="HUMAN-IN-THE-LOOP"
              title="工程师审批"
              description="高风险动作必须经过人工授权并记录理由"
            />
            {approval === "pending" ? (
              <>
                <div className="approval-gate">
                  <div className="approval-flow">
                    <span>
                      <Bot size={14} />
                      <small>AI Recommendation</small>
                    </span>
                    <ChevronRight size={12} />
                    <span>
                      <ShieldCheck size={14} />
                      <small>Safety Review</small>
                    </span>
                    <ChevronRight size={12} />
                    <span className="active">
                      <UserCheck size={14} />
                      <small>Human Approval</small>
                    </span>
                  </div>
                  <div className="approval-notice">
                    <ShieldCheck size={15} />
                    <p>
                      <strong>安全与工程审核已通过</strong>
                      <small>请确认风险、资源和天气窗口后执行。</small>
                    </p>
                  </div>
                </div>
                <textarea
                  className="approval-comment"
                  placeholder="填写审批意见（必填）…"
                  aria-label="审批意见"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                />
                <div className="approval-actions">
                  <Button variant="secondary" onClick={() => submitApproval("reject")}>
                    <X size={14} /> Reject
                  </Button>
                  <Button variant="secondary" onClick={() => submitApproval("request-revision")}>
                    <RefreshCcw size={14} /> Request Revision
                  </Button>
                  <Button variant="secondary" onClick={() => submitApproval("escalate")}>
                    <ArrowUpRight size={14} /> Escalate
                  </Button>
                  <Button
                    variant="primary"
                    onClick={() => submitApproval("approve")}
                    disabled={!comment.trim()}
                  >
                    <Check size={14} /> Approve
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
                    ? "方案已批准并进入执行"
                    : approval === "request-revision"
                      ? "已请求修订"
                      : approval === "escalate"
                        ? "已升级至场站经理"
                        : "方案已拒绝"}
                </h3>
                <p>
                  {approval === "approve"
                    ? "审批门禁已解除；WO-20260823-017 已排程，可进入现场执行。"
                    : workflow.approval?.comment}
                </p>
                <small>
                  {workflow.approval?.approver} · {workflow.approval?.approverRole} ·{" "}
                  {workflow.approval
                    ? new Date(workflow.approval.timestamp).toLocaleString("zh-CN")
                    : "—"}
                </small>
                <Button variant="secondary" onClick={replayApproval}>
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

export function MissionDetailPage({ missionId = "MISSION-2026-0823" }: { missionId?: string }) {
  const mission = getMission(missionId);
  if (!mission) return null;
  return mission.id === featuredMission.id ? (
    <FeaturedMissionDetailPage />
  ) : (
    <GenericMissionDetailPage mission={mission} />
  );
}
