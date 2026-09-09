"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  CalendarClock,
  ChevronRight,
  CircleGauge,
  Clock3,
  Database,
  Filter,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wrench,
} from "lucide-react";
import {
  matrixRiskFor,
  predictiveAssessments,
  predictiveModelMeta,
  probabilityBandFor,
  type PredictiveAssessment,
} from "@/app/api/predictive-assessments/fixtures";
import { TimeSeriesChart, type TimeSeriesPoint } from "@/components/charts/time-series-chart";
import { DataTable } from "@/components/data-display/data-table";
import { HealthBadge, StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { apiGet } from "@/lib/api-client";
import { scadaSeries } from "@/lib";
import type { DemoWorkflowState } from "@/lib/demo-workflow";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import type { RiskLevel, TrendDirection } from "@/lib/types";

import styles from "./predictive-maintenance-page.module.css";

const windows = ["24H", "7D", "30D", "90D"] as const;
type TimeWindow = (typeof windows)[number];
type RiskFilter = "all" | RiskLevel;
type TrendFilter = "all" | TrendDirection;

type PredictiveResponse = {
  data: PredictiveAssessment[];
  meta: {
    count: number;
    total: number;
    filteredTotal: number;
    model: typeof predictiveModelMeta;
  };
};

const riskLabels: Record<RiskLevel, string> = {
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
};

const trendLabels: Record<TrendDirection, string> = {
  improving: "改善",
  stable: "稳定",
  declining: "下降",
};

const riskTone = (risk: RiskLevel): "critical" | "warning" | "info" | "success" =>
  risk === "critical"
    ? "critical"
    : risk === "high"
      ? "warning"
      : risk === "medium"
        ? "info"
        : "success";

const byPriority = (left: PredictiveAssessment, right: PredictiveAssessment): number =>
  right.priorityScore - left.priorityScore || left.turbineId.localeCompare(right.turbineId);

const assessmentColumns: readonly LegacyColumnDef<PredictiveAssessment, unknown>[] = [
  {
    accessorKey: "priorityScore",
    header: "优先分",
    cell: ({ row }) => <span className={styles.rank}>{row.original.priorityScore.toFixed(1)}</span>,
  },
  {
    id: "asset",
    header: "机组 / 部件",
    accessorFn: (assessment) => `${assessment.turbineId} ${assessment.component}`,
    cell: ({ row }) => (
      <span>
        <strong>{row.original.turbineId}</strong>
        <small>{row.original.component}</small>
      </span>
    ),
  },
  {
    accessorKey: "componentHealth",
    header: "健康度",
    cell: ({ row }) => <HealthBadge score={row.original.componentHealth} />,
  },
  {
    accessorKey: "failureProbability30d",
    header: "30 天失效概率",
    cell: ({ row }) => (
      <span>
        <strong>{row.original.failureProbability30d}%</strong>
        <small>Band {row.original.probabilityBand}/5</small>
      </span>
    ),
  },
  {
    accessorKey: "remainingUsefulLifeDays",
    header: "Estimated RUL",
    cell: ({ row }) => (
      <span>
        <strong>{row.original.remainingUsefulLifeDays} d</strong>
        <small>±12 days</small>
      </span>
    ),
  },
  {
    accessorKey: "anomalyScore",
    header: "异常分数",
    cell: ({ row }) => (
      <span>
        <strong>{row.original.anomalyScore.toFixed(2)}</strong>
        <small>{trendLabels[row.original.trend]}</small>
      </span>
    ),
  },
  {
    accessorKey: "matrixRisk",
    header: "矩阵风险",
    cell: ({ row }) => (
      <StatusBadge
        value={row.original.matrixRisk}
        label={riskLabels[row.original.matrixRisk]}
        tone={riskTone(row.original.matrixRisk)}
        compact
      />
    ),
  },
];

const dateLabel = (date: Date, window: TimeWindow): string =>
  window === "24H"
    ? date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })
    : `${date.getMonth() + 1}/${date.getDate()}`;

