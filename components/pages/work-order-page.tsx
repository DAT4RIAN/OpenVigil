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
  MoreHorizontal,
  PackageCheck,
  Plus,
  Search,
  ShieldCheck,
  UserRound,
  Wrench,
  X,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, KeyValue, Progress } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { featuredMission, historicalWorkOrders, workOrders } from "@/lib";
import type { WorkOrder, WorkOrderPriority, WorkOrderStatus } from "@/lib/types";
import { canCompleteFeaturedWorkOrder } from "@/lib/demo-workflow";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { cn } from "@/lib/utils";

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

const PAGE_SIZE = 6;
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

function csvCell(value: string | number) {
  return `"${String(value).replaceAll('"', '""')}"`;
}

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
  const completed = workOrder.tasks.filter((task) => task.completed).length;
  return (
    <>
      <button className="drawer-backdrop" onClick={onClose} aria-label="关闭工单详情" />
      <aside
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
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<WorkOrderStatusFilter>("all");
  const [priority, setPriority] = useState<"all" | WorkOrderPriority>("all");
  const [plannedStart, setPlannedStart] = useState<PlannedStartFilter>("all");
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    const parameters = new URLSearchParams(window.location.search);
    const deepLinkedWorkOrderId = parameters.get("workOrder");
    const deepLinkedTurbineId = parameters.get("turbineId");
    const timer = window.setTimeout(() => {
      if (deepLinkedWorkOrderId) setSelectedId(deepLinkedWorkOrderId);
      else if (deepLinkedTurbineId) setQuery(deepLinkedTurbineId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const displayWorkOrders = useMemo(
    () =>
      workOrders.map((item) =>
        item.id === WORKFLOW_WORK_ORDER_ID
          ? {
              ...item,
              status: workflow.workOrderStatus,
              tasks: item.tasks.map((task) => ({
                ...task,
                completed: workflow.completedTaskIds.includes(task.id),
                completionNote: workflow.completedTaskIds.includes(task.id)
                  ? "已按作业指导书完成并记录"
                  : null,
              })),
            }
          : item,
      ),
    [workflow.completedTaskIds, workflow.workOrderStatus],
  );
  const filtered = useMemo(
    () =>
      displayWorkOrders.filter((item) => {
        const normalizedQuery = query.trim().toLowerCase();
        const matchesSearch = `${item.id} ${item.turbineId} ${item.issue} ${item.assignedTeam}`
          .toLowerCase()
          .includes(normalizedQuery);
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

        return matchesSearch && matchesStatus && matchesPriority && matchesPlannedStart;
      }),
    [displayWorkOrders, plannedStart, priority, query, status],
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
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const pageRowIds = pageRows.map((item) => item.id);
  const selectedFilteredCount = selectedIds.filter((id) =>
    filtered.some((item) => item.id === id),
  ).length;
  const allPageRowsSelected =
    pageRowIds.length > 0 && pageRowIds.every((id) => selectedIds.includes(id));
  const hasFilters =
    query.trim().length > 0 || status !== "all" || priority !== "all" || plannedStart !== "all";

  const resetResultState = () => {
    setPage(1);
    setSelectedIds([]);
  };

  const applyStatus = (nextStatus: WorkOrderStatusFilter) => {
    setStatus(nextStatus);
    resetResultState();
  };

  const toggleRow = (id: string) => {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((selectedId) => selectedId !== id) : [...current, id],
    );
  };

  const toggleCurrentPage = () => {
    setSelectedIds((current) => {
      if (pageRowIds.every((id) => current.includes(id))) {
        return current.filter((id) => !pageRowIds.includes(id));
      }
      return [...new Set([...current, ...pageRowIds])];
    });
  };

  const exportFilteredWorkOrders = () => {
    const header = [
      "Work Order ID",
      "Wind Turbine",
      "Issue",
      "Priority",
      "Status",
      "Assigned Team",
      "Related Mission",
      "Planned Start",
      "Deadline",
    ];
    const rows = filtered.map((item) => [
      item.id,
      item.turbineId,
      item.issue,
      item.priority,
      statusLabels[item.status],
      item.assignedTeam,
      item.relatedMissionId ?? "",
      item.plannedStart,
      item.deadline,
    ]);
    const csv = [header, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `windops-work-orders-${new Date(SNAPSHOT_TIMESTAMP).toISOString().slice(0, 10)}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
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
          <>
            <Button
              variant="secondary"
              onClick={exportFilteredWorkOrders}
              disabled={filtered.length === 0}
            >
              <Download size={15} /> 导出
            </Button>
            <Button variant="primary" disabled title="当前演示环境不写入新工单">
              <Plus size={15} /> 创建工单
            </Button>
          </>
        }
      />

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
                {workflow.knowledgeCaseId ? "案例已沉淀" : "等待执行"}
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

      <section className="data-toolbar">
        <div className="search-field">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              resetResultState();
            }}
            placeholder="搜索工单、机组或班组…"
            aria-label="搜索工单"
          />
        </div>
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
          onClick={() => {
            setPriority(nextOption(priorityFilterOptions, priority));
            resetResultState();
          }}
          aria-label={`优先级筛选：${priorityFilterLabels[priority]}，点击切换`}
          title="点击循环切换优先级筛选"
        >
          <Filter size={14} /> {priorityFilterLabels[priority]} <ChevronDown size={12} />
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            setPlannedStart(nextOption(plannedStartFilterOptions, plannedStart));
            resetResultState();
          }}
          aria-label={`计划开始筛选：${plannedStartFilterLabels[plannedStart]}，点击切换`}
          title="点击循环切换计划开始时间筛选"
        >
          <CalendarClock size={14} /> {plannedStartFilterLabels[plannedStart]}{" "}
          <ChevronDown size={12} />
        </Button>
        <span className="toolbar-result">{filtered.length} Work Orders</span>
        <Button
          variant="ghost"
          disabled={!hasFilters}
          onClick={() => {
            setStatus("all");
            setPriority("all");
            setPlannedStart("all");
            setQuery("");
            resetResultState();
          }}
        >
          清除筛选
        </Button>
      </section>

      <Card className="data-table-card">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    aria-label="选择当前页所有工单"
                    checked={allPageRowsSelected}
                    disabled={pageRows.length === 0}
                    onChange={toggleCurrentPage}
                  />
                </th>
                <th>Work Order ID</th>
                <th>Wind Turbine</th>
                <th>Issue</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Assigned Team</th>
                <th>Created By</th>
                <th>Related Mission</th>
                <th>Planned Start</th>
                <th>Deadline</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {pageRows.map((item) => (
                <tr
                  className={cn(
                    item.id === featured?.id && "row-featured",
                    selectedIds.includes(item.id) && "selected",
                  )}
                  key={item.id}
                  onClick={() => setSelectedId(item.id)}
                >
                  <td onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`选择 ${item.id}`}
                      checked={selectedIds.includes(item.id)}
                      onChange={() => toggleRow(item.id)}
                    />
                  </td>
                  <td>
                    <strong className="mono">{item.id}</strong>
                  </td>
                  <td className="mono">{item.turbineId}</td>
                  <td>
                    <span className="alarm-title-cell">
                      <strong>{item.issue}</strong>
                      <small>{item.description}</small>
                    </span>
                  </td>
                  <td>
                    <StatusBadge
                      value={item.priority}
                      label={item.priority.toUpperCase()}
                      tone={
                        item.priority === "critical"
                          ? "critical"
                          : item.priority === "high"
                            ? "warning"
                            : "info"
                      }
                      compact
                    />
                  </td>
                  <td>
                    <StatusBadge
                      value={item.status}
                      label={statusLabels[item.status]}
                      tone={
                        item.status === "completed" || item.status === "closed"
                          ? "success"
                          : item.status === "in-progress"
                            ? "info"
                            : item.status === "scheduled"
                              ? "maintenance"
                              : "warning"
                      }
                      compact
                    />
                  </td>
                  <td>
                    <span className="team-cell">
                      <UserRound size={13} /> {item.assignedTeam}
                    </span>
                  </td>
                  <td>
                    {item.createdByAgentId ? (
                      <span className="ai-status-cell">
                        <Bot size={13} /> AI Agent
                      </span>
                    ) : (
                      "人工创建"
                    )}
                  </td>
                  <td className="mono">{item.relatedMissionId ?? "—"}</td>
                  <td>{new Date(item.plannedStart).toLocaleDateString("zh-CN")}</td>
                  <td>{new Date(item.deadline).toLocaleDateString("zh-CN")}</td>
                  <td>
                    <Button size="icon" variant="ghost" aria-label="更多">
                      <MoreHorizontal size={14} />
                    </Button>
                  </td>
                </tr>
              ))}
              {pageRows.length === 0 ? (
                <tr>
                  <td colSpan={12} style={{ padding: "32px", textAlign: "center" }}>
                    没有符合当前筛选条件的工单
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="table-pagination">
          <span>
            已选择 {selectedFilteredCount} / {filtered.length} 行
          </span>
          <span>
            第 {currentPage} 页，共 {pageCount} 页
          </span>
          <div>
            <Button
              size="sm"
              variant="secondary"
              disabled={currentPage <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              上一页
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={currentPage >= pageCount}
              onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
            >
              下一页
            </Button>
          </div>
        </div>
      </Card>
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
