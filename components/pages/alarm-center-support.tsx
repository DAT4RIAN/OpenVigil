import { Bot } from "lucide-react";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import { StatusBadge, type StatusTone } from "@/components/data-display/status-badge";
import type { Alarm, AlarmSeverity } from "@/lib/types";
import { cn } from "@/lib/utils";
import { localizedStatusLabel, localizedSubsystemLabel } from "@/lib/ui-localization";

export const severityTone: Record<AlarmSeverity, StatusTone> = {
  critical: "critical",
  major: "warning",
  minor: "maintenance",
  warning: "warning",
  info: "info",
};
export const productionAlarmEventTypes = [
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
export const severityLabel: Record<AlarmSeverity, string> = {
  critical: "严重",
  major: "重要",
  minor: "次要",
  warning: "警告",
  info: "信息",
};

export const alarmColumns: readonly LegacyColumnDef<Alarm, unknown>[] = [
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

export const alarmCsvExport = {
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

export const alarmSearchText = (alarm: Alarm): string =>
  `${alarm.id} ${alarm.code} ${alarm.title} ${alarm.description} ${alarm.turbineId} ${alarm.subsystem} ${alarm.assignee ?? ""}`;

export const alarmRowId = (alarm: Alarm): string => alarm.id;

export function duration(minutes: number) {
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export const subsystemTerms: Record<Alarm["subsystem"], string> = {
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

export interface ProductionAlarmDetail {
  readonly alarm_id: string;
  readonly mission_id: string | null;
  readonly evidence: Record<string, unknown> | null;
}

export interface ProductionKnowledgeCaseCollection {
  readonly count: number;
  readonly cases: readonly {
    readonly case_id: string;
    readonly mission_id: string;
    readonly work_order_id: string | null;
    readonly turbine_id: string;
    readonly title: string;
  }[];
}

export interface ProductionWorkOrderCollection {
  readonly count: number;
  readonly work_orders: readonly {
    readonly work_order_id: string;
    readonly title: string;
    readonly status: string;
    readonly assigned_team: string | null;
    readonly estimated_duration_hours: number | null;
  }[];
}

export interface ProductionKnowledgeDocumentCollection {
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
export function productionScadaEvidence(alarm: Alarm, detail: ProductionAlarmDetail | undefined) {
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
