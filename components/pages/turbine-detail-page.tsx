"use client";

import { useState } from "react";
import {
  Activity,
  TriangleAlert as AlarmTriangle,
  ArrowRight,
  Bot,
  CalendarClock,
  ClipboardCheck,
  FileText,
  Gauge,
  Play,
  Radio,
  Settings2,
  ShieldAlert,
  Thermometer,
  TowerControl,
  TrendingDown,
  Wind,
  Wrench,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, KeyValue, Progress } from "@/components/ui/primitives";
import { HealthBadge, StatusBadge } from "@/components/data-display/status-badge";
import { TimeSeriesChart, type TimeSeriesPoint } from "@/components/charts/time-series-chart";
import { alarms, featuredMission, knowledgeDocuments, scadaSeries, subsystemHealth, turbine023, workOrders } from "@/lib";
import type { SubsystemHealth } from "@/lib/types";
import { cn } from "@/lib/utils";

const tabs = ["Overview", "SCADA", "Health", "Alarms", "Missions", "Maintenance", "Documents"] as const;
type Tab = (typeof tabs)[number];

function stateLabel(state: SubsystemHealth["state"]) {
  const labels: Record<SubsystemHealth["state"], string> = {
    healthy: "健康", watch: "关注", degraded: "退化", critical: "严重", maintenance: "维护", offline: "离线",
  };
  return labels[state];
}

function series(metric: string): TimeSeriesPoint[] {
  const match = scadaSeries.find((item) => item.metric === metric);
  return match?.points.map((point) => ({
    timestamp: new Date(point.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }),
    value: point.value,
    anomaly: point.isAnomaly,
    aiEvent: Boolean(point.aiEvent),
  })) ?? [];
}

