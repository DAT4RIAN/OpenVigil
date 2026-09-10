"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import type { Decision, DecisionAlternative } from "@/lib/types";
import { apiGet, apiPost } from "@/lib/api-client";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { isServerWorkflowAlternativeId } from "@/lib/server-workflow-contract";
import {
  localizedEvidenceType,
  localizedSeverityLabel,
  localizedStatusLabel,
} from "@/lib/ui-localization";
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
          <Sparkles size={11} /> AI 推荐
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
            label={localizedSeverityLabel(option.safetyRisk)}
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

export function DecisionCenterPage({ runtimeMode }: { runtimeMode: "demo" | "production" }) {
  const productionMode = runtimeMode === "production";
  const [activeDecisionId, setActiveDecisionId] = useState(
    productionMode ? "" : featuredDecision.id,
  );
  const [selectedId, setSelectedId] = useState(
    productionMode ? "" : featuredDecision.recommendedAlternativeId,
  );
  const [comment, setComment] = useState(
    productionMode ? "" : "同意执行方案 B。已确认安全措施、资源和气象窗口。",
  );
  const workflow = useDemoWorkflow();
  const [showAllEvidence, setShowAllEvidence] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const approvalWritable = productionMode || workflow.writable;
  const decisionQuery = useQuery({
    queryKey: ["decisions", runtimeMode],
    queryFn: ({ signal }) =>
      apiGet<{ readonly data: readonly Decision[] }>("/api/decisions", signal),
    initialData: productionMode ? undefined : { data: decisions },
  });
  const decisionItems = useMemo(() => decisionQuery.data?.data ?? [], [decisionQuery.data?.data]);
  const currentDecision =
    decisionItems.find((decision) => decision.id === activeDecisionId) ?? decisionItems[0];
  const isFeaturedDecision = !productionMode && currentDecision?.id === featuredDecision.id;
  const approval = productionMode
    ? (currentDecision?.approval.action ?? "pending")
    : isFeaturedDecision
      ? (workflow.approval?.action ?? "pending")
      : (currentDecision?.approval.action ?? "pending");
  const effectiveSelectedId = productionMode
    ? selectedId ||
      currentDecision?.approval.selectedAlternativeId ||
      currentDecision?.recommendedAlternativeId
    : isFeaturedDecision && workflow.approval?.selectedAlternativeId
      ? workflow.approval.selectedAlternativeId
      : selectedId;
  const selected =
    currentDecision?.alternatives.find((option) => option.id === effectiveSelectedId) ??
    currentDecision?.alternatives[0];
  const weatherWindow = productionMode
    ? undefined
    : (weatherWindows.find((item) => item.id === selected?.weatherWindowId) ?? weatherWindows[0]);
  const relatedEvidence = productionMode
    ? (currentDecision?.evidenceIds ?? []).map((id) => ({ id, label: id }))
    : evidenceItems
        .filter((item) => currentDecision?.evidenceIds.includes(item.id))
        .map((item) => ({ id: item.id, label: localizedEvidenceType(item.type) }));

  useEffect(() => {
    if (!currentDecision) return;
    const timer = window.setTimeout(() => {
      if (!activeDecisionId || !decisionItems.some((item) => item.id === activeDecisionId)) {
        setActiveDecisionId(currentDecision.id);
      }
      if (!selectedId || !currentDecision.alternatives.some((item) => item.id === selectedId)) {
        setSelectedId(
          currentDecision.approval.selectedAlternativeId ??
            currentDecision.recommendedAlternativeId,
        );
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activeDecisionId, currentDecision, decisionItems, selectedId]);

  async function submitApproval(action: "approve" | "reject" | "request-revision" | "escalate") {
    if (!currentDecision || !selected) return;
    if (productionMode) {
      if (!currentDecision.missionRevision) {
        setApprovalError("当前决策缺少 Mission 修订号，无法安全提交审批。");
        return;
      }
      if (comment.trim().length < 3) {
        setApprovalError("请显式填写至少 3 个字符的审批理由，不会代入演示文案。");
        return;
      }
      setSubmitting(true);
      setApprovalError(null);
      try {
        await apiPost(
          `/api/backend/missions/${encodeURIComponent(currentDecision.missionId)}/approvals`,
          {
            action: action.replaceAll("-", "_"),
            expected_revision: currentDecision.missionRevision,
            selected_alternative_id: action === "approve" ? selected.id : null,
            reason: comment.trim(),
            comment: comment.trim(),
          },
        );
        await decisionQuery.refetch();
      } catch (reason) {
        setApprovalError(reason instanceof Error ? reason.message : "审批提交失败，请重试。");
      } finally {
        setSubmitting(false);
      }
      return;
    }
    if (!isFeaturedDecision || !isServerWorkflowAlternativeId(selected.id)) return;
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

  if (!currentDecision) {
    return (
      <AppShell runtimeMode={runtimeMode} activePath="/decisions">
        <PageHeader
          eyebrow="AI 运营"
          title="决策中心"
          description="基于安全、成本、停机损失、天气与资源的可解释运维决策"
          breadcrumb={["AI 运营", "决策中心"]}
        />
        <Card>
          <CardHeader
            eyebrow={productionMode ? "生产数据" : "审核队列"}
            title={decisionQuery.isLoading ? "正在加载决策…" : "当前没有待处理决策"}
            description={
              decisionQuery.error instanceof Error
                ? decisionQuery.error.message
                : "新 Mission 完成分析与多 Agent 复核后，决策会进入这里。"
            }
          />
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/decisions">
      <PageHeader
        eyebrow="AI 运营"
        title="决策中心"
        description="基于安全、成本、停机损失、天气与资源的可解释运维决策"
        breadcrumb={["AI 运营", "决策中心"]}
        meta={
          <>
            <StatusBadge
              value={isFeaturedDecision ? workflow.decisionStatus : currentDecision.status}
              label={localizedStatusLabel(
                isFeaturedDecision ? workflow.decisionStatus : currentDecision.status,
              )}
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
            <span className="page-meta-text">人工审批策略 · 所有动作写入审计记录</span>
          </>
        }
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => document.getElementById("decision-evidence")?.scrollIntoView()}
            >
              <FileSearch size={15} /> 证据策略
            </Button>
            <Button
              variant="primary"
              onClick={() => document.getElementById("decision-review-queue")?.scrollIntoView()}
            >
              <ShieldCheck size={15} /> 审核队列
            </Button>
          </>
        }
      />

      <section className="decision-layout">
        <aside className="decision-queue" id="decision-review-queue">
          <div className="decision-queue__header">
            <div>
              <span className="eyebrow">审核队列</span>
              <h2>待决策事件</h2>
            </div>
            <span>{decisionItems.length}</span>
          </div>
          {decisionItems.map((decision, index) => (
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
                  {localizedStatusLabel(
                    !productionMode && decision.id === featuredDecision.id
                      ? workflow.decisionStatus
                      : decision.status,
                  )}
                </em>
              </span>
              <ChevronRight size={14} />
            </button>
          ))}
          <div className="decision-queue__footer">
            <CheckCircle2 size={14} />
            <span>
              <strong>
                {productionMode
                  ? `${decisionItems.filter((item) => item.status === "approved").length} 项已批准`
                  : "12 项今日已完成"}
              </strong>
              <small>{productionMode ? "来自权威审批记录" : "平均审批 18 分钟"}</small>
            </span>
          </div>
        </aside>

        <main className="decision-workspace">
          <Card className="decision-incident">
            <div className="decision-incident__icon">
              <AlarmTriangle size={21} />
            </div>
            <div className="decision-incident__copy">
              <span className="eyebrow">事件 · {currentDecision.missionId}</span>
              <h2>{currentDecision.incident}</h2>
              <p>{currentDecision.diagnosis}</p>
            </div>
            <div className="decision-confidence">
              <small>AI 置信度</small>
              <strong>{currentDecision.confidencePercent}%</strong>
              <span>高</span>
            </div>
            <a href={`/missions/${currentDecision.missionId}`}>
              Mission 详情 <ArrowRight size={13} />
            </a>
          </Card>

          <section className="decision-evidence-bar" id="decision-evidence">
            <div>
              <FileSearch size={15} />
              <span>
                <small>证据</small>
                <strong>{relatedEvidence.length} 结构化证据</strong>
              </span>
            </div>
            {relatedEvidence.slice(0, showAllEvidence ? relatedEvidence.length : 4).map((item) => (
              <span className="evidence-source-chip" key={item.id}>
                {item.label}
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
              eyebrow="备选方案"
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
              eyebrow="推荐依据"
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
            <CardHeader eyebrow="已选方案" title={selected?.label ?? "方案 B"} />
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
                    label={localizedSeverityLabel(selected?.safetyRisk ?? "medium")}
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
            <CardHeader eyebrow="执行就绪度" title="作业条件" />
            <div className="readiness-detail">
              <span>
                <WeatherSun size={16} />
              </span>
              <div>
                <small>天气窗口</small>
                <strong>
                  {productionMode
                    ? (selected?.weatherWindowId ?? "该方案无需现场天气窗口")
                    : `${new Date(weatherWindow?.startsAt ?? "2026-08-14").toLocaleDateString(
                        "zh-CN",
                        {
                          month: "short",
                          day: "numeric",
                        },
                      )} · 08:00–16:00`}
                </strong>
                <em>
                  {productionMode
                    ? selected?.weatherWindowId
                      ? "批准时由后端再次校验并原子预留窗口"
                      : "无需海上现场资源"
                    : `风速 ${weatherWindow?.windSpeedMps} m/s · 浪高 ${weatherWindow?.waveHeightM} m`}
                </em>
              </div>
              <StatusBadge
                value={selected?.weatherWindowId ? "suitable" : "not-required"}
                label={selected?.weatherWindowId ? "待批准时复核" : "无需窗口"}
                tone={selected?.weatherWindowId ? "success" : "info"}
                compact
              />
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
              eyebrow="人工审批"
              title="授权执行"
              description="批准、拒绝、修订与升级均写入审计记录"
            />
            {!productionMode && !isFeaturedDecision ? (
              <div className="approval-policy" role="note">
                <ShieldCheck size={15} />
                <span>
                  <strong>只读决策快照 · {localizedStatusLabel(currentDecision.status)}</strong>
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
                      {approvalWritable
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
                    disabled={!approvalWritable || submitting}
                    placeholder={
                      productionMode ? "请显式填写审批意见，提交后写入生产审计记录" : undefined
                    }
                  />
                </label>
                {approvalError ? (
                  <p className="field-evidence-form__error" role="alert">
                    {approvalError}
                  </p>
                ) : null}
                <div className="decision-approval__actions">
                  <Button
                    variant="secondary"
                    onClick={() => void submitApproval("reject")}
                    disabled={
                      !approvalWritable ||
                      submitting ||
                      (productionMode && comment.trim().length < 3)
                    }
                  >
                    <X size={14} /> 拒绝
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => void submitApproval("request-revision")}
                    disabled={
                      !approvalWritable ||
                      submitting ||
                      (productionMode && comment.trim().length < 3)
                    }
                  >
                    <RefreshCcw size={14} /> 要求修订
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => void submitApproval("escalate")}
                    disabled={
                      !approvalWritable ||
                      submitting ||
                      (productionMode && comment.trim().length < 3)
                    }
                  >
                    <ArrowUpRight size={14} /> 升级处理
                  </Button>
                  <Button
                    variant="primary"
                    onClick={() => void submitApproval("approve")}
                    disabled={
                      !comment.trim() ||
                      (productionMode && comment.trim().length < 3) ||
                      !approvalWritable ||
                      submitting
                    }
                  >
                    <UserCheck size={14} /> 批准方案
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
                    ? `${productionMode ? currentDecision.approval.selectedAlternativeId : (workflow.approval?.selectedAlternativeId ?? "所选方案")} 已批准`
                    : approval === "request-revision"
                      ? "已请求 AI 修订"
                      : approval === "escalate"
                        ? "已升级至场站经理"
                        : "方案已拒绝"}
                </h3>
                <p>
                  {productionMode
                    ? currentDecision.approval.comment ||
                      currentDecision.approval.reason ||
                      "审批记录已写入权威后端。"
                    : approval === "approve"
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
                  {productionMode
                    ? `${currentDecision.approval.approver ?? "—"} · ${
                        currentDecision.approval.timestamp
                          ? new Date(currentDecision.approval.timestamp).toLocaleString("zh-CN")
                          : "—"
                      }`
                    : `${workflow.approval?.approver ?? "—"} · ${
                        workflow.approval?.approverRole ?? "—"
                      } · ${
                        workflow.approval
                          ? new Date(workflow.approval.timestamp).toLocaleString("zh-CN")
                          : "—"
                      }`}
                </small>
                {!productionMode ? (
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
                ) : null}
              </div>
            )}
          </Card>
        </aside>
      </section>
    </AppShell>
  );
}
