"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Boxes,
  Grid2X2,
  List,
  Map,
  MoreHorizontal,
  Network,
  Plus,
  Search,
  SlidersHorizontal,
  TowerControl,
  Wind,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, KeyValue, Progress } from "@/components/ui/primitives";
import { HealthBadge, StatusBadge, type StatusTone } from "@/components/data-display/status-badge";
import { turbines, windFarm } from "@/lib";
import type { TurbineStatus, WindTurbine } from "@/lib/types";
import { cn } from "@/lib/utils";

type ViewMode = "cards" | "list" | "topology" | "map";

const statusMeta: Record<TurbineStatus, { label: string; tone: StatusTone }> = {
  running: { label: "运行", tone: "success" },
  warning: { label: "预警", tone: "warning" },
  critical: { label: "故障", tone: "critical" },
  maintenance: { label: "维护", tone: "maintenance" },
  offline: { label: "离线", tone: "offline" },
  "communication-lost": { label: "通信中断", tone: "offline" },
};

function TurbineDrawer({ turbine, onClose }: { turbine: WindTurbine; onClose: () => void }) {
  const anomaly = turbine.id === "WT-023";
  return (
    <>
      <button className="drawer-backdrop" onClick={onClose} aria-label="关闭机组概览" />
      <aside className="detail-drawer" aria-label={`${turbine.id} 快速概览`}>
        <header className="detail-drawer__header">
          <div><span className="eyebrow">WIND TURBINE</span><h2>{turbine.id}</h2><p>{turbine.manufacturer} · {turbine.model}</p></div>
          <Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭"><X size={18} /></Button>
        </header>
        <div className="detail-drawer__status">
          <StatusBadge value={turbine.status} label={statusMeta[turbine.status].label} tone={statusMeta[turbine.status].tone} pulse={turbine.status === "running"} />
          <HealthBadge score={turbine.healthScore} />
          <span>最后更新 12 秒前</span>
        </div>

        {anomaly ? (
          <div className="drawer-alert">
            <span className="drawer-alert__icon"><Activity size={16} /></span>
            <span><strong>AI 检测到主轴承早期退化</strong><small>置信度 87% · 建议 72 小时内检查</small></span>
            <Link href="/missions/MISSION-2026-0823">查看</Link>
          </div>
        ) : null}

        <section className="drawer-section">
          <h3>实时运行</h3>
          <div className="drawer-metrics">
            <div><span><Zap size={14} /> 有功功率</span><strong>{turbine.powerMW.toFixed(2)} <small>MW</small></strong></div>
            <div><span><Wind size={14} /> 风速</span><strong>{turbine.windSpeedMps.toFixed(1)} <small>m/s</small></strong></div>
            <div><span><Activity size={14} /> 转子转速</span><strong>{turbine.rotorSpeedRpm.toFixed(1)} <small>rpm</small></strong></div>
            <div><span><TowerControl size={14} /> 可利用率</span><strong>{turbine.availabilityPercent.toFixed(1)} <small>%</small></strong></div>
          </div>
        </section>

        <section className="drawer-section">
          <div className="drawer-section__title"><h3>健康状态</h3><strong>{turbine.healthScore}/100</strong></div>
          <Progress value={turbine.healthScore} tone={turbine.healthScore >= 90 ? "success" : turbine.healthScore >= 75 ? "warning" : "critical"} />
          <div className="key-value-list">
            <KeyValue label="主轴承" value={anomaly ? "63 · 退化" : `${Math.min(98, turbine.healthScore + 1)} · 正常`} />
            <KeyValue label="齿轮箱" value={`${Math.min(98, turbine.healthScore + 10)} · 正常`} />
            <KeyValue label="发电机" value={`${Math.min(99, turbine.healthScore + 12)} · 正常`} />
            <KeyValue label="活跃告警" value={`${turbine.activeAlarmCount} 条`} />
          </div>
        </section>

        <section className="drawer-section">
          <h3>维护信息</h3>
          <div className="key-value-list">
            <KeyValue label="上次维护" value={new Date(turbine.lastMaintenanceAt).toLocaleDateString("zh-CN")} />
            <KeyValue label="下次巡检" value={new Date(turbine.nextInspectionAt).toLocaleDateString("zh-CN")} />
            <KeyValue label="当前 Mission" value={turbine.currentMissionId ?? "—"} mono />
          </div>
        </section>

        <footer className="detail-drawer__footer">
          <a className="button button--secondary button--md" href="/scada"><Activity size={15} /> 历史趋势</a>
          <a className="button button--secondary button--md" href="/work-orders"><Wrench size={15} /> 创建工单</a>
          <a className="button button--primary button--md" href={`/turbines/${turbine.id}`}>进入机组详情 <ArrowRight size={15} /></a>
        </footer>
      </aside>
    </>
  );
}

