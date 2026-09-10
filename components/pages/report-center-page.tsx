"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  Building2,
  CalendarDays,
  CheckCircle2,
  Download,
  FileChartColumn,
  FileText,
  HeartPulse,
  RefreshCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, EmptyState } from "@/components/ui/primitives";
import { apiGet, apiPostCommand } from "@/lib/api-client";
import type { ReportPeriod, ReportType, WindOpsReport } from "@/lib/report-data";
import { localizedStatusLabel } from "@/lib/ui-localization";
import type { WindOpsRuntimeMode } from "@/lib/production-runtime";

import styles from "./report-center-page.module.css";

type ReportsEnvelope = {
  ok: true;
  data: {
    reports: WindOpsReport[];
    facets: {
      reportTypes: Record<ReportType, number>;
      periods: Record<ReportPeriod, number>;
    };
  };
  error: null;
  meta: {
    count: number;
    total: number;
    catalogTotal: number;
    snapshotAt: string;
    workflowPersistence: "d1" | "ephemeral" | "postgresql";
    workflowRevision: number;
  };
};

type TypeFilter = "all" | ReportType;
type PeriodFilter = "all" | ReportPeriod;

const typeOptions: readonly {
  readonly value: TypeFilter;
  readonly label: string;
  readonly icon: typeof Activity;
}[] = [
  { value: "all", label: "全部报告", icon: FileChartColumn },
  { value: "daily-operations", label: "运营日报", icon: Activity },
  { value: "alarm-analysis", label: "告警分析", icon: AlertTriangle },
  { value: "ai-diagnosis", label: "AI 诊断", icon: Bot },
  { value: "maintenance", label: "维护报告", icon: Wrench },
  { value: "asset-health", label: "资产健康", icon: HeartPulse },
  { value: "weekly-wind-farm", label: "风场周报", icon: Building2 },
];

const metricIcons = [BarChart3, Activity, ShieldCheck, Sparkles] as const;

