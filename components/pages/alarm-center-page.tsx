"use client";

import { useMemo, useState } from "react";
import { Activity, TriangleAlert as AlarmTriangle, ArrowRight, Bot, Check, ChevronDown, Clock3, Download, FileSearch, Filter, MoreHorizontal, Search, ShieldAlert, Thermometer, UserRound, X } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, KeyValue } from "@/components/ui/primitives";
import { StatusBadge, type StatusTone } from "@/components/data-display/status-badge";
import { alarms, evidenceItems, featuredMission } from "@/lib";
import type { Alarm, AlarmSeverity } from "@/lib/types";
import { cn } from "@/lib/utils";

const severityTone: Record<AlarmSeverity, StatusTone> = { critical: "critical", major: "warning", minor: "maintenance", warning: "warning", info: "info" };
const severityLabel: Record<AlarmSeverity, string> = { critical: "CRITICAL", major: "MAJOR", minor: "MINOR", warning: "WARNING", info: "INFO" };

function duration(minutes: number) {
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function AlarmDrawer({ alarm, onClose }: { alarm: Alarm; onClose: () => void }) {
  const relatedEvidence = evidenceItems.filter((item) => alarm.evidenceIds.includes(item.id));
  const featured = alarm.turbineId === "WT-023";
  return <><button className="drawer-backdrop" onClick={onClose} aria-label="关闭告警详情" /><aside className="detail-drawer alarm-drawer" aria-label={`${alarm.id} 告警详情`}>
    <header className="detail-drawer__header"><div><span className="eyebrow">ALARM DETAIL</span><h2>{alarm.code}</h2><p>{alarm.turbineId} · {alarm.subsystem}</p></div><Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭"><X size={18} /></Button></header>
    <div className="detail-drawer__status"><StatusBadge value={alarm.severity} label={severityLabel[alarm.severity]} tone={severityTone[alarm.severity]} /><StatusBadge value={alarm.status} label={alarm.status.toUpperCase()} /><span>持续 {duration(alarm.durationMinutes)}</span></div>
    <section className="alarm-detail-hero"><span className={`alarm-detail-hero__icon alarm-detail-hero__icon--${alarm.severity}`}><AlarmTriangle size={20} /></span><div><h3>{alarm.title}</h3><p>{alarm.description}</p></div></section>
    <section className="drawer-section"><h3>告警信息</h3><div className="key-value-list"><KeyValue label="触发时间" value={new Date(alarm.triggeredAt).toLocaleString("zh-CN")} /><KeyValue label="当前值" value={alarm.currentValue === null ? "—" : `${alarm.currentValue} ${alarm.unit}`} /><KeyValue label="告警阈值" value={alarm.threshold === null ? "—" : `${alarm.threshold} ${alarm.unit}`} /><KeyValue label="负责人" value={alarm.assignee ?? "未指派"} /><KeyValue label="AI 状态" value={alarm.aiStatus} /></div></section>
    {featured ? <section className="ai-diagnosis-card"><div className="ai-diagnosis-card__header"><span><Bot size={17} /></span><div><span className="eyebrow">AI DIAGNOSIS</span><h3>主轴承早期退化</h3></div><strong>87%</strong></div><p>振动 RMS 持续升高，且与主轴承温升和功率波动存在显著相关性。建议降载运行，并在 72 小时内完成现场检查。</p><div className="diagnosis-signals"><span><Activity size={13} /> 振动 +27%</span><span><Thermometer size={13} /> 温度 +8.4°C</span><span><Activity size={13} /> 功率波动 +6%</span></div><a href={`/missions/${featuredMission.id}`}>打开完整诊断 Mission <ArrowRight size={13} /></a></section> : null}
    <section className="drawer-section"><div className="drawer-section__title"><h3>证据链</h3><span className="record-count">{relatedEvidence.length} 项</span></div><div className="evidence-compact-list">{relatedEvidence.length ? relatedEvidence.map((item) => <div key={item.id}><span><FileSearch size={14} /></span><div><strong>{item.title}</strong><small>{item.sourceLabel} · {new Date(item.observedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}</small></div>{item.deltaPercent !== null ? <em>+{item.deltaPercent}%</em> : null}</div>) : <p className="no-evidence">AI 证据正在整理中</p>}</div></section>
    <section className="drawer-section"><h3>处理记录</h3><div className="alarm-audit"><div><span><Check size={12} /></span><p><strong>告警已确认</strong><small>值班工程师 · 09:18</small></p></div><div><span><Bot size={12} /></span><p><strong>AI 分析完成</strong><small>Failure Diagnosis Agent · 09:31</small></p></div><div><span><ShieldAlert size={12} /></span><p><strong>等待人工审批</strong><small>当前状态 · 10:02</small></p></div></div></section>
    <footer className="detail-drawer__footer"><Button variant="secondary"><Check size={14} /> 确认告警</Button><Button variant="secondary"><UserRound size={14} /> 指派</Button><a href={`/missions/${featuredMission.id}`} className="button button--primary button--md">进入 Mission <ArrowRight size={14} /></a></footer>
  </aside></>;
}

export function AlarmCenterPage() {
  const featuredAlarm = alarms.find((alarm) => alarm.turbineId === "WT-023") ?? alarms[0];
  const [selected, setSelected] = useState<Alarm | null>(null);
  const [severity, setSeverity] = useState<"all" | AlarmSeverity>("all");
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => alarms.filter((alarm) => (severity === "all" || alarm.severity === severity) && `${alarm.id} ${alarm.code} ${alarm.title} ${alarm.turbineId}`.toLowerCase().includes(query.toLowerCase())), [query, severity]);
  const counts = { critical: alarms.filter((item) => item.severity === "critical").length, major: alarms.filter((item) => item.severity === "major").length, warning: alarms.filter((item) => item.severity === "warning").length, diagnosed: alarms.filter((item) => item.aiStatus === "diagnosed" || item.aiStatus === "action-created").length };

  return <AppShell activePath="/alarms">
    <PageHeader eyebrow="智能运维" title="告警中心" description="工业级告警分级、关联分析与 AI 诊断闭环" breadcrumb={["智能运维", "告警中心"]} meta={<><StatusBadge value="critical" label={`${counts.critical} CRITICAL`} tone="critical" pulse /><span className="page-meta-text">17 个活跃告警 · 6 个正在 AI 分析</span></>} actions={<><Button variant="secondary"><Download size={15} /> 导出</Button><Button variant="primary"><Check size={15} /> 批量确认</Button></>} />

    <section className="alarm-summary-grid"><button onClick={() => setSeverity("critical")} className={cn(severity === "critical" && "active")}><span className="summary-icon summary-icon--critical"><AlarmTriangle size={16} /></span><span><small>Critical</small><strong>{counts.critical}</strong></span><em>需立即处理</em></button><button onClick={() => setSeverity("major")} className={cn(severity === "major" && "active")}><span className="summary-icon summary-icon--warning"><ShieldAlert size={16} /></span><span><small>Major</small><strong>{counts.major}</strong></span><em>重点关注</em></button><button onClick={() => setSeverity("warning")} className={cn(severity === "warning" && "active")}><span className="summary-icon summary-icon--maintenance"><Activity size={16} /></span><span><small>Warning</small><strong>{counts.warning}</strong></span><em>趋势观察</em></button><button onClick={() => setSeverity("all")} className={cn(severity === "all" && "active")}><span className="summary-icon summary-icon--info"><Bot size={16} /></span><span><small>AI Diagnosed</small><strong>{counts.diagnosed}</strong></span><em>已形成判断</em></button></section>

    <section className="data-toolbar"><div className="search-field"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索告警、机组或代码…" aria-label="搜索告警" /></div><Button variant="secondary"><Filter size={14} /> 状态 <ChevronDown size={12} /></Button><Button variant="secondary"><Clock3 size={14} /> 触发时间 <ChevronDown size={12} /></Button><span className="toolbar-result">{filtered.length} 条记录</span><Button variant="ghost" onClick={() => { setSeverity("all"); setQuery(""); }}>清除筛选</Button></section>

    <Card className="data-table-card alarm-table-card"><div className="table-scroll"><table className="data-table alarm-table"><thead><tr><th><input type="checkbox" aria-label="选择所有告警" /></th><th>Severity</th><th>Wind Turbine</th><th>Subsystem</th><th>Alarm Code</th><th>Alarm</th><th>Triggered At</th><th>Duration</th><th>Status</th><th>AI Status</th><th>Assignee</th><th /></tr></thead><tbody>{filtered.map((alarm) => <tr key={alarm.id} className={cn(alarm.id === featuredAlarm?.id && "row-featured")} onClick={() => setSelected(alarm)}><td onClick={(event) => event.stopPropagation()}><input type="checkbox" aria-label={`选择 ${alarm.id}`} /></td><td><StatusBadge value={alarm.severity} label={severityLabel[alarm.severity]} tone={severityTone[alarm.severity]} compact /></td><td><strong className="mono">{alarm.turbineId}</strong></td><td>{alarm.subsystem.replaceAll("-", " ")}</td><td className="mono">{alarm.code}</td><td><span className="alarm-title-cell"><strong>{alarm.title}</strong><small>{alarm.description}</small></span></td><td>{new Date(alarm.triggeredAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })}</td><td>{duration(alarm.durationMinutes)}</td><td><StatusBadge value={alarm.status} compact /></td><td><span className={cn("ai-status-cell", alarm.aiStatus === "analyzing" && "ai-status-cell--working")}><Bot size={13} /> {alarm.aiStatus}</span></td><td>{alarm.assignee ?? <span className="muted">未指派</span>}</td><td><Button size="icon" variant="ghost" aria-label="更多"><MoreHorizontal size={14} /></Button></td></tr>)}</tbody></table></div><div className="table-pagination"><span>已选择 0 / {filtered.length} 行</span><span>第 1 页，共 3 页</span><div><Button size="sm" variant="secondary" disabled>上一页</Button><Button size="sm" variant="secondary">下一页</Button></div></div></Card>
    {selected ? <AlarmDrawer alarm={selected} onClose={() => setSelected(null)} /> : null}
  </AppShell>;
}
