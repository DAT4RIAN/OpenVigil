import { Bot, UserRound } from "lucide-react";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import { StatusBadge } from "@/components/data-display/status-badge";
import type { WorkOrder, WorkOrderPriority, WorkOrderStatus } from "@/lib/types";

export const statusLabels: Record<WorkOrderStatus, string> = {
  draft: "草稿",
  "pending-approval": "待审批",
  scheduled: "已排程",
  "in-progress": "执行中",
  paused: "暂停",
  completed: "已完成",
  closed: "已关闭",
};

export type WorkOrderStatusFilter = "all" | WorkOrderStatus | "completed-group";
export type PlannedStartFilter = "all" | "due" | "next-24h" | "next-7d";

export const WORKFLOW_WORK_ORDER_ID = "WO-20260823-017";
export const SNAPSHOT_TIMESTAMP = Date.parse("2026-08-13T12:00:00+08:00");
export const DAY_MS = 24 * 60 * 60 * 1000;

export const statusFilterOptions: readonly WorkOrderStatusFilter[] = [
  "all",
  "draft",
  "pending-approval",
  "scheduled",
  "in-progress",
  "paused",
  "completed-group",
];
export const statusFilterLabels: Record<WorkOrderStatusFilter, string> = {
  all: "全部状态",
  draft: "草稿",
  "pending-approval": "待审批",
  scheduled: "已排程",
  "in-progress": "执行中",
  paused: "暂停",
  completed: "已完成",
  closed: "已关闭",
  "completed-group": "已完成 / 已关闭",
};
export const priorityFilterOptions: readonly ("all" | WorkOrderPriority)[] = [
  "all",
  "critical",
  "high",
  "medium",
  "low",
];
export const priorityFilterLabels: Record<"all" | WorkOrderPriority, string> = {
  all: "全部优先级",
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
};
export const plannedStartFilterOptions: readonly PlannedStartFilter[] = [
  "all",
  "due",
  "next-24h",
  "next-7d",
];
export const plannedStartFilterLabels: Record<PlannedStartFilter, string> = {
  all: "全部计划时间",
  due: "计划时间已到",
  "next-24h": "未来 24 小时",
  "next-7d": "未来 7 天",
};

export function nextOption<T extends string>(options: readonly T[], current: T): T {
  return options[(options.indexOf(current) + 1) % options.length] ?? options[0];
}

export const workOrderColumns: readonly LegacyColumnDef<WorkOrder, unknown>[] = [
  {
    accessorKey: "id",
    header: "工单编号",
    cell: ({ row }) => <strong className="mono">{row.original.id}</strong>,
  },
  {
    accessorKey: "turbineId",
    header: "风机",
    cell: ({ row }) => <span className="mono">{row.original.turbineId}</span>,
  },
  {
    accessorKey: "issue",
    header: "问题",
    cell: ({ row }) => (
      <span className="alarm-title-cell">
        <strong>{row.original.issue}</strong>
        <small>{row.original.description}</small>
      </span>
    ),
    size: 300,
  },
  {
    accessorKey: "priority",
    header: "优先级",
    cell: ({ row }) => (
      <StatusBadge
        value={row.original.priority}
        label={
          row.original.priority === "critical"
            ? "严重"
            : row.original.priority === "high"
              ? "高"
              : row.original.priority === "medium"
                ? "中"
                : "低"
        }
        tone={
          row.original.priority === "critical"
            ? "critical"
            : row.original.priority === "high"
              ? "warning"
              : "info"
        }
        compact
      />
    ),
  },
  {
    accessorKey: "status",
    header: "状态",
    cell: ({ row }) => (
      <StatusBadge
        value={row.original.status}
        label={statusLabels[row.original.status]}
        tone={
          row.original.status === "completed" || row.original.status === "closed"
            ? "success"
            : row.original.status === "in-progress"
              ? "info"
              : row.original.status === "scheduled"
                ? "maintenance"
                : "warning"
        }
        compact
      />
    ),
  },
  {
    accessorKey: "assignedTeam",
    header: "执行班组",
    cell: ({ row }) => (
      <span className="team-cell">
        <UserRound size={13} /> {row.original.assignedTeam}
      </span>
    ),
  },
  {
    accessorKey: "createdByAgentId",
    header: "创建方式",
    cell: ({ row }) =>
      row.original.createdByAgentId ? (
        <span className="ai-status-cell">
          <Bot size={13} /> AI Agent
        </span>
      ) : (
        "人工创建"
      ),
  },
  {
    accessorKey: "relatedMissionId",
    header: "关联 Mission",
    cell: ({ row }) => <span className="mono">{row.original.relatedMissionId ?? "—"}</span>,
  },
  {
    accessorKey: "plannedStart",
    header: "计划开始",
    cell: ({ row }) => new Date(row.original.plannedStart).toLocaleDateString("zh-CN"),
  },
  {
    accessorKey: "deadline",
    header: "截止时间",
    cell: ({ row }) => new Date(row.original.deadline).toLocaleDateString("zh-CN"),
  },
];

export const workOrderCsvExport = {
  filename: "openvigil-work-orders-2026-08-13.csv",
  columns: [
    { label: "工单编号", value: (workOrder: WorkOrder) => workOrder.id },
    { label: "风机", value: (workOrder: WorkOrder) => workOrder.turbineId },
    { label: "问题", value: (workOrder: WorkOrder) => workOrder.issue },
    {
      label: "优先级",
      value: (workOrder: WorkOrder) => priorityFilterLabels[workOrder.priority],
    },
    { label: "状态", value: (workOrder: WorkOrder) => statusLabels[workOrder.status] },
    { label: "执行班组", value: (workOrder: WorkOrder) => workOrder.assignedTeam },
    { label: "关联 Mission", value: (workOrder: WorkOrder) => workOrder.relatedMissionId },
    { label: "计划开始", value: (workOrder: WorkOrder) => workOrder.plannedStart },
    { label: "截止时间", value: (workOrder: WorkOrder) => workOrder.deadline },
  ],
} as const;

export const workOrderSearchText = (workOrder: WorkOrder): string =>
  `${workOrder.id} ${workOrder.turbineId} ${workOrder.issue} ${workOrder.description} ${workOrder.assignedTeam} ${workOrder.relatedMissionId ?? ""}`;

export const workOrderRowId = (workOrder: WorkOrder): string => workOrder.id;

export const FIELD_ARTIFACT_TYPES = new Set([
  "application/json",
  "application/pdf",
  "image/jpeg",
  "image/png",
  "text/plain",
  "video/mp4",
]);
export const FIELD_ARTIFACT_ACCEPT = [...FIELD_ARTIFACT_TYPES].join(",");
export const MAX_FIELD_ARTIFACT_BYTES = 50 * 1024 * 1024;

export type SchemaProperty = Readonly<Record<string, unknown>>;

export type ArtifactUploadGrant = {
  artifact_uri: string;
  upload_url: string;
  required_headers: Readonly<Record<string, string>>;
};

export function recordValue(value: unknown): Readonly<Record<string, unknown>> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Readonly<Record<string, unknown>>)
    : {};
}

export function fieldContentType(file: File): string | null {
  if (FIELD_ARTIFACT_TYPES.has(file.type)) return file.type;
  const extension = file.name.split(".").pop()?.toLowerCase();
  return (
    {
      json: "application/json",
      pdf: "application/pdf",
      jpg: "image/jpeg",
      jpeg: "image/jpeg",
      png: "image/png",
      txt: "text/plain",
      mp4: "video/mp4",
    }[extension ?? ""] ?? null
  );
}

export async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}
