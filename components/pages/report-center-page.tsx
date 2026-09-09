"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { apiGet } from "@/lib/api-client";
import type { ReportPeriod, ReportType, WindOpsReport } from "@/lib/report-data";

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
    workflowPersistence: "d1" | "ephemeral";
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
  { value: "all", label: "All reports", icon: FileChartColumn },
  { value: "daily-operations", label: "Daily Operations", icon: Activity },
  { value: "alarm-analysis", label: "Alarm Analysis", icon: AlertTriangle },
  { value: "ai-diagnosis", label: "AI Diagnosis", icon: Bot },
  { value: "maintenance", label: "Maintenance", icon: Wrench },
  { value: "asset-health", label: "Asset Health", icon: HeartPulse },
  { value: "weekly-wind-farm", label: "Weekly Wind Farm", icon: Building2 },
];

const metricIcons = [BarChart3, Activity, ShieldCheck, Sparkles] as const;

const formatDateTime = (value: string): string =>
  new Date(value).toLocaleString("en-GB", {
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
  const revision = `expectedRevision=${report.workflow.revision}`;
  return (
    <div className={compact ? styles.compactExportActions : styles.exportActions}>
      <a
        className="button button--secondary button--md"
        download={`${report.id.toLowerCase()}.pdf`}
        href={`${basePath}?format=pdf&${revision}`}
      >
        <Download size={14} aria-hidden="true" /> Export PDF
      </a>
      <a
        className="button button--primary button--md"
        download={`${report.id.toLowerCase()}.docx`}
        href={`${basePath}?format=docx&${revision}`}
      >
        <FileText size={14} aria-hidden="true" /> Export DOCX
      </a>
    </div>
  );
}

function ReportPreview({ report }: { report: WindOpsReport }) {
  return (
    <article className={styles.preview} aria-label={`${report.title} preview`}>
      <header className={styles.previewHeader}>
        <div className={styles.documentMark} aria-hidden="true">
          <FileChartColumn size={22} />
        </div>
        <div>
          <span>{report.typeLabel.toUpperCase()}</span>
          <h2>{report.title}</h2>
          <p>{report.subtitle}</p>
        </div>
        <StatusBadge value="ready" label="READY" tone="success" compact />
      </header>

      <dl className={styles.documentMeta}>
        <div>
          <dt>REPORT ID</dt>
          <dd>{report.id}</dd>
        </div>
        <div>
          <dt>PERIOD</dt>
          <dd>{report.periodLabel}</dd>
        </div>
        <div>
          <dt>OWNER</dt>
          <dd>{report.ownerAgent}</dd>
        </div>
        <div>
          <dt>GENERATED</dt>
          <dd>{formatDateTime(report.generatedAt)}</dd>
        </div>
      </dl>

      <section className={styles.highlight}>
        <span>
          <Sparkles size={15} aria-hidden="true" /> EXECUTIVE HIGHLIGHT
        </span>
        <p>{report.highlight}</p>
      </section>

      <section className={styles.metricGrid} aria-label="Report metrics">
        {report.metrics.map((metric, index) => {
          const Icon = metricIcons[index % metricIcons.length]!;
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
            <ShieldCheck size={15} aria-hidden="true" /> WT-023 WORKFLOW TRACE
          </span>
          <code>REV {report.workflow.revision}</code>
        </div>
        <div className={styles.workflowSteps}>
          <div>
            <small>MISSION</small>
            <strong>{report.workflow.missionStatus}</strong>
          </div>
          <span aria-hidden="true" />
          <div>
            <small>DECISION</small>
            <strong>{report.workflow.decisionStatus}</strong>
          </div>
          <span aria-hidden="true" />
          <div>
            <small>WORK ORDER</small>
            <strong>{report.workflow.workOrderStatus}</strong>
          </div>
          <span aria-hidden="true" />
          <div>
            <small>FIELD TASKS</small>
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
            Deterministic fixtures + authoritative server workflow overlay
            <small>Export is rejected if this preview revision has changed.</small>
          </span>
        </div>
        <ExportActions report={report} compact />
      </footer>
    </article>
  );
}

export function ReportCenterPage() {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<TypeFilter>("all");
  const [period, setPeriod] = useState<PeriodFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const reportsPath = useMemo(() => buildReportsPath(query, type, period), [period, query, type]);
  const reportsQuery = useQuery({
    queryKey: ["report-center", reportsPath],
    queryFn: ({ signal }) => apiGet<ReportsEnvelope>(reportsPath, signal),
  });
  const reports = reportsQuery.data?.data.reports ?? [];

  const selectedReport = reports.find((report) => report.id === selectedId) ?? reports[0] ?? null;

  return (
    <AppShell activePath="/reports">
      <PageHeader
        eyebrow="KNOWLEDGE & REPORTING"
        title="Report Center"
        description="Preview and export traceable operational reports generated from fleet fixtures and the live WT-023 workflow"
        breadcrumb={["Knowledge & reporting", "Report Center"]}
        meta={
          <>
            <StatusBadge
              value={reportsQuery.isError ? "degraded" : "healthy"}
              label={reportsQuery.isError ? "REPORT API DEGRADED" : "EXPORT ENGINE READY"}
            />
            <span className="page-meta-text">
              {reportsQuery.data
                ? `REV ${reportsQuery.data.meta.workflowRevision} / ${reportsQuery.data.meta.workflowPersistence.toUpperCase()}`
                : "LOADING REPORT LEDGER"}
            </span>
          </>
        }
        actions={selectedReport ? <ExportActions report={selectedReport} /> : undefined}
      />

      <section className={styles.summaryStrip} aria-label="Report Center summary">
        <div>
          <FileChartColumn size={18} aria-hidden="true" />
          <span>
            <small>REPORT TYPES</small>
            <strong>6 governed templates</strong>
          </span>
        </div>
        <div>
          <CalendarDays size={18} aria-hidden="true" />
          <span>
            <small>PERIOD COVERAGE</small>
            <strong>Daily · incident · weekly</strong>
          </span>
        </div>
        <div>
          <ShieldCheck size={18} aria-hidden="true" />
          <span>
            <small>EXPORT INTEGRITY</small>
            <strong>PDF 1.4 · DOCX OOXML</strong>
          </span>
        </div>
      </section>

      <section className={styles.toolbar} aria-label="Report filters">
        <label className={styles.searchField}>
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">Search reports</span>
          <input
            aria-label="Search reports"
            maxLength={120}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search report title, asset, tag, or entity ID"
            type="search"
            value={query}
          />
        </label>
        <label className={styles.selectField}>
          <span>TYPE</span>
          <select
            aria-label="Filter by report type"
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
          <span>PERIOD</span>
          <select
            aria-label="Filter by report period"
            onChange={(event) => setPeriod(event.target.value as PeriodFilter)}
            value={period}
          >
            <option value="all">All periods</option>
            <option value="daily">Daily</option>
            <option value="incident">Incident</option>
            <option value="snapshot">Snapshot</option>
            <option value="weekly">Weekly</option>
          </select>
        </label>
        <Button
          aria-label="Refresh reports"
          disabled={reportsQuery.isFetching}
          onClick={() => void reportsQuery.refetch()}
          variant="secondary"
        >
          <RefreshCcw className={reportsQuery.isFetching ? "spin" : undefined} size={14} />
          Refresh
        </Button>
      </section>

      <div className={styles.workspace}>
        <aside className={styles.catalog} aria-label="Report catalog">
          <header>
            <div>
              <span>REPORT CATALOG</span>
              <strong>
                {reportsQuery.data?.meta.total ?? 0} / {reportsQuery.data?.meta.catalogTotal ?? 6}
              </strong>
            </div>
            <small>Select a report to inspect its evidence-backed preview.</small>
          </header>

          {reportsQuery.isPending ? (
            <div className={styles.loadingList} aria-label="Loading reports">
              {Array.from({ length: 5 }, (_, index) => (
                <span key={index} />
              ))}
            </div>
          ) : reportsQuery.isError ? (
            <EmptyState
              icon={<AlertTriangle size={20} />}
              title="Report catalog unavailable"
              description="Refresh the report ledger to retry the API request."
            />
          ) : reports.length === 0 ? (
            <EmptyState
              icon={<Search size={20} />}
              title="No matching reports"
              description="Clear the search or broaden the type and period filters."
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
                    <span className={styles.readyDot} title="Ready" />
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        <main className={styles.previewPanel}>
          {selectedReport ? (
            <ReportPreview report={selectedReport} />
          ) : (
            <EmptyState
              icon={<FileChartColumn size={20} />}
              title="Select a report"
              description="Choose a report from the catalog to open its full preview."
            />
          )}
        </main>
      </div>
    </AppShell>
  );
}