export function WindFarmPage() {
  const [view, setView] = useState<ViewMode>("cards");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | TurbineStatus>("all");
  const [selected, setSelected] = useState<WindTurbine | null>(null);
  const filtered = useMemo(() => turbines.filter((turbine) => {
    const matchesQuery = turbine.id.toLowerCase().includes(query.trim().toLowerCase());
    const matchesStatus = status === "all" || turbine.status === status;
    return matchesQuery && matchesStatus;
  }), [query, status]);

  return (
    <AppShell activePath="/wind-farms">
      <PageHeader
        eyebrow="资产与监测"
        title="华东海上风电场"
        description="384 MW · 64 台 GW165-6.0MW 海上风电机组的运行状态与健康概览"
        breadcrumb={["资产与监测", "风场", windFarm.code]}
        meta={<><StatusBadge value="running" label="场站运行中" tone="success" pulse /><span className="page-meta-text">场站可利用率 96.8% · 数据延迟 12s</span></>}
        actions={<><Button variant="secondary"><Boxes size={15} /> 管理视图</Button><Button variant="primary"><Plus size={15} /> 新建巡检</Button></>}
      />

      <section className="farm-summary-bar">
        <div><small>当前功率</small><strong>{windFarm.currentPowerMW.toFixed(1)} <span>MW</span></strong></div>
        <div><small>今日发电</small><strong>{windFarm.todayGenerationGWh.toFixed(2)} <span>GWh</span></strong></div>
        <div><small>运行机组</small><strong>{turbines.filter((item) => item.status === "running").length} <span>/ 64</span></strong></div>
        <div><small>平均健康度</small><strong>{windFarm.averageHealthScore.toFixed(1)} <span>%</span></strong></div>
        <div><small>活跃告警</small><strong className="critical-text">{windFarm.activeAlarmCount}</strong></div>
        <div><small>AI Missions</small><strong className="info-text">{windFarm.activeMissionCount}</strong></div>
      </section>

      <section className="data-toolbar">
        <div className="search-field"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索机组编号…" aria-label="搜索机组" /></div>
        <select className="select-field" value={status} onChange={(event) => setStatus(event.target.value as "all" | TurbineStatus)} aria-label="按状态筛选">
          <option value="all">全部状态</option><option value="running">运行</option><option value="warning">预警</option><option value="critical">故障</option><option value="maintenance">维护</option><option value="offline">离线</option>
        </select>
        <Button variant="secondary"><SlidersHorizontal size={14} /> 更多筛选</Button>
        <span className="toolbar-result">显示 {filtered.length} / {turbines.length} 台机组</span>
        <div className="view-switcher" aria-label="视图切换">
          <button className={cn(view === "cards" && "active")} onClick={() => setView("cards")} aria-label="卡片视图"><Grid2X2 size={15} /></button>
          <button className={cn(view === "list" && "active")} onClick={() => setView("list")} aria-label="列表视图"><List size={15} /></button>
          <button className={cn(view === "topology" && "active")} onClick={() => setView("topology")} aria-label="拓扑视图"><Network size={15} /></button>
          <button className={cn(view === "map" && "active")} onClick={() => setView("map")} aria-label="地图视图"><Map size={15} /></button>
        </div>
      </section>

      {view === "cards" ? (
        <section className="turbine-card-grid">
          {filtered.map((turbine) => (
            <button className={cn("turbine-card", turbine.id === "WT-023" && "turbine-card--featured")} onClick={() => setSelected(turbine)} key={turbine.id}>
              <span className="turbine-card__header"><span><TowerControl size={15} /><strong>{turbine.id}</strong></span><StatusBadge value={turbine.status} label={statusMeta[turbine.status].label} tone={statusMeta[turbine.status].tone} compact /></span>
              <span className="turbine-card__power"><strong>{turbine.powerMW.toFixed(2)}</strong><small>MW</small></span>
              <span className="turbine-card__metrics"><span><small>风速</small><strong>{turbine.windSpeedMps.toFixed(1)} m/s</strong></span><span><small>健康度</small><strong className={turbine.healthScore < 75 ? "critical-text" : ""}>{turbine.healthScore}</strong></span><span><small>告警</small><strong>{turbine.activeAlarmCount}</strong></span></span>
              <span className="turbine-card__footer"><span>{turbine.currentMissionId ? "AI Mission 进行中" : "运行稳定"}</span><ArrowRight size={13} /></span>
            </button>
          ))}
        </section>
      ) : null}

      {view === "list" ? (
        <Card className="data-table-card">
          <div className="table-scroll"><table className="data-table"><thead><tr><th>机组</th><th>状态</th><th>有功功率</th><th>风速</th><th>转子转速</th><th>健康度</th><th>告警</th><th>当前 Mission</th><th>最近维护</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>
            {filtered.map((turbine) => <tr key={turbine.id} onClick={() => setSelected(turbine)}><td><span className="asset-cell"><span className="asset-icon"><TowerControl size={15} /></span><span><strong>{turbine.id}</strong><small>{turbine.model}</small></span></span></td><td><StatusBadge value={turbine.status} label={statusMeta[turbine.status].label} tone={statusMeta[turbine.status].tone} compact /></td><td><strong>{turbine.powerMW.toFixed(2)} MW</strong></td><td>{turbine.windSpeedMps.toFixed(1)} m/s</td><td>{turbine.rotorSpeedRpm.toFixed(1)} rpm</td><td><HealthBadge score={turbine.healthScore} /></td><td>{turbine.activeAlarmCount}</td><td className="mono">{turbine.currentMissionId ?? "—"}</td><td>{new Date(turbine.lastMaintenanceAt).toLocaleDateString("zh-CN")}</td><td><Button size="icon" variant="ghost" aria-label="更多操作"><MoreHorizontal size={15} /></Button></td></tr>)}
          </tbody></table></div>
        </Card>
      ) : null}

      {view === "topology" ? (
        <Card className="topology-panel">
          <div className="topology-header"><span><Network size={16} /><strong>风场阵列拓扑</strong></span><span className="topology-legend"><i className="summary-dot summary-dot--success" /> 运行 <i className="summary-dot summary-dot--warning" /> 预警 <i className="summary-dot summary-dot--critical" /> 故障</span></div>
          <div className="topology-grid">
            {filtered.map((turbine) => <button className={cn("topology-node", `topology-node--${statusMeta[turbine.status].tone}`, turbine.id === "WT-023" && "topology-node--selected")} key={turbine.id} onClick={() => setSelected(turbine)}><TowerControl size={14} /><strong>{turbine.id}</strong><small>{turbine.powerMW.toFixed(1)} MW · H{turbine.healthScore}</small></button>)}
          </div>
        </Card>
      ) : null}

      {view === "map" ? (
        <Card className="farm-map">
          <div className="farm-map__labels"><span><Map size={15} /> 近海阵列 A 区</span><small>121.3°E · 31.0°N · 示意视图</small></div>
          <div className="farm-map__watermark">EAST CHINA SEA</div>
          {filtered.map((turbine) => <button key={turbine.id} onClick={() => setSelected(turbine)} className={cn("map-node", `map-node--${statusMeta[turbine.status].tone}`)} style={{ left: `${7 + turbine.gridPosition.column * 10.7}%`, top: `${9 + turbine.gridPosition.row * 10.3}%` }} title={`${turbine.id} · ${statusMeta[turbine.status].label}`}><TowerControl size={12} /><span>{turbine.id}</span></button>)}
        </Card>
      ) : null}

      {selected ? <TurbineDrawer turbine={selected} onClose={() => setSelected(null)} /> : null}
    </AppShell>
  );
}
