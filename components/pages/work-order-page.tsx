"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Bot,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Download,
  Filter,
  HardHat,
  PackageCheck,
  Plus,
  ShieldCheck,
  UserRound,
  Wrench,
  X,
} from "lucide-react";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import { DataTable } from "@/components/data-display/data-table";
import { AppShell } from "@/components/layout/app-shell";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { PageHeader } from "@/components/layout/page-header";
import { Button, KeyValue, Progress } from "@/components/ui/primitives";
import { QueryStateNotice, RuntimeHealthBadge } from "@/components/ui/query-state";
import { StatusBadge } from "@/components/data-display/status-badge";
import { featuredMission, historicalWorkOrders, workOrders } from "@/lib";
import type { WorkOrder, WorkOrderPriority, WorkOrderStatus, WorkOrderTask } from "@/lib/types";
import { canCompleteFeaturedWorkOrder } from "@/lib/demo-workflow";
import { overlayClientWorkOrders } from "@/lib/client-workflow-overlays";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { asText, cn } from "@/lib/utils";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";
import { apiGet, apiPost } from "@/lib/api-client";
import { deriveQueryViewState, latestValidTimestamp, queryRuntimeHealth } from "@/lib/query-state";

const statusLabels: Record<WorkOrderStatus, string> = {
  draft: "草稿",
  "pending-approval": "待审批",
  scheduled: "已排程",
  "in-progress": "执行中",
  paused: "暂停",
  completed: "已完成",
  closed: "已关闭",
};

type WorkOrderStatusFilter = "all" | WorkOrderStatus | "completed-group";
type PlannedStartFilter = "all" | "due" | "next-24h" | "next-7d";

const WORKFLOW_WORK_ORDER_ID = "WO-20260823-017";
const SNAPSHOT_TIMESTAMP = Date.parse("2026-08-13T12:00:00+08:00");
const DAY_MS = 24 * 60 * 60 * 1000;

