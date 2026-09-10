"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  TriangleAlert as AlarmTriangle,
  Bot,
  ChevronDown,
  Clock3,
  Filter,
  ShieldAlert,
  X,
} from "lucide-react";
import { DataTable } from "@/components/data-display/data-table";
import { AppShell } from "@/components/layout/app-shell";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { windFarm } from "@/lib/farm-data";
import { alarms } from "@/lib/operations-data";
import type { Alarm, AlarmSeverity } from "@/lib/types";
import { apiGet, apiPost } from "@/lib/api-client";
import { useRealtimeChannel } from "@/lib/use-realtime-channel";
import { useProductionEvents } from "@/lib/use-production-events";
import { asText, cn } from "@/lib/utils";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { overlayClientAlarms } from "@/lib/client-workflow-overlays";
import { AlarmDrawer } from "./alarm-center-drawer";
import {
  alarmColumns,
  alarmCsvExport,
  alarmRowId,
  alarmSearchText,
  productionAlarmEventTypes,
} from "./alarm-center-support";

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