function withWorkflowState(
  assessment: PredictiveAssessment,
  workflow: DemoWorkflowState,
): PredictiveAssessment {
  if (assessment.turbineId !== "WT-023" || workflow.workOrderStatus !== "completed") {
    return assessment;
  }

  const probabilityBand = probabilityBandFor(12);
  const riskScore = probabilityBand * assessment.consequenceBand;
  return {
    ...assessment,
    healthScore: workflow.turbineHealthScore,
    componentHealth: workflow.mainBearingHealthScore,
    state: "watch",
    trend: "improving",
    riskLevel: "medium",
    failureProbability30d: 12,
    remainingUsefulLifeDays: 126,
    anomalyScore: 0.42,
    primaryFinding: "现场复测后振动与温升回落，进入趋势观察",
    probabilityBand,
    riskScore,
    matrixRisk: matrixRiskFor(probabilityBand, assessment.consequenceBand),
    priorityScore: Number((12 * assessment.consequenceBand + 4.2).toFixed(2)),
  };
}

function workflowRecommendation(workflow: DemoWorkflowState): {
  readonly title: string;
  readonly detail: string;
} {
  if (workflow.missionStatus === "completed" || workflow.workOrderStatus === "completed") {
    return {
      title: "维护闭环已验证",
      detail: `${workflow.knowledgeCaseId ?? "WT-023 闭环案例"} 已沉淀，风险由 HIGH 降至 MEDIUM。`,
    };
  }

  if (workflow.workOrderStatus === "in-progress") {
    return {
      title: "现场工单执行中",
      detail: `WO-20260823-017 已完成 ${workflow.completedTaskIds.length}/5 项任务，等待复测与结果验证。`,
    };
  }

  if (workflow.workOrderStatus === "scheduled") {
    return {
      title: "方案 B 已批准并排程",
      detail: "人工审批已记录；WO-20260823-017 等待现场班组启动。",
    };
  }

  if (workflow.decisionStatus === "rejected" || workflow.missionStatus === "decision-pending") {
    return {
      title: "方案 B 已被拒绝",
      detail: "高风险执行门禁保持锁定；等待 Agent 生成新的处置方案。",
    };
  }

  if (workflow.decisionStatus === "revision-requested" || workflow.missionStatus === "diagnosed") {
    return {
      title: "方案 B 待修订",
      detail: "审批人已请求补充证据或调整方案；WO-20260823-017 保持草稿。",
    };
  }

  if (workflow.decisionStatus === "approved") {
    return {
      title: "方案 B 已获人工批准",
      detail: "审批记录已写入；WO-20260823-017 等待排程同步。",
    };
  }

  return {
    title: "方案 B 等待人工审批",
    detail: "高风险执行门禁仍锁定；WO-20260823-017 保持草稿，尚未排程。",
  };
}

function createTrendData(
  assessment: PredictiveAssessment,
  window: TimeWindow,
  completed: boolean,
): { health: TimeSeriesPoint[]; anomaly: TimeSeriesPoint[] } {
  const windowConfig = {
    "24H": { count: 25, intervalHours: 1 },
    "7D": { count: 28, intervalHours: 6 },
    "30D": { count: 30, intervalHours: 24 },
    "90D": { count: 30, intervalHours: 72 },
  }[window];
  const turbineNumber = Number(assessment.turbineId.slice(3));
  const end = Date.parse("2026-08-13T10:30:00+08:00");
  const scadaAnomaly = scadaSeries.find((series) => series.metric === "anomaly-score");
  const sourcePoints =
    assessment.turbineId === "WT-023" && window === "24H"
      ? scadaAnomaly?.points.slice(-windowConfig.count)
      : undefined;

  const anomaly = Array.from({ length: windowConfig.count }, (_, index): TimeSeriesPoint => {
    const timestamp = new Date(
      end - (windowConfig.count - 1 - index) * windowConfig.intervalHours * 60 * 60 * 1000,
    );
    const progress = index / Math.max(1, windowConfig.count - 1);
    const source = sourcePoints?.[index];
    const baseline = Math.max(0.08, assessment.anomalyScore - 0.2);
    const simulated =
      baseline +
      (assessment.anomalyScore - baseline) * progress +
      Math.sin((index + turbineNumber) * 0.74) * 0.025;
    const preMaintenance = 0.72 + 0.14 * progress + Math.sin(index * 0.74) * 0.018;
    const value = completed
      ? preMaintenance - Math.max(0, (progress - 0.72) / 0.28) * 0.44
      : (source?.value ?? simulated);

    return {
      timestamp: dateLabel(timestamp, window),
      value: Number(Math.max(0.04, value).toFixed(2)),
      anomaly: value >= 0.65,
      aiEvent: Boolean(source?.aiEvent) || index === Math.floor(windowConfig.count * 0.72),
    };
  });

  const health = anomaly.map((point, index): TimeSeriesPoint => {
    const progress = index / Math.max(1, anomaly.length - 1);
    const historicalOffset =
      assessment.trend === "declining" ? 9 : assessment.trend === "improving" ? -5 : 2;
    const recovery = completed ? Math.max(0, (progress - 0.72) / 0.28) * 15 : 0;
    const value =
      assessment.componentHealth +
      historicalOffset * (1 - progress) +
      recovery -
      (completed ? 15 : 0) +
      Math.sin((index + turbineNumber) * 0.52) * 0.7;
    return {
      timestamp: point.timestamp,
      value: Number(Math.max(35, Math.min(99, value)).toFixed(1)),
      anomaly: value < 75,
      aiEvent: point.aiEvent,
    };
  });

  return { health, anomaly };
}