const formatDateTime = (value: string): string =>
  new Date(value).toLocaleString("zh-CN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  });

const buildReportsPath = (query: string, type: TypeFilter, period: PeriodFilter): string => {
  const params = new URLSearchParams({ sort: "generatedAt", order: "desc", pageSize: "12" });
  if (query.trim()) params.set("q", query.trim());
  if (type !== "all") params.set("type", type);
  if (period !== "all") params.set("period", period);
  return `/api/reports?${params.toString()}`;
};

function ExportActions({ report, compact = false }: { report: WindOpsReport; compact?: boolean }) {
  const basePath = `/api/reports/${encodeURIComponent(report.id)}/export`;
  const versionCheck = report.contentDigest
    ? `expectedDigest=${encodeURIComponent(report.contentDigest)}`
    : `expectedRevision=${report.workflow.revision}`;
  return (
    <div className={compact ? styles.compactExportActions : styles.exportActions}>
      <a
        className="button button--secondary button--md"
        download={`${report.id.toLowerCase()}.pdf`}
        href={`${basePath}?format=pdf&${versionCheck}`}
      >
        <Download size={14} aria-hidden="true" /> 导出 PDF
      </a>
      <a
        className="button button--primary button--md"
        download={`${report.id.toLowerCase()}.docx`}
        href={`${basePath}?format=docx&${versionCheck}`}
      >
        <FileText size={14} aria-hidden="true" /> 导出 DOCX
      </a>
    </div>
  );
}

function ReportPreview({ report, production }: { report: WindOpsReport; production: boolean }) {
  return (
    <article className={styles.preview} aria-label={`${report.title}预览`}>
      <header className={styles.previewHeader}>
        <div className={styles.documentMark} aria-hidden="true">
          <FileChartColumn size={22} />
        </div>
        <div>
          <span>{report.typeLabel.toUpperCase()}</span>
          <h2>{report.title}</h2>
          <p>{report.subtitle}</p>
        </div>
        <StatusBadge value="ready" label="就绪" tone="success" compact />
      </header>

      <dl className={styles.documentMeta}>
        <div>
          <dt>报告编号</dt>
          <dd>{report.id}</dd>
        </div>
        <div>
          <dt>报告周期</dt>
          <dd>{report.periodLabel}</dd>
        </div>
        <div>
          <dt>负责人</dt>
          <dd>{report.ownerAgent}</dd>
        </div>
        <div>
          <dt>生成时间</dt>
          <dd>{formatDateTime(report.generatedAt)}</dd>
        </div>
      </dl>

      <section className={styles.highlight}>
        <span>
          <Sparkles size={15} aria-hidden="true" /> 执行摘要
        </span>
        <p>{report.highlight}</p>
      </section>

      <section className={styles.metricGrid} aria-label="报告指标">
        {report.metrics.map((metric, index) => {
          const Icon = metricIcons[index % metricIcons.length];
          return (
            <div className={styles.metric} data-tone={metric.tone} key={metric.label}>
              <span>
                <Icon size={14} aria-hidden="true" /> {metric.label}
              </span>
              <strong>{metric.value}</strong>
              <small>{metric.context}</small>
            </div>
          );
        })}
      </section>

      <div className={styles.reportBody}>
        {report.sections.map((section, sectionIndex) => (
          <section key={section.heading}>
            <div className={styles.sectionNumber}>{String(sectionIndex + 1).padStart(2, "0")}</div>
            <div>
              <h3>{section.heading}</h3>
              <p>{section.summary}</p>
              <ul>
                {section.findings.map((finding) => (
                  <li key={finding}>{finding}</li>
                ))}
              </ul>
            </div>
          </section>
        ))}
      </div>

      <section className={styles.workflowTrace}>
        <div className={styles.workflowHeader}>
          <span>
            <ShieldCheck size={15} aria-hidden="true" /> WT-023 工作流追踪
          </span>
          <code>修订 {report.workflow.revision}</code>
        </div>
        <div className={styles.workflowSteps}>
          <div>
            <small>MISSION</small>
            <strong>{localizedStatusLabel(report.workflow.missionStatus)}</strong>
          </div>
          <span aria-hidden="true" />
          <div>
            <small>决策</small>
            <strong>{localizedStatusLabel(report.workflow.decisionStatus)}</strong>
          </div>
          <span aria-hidden="true" />
          <div>
            <small>工单</small>
            <strong>{localizedStatusLabel(report.workflow.workOrderStatus)}</strong>
          </div>
          <span aria-hidden="true" />
          <div>
            <small>现场任务</small>
            <strong>
              {report.workflow.completedTaskCount}/{report.workflow.totalTaskCount}
            </strong>
          </div>
        </div>
        <div className={styles.entityLinks}>
          {report.linkedEntityIds.map((entityId) => (
            <code key={entityId}>{entityId}</code>
          ))}
        </div>
      </section>

      <footer className={styles.previewFooter}>
        <div>
          <CheckCircle2 size={15} aria-hidden="true" />
          <span>
            {production ? "PostgreSQL 不可变报告快照" : "确定性演示数据 + 权威服务器工作流叠加"}
            <small>
              {report.contentDigest
                ? `SHA-256 ${report.contentDigest.slice(0, 16)}…；摘要不匹配时拒绝导出。`
                : "若预览版本已变化，系统将拒绝导出。"}
            </small>
          </span>
        </div>
        <ExportActions report={report} compact />
      </footer>
    </article>
  );
}

export function ReportCenterPage({ runtimeMode }: { runtimeMode: WindOpsRuntimeMode }) {
  const isProduction = runtimeMode === "production";
  const [query, setQuery] = useState("");
  const [type, setType] = useState<TypeFilter>("all");
  const [period, setPeriod] = useState<PeriodFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [generationType, setGenerationType] = useState<ReportType>("daily-operations");
  const [generationPeriod, setGenerationPeriod] = useState<ReportPeriod>("daily");
  const [generationReason, setGenerationReason] = useState("");
  const queryClient = useQueryClient();
  const reportsPath = useMemo(() => buildReportsPath(query, type, period), [period, query, type]);
  const reportsQuery = useQuery({
    queryKey: ["report-center", reportsPath],
    queryFn: ({ signal }) => apiGet<ReportsEnvelope>(reportsPath, signal),
  });
  const reports = reportsQuery.data?.data.reports ?? [];
  const generationMutation = useMutation({
    mutationFn: () =>
      apiPostCommand<{ data: WindOpsReport; meta: { replayed: boolean } }>(
        "/api/backend/reports",
        {
          report_type: generationType,
          period: generationPeriod,
          reason: generationReason.trim(),
        },
        crypto.randomUUID(),
      ),
    onSuccess: async (payload) => {
      setSelectedId(payload.data.id);
      setGenerationReason("");
      await queryClient.invalidateQueries({ queryKey: ["report-center"] });
    },
  });

  const selectedReport = reports.find((report) => report.id === selectedId) ?? reports[0] ?? null;

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/reports">
      <PageHeader
        eyebrow="知识与报告"
        title="报告中心"
        description={
          isProduction
            ? "预览并导出由 PostgreSQL 权威运营台账即时生成的可追溯报告"
            : "预览并导出由全场演示数据和 WT-023 实时工作流生成的可追溯运营报告"
        }
        breadcrumb={["知识与报告", "报告中心"]}
        meta={
          <>
            <StatusBadge
              value={reportsQuery.isError ? "degraded" : "healthy"}
              label={reportsQuery.isError ? "报告 API 降级" : "导出引擎就绪"}
            />
            <span className="page-meta-text">
              {reportsQuery.data
                ? `REV ${reportsQuery.data.meta.workflowRevision} / ${reportsQuery.data.meta.workflowPersistence.toUpperCase()}`
                : "正在加载报告账本"}
            </span>
          </>
        }
        actions={selectedReport ? <ExportActions report={selectedReport} /> : undefined}
      />

      <section className={styles.summaryStrip} aria-label="报告中心摘要">
        <div>
          <FileChartColumn size={18} aria-hidden="true" />
          <span>
            <small>报告类型</small>
            <strong>
              {isProduction
                ? `${reportsQuery.data?.meta.catalogTotal ?? 0} 个持久化快照`
                : "6 个受控模板"}
            </strong>
          </span>
        </div>
        <div>
          <CalendarDays size={18} aria-hidden="true" />
          <span>
            <small>周期覆盖</small>
            <strong>日报 · 事件报告 · 周报</strong>
          </span>
        </div>
        <div>
          <ShieldCheck size={18} aria-hidden="true" />
          <span>
            <small>导出完整性</small>
            <strong>PDF 1.4 · DOCX OOXML</strong>
          </span>
        </div>
      </section>

      {isProduction ? (
        <form
          className={styles.generationPanel}
          onSubmit={(event) => {
            event.preventDefault();
            generationMutation.mutate();
          }}
        >
          <div>
            <strong>生成不可变报告快照</strong>
            <small>从当前权威台账创建持久化、可审计、可摘要校验的版本。</small>
          </div>
          <label className={styles.selectField}>
            <span>报告类型</span>
            <select
              value={generationType}
              onChange={(event) => setGenerationType(event.target.value as ReportType)}
            >
              {typeOptions.slice(1).map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.selectField}>
            <span>报告周期</span>
            <select
              value={generationPeriod}
              onChange={(event) => setGenerationPeriod(event.target.value as ReportPeriod)}
            >
              <option value="daily">日报</option>
              <option value="weekly">周报</option>
              <option value="incident">事件窗口</option>
              <option value="snapshot">即时快照</option>
            </select>
          </label>
          <label className={styles.reasonField}>
            <span>生成原因</span>
            <input
              required
              minLength={3}
              maxLength={500}
              value={generationReason}
              onChange={(event) => setGenerationReason(event.target.value)}
              placeholder="例如：每日运行交接"
            />
          </label>
          <Button
            type="submit"
            loading={generationMutation.isPending}
            disabled={generationReason.trim().length < 3}
          >
            生成并固化
          </Button>
          {generationMutation.isError ? (
            <span className={styles.generationError} role="alert">
              {generationMutation.error.message}
            </span>
          ) : null}
        </form>
      ) : null}

      <section className={styles.toolbar} aria-label="报告筛选">
        <label className={styles.searchField}>
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">搜索报告</span>
          <input
            aria-label="搜索报告"
            maxLength={120}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索报告标题、资产、标签或实体编号"
            type="search"
            value={query}
          />
        </label>
        <label className={styles.selectField}>
          <span>类型</span>
          <select
            aria-label="按报告类型筛选"
            onChange={(event) => setType(event.target.value as TypeFilter)}
            value={type}
          >
            {typeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.selectField}>
          <span>周期</span>
          <select
            aria-label="按报告周期筛选"
            onChange={(event) => setPeriod(event.target.value as PeriodFilter)}
            value={period}
          >
            <option value="all">全部周期</option>
            <option value="daily">日报</option>
            <option value="incident">事件</option>
            <option value="snapshot">快照</option>
            <option value="weekly">周报</option>
          </select>
        </label>
        <Button
          aria-label="刷新报告"
          disabled={reportsQuery.isFetching}
          onClick={() => void reportsQuery.refetch()}
          variant="secondary"
        >
          <RefreshCcw className={reportsQuery.isFetching ? "spin" : undefined} size={14} />
          刷新
        </Button>
      </section>

      <div className={styles.workspace}>
        <aside className={styles.catalog} aria-label="报告目录">
          <header>
            <div>
              <span>报告目录</span>
              <strong>
                {reportsQuery.data?.meta.total ?? 0} /{" "}
                {reportsQuery.data?.meta.catalogTotal ?? (isProduction ? 0 : 6)}
              </strong>
            </div>
            <small>选择一份报告，查看基于证据生成的预览。</small>
          </header>

          {reportsQuery.isPending ? (
            <div className={styles.loadingList} aria-label="正在加载报告">
              {Array.from({ length: 5 }, (_, index) => (
                <span key={index} />
              ))}
            </div>
          ) : reportsQuery.isError ? (
            <EmptyState
              icon={<AlertTriangle size={20} />}
              title="报告目录不可用"
              description="刷新报告账本并重试 API 请求。"
            />
          ) : reports.length === 0 ? (
            <EmptyState
              icon={<Search size={20} />}
              title="没有匹配的报告"
              description="请清除搜索条件，或放宽类型与周期筛选。"
            />
          ) : (
            <div className={styles.reportList}>
              {reports.map((report) => {
                const option = typeOptions.find((item) => item.value === report.type)!;
                const Icon = option.icon;
                const active = report.id === selectedReport?.id;
                return (
                  <button
                    aria-pressed={active}
                    className={styles.reportCard}
                    data-active={active}
                    key={report.id}
                    onClick={() => setSelectedId(report.id)}
                    type="button"
                  >
                    <span className={styles.reportIcon}>
                      <Icon size={17} aria-hidden="true" />
                    </span>
                    <span className={styles.reportCardCopy}>
                      <small>{report.typeLabel}</small>
                      <strong>{report.title}</strong>
                      <em>{report.periodLabel}</em>
                    </span>
                    <span className={styles.readyDot} title="就绪" />
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        <main className={styles.previewPanel}>
          {selectedReport ? (
            <ReportPreview report={selectedReport} production={isProduction} />
          ) : (
            <EmptyState
              icon={<FileChartColumn size={20} />}
              title="请选择报告"
              description="从目录中选择报告以打开完整预览。"
            />
          )}
        </main>
      </div>
    </AppShell>
  );
}
