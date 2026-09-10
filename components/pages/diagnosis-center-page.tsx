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
import type { WindOpsRuntimeMode } from "@/lib/production-runtime";
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
    readonly model: {
      readonly mode: string;
      readonly deterministic: boolean;
      readonly readOnly: boolean;
      readonly realInference: boolean;
      readonly notice: string;
    };
  };
}

interface BenchmarkDiagnosisEnvelope {
  readonly data: readonly {
    readonly replay_run_id: string;
    readonly event: {
      readonly event_id: number;
      readonly farm: string;
      readonly logical_asset_id: string;
      readonly online_turbine_id: string;
    };
    readonly replay: {
      readonly status: string;
      readonly mode: string;
      readonly anchor_at: string;
      readonly time_rule_version: string;
      readonly time_semantics: string;
      readonly error: string | null;
    };
    readonly model: {
      readonly model_id: string | null;
      readonly name: string | null;
      readonly version: string | null;
      readonly kind: string | null;
      readonly artifact_sha256: string | null;
      readonly artifact_present: boolean;
    };
    readonly deployment: {
      readonly deployment_id: string | null;
      readonly status: string | null;
      readonly target_id: string | null;
      readonly stale: boolean;
      readonly threshold_policy_version: string | null;
      readonly threshold_policy_sha256: string | null;
    };
    readonly quality_report: {
      readonly status: string;
      readonly quality_rule_version: string | null;
      readonly feature_set_version: string | null;
      readonly mask_count: number;
      readonly mask_artifact: {
        readonly uri: string | null;
        readonly sha256: string | null;
        readonly present: boolean;
      };
    };
    readonly predictions: readonly {
      readonly prediction_id: string;
      readonly status: string;
      readonly error_code: string | null;
      readonly anomaly_score: number | null;
      readonly binary_prediction: boolean | null;
      readonly component: string | null;
      readonly model_id: string;
      readonly deployment_id: string;
      readonly evaluation_run_id: string | null;
      readonly feature_window: {
        readonly start: string | null;
        readonly end: string | null;
        readonly start_sequence: number | null;
        readonly end_sequence: number | null;
      };
      readonly threshold: {
        readonly value: number | null;
        readonly comparison: string | null;
        readonly policy_version: string | null;
        readonly policy_sha256: string | null;
      };
      readonly time_evidence: {
        readonly synthetic_observed_at: string;
        readonly observed_at_is_synthetic: boolean;
        readonly time_claim: string | null;
        readonly anonymous_observed_at: string | null;
        readonly source_time_stamp: string | number | null;
        readonly source_row_id: number | null;
      };
      readonly quality: {
        readonly signal_count: number;
        readonly signals_truncated: boolean;
        readonly quality_counts: Readonly<Record<string, number>>;
        readonly quality_mask_refs: readonly string[];
      };
      readonly evidence_artifact: {
        readonly uri: string | null;
        readonly sha256: string | null;
        readonly present: boolean;
      };
      readonly links: {
        readonly alarm_id: string | null;
        readonly alarm_status: string | null;
        readonly mission_id: string | null;
        readonly mission_status: string | null;
        readonly decision_id: string | null;
      };
    }[];
    readonly predictions_truncated: boolean;
    readonly first_alert: {
      readonly prediction_id: string;
      readonly alarm_id: string;
      readonly mission_id: string | null;
      readonly synthetic_observed_at: string;
      readonly anonymous_observed_at: string | null;
      readonly source_sequence: number;
      readonly lead_source_rows: number | null;
      readonly lead_semantics: "source-row-offset-not-rul";
    } | null;
    readonly truth: {
      readonly access: "restricted" | "revealed";
      readonly event_label: string | null;
      readonly event_interval_start: number | null;
      readonly event_interval_end: number | null;
      readonly description: string | null;
    };
  }[];
  readonly meta: {
    readonly count: number;
    readonly filtered_total: number;
    readonly truth_revealed: boolean;
    readonly truth_reveal_allowed: boolean;
    readonly bounds: {
      readonly diagnosis_page_max: number;
      readonly predictions_per_replay_max: number;
      readonly signals_inspected_per_prediction_max: number;
    };
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

export function DiagnosisCenterPage({ runtimeMode }: { runtimeMode: WindOpsRuntimeMode }) {
  const workflow = useDemoWorkflow();
  const isProduction = runtimeMode === "production";
  const [selectedId, setSelectedId] = useState("WT-023");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const [selectedBenchmarkReplayId, setSelectedBenchmarkReplayId] = useState("");
  const [revealBenchmarkTruth, setRevealBenchmarkTruth] = useState(false);
  const benchmarkDiagnosisEndpoint =
    runtimeMode === "production"
      ? [
          "/api/backend/benchmarks/diagnoses?limit=16",
          revealBenchmarkTruth ? "&revealTruth=true" : "",
        ].join("")
      : null;
  const benchmarkDiagnosisQuery = useQuery({
    queryKey: ["care-benchmark-diagnoses", benchmarkDiagnosisEndpoint],
    queryFn: ({ signal }) =>
      apiGet<BenchmarkDiagnosisEnvelope>(benchmarkDiagnosisEndpoint ?? "", signal),
    enabled: Boolean(benchmarkDiagnosisEndpoint),
    staleTime: 0,
  });
  const benchmarkDiagnoses = benchmarkDiagnosisQuery.data?.data ?? [];
  const selectedBenchmarkDiagnosis =
    benchmarkDiagnoses.find((row) => row.replay_run_id === selectedBenchmarkReplayId) ??
    benchmarkDiagnoses[0] ??
    null;

  useEffect(() => {
    const turbineId = new URLSearchParams(window.location.search).get("turbineId")?.toUpperCase();
    if (!turbineId || !/^WT-[A-Z0-9-]+$/.test(turbineId)) return;
    const timer = window.setTimeout(() => setSelectedId(turbineId), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (
      !selectedBenchmarkDiagnosis ||
      selectedBenchmarkDiagnosis.replay_run_id === selectedBenchmarkReplayId
    ) {
      return;
    }
    const timer = window.setTimeout(
      () => setSelectedBenchmarkReplayId(selectedBenchmarkDiagnosis.replay_run_id),
      0,
    );
    return () => window.clearTimeout(timer);
  }, [selectedBenchmarkDiagnosis, selectedBenchmarkReplayId]);

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
      data: isProduction ? [] : initialRecords,
      meta: {
        count: isProduction ? 0 : initialRecords.length,
        total: isProduction ? 0 : initialRecords.length,
        filteredTotal: isProduction ? 0 : initialRecords.length,
        // production 初始不携带 fixture 模型声明，等待真实查询返回治理元数据。
        model: isProduction
          ? {
              mode: "pending",
              deterministic: false,
              readOnly: true,
              realInference: false,
              notice: "正在读取生产诊断模型元数据…",
            }
          : diagnosisModelMeta,
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
  const featured = workflowRecords[22];
  const records = useMemo(
    () =>
      isProduction
        ? diagnosisQuery.data.data
        : diagnosisQuery.data.data.map((record) =>
            record.turbineId === featured.turbineId ? featured : record,
          ),
    [diagnosisQuery.data.data, featured, isProduction],
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
    <AppShell runtimeMode={runtimeMode} activePath="/diagnosis">
      <PageHeader
        eyebrow="智能运维"
        title="智能诊断中心"
        description="从异常接入到差分诊断、Agent 协作和人工门禁，用结构化证据解释每一条诊断结论。"
        breadcrumb={["智能运维", "智能诊断"]}
        meta={
          <>
            <StatusBadge
              value="info"
              label={isProduction ? "生产 Mission 诊断" : "确定性演示"}
              tone="info"
            />
            <span className="page-meta-text">
              {diagnosisQuery.data.meta.total} 条权威诊断 · 只读推理输出
            </span>
          </>
        }
        actions={
          isProduction ? (
            selected?.missionId ? (
              <Link
                className="button button--secondary button--md"
                href={`/missions/${selected.missionId}`}
              >
                <GitBranch size={15} /> 查看 {selected.turbineId} Mission
              </Link>
            ) : null
          ) : (
            <Link
              className="button button--secondary button--md"
              href="/missions/MISSION-2026-0823"
            >
              <GitBranch size={15} /> 查看 WT-023 Mission
            </Link>
          )
        }
      />

      <section className={styles.modelNotice} aria-label="诊断模型边界">
        <span className={styles.noticeIcon}>
          <Sparkles size={18} aria-hidden="true" />
        </span>
        <div>
          <strong>
            {isProduction
              ? "受治理模型诊断 · 证据与执行可追溯"
              : "AI 原生诊断工作台 · 只读演示 · 无真实推理"}
          </strong>
          <p>{diagnosisQuery.data.meta.model.notice}</p>
        </div>
        <span className={styles.noticeFact}>
          <Database size={13} /> {isProduction ? "持久化证据" : "固定证据快照"}
        </span>
        <span className={styles.noticeFact}>
          <BadgeCheck size={13} /> 公开可审计输出
        </span>
      </section>

      <section className={styles.benchmarkPanel} aria-label="CARE 回放诊断证据">
        <header className={styles.benchmarkHeader}>
          <div>
            <span>CARE v6 · GOVERNED REPLAY</span>
            <h2>异常预测与业务闭环</h2>
            <p>合成回放时间、匿名来源时间、质量 mask、模型预测、告警与 Mission 同链核验。</p>
          </div>
          <div className={styles.benchmarkActions}>
            <button
              type="button"
              onClick={() => void benchmarkDiagnosisQuery.refetch()}
              disabled={runtimeMode !== "production" || benchmarkDiagnosisQuery.isFetching}
            >
              {benchmarkDiagnosisQuery.isFetching ? "同步中…" : "刷新证据"}
            </button>
            <button
              type="button"
              onClick={() => setRevealBenchmarkTruth((current) => !current)}
              disabled={
                runtimeMode !== "production" ||
                benchmarkDiagnosisQuery.isFetching ||
                !benchmarkDiagnosisQuery.data?.meta.truth_reveal_allowed
              }
              title={
                benchmarkDiagnosisQuery.data?.meta.truth_reveal_allowed
                  ? undefined
                  : "当前身份没有 benchmark_truth 数据范围"
              }
            >
              {revealBenchmarkTruth ? "隐藏真值" : "按权限揭示真值"}
            </button>
          </div>
        </header>

        {runtimeMode !== "production" ? (
          <div className={styles.benchmarkState}>
            演示模式不加载 CARE fixture，也不把固定诊断、提前量或模型分数冒充真实评估。
          </div>
        ) : benchmarkDiagnosisQuery.isLoading ? (
          <div className={styles.benchmarkState}>正在读取 PostgreSQL 回放与诊断证据…</div>
        ) : benchmarkDiagnosisQuery.isError ? (
          <div className={styles.benchmarkState} data-tone="error" role="alert">
            <AlertTriangle size={15} /> CARE 诊断 API、数据域或真值权限校验失败；未回退演示数据。
          </div>
        ) : !selectedBenchmarkDiagnosis ? (
          <div className={styles.benchmarkState}>
            当前授权范围没有 CARE replay diagnosis；不会生成占位预测或 Mission。
          </div>
        ) : (
          <div className={styles.benchmarkWorkspace}>
            <aside className={styles.benchmarkRuns}>
              {benchmarkDiagnoses.map((diagnosis) => (
                <button
                  type="button"
                  key={diagnosis.replay_run_id}
                  data-selected={
                    diagnosis.replay_run_id === selectedBenchmarkDiagnosis.replay_run_id
                  }
                  onClick={() => setSelectedBenchmarkReplayId(diagnosis.replay_run_id)}
                >
                  <span>
                    <strong>
                      {diagnosis.event.farm}
                      {diagnosis.event.event_id} · {diagnosis.event.online_turbine_id}
                    </strong>
                    <small>{diagnosis.replay_run_id}</small>
                  </span>
                  <StatusBadge
                    value={diagnosis.replay.status}
                    label={diagnosis.replay.status}
                    tone={diagnosis.replay.status === "completed" ? "success" : "warning"}
                    compact
                  />
                </button>
              ))}
            </aside>

            <div className={styles.benchmarkDetail}>
              <div className={styles.benchmarkFacts}>
                <span>
                  <small>时间轴</small>
                  <strong>合成回放时间</strong>
                  <em>{selectedBenchmarkDiagnosis.replay.time_rule_version}</em>
                </span>
                <span data-alert={selectedBenchmarkDiagnosis.deployment.stale}>
                  <small>部署</small>
                  <strong>{selectedBenchmarkDiagnosis.deployment.deployment_id ?? "未绑定"}</strong>
                  <em>
                    {selectedBenchmarkDiagnosis.deployment.stale
                      ? "已陈旧"
                      : (selectedBenchmarkDiagnosis.deployment.status ?? "缺失")}
                  </em>
                </span>
                <span data-alert={!selectedBenchmarkDiagnosis.model.artifact_present}>
                  <small>anomaly 模型制品</small>
                  <strong>
                    {selectedBenchmarkDiagnosis.model.name ??
                      selectedBenchmarkDiagnosis.model.model_id ??
                      "缺失"}
                  </strong>
                  <em>
                    {selectedBenchmarkDiagnosis.model.artifact_present
                      ? selectedBenchmarkDiagnosis.model.artifact_sha256?.slice(0, 12)
                      : "artifact missing"}
                  </em>
                </span>
                <span data-alert={!selectedBenchmarkDiagnosis.quality_report.mask_artifact.present}>
                  <small>质量 mask</small>
                  <strong>
                    {selectedBenchmarkDiagnosis.quality_report.mask_count} 条 ·{" "}
                    {selectedBenchmarkDiagnosis.quality_report.status}
                  </strong>
                  <em>
                    {selectedBenchmarkDiagnosis.quality_report.quality_rule_version ?? "缺失"}
                  </em>
                </span>
              </div>

              <div className={styles.truthStrip} data-revealed={revealBenchmarkTruth}>
                <LockKeyhole size={14} />
                <span>
                  <strong>
                    真值：
                    {selectedBenchmarkDiagnosis.truth.access === "revealed"
                      ? selectedBenchmarkDiagnosis.truth.event_label
                      : "评估前隐藏 / 当前受限"}
                  </strong>
                  <small>
                    {selectedBenchmarkDiagnosis.truth.access === "revealed"
                      ? (selectedBenchmarkDiagnosis.truth.description ?? "无故障描述")
                      : "只有 benchmark_truth 授权可揭示事件区间和故障描述。"}
                  </small>
                </span>
              </div>

              {selectedBenchmarkDiagnosis.first_alert ? (
                <div className={styles.firstAlert}>
                  <Activity size={15} />
                  <span>
                    <strong>
                      最早模型告警 · {selectedBenchmarkDiagnosis.first_alert.alarm_id}
                    </strong>
                    <small>
                      合成时间 {selectedBenchmarkDiagnosis.first_alert.synthetic_observed_at} ·
                      匿名来源时间{" "}
                      {selectedBenchmarkDiagnosis.first_alert.anonymous_observed_at ?? "未记录"} ·
                      提前行数（非 RUL）{" "}
                      {selectedBenchmarkDiagnosis.first_alert.lead_source_rows ?? "真值受限"}
                    </small>
                  </span>
                  {selectedBenchmarkDiagnosis.first_alert.mission_id ? (
                    <Link href={"/missions/" + selectedBenchmarkDiagnosis.first_alert.mission_id}>
                      Mission <ArrowRight size={12} />
                    </Link>
                  ) : (
                    <em>未关联 Mission</em>
                  )}
                </div>
              ) : (
                <div className={styles.benchmarkState}>
                  此 replay 未形成模型告警；正常抑制或连续窗口不足不会伪造 Mission。
                </div>
              )}

              <div className={styles.predictionList}>
                {selectedBenchmarkDiagnosis.predictions.map((prediction) => (
                  <article key={prediction.prediction_id} data-status={prediction.status}>
                    <div className={styles.predictionHeadline}>
                      <span>
                        <strong>
                          score {prediction.anomaly_score ?? "—"} · binary{" "}
                          {prediction.binary_prediction === null
                            ? "—"
                            : prediction.binary_prediction
                              ? "true"
                              : "false"}
                        </strong>
                        <small>
                          threshold {prediction.threshold.value ?? "—"} ·{" "}
                          {prediction.threshold.policy_version ?? "策略缺失"}
                        </small>
                      </span>
                      <StatusBadge
                        value={prediction.status}
                        label={prediction.error_code ?? prediction.status}
                        tone={prediction.status === "succeeded" ? "success" : "critical"}
                        compact
                      />
                    </div>
                    <div className={styles.predictionEvidence}>
                      <span>
                        <small>特征窗口 / sequence</small>
                        <strong>
                          {prediction.feature_window.start ?? "—"} →{" "}
                          {prediction.feature_window.end ?? "—"}
                        </strong>
                        <em>
                          {prediction.feature_window.start_sequence ?? "—"} →{" "}
                          {prediction.feature_window.end_sequence ?? "—"}
                        </em>
                      </span>
                      <span>
                        <small>时间证据</small>
                        <strong>合成 {prediction.time_evidence.synthetic_observed_at}</strong>
                        <em>
                          匿名 {prediction.time_evidence.anonymous_observed_at ?? "未记录"} · row{" "}
                          {prediction.time_evidence.source_row_id ?? "—"}
                        </em>
                      </span>
                      <span>
                        <small>质量 / mask</small>
                        <strong>
                          good {prediction.quality.quality_counts.good ?? 0} · uncertain{" "}
                          {prediction.quality.quality_counts.uncertain ?? 0} · bad{" "}
                          {prediction.quality.quality_counts.bad ?? 0}
                        </strong>
                        <em>
                          {prediction.quality.quality_mask_refs.length
                            ? prediction.quality.quality_mask_refs.join(" · ")
                            : "无 mask 引用"}
                        </em>
                      </span>
                      <span data-alert={!prediction.evidence_artifact.present}>
                        <small>闭环链接 / evidence</small>
                        <strong>
                          Prediction {prediction.prediction_id.slice(0, 12)} · Alarm{" "}
                          {prediction.links.alarm_id ?? "—"}
                        </strong>
                        <em>
                          Mission {prediction.links.mission_id ?? "—"} · Decision{" "}
                          {prediction.links.decision_id ?? "—"} ·{" "}
                          {prediction.evidence_artifact.present ? "artifact verified" : "缺制品"}
                        </em>
                      </span>
                    </div>
                  </article>
                ))}
                {!selectedBenchmarkDiagnosis.predictions.length ? (
                  <div className={styles.benchmarkState}>
                    此 replay 没有持久化 ModelPrediction；页面不会根据 SCADA 属性合成分数。
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        )}
      </section>

      {diagnosisQuery.isError ? (
        <div className={styles.errorBanner} role="status">
          <AlertTriangle size={15} /> 诊断 API 暂不可用；
          {isProduction ? "生产模式不会回退到演示诊断。" : "当前显示内置只读快照。"}
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
            <strong>{records.length}</strong> / {diagnosisQuery.data.meta.total}
          </span>
        </div>
      </section>

      <div className={styles.workspace}>
        <aside className={styles.inboxPanel}>
          <div className={styles.panelHeader}>
            <div>
              <span>诊断收件箱</span>
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
                <span className={styles.heroEyebrow}>已选诊断 · {selected.id}</span>
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
                  <small>健康度</small>
                  <strong>{selected.healthScore}</strong>
                </span>
                <span>
                  <small>异常分数</small>
                  <strong>{selected.anomaly.anomalyScore.toFixed(2)}</strong>
                </span>
                <span>
                  <small>引用数</small>
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
                    <span>异常输入</span>
                    <h3>异常接入</h3>
                    <p>{sourceLabels[selected.anomaly.source]}</p>
                  </div>
                  <StatusBadge
                    value={
                      selected.anomaly.anomalyScore >= selected.anomaly.threshold
                        ? "warning"
                        : "normal"
                    }
                    label={`分数 ${selected.anomaly.anomalyScore.toFixed(2)}`}
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
                    <span>风险与治理</span>
                    <h3>风险与人工门禁</h3>
                    <p>人工参与审批</p>
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
                    <span>决策 · {selected.gate.decisionStatus}</span>
                    <span>工单 · {selected.gate.workOrderStatus}</span>
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
                  <span>结构化鉴别诊断</span>
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
                    <span>AGENT 协作</span>
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
                    <span>证据引用</span>
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
