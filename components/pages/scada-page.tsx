"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Activity, TriangleAlert as AlarmTriangle, CalendarDays, Download, Gauge, Maximize2, Radio, RefreshCcw, Search, Thermometer, Wind, Zap } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { TimeSeriesChart, type TimeSeriesPoint } from "@/components/charts/time-series-chart";
import { scadaSeries, turbine023 } from "@/lib";
import type { ScadaSeries } from "@/lib/types";
import { cn } from "@/lib/utils";

const ranges = ["LIVE", "1H", "6H", "24H", "7D", "30D"] as const;

function toChartData(series: ScadaSeries): TimeSeriesPoint[] {
  return series.points.map((point) => ({
    timestamp: new Date(point.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }),
    value: point.value,
    anomaly: point.isAnomaly,
    aiEvent: Boolean(point.aiEvent),
  }));
}

function metricIcon(metric: ScadaSeries["metric"]) {
  if (metric.includes("temperature")) return Thermometer;
  if (metric.includes("wind")) return Wind;
  if (metric.includes("power")) return Zap;
  if (metric.includes("speed")) return Gauge;
  return Activity;
}

function signalState(series: ScadaSeries) {
  const warning = series.thresholds.some((threshold) => threshold.direction === "above" ? series.currentValue >= threshold.value : series.currentValue <= threshold.value);
  return warning ? "warning" : "normal";
}

