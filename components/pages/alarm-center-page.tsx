"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  TriangleAlert as AlarmTriangle,
  ArrowRight,
  BookOpenText,
  Bot,
  Check,
  ChevronDown,
  Clock3,
  FileSearch,
  Filter,
  History,
  ShieldAlert,
  Thermometer,
  UserRound,
  Wrench,
  X,
} from "lucide-react";
import Link from "next/link";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import { DataTable } from "@/components/data-display/data-table";
import { AppShell } from "@/components/layout/app-shell";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { PageHeader } from "@/components/layout/page-header";
import { Button, KeyValue } from "@/components/ui/primitives";
import { StatusBadge, type StatusTone } from "@/components/data-display/status-badge";
import {
  alarms,
  evidenceItems,
  failureCases,
  featuredMission,
  historicalWorkOrders,
  knowledgeDocuments,
  windFarm,
} from "@/lib";
import type { Alarm, AlarmSeverity } from "@/lib/types";
import { apiGet, apiPost } from "@/lib/api-client";
import { useRealtimeChannel } from "@/lib/use-realtime-channel";
import { useProductionEvents } from "@/lib/use-production-events";
import { asText, cn } from "@/lib/utils";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { overlayClientAlarms } from "@/lib/client-workflow-overlays";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";
import { localizedStatusLabel, localizedSubsystemLabel } from "@/lib/ui-localization";

const severityTone: Record<AlarmSeverity, StatusTone> = {
  critical: "critical",
  major: "warning",
  minor: "maintenance",
  warning: "warning",
  info: "info",
};
const productionAlarmEventTypes = [
  "alarm.opened",
  "alarm.acknowledged",
  "alarm.assigned",
  "alarm.unassigned",
  "alarm.resolved",
  "mission.created",
  "mission.review_ready",
  "mission.approval.approve",
  "mission.approval.reject",
  "mission.approval.request_revision",
  "mission.approval.escalate",
  "work_order.created",
  "work_order.completed",
] as const;
const severityLabel: Record<AlarmSeverity, string> = {
  critical: "严重",
  major: "重要",
  minor: "次要",
  warning: "警告",
  info: "信息",
};

const alarmColumns: readonly LegacyColumnDef<Alarm, unknown>[] = [
  {
    accessorKey: "severity",
    header: "严重度",
    cell: ({ row }) => (
      <StatusBadge
        value={row.original.severity}
        label={severityLabel[row.original.severity]}
        tone={severityTone[row.original.severity]}
        compact
      />
    ),
  },
  {
    accessorKey: "turbineId",
    header: "风机",
    cell: ({ row }) => <strong className="mono">{row.original.turbineId}</strong>,
  },
  {
    accessorKey: "subsystem",
    header: "子系统",
    cell: ({ row }) => localizedSubsystemLabel(row.original.subsystem),
  },
  {
    accessorKey: "code",
    header: "告警代码",
    cell: ({ row }) => <span className="mono">{row.original.code}</span>,
  },
  {
    accessorKey: "title",
    header: "告警",
    cell: ({ row }) => (
      <span className="alarm-title-cell">
        <strong>{row.original.title}</strong>
        <small>{row.original.description}</small>
      </span>
    ),
    size: 300,
  },
  {
    accessorKey: "triggeredAt",
    header: "触发时间",
    cell: ({ row }) =>
      new Date(row.original.triggeredAt).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }),
  },
  {
    accessorKey: "durationMinutes",
    header: "持续时间",
    cell: ({ row }) => duration(row.original.durationMinutes),
  },
  {
    accessorKey: "status",
    header: "状态",
    cell: ({ row }) => <StatusBadge value={row.original.status} compact />,
  },
  {
    accessorKey: "aiStatus",
    header: "AI 状态",
    cell: ({ row }) => (
      <span
        className={cn(
          "ai-status-cell",
          row.original.aiStatus === "analyzing" && "ai-status-cell--working",
        )}
      >
        <Bot size={13} /> {localizedStatusLabel(row.original.aiStatus)}
      </span>
    ),
  },
  {
    accessorKey: "assignee",
    header: "负责人",
    cell: ({ row }) => row.original.assignee ?? <span className="muted">未指派</span>,
  },
];

const alarmCsvExport = {
  filename: "openvigil-alarms.csv",
  columns: [
    { label: "告警 ID", value: (alarm: Alarm) => alarm.id },
    { label: "严重度", value: (alarm: Alarm) => severityLabel[alarm.severity] },
    { label: "风机", value: (alarm: Alarm) => alarm.turbineId },
    { label: "子系统", value: (alarm: Alarm) => localizedSubsystemLabel(alarm.subsystem) },
    { label: "告警代码", value: (alarm: Alarm) => alarm.code },
    { label: "告警", value: (alarm: Alarm) => alarm.title },
    { label: "触发时间", value: (alarm: Alarm) => alarm.triggeredAt },
    { label: "状态", value: (alarm: Alarm) => localizedStatusLabel(alarm.status) },
    { label: "AI 状态", value: (alarm: Alarm) => localizedStatusLabel(alarm.aiStatus) },
    { label: "负责人", value: (alarm: Alarm) => alarm.assignee },
  ],
} as const;