function OverviewTab() {
  const bearing = subsystemHealth.find((item) => item.key === "main-bearing");
  return (
    <div className="asset-overview-grid">
      <Card className="asset-hero-card">
        <div className="asset-hero-card__visual"><span className="asset-hero-grid" /><TowerControl size={88} strokeWidth={1.2} /><span className="asset-hero-card__tag">DIGITAL ASSET</span></div>
        <div className="asset-hero-card__content">
          <span className="eyebrow">ASSET PROFILE</span>
          <h2>{turbine023.id}</h2>
          <p>{turbine023.manufacturer} {turbine023.model}</p>
          <div className="asset-profile-list"><KeyValue label="额定功率" value={`${turbine023.ratedPowerMW.toFixed(1)} MW`} /><KeyValue label="序列号" value={turbine023.serialNumber} mono /><KeyValue label="投运年限" value="4.7 年" /><KeyValue label="全周期可利用率" value="97.2%" /></div>
        </div>
      </Card>

      <Card className="asset-live-card">
        <CardHeader eyebrow="LIVE SNAPSHOT" title="实时运行参数" description="数据质量良好 · 12 秒前更新" />
        <div className="live-metric-grid">
          <div><span><Zap size={14} /> 有功功率</span><strong>5.34 <small>MW</small></strong><em>89% 额定功率</em></div>
          <div><span><Wind size={14} /> 风速</span><strong>9.7 <small>m/s</small></strong><em>东南风 128°</em></div>
          <div><span><Gauge size={14} /> 转子转速</span><strong>11.6 <small>rpm</small></strong><em>稳定</em></div>
          <div className="live-metric--warning"><span><Thermometer size={14} /> 主轴承温度</span><strong>76.4 <small>°C</small></strong><em>+8.4°C 基线偏差</em></div>
        </div>
        <div className="asset-mini-chart"><div><span className="eyebrow">ACTIVE POWER · 6H</span><strong>稳定输出，存在 6% 功率波动</strong></div><TimeSeriesChart data={series("active-power")} height={108} unit="MW" compact /></div>
      </Card>

      <Card className="bearing-focus-card">
        <div className="bearing-focus-card__header"><span className="bearing-focus-icon"><ShieldAlert size={19} /></span><span><span className="eyebrow">PRIMARY RISK</span><h2>主轴承早期退化</h2></span><StatusBadge value="high" label="HIGH RISK" tone="critical" /></div>
        <p>振动 RMS 持续升高并与温升、功率波动呈相关性。故障诊断 Agent 给出 87% 置信度。</p>
        <div className="risk-stat-grid"><div><small>当前健康度</small><strong>{bearing?.healthScore ?? 63}<span>/100</span></strong><Progress value={bearing?.healthScore ?? 63} tone="critical" /></div><div><small>30 天失效概率</small><strong>{bearing?.failureProbability30d ?? 34}<span>%</span></strong><Progress value={bearing?.failureProbability30d ?? 34} tone="warning" /></div><div><small>预计 RUL</small><strong>{bearing?.remainingUsefulLifeDays ?? 47}<span>天</span></strong><span className="trend-label"><TrendingDown size={12} /> 持续下降</span></div><div><small>异常得分</small><strong>{bearing?.anomalyScore.toFixed(2) ?? "0.86"}</strong><span className="trend-label warning-text"><Activity size={12} /> 高于阈值</span></div></div>
        <div className="bearing-focus-card__action"><span><Bot size={15} /><strong>AI 建议：降载运行并在 72 小时内检查</strong></span><a href={`/missions/${featuredMission.id}`}>查看决策 <ArrowRight size={13} /></a></div>
      </Card>

      <Card className="subsystem-panel">
        <CardHeader eyebrow="COMPONENT HEALTH" title="子系统健康状态" description="基于 SCADA、振动和维护数据的综合评估" action={<a className="text-link" href="/scada">查看监测 <ArrowRight size={12} /></a>} />
        <div className="subsystem-grid">
          {subsystemHealth.map((item) => <div className={cn("subsystem-item", item.key === "main-bearing" && "subsystem-item--focus")} key={item.id}><div className="subsystem-item__top"><span><Settings2 size={14} /><strong>{item.name}</strong></span><StatusBadge value={item.state} label={stateLabel(item.state)} tone={item.healthScore >= 90 ? "success" : item.healthScore >= 75 ? "warning" : "critical"} compact /></div><div className="subsystem-score"><strong>{item.healthScore}</strong><span>/ 100</span></div><Progress value={item.healthScore} tone={item.healthScore >= 90 ? "success" : item.healthScore >= 75 ? "warning" : "critical"} /><div className="subsystem-item__footer"><span>失效概率 {item.failureProbability30d}%</span><span>RUL {item.remainingUsefulLifeDays ?? "—"}d</span></div></div>)}
        </div>
      </Card>

      <Card className="asset-history-card">
        <CardHeader eyebrow="ASSET HISTORY" title="最近事件" description="维护、告警与 AI 分析记录" />
        <div className="asset-history-list">
          <div><span className="history-icon history-icon--critical"><AlarmTriangle size={14} /></span><span><strong>主轴承振动告警升级</strong><small>ALM-2026-0031 · 今天 09:42</small></span></div>
          <div><span className="history-icon history-icon--info"><Bot size={14} /></span><span><strong>多 Agent 诊断完成</strong><small>退化概率 87% · 今天 09:31</small></span></div>
          <div><span className="history-icon history-icon--maintenance"><Wrench size={14} /></span><span><strong>季度润滑系统巡检</strong><small>WO-20260702-008 · 2026/07/02</small></span></div>
          <div><span className="history-icon"><Radio size={14} /></span><span><strong>振动传感器校准</strong><small>结果正常 · 2026/06/18</small></span></div>
        </div>
      </Card>
    </div>
  );
}

function ScadaTab() {
  return <div className="two-column-content"><Card><CardHeader eyebrow="SCADA · 24H" title="主轴承振动 RMS" description="阈值、异常点与 AI 事件联动" /><TimeSeriesChart data={series("main-bearing-vibration-rms")} height={300} unit="mm/s" threshold={4.5} primaryName="振动 RMS" /></Card><Card><CardHeader eyebrow="CORRELATED SIGNAL" title="主轴承温度" description="与振动异常存在 0.79 相关度" /><TimeSeriesChart data={series("main-bearing-temperature")} height={300} unit="°C" threshold={75} primaryName="轴承温度" /></Card></div>;
}

