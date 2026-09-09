"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  CircleGauge,
  Database,
  ExternalLink,
  FileSearch,
  Filter,
  GitBranch,
  LockKeyhole,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";
import { StatusBadge, type StatusTone } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { apiGet } from "@/lib/api-client";
import {
  createDiagnosisRecords,
  diagnosisModelMeta,
  diagnosisRecords,
  sortDiagnosisRecords,
  type DiagnosisRecord,
  type DiagnosisStatus,
} from "@/lib/diagnosis-data";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import type { RiskLevel } from "@/lib/types";

import styles from "./diagnosis-center-page.module.css";

type StatusFilter = "all" | DiagnosisStatus;
type RiskFilter = "all" | RiskLevel;

interface DiagnosisResponse {
  readonly data: readonly DiagnosisRecord[];
  readonly meta: {
    readonly count: number;
    readonly total: number;
    readonly filteredTotal: number;
    readonly model: typeof diagnosisModelMeta;
  };
}

const statusLabels: Readonly<Record<DiagnosisStatus, string>> = {
  triage: "待分诊",
  monitoring: "持续监测",
  analyzed: "诊断已形成",
  "awaiting-review": "人工复核中",
  "revision-needed": "方案待修订",
  rejected: "方案被拒绝",
  scheduled: "等待安全窗口",
  "in-progress": "受控作业中",
  closed: "验证闭环",
};

const riskLabels: Readonly<Record<RiskLevel, string>> = {
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
};

const riskTone = (risk: RiskLevel): StatusTone =>
  risk === "critical"
    ? "critical"
    : risk === "high"
      ? "warning"
      : risk === "medium"
        ? "info"
        : "success";

const statusTone = (status: DiagnosisStatus): StatusTone => {
  if (status === "closed") return "success";
  if (status === "in-progress" || status === "scheduled" || status === "analyzed") return "info";
  if (status === "rejected") return "critical";
  if (status === "monitoring") return "neutral";
  return "warning";
};

const sourceLabels: Readonly<Record<string, string>> = {
  "scada-anomaly": "SCADA 异常检出",
  "alarm-correlation": "告警关联接入",
  "scheduled-health-scan": "定时健康扫描",
};

const initialRecords = sortDiagnosisRecords(diagnosisRecords, "priority-desc");