function matrixCellRisk(probability: number, consequence: number): RiskLevel {
  return matrixRiskFor(probability, consequence);
}

export function PredictiveMaintenancePage() {
  const workflow = useDemoWorkflow();
  const [selectedId, setSelectedId] = useState("WT-023");
  const [timeWindow, setTimeWindow] = useState<TimeWindow>("30D");
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const [trendFilter, setTrendFilter] = useState<TrendFilter>("all");

  useEffect(() => {
    const turbineId = new URLSearchParams(window.location.search).get("turbineId")?.toUpperCase();
    if (!turbineId || !predictiveAssessments.some((item) => item.turbineId === turbineId)) return;
    const timer = window.setTimeout(() => setSelectedId(turbineId), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const endpoint = useMemo(() => {
    const params = new URLSearchParams({ limit: "64", sort: "risk-desc" });
    if (riskFilter !== "all") params.set("risk", riskFilter);
    if (trendFilter !== "all") params.set("trend", trendFilter);
    return `/api/predictive-assessments?${params.toString()}`;
  }, [riskFilter, trendFilter]);

  const assessmentsQuery = useQuery({
    queryKey: ["predictive-assessments", endpoint],
    queryFn: ({ signal }) => apiGet<PredictiveResponse>(endpoint, signal),
    initialData: {
      data: [...predictiveAssessments],
      meta: {
        count: predictiveAssessments.length,
        total: predictiveAssessments.length,
        filteredTotal: predictiveAssessments.length,
        model: predictiveModelMeta,
      },
    },
    initialDataUpdatedAt: 0,
    staleTime: 0,
  });

  const fleet = useMemo(
    () =>
      predictiveAssessments
        .map((assessment) => withWorkflowState(assessment, workflow))
        .sort(byPriority),
    [workflow],
  );
  const visible = useMemo(() => {
    return assessmentsQuery.data.data
      .map((assessment) => withWorkflowState(assessment, workflow))
      .filter(
        (assessment) =>
          (riskFilter === "all" || assessment.matrixRisk === riskFilter) &&
          (trendFilter === "all" || assessment.trend === trendFilter),
      )
      .sort(byPriority);
  }, [assessmentsQuery.data.data, riskFilter, trendFilter, workflow]);
  const selected = fleet.find((assessment) => assessment.turbineId === selectedId) ?? fleet[0]!;
  const closedLoop = selected.turbineId === "WT-023" && workflow.workOrderStatus === "completed";
  const recommendation =
    selected.turbineId === "WT-023"
      ? workflowRecommendation(workflow)
      : {
          title: "按风险优先级安排维护",
          detail: `${selected.component} 当前为 ${riskLabels[selected.matrixRisk]}风险，建议结合 RUL 与资源窗口持续评估。`,
        };
  const trendData = useMemo(
    () => createTrendData(selected, timeWindow, closedLoop),
    [closedLoop, selected, timeWindow],
  );
  const matrix = useMemo(
    () =>
      Array.from({ length: 5 }, (_, consequenceIndex) => {
        const consequence = 5 - consequenceIndex;
        return Array.from({ length: 5 }, (_, probabilityIndex) => {
          const probability = probabilityIndex + 1;
          return {
            consequence,
            probability,
            risk: matrixCellRisk(probability, consequence),
            records: fleet.filter(
              (assessment) =>
                assessment.probabilityBand === probability &&
                assessment.consequenceBand === consequence,
            ),
          };
        });
      }),
    [fleet],
  );

  const fleetHighRisk = fleet.filter((assessment) =>
    ["critical", "high"].includes(assessment.matrixRisk),
  ).length;
  const fleetRul = Math.min(...fleet.map((assessment) => assessment.remainingUsefulLifeDays));

  return (
    <AppShell activePath="/predictive-maintenance">
      <PageHeader
        eyebrow="智能运维"
        title="预测性维护"
        description="用失效概率、剩余寿命与风险后果对 64 台机组进行可解释的维护排序"
        breadcrumb={["智能运维", "预测性维护"]}
        meta={
          <>
            <StatusBadge value="info" label="FIXTURE MODEL" />
            <span className="page-meta-text">评估快照 2026-08-13 10:30 CST</span>
          </>
        }
        actions={
          <Link className="button button--secondary button--md" href="/health">
            <Activity size={15} /> 设备健康
          </Link>
        }
      />

      <section className={styles.modelNotice} aria-label="模型说明">
        <div className={styles.modelIcon}>
          <Sparkles size={18} aria-hidden="true" />
        </div>
        <div>
          <strong>{predictiveModelMeta.label}</strong>
          <p>{predictiveModelMeta.notice}</p>
        </div>
        <span>
          <Database size={13} /> 131,072 SCADA fixture points
        </span>
        <span>
          <BadgeCheck size={13} /> Deterministic · Read only
        </span>
      </section>

      <section className={styles.controlBar} aria-label="预测性维护筛选器">
        <label className={styles.assetSelect}>
          <span>分析对象</span>
          <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
            {fleet.map((assessment) => (
              <option key={assessment.turbineId} value={assessment.turbineId}>
                {assessment.turbineId} · {assessment.component}
              </option>
            ))}
          </select>
        </label>
        <div className={styles.windowControl} role="group" aria-label="健康趋势时间窗口">
          <span>趋势窗口</span>
          <div>
            {windows.map((item) => (
              <button
                key={item}
                type="button"
                aria-pressed={timeWindow === item}
                onClick={() => setTimeWindow(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.snapshotState}>
          <span className={styles.liveDot} />
          <div>
            <small>ASSESSMENT STATE</small>
            <strong>{closedLoop ? "POST-MAINTENANCE" : "MONITORING"}</strong>
          </div>
        </div>
      </section>

      <section className={styles.heroGrid} aria-label={`${selected.turbineId} 预测摘要`}>
        <article className={styles.assetHero}>
          <div className={styles.assetHeroTop}>
            <div>
              <span className={styles.eyebrow}>SELECTED COMPONENT</span>
              <h2>{selected.turbineId}</h2>
              <p>
                {selected.component} · {selected.primaryFinding}
              </p>
            </div>
            <StatusBadge
              value={selected.matrixRisk}
              label={`${riskLabels[selected.matrixRisk]}风险`}
              tone={riskTone(selected.matrixRisk)}
            />
          </div>
          <div className={styles.assetHealth}>
            <div
              className={styles.healthRing}
              style={{ "--score": `${selected.componentHealth * 3.6}deg` } as CSSProperties}
            >
              <span>{selected.componentHealth}</span>
              <small>/ 100</small>
            </div>
            <div>
              <span>COMPONENT HEALTH</span>
              <strong>{trendLabels[selected.trend]}</strong>
              <small>
                {closedLoop ? "现场复测已回写" : `最近评估 ${selected.assessedAt.slice(11, 16)}`}
              </small>
            </div>
          </div>
          <div className={styles.storyStatus} data-complete={closedLoop || undefined}>
            {closedLoop ? <ShieldCheck size={17} /> : <AlertTriangle size={17} />}
            <div>
              <strong>{recommendation.title}</strong>
              <p>{recommendation.detail}</p>
            </div>
          </div>
        </article>

        <div className={styles.metricGrid}>
          <article className={styles.metricCard}>
            <div className={styles.metricIconCritical}>
              <TrendingUp size={16} />
            </div>
            <span>FAILURE PROBABILITY</span>
            <strong>
              {selected.failureProbability30d}
              <small>%</small>
            </strong>
            <p>未来 30 天 · Band {selected.probabilityBand}/5</p>
          </article>
          <article className={styles.metricCard}>
            <div className={styles.metricIconInfo}>
              <Clock3 size={16} />
            </div>
            <span>ESTIMATED RUL</span>
            <strong>
              {selected.remainingUsefulLifeDays}
              <small> days</small>
            </strong>
            <p>确定性点估计 · 区间 ±12 天</p>
          </article>
          <article className={styles.metricCard}>
            <div className={styles.metricIconWarning}>
              <CircleGauge size={16} />
            </div>
            <span>ANOMALY SCORE</span>
            <strong>{selected.anomalyScore.toFixed(2)}</strong>
            <p>预警阈值 0.65</p>
          </article>
          <article className={styles.metricCard}>
            <div className={styles.metricIconSuccess}>
              <Wrench size={16} />
            </div>
            <span>FLEET PRIORITY</span>
            <strong>#{fleet.findIndex((item) => item.turbineId === selected.turbineId) + 1}</strong>
            <p>
              {fleetHighRisk} 台高风险 · 最短 RUL {fleetRul}d
            </p>
          </article>
        </div>
      </section>

      <section className={styles.chartGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <span>HEALTH TREND</span>
              <h3>{selected.component} 健康趋势</h3>
              <p>{timeWindow} 窗口 · 低于 75 进入退化区</p>
            </div>
            <span className={styles.trendPill} data-trend={selected.trend}>
              {selected.trend === "improving" ? (
                <TrendingUp size={13} />
              ) : (
                <TrendingDown size={13} />
              )}
              {trendLabels[selected.trend]}
            </span>
          </div>
          <TimeSeriesChart
            data={trendData.health}
            height={250}
            unit="pts"
            threshold={75}
            primaryName="Health score"
          />
        </article>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <span>ANOMALY TRAJECTORY</span>
              <h3>异常分数与 AI 事件</h3>
              <p>WT-023 的 24H 视图复用 SCADA anomaly-score 测点</p>
            </div>
            <StatusBadge value={selected.anomalyScore >= 0.65 ? "warning" : "normal"} />
          </div>
          <TimeSeriesChart
            data={trendData.anomaly}
            height={250}
            unit="score"
            threshold={0.65}
            primaryName="Anomaly score"
          />
        </article>
      </section>

      <section className={styles.analysisGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <span>PROBABILITY × CONSEQUENCE</span>
              <h3>全场部件风险矩阵</h3>
              <p>每个点代表一台机组的首要风险部件；点击点切换分析对象</p>
            </div>
            <div className={styles.matrixLegend}>
              <i data-risk="low" />低 <i data-risk="medium" />中 <i data-risk="high" />高{" "}
              <i data-risk="critical" />
              严重
            </div>
          </div>
          <div className={styles.matrixLayout}>
            <span className={styles.yAxis}>CONSEQUENCE →</span>
            <div className={styles.matrixGrid}>
              {matrix.flat().map((cell) => (
                <div
                  key={`${cell.consequence}-${cell.probability}`}
                  className={styles.matrixCell}
                  data-risk={cell.risk}
                  aria-label={`概率 ${cell.probability}，后果 ${cell.consequence}，${cell.records.length} 台机组`}
                >
                  <small>{cell.records.length || ""}</small>
                  <span className={styles.matrixCoordinate}>
                    P{cell.probability} · C{cell.consequence}
                  </span>
                  <div>
                    {cell.records.map((assessment) => (
                      <button
                        key={assessment.turbineId}
                        type="button"
                        className={
                          assessment.turbineId === selected.turbineId
                            ? styles.matrixDotSelected
                            : styles.matrixDot
                        }
                        onClick={() => setSelectedId(assessment.turbineId)}
                        title={`${assessment.turbineId} · ${assessment.component} · ${riskLabels[assessment.matrixRisk]}风险`}
                        aria-label={`选择 ${assessment.turbineId} ${assessment.component}`}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <span className={styles.xAxis}>FAILURE PROBABILITY →</span>
          </div>
        </article>

        <aside className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <span>RISK EXPLAINABILITY</span>
              <h3>{selected.turbineId} 评分依据</h3>
              <p>结构化指标，不展示隐藏推理过程</p>
            </div>
          </div>
          <div className={styles.explainScore}>
            <div>
              <small>概率等级</small>
              <strong>{selected.probabilityBand} / 5</strong>
            </div>
            <span>×</span>
            <div>
              <small>后果等级</small>
              <strong>{selected.consequenceBand} / 5</strong>
            </div>
            <span>=</span>
            <div>
              <small>矩阵分数</small>
              <strong>{selected.riskScore} / 25</strong>
            </div>
          </div>
          <ol className={styles.evidenceList}>
            <li>
              <span>01</span>
              <div>
                <strong>健康评估</strong>
                <p>
                  {selected.component} {selected.componentHealth}/100，趋势
                  {trendLabels[selected.trend]}
                </p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>异常证据</strong>
                <p>
                  Anomaly {selected.anomalyScore.toFixed(2)}；30 天失效概率{" "}
                  {selected.failureProbability30d}%
                </p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>运营后果</strong>
                <p>
                  {selected.activeAlarmCount} 条活跃告警；机组状态 {selected.turbineStatus}
                </p>
              </div>
            </li>
          </ol>
          <Link className={styles.assetLink} href={`/turbines/${selected.turbineId}`}>
            打开数字资产 <ChevronRight size={14} />
          </Link>
        </aside>
      </section>

      <section className={styles.rankingPanel}>
        <div className={styles.rankingHeader}>
          <div>
            <span>FLEET RISK RANKING</span>
            <h3>64 台机组维护优先级</h3>
            <p>默认按风险优先分排序；所有筛选均请求只读 API</p>
          </div>
          <div className={styles.syncState}>
            <RefreshCcw
              size={13}
              className={assessmentsQuery.isFetching ? styles.spinning : undefined}
            />
            {assessmentsQuery.isError
              ? "使用本地快照"
              : assessmentsQuery.isFetching
                ? "同步中"
                : "API 已同步"}
          </div>
        </div>
        <div className={styles.tableScroll}>
          <DataTable
            data={visible}
            columns={assessmentColumns}
            getRowId={(assessment) => assessment.turbineId}
            selectedRowId={selected.turbineId}
            onRowActivate={(assessment) => setSelectedId(assessment.turbineId)}
            initialSorting={[{ id: "priorityScore", desc: true }]}
            pageSize={8}
            emptyMessage="没有匹配的预测评估"
            searchTextForRow={(assessment) =>
              `${assessment.turbineId} ${assessment.component} ${assessment.primaryFinding}`
            }
            searchPlaceholder="搜索机组、部件或发现…"
            filterControls={
              <>
                <label>
                  <Filter size={14} />
                  <select
                    aria-label="筛选风险"
                    value={riskFilter}
                    onChange={(event) => setRiskFilter(event.target.value as RiskFilter)}
                  >
                    <option value="all">全部风险</option>
                    <option value="critical">严重风险</option>
                    <option value="high">高风险</option>
                    <option value="medium">中风险</option>
                    <option value="low">低风险</option>
                  </select>
                </label>
                <label>
                  <Activity size={14} />
                  <select
                    aria-label="筛选趋势"
                    value={trendFilter}
                    onChange={(event) => setTrendFilter(event.target.value as TrendFilter)}
                  >
                    <option value="all">全部趋势</option>
                    <option value="declining">下降</option>
                    <option value="stable">稳定</option>
                    <option value="improving">改善</option>
                  </select>
                </label>
                <span>{visible.length} / 64 turbines</span>
              </>
            }
            bulkActions={[
              {
                label: "复制机组编号",
                onActivate: (assessments) =>
                  navigator.clipboard.writeText(
                    assessments.map((assessment) => assessment.turbineId).join("\n"),
                  ),
              },
            ]}
            csvExport={{
              filename: "windops-predictive-assessments.csv",
              columns: [
                { label: "机组", value: (assessment) => assessment.turbineId },
                { label: "部件", value: (assessment) => assessment.component },
                { label: "优先分", value: (assessment) => assessment.priorityScore },
                { label: "部件健康度", value: (assessment) => assessment.componentHealth },
                {
                  label: "30天失效概率",
                  value: (assessment) => assessment.failureProbability30d,
                },
                {
                  label: "剩余寿命天数",
                  value: (assessment) => assessment.remainingUsefulLifeDays,
                },
                { label: "异常分数", value: (assessment) => assessment.anomalyScore },
                { label: "矩阵风险", value: (assessment) => assessment.matrixRisk },
              ],
            }}
          />
        </div>
      </section>

      <footer className={styles.methodFooter}>
        <div>
          <CalendarClock size={15} />
          <span>
            <strong>固定评估时点</strong>2026-08-13 10:30 CST
          </span>
        </div>
        <div>
          <Database size={15} />
          <span>
            <strong>数据来源</strong>SCADA、告警、健康与维护 fixture
          </span>
        </div>
        <div>
          <ShieldCheck size={15} />
          <span>
            <strong>运行边界</strong>无真实推理、无自动控制、只读 API
          </span>
        </div>
      </footer>
    </AppShell>
  );
}
