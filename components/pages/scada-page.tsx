"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  TriangleAlert as AlarmTriangle,
  CalendarDays,
  Download,
  Gauge,
  Maximize2,
  Radio,
  RefreshCcw,
  Search,
  Thermometer,
  Wind,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { TimeSeriesChart, type TimeSeriesPoint } from "@/components/charts/time-series-chart";
import { getTurbine, scadaSeries, turbine023 } from "@/lib";
import { apiGet } from "@/lib/api-client";
import type { ScadaHistoryRange, ScadaHistorySnapshot } from "@/lib/scada-history";
import type { RealtimeFrame } from "@/lib/realtime-stream";
import type { ScadaSeries } from "@/lib/types";
import { useRealtimeChannel } from "@/lib/use-realtime-channel";
import { cn } from "@/lib/utils";

const ranges: readonly ScadaHistoryRange[] = ["LIVE", "1H", "6H", "24H", "7D", "30D"];

interface LiveScadaValue {
  readonly seriesId: string;
  readonly turbineId: string;
  readonly metric: string;
  readonly value: number;
  readonly quality: "good" | "uncertain" | "bad";
  readonly isAnomaly: boolean;
}

function toChartData(series: ScadaSeries, range: ScadaHistoryRange): TimeSeriesPoint[] {
  return series.points.map((point) => ({
    timestamp: new Date(point.timestamp).toLocaleString("zh-CN", {
      month: range === "7D" || range === "30D" ? "2-digit" : undefined,
      day: range === "7D" || range === "30D" ? "2-digit" : undefined,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }),
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
  const warning = series.thresholds.some((threshold) =>
    threshold.direction === "above"
      ? series.currentValue >= threshold.value
      : series.currentValue <= threshold.value,
  );
  return warning ? "warning" : "normal";
}

export function ScadaPage() {
  const [turbineId, setTurbineId] = useState(turbine023.id);
  const [range, setRange] = useState<ScadaHistoryRange>("24H");
  const [customOpen, setCustomOpen] = useState(false);
  const [customFrom, setCustomFrom] = useState("2026-08-06");
  const [customTo, setCustomTo] = useState("2026-08-13");
  const scadaStream = useRealtimeChannel("scada", range === "LIVE" && turbineId === turbine023.id);
  const streamStatus = scadaStream.status;
  const liveFrame = scadaStream.frame as RealtimeFrame | null;
  const scadaQuery = useQuery({
    queryKey: ["scada-history", turbineId, range],
    queryFn: ({ signal }) =>
      apiGet<ScadaHistorySnapshot>(
        `/api/scada-history?turbineId=${turbineId}&range=${range}`,
        signal,
      ),
    initialData: {
      data: [...scadaSeries],
      meta: {
        count: scadaSeries.length,
        pointCount: scadaSeries.reduce((total, series) => total + series.points.length, 0),
        turbineId,
        range: "24H",
        interval: "15 min",
        startsAt: scadaSeries[0]?.points[0]?.timestamp ?? "2026-08-12T10:30:00+08:00",
        endsAt: "2026-08-13T10:30:00+08:00",
        snapshotAt: "2026-08-13T10:30:00+08:00",
        deterministic: true,
      },
    },
    // The 24-hour fixture is an SSR/failure fallback, not fresh data for every range key.
    initialDataUpdatedAt: 0,
    staleTime: 0,
    placeholderData: (previous) => previous,
  });
  const availableSeries = useMemo(() => {
    if (range !== "LIVE" || !liveFrame || !Array.isArray(liveFrame.data.values)) {
      return scadaQuery.data.data;
    }
    const values = liveFrame.data.values as readonly LiveScadaValue[];
    const bySeries = new Map(values.map((value) => [value.seriesId, value]));
    return scadaQuery.data.data.map((series) => {
      const update = bySeries.get(series.id);
      if (!update) return series;
      return {
        ...series,
        currentValue: update.value,
        points: [
          ...series.points.slice(-11),
          {
            timestamp: liveFrame.emittedAt,
            value: update.value,
            quality: update.quality,
            isAnomaly: update.isAnomaly,
            aiEvent: null,
          },
        ],
      };
    });
  }, [liveFrame, range, scadaQuery.data.data]);
  const initial =
    availableSeries.find((item) => item.metric === "main-bearing-vibration-rms") ??
    availableSeries[0];
  const [selectedId, setSelectedId] = useState(initial?.id ?? "");
  const [query, setQuery] = useState("");
  useEffect(() => {
    const parameters = new URLSearchParams(window.location.search);
    const requestedTurbineId = parameters.get("turbineId")?.toUpperCase();
    const metric = parameters.get("metric");
    const matchingSeries = metric
      ? scadaSeries.find((series) => series.metric === metric || series.id === metric)
      : undefined;
    const timer = window.setTimeout(() => {
      if (requestedTurbineId && getTurbine(requestedTurbineId)) setTurbineId(requestedTurbineId);
      if (matchingSeries) setSelectedId(matchingSeries.id);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const turbine = getTurbine(turbineId) ?? turbine023;
  const selected = availableSeries.find((item) => item.id === selectedId) ?? initial;
  const filtered = useMemo(
    () =>
      availableSeries.filter((item) =>
        `${item.label} ${item.metric}`.toLowerCase().includes(query.toLowerCase()),
      ),
    [availableSeries, query],
  );
  if (!selected)
    return (
      <AppShell activePath="/scada">
        <EmptyState
          icon={<Activity size={24} />}
          title="SCADA 数据不可用"
          description="没有找到可渲染的测点，请检查 Mock Data Service。"
        />
      </AppShell>
    );
  const threshold = selected.thresholds[0]?.value;
  const activePower = availableSeries.find((item) => item.metric === "active-power");
  const windSpeed = availableSeries.find((item) => item.metric === "wind-speed");
  const rotorSpeed = availableSeries.find((item) => item.metric === "rotor-speed");
  const generatorTemp = availableSeries.find((item) => item.metric === "generator-temperature");

  function exportCsv() {
    const rows = [
      "timestamp,value,quality,is_anomaly,ai_event",
      ...selected.points.map((point) =>
        [
          point.timestamp,
          point.value,
          point.quality,
          point.isAnomaly,
          JSON.stringify(point.aiEvent ?? ""),
        ].join(","),
      ),
    ];
    const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${selected.turbineId}-${selected.metric}-${range}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <AppShell activePath="/scada">
      <PageHeader
        eyebrow="SCADA 数据平面"
        title="实时监测"
        description={`${turbine.id} · ${turbine.model} · 高频测点、阈值与 AI 事件联合监控`}
        breadcrumb={["资产与监测", "实时监测", turbine.id]}
        meta={
          <>
            <StatusBadge
              value={scadaQuery.isError || streamStatus === "fallback" ? "degraded" : "running"}
              label={
                scadaQuery.isError
                  ? "接口降级 · 本地快照"
                  : range === "LIVE" && streamStatus === "connected"
                    ? "WEBSOCKET 实时"
                    : range === "LIVE" && streamStatus === "fallback"
                      ? "WEBSOCKET 回退 · API 快照"
                      : "数据流正常"
              }
              tone={scadaQuery.isError || streamStatus === "fallback" ? "warning" : "success"}
              pulse={!scadaQuery.isError && streamStatus !== "fallback"}
            />
            <span className="page-meta-text">
              {availableSeries.length} / {availableSeries.length} 测点在线 · 快照{" "}
              {new Date(scadaQuery.data.meta.snapshotAt).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
              })}
            </span>
          </>
        }
        actions={
          <>
            <Button variant="secondary" onClick={() => setCustomOpen((value) => !value)}>
              <CalendarDays size={15} /> 自定义时段
            </Button>
            <Button variant="secondary" onClick={exportCsv}>
              <Download size={15} /> 导出 CSV
            </Button>
            <Button
              variant="primary"
              loading={scadaQuery.isFetching}
              onClick={() => void scadaQuery.refetch()}
            >
              <RefreshCcw size={15} /> 刷新数据
            </Button>
          </>
        }
      />

      {customOpen ? (
        <Card className="scada-custom-range" role="region" aria-label="自定义 SCADA 时段">
          <label>
            开始日期
            <input
              type="date"
              value={customFrom}
              onChange={(event) => setCustomFrom(event.target.value)}
            />
          </label>
          <span>→</span>
          <label>
            结束日期
            <input
              type="date"
              value={customTo}
              onChange={(event) => setCustomTo(event.target.value)}
            />
          </label>
          <Button
            variant="primary"
            onClick={() => {
              const days = Math.max(
                1,
                Math.ceil(
                  (new Date(customTo).getTime() - new Date(customFrom).getTime()) / 86_400_000,
                ),
              );
              setRange(days <= 1 ? "24H" : days <= 7 ? "7D" : "30D");
              setCustomOpen(false);
            }}
          >
            应用范围
          </Button>
          <small>演示数据会按所选跨度自动采用 15 分钟、1 小时或 4 小时采样。</small>
        </Card>
      ) : null}

      <section className="scada-control-bar">
        <div className="asset-selector">
          <span>
            <Radio size={15} />
            <small>监测资产</small>
            <strong>{turbine023.id}</strong>
          </span>
          <span className="asset-selector__divider" />
          <span>
            <small>数据源</small>
            <strong>SCADA Gateway 01</strong>
          </span>
        </div>
        <div className="range-switcher">
          {ranges.map((item) => (
            <button
              key={item}
              onClick={() => setRange(item)}
              className={cn(range === item && "active")}
            >
              {item}
            </button>
          ))}
        </div>
        <span className="stream-indicator">
          <i />{" "}
          {range === "LIVE"
            ? streamStatus === "connected"
              ? "LIVE WEBSOCKET · 1s"
              : "LIVE SNAPSHOT · reconnecting"
            : `${range} · ${scadaQuery.data.meta.interval}`}
        </span>
      </section>

      <section className="scada-live-grid">
        <div>
          <span>
            <Wind size={14} /> 风速
          </span>
          <strong>
            {windSpeed?.currentValue.toFixed(1) ?? "9.7"}
            <small>m/s</small>
          </strong>
          <em>正常范围</em>
        </div>
        <div>
          <span>
            <Zap size={14} /> 有功功率
          </span>
          <strong>
            {activePower?.currentValue.toFixed(2) ?? "5.34"}
            <small>MW</small>
          </strong>
          <em>89% 额定</em>
        </div>
        <div>
          <span>
            <Gauge size={14} /> 转子转速
          </span>
          <strong>
            {rotorSpeed?.currentValue.toFixed(1) ?? "11.6"}
            <small>rpm</small>
          </strong>
          <em>稳定</em>
        </div>
        <div>
          <span>
            <Thermometer size={14} /> 发电机温度
          </span>
          <strong>
            {generatorTemp?.currentValue.toFixed(1) ?? "67.3"}
            <small>°C</small>
          </strong>
          <em>正常</em>
        </div>
        <div className="scada-live--warning">
          <span>
            <Activity size={14} /> 轴承振动
          </span>
          <strong>
            4.81<small>mm/s</small>
          </strong>
          <em>超过预警阈值</em>
        </div>
      </section>

      <section className="scada-layout">
        <div className="scada-chart-stack">
          <Card className="scada-main-chart">
            <CardHeader
              eyebrow={`${selected.metric.toUpperCase()} · ${range}`}
              title={selected.label}
              description={`正常范围 ${selected.normalRange[0]}–${selected.normalRange[1]} ${selected.unit} · 当前 ${selected.currentValue.toFixed(selected.precision)} ${selected.unit}`}
              action={
                <div className="chart-actions">
                  <StatusBadge
                    value={signalState(selected)}
                    label={signalState(selected) === "normal" ? "NORMAL" : "WARNING"}
                  />
                  <Button size="icon" variant="ghost" aria-label="全屏">
                    <Maximize2 size={15} />
                  </Button>
                </div>
              }
            />
            <div className="scada-chart-context">
              <span>
                <i className="legend-line legend-line--signal" />
                {selected.label}
              </span>
              <span>
                <i className="legend-line legend-line--threshold" />
                告警阈值
              </span>
              <span>
                <i className="legend-marker legend-marker--anomaly" />
                异常点
              </span>
              <span>
                <i className="legend-marker legend-marker--ai" />
                AI 事件
              </span>
            </div>
            <TimeSeriesChart
              data={toChartData(selected, range)}
              height={340}
              unit={selected.unit}
              threshold={threshold}
              primaryName={selected.label}
            />
          </Card>
          <Card className="scada-correlation">
            <CardHeader
              eyebrow="CORRELATED SIGNALS"
              title="关联信号趋势"
              description="主轴承温度与振动异常的时间相关性"
              action={
                <span className="correlation-score">
                  相关度 <strong>0.79</strong>
                </span>
              }
            />
            <div className="correlation-chart-grid">
              <div>
                <span>主轴承温度</span>
                <TimeSeriesChart
                  data={toChartData(
                    availableSeries.find((item) => item.metric === "main-bearing-temperature") ??
                      selected,
                    range,
                  )}
                  height={150}
                  unit="°C"
                  threshold={75}
                  primaryName="主轴承温度"
                />
              </div>
              <div>
                <span>异常得分</span>
                <TimeSeriesChart
                  data={toChartData(
                    availableSeries.find((item) => item.metric === "anomaly-score") ?? selected,
                    range,
                  )}
                  height={150}
                  unit="score"
                  threshold={0.7}
                  primaryName="异常得分"
                />
              </div>
            </div>
          </Card>
        </div>

        <Card className="signals-panel">
          <div className="signals-panel__header">
            <div>
              <span className="eyebrow">VARIABLES</span>
              <h2>SCADA 测点</h2>
            </div>
            <span>{availableSeries.length} signals</span>
          </div>
          <div className="signal-search">
            <Search size={14} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索测点…"
              aria-label="搜索测点"
            />
          </div>
          <div className="signal-list">
            {filtered.length ? (
              filtered.map((item) => {
                const Icon = metricIcon(item.metric);
                const state = signalState(item);
                return (
                  <button
                    className={cn("signal-row", item.id === selected.id && "signal-row--active")}
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <span
                      className={cn("signal-icon", state === "warning" && "signal-icon--warning")}
                    >
                      <Icon size={14} />
                    </span>
                    <span className="signal-row__copy">
                      <strong>{item.label}</strong>
                      <small>{item.metric}</small>
                    </span>
                    <span className="signal-row__value">
                      <strong>{item.currentValue.toFixed(item.precision)}</strong>
                      <small>{item.unit}</small>
                    </span>
                    <i
                      className={cn(
                        "signal-quality",
                        state === "warning" && "signal-quality--warning",
                      )}
                    />
                  </button>
                );
              })
            ) : (
              <EmptyState
                icon={<Search size={20} />}
                title="没有匹配测点"
                description="尝试搜索 Wind、Power、Temperature 或清空条件。"
              />
            )}
          </div>
          <div className="signals-panel__footer">
            <span>
              <i /> 数据质量 99.98%
            </span>
            <span>Gateway 01</span>
          </div>
        </Card>
      </section>

      <section className="event-ribbon">
        <span className="event-ribbon__icon">
          <AlarmTriangle size={16} />
        </span>
        <span>
          <small>AI EVENT · 09:14:32</small>
          <strong>振动与温升关联异常持续 37 分钟，已升级为 MISSION-2026-0823</strong>
        </span>
        <Link href="/missions/MISSION-2026-0823">
          查看分析证据 <Activity size={13} />
        </Link>
      </section>
    </AppShell>
  );
}
