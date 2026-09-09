"use client";

import { useEffect, useMemo, useState } from "react";
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
import { PageHeader } from "@/components/layout/page-header";
import { Button, KeyValue, Progress } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { featuredMission, historicalWorkOrders, workOrders } from "@/lib";
import type { WorkOrder, WorkOrderPriority, WorkOrderStatus } from "@/lib/types";
import { canCompleteFeaturedWorkOrder } from "@/lib/demo-workflow";
import { overlayClientWorkOrders } from "@/lib/client-workflow-overlays";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { cn } from "@/lib/utils";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";

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
    header: "Work Order ID",
    cell: ({ row }) => <strong className="mono">{row.original.id}</strong>,
  },
  {
    accessorKey: "turbineId",
    header: "Wind Turbine",
    cell: ({ row }) => <span className="mono">{row.original.turbineId}</span>,
  },
  {
    accessorKey: "issue",
    header: "Issue",
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
    header: "Priority",
    cell: ({ row }) => (
      <StatusBadge
        value={row.original.priority}
        label={row.original.priority.toUpperCase()}
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
    header: "Status",
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
    header: "Assigned Team",
    cell: ({ row }) => (
      <span className="team-cell">
        <UserRound size={13} /> {row.original.assignedTeam}
      </span>
    ),
  },
  {
    accessorKey: "createdByAgentId",
    header: "Created By",
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
    header: "Related Mission",
    cell: ({ row }) => <span className="mono">{row.original.relatedMissionId ?? "—"}</span>,
  },
  {
    accessorKey: "plannedStart",
    header: "Planned Start",
    cell: ({ row }) => new Date(row.original.plannedStart).toLocaleDateString("zh-CN"),
  },
  {
    accessorKey: "deadline",
    header: "Deadline",
    cell: ({ row }) => new Date(row.original.deadline).toLocaleDateString("zh-CN"),
  },
];

const workOrderCsvExport = {
  filename: "windops-work-orders-2026-08-13.csv",
  columns: [
    { label: "Work Order ID", value: (workOrder: WorkOrder) => workOrder.id },
    { label: "Wind Turbine", value: (workOrder: WorkOrder) => workOrder.turbineId },
    { label: "Issue", value: (workOrder: WorkOrder) => workOrder.issue },
    { label: "Priority", value: (workOrder: WorkOrder) => workOrder.priority },
    { label: "Status", value: (workOrder: WorkOrder) => statusLabels[workOrder.status] },
    { label: "Assigned Team", value: (workOrder: WorkOrder) => workOrder.assignedTeam },
    { label: "Related Mission", value: (workOrder: WorkOrder) => workOrder.relatedMissionId },
    { label: "Planned Start", value: (workOrder: WorkOrder) => workOrder.plannedStart },
    { label: "Deadline", value: (workOrder: WorkOrder) => workOrder.deadline },
  ],
} as const;

const workOrderSearchText = (workOrder: WorkOrder): string =>
  `${workOrder.id} ${workOrder.turbineId} ${workOrder.issue} ${workOrder.description} ${workOrder.assignedTeam} ${workOrder.relatedMissionId ?? ""}`;

const workOrderRowId = (workOrder: WorkOrder): string => workOrder.id;