const statusFilterOptions: readonly WorkOrderStatusFilter[] = [
  "all",
  "draft",
  "pending-approval",
  "scheduled",
  "in-progress",
  "paused",
  "completed-group",
];
const statusFilterLabels: Record<WorkOrderStatusFilter, string> = {
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
const priorityFilterOptions: readonly ("all" | WorkOrderPriority)[] = [
  "all",
  "critical",
  "high",
  "medium",
  "low",
];
const priorityFilterLabels: Record<"all" | WorkOrderPriority, string> = {
  all: "全部优先级",
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
};
const plannedStartFilterOptions: readonly PlannedStartFilter[] = [
  "all",
  "due",
  "next-24h",
  "next-7d",
];
const plannedStartFilterLabels: Record<PlannedStartFilter, string> = {
  all: "全部计划时间",
  due: "计划时间已到",
  "next-24h": "未来 24 小时",
  "next-7d": "未来 7 天",
};

function nextOption<T extends string>(options: readonly T[], current: T): T {
  return options[(options.indexOf(current) + 1) % options.length] ?? options[0];
}

const workOrderColumns: readonly LegacyColumnDef<WorkOrder, unknown>[] = [
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

const workOrderCsvExport = {
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

const workOrderSearchText = (workOrder: WorkOrder): string =>
  `${workOrder.id} ${workOrder.turbineId} ${workOrder.issue} ${workOrder.description} ${workOrder.assignedTeam} ${workOrder.relatedMissionId ?? ""}`;

const workOrderRowId = (workOrder: WorkOrder): string => workOrder.id;

const FIELD_ARTIFACT_TYPES = new Set([
  "application/json",
  "application/pdf",
  "image/jpeg",
  "image/png",
  "text/plain",
  "video/mp4",
]);
const FIELD_ARTIFACT_ACCEPT = [...FIELD_ARTIFACT_TYPES].join(",");
const MAX_FIELD_ARTIFACT_BYTES = 50 * 1024 * 1024;

type SchemaProperty = Readonly<Record<string, unknown>>;

type ArtifactUploadGrant = {
  artifact_uri: string;
  upload_url: string;
  required_headers: Readonly<Record<string, string>>;
};

function recordValue(value: unknown): Readonly<Record<string, unknown>> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Readonly<Record<string, unknown>>)
    : {};
}

function fieldContentType(file: File): string | null {
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

async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function FieldTaskCompletionForm({
  workOrderId,
  task,
  onCompleted,
  authorized,
}: {
  workOrderId: string;
  task: WorkOrderTask;
  onCompleted: () => Promise<void>;
  authorized: boolean;
}) {
  const schema = recordValue(task.measurementSchema);
  const properties = recordValue(schema.properties);
  const required = new Set(
    Array.isArray(schema.required)
      ? schema.required.filter((value): value is string => typeof value === "string")
      : [],
  );
  const initialMeasurement = Object.fromEntries(
    Object.entries(properties)
      .map(([name, value]) => [name, recordValue(value).const] as const)
      .filter((entry) => entry[1] !== undefined),
  );
  const [measurement, setMeasurement] = useState<Record<string, unknown>>(initialMeasurement);
  const [result, setResult] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateMeasurement = (name: string, raw: string, property: SchemaProperty) => {
    setMeasurement((current) => {
      const next = { ...current };
      if (raw === "") {
        delete next[name];
        return next;
      }
      next[name] =
        property.type === "number" || property.type === "integer"
          ? Number(raw)
          : property.type === "boolean"
            ? raw === "true"
            : raw;
      return next;
    });
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!authorized) {
      setError("当前角色没有提交现场证据或完成任务的权限。");
      return;
    }
    if (!file) {
      setError("请选择现场证据文件。");
      return;
    }
    if (file.size <= 0 || file.size > MAX_FIELD_ARTIFACT_BYTES) {
      setError("现场证据文件必须在 1 Byte 到 50 MiB 之间。");
      return;
    }
    const contentType = fieldContentType(file);
    if (!contentType) {
      setError("仅支持 JSON、PDF、JPEG、PNG、TXT 或 MP4 证据文件。");
      return;
    }
    const missing = [...required].filter(
      (name) => measurement[name] === undefined || measurement[name] === "",
    );
    if (missing.length) {
      setError(`请填写必填测量字段：${missing.join("、")}。`);
      return;
    }
    if (result.trim().length < 3) {
      setError("请填写至少 3 个字符的现场结论。");
      return;
    }

    setSubmitting(true);
    try {
      const artifactSha256 = await sha256Hex(file);
      const taskPath = `/api/backend/work-orders/${encodeURIComponent(workOrderId)}/tasks/${encodeURIComponent(task.id)}`;
      const grant = await apiPost<ArtifactUploadGrant>(`${taskPath}/artifacts/presign`, {
        file_name: file.name,
        content_type: contentType,
        artifact_sha256: artifactSha256,
      });
      const upload = await fetch(grant.upload_url, {
        method: "PUT",
        headers: grant.required_headers,
        body: file,
      });
      if (!upload.ok) {
        throw new Error(`对象存储上传失败（HTTP ${upload.status}）。`);
      }
      await apiPost(`${taskPath}/complete`, {
        result: result.trim(),
        artifact_uri: grant.artifact_uri,
        artifact_sha256: artifactSha256,
        measurement,
      });
      await onCompleted();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "现场证据提交失败，请重试。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="field-evidence-form" onSubmit={(event) => void submit(event)}>
      <div className="field-evidence-form__heading">
        <span>
          <ShieldCheck size={14} /> 当前可执行任务
        </span>
        <small className="mono">{task.schemaVersion ?? "schema-unversioned"}</small>
      </div>
      <strong>
        {task.sequence}. {task.title}
      </strong>
      <div className="field-evidence-form__fields">
        {Object.entries(properties).map(([name, rawProperty]) => {
          const property = recordValue(rawProperty);
          const label = typeof property.title === "string" ? property.title : name;
          const enumValues = Array.isArray(property.enum) ? property.enum : null;
          const constant = property.const;
          return (
            <label key={name}>
              <span>
                {label} {required.has(name) ? "*" : ""}
              </span>
              {constant !== undefined ? (
                <input value={asText(constant)} readOnly aria-readonly="true" />
              ) : enumValues ? (
                <select
                  value={asText(measurement[name])}
                  onChange={(event) => updateMeasurement(name, event.target.value, property)}
                  required={required.has(name)}
                >
                  <option value="">请选择</option>
                  {enumValues.map((value) => (
                    <option key={String(value)} value={String(value)}>
                      {String(value)}
                    </option>
                  ))}
                </select>
              ) : property.type === "boolean" ? (
                <select
                  value={asText(measurement[name])}
                  onChange={(event) => updateMeasurement(name, event.target.value, property)}
                  required={required.has(name)}
                >
                  <option value="">请选择</option>
                  <option value="true">是</option>
                  <option value="false">否</option>
                </select>
              ) : (
                <input
                  type={
                    property.type === "number" || property.type === "integer" ? "number" : "text"
                  }
                  step={
                    property.type === "integer" ? 1 : property.type === "number" ? "any" : undefined
                  }
                  min={typeof property.minimum === "number" ? property.minimum : undefined}
                  max={typeof property.maximum === "number" ? property.maximum : undefined}
                  value={asText(measurement[name])}
                  onChange={(event) => updateMeasurement(name, event.target.value, property)}
                  required={required.has(name)}
                />
              )}
              {typeof property.description === "string" ? (
                <small>{property.description}</small>
              ) : null}
            </label>
          );
        })}
        <label>
          <span>现场结论 *</span>
          <textarea
            rows={3}
            value={result}
            onChange={(event) => setResult(event.target.value)}
            placeholder="记录检查、测量和处置结论"
            required
          />
        </label>
        <label>
          <span>不可变现场证据 *</span>
          <input
            type="file"
            accept={FIELD_ARTIFACT_ACCEPT}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            required
          />
          <small>上传后由后端重新计算 SHA-256；最大 50 MiB。</small>
        </label>
      </div>
      {error ? (
        <p className="field-evidence-form__error" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit" variant="primary" disabled={submitting || !authorized}>
        <ShieldCheck size={14} /> {submitting ? "校验并提交中…" : "上传证据并完成任务"}
      </Button>
    </form>
  );
}

function WorkOrderDrawer({
  workOrder,
  runtimeMode,
  isWorkflowWorkOrder,
  workflowWritable,
  onClose,
  onToggleTask,
  onStart,
  onComplete,
  onProductionTaskCompleted,
  canComplete,
  canCompleteProductionTask,
}: {
  workOrder: WorkOrder;
  runtimeMode: "demo" | "production";
  isWorkflowWorkOrder: boolean;
  workflowWritable: boolean;
  onClose: () => void;
  onToggleTask: (taskId: string) => void;
  onStart: () => void;
  onComplete: () => void;
  onProductionTaskCompleted: () => Promise<void>;
  canComplete: boolean;
  canCompleteProductionTask: boolean;
}) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose);
  const completed = workOrder.tasks.filter((task) => task.completed).length;
  const productionMode = runtimeMode === "production";
  const nextProductionTask = productionMode
    ? workOrder.tasks.find((task) => !task.completed)
    : undefined;
  const eamStatusLabel =
    workOrder.eam?.syncStatus === "pending"
      ? "等待发布"
      : workOrder.eam?.syncStatus === "accepted"
        ? "EAM 已接收"
        : workOrder.eam?.syncStatus === "in_progress"
          ? "EAM 执行中"
          : workOrder.eam?.syncStatus === "completed" || workOrder.eam?.syncStatus === "closed"
            ? "EAM 已完成"
            : (workOrder.eam?.syncStatus.replaceAll("_", " ") ?? "未启用");
  return (
    <>
      <button className="drawer-backdrop" onClick={onClose} aria-label="关闭工单详情" />
      <aside
        ref={dialogRef}
        tabIndex={-1}
        className="detail-drawer work-order-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`${workOrder.id} 工单详情`}
      >
        <header className="detail-drawer__header">
          <div>
            <span className="eyebrow">工单</span>
            <h2>{workOrder.id}</h2>
            <p>
              {workOrder.turbineId} · {workOrder.assignedTeam}
            </p>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </Button>
        </header>
        <div className="detail-drawer__status">
          <StatusBadge
            value={workOrder.status}
            label={statusLabels[workOrder.status]}
            tone={
              workOrder.status === "completed" || workOrder.status === "closed"
                ? "success"
                : workOrder.status === "in-progress"
                  ? "info"
                  : "warning"
            }
          />
          <StatusBadge
            value={workOrder.priority}
            label={
              workOrder.priority === "critical"
                ? "严重"
                : workOrder.priority === "high"
                  ? "高"
                  : workOrder.priority === "medium"
                    ? "中"
                    : "低"
            }
            tone={
              workOrder.priority === "critical"
                ? "critical"
                : workOrder.priority === "high"
                  ? "warning"
                  : "info"
            }
          />
          <span>{new Date(workOrder.plannedStart).toLocaleDateString("zh-CN")}</span>
        </div>
        <section className="work-order-hero">
          <span>
            <ClipboardCheck size={22} />
          </span>
          <div>
            <h3>{workOrder.issue}</h3>
            <p>{workOrder.description}</p>
          </div>
        </section>
        {workOrder.createdByAgentId ? (
          <div className="ai-generated-note">
            <Bot size={15} />
            <span>
              <strong>由工单 Agent 自动生成</strong>
              <small>来源 {workOrder.relatedMissionId} · 已通过安全审核</small>
            </span>
            <StatusBadge value="approved" label="AI 已验证" tone="info" compact />
          </div>
        ) : null}
        {productionMode && workOrder.eam ? (
          <div className="ai-generated-note" role="status">
            <PackageCheck size={15} />
            <span>
              <strong>企业资产管理系统同步</strong>
              <small>
                {workOrder.eam.externalId
                  ? `${workOrder.eam.provider ?? "EAM"} 工单 ${workOrder.eam.externalId}`
                  : "审批事务已持久化，等待出站工作进程发布"}
                {workOrder.eam.externalUpdatedAt
                  ? ` · 外部更新时间 ${new Date(workOrder.eam.externalUpdatedAt).toLocaleString("zh-CN")}`
                  : ""}
              </small>
            </span>
            <StatusBadge
              value={workOrder.eam.syncStatus}
              label={eamStatusLabel}
              tone={
                workOrder.eam.syncStatus === "completed" || workOrder.eam.syncStatus === "closed"
                  ? "success"
                  : workOrder.eam.syncStatus === "pending"
                    ? "warning"
                    : "info"
              }
              compact
            />
          </div>
        ) : null}
        <section className="drawer-section">
          <h3>计划信息</h3>
          <div className="key-value-list">
            <KeyValue
              label="计划开始"
              value={new Date(workOrder.plannedStart).toLocaleString("zh-CN")}
            />
            <KeyValue
              label="完成期限"
              value={new Date(workOrder.deadline).toLocaleString("zh-CN")}
            />
            <KeyValue label="预计时长" value={`${workOrder.estimatedDurationHours} 小时`} />
            <KeyValue label="责任班组" value={workOrder.assignedTeam} />
            <KeyValue label="关联 Mission" value={workOrder.relatedMissionId ?? "—"} mono />
          </div>
        </section>
        <section className="drawer-section">
          <div className="drawer-section__title">
            <h3>任务清单</h3>
            <span className="record-count">
              {completed} / {workOrder.tasks.length}
            </span>
          </div>
          <Progress value={(completed / Math.max(1, workOrder.tasks.length)) * 100} tone="info" />
          {!productionMode && (!isWorkflowWorkOrder || !workflowWritable) ? (
            <div className="ai-generated-note" role="note">
              <ShieldCheck size={15} />
              <span>
                <strong>{isWorkflowWorkOrder ? "D1 暂不可写" : "只读 Demo 工单"}</strong>
                <small>
                  {isWorkflowWorkOrder
                    ? "服务器持久化不可用，任务与执行动作已安全禁用。"
                    : `当前状态为 ${statusLabels[workOrder.status]}；仅 ${WORKFLOW_WORK_ORDER_ID} 接入 WT-023 闭环，任务与执行动作已禁用。`}
                </small>
              </span>
              <StatusBadge value="read-only" label="只读" tone="maintenance" compact />
            </div>
          ) : null}
          <div className="task-checklist">
            {workOrder.tasks.map((task) => (
              <label key={task.id}>
                <input
                  type="checkbox"
                  checked={task.completed}
                  disabled={
                    productionMode ||
                    !isWorkflowWorkOrder ||
                    !workflowWritable ||
                    workOrder.status !== "in-progress"
                  }
                  onChange={() => {
                    if (isWorkflowWorkOrder) onToggleTask(task.id);
                  }}
                />
                <span>
                  <strong>
                    {task.sequence}. {task.title}
                  </strong>
                  {task.completionNote ? <small>{task.completionNote}</small> : null}
                </span>
              </label>
            ))}
          </div>
          {productionMode &&
          nextProductionTask &&
          (workOrder.status === "scheduled" || workOrder.status === "in-progress") ? (
            canCompleteProductionTask ? (
              <FieldTaskCompletionForm
                key={nextProductionTask.id}
                workOrderId={workOrder.id}
                task={nextProductionTask}
                onCompleted={onProductionTaskCompleted}
                authorized={canCompleteProductionTask}
              />
            ) : (
              <div
                className="ai-generated-note"
                role="status"
                data-capability="work_order.task.complete"
              >
                <ShieldCheck size={15} />
                <span>
                  <strong>现场任务只读</strong>
                  <small>提交证据和完成任务需要现场技术员及对应工单范围授权。</small>
                </span>
              </div>
            )
          ) : null}
        </section>
        <section className="drawer-section">
          <h3>安全与 PPE</h3>
          <div className="safety-procedure">
            <span className="safety-procedure__icon">
              <ShieldCheck size={15} />
            </span>
            <div>
              {workOrder.safetyProcedures.map((procedure) => (
                <span key={procedure}>
                  <Check size={11} /> {procedure}
                </span>
              ))}
            </div>
          </div>
          <div className="ppe-chips">
            {workOrder.ppeRequirements.map((item) => (
              <span key={item}>
                <HardHat size={11} /> {item}
              </span>
            ))}
          </div>
        </section>
        <section className="drawer-section">
          <h3>备件与工具</h3>
          <div className="part-list">
            {workOrder.spareParts.map((part) => (
              <div key={part.partNumber}>
                <span>
                  <PackageCheck size={14} />
                </span>
                <div>
                  <strong>{part.name}</strong>
                  <small>
                    {part.partNumber} · 需要 {part.quantity}
                  </small>
                </div>
                <StatusBadge
                  value={part.available >= part.quantity ? "available" : "shortage"}
                  label={part.available >= part.quantity ? `可用 ${part.available}` : "库存不足"}
                  tone={part.available >= part.quantity ? "success" : "critical"}
                  compact
                />
              </div>
            ))}
          </div>
          <div className="tool-chip-grid">
            {workOrder.requiredTools.map((tool) => (
              <span key={tool}>
                <Wrench size={11} /> {tool}
              </span>
            ))}
          </div>
        </section>
        <footer className="detail-drawer__footer">
          <Button variant="secondary" onClick={() => window.print()}>
            <Download size={14} /> 导出 PDF
          </Button>
          <Button variant="secondary" disabled title="资源重新指派将在资源中心完成">
            <UserRound size={14} /> 重新指派
          </Button>
          {productionMode ? (
            <Button variant="primary" disabled>
              <ShieldCheck size={14} />
              {workOrder.status === "completed"
                ? "证据已验证 · 工单已闭环"
                : nextProductionTask
                  ? `按任务 ${nextProductionTask.sequence} 提交现场证据`
                  : `当前状态 · ${statusLabels[workOrder.status]}`}
            </Button>
          ) : !isWorkflowWorkOrder || !workflowWritable ? (
            <Button
              variant="primary"
              disabled
              title={
                isWorkflowWorkOrder
                  ? "D1 持久化当前不可用"
                  : `${workOrder.id} 为只读 Demo 工单，不会修改 WT-023 闭环状态`
              }
            >
              <ShieldCheck size={14} /> 只读 · {statusLabels[workOrder.status]}
            </Button>
          ) : workOrder.status === "scheduled" ? (
            <Button variant="primary" onClick={onStart}>
              <Wrench size={14} /> 开始执行
            </Button>
          ) : workOrder.status === "in-progress" ? (
            <Button variant="primary" onClick={onComplete} disabled={!canComplete}>
              <CheckCircle2 size={14} />{" "}
              {canComplete ? "完成并回写" : `完成任务 ${completed}/${workOrder.tasks.length}`}
            </Button>
          ) : (
            <Button variant="primary" disabled>
              <CheckCircle2 size={14} />{" "}
              {workOrder.status === "completed" ? "闭环已完成" : "等待审批"}
            </Button>
          )}
        </footer>
      </aside>
    </>
  );
}

export function WorkOrderPage({ runtimeMode }: { runtimeMode: "demo" | "production" }) {
  const { can } = useOpenVigilIdentity();
  const canCompleteProductionTask = runtimeMode === "demo" || can("work_order.task.complete");
  const workflow = useDemoWorkflow();
  const [status, setStatus] = useState<WorkOrderStatusFilter>("all");
  const [priority, setPriority] = useState<"all" | WorkOrderPriority>("all");
  const [plannedStart, setPlannedStart] = useState<PlannedStartFilter>("all");
  const [turbineScope, setTurbineScope] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createIntent, setCreateIntent] = useState(false);
  const workOrderQuery = useQuery({
    queryKey: ["work-orders", workflow.serverRevision, runtimeMode],
    queryFn: ({ signal }) =>
      apiGet<{ readonly data: readonly WorkOrder[] }>("/api/work-orders", signal),
    initialData: runtimeMode === "demo" ? { data: workOrders } : undefined,
    retry: false,
    staleTime: 60_000,
  });
  const workOrderState = deriveQueryViewState({
    data: workOrderQuery.data?.data,
    dataUpdatedAt: workOrderQuery.dataUpdatedAt,
    error: workOrderQuery.error,
    isError: workOrderQuery.isError,
    isFetching: workOrderQuery.isFetching,
    isPending: workOrderQuery.isPending,
    isStale: workOrderQuery.isStale,
    isEmpty: (data) => data.length === 0,
    sourceUpdatedAt:
      runtimeMode === "production"
        ? latestValidTimestamp(
            workOrderQuery.data?.data.map((workOrder) => workOrder.updatedAt) ?? [],
          )
        : null,
    staleAfterMs: 60_000,
  });
  const pageHealth = queryRuntimeHealth(workOrderState, "工单台账");

  useEffect(() => {
    const parameters = new URLSearchParams(window.location.search);
    const deepLinkedWorkOrderId = parameters.get("workOrder");
    const deepLinkedTurbineId = parameters.get("turbineId");
    const requestedCreateIntent = parameters.get("intent") === "create";
    const timer = window.setTimeout(() => {
      if (deepLinkedWorkOrderId) setSelectedId(deepLinkedWorkOrderId);
      else if (deepLinkedTurbineId) setTurbineScope(deepLinkedTurbineId.toUpperCase());
      setCreateIntent(requestedCreateIntent);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const displayWorkOrders = useMemo(
    () =>
      runtimeMode === "demo"
        ? overlayClientWorkOrders(workOrderQuery.data?.data ?? [], workflow)
        : (workOrderQuery.data?.data ?? []),
    [runtimeMode, workOrderQuery.data?.data, workflow],
  );
  const [scheduleReference] = useState(() =>
    runtimeMode === "production" ? Date.now() : SNAPSHOT_TIMESTAMP,
  );
  const filtered = useMemo(
    () =>
      displayWorkOrders.filter((item) => {
        const matchesTurbine = turbineScope === null || item.turbineId === turbineScope;
        const matchesStatus =
          status === "all" ||
          (status === "completed-group"
            ? item.status === "completed" || item.status === "closed"
            : item.status === status);
        const matchesPriority = priority === "all" || item.priority === priority;
        const plannedTimestamp = Date.parse(item.plannedStart);
        const matchesPlannedStart =
          plannedStart === "all" ||
          (plannedStart === "due" && plannedTimestamp < scheduleReference) ||
          (plannedStart === "next-24h" &&
            plannedTimestamp >= scheduleReference &&
            plannedTimestamp <= scheduleReference + DAY_MS) ||
          (plannedStart === "next-7d" &&
            plannedTimestamp >= scheduleReference &&
            plannedTimestamp <= scheduleReference + 7 * DAY_MS);

        return matchesTurbine && matchesStatus && matchesPriority && matchesPlannedStart;
      }),
    [displayWorkOrders, plannedStart, priority, scheduleReference, status, turbineScope],
  );
  const featured =
    (runtimeMode === "demo"
      ? displayWorkOrders.find((item) => item.relatedMissionId === featuredMission.id)
      : undefined) ?? displayWorkOrders[0];
  const selected =
    displayWorkOrders.find((item) => item.id === selectedId) ??
    (runtimeMode === "demo"
      ? historicalWorkOrders.find((item) => item.id === selectedId)
      : undefined) ??
    null;
  const counts = {
    pending: displayWorkOrders.filter((item) => item.status === "pending-approval").length,
    scheduled: displayWorkOrders.filter((item) => item.status === "scheduled").length,
    progress: displayWorkOrders.filter((item) => item.status === "in-progress").length,
    completed: displayWorkOrders.filter(
      (item) => item.status === "completed" || item.status === "closed",
    ).length,
  };
  const summaryStatus =
    runtimeMode === "production" ? (featured?.status ?? "draft") : workflow.workOrderStatus;
  const summaryCompletedTaskCount =
    runtimeMode === "production"
      ? (featured?.tasks.filter((task) => task.completed).length ?? 0)
      : workflow.completedTaskIds.length;
  const hasFilters =
    turbineScope !== null || status !== "all" || priority !== "all" || plannedStart !== "all";

  const applyStatus = (nextStatus: WorkOrderStatusFilter) => {
    setStatus(nextStatus);
  };
  const queryBlocked =
    workOrderState.lifecycle === "initial-loading" || workOrderState.lifecycle === "error-no-data";

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/work-orders" pageHealth={pageHealth}>
      <PageHeader
        eyebrow="运维执行"
        title="工单中心"
        description="从 AI 决策到人员、资源、安全流程和现场执行的闭环管理"
        breadcrumb={["运维执行", "工单中心"]}
        meta={
          <>
            <RuntimeHealthBadge health={pageHealth} />
            {workOrderState.hasData && featured ? (
              <StatusBadge
                value={summaryStatus}
                label={
                  summaryStatus === "in-progress"
                    ? "执行中"
                    : summaryStatus === "pending-approval"
                      ? "等待审批"
                      : summaryStatus === "scheduled"
                        ? "已排程"
                        : summaryStatus === "completed"
                          ? "已完成"
                          : "草案"
                }
                tone={
                  summaryStatus === "completed"
                    ? "success"
                    : summaryStatus === "in-progress"
                      ? "info"
                      : "maintenance"
                }
                pulse={summaryStatus === "in-progress"}
              />
            ) : null}
            <span className="page-meta-text">
              {workOrderState.hasData
                ? `${counts.pending} 待审批 · ${counts.scheduled} 已排程 · ${counts.completed} 已完成`
                : "等待工单权威台账"}
            </span>
          </>
        }
        actions={
          <Button variant="primary" disabled title="工单只能由已审批 Mission 的受控工作流创建">
            <Plus size={15} /> 创建工单
          </Button>
        }
      />

      {queryBlocked ? (
        <QueryStateNotice
          state={workOrderState}
          target="工单台账"
          impact="工单数量、排程状态、任务进度与筛选结果"
          onRetry={() => void workOrderQuery.refetch()}
        />
      ) : (
        <>
          <QueryStateNotice
            state={workOrderState}
            target="工单台账"
            impact="现有工单内容"
            onRetry={() => void workOrderQuery.refetch()}
          />

          {createIntent ? (
            <section className="controlled-entry-note" role="status">
              <ShieldCheck size={16} />
              <span>
                <strong>已打开受控工单创建入口</strong>
                <small>
                  {turbineScope ? `资产范围：${turbineScope}。` : "未指定资产范围。"}{" "}
                  {runtimeMode === "production"
                    ? "生产工单只能由已审批 Mission 的审批门禁原子创建，并同时预留资源与天气窗口。"
                    : "演示模式只展示可审计的只读工作台，不会假创建工单。"}
                </small>
              </span>
              <Button
                variant="ghost"
                onClick={() => setCreateIntent(false)}
                aria-label="关闭受控入口提示"
              >
                <X size={14} />
              </Button>
            </section>
          ) : null}

          {featured ? (
            <section className="featured-work-order">
              <div className="featured-work-order__tag">
                <Bot size={14} />
                <span>
                  <small>AI 生成 · {featured.relatedMissionId ?? "无关联 Mission"}</small>
                  <strong>
                    {runtimeMode === "production"
                      ? featured.issue
                      : summaryStatus === "completed"
                        ? "WT-023 检查已完成，结果已回写"
                        : summaryStatus === "in-progress"
                          ? "WT-023 主轴承检查正在执行"
                          : "WT-023 主轴承检查工单已准备"}
                  </strong>
                </span>
              </div>
              <div className="featured-work-order__facts">
                <span>
                  <small>建议窗口</small>
                  <strong>
                    {new Date(featured.plannedStart).toLocaleString("zh-CN", {
                      month: "numeric",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: false,
                    })}
                  </strong>
                </span>
                <span>
                  <small>任务进度</small>
                  <strong>
                    {summaryCompletedTaskCount} / {featured.tasks.length}
                  </strong>
                </span>
                <span>
                  <small>闭环状态</small>
                  <strong
                    className={
                      summaryStatus === "completed" || workflow.knowledgeCaseId
                        ? "success-text"
                        : "warning-text"
                    }
                  >
                    {summaryStatus === "completed" || workflow.knowledgeCaseId
                      ? "案例已沉淀"
                      : summaryStatus === "draft" || summaryStatus === "pending-approval"
                        ? "等待审批"
                        : summaryStatus === "scheduled"
                          ? "已排程"
                          : summaryStatus === "in-progress"
                            ? "现场执行中"
                            : summaryStatus === "paused"
                              ? "执行已暂停"
                              : "等待验证"}
                  </strong>
                </span>
              </div>
              <Button variant="primary" onClick={() => setSelectedId(featured.id)}>
                {summaryStatus === "completed" ? "查看结果" : "打开工单"} <ArrowRight size={14} />
              </Button>
            </section>
          ) : null}

          <section className="work-order-summary">
            <button
              onClick={() =>
                applyStatus(status === "pending-approval" ? "all" : "pending-approval")
              }
              className={cn(status === "pending-approval" && "active")}
              aria-pressed={status === "pending-approval"}
            >
              <span className="wo-summary-icon wo-summary-icon--warning">
                <ShieldCheck size={16} />
              </span>
              <span>
                <small>等待审批</small>
                <strong>{counts.pending}</strong>
              </span>
            </button>
            <button
              onClick={() => applyStatus(status === "scheduled" ? "all" : "scheduled")}
              className={cn(status === "scheduled" && "active")}
              aria-pressed={status === "scheduled"}
            >
              <span className="wo-summary-icon wo-summary-icon--maintenance">
                <CalendarClock size={16} />
              </span>
              <span>
                <small>已排程</small>
                <strong>{counts.scheduled}</strong>
              </span>
            </button>
            <button
              onClick={() => applyStatus(status === "in-progress" ? "all" : "in-progress")}
              className={cn(status === "in-progress" && "active")}
              aria-pressed={status === "in-progress"}
            >
              <span className="wo-summary-icon wo-summary-icon--info">
                <Wrench size={16} />
              </span>
              <span>
                <small>执行中</small>
                <strong>{counts.progress}</strong>
              </span>
            </button>
            <button
              onClick={() => applyStatus(status === "completed-group" ? "all" : "completed-group")}
              className={cn(status === "completed-group" && "active")}
              aria-pressed={status === "completed-group"}
            >
              <span className="wo-summary-icon wo-summary-icon--success">
                <CheckCircle2 size={16} />
              </span>
              <span>
                <small>已完成</small>
                <strong>{counts.completed}</strong>
              </span>
            </button>
          </section>

          <DataTable
            bulkActions={[
              {
                label: "打开首个所选工单",
                onActivate: (rows) => {
                  const workOrder = rows[0];
                  if (workOrder) setSelectedId(workOrder.id);
                },
              },
            ]}
            columns={workOrderColumns}
            csvExport={workOrderCsvExport}
            data={filtered}
            emptyMessage={
              displayWorkOrders.length === 0
                ? "当前范围内确实没有工单；权威台账已成功返回空结果。"
                : "筛选结果为空；请调整条件或使用“清除筛选”。"
            }
            getRowId={workOrderRowId}
            initialSorting={[{ id: "plannedStart", desc: false }]}
            onRowActivate={(workOrder) => setSelectedId(workOrder.id)}
            pageSize={6}
            searchPlaceholder="搜索工单、机组或班组…"
            searchTextForRow={workOrderSearchText}
            selectedRowId={selectedId ?? featured?.id}
            filterControls={
              <>
                <Button
                  variant="secondary"
                  onClick={() => applyStatus(nextOption(statusFilterOptions, status))}
                  aria-label={`状态筛选：${statusFilterLabels[status]}，点击切换`}
                  title="点击循环切换状态筛选"
                >
                  <ClipboardCheck size={14} /> {statusFilterLabels[status]}{" "}
                  <ChevronDown size={12} />
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setPriority(nextOption(priorityFilterOptions, priority))}
                  aria-label={`优先级筛选：${priorityFilterLabels[priority]}，点击切换`}
                  title="点击循环切换优先级筛选"
                >
                  <Filter size={14} /> {priorityFilterLabels[priority]} <ChevronDown size={12} />
                </Button>
                <Button
                  variant="secondary"
                  onClick={() =>
                    setPlannedStart(nextOption(plannedStartFilterOptions, plannedStart))
                  }
                  aria-label={`计划开始筛选：${plannedStartFilterLabels[plannedStart]}，点击切换`}
                  title="点击循环切换计划开始时间筛选"
                >
                  <CalendarClock size={14} /> {plannedStartFilterLabels[plannedStart]}{" "}
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
                    setStatus("all");
                    setPriority("all");
                    setPlannedStart("all");
                    setTurbineScope(null);
                  }}
                >
                  清除筛选
                </Button>
              </>
            }
          />
          {selected ? (
            <WorkOrderDrawer
              workOrder={selected}
              runtimeMode={runtimeMode}
              isWorkflowWorkOrder={selected.id === WORKFLOW_WORK_ORDER_ID}
              workflowWritable={workflow.writable}
              onClose={() => setSelectedId(null)}
              onToggleTask={(taskId) => {
                if (selected.id !== WORKFLOW_WORK_ORDER_ID) return;
                workflow.dispatch({
                  type: "toggle-task",
                  taskId,
                  timestamp: new Date().toISOString(),
                  actor: "海维二组",
                });
              }}
              onStart={() => {
                if (selected.id !== WORKFLOW_WORK_ORDER_ID) return;
                workflow.dispatch({
                  type: "start-work-order",
                  timestamp: new Date().toISOString(),
                  actor: "海维二组",
                });
              }}
              onComplete={() => {
                if (selected.id !== WORKFLOW_WORK_ORDER_ID) return;
                workflow.dispatch({
                  type: "complete-work-order",
                  timestamp: new Date().toISOString(),
                  actor: "林工",
                });
              }}
              onProductionTaskCompleted={async () => {
                await workOrderQuery.refetch();
              }}
              canComplete={canCompleteFeaturedWorkOrder(workflow)}
              canCompleteProductionTask={canCompleteProductionTask}
            />
          ) : null}
        </>
      )}
    </AppShell>
  );
}