const alarmSearchText = (alarm: Alarm): string =>
  `${alarm.id} ${alarm.code} ${alarm.title} ${alarm.description} ${alarm.turbineId} ${alarm.subsystem} ${alarm.assignee ?? ""}`;

const alarmRowId = (alarm: Alarm): string => alarm.id;

function duration(minutes: number) {
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

const subsystemTerms: Record<Alarm["subsystem"], string> = {
  "main-bearing": "主轴承",
  "main-shaft": "主轴",
  gearbox: "齿轮箱",
  converter: "变流器",
  pitch: "变桨",
  generator: "发电机",
  yaw: "偏航",
  blades: "叶片",
  hub: "轮毂",
  tower: "塔筒",
  foundation: "基础",
  electrical: "电气",
};

interface ProductionAlarmDetail {
  readonly alarm_id: string;
  readonly mission_id: string | null;
  readonly evidence: Record<string, unknown> | null;
}

interface ProductionKnowledgeCaseCollection {
  readonly count: number;
  readonly cases: readonly {
    readonly case_id: string;
    readonly mission_id: string;
    readonly work_order_id: string | null;
    readonly turbine_id: string;
    readonly title: string;
  }[];
}

interface ProductionWorkOrderCollection {
  readonly count: number;
  readonly work_orders: readonly {
    readonly work_order_id: string;
    readonly title: string;
    readonly status: string;
    readonly assigned_team: string | null;
    readonly estimated_duration_hours: number | null;
  }[];
}

interface ProductionKnowledgeDocumentCollection {
  readonly count: number;
  readonly documents: readonly {
    readonly document_id: string;
    readonly title: string;
    readonly document_version: string;
  }[];
}

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

/** Derive the only honest SCADA evidence available in production: the alarm's own persisted payload. */
function productionScadaEvidence(alarm: Alarm, detail: ProductionAlarmDetail | undefined) {
  const evidence = asRecord(detail?.evidence);
  if (!evidence) return [];
  const attributes = asRecord(evidence.attributes) ?? {};
  const variable = typeof evidence.variable === "string" ? evidence.variable : "";
  const unit = typeof evidence.unit === "string" ? evidence.unit : "";
  const value = typeof evidence.value === "number" ? evidence.value : null;
  const threshold = typeof attributes.threshold === "number" ? attributes.threshold : null;
  if (value === null && !variable) return [];
  return [
    {
      id: `${alarm.id}:evidence`,
      title: variable || alarm.code,
      summary: `当前值 ${value ?? "—"}${unit ? ` ${unit}` : ""} · 阈值 ${threshold ?? "—"}${unit ? ` ${unit}` : ""}`,
      sourceLabel: "PostgreSQL 告警证据载荷",
    },
  ];
}

function AlarmDrawer({
  alarm,
  production,
  onClose,
  onAcknowledge,
  onToggleAssignment,
  commandsAllowed,
}: {
  alarm: Alarm;
  production: boolean;
  onClose: () => void;
  onAcknowledge: (alarmId: string) => void;
  onToggleAssignment: (alarm: Alarm) => void;
  commandsAllowed: boolean;
}) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose);
  // demo 分支保留特色告警故事；production 分支一律以权威后端数据为准，不渲染 fixture。
  const featured = !production && (alarm.id === "ALARM-0031" || alarm.turbineId === "WT-023");
  const canAcknowledge = commandsAllowed && alarm.status === "active";
  const canAssign = commandsAllowed && alarm.status !== "resolved";
  const detailQuery = useQuery({
    queryKey: ["alarm-detail", alarm.id],
    queryFn: ({ signal }) =>
      apiGet<ProductionAlarmDetail>(`/api/backend/alarms/${encodeURIComponent(alarm.id)}`, signal),
    enabled: production,
    retry: false,
  });
  const missionId = production
    ? (detailQuery.data?.mission_id ?? alarm.missionId)
    : alarm.missionId;
  const casesQuery = useQuery({
    queryKey: ["alarm-knowledge-cases", missionId],
    queryFn: ({ signal }) =>
      apiGet<ProductionKnowledgeCaseCollection>(
        `/api/backend/knowledge/cases?mission_id=${encodeURIComponent(missionId ?? "")}`,
        signal,
      ),
    enabled: production && missionId !== null,
    retry: false,
  });
  const workOrderQuery = useQuery({
    queryKey: ["alarm-turbine-work-orders", alarm.turbineId],
    queryFn: ({ signal }) =>
      apiGet<ProductionWorkOrderCollection>(
        `/api/backend/work-orders?turbine_id=${encodeURIComponent(alarm.turbineId)}&limit=20`,
        signal,
      ),
    enabled: production,
    retry: false,
  });
  const subsystemTerm = subsystemTerms[alarm.subsystem];
  const documentQuery = useQuery({
    queryKey: ["alarm-knowledge-documents", subsystemTerm],
    queryFn: ({ signal }) =>
      apiGet<ProductionKnowledgeDocumentCollection>(
        `/api/backend/knowledge/documents?q=${encodeURIComponent(subsystemTerm)}&limit=20`,
        signal,
      ),
    enabled: production,
    retry: false,
  });
  const relatedEvidence = production
    ? []
    : evidenceItems.filter(
        (item) =>
          alarm.evidenceIds.includes(item.id) ||
          (featured && alarm.missionId !== null && item.missionId === alarm.missionId),
      );
  const missionHref = missionId ? `/missions/${missionId}` : `/missions`;
  const productionEvidence = productionScadaEvidence(alarm, detailQuery.data);
  const scadaEvidence = relatedEvidence.filter((item) =>
    ["scada-signal", "vibration-spectrum"].includes(item.type),
  );
  const modelEvidence = relatedEvidence.filter((item) => item.type === "model-output");
  const historicalEvidence = relatedEvidence.filter((item) => item.type === "historical-case");
  const maintenanceEvidence = relatedEvidence.filter((item) => item.type === "maintenance-record");
  const knowledgeEvidence = relatedEvidence.filter((item) => item.type === "knowledge-document");
  const similarCases = production
    ? []
    : failureCases.filter((item) => item.subsystem === alarm.subsystem).slice(0, featured ? 2 : 1);
  const maintenanceRecords = production
    ? []
    : historicalWorkOrders
        .filter((item) => item.issue.includes(subsystemTerm))
        .slice(0, featured ? 2 : 1);
  const referencedKnowledge = production
    ? []
    : knowledgeDocuments
        .filter(
          (document) =>
            document.relatedTurbineIds.includes(alarm.turbineId) ||
            (alarm.missionId !== null && document.relatedMissionIds.includes(alarm.missionId)),
        )
        .slice(0, featured ? 3 : 2);
  const productionCases = casesQuery.data?.cases ?? [];
  const productionWorkOrders = workOrderQuery.data?.work_orders ?? [];
  const productionDocuments = documentQuery.data?.documents ?? [];
  return (
    <>
      <button className="drawer-backdrop" onClick={onClose} aria-label="关闭告警详情" />
      <aside
        ref={dialogRef}
        tabIndex={-1}
        className="detail-drawer alarm-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`${alarm.id} 告警详情`}
      >
        <header className="detail-drawer__header">
          <div>
            <span className="eyebrow">告警详情</span>
            <h2>{alarm.code}</h2>
            <p>
              {alarm.turbineId} · {alarm.subsystem}
            </p>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </Button>
        </header>
        <div className="detail-drawer__status">
          <StatusBadge
            value={alarm.severity}
            label={severityLabel[alarm.severity]}
            tone={severityTone[alarm.severity]}
          />
          <StatusBadge value={alarm.status} label={localizedStatusLabel(alarm.status)} />
          <span>持续 {duration(alarm.durationMinutes)}</span>
        </div>
        <section className="alarm-detail-hero">
          <span className={`alarm-detail-hero__icon alarm-detail-hero__icon--${alarm.severity}`}>
            <AlarmTriangle size={20} />
          </span>
          <div>
            <h3>{alarm.title}</h3>
            <p>{alarm.description}</p>
          </div>
        </section>
        <section className="drawer-section">
          <h3>告警信息</h3>
          <div className="key-value-list">
            <KeyValue
              label="触发时间"
              value={new Date(alarm.triggeredAt).toLocaleString("zh-CN")}
            />
            <KeyValue
              label="当前值"
              value={alarm.currentValue === null ? "—" : `${alarm.currentValue} ${alarm.unit}`}
            />
            <KeyValue
              label="告警阈值"
              value={alarm.threshold === null ? "—" : `${alarm.threshold} ${alarm.unit}`}
            />
            <KeyValue label="负责人" value={alarm.assignee ?? "未指派"} />
            <KeyValue label="AI 状态" value={alarm.aiStatus} />
          </div>
        </section>
        <section className="drawer-section alarm-evidence-section" aria-labelledby="scada-evidence">
          <div className="drawer-section__title">
            <h3 id="scada-evidence">
              <Activity size={14} /> SCADA 趋势
            </h3>
            <Link href={`/scada?turbineId=${alarm.turbineId}`}>
              打开趋势 <ArrowRight size={12} />
            </Link>
          </div>
          <div className="evidence-compact-list">
            {production ? (
              detailQuery.isPending ? (
                <p className="no-evidence">正在读取权威告警证据…</p>
              ) : detailQuery.isError ? (
                <p className="no-evidence" role="alert">
                  生产告警证据读取失败，已失败关闭，不回退演示数据。
                </p>
              ) : productionEvidence.length ? (
                productionEvidence.map((item) => (
                  <div key={item.id}>
                    <span>
                      <Activity size={14} />
                    </span>
                    <div>
                      <strong>{item.title}</strong>
                      <small>{item.summary}</small>
                      <small>{item.sourceLabel}</small>
                    </div>
                  </div>
                ))
              ) : (
                <p className="no-evidence">该告警未携带结构化 SCADA 证据载荷</p>
              )
            ) : scadaEvidence.length ? (
              scadaEvidence.map((item) => (
                <div key={item.id}>
                  <span>
                    <Activity size={14} />
                  </span>
                  <div>
                    <strong>{item.title}</strong>
                    <small>{item.summary}</small>
                    <small>
                      {item.sourceLabel} · {item.confidencePercent ?? "—"}% 可信度
                    </small>
                  </div>
                  {item.deltaPercent !== null ? <em>+{item.deltaPercent}%</em> : null}
                </div>
              ))
            ) : (
              <p className="no-evidence">暂无可关联的 SCADA 趋势证据</p>
            )}
          </div>
        </section>

        <section
          className="drawer-section alarm-evidence-section"
          aria-labelledby="history-evidence"
        >
          <div className="drawer-section__title">
            <h3 id="history-evidence">
              <History size={14} /> 历史相似事件
            </h3>
            <span className="record-count">
              {production
                ? productionCases.length
                : historicalEvidence.length + similarCases.length}{" "}
              项
            </span>
          </div>
          <div className="evidence-compact-list evidence-compact-list--linked">
            {production ? (
              missionId === null ? (
                <p className="no-evidence">当前告警未关联 Mission，暂无真实相似案例。</p>
              ) : casesQuery.isPending ? (
                <p className="no-evidence">正在读取生产知识案例…</p>
              ) : casesQuery.isError ? (
                <p className="no-evidence" role="alert">
                  相似案例读取失败，已失败关闭，不回退演示案例。
                </p>
              ) : productionCases.length ? (
                productionCases.map((item) => (
                  <Link
                    href={
                      item.work_order_id
                        ? `/work-orders?workOrder=${item.work_order_id}`
                        : `/missions/${item.mission_id}`
                    }
                    key={item.case_id}
                  >
                    <span>
                      <History size={14} />
                    </span>
                    <div>
                      <strong>{item.title}</strong>
                      <small>
                        {item.turbine_id} · {item.case_id} · 已沉淀闭环案例
                      </small>
                    </div>
                    <ArrowRight size={13} />
                  </Link>
                ))
              ) : (
                <p className="no-evidence">生产知识库暂无该 Mission 的相似案例</p>
              )
            ) : (
              <>
                {historicalEvidence.map((item) => (
                  <Link href={`/knowledge?document=${item.sourceId ?? ""}`} key={item.id}>
                    <span>
                      <FileSearch size={14} />
                    </span>
                    <div>
                      <strong>{item.title}</strong>
                      <small>{item.summary}</small>
                    </div>
                    <em>{item.value ?? "—"}</em>
                  </Link>
                ))}
                {similarCases.map((failureCase) => (
                  <Link
                    href={`/work-orders?workOrder=${failureCase.relatedWorkOrderId}`}
                    key={failureCase.id}
                  >
                    <span>
                      <History size={14} />
                    </span>
                    <div>
                      <strong>{failureCase.title}</strong>
                      <small>
                        {failureCase.turbineId} · {failureCase.failureMode} · 停机{" "}
                        {failureCase.downtimeHours}h
                      </small>
                    </div>
                    <StatusBadge value={failureCase.severity} compact />
                  </Link>
                ))}
              </>
            )}
          </div>
        </section>

        <section
          className="drawer-section alarm-evidence-section"
          aria-labelledby="maintenance-evidence"
        >
          <div className="drawer-section__title">
            <h3 id="maintenance-evidence">
              <Wrench size={14} /> 维护记录
            </h3>
            <Link href={`/work-orders?turbineId=${alarm.turbineId}`}>
              工单中心 <ArrowRight size={12} />
            </Link>
          </div>
          <div className="evidence-compact-list evidence-compact-list--linked">
            {production ? (
              workOrderQuery.isPending ? (
                <p className="no-evidence">正在读取该机组的生产工单…</p>
              ) : workOrderQuery.isError ? (
                <p className="no-evidence" role="alert">
                  维护记录读取失败，已失败关闭，不回退演示工单。
                </p>
              ) : productionWorkOrders.length ? (
                productionWorkOrders.map((workOrder) => (
                  <Link
                    href={`/work-orders?workOrder=${workOrder.work_order_id}`}
                    key={workOrder.work_order_id}
                  >
                    <span>
                      <Wrench size={14} />
                    </span>
                    <div>
                      <strong>{workOrder.title}</strong>
                      <small>
                        {workOrder.work_order_id} · {workOrder.assigned_team ?? "未分配"} ·{" "}
                        {workOrder.estimated_duration_hours ?? "—"}h
                      </small>
                    </div>
                    <StatusBadge value={workOrder.status.replaceAll("_", "-")} compact />
                  </Link>
                ))
              ) : (
                <p className="no-evidence">该机组暂无生产维护工单记录</p>
              )
            ) : (
              <>
                {maintenanceEvidence.map((item) => (
                  <Link href={`/knowledge?document=${item.sourceId ?? ""}`} key={item.id}>
                    <span>
                      <FileSearch size={14} />
                    </span>
                    <div>
                      <strong>{item.title}</strong>
                      <small>{item.summary}</small>
                    </div>
                    <ArrowRight size={13} />
                  </Link>
                ))}
                {maintenanceRecords.map((workOrder) => (
                  <Link href={`/work-orders?workOrder=${workOrder.id}`} key={workOrder.id}>
                    <span>
                      <Wrench size={14} />
                    </span>
                    <div>
                      <strong>{workOrder.issue}</strong>
                      <small>
                        {workOrder.id} · {workOrder.assignedTeam} ·{" "}
                        {workOrder.estimatedDurationHours}h
                      </small>
                    </div>
                    <StatusBadge value={workOrder.status} compact />
                  </Link>
                ))}
              </>
            )}
          </div>
        </section>

        <section
          className="drawer-section alarm-evidence-section"
          aria-labelledby="knowledge-evidence"
        >
          <div className="drawer-section__title">
            <h3 id="knowledge-evidence">
              <BookOpenText size={14} /> 知识库引用
            </h3>
            <Link href={`/knowledge?turbineId=${alarm.turbineId}`}>
              知识库 <ArrowRight size={12} />
            </Link>
          </div>
          <div className="evidence-compact-list evidence-compact-list--linked">
            {production ? (
              documentQuery.isPending ? (
                <p className="no-evidence">正在检索生产知识库文档…</p>
              ) : documentQuery.isError ? (
                <p className="no-evidence" role="alert">
                  知识库引用读取失败，已失败关闭，不回退演示文档。
                </p>
              ) : productionDocuments.length ? (
                productionDocuments.map((document) => (
                  <Link
                    href={`/knowledge?document=${document.document_id}`}
                    key={document.document_id}
                  >
                    <span>
                      <BookOpenText size={14} />
                    </span>
                    <div>
                      <strong>{document.title}</strong>
                      <small>
                        {document.document_id} · v{document.document_version}
                      </small>
                    </div>
                    <ArrowRight size={13} />
                  </Link>
                ))
              ) : (
                <p className="no-evidence">生产知识库暂无匹配「{subsystemTerm}」的文档</p>
              )
            ) : (
              <>
                {knowledgeEvidence.map((item) => (
                  <Link href={`/knowledge?document=${item.sourceId ?? ""}`} key={item.id}>
                    <span>
                      <BookOpenText size={14} />
                    </span>
                    <div>
                      <strong>{item.sourceLabel}</strong>
                      <small>{item.summary}</small>
                    </div>
                    <ArrowRight size={13} />
                  </Link>
                ))}
                {referencedKnowledge
                  .filter(
                    (document) => !knowledgeEvidence.some((item) => item.sourceId === document.id),
                  )
                  .map((document) => (
                    <Link href={`/knowledge?document=${document.id}`} key={document.id}>
                      <span>
                        <BookOpenText size={14} />
                      </span>
                      <div>
                        <strong>{document.title}</strong>
                        <small>
                          {document.id} · {document.version} · {document.pageCount} 页
                        </small>
                      </div>
                      <ArrowRight size={13} />
                    </Link>
                  ))}
              </>
            )}
          </div>
        </section>

        <section className="alarm-agent-analysis" aria-labelledby="agent-analysis">
          <div className="alarm-agent-analysis__label">
            <Bot size={14} />
            <h3 id="agent-analysis">Agent 分析</h3>
            <span>故障诊断 Agent</span>
          </div>
          {production ? (
            detailQuery.isPending ? (
              <div className="alarm-agent-analysis__pending">
                <Bot size={17} />
                <div>
                  <strong>正在读取权威告警详情</strong>
                  <p>生产模式不会展示演示诊断结论，Mission 关联以权威后端为准。</p>
                </div>
              </div>
            ) : detailQuery.isError ? (
              <div className="alarm-agent-analysis__pending" role="alert">
                <Bot size={17} />
                <div>
                  <strong>告警详情读取失败</strong>
                  <p>已失败关闭，不回退演示诊断；请检查生产后端连通性后重试。</p>
                </div>
              </div>
            ) : missionId ? (
              <div className="ai-diagnosis-card">
                <div className="ai-diagnosis-card__header">
                  <span>
                    <Bot size={17} />
                  </span>
                  <div>
                    <span className="eyebrow">AI 诊断</span>
                    <h3>已关联诊断 Mission</h3>
                  </div>
                </div>
                <p>
                  该告警已关联持久化 Mission <span className="mono">{missionId}</span>
                  ；诊断结论、证据与审批链路以权威 Mission 记录为准。
                </p>
                <a href={`/missions/${missionId}`}>
                  打开完整诊断 Mission <ArrowRight size={13} />
                </a>
              </div>
            ) : (
              <div className="alarm-agent-analysis__pending">
                <Bot size={17} />
                <div>
                  <strong>
                    {alarm.aiStatus === "queued" || alarm.aiStatus === "analyzing"
                      ? "关联分析进行中"
                      : "尚未关联诊断 Mission"}
                  </strong>
                  <p>
                    {alarm.aiStatus === "queued" || alarm.aiStatus === "analyzing"
                      ? "Agent 正在校验趋势、历史案例和维护记录，完成后将生成可审批建议。"
                      : "生产模式不会展示演示诊断结论；Mission 创建后将在此给出真实链接。"}
                  </p>
                </div>
              </div>
            )
          ) : featured ? (
            <div className="ai-diagnosis-card">
              <div className="ai-diagnosis-card__header">
                <span>
                  <Bot size={17} />
                </span>
                <div>
                  <span className="eyebrow">AI 诊断</span>
                  <h3>主轴承早期退化</h3>
                </div>
                <strong>87%</strong>
              </div>
              <p>
                振动 RMS 持续升高，且与主轴承温升和功率波动存在显著相关性。建议降载运行，并在 72
                小时内完成现场检查。
              </p>
              <div className="diagnosis-signals">
                <span>
                  <Activity size={13} /> 振动 +27%
                </span>
                <span>
                  <Thermometer size={13} /> 温度 +8.4°C
                </span>
                <span>
                  <Activity size={13} /> 功率波动 +6%
                </span>
              </div>
              <div className="agent-model-evidence">
                {modelEvidence.slice(0, 2).map((item) => (
                  <div key={item.id}>
                    <span>{item.metric}</span>
                    <strong>
                      {item.value} {item.unit}
                    </strong>
                    <small>{item.title}</small>
                  </div>
                ))}
              </div>
              <Link href={`/missions/${featuredMission.id}`}>
                打开完整诊断 Mission <ArrowRight size={13} />
              </Link>
            </div>
          ) : (
            <div className="alarm-agent-analysis__pending">
              <Bot size={17} />
              <div>
                <strong>关联分析进行中</strong>
                <p>Agent 正在校验趋势、历史案例和维护记录，完成后将生成可审批建议。</p>
              </div>
            </div>
          )}
        </section>
        <section className="drawer-section">
          <h3>处理记录</h3>
          <div className="alarm-audit">
            <div>
              <span>
                <AlarmTriangle size={12} />
              </span>
              <p>
                <strong>告警已触发</strong>
                <small>
                  {alarm.turbineId} · {new Date(alarm.triggeredAt).toLocaleString("zh-CN")}
                </small>
              </p>
            </div>
            {alarm.status === "active" ? (
              <div>
                <span>
                  <Clock3 size={12} />
                </span>
                <p>
                  <strong>等待告警确认</strong>
                  <small>当前状态 · 活动</small>
                </p>
              </div>
            ) : null}
            {alarm.status === "acknowledged" || alarm.status === "resolved" ? (
              <div>
                <span>
                  <Check size={12} />
                </span>
                <p>
                  <strong>告警已确认</strong>
                  <small>
                    {alarm.assignee ?? "值班工程师"} ·{" "}
                    {alarm.acknowledgedAt
                      ? new Date(alarm.acknowledgedAt).toLocaleString("zh-CN")
                      : "确认时间未记录"}
                  </small>
                </p>
              </div>
            ) : null}
            {alarm.status === "suppressed" ? (
              <div>
                <span>
                  <ShieldAlert size={12} />
                </span>
                <p>
                  <strong>告警已抑制</strong>
                  <small>当前状态 · 已抑制</small>
                </p>
              </div>
            ) : null}
            <div>
              <span>
                <Bot size={12} />
              </span>
              <p>
                <strong>
                  {alarm.aiStatus === "queued" && "已进入 AI 分析队列"}
                  {alarm.aiStatus === "analyzing" && "AI 分析进行中"}
                  {alarm.aiStatus === "diagnosed" && "AI 分析完成"}
                  {alarm.aiStatus === "action-created" && "AI 已创建处置动作"}
                  {alarm.aiStatus === "not-required" && "无需 AI 分析"}
                </strong>
                <small>故障诊断 Agent · {alarm.aiStatus}</small>
              </p>
            </div>
            <div>
              <span>
                <ShieldAlert size={12} />
              </span>
              <p>
                <strong>{alarm.missionId ? "已关联处置 Mission" : "尚未创建 Mission"}</strong>
                <small>{alarm.missionId ?? "当前告警暂无闭环任务"}</small>
              </p>
            </div>
            {alarm.assignee ? (
              <div>
                <span>
                  <UserRound size={12} />
                </span>
                <p>
                  <strong>已指派负责人</strong>
                  <small>
                    {alarm.assignee} · {production ? "权威告警状态" : "本地处置状态"}
                  </small>
                </p>
              </div>
            ) : null}
            {alarm.status === "resolved" ? (
              <div>
                <span>
                  <Check size={12} />
                </span>
                <p>
                  <strong>告警已解决</strong>
                  <small>
                    {alarm.resolvedAt
                      ? new Date(alarm.resolvedAt).toLocaleString("zh-CN")
                      : "解决时间未记录"}
                  </small>
                </p>
              </div>
            ) : null}
          </div>
        </section>
        <footer className="detail-drawer__footer">
          {!commandsAllowed ? (
            <span role="status" data-capability="alarm.command">
              当前角色可查看告警；确认和指派需要值班审批权限。
            </span>
          ) : null}
          <Button
            variant="secondary"
            disabled={!canAcknowledge}
            onClick={() => onAcknowledge(alarm.id)}
          >
            <Check size={14} />{" "}
            {alarm.status === "acknowledged"
              ? "已确认"
              : alarm.status === "resolved"
                ? "已解决"
                : alarm.status === "suppressed"
                  ? "已抑制"
                  : "确认告警"}
          </Button>
          <Button
            variant="secondary"
            disabled={!canAssign}
            onClick={() => onToggleAssignment(alarm)}
          >
            <UserRound size={14} />{" "}
            {alarm.status === "resolved"
              ? "已解决 · 不可指派"
              : alarm.assignee
                ? "取消指派"
                : production
                  ? "指派给我"
                  : "指派值班工程师"}
          </Button>
          {production ? (
            <a href={missionHref} className="button button--primary button--md">
              进入 Mission <ArrowRight size={14} />
            </a>
          ) : (
            <Link href={missionHref} className="button button--primary button--md">
              进入 Mission <ArrowRight size={14} />
            </Link>
          )}
        </footer>
      </aside>
    </>
  );
}