export function ScadaPage() {
  const initial = scadaSeries.find((item) => item.metric === "main-bearing-vibration-rms") ?? scadaSeries[0];
  const [selectedId, setSelectedId] = useState(initial?.id ?? "");
  const [range, setRange] = useState<(typeof ranges)[number]>("24H");
  const [query, setQuery] = useState("");
  const selected = scadaSeries.find((item) => item.id === selectedId) ?? initial;
  const filtered = useMemo(() => scadaSeries.filter((item) => `${item.label} ${item.metric}`.toLowerCase().includes(query.toLowerCase())), [query]);
  if (!selected) return null;
  const threshold = selected.thresholds[0]?.value;
  const activePower = scadaSeries.find((item) => item.metric === "active-power");
  const windSpeed = scadaSeries.find((item) => item.metric === "wind-speed");
  const rotorSpeed = scadaSeries.find((item) => item.metric === "rotor-speed");
  const generatorTemp = scadaSeries.find((item) => item.metric === "generator-temperature");

  return (
    <AppShell activePath="/scada">
      <PageHeader eyebrow="SCADA 数据平面" title="实时监测" description={`${turbine023.id} · ${turbine023.model} · 高频测点、阈值与 AI 事件联合监控`} breadcrumb={["资产与监测", "实时监测", turbine023.id]} meta={<><StatusBadge value="running" label="数据流正常" tone="success" pulse /><span className="page-meta-text">{scadaSeries.length} / {scadaSeries.length} 测点在线 · 实时流 10s · 历史序列 15min</span></>} actions={<><Button variant="secondary"><CalendarDays size={15} /> 自定义时段</Button><Button variant="secondary"><Download size={15} /> 导出 CSV</Button><Button variant="primary"><RefreshCcw size={15} /> 刷新数据</Button></>} />

      <section className="scada-control-bar">
        <div className="asset-selector"><span><Radio size={15} /><small>监测资产</small><strong>{turbine023.id}</strong></span><span className="asset-selector__divider" /><span><small>数据源</small><strong>SCADA Gateway 01</strong></span></div>
        <div className="range-switcher">{ranges.map((item) => <button key={item} onClick={() => setRange(item)} className={cn(range === item && "active")}>{item}</button>)}</div>
        <span className="stream-indicator"><i /> LIVE STREAM · 12s</span>
      </section>

      <section className="scada-live-grid">
        <div><span><Wind size={14} /> 风速</span><strong>{windSpeed?.currentValue.toFixed(1) ?? "9.7"}<small>m/s</small></strong><em>正常范围</em></div>
        <div><span><Zap size={14} /> 有功功率</span><strong>{activePower?.currentValue.toFixed(2) ?? "5.34"}<small>MW</small></strong><em>89% 额定</em></div>
        <div><span><Gauge size={14} /> 转子转速</span><strong>{rotorSpeed?.currentValue.toFixed(1) ?? "11.6"}<small>rpm</small></strong><em>稳定</em></div>
        <div><span><Thermometer size={14} /> 发电机温度</span><strong>{generatorTemp?.currentValue.toFixed(1) ?? "67.3"}<small>°C</small></strong><em>正常</em></div>
        <div className="scada-live--warning"><span><Activity size={14} /> 轴承振动</span><strong>4.81<small>mm/s</small></strong><em>超过预警阈值</em></div>
      </section>

      <section className="scada-layout">
        <div className="scada-chart-stack">
          <Card className="scada-main-chart">
            <CardHeader eyebrow={`${selected.metric.toUpperCase()} · ${range}`} title={selected.label} description={`正常范围 ${selected.normalRange[0]}–${selected.normalRange[1]} ${selected.unit} · 当前 ${selected.currentValue.toFixed(selected.precision)} ${selected.unit}`} action={<div className="chart-actions"><StatusBadge value={signalState(selected)} label={signalState(selected) === "normal" ? "NORMAL" : "WARNING"} /><Button size="icon" variant="ghost" aria-label="全屏"><Maximize2 size={15} /></Button></div>} />
            <div className="scada-chart-context"><span><i className="legend-line legend-line--signal" />{selected.label}</span><span><i className="legend-line legend-line--threshold" />告警阈值</span><span><i className="legend-marker legend-marker--anomaly" />异常点</span><span><i className="legend-marker legend-marker--ai" />AI 事件</span></div>
            <TimeSeriesChart data={toChartData(selected)} height={340} unit={selected.unit} threshold={threshold} primaryName={selected.label} />
          </Card>
          <Card className="scada-correlation">
            <CardHeader eyebrow="CORRELATED SIGNALS" title="关联信号趋势" description="主轴承温度与振动异常的时间相关性" action={<span className="correlation-score">相关度 <strong>0.79</strong></span>} />
            <div className="correlation-chart-grid"><div><span>主轴承温度</span><TimeSeriesChart data={toChartData(scadaSeries.find((item) => item.metric === "main-bearing-temperature") ?? selected)} height={150} unit="°C" threshold={75} primaryName="主轴承温度" /></div><div><span>异常得分</span><TimeSeriesChart data={toChartData(scadaSeries.find((item) => item.metric === "anomaly-score") ?? selected)} height={150} unit="score" threshold={0.7} primaryName="异常得分" /></div></div>
          </Card>
        </div>

        <Card className="signals-panel">
          <div className="signals-panel__header"><div><span className="eyebrow">VARIABLES</span><h2>SCADA 测点</h2></div><span>{scadaSeries.length} signals</span></div>
          <div className="signal-search"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索测点…" aria-label="搜索测点" /></div>
          <div className="signal-list">
            {filtered.map((item) => {
              const Icon = metricIcon(item.metric);
              const state = signalState(item);
              return <button className={cn("signal-row", item.id === selected.id && "signal-row--active")} key={item.id} onClick={() => setSelectedId(item.id)}><span className={cn("signal-icon", state === "warning" && "signal-icon--warning")}><Icon size={14} /></span><span className="signal-row__copy"><strong>{item.label}</strong><small>{item.metric}</small></span><span className="signal-row__value"><strong>{item.currentValue.toFixed(item.precision)}</strong><small>{item.unit}</small></span><i className={cn("signal-quality", state === "warning" && "signal-quality--warning")} /></button>;
            })}
          </div>
          <div className="signals-panel__footer"><span><i /> 数据质量 99.98%</span><span>Gateway 01</span></div>
        </Card>
      </section>

      <section className="event-ribbon">
        <span className="event-ribbon__icon"><AlarmTriangle size={16} /></span>
        <span><small>AI EVENT · 09:14:32</small><strong>振动与温升关联异常持续 37 分钟，已升级为 MISSION-2026-0823</strong></span>
        <Link href="/missions/MISSION-2026-0823">查看分析证据 <Activity size={13} /></Link>
      </section>
    </AppShell>
  );
}
