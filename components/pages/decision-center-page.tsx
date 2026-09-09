"use client";

import { useState } from "react";
import {
  TriangleAlert as AlarmTriangle,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  FileSearch,
  PackageCheck,
  RefreshCcw,
  Scale,
  ShieldCheck,
  Ship,
  Sparkles,
  UserCheck,
  Users,
  CloudSun as WeatherSun,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, KeyValue } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { decisions, evidenceItems, featuredDecision, weatherWindows } from "@/lib";
import type { DecisionAlternative } from "@/lib/types";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { isServerWorkflowAlternativeId } from "@/lib/server-workflow-contract";
import { cn } from "@/lib/utils";

const solutionIcons = [ShieldCheck, Scale, Zap];

function AlternativeCard({
  option,
  selected,
  onSelect,
  index,
}: {
  option: DecisionAlternative;
  selected: boolean;
  onSelect: () => void;
  index: number;
}) {
  const Icon = solutionIcons[index] ?? Scale;
  return (
    <button
      className={cn(
        "alternative-card",
        selected && "alternative-card--selected",
        option.recommended && "alternative-card--recommended",
      )}
      onClick={onSelect}
    >
      {option.recommended ? (
        <span className="recommended-ribbon">
          <Sparkles size={11} /> AI RECOMMENDED
        </span>
      ) : null}
      <div className="alternative-card__header">
        <span className="alternative-icon">
          <Icon size={18} />
        </span>
        <span>
          <small>{option.label}</small>
          <strong>{option.title}</strong>
        </span>
        <span className="radio-mark">{selected ? <Check size={11} /> : null}</span>
      </div>
      <p>{option.description}</p>
      <div className="alternative-metrics">
        <div>
          <small>安全风险</small>
          <StatusBadge
            value={option.safetyRisk}
            label={option.safetyRisk.toUpperCase()}
            tone={
              option.safetyRisk === "low"
                ? "success"
                : option.safetyRisk === "medium"
                  ? "warning"
                  : "critical"
            }
            compact
          />
        </div>
        <div>
          <small>停机时间</small>
          <strong>{option.estimatedDowntimeHours} h</strong>
        </div>
        <div>
          <small>预计成本</small>
          <strong>¥{(option.estimatedCostCny / 10000).toFixed(1)}万</strong>
        </div>
        <div>
          <small>发电损失</small>
          <strong>{option.estimatedEnergyLossMWh} MWh</strong>
        </div>
        <div>
          <small>恶化概率</small>
          <strong className={option.deteriorationRiskPercent > 30 ? "critical-text" : ""}>
            {option.deteriorationRiskPercent}%
          </strong>
        </div>
      </div>
      <div className="alternative-rationale">
        <Bot size={13} />
        <span>{option.rationale}</span>
      </div>
    </button>
  );
}