export function AlarmCenterPage({ runtimeMode }: { runtimeMode: "demo" | "production" }) {
  const { can } = useOpenVigilIdentity();
  const canCommandAlarms = runtimeMode === "demo" || can("alarm.command");
  const queryClient = useQueryClient();
  const workflow = useDemoWorkflow();
  const [selectedAlarmId, setSelectedAlarmId] = useState<string | null>(null);
  const [severity, setSeverity] = useState<"all" | AlarmSeverity>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | Alarm["status"]>("all");
  const [timeWindowHours, setTimeWindowHours] = useState<0 | 1 | 6 | 24>(0);
  const [turbineScope, setTurbineScope] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const alarmQuery = useQuery({
    queryKey: ["alarms", workflow.serverRevision],
    queryFn: ({ signal }) =>
      apiGet<{
        readonly data: readonly Alarm[];
        readonly meta: { readonly alarmMutationPersistence: string };
      }>("/api/alarms", signal),
    initialData:
      runtimeMode === "demo"
        ? { data: alarms, meta: { alarmMutationPersistence: "unavailable" } }
        : undefined,
  });
  useEffect(() => {
    const parameters = new URLSearchParams(window.location.search);
    const turbineId = parameters.get("turbineId")?.toUpperCase();
    const alarmId = parameters.get("alarm")?.toUpperCase();
    const timer = window.setTimeout(() => {
      if (turbineId) setTurbineScope(turbineId);
      if (alarmId && alarmQuery.data?.data.some((alarm) => alarm.id === alarmId)) {
        setSelectedAlarmId(alarmId);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [alarmQuery.data?.data]);
  const alarmStream = useRealtimeChannel("alarms", runtimeMode === "demo");
  const productionStream = useProductionEvents({
    enabled: runtimeMode === "production",
    eventTypes: productionAlarmEventTypes,
    cursorKey: "windops.production-events.alarms.v1",
    onReady: () => void queryClient.invalidateQueries({ queryKey: ["alarms"] }),
    onEvent: () => void queryClient.invalidateQueries({ queryKey: ["alarms"] }),
  });
  const visibleAlarms = useMemo(
    () =>
      runtimeMode === "demo"
        ? overlayClientAlarms(alarmQuery.data?.data ?? [], workflow)
        : (alarmQuery.data?.data ?? []),
    [alarmQuery.data?.data, runtimeMode, workflow],
  );
  const mutateAlarm = useCallback(
    async (alarm: Alarm, action: "acknowledge" | "assign") => {
      if (!canCommandAlarms) {
        setMutationError("当前角色可查看告警，但没有确认或指派权限。");
        return;
      }
      const operationId = crypto.randomUUID();
      setMutationError(null);
      try {
        await apiPost("/api/alarms", {
          alarmId: alarm.id,
          action,
          ...(action === "assign"
            ? {
                assignee: alarm.assignee ? null : runtimeMode === "demo" ? "值班工程师" : undefined,
              }
            : {}),
          correlationId: `alarm-${operationId}`,
          idempotencyKey: `alarm-${alarm.id}-${operationId}`,
          ...(runtimeMode === "production"
            ? {
                expectedRevision: alarm.revision,
                reason:
                  action === "acknowledge"
                    ? "Alarm Center operator acknowledgement"
                    : alarm.assignee
                      ? "Alarm Center operator self-unassignment"
                      : "Alarm Center operator self-assignment",
              }
            : {}),
        });
        await alarmQuery.refetch();
      } catch (error) {
        setMutationError(error instanceof Error ? error.message : "告警持久化失败");
      }
    },
    [alarmQuery, canCommandAlarms, runtimeMode],
  );
  const selectedAlarm = visibleAlarms.find((alarm) => alarm.id === selectedAlarmId) ?? null;
  const featuredAlarm =
    visibleAlarms.find((alarm) => alarm.turbineId === "WT-023") ?? visibleAlarms[0];
  const filtered = useMemo(
    () =>
      visibleAlarms.filter(
        (alarm) =>
          (turbineScope === null || alarm.turbineId === turbineScope) &&
          (severity === "all" || alarm.severity === severity) &&
          (statusFilter === "all" || alarm.status === statusFilter) &&
          (timeWindowHours === 0 ||
            new Date(windFarm.lastUpdatedAt).getTime() - new Date(alarm.triggeredAt).getTime() <=
              timeWindowHours * 3_600_000),
      ),
    [severity, statusFilter, timeWindowHours, turbineScope, visibleAlarms],
  );
  const counts = {
    critical: visibleAlarms.filter((item) => item.severity === "critical").length,
    major: visibleAlarms.filter((item) => item.severity === "major").length,
    warning: visibleAlarms.filter((item) => item.severity === "warning").length,
    diagnosed: visibleAlarms.filter(
      (item) => item.aiStatus === "diagnosed" || item.aiStatus === "action-created",
    ).length,
  };
  const unresolvedCount = visibleAlarms.filter((alarm) => alarm.status !== "resolved").length;
  const analyzingCount = visibleAlarms.filter((alarm) =>
    ["queued", "analyzing"].includes(alarm.aiStatus),
  ).length;
  const liveAlarmId =
    runtimeMode === "production"
      ? (productionStream.lastEvent?.aggregate_id ?? "")
      : alarmStream.frame?.event === "alarm-update"
        ? asText(alarmStream.frame.data.id)
        : "";
  const hasFilters =
    turbineScope !== null || severity !== "all" || statusFilter !== "all" || timeWindowHours !== 0;

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/alarms">
      <PageHeader
        eyebrow="智能运维"
        title="告警中心"
        description="工业级告警分级、关联分析与 AI 诊断闭环"
        breadcrumb={["智能运维", "告警中心"]}
        meta={
          <>
            <StatusBadge
              value="critical"
              label={`${counts.critical} 条严重告警`}
              tone="critical"
              pulse
            />
            <span className="page-meta-text">
              {unresolvedCount} 个活跃告警 · {analyzingCount} 个正在 AI 分析 ·{" "}
              {runtimeMode === "production"
                ? productionStream.status === "connected"
                  ? `SSE 实时 · 游标 ${productionStream.cursor ?? "同步中"}${liveAlarmId ? ` · ${liveAlarmId}` : ""}`
                  : "SSE 正在重连 · 权威快照"
                : alarmStream.status === "connected"
                  ? `WS 实时 · ${liveAlarmId}`
                  : "数据快照"}
              {mutationError ? ` · 写入失败：${mutationError}` : ""}
            </span>
          </>
        }
      />

      <section className="alarm-summary-grid">
        <button
          onClick={() => setSeverity("critical")}
          className={cn(severity === "critical" && "active")}
        >
          <span className="summary-icon summary-icon--critical">
            <AlarmTriangle size={16} />
          </span>
          <span>
            <small>严重</small>
            <strong>{counts.critical}</strong>
          </span>
          <em>需立即处理</em>
        </button>
        <button
          onClick={() => setSeverity("major")}
          className={cn(severity === "major" && "active")}
        >
          <span className="summary-icon summary-icon--warning">
            <ShieldAlert size={16} />
          </span>
          <span>
            <small>重要</small>
            <strong>{counts.major}</strong>
          </span>
          <em>重点关注</em>
        </button>
        <button
          onClick={() => setSeverity("warning")}
          className={cn(severity === "warning" && "active")}
        >
          <span className="summary-icon summary-icon--maintenance">
            <Activity size={16} />
          </span>
          <span>
            <small>警告</small>
            <strong>{counts.warning}</strong>
          </span>
          <em>趋势观察</em>
        </button>
        <button onClick={() => setSeverity("all")} className={cn(severity === "all" && "active")}>
          <span className="summary-icon summary-icon--info">
            <Bot size={16} />
          </span>
          <span>
            <small>AI 已诊断</small>
            <strong>{counts.diagnosed}</strong>
          </span>
          <em>已形成判断</em>
        </button>
      </section>

      <DataTable
        columns={alarmColumns}
        csvExport={alarmCsvExport}
        data={filtered}
        emptyMessage="没有符合当前筛选条件的告警"
        getRowId={alarmRowId}
        initialSorting={[{ id: "triggeredAt", desc: true }]}
        onRowActivate={(alarm) => setSelectedAlarmId(alarm.id)}
        pageSize={8}
        searchPlaceholder="搜索告警、机组或代码…"
        searchTextForRow={alarmSearchText}
        selectedRowId={selectedAlarmId ?? featuredAlarm?.id}
        bulkActions={
          canCommandAlarms
            ? [
                {
                  label: "确认所选活跃告警",
                  onActivate: (rows: readonly Alarm[]) => {
                    void Promise.all(
                      rows
                        .filter((alarm) => alarm.status === "active")
                        .map((alarm) => mutateAlarm(alarm, "acknowledge")),
                    );
                  },
                },
              ]
            : []
        }
        filterControls={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                const options: readonly ("all" | Alarm["status"])[] = [
                  "all",
                  "active",
                  "acknowledged",
                  "suppressed",
                  "resolved",
                ];
                setStatusFilter(options[(options.indexOf(statusFilter) + 1) % options.length]);
              }}
            >
              <Filter size={14} /> 状态 {statusFilter === "all" ? "全部" : statusFilter}{" "}
              <ChevronDown size={12} />
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                const options = [0, 1, 6, 24] as const;
                setTimeWindowHours(
                  options[(options.indexOf(timeWindowHours) + 1) % options.length],
                );
              }}
            >
              <Clock3 size={14} /> 触发时间 {timeWindowHours ? `${timeWindowHours}H` : "全部"}{" "}
              <ChevronDown size={12} />
            </Button>
            {turbineScope ? (
              <Button variant="secondary" onClick={() => setTurbineScope(null)}>
                机组 {turbineScope} <X size={12} />
              </Button>
            ) : null}
            <Button
              variant="ghost"
              disabled={!hasFilters}
              onClick={() => {
                setSeverity("all");
                setStatusFilter("all");
                setTimeWindowHours(0);
                setTurbineScope(null);
              }}
            >
              清除筛选
            </Button>
          </>
        }
      />
      {selectedAlarm ? (
        <AlarmDrawer
          alarm={selectedAlarm}
          production={runtimeMode === "production"}
          onClose={() => setSelectedAlarmId(null)}
          onAcknowledge={() => void mutateAlarm(selectedAlarm, "acknowledge")}
          onToggleAssignment={(alarm) => void mutateAlarm(alarm, "assign")}
          commandsAllowed={canCommandAlarms}
        />
      ) : null}
    </AppShell>
  );
}
