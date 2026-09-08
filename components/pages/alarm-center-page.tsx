"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  TriangleAlert as AlarmTriangle,
  ArrowRight,
  BookOpenText,
  Bot,
  Check,
  ChevronDown,
  Clock3,
  Download,
  FileSearch,
  Filter,
  History,
  MoreHorizontal,
  Search,
  ShieldAlert,
  Thermometer,
  UserRound,
  Wrench,
  X,
} from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, KeyValue } from "@/components/ui/primitives";
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
import { useRealtimeChannel } from "@/lib/use-realtime-channel";
import { cn } from "@/lib/utils";

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
  const [selectedAlarmId, setSelectedAlarmId] = useState<string | null>(null);
  const [severity, setSeverity] = useState<"all" | AlarmSeverity>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | Alarm["status"]>("all");
  const [timeWindowHours, setTimeWindowHours] = useState<0 | 1 | 6 | 24>(0);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<readonly string[]>([]);
  const [acknowledgedIds, setAcknowledgedIds] = useState<readonly string[]>([]);
  const [assignmentOverrides, setAssignmentOverrides] = useState<
    Readonly<Record<string, string | null>>
  >({});
  useEffect(() => {
    const parameters = new URLSearchParams(window.location.search);
    const turbineId = parameters.get("turbineId")?.toUpperCase();
    const alarmId = parameters.get("alarm")?.toUpperCase();
    const timer = window.setTimeout(() => {
      if (turbineId) setQuery(turbineId);
      if (alarmId && alarms.some((alarm) => alarm.id === alarmId)) setSelectedAlarmId(alarmId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const alarmStream = useRealtimeChannel("alarms");
  const visibleAlarms = useMemo(
    () =>
      alarms.map((alarm) => {
        const isLocallyAcknowledged =
          acknowledgedIds.includes(alarm.id) && alarm.status === "active";
        const hasAssignmentOverride = Object.prototype.hasOwnProperty.call(
          assignmentOverrides,
          alarm.id,
        );
        return {
          ...alarm,
          ...(isLocallyAcknowledged
            ? {
                status: "acknowledged" as const,
                acknowledgedAt: alarm.acknowledgedAt ?? windFarm.lastUpdatedAt,
              }
            : {}),
          ...(hasAssignmentOverride ? { assignee: assignmentOverrides[alarm.id] ?? null } : {}),
        };
      }),
    [acknowledgedIds, assignmentOverrides],
  );
  const selectedAlarm = visibleAlarms.find((alarm) => alarm.id === selectedAlarmId) ?? null;
  const featuredAlarm =
    visibleAlarms.find((alarm) => alarm.turbineId === "WT-023") ?? visibleAlarms[0];
  const filtered = useMemo(
    () =>
      visibleAlarms.filter(
        (alarm) =>
          (severity === "all" || alarm.severity === severity) &&
          (statusFilter === "all" || alarm.status === statusFilter) &&
          (timeWindowHours === 0 ||
            new Date(windFarm.lastUpdatedAt).getTime() - new Date(alarm.triggeredAt).getTime() <=
              timeWindowHours * 3_600_000) &&
          `${alarm.id} ${alarm.code} ${alarm.title} ${alarm.turbineId}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [query, severity, statusFilter, timeWindowHours, visibleAlarms],
  );
  const pageSize = 8;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
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

  const toggleSelection = (id: string) =>
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((candidate) => candidate !== id) : [...current, id],
    );

  function exportCsv() {
    const rows = [
      "id,severity,turbine,subsystem,code,title,triggered_at,status,ai_status,assignee",
      ...filtered.map((alarm) =>
        [
          alarm.id,
          alarm.severity,
          alarm.turbineId,
          alarm.subsystem,
          alarm.code,
          JSON.stringify(alarm.title),
          alarm.triggeredAt,
          alarm.status,
          alarm.aiStatus,
          JSON.stringify(alarm.assignee ?? ""),
        ].join(","),
      ),
    ];
    const url = URL.createObjectURL(
      new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "windops-alarms.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

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
            </span>
          </>
        }
        actions={
          <>
            <Button variant="secondary" onClick={exportCsv}>
              <Download size={15} /> 导出
            </Button>
            <Button
              variant="primary"
              disabled={!selectedIds.length}
              onClick={() => {
                setAcknowledgedIds((current) => [...new Set([...current, ...selectedIds])]);
                setSelectedIds([]);
              }}
            >
              <Check size={15} /> 批量确认 {selectedIds.length || ""}
            </Button>
          </>
        }
      />

      <section className="alarm-summary-grid">
        <button
          onClick={() => {
            setSeverity("critical");
            setPage(0);
          }}
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
          onClick={() => {
            setSeverity("major");
            setPage(0);
          }}
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
          onClick={() => {
            setSeverity("warning");
            setPage(0);
          }}
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
        <button
          onClick={() => {
            setSeverity("all");
            setPage(0);
          }}
          className={cn(severity === "all" && "active")}
        >
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

      <section className="data-toolbar">
        <div className="search-field">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
            }}
            placeholder="搜索告警、机组或代码…"
            aria-label="搜索告警"
          />
        </div>
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
            setPage(0);
          }}
        >
          <Filter size={14} /> 状态 {statusFilter === "all" ? "全部" : statusFilter}{" "}
          <ChevronDown size={12} />
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            const options = [0, 1, 6, 24] as const;
            setTimeWindowHours(options[(options.indexOf(timeWindowHours) + 1) % options.length]!);
            setPage(0);
          }}
        >
          <Clock3 size={14} /> 触发时间 {timeWindowHours ? `${timeWindowHours}H` : "全部"}{" "}
          <ChevronDown size={12} />
        </Button>
        <span className="toolbar-result">{filtered.length} 条记录</span>
        <Button
          variant="ghost"
          onClick={() => {
            setSeverity("all");
            setStatusFilter("all");
            setTimeWindowHours(0);
            setQuery("");
            setPage(0);
          }}
        >
          清除筛选
        </Button>
      </section>

      <Card className="data-table-card alarm-table-card">
        <div className="table-scroll">
          <table className="data-table alarm-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    aria-label="选择当前页所有告警"
                    checked={
                      pageRows.length > 0 &&
                      pageRows.every((alarm) => selectedIds.includes(alarm.id))
                    }
                    onChange={(event) => {
                      const pageIds = pageRows.map((alarm) => alarm.id);
                      setSelectedIds((current) =>
                        event.target.checked
                          ? [...new Set([...current, ...pageIds])]
                          : current.filter((id) => !pageIds.includes(id)),
                      );
                    }}
                  />
                </th>
                <th>Severity</th>
                <th>Wind Turbine</th>
                <th>Subsystem</th>
                <th>Alarm Code</th>
                <th>Alarm</th>
                <th>Triggered At</th>
                <th>Duration</th>
                <th>Status</th>
                <th>AI Status</th>
                <th>Assignee</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {pageRows.map((alarm) => (
                <tr
                  key={alarm.id}
                  className={cn(alarm.id === featuredAlarm?.id && "row-featured")}
                  onClick={() => setSelectedAlarmId(alarm.id)}
                >
                  <td onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`选择 ${alarm.id}`}
                      checked={selectedIds.includes(alarm.id)}
                      onChange={() => toggleSelection(alarm.id)}
                    />
                  </td>
                  <td>
                    <StatusBadge
                      value={alarm.severity}
                      label={severityLabel[alarm.severity]}
                      tone={severityTone[alarm.severity]}
                      compact
                    />
                  </td>
                  <td>
                    <strong className="mono">{alarm.turbineId}</strong>
                  </td>
                  <td>{alarm.subsystem.replaceAll("-", " ")}</td>
                  <td className="mono">{alarm.code}</td>
                  <td>
                    <span className="alarm-title-cell">
                      <strong>{alarm.title}</strong>
                      <small>{alarm.description}</small>
                    </span>
                  </td>
                  <td>
                    {new Date(alarm.triggeredAt).toLocaleString("zh-CN", {
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: false,
                    })}
                  </td>
                  <td>{duration(alarm.durationMinutes)}</td>
                  <td>
                    <StatusBadge value={alarm.status} compact />
                  </td>
                  <td>
                    <span
                      className={cn(
                        "ai-status-cell",
                        alarm.aiStatus === "analyzing" && "ai-status-cell--working",
                      )}
                    >
                      <Bot size={13} /> {alarm.aiStatus}
                    </span>
                  </td>
                  <td>{alarm.assignee ?? <span className="muted">未指派</span>}</td>
                  <td>
                    <Button size="icon" variant="ghost" aria-label="更多">
                      <MoreHorizontal size={14} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-pagination">
          <span>
            已选择 {selectedIds.length} / {filtered.length} 行
          </span>
          <span>
            第 {currentPage + 1} 页，共 {pageCount} 页
          </span>
          <div>
            <Button
              size="sm"
              variant="secondary"
              disabled={currentPage === 0}
              onClick={() => setPage(Math.max(0, currentPage - 1))}
            >
              上一页
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={currentPage >= pageCount - 1}
              onClick={() => setPage(Math.min(pageCount - 1, currentPage + 1))}
            >
              下一页
            </Button>
          </div>
        </div>
      </Card>
      {selectedAlarm ? (
        <AlarmDrawer
          alarm={selectedAlarm}
          onClose={() => setSelectedAlarmId(null)}
          onAcknowledge={(alarmId) =>
            setAcknowledgedIds((current) =>
              current.includes(alarmId) ? current : [...current, alarmId],
            )
          }
          onToggleAssignment={(alarm) =>
            setAssignmentOverrides((current) => ({
              ...current,
              [alarm.id]: alarm.assignee ? null : "值班工程师",
            }))
          }
        />
      ) : null}
    </AppShell>
  );
}