export function DecisionCenterPage() {
  const [activeDecisionId, setActiveDecisionId] = useState(featuredDecision.id);
  const [selectedId, setSelectedId] = useState(featuredDecision.recommendedAlternativeId);
  const [comment, setComment] = useState("同意执行方案 B。已确认安全措施、资源和气象窗口。");
  const workflow = useDemoWorkflow();
  const [showAllEvidence, setShowAllEvidence] = useState(false);
  const currentDecision =
    decisions.find((decision) => decision.id === activeDecisionId) ?? featuredDecision;
  const isFeaturedDecision = currentDecision.id === featuredDecision.id;
  const approval = isFeaturedDecision
    ? (workflow.approval?.action ?? "pending")
    : (currentDecision.approval.action ?? "pending");
  const effectiveSelectedId =
    isFeaturedDecision && workflow.approval?.selectedAlternativeId
      ? workflow.approval.selectedAlternativeId
      : selectedId;
  const selected =
    currentDecision.alternatives.find((option) => option.id === effectiveSelectedId) ??
    currentDecision.alternatives[0];
  const window =
    weatherWindows.find((item) => item.id === selected?.weatherWindowId) ?? weatherWindows[0];
  const relatedEvidence = evidenceItems.filter((item) =>
    currentDecision.evidenceIds.includes(item.id),
  );

  function submitApproval(action: "approve" | "reject" | "request-revision" | "escalate") {
    if (!isFeaturedDecision || !isServerWorkflowAlternativeId(selected?.id)) return;
    workflow.dispatch({
      type: "submit-approval",
      action,
      selectedAlternativeId: selected.id,
      approver: "李明远",
      approverRole: "值班总工程师",
      timestamp: new Date().toISOString(),
      reason:
        action === "approve"
          ? "已核验安全、资源与天气窗口"
          : action === "escalate"
            ? "故障后果需要场站经理共同决策"
            : action === "request-revision"
              ? "候选方案需要补充降载曲线"
              : "当前方案风险不可接受",
      comment: comment.trim() || "未填写补充意见",
    });
  }

  return (
    <AppShell activePath="/decisions">
      <PageHeader
        eyebrow="AI Operations"
        title="Decision Center"
        description="基于安全、成本、停机损失、天气与资源的可解释运维决策"
        breadcrumb={["AI Operations", "Decision Center"]}
        meta={
          <>
            <StatusBadge
              value={isFeaturedDecision ? workflow.decisionStatus : currentDecision.status}
              label={(isFeaturedDecision ? workflow.decisionStatus : currentDecision.status)
                .replaceAll("-", " ")
                .toUpperCase()}
              tone={
                (isFeaturedDecision ? workflow.decisionStatus : currentDecision.status) ===
                "approved"
                  ? "success"
                  : "warning"
              }
              pulse={
                (isFeaturedDecision ? workflow.decisionStatus : currentDecision.status) ===
                "under-review"
              }
            />
            <span className="page-meta-text">Human approval policy · 所有动作写入审计记录</span>
          </>
        }
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => document.getElementById("decision-evidence")?.scrollIntoView()}
            >
              <FileSearch size={15} /> Evidence Policy
            </Button>
            <Button
              variant="primary"
              onClick={() => document.getElementById("decision-review-queue")?.scrollIntoView()}
            >
              <ShieldCheck size={15} /> Review Queue
            </Button>
          </>
        }
      />

      <section className="decision-layout">
        <aside className="decision-queue" id="decision-review-queue">
          <div className="decision-queue__header">
            <div>
              <span className="eyebrow">REVIEW QUEUE</span>
              <h2>待决策事件</h2>
            </div>
            <span>{decisions.length}</span>
          </div>
          {decisions.map((decision, index) => (
            <button
              className={cn("decision-queue-item", decision.id === currentDecision.id && "active")}
              key={decision.id}
              onClick={() => {
                setActiveDecisionId(decision.id);
                setSelectedId(decision.recommendedAlternativeId);
              }}
              aria-pressed={decision.id === currentDecision.id}
            >
              <span
                className={cn(
                  "decision-queue-priority",
                  decision.risk === "critical" && "critical",
                )}
              >
                {index + 1}
              </span>
              <span>
                <small className="mono">{decision.id}</small>
                <strong>{decision.incident}</strong>
                <em>
                  {decision.turbineId} ·{" "}
                  {decision.id === featuredDecision.id ? workflow.decisionStatus : decision.status}
                </em>
              </span>
              <ChevronRight size={14} />
            </button>
          ))}
          <div className="decision-queue__footer">
            <CheckCircle2 size={14} />
            <span>
              <strong>12 项今日已完成</strong>
              <small>平均审批 18 分钟</small>
            </span>
          </div>
        </aside>

        <main className="decision-workspace">
          <Card className="decision-incident">
            <div className="decision-incident__icon">
              <AlarmTriangle size={21} />
            </div>
            <div className="decision-incident__copy">
              <span className="eyebrow">INCIDENT · {currentDecision.missionId}</span>
              <h2>{currentDecision.incident}</h2>
              <p>{currentDecision.diagnosis}</p>
            </div>
            <div className="decision-confidence">
              <small>AI CONFIDENCE</small>
              <strong>{currentDecision.confidencePercent}%</strong>
              <span>High</span>
            </div>
            <a href={`/missions/${currentDecision.missionId}`}>
              Mission Detail <ArrowRight size={13} />
            </a>
          </Card>

          <section className="decision-evidence-bar" id="decision-evidence">
            <div>
              <FileSearch size={15} />
              <span>
                <small>EVIDENCE</small>
                <strong>{relatedEvidence.length} 结构化证据</strong>
              </span>
            </div>
            {relatedEvidence.slice(0, showAllEvidence ? relatedEvidence.length : 4).map((item) => (
              <span className="evidence-source-chip" key={item.id}>
                {item.type.replaceAll("-", " ")}
              </span>
            ))}
            <button
              type="button"
              onClick={() => setShowAllEvidence((value) => !value)}
              aria-expanded={showAllEvidence}
            >
              {showAllEvidence ? "收起证据" : "查看全部"} <ArrowRight size={12} />
            </button>
          </section>

          <Card className="alternative-panel">
            <CardHeader
              eyebrow="ALTERNATIVE SOLUTIONS"
              title="候选运维方案"
              description="选择方案以更新右侧风险与资源评估"
              action={
                <span className="comparison-label">
                  <Scale size={13} /> 多目标权衡模型 v3.2
                </span>
              }
            />
            <div className="alternative-grid">
              {currentDecision.alternatives.map((option, index) => (
                <AlternativeCard
                  key={option.id}
                  option={option}
                  index={index}
                  selected={effectiveSelectedId === option.id}
                  onSelect={() => setSelectedId(option.id)}
                />
              ))}
            </div>
          </Card>

          <Card className="decision-explain">
            <CardHeader
              eyebrow="WHY THIS PLAN"
              title="AI 推荐依据"
              description="公开的结构化依据，不包含模型隐藏推理"
            />
            <div className="decision-factor-grid">
              <div>
                <span className="factor-icon factor-icon--success">
                  <ShieldCheck size={15} />
                </span>
                <span>
                  <strong>降低安全风险</strong>
                  <small>所选方案的恶化概率为 {selected?.deteriorationRiskPercent}%</small>
                </span>
              </div>
              <div>
                <span className="factor-icon factor-icon--info">
                  <WeatherSun size={15} />
                </span>
                <span>
                  <strong>匹配作业窗口</strong>
                  <small>
                    {selected?.weatherWindowId
                      ? "已关联满足风速与浪高约束的作业窗口"
                      : "该方案不依赖现场气象窗口"}
                  </small>
                </span>
              </div>
              <div>
                <span className="factor-icon factor-icon--warning">
                  <CircleDollarSign size={15} />
                </span>
                <span>
                  <strong>控制经济损失</strong>
                  <small>
                    预计成本 ¥{((selected?.estimatedCostCny ?? 0) / 10000).toFixed(1)} 万，发电损失{" "}
                    {selected?.estimatedEnergyLossMWh} MWh
                  </small>
                </span>
              </div>
              <div>
                <span className="factor-icon factor-icon--maintenance">
                  <PackageCheck size={15} />
                </span>
                <span>
                  <strong>资源已就绪</strong>
                  <small>{selected?.requiredResources.join("、") || "无需额外现场资源"}</small>
                </span>
              </div>
            </div>
          </Card>
        </main>

        <aside className="decision-review-column">
          <Card className="selected-plan-card">
            <CardHeader eyebrow="SELECTED PLAN" title={selected?.label ?? "方案 B"} />
            <div className="selected-plan-title">
              <span>
                <Sparkles size={16} />
              </span>
              <div>
                <strong>{selected?.title}</strong>
                <small>{selected?.recommended ? "AI 首选方案" : "人工选择方案"}</small>
              </div>
            </div>
            <div className="selected-plan-facts">
              <KeyValue
                label="安全风险"
                value={
                  <StatusBadge
                    value={selected?.safetyRisk ?? "medium"}
                    label={(selected?.safetyRisk ?? "medium").toUpperCase()}
                    tone="warning"
                    compact
                  />
                }
              />
              <KeyValue
                label="预计成本"
                value={`¥${((selected?.estimatedCostCny ?? 0) / 10000).toFixed(1)} 万`}
              />
              <KeyValue label="停机时间" value={`${selected?.estimatedDowntimeHours} 小时`} />
              <KeyValue label="发电损失" value={`${selected?.estimatedEnergyLossMWh} MWh`} />
              <KeyValue label="故障恶化概率" value={`${selected?.deteriorationRiskPercent}%`} />
            </div>
          </Card>

          <Card className="execution-readiness">
            <CardHeader eyebrow="EXECUTION READINESS" title="作业条件" />
            <div className="readiness-detail">
              <span>
                <WeatherSun size={16} />
              </span>
              <div>
                <small>WEATHER WINDOW</small>
                <strong>
                  {new Date(window?.startsAt ?? "2026-08-14").toLocaleDateString("zh-CN", {
                    month: "short",
                    day: "numeric",
                  })}{" "}
                  · 08:00–16:00
                </strong>
                <em>
                  风速 {window?.windSpeedMps} m/s · 浪高 {window?.waveHeightM} m
                </em>
              </div>
              <StatusBadge value="suitable" label="适合" tone="success" compact />
            </div>
            <div className="execution-resource-list">
              {(selected?.requiredResources ?? currentDecision.requiredResources).map(
                (resource, index) => (
                  <span key={resource}>
                    {index === 0 ? (
                      <Users size={13} />
                    ) : resource.includes("CTV") || resource.includes("船") ? (
                      <Ship size={13} />
                    ) : resource.includes("备件") || resource.includes("套件") ? (
                      <PackageCheck size={13} />
                    ) : (
                      <Wrench size={13} />
                    )}
                    <strong>{resource}</strong>
                    <Check size={12} />
                  </span>
                ),
              )}
            </div>
          </Card>

          <Card
            className={cn("decision-approval", approval !== "pending" && "decision-approval--done")}
          >
            <CardHeader
              eyebrow="HUMAN APPROVAL"
              title="授权执行"
              description="批准、拒绝、修订与升级均写入审计记录"
            />
            {!isFeaturedDecision ? (
              <div className="approval-policy" role="note">
                <ShieldCheck size={15} />
                <span>
                  <strong>只读决策快照 · {currentDecision.status.replaceAll("-", " ")}</strong>
                  <small>
                    当前演示仅允许 {featuredDecision.id} 写入服务器审计状态；该决策不会误改 WT-023
                    闭环。
                  </small>
                </span>
              </div>
            ) : approval === "pending" ? (
              <>
                <div className="approval-policy">
                  <ShieldCheck size={15} />
                  <span>
                    <strong>审批策略 HITL-HIGH-02</strong>
                    <small>
                      {workflow.writable
                        ? `将${selected?.label ?? "所选方案"}（${selected?.id ?? "—"}）写入审批、审计与工单状态`
                        : "D1 当前不可写；审批动作已切换为只读"}
                    </small>
                  </span>
                </div>
                <label className="approval-field">
                  <span>审批理由</span>
                  <textarea
                    value={comment}
                    onChange={(event) => setComment(event.target.value)}
                    disabled={!workflow.writable}
                  />
                </label>
                <div className="decision-approval__actions">
                  <Button
                    variant="secondary"
                    onClick={() => submitApproval("reject")}
                    disabled={!workflow.writable}
                  >
                    <X size={14} /> Reject
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => submitApproval("request-revision")}
                    disabled={!workflow.writable}
                  >
                    <RefreshCcw size={14} /> Request Revision
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => submitApproval("escalate")}
                    disabled={!workflow.writable}
                  >
                    <ArrowUpRight size={14} /> Escalate
                  </Button>
                  <Button
                    variant="primary"
                    onClick={() => submitApproval("approve")}
                    disabled={!comment.trim() || !workflow.writable}
                  >
                    <UserCheck size={14} /> Approve Plan
                  </Button>
                </div>
              </>
            ) : (
              <div className="decision-approved-result">
                <span>
                  {approval === "approve" ? (
                    <CheckCircle2 size={26} />
                  ) : approval === "request-revision" ? (
                    <RefreshCcw size={26} />
                  ) : approval === "escalate" ? (
                    <ArrowUpRight size={26} />
                  ) : (
                    <X size={26} />
                  )}
                </span>
                <h3>
                  {approval === "approve"
                    ? `${workflow.approval?.selectedAlternativeId ?? "所选方案"} 已批准`
                    : approval === "request-revision"
                      ? "已请求 AI 修订"
                      : approval === "escalate"
                        ? "已升级至场站经理"
                        : "方案已拒绝"}
                </h3>
                <p>
                  {approval === "approve"
                    ? workflow.workOrderStatus === "scheduled"
                      ? `${selected?.label ?? "所选方案"}「${selected?.title ?? ""}」已写入工单 WO-20260823-017 并排程。`
                      : workflow.workOrderStatus === "in-progress"
                        ? "审批门禁已解除；工单 WO-20260823-017 正在现场执行。"
                        : workflow.workOrderStatus === "completed"
                          ? "审批门禁已解除；工单 WO-20260823-017 已完成并验证。"
                          : "审批记录已写入，等待工单状态同步。"
                    : workflow.approval?.comment}
                </p>
                <small>
                  {workflow.approval?.approver} · {workflow.approval?.approverRole} ·{" "}
                  {workflow.approval
                    ? new Date(workflow.approval.timestamp).toLocaleString("zh-CN")
                    : "—"}
                </small>
                <Button
                  variant="secondary"
                  disabled={!workflow.writable}
                  onClick={() =>
                    workflow.dispatch({
                      type: "replay-approval",
                      timestamp: new Date().toISOString(),
                    })
                  }
                >
                  重放审批环节
                </Button>
              </div>
            )}
          </Card>
        </aside>
      </section>
    </AppShell>
  );
}