function WorkOrderDrawer({
  workOrder,
  isWorkflowWorkOrder,
  workflowWritable,
  onClose,
  onToggleTask,
  onStart,
  onComplete,
  canComplete,
}: {
  workOrder: WorkOrder;
  isWorkflowWorkOrder: boolean;
  workflowWritable: boolean;
  onClose: () => void;
  onToggleTask: (taskId: string) => void;
  onStart: () => void;
  onComplete: () => void;
  canComplete: boolean;
}) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose);
  const completed = workOrder.tasks.filter((task) => task.completed).length;
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
            <span className="eyebrow">WORK ORDER</span>
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
            label={workOrder.priority.toUpperCase()}
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
              <strong>由 Work Order Agent 自动生成</strong>
              <small>来源 {workOrder.relatedMissionId} · 已通过 Safety Review</small>
            </span>
            <StatusBadge value="approved" label="AI VERIFIED" tone="info" compact />
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
          {!isWorkflowWorkOrder || !workflowWritable ? (
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
              <StatusBadge value="read-only" label="READ ONLY" tone="maintenance" compact />
            </div>
          ) : null}
          <div className="task-checklist">
            {workOrder.tasks.map((task) => (
              <label key={task.id}>
                <input
                  type="checkbox"
                  checked={task.completed}
                  disabled={
                    !isWorkflowWorkOrder || !workflowWritable || workOrder.status !== "in-progress"
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
          {!isWorkflowWorkOrder || !workflowWritable ? (
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

export function WorkOrderPage() {
  const workflow = useDemoWorkflow();
  const [status, setStatus] = useState<WorkOrderStatusFilter>("all");
  const [priority, setPriority] = useState<"all" | WorkOrderPriority>("all");
  const [plannedStart, setPlannedStart] = useState<PlannedStartFilter>("all");
  const [turbineScope, setTurbineScope] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createIntent, setCreateIntent] = useState(false);

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
    () => overlayClientWorkOrders(workOrders, workflow),
    [workflow],
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
          (plannedStart === "due" && plannedTimestamp < SNAPSHOT_TIMESTAMP) ||
          (plannedStart === "next-24h" &&
            plannedTimestamp >= SNAPSHOT_TIMESTAMP &&
            plannedTimestamp <= SNAPSHOT_TIMESTAMP + DAY_MS) ||
          (plannedStart === "next-7d" &&
            plannedTimestamp >= SNAPSHOT_TIMESTAMP &&
            plannedTimestamp <= SNAPSHOT_TIMESTAMP + 7 * DAY_MS);

        return matchesTurbine && matchesStatus && matchesPriority && matchesPlannedStart;
      }),
    [displayWorkOrders, plannedStart, priority, status, turbineScope],
  );
  const featured =
    displayWorkOrders.find((item) => item.relatedMissionId === featuredMission.id) ??
    displayWorkOrders[0];
  const selected =
    displayWorkOrders.find((item) => item.id === selectedId) ??
    historicalWorkOrders.find((item) => item.id === selectedId) ??
    null;
  const counts = {
    pending: displayWorkOrders.filter((item) => item.status === "pending-approval").length,
    scheduled: displayWorkOrders.filter((item) => item.status === "scheduled").length,
    progress: displayWorkOrders.filter((item) => item.status === "in-progress").length,
    completed: displayWorkOrders.filter(
      (item) => item.status === "completed" || item.status === "closed",
    ).length,
  };
  const hasFilters =
    turbineScope !== null || status !== "all" || priority !== "all" || plannedStart !== "all";

  const applyStatus = (nextStatus: WorkOrderStatusFilter) => {
    setStatus(nextStatus);
  };

  return (
    <AppShell activePath="/work-orders">
      <PageHeader
        eyebrow="运维执行"
        title="工单中心"
        description="从 AI 决策到人员、资源、安全流程和现场执行的闭环管理"
        breadcrumb={["运维执行", "工单中心"]}
        meta={
          <>
            <StatusBadge
              value={workflow.workOrderStatus}
              label={workflow.workOrderStatus.replaceAll("-", " ").toUpperCase()}
              tone={
                workflow.workOrderStatus === "completed"
                  ? "success"
                  : workflow.workOrderStatus === "in-progress"
                    ? "info"
                    : "maintenance"
              }
              pulse={workflow.workOrderStatus === "in-progress"}
            />
            <span className="page-meta-text">
              {counts.pending} 待审批 · {counts.scheduled} 已排程 · {counts.completed} 已完成
            </span>
          </>
        }
        actions={
          <Button variant="primary" disabled title="当前演示环境不写入新工单">
            <Plus size={15} /> 创建工单
          </Button>
        }
      />

      {createIntent ? (
        <section className="controlled-entry-note" role="status">
          <ShieldCheck size={16} />
          <span>
            <strong>已打开受控工单创建入口</strong>
            <small>
              {turbineScope ? `资产范围：${turbineScope}。` : "未指定资产范围。"}{" "}
              当前没有通用工单写入 API；页面仅展示可审计的只读工作台，不会假创建工单。
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
              <small>AI GENERATED · MISSION-2026-0823</small>
              <strong>
                {workflow.workOrderStatus === "completed"
                  ? "WT-023 检查已完成，结果已回写"
                  : workflow.workOrderStatus === "in-progress"
                    ? "WT-023 主轴承检查正在执行"
                    : "WT-023 主轴承检查工单已准备"}
              </strong>
            </span>
          </div>
          <div className="featured-work-order__facts">
            <span>
              <small>建议窗口</small>
              <strong>8月14日 · 08:00</strong>
            </span>
            <span>
              <small>任务进度</small>
              <strong>
                {workflow.completedTaskIds.length} / {featured.tasks.length}
              </strong>
            </span>
            <span>
              <small>闭环状态</small>
              <strong className={workflow.knowledgeCaseId ? "success-text" : "warning-text"}>
                {workflow.knowledgeCaseId
                  ? "案例已沉淀"
                  : workflow.workOrderStatus === "draft" ||
                      workflow.workOrderStatus === "pending-approval"
                    ? "等待审批"
                    : workflow.workOrderStatus === "scheduled"
                      ? "已排程"
                      : workflow.workOrderStatus === "in-progress"
                        ? "现场执行中"
                        : workflow.workOrderStatus === "paused"
                          ? "执行已暂停"
                          : "等待验证"}
              </strong>
            </span>
          </div>
          <Button variant="primary" onClick={() => setSelectedId(featured.id)}>
            {workflow.workOrderStatus === "completed" ? "查看结果" : "打开工单"}{" "}
            <ArrowRight size={14} />
          </Button>
        </section>
      ) : null}

      <section className="work-order-summary">
        <button
          onClick={() => applyStatus(status === "pending-approval" ? "all" : "pending-approval")}
          className={cn(status === "pending-approval" && "active")}
          aria-pressed={status === "pending-approval"}
        >
          <span className="wo-summary-icon wo-summary-icon--warning">
            <ShieldCheck size={16} />
          </span>
          <span>
            <small>PENDING APPROVAL</small>
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
            <small>SCHEDULED</small>
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
            <small>IN PROGRESS</small>
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
            <small>COMPLETED</small>
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
        emptyMessage="没有符合当前筛选条件的工单"
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
              <ClipboardCheck size={14} /> {statusFilterLabels[status]} <ChevronDown size={12} />
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
              onClick={() => setPlannedStart(nextOption(plannedStartFilterOptions, plannedStart))}
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
          canComplete={canCompleteFeaturedWorkOrder(workflow)}
        />
      ) : null}
    </AppShell>
  );
}