export function DiagnosisCenterPage() {
  const workflow = useDemoWorkflow();
  const [selectedId, setSelectedId] = useState("WT-023");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");

  useEffect(() => {
    const turbineId = new URLSearchParams(window.location.search).get("turbineId")?.toUpperCase();
    if (!turbineId || !diagnosisRecords.some((record) => record.turbineId === turbineId)) return;
    const timer = window.setTimeout(() => setSelectedId(turbineId), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const endpoint = useMemo(() => {
    const params = new URLSearchParams({ limit: "64", sort: "priority-desc" });
    if (query.trim()) params.set("q", query.trim());
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (riskFilter !== "all") params.set("risk", riskFilter);
    return `/api/diagnoses?${params.toString()}`;
  }, [query, riskFilter, statusFilter]);

  const diagnosisQuery = useQuery({
    queryKey: ["diagnoses", endpoint],
    queryFn: ({ signal }) => apiGet<DiagnosisResponse>(endpoint, signal),
    initialData: {
      data: initialRecords,
      meta: {
        count: initialRecords.length,
        total: initialRecords.length,
        filteredTotal: initialRecords.length,
        model: diagnosisModelMeta,
      },
    },
    initialDataUpdatedAt: 0,
    staleTime: 0,
  });

  const workflowRecords = useMemo(
    () =>
      createDiagnosisRecords({
        missionStatus: workflow.missionStatus,
        decisionStatus: workflow.decisionStatus,
        workOrderStatus: workflow.workOrderStatus,
      }),
    [workflow.decisionStatus, workflow.missionStatus, workflow.workOrderStatus],
  );
  const featured = workflowRecords[22]!;
  const records = useMemo(
    () =>
      diagnosisQuery.data.data.map((record) =>
        record.turbineId === featured.turbineId ? featured : record,
      ),
    [diagnosisQuery.data.data, featured],
  );
  const selected = records.find((record) => record.turbineId === selectedId) ?? records[0] ?? null;

  useEffect(() => {
    if (!selected || selected.turbineId === selectedId) return;
    const timer = window.setTimeout(() => setSelectedId(selected.turbineId), 0);
    return () => window.clearTimeout(timer);
  }, [selected, selectedId]);

  const highRiskCount = records.filter(
    (record) => record.risk === "critical" || record.risk === "high",
  ).length;
  const reviewCount = records.filter((record) => record.status === "awaiting-review").length;
  const topCandidate = selected?.candidates[0] ?? null;

  return (
    <AppShell activePath="/diagnosis">
      <PageHeader
        eyebrow="智能运维"
        title="智能诊断中心"
        description="从异常接入到差分诊断、Agent 协作和人工门禁，用结构化证据解释每一条诊断结论。"
        breadcrumb={["智能运维", "智能诊断"]}
        meta={
          <>
            <StatusBadge value="info" label="DETERMINISTIC DEMO" tone="info" />
            <span className="page-meta-text">64 台机组 · 只读诊断快照</span>
          </>
        }
        actions={
          <Link className="button button--secondary button--md" href="/missions/MISSION-2026-0823">
            <GitBranch size={15} /> 查看 WT-023 Mission
          </Link>
        }
      />

      <section className={styles.modelNotice} aria-label="诊断模型边界">
        <span className={styles.noticeIcon}>
          <Sparkles size={18} aria-hidden="true" />
        </span>
        <div>
          <strong>AI-native 诊断工作台 · readOnly=true · realInference=false</strong>
          <p>{diagnosisModelMeta.notice}</p>
        </div>
        <span className={styles.noticeFact}>
          <Database size={13} /> 固定证据快照
        </span>
        <span className={styles.noticeFact}>
          <BadgeCheck size={13} /> 公开可审计输出
        </span>
      </section>

      {diagnosisQuery.isError ? (
        <div className={styles.errorBanner} role="status">
          <AlertTriangle size={15} /> 诊断 API 暂不可用，当前显示内置只读快照。
        </div>
      ) : null}

      <section className={styles.toolbar} aria-label="诊断筛选">
        <label className={styles.assetSelect}>
          <span>分析对象</span>
          <select
            value={selected?.turbineId ?? ""}
            disabled={!records.length}
            onChange={(event) => setSelectedId(event.target.value)}
          >
            {records.length ? (
              records.map((record) => (
                <option key={record.turbineId} value={record.turbineId}>
                  {record.turbineId} · {record.headline}
                </option>
              ))
            ) : (
              <option value="">无匹配资产</option>
            )}
          </select>
        </label>
        <label className={styles.searchBox}>
          <Search size={15} aria-hidden="true" />
          <input
            aria-label="搜索诊断记录"
            placeholder="搜索机组、发现或候选故障模式…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className={styles.filterSelect}>
          <Filter size={14} aria-hidden="true" />
          <select
            aria-label="按诊断状态筛选"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
          >
            <option value="all">全部状态</option>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.filterSelect}>
          <CircleGauge size={14} aria-hidden="true" />
          <select
            aria-label="按风险筛选"
            value={riskFilter}
            onChange={(event) => setRiskFilter(event.target.value as RiskFilter)}
          >
            <option value="all">全部风险</option>
            {Object.entries(riskLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}风险
              </option>
            ))}
          </select>
        </label>
        <div className={styles.toolbarStats}>
          <span>
            <strong>{highRiskCount}</strong> 高风险
          </span>
          <span>
            <strong>{reviewCount}</strong> 人工复核
          </span>
          <span>
            <strong>{records.length}</strong> / 64
          </span>
        </div>
      </section>

      <div className={styles.workspace}>
        <aside className={styles.inboxPanel}>
          <div className={styles.panelHeader}>
            <div>
              <span>DIAGNOSIS INBOX</span>
              <h2>机组诊断记录</h2>
            </div>
            <span
              className={styles.syncState}
              data-fetching={diagnosisQuery.isFetching || undefined}
            >
              {diagnosisQuery.isFetching
                ? "同步中"
                : `${diagnosisQuery.data.meta.filteredTotal} 条`}
            </span>
          </div>
          <div className={styles.recordList}>
            {records.map((record) => (
              <button
                key={record.id}
                type="button"
                className={
                  record.turbineId === selected?.turbineId ? styles.selectedRecord : undefined
                }
                onClick={() => setSelectedId(record.turbineId)}
                aria-pressed={record.turbineId === selected?.turbineId}
              >
                <span className={styles.recordTopline}>
                  <strong>{record.turbineId}</strong>
                  <StatusBadge
                    value={record.risk}
                    label={riskLabels[record.risk]}
                    tone={riskTone(record.risk)}
                    compact
                  />
                </span>
                <span className={styles.recordHeadline}>{record.headline}</span>
                <span className={styles.recordMeta}>
                  <span>{statusLabels[record.status]}</span>
                  <span>异常 {record.anomaly.anomalyScore.toFixed(2)}</span>
                  <span>置信 {record.overallConfidencePercent}%</span>
                </span>
              </button>
            ))}
            {!records.length ? (
              <div className={styles.emptyState}>
                <Search size={20} />
                <strong>没有匹配的诊断记录</strong>
                <p>调整关键词、状态或风险筛选后重试。</p>
              </div>
            ) : null}
          </div>
        </aside>

        {selected && topCandidate ? (
          <main className={styles.detailPanel} aria-label={`${selected.turbineId} 诊断详情`}>
            <section className={styles.detailHero}>
              <div className={styles.heroCopy}>
                <span className={styles.heroEyebrow}>SELECTED DIAGNOSIS · {selected.id}</span>
                <div className={styles.heroTitleRow}>
                  <h2>{selected.turbineId}</h2>
                  <StatusBadge
                    value={selected.status}
                    label={statusLabels[selected.status]}
                    tone={statusTone(selected.status)}
                  />
                  <StatusBadge
                    value={selected.risk}
                    label={`${riskLabels[selected.risk]}风险`}
                    tone={riskTone(selected.risk)}
                  />
                </div>
                <h3>{selected.headline}</h3>
                <p>
                  主候选：{topCandidate.faultMode} · 概率 {topCandidate.probabilityPercent}% ·
                  结论置信度 {selected.overallConfidencePercent}%
                </p>
              </div>
              <div className={styles.heroMetrics}>
                <span>
                  <small>HEALTH</small>
                  <strong>{selected.healthScore}</strong>
                </span>
                <span>
                  <small>ANOMALY</small>
                  <strong>{selected.anomaly.anomalyScore.toFixed(2)}</strong>
                </span>
                <span>
                  <small>CITATIONS</small>
                  <strong>{selected.citations.length}</strong>
                </span>
              </div>
              <div className={styles.heroActions}>
                {selected.missionId ? (
                  <Link className={styles.primaryLink} href={`/missions/${selected.missionId}`}>
                    <GitBranch size={14} /> 查看现有 Mission <ArrowRight size={13} />
                  </Link>
                ) : (
                  <button type="button" disabled title="当前只读演示不会创建新的 Mission">
                    未关联 Mission
                  </button>
                )}
                <Link className={styles.secondaryLink} href={`/turbines/${selected.turbineId}`}>
                  打开数字资产 <ChevronRight size={13} />
                </Link>
              </div>
            </section>

            <section className={styles.summaryGrid}>
              <article className={styles.anomalyPanel}>
                <div className={styles.sectionHeader}>
                  <span className={styles.sectionIcon}>
                    <Activity size={16} />
                  </span>
                  <div>
                    <span>ANOMALY INTAKE</span>
                    <h3>异常接入</h3>
                    <p>{sourceLabels[selected.anomaly.source]}</p>
                  </div>
                  <StatusBadge
                    value={
                      selected.anomaly.anomalyScore >= selected.anomaly.threshold
                        ? "warning"
                        : "normal"
                    }
                    label={`SCORE ${selected.anomaly.anomalyScore.toFixed(2)}`}
                    compact
                  />
                </div>
                <p className={styles.anomalySummary}>{selected.anomaly.summary}</p>
                <div className={styles.signalGrid}>
                  {selected.anomaly.signals.map((signal) => (
                    <div key={signal.id} data-abnormal={signal.abnormal || undefined}>
                      <span>{signal.label}</span>
                      <strong>
                        {signal.value} <small>{signal.unit}</small>
                      </strong>
                      <small>
                        基线 {signal.baseline} · {signal.deltaPercent > 0 ? "+" : ""}
                        {signal.deltaPercent}%
                      </small>
                    </div>
                  ))}
                </div>
              </article>

              <article className={styles.gatePanel} data-state={selected.gate.state}>
                <div className={styles.sectionHeader}>
                  <span className={styles.sectionIcon}>
                    <LockKeyhole size={16} />
                  </span>
                  <div>
                    <span>RISK &amp; GOVERNANCE</span>
                    <h3>风险与人工门禁</h3>
                    <p>Human-in-the-loop</p>
                  </div>
                </div>
                <div className={styles.gateMessage}>
                  <ShieldCheck size={18} />
                  <div>
                    <strong>{selected.gate.title}</strong>
                    <p>{selected.gate.explanation}</p>
                  </div>
                </div>
                <div className={styles.gateColumns}>
                  <div>
                    <span>允许</span>
                    <ul>
                      {selected.gate.allowedActions.map((item) => (
                        <li key={item}>
                          <CheckCircle2 size={12} /> {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <span>受限</span>
                    <ul>
                      {selected.gate.blockedActions.map((item) => (
                        <li key={item}>
                          <LockKeyhole size={12} /> {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
                {selected.gate.decisionStatus ? (
                  <div className={styles.gateStateRow}>
                    <span>Decision · {selected.gate.decisionStatus}</span>
                    <span>Work order · {selected.gate.workOrderStatus}</span>
                  </div>
                ) : null}
              </article>
            </section>

            <section className={styles.differentialPanel}>
              <div className={styles.sectionHeader}>
                <span className={styles.sectionIcon}>
                  <Target size={16} />
                </span>
                <div>
                  <span>STRUCTURED DIFFERENTIAL</span>
                  <h3>差分诊断</h3>
                  <p>候选故障模式、支持证据、反证与下一步</p>
                </div>
                <span className={styles.probabilityCheck}>
                  <BadgeCheck size={13} /> 概率合计 100%
                </span>
              </div>
              <div className={styles.candidateList}>
                {selected.candidates.map((candidate, index) => (
                  <article key={candidate.id} className={styles.candidateCard}>
                    <div className={styles.candidateRank}>{String(index + 1).padStart(2, "0")}</div>
                    <div className={styles.candidateBody}>
                      <div className={styles.candidateTitle}>
                        <div>
                          <strong>{candidate.faultMode}</strong>
                          <span>{candidate.subsystem}</span>
                        </div>
                        <div className={styles.probability}>
                          <strong>{candidate.probabilityPercent}%</strong>
                          <small>置信 {candidate.confidencePercent}%</small>
                        </div>
                      </div>
                      <div className={styles.probabilityBar} aria-hidden="true">
                        <i style={{ width: `${candidate.probabilityPercent}%` }} />
                      </div>
                      <div className={styles.evidenceColumns}>
                        <div>
                          <span>支持证据</span>
                          <ul>
                            {candidate.supportingSummary.map((item) => (
                              <li key={item}>
                                <CheckCircle2 size={12} /> {item}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <span>反证 / 不确定性</span>
                          <ul>
                            {candidate.counterEvidence.map((item) => (
                              <li key={item}>
                                <AlertTriangle size={12} /> {item}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                      <div className={styles.nextStep}>
                        <ArrowRight size={13} />
                        <span>
                          <strong>建议下一步</strong> {candidate.recommendedNextStep}
                        </span>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className={styles.lowerGrid}>
              <article className={styles.collaborationPanel}>
                <div className={styles.sectionHeader}>
                  <span className={styles.sectionIcon}>
                    <BrainCircuit size={16} />
                  </span>
                  <div>
                    <span>AGENT COLLABORATION</span>
                    <h3>Agent 协作记录</h3>
                    <p>只展示可审计结论、证据引用与工具结果</p>
                  </div>
                </div>
                <ol className={styles.agentFlow}>
                  {selected.collaboration.map((step) => (
                    <li key={step.id} data-status={step.status}>
                      <span className={styles.stepNumber}>{step.sequence}</span>
                      <div className={styles.stepBody}>
                        <div className={styles.stepHeader}>
                          <span>
                            <Bot size={13} />
                            <strong>{step.agentName}</strong>
                            <small>{step.role}</small>
                          </span>
                          <StatusBadge
                            value={step.status}
                            label={
                              step.status === "complete"
                                ? "完成"
                                : step.status === "waiting-human"
                                  ? "等待人工"
                                  : "监测"
                            }
                            tone={
                              step.status === "complete"
                                ? "success"
                                : step.status === "waiting-human"
                                  ? "warning"
                                  : "info"
                            }
                            compact
                          />
                        </div>
                        <p>{step.publicOutput}</p>
                        <div className={styles.toolResults}>
                          {step.toolResults.map((result) => (
                            <span key={`${step.id}-${result.tool}`}>
                              <code>{result.tool}</code> {result.result}
                            </span>
                          ))}
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>
              </article>

              <aside className={styles.citationPanel}>
                <div className={styles.sectionHeader}>
                  <span className={styles.sectionIcon}>
                    <FileSearch size={16} />
                  </span>
                  <div>
                    <span>EVIDENCE CITATIONS</span>
                    <h3>证据引用</h3>
                    <p>点击深链回到原始业务上下文</p>
                  </div>
                </div>
                <div className={styles.citationList}>
                  {selected.citations.map((citation, index) => (
                    <Link key={citation.id} href={citation.href}>
                      <span className={styles.citationIndex}>[{index + 1}]</span>
                      <span>
                        <strong>{citation.title}</strong>
                        <small>{citation.sourceLabel}</small>
                        <p>{citation.summary}</p>
                      </span>
                      <ExternalLink size={13} />
                    </Link>
                  ))}
                </div>
              </aside>
            </section>
          </main>
        ) : (
          <main className={styles.detailPanel} aria-label="诊断详情空状态">
            <div className={styles.emptyState}>
              <Search size={20} />
              <strong>没有可显示的诊断详情</strong>
              <p>当前筛选没有匹配记录；调整关键词、状态或风险后重试。</p>
            </div>
          </main>
        )}
      </div>

      <footer className={styles.methodFooter}>
        <span>
          <Database size={14} /> <strong>数据边界</strong> 固定 SCADA、告警、健康和知识证据
        </span>
        <span>
          <BrainCircuit size={14} /> <strong>解释边界</strong> 结构化结论、反证、工具结果
        </span>
        <span>
          <ShieldCheck size={14} /> <strong>控制边界</strong> 只读；高风险动作必须人工授权
        </span>
      </footer>
    </AppShell>
  );
}
