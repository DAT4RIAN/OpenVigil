"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Bot,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Filter,
  Plus,
  ShieldCheck,
  Wrench,
  X,
} from "lucide-react";
import { DataTable } from "@/components/data-display/data-table";
import { AppShell } from "@/components/layout/app-shell";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/primitives";
import { QueryStateNotice, RuntimeHealthBadge } from "@/components/ui/query-state";
import { StatusBadge } from "@/components/data-display/status-badge";
import { historicalWorkOrders } from "@/lib/archive-data";
import { featuredMission, workOrders } from "@/lib/operations-data";
import type { WorkOrder, WorkOrderPriority } from "@/lib/types";
import { canCompleteFeaturedWorkOrder } from "@/lib/demo-workflow";
import { overlayClientWorkOrders } from "@/lib/client-workflow-overlays";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { cn } from "@/lib/utils";
import { apiGet } from "@/lib/api-client";
import { deriveQueryViewState, latestValidTimestamp, queryRuntimeHealth } from "@/lib/query-state";
import { WorkOrderDrawer } from "./work-order-drawer";
import {
  DAY_MS,
  SNAPSHOT_TIMESTAMP,
  WORKFLOW_WORK_ORDER_ID,
  nextOption,
  plannedStartFilterLabels,
  plannedStartFilterOptions,
  priorityFilterLabels,
  priorityFilterOptions,
  statusFilterLabels,
  statusFilterOptions,
  workOrderColumns,
  workOrderCsvExport,
  workOrderRowId,
  workOrderSearchText,
  type PlannedStartFilter,
  type WorkOrderStatusFilter,
} from "./work-order-support";

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
