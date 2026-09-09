"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { cn } from "@/lib/utils";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { overlayClientAlarms } from "@/lib/client-workflow-overlays";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";

const severityTone: Record<AlarmSeverity, StatusTone> = {
  critical: "critical",
  major: "warning",
  minor: "maintenance",
  warning: "warning",
  info: "info",
};
const severityLabel: Record<AlarmSeverity, string> = {
  critical: "CRITICAL",
  major: "MAJOR",
  minor: "MINOR",
  warning: "WARNING",
  info: "INFO",
};

const alarmColumns: readonly LegacyColumnDef<Alarm, unknown>[] = [
  {
    accessorKey: "severity",
    header: "Severity",
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
    header: "Wind Turbine",
    cell: ({ row }) => <strong className="mono">{row.original.turbineId}</strong>,
  },
  {
    accessorKey: "subsystem",
    header: "Subsystem",
    cell: ({ row }) => row.original.subsystem.replaceAll("-", " "),
  },
  {
    accessorKey: "code",
    header: "Alarm Code",
    cell: ({ row }) => <span className="mono">{row.original.code}</span>,
  },
  {
    accessorKey: "title",
    header: "Alarm",
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
    header: "Triggered At",
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
    header: "Duration",
    cell: ({ row }) => duration(row.original.durationMinutes),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge value={row.original.status} compact />,
  },
  {
    accessorKey: "aiStatus",
    header: "AI Status",
    cell: ({ row }) => (
      <span
        className={cn(
          "ai-status-cell",
          row.original.aiStatus === "analyzing" && "ai-status-cell--working",
        )}
      >
        <Bot size={13} /> {row.original.aiStatus}
      </span>
    ),
  },
  {
    accessorKey: "assignee",
    header: "Assignee",
    cell: ({ row }) => row.original.assignee ?? <span className="muted">未指派</span>,
  },
];

const alarmCsvExport = {
  filename: "windops-alarms.csv",
  columns: [
    { label: "Alarm ID", value: (alarm: Alarm) => alarm.id },
    { label: "Severity", value: (alarm: Alarm) => alarm.severity },
    { label: "Wind Turbine", value: (alarm: Alarm) => alarm.turbineId },
    { label: "Subsystem", value: (alarm: Alarm) => alarm.subsystem },
    { label: "Alarm Code", value: (alarm: Alarm) => alarm.code },
    { label: "Alarm", value: (alarm: Alarm) => alarm.title },
    { label: "Triggered At", value: (alarm: Alarm) => alarm.triggeredAt },
    { label: "Status", value: (alarm: Alarm) => alarm.status },
    { label: "AI Status", value: (alarm: Alarm) => alarm.aiStatus },
    { label: "Assignee", value: (alarm: Alarm) => alarm.assignee },
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

function AlarmDrawer({
  alarm,
  onClose,
  onAcknowledge,
  onToggleAssignment,
}: {
  alarm: Alarm;
  onClose: () => void;
  onAcknowledge: (alarmId: string) => void;
  onToggleAssignment: (alarm: Alarm) => void;
}) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose);
  const featured = alarm.id === "ALARM-0031" || alarm.turbineId === "WT-023";
  const canAcknowledge = alarm.status === "active";
  const canAssign = alarm.status !== "resolved";
  const relatedEvidence = evidenceItems.filter(
    (item) =>
      alarm.evidenceIds.includes(item.id) ||
      (featured && alarm.missionId !== null && item.missionId === alarm.missionId),
  );
  const missionHref = alarm.missionId ? `/missions/${alarm.missionId}` : `/missions`;
  const scadaEvidence = relatedEvidence.filter((item) =>
    ["scada-signal", "vibration-spectrum"].includes(item.type),
  );
  const modelEvidence = relatedEvidence.filter((item) => item.type === "model-output");
  const historicalEvidence = relatedEvidence.filter((item) => item.type === "historical-case");
  const maintenanceEvidence = relatedEvidence.filter((item) => item.type === "maintenance-record");
  const knowledgeEvidence = relatedEvidence.filter((item) => item.type === "knowledge-document");
  const subsystemTerm = subsystemTerms[alarm.subsystem];
  const similarCases = failureCases
    .filter((item) => item.subsystem === alarm.subsystem)
    .slice(0, featured ? 2 : 1);
  const maintenanceRecords = historicalWorkOrders
    .filter((item) => item.issue.includes(subsystemTerm))
    .slice(0, featured ? 2 : 1);
  const referencedKnowledge = knowledgeDocuments
    .filter(
      (document) =>
        document.relatedTurbineIds.includes(alarm.turbineId) ||
        (alarm.missionId !== null && document.relatedMissionIds.includes(alarm.missionId)),
    )
    .slice(0, featured ? 3 : 2);
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
            <span className="eyebrow">ALARM DETAIL</span>
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
          <StatusBadge value={alarm.status} label={alarm.status.toUpperCase()} />
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
            {scadaEvidence.length ? (
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
              {historicalEvidence.length + similarCases.length} 项
            </span>
          </div>
          <div className="evidence-compact-list evidence-compact-list--linked">
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
                    {workOrder.id} · {workOrder.assignedTeam} · {workOrder.estimatedDurationHours}h
                  </small>
                </div>
                <StatusBadge value={workOrder.status} compact />
              </Link>
            ))}
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
          </div>
        </section>

        <section className="alarm-agent-analysis" aria-labelledby="agent-analysis">
          <div className="alarm-agent-analysis__label">
            <Bot size={14} />
            <h3 id="agent-analysis">Agent 分析</h3>
            <span>Failure Diagnosis Agent</span>
          </div>
          {featured ? (
            <div className="ai-diagnosis-card">
              <div className="ai-diagnosis-card__header">
                <span>
                  <Bot size={17} />
                </span>
                <div>
                  <span className="eyebrow">AI DIAGNOSIS</span>
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
                  <small>当前状态 · ACTIVE</small>
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
                  <small>当前状态 · SUPPRESSED</small>
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
                <small>Failure Diagnosis Agent · {alarm.aiStatus}</small>
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
                  <small>{alarm.assignee} · 当前本地处置状态</small>
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
                : "指派值班工程师"}
          </Button>
          <Link href={missionHref} className="button button--primary button--md">
            进入 Mission <ArrowRight size={14} />
          </Link>
        </footer>
      </aside>
    </>
  );
}