function HealthTab() {
  return <div className="health-detail-layout"><Card className="health-matrix-card"><CardHeader eyebrow="ASSET HEALTH" title="子系统风险矩阵" description="概率 × 后果的综合风险排序" /><div className="risk-matrix"><div className="risk-axis risk-axis--y">失效概率 ↑</div>{[5,4,3,2,1].flatMap((row) => [1,2,3,4,5].map((column) => { const level = row * column >= 16 ? "critical" : row * column >= 10 ? "high" : row * column >= 5 ? "medium" : "low"; const bearing = row === 4 && column === 4; return <div key={`${row}-${column}`} className={cn("risk-cell", `risk-cell--${level}`)}>{bearing ? <span>主轴承</span> : null}</div>; }))}<div className="risk-axis risk-axis--x">后果严重度 →</div></div></Card><Card><CardHeader eyebrow="DEGRADATION" title="健康趋势" description="过去 90 天持续下降" /><TimeSeriesChart data={series("anomaly-score")} height={290} unit="score" threshold={0.7} primaryName="异常得分" /></Card></div>;
}

function RelatedList({ type }: { type: "alarms" | "maintenance" | "documents" }) {
  const items = type === "alarms" ? alarms.filter((item) => item.turbineId === turbine023.id).map((item) => ({ id: item.id, title: item.title, meta: `${item.code} · ${item.severity.toUpperCase()}`, status: item.status })) : type === "maintenance" ? workOrders.filter((item) => item.turbineId === turbine023.id).map((item) => ({ id: item.id, title: item.issue, meta: `${item.assignedTeam} · ${new Date(item.plannedStart).toLocaleDateString("zh-CN")}`, status: item.status })) : knowledgeDocuments.filter((item) => item.relatedTurbineIds.includes(turbine023.id)).map((item) => ({ id: item.id, title: item.title, meta: `${item.type} · ${item.version}`, status: item.vectorized ? "vectorized" : "pending" }));
  return <Card className="related-records"><CardHeader eyebrow="RELATED RECORDS" title={type === "alarms" ? "相关告警" : type === "maintenance" ? "维护记录" : "关联文档"} description={`与 ${turbine023.id} 资产关联的可追溯记录`} /><div className="related-list">{items.map((item) => <div key={item.id}><span className="related-list__icon">{type === "alarms" ? <AlarmTriangle size={15} /> : type === "maintenance" ? <ClipboardCheck size={15} /> : <FileText size={15} />}</span><span><strong>{item.title}</strong><small>{item.id} · {item.meta}</small></span><StatusBadge value={item.status} compact /></div>)}</div></Card>;
}

export function TurbineDetailPage() {
  const [tab, setTab] = useState<Tab>("Overview");
  return (
    <AppShell activePath="/turbines/WT-023">
      <PageHeader eyebrow="数字资产" title={`${turbine023.id} · ${turbine023.model}`} description="主轴承异常已进入多 Agent 协同诊断与人工审批流程" breadcrumb={["资产与监测", "风场", "华东海上风电场", turbine023.id]} meta={<><StatusBadge value={turbine023.status} label="预警运行" tone="warning" pulse /><HealthBadge score={turbine023.healthScore} /><span className="page-meta-text">最后同步 12 秒前</span></>} actions={<><Button variant="secondary"><CalendarClock size={15} /> 维护计划</Button><Button variant="secondary"><Activity size={15} /> 历史趋势</Button><Button variant="primary"><Play size={15} /> 启动 AI 诊断</Button></>} />
      <nav className="detail-tabs" aria-label="机组详情标签页">{tabs.map((item) => <button key={item} className={cn(tab === item && "active")} onClick={() => setTab(item)}>{item}{item === "Alarms" ? <span>3</span> : null}{item === "Missions" ? <span>1</span> : null}</button>)}</nav>
      {tab === "Overview" ? <OverviewTab /> : null}
      {tab === "SCADA" ? <ScadaTab /> : null}
      {tab === "Health" ? <HealthTab /> : null}
      {tab === "Alarms" ? <RelatedList type="alarms" /> : null}
      {tab === "Missions" ? <Card className="mission-callout"><span className="mission-callout__icon"><Bot size={24} /></span><span><span className="eyebrow">ACTIVE MISSION</span><h2>{featuredMission.title}</h2><p>{featuredMission.summary}</p><div><StatusBadge value={featuredMission.status} label="执行准备中" tone="info" pulse /><strong>{featuredMission.progressPercent}%</strong></div></span><a className="button button--primary button--md" href={`/missions/${featuredMission.id}`}>打开 Mission <ArrowRight size={14} /></a></Card> : null}
      {tab === "Maintenance" ? <RelatedList type="maintenance" /> : null}
      {tab === "Documents" ? <RelatedList type="documents" /> : null}
    </AppShell>
  );
}