export function AlarmCenterPage() {
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
    initialData: { data: alarms, meta: { alarmMutationPersistence: "unavailable" } },
  });
  useEffect(() => {
    const parameters = new URLSearchParams(window.location.search);
    const turbineId = parameters.get("turbineId")?.toUpperCase();
    const alarmId = parameters.get("alarm")?.toUpperCase();
    const timer = window.setTimeout(() => {
      if (turbineId) setTurbineScope(turbineId);
      if (alarmId && alarms.some((alarm) => alarm.id === alarmId)) setSelectedAlarmId(alarmId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const alarmStream = useRealtimeChannel("alarms");
  const visibleAlarms = useMemo(
    () => overlayClientAlarms(alarmQuery.data.data, workflow),
    [alarmQuery.data.data, workflow],
  );
  const mutateAlarm = useCallback(
    async (alarm: Alarm, action: "acknowledge" | "assign") => {
      const operationId = crypto.randomUUID();
      setMutationError(null);
      try {
        await apiPost("/api/alarms", {
          alarmId: alarm.id,
          action,
          ...(action === "assign" ? { assignee: alarm.assignee ? null : "值班工程师" } : {}),
          correlationId: `alarm-${operationId}`,
          idempotencyKey: `alarm-${alarm.id}-${operationId}`,
        });
        await alarmQuery.refetch();
      } catch (error) {
        setMutationError(error instanceof Error ? error.message : "告警持久化失败");
      }
    },
    [alarmQuery],
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
    alarmStream.frame?.event === "alarm-update" ? String(alarmStream.frame.data.id ?? "") : "";
  const hasFilters =
    turbineScope !== null || severity !== "all" || statusFilter !== "all" || timeWindowHours !== 0;

  return (
    <AppShell activePath="/alarms">
      <PageHeader
        eyebrow="智能运维"
        title="告警中心"
        description="工业级告警分级、关联分析与 AI 诊断闭环"
        breadcrumb={["智能运维", "告警中心"]}
        meta={
          <>
            <StatusBadge
              value="critical"
              label={`${counts.critical} CRITICAL`}
              tone="critical"
              pulse
            />
            <span className="page-meta-text">
              {unresolvedCount} 个活跃告警 · {analyzingCount} 个正在 AI 分析 ·{" "}
              {alarmStream.status === "connected" ? `WS LIVE ${liveAlarmId}` : "SNAPSHOT"}
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
            <small>Critical</small>
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
            <small>Major</small>
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
            <small>Warning</small>
            <strong>{counts.warning}</strong>
          </span>
          <em>趋势观察</em>
        </button>
        <button onClick={() => setSeverity("all")} className={cn(severity === "all" && "active")}>
          <span className="summary-icon summary-icon--info">
            <Bot size={16} />
          </span>
          <span>
            <small>AI Diagnosed</small>
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
        bulkActions={[
          {
            label: "确认所选活跃告警",
            onActivate: (rows) => {
              void Promise.all(
                rows
                  .filter((alarm) => alarm.status === "active")
                  .map((alarm) => mutateAlarm(alarm, "acknowledge")),
              );
            },
          },
        ]}
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
                setStatusFilter(options[(options.indexOf(statusFilter) + 1) % options.length]!);
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
                  options[(options.indexOf(timeWindowHours) + 1) % options.length]!,
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
          onClose={() => setSelectedAlarmId(null)}
          onAcknowledge={() => void mutateAlarm(selectedAlarm, "acknowledge")}
          onToggleAssignment={(alarm) => void mutateAlarm(alarm, "assign")}
        />
      ) : null}
    </AppShell>
  );
}
