"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
import type { ScadaSeries } from "@/lib/types";
import { useRealtimeChannel } from "@/lib/use-realtime-channel";
import { useProductionEvents } from "@/lib/use-production-events";
import { cn } from "@/lib/utils";
import { localizedMetricLabel } from "@/lib/ui-localization";

const ranges: readonly ScadaHistoryRange[] = ["LIVE", "1H", "6H", "24H", "7D", "30D"];

interface LiveScadaValue {
  readonly seriesId: string;
  readonly turbineId: string;
  readonly metric: string;
  readonly value: number;
  readonly quality: "good" | "uncertain" | "bad";
  readonly isAnomaly: boolean;
}

interface ScadaAsset {
  readonly id: string;
  readonly model: string;
}

const fallbackSnapshot = (turbineId: string): ScadaHistorySnapshot => ({
  data: [],
  meta: {
    count: 0,
    pointCount: 0,
    turbineId,
    range: "24H",
    interval: "—",
    startsAt: new Date(0).toISOString(),
    endsAt: new Date(0).toISOString(),
    snapshotAt: new Date(0).toISOString(),
    deterministic: false,
  },
});

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

function correlation(left: ScadaSeries | undefined, right: ScadaSeries | undefined): number | null {
  if (!left || !right) return null;
  const count = Math.min(left.points.length, right.points.length);
  if (count < 2) return null;
  const leftValues = left.points.slice(-count).map((point) => point.value);
  const rightValues = right.points.slice(-count).map((point) => point.value);
  const leftMean = leftValues.reduce((sum, value) => sum + value, 0) / count;
  const rightMean = rightValues.reduce((sum, value) => sum + value, 0) / count;
  const numerator = leftValues.reduce(
    (sum, value, index) => sum + (value - leftMean) * (rightValues[index] - rightMean),
    0,
  );
  const denominator = Math.sqrt(
    leftValues.reduce((sum, value) => sum + (value - leftMean) ** 2, 0) *
      rightValues.reduce((sum, value) => sum + (value - rightMean) ** 2, 0),
  );
  return denominator === 0 ? null : numerator / denominator;
}

export function ScadaPage({ runtimeMode }: { runtimeMode: "demo" | "production" }) {
  const queryClient = useQueryClient();
  const [turbineId, setTurbineId] = useState(runtimeMode === "demo" ? turbine023.id : "");
  const [range, setRange] = useState<ScadaHistoryRange>("24H");
  const [customOpen, setCustomOpen] = useState(false);
  const [customFrom, setCustomFrom] = useState("2026-08-06");
  const [customTo, setCustomTo] = useState("2026-08-13");
  const [customWindow, setCustomWindow] = useState<{ from: string; to: string } | null>(null);
  const assetQuery = useQuery({
    queryKey: ["scada-assets", runtimeMode],
    queryFn: ({ signal }) =>
      apiGet<{ readonly data: readonly ScadaAsset[] }>("/api/turbines", signal),
    initialData:
      runtimeMode === "demo"
        ? { data: [{ id: turbine023.id, model: turbine023.model }] }
        : undefined,
    enabled: runtimeMode === "production",
  });
  useEffect(() => {
    if (!turbineId && assetQuery.data?.data[0]) {
      const timer = window.setTimeout(() => setTurbineId(assetQuery.data.data[0].id), 0);
      return () => window.clearTimeout(timer);
    }
  }, [assetQuery.data, turbineId]);
  const scadaStream = useRealtimeChannel(
    "scada",
    runtimeMode === "demo" && range === "LIVE" && turbineId === turbine023.id,
  );
  const streamStatus = scadaStream.status;
  const liveFrame = scadaStream.frame;
  const queryParameters = new URLSearchParams({ turbineId, range });
  if (customWindow) {
    queryParameters.set("from", `${customWindow.from}T00:00:00+08:00`);
    queryParameters.set("to", `${customWindow.to}T23:59:59+08:00`);
  }
  const scadaQuery = useQuery({
    queryKey: ["scada-history", turbineId, range, customWindow, runtimeMode],
    queryFn: ({ signal }) =>
      apiGet<ScadaHistorySnapshot>(`/api/scada-history?${queryParameters}`, signal),
    initialData:
      runtimeMode === "demo"
        ? {
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
          }
        : undefined,
    enabled: Boolean(turbineId),
    refetchInterval: runtimeMode === "production" && range === "LIVE" ? 30_000 : false,
    // The 24-hour fixture is an SSR/failure fallback, not fresh data for every range key.
    initialDataUpdatedAt: 0,
    staleTime: 0,
    placeholderData: (previous) => previous,
  });
  const productionStream = useProductionEvents({
    enabled: runtimeMode === "production" && range === "LIVE" && Boolean(turbineId),
    eventTypes: ["scada.sample.accepted"],
    cursorKey: "windops.production-events.scada.v1",
    minimumDispatchIntervalMs: 1_000,
    onReady: () => void queryClient.invalidateQueries({ queryKey: ["scada-history", turbineId] }),
    onEvent: (event) => {
      if (event.aggregate_id === turbineId || event.payload.turbine_id === turbineId) {
        void queryClient.invalidateQueries({ queryKey: ["scada-history", turbineId] });
      }
    },
  });
  const scadaSnapshot = scadaQuery.data ?? fallbackSnapshot(turbineId);
  const availableSeries = useMemo(() => {
    if (
      runtimeMode === "production" ||
      range !== "LIVE" ||
      !liveFrame ||
      !Array.isArray(liveFrame.data.values)
    ) {
      return scadaSnapshot.data;
    }
    const values = liveFrame.data.values as readonly LiveScadaValue[];
    const bySeries = new Map(values.map((value) => [value.seriesId, value]));
    return scadaSnapshot.data.map((series) => {
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
  }, [liveFrame, range, runtimeMode, scadaSnapshot.data]);
  const initial =
    availableSeries.find((item) => item.metric === "main-bearing-vibration-rms") ??
    availableSeries[0];
  const [selectedId, setSelectedId] = useState(initial?.id ?? "");
  const [query, setQuery] = useState("");
  const deepLinkApplied = useRef(false);
  useEffect(() => {
    if (deepLinkApplied.current) return;
    const parameters = new URLSearchParams(window.location.search);
    const requestedTurbineId = parameters.get("turbineId")?.toUpperCase();
    const metric = parameters.get("metric");
    const requestedAssetAvailable = requestedTurbineId
      ? runtimeMode === "demo"
        ? Boolean(getTurbine(requestedTurbineId))
        : Boolean(assetQuery.data?.data.some((asset) => asset.id === requestedTurbineId))
      : true;
    if (runtimeMode === "production" && requestedTurbineId && !assetQuery.data) return;
    if (runtimeMode === "production" && metric && !availableSeries.length) return;
    const matchingSeries = metric
      ? (runtimeMode === "demo" ? scadaSeries : availableSeries).find(
          (series) => series.metric === metric || series.id === metric,
        )
      : undefined;
    const timer = window.setTimeout(() => {
      if (requestedTurbineId && requestedAssetAvailable) setTurbineId(requestedTurbineId);
      if (matchingSeries) setSelectedId(matchingSeries.id);
      deepLinkApplied.current = true;
    }, 0);
    return () => window.clearTimeout(timer);
  }, [assetQuery.data, availableSeries, runtimeMode]);
  const turbine =
    runtimeMode === "demo"
      ? (getTurbine(turbineId) ?? turbine023)
      : (assetQuery.data?.data.find((asset) => asset.id === turbineId) ?? {
          id: turbineId,
          model: "权威资产台账",
        });
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
      <AppShell runtimeMode={runtimeMode} activePath="/scada">
        <EmptyState
          icon={<Activity size={24} />}
          title={
            scadaQuery.isLoading || assetQuery.isLoading ? "正在读取 SCADA" : "SCADA 数据不可用"
          }
          description={
            scadaQuery.isError || assetQuery.isError
              ? "权威时序服务当前不可用，生产模式不会回退到演示曲线。"
              : "所选机组和时段内没有可渲染的受治理测点。"
          }
        />
      </AppShell>
    );
  const threshold = selected.thresholds[0]?.value;
  const activePower = availableSeries.find((item) => item.metric === "active-power");
  const windSpeed = availableSeries.find((item) => item.metric === "wind-speed");
  const rotorSpeed = availableSeries.find((item) => item.metric === "rotor-speed");
  const generatorTemp = availableSeries.find((item) => item.metric === "generator-temperature");
  const bearingVibration = availableSeries.find(
    (item) => item.metric === "main-bearing-vibration-rms",
  );
  const bearingTemperature = availableSeries.find(
    (item) => item.metric === "main-bearing-temperature",
  );
  const anomalyScore = availableSeries.find((item) => item.metric === "anomaly-score");
  const correlationScore = correlation(bearingTemperature, bearingVibration);
  const allPoints = availableSeries.flatMap((series) => series.points);
  const goodQualityPercent = allPoints.length
    ? (allPoints.filter((point) => point.quality === "good").length / allPoints.length) * 100
    : null;

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
    <AppShell runtimeMode={runtimeMode} activePath="/scada">
      <PageHeader
        eyebrow="SCADA 数据平面"
        title="实时监测"
        description={`${turbine.id} · ${turbine.model} · 高频测点、阈值与 AI 事件联合监控`}
        breadcrumb={["资产与监测", "实时监测", turbine.id]}
        meta={
          <>
            <StatusBadge
              value={
                scadaQuery.isError || (runtimeMode === "demo" && streamStatus === "fallback")
                  ? "degraded"
                  : "running"
              }
              label={
                scadaQuery.isError
                  ? runtimeMode === "production"
                    ? "权威时序服务不可用"
                    : "接口降级 · 本地快照"
                  : runtimeMode === "production" && range === "LIVE"
                    ? productionStream.status === "connected"
                      ? `TIMESCALEDB · SSE 游标 ${productionStream.cursor ?? "同步中"}`
                      : "TIMESCALEDB · SSE 重连中"
                    : range === "LIVE" && streamStatus === "connected"
                      ? "WEBSOCKET 实时"
                      : range === "LIVE" && streamStatus === "fallback"
                        ? "WEBSOCKET 回退 · API 快照"
                        : runtimeMode === "production"
                          ? "权威时序数据"
                          : "数据流正常"
              }
              tone={
                scadaQuery.isError || (runtimeMode === "demo" && streamStatus === "fallback")
                  ? "warning"
                  : "success"
              }
              pulse={!scadaQuery.isError}
            />
            <span className="page-meta-text">
              {availableSeries.length} / {availableSeries.length} 测点在线 · 快照{" "}
              {new Date(scadaSnapshot.meta.snapshotAt).toLocaleTimeString("zh-CN", {
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
              if (!customFrom || !customTo || customFrom > customTo) return;
              setCustomWindow({ from: customFrom, to: customTo });
              setCustomOpen(false);
            }}
            disabled={!customFrom || !customTo || customFrom > customTo}
          >
            应用范围
          </Button>
          <small>
            {runtimeMode === "production"
              ? "将按所选起止时间查询权威时序；后端依据跨度自动聚合。"
              : "演示数据会按所选跨度自动采用 15 分钟、1 小时或 4 小时采样。"}
          </small>
        </Card>
      ) : null}

      <section className="scada-control-bar">
        <div className="asset-selector">
          <span>
            <Radio size={15} />
            <small>监测资产</small>
            {runtimeMode === "production" ? (
              <select
                aria-label="选择生产监测资产"
                value={turbineId}
                onChange={(event) => {
                  setTurbineId(event.target.value);
                  setSelectedId("");
                  setCustomWindow(null);
                }}
              >
                {(assetQuery.data?.data ?? []).map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.id}
                  </option>
                ))}
              </select>
            ) : (
              <strong>{turbine.id}</strong>
            )}
          </span>
          <span className="asset-selector__divider" />
          <span>
            <small>数据源</small>
            <strong>
              {selected.sourceId ?? (runtimeMode === "demo" ? "SCADA Gateway 01" : "—")}
            </strong>
          </span>
        </div>
        <div className="range-switcher">
          {ranges.map((item) => (
            <button
              key={item}
              onClick={() => {
                setCustomWindow(null);
                setRange(item);
              }}
              className={cn(range === item && !customWindow && "active")}
            >
              {item}
            </button>
          ))}
        </div>
        <span className="stream-indicator">
          <i />{" "}
          {range === "LIVE"
            ? runtimeMode === "production"
              ? productionStream.status === "connected"
                ? "权威事件驱动快照 · SSE"
                : "权威快照 · 30 秒对账轮询"
              : streamStatus === "connected"
                ? "WebSocket 实时 · 1 秒"
                : "实时快照 · 正在重连"
            : `${customWindow ? "CUSTOM" : range} · ${scadaSnapshot.meta.interval}`}
        </span>
      </section>

      <section className="scada-live-grid">
        <div>
          <span>
            <Wind size={14} /> 风速
          </span>
          <strong>
            {windSpeed?.currentValue.toFixed(1) ?? (runtimeMode === "demo" ? "9.7" : "—")}
            <small>m/s</small>
          </strong>
          <em>正常范围</em>
        </div>
        <div>
          <span>
            <Zap size={14} /> 有功功率
          </span>
          <strong>
            {activePower?.currentValue.toFixed(2) ?? (runtimeMode === "demo" ? "5.34" : "—")}
            <small>MW</small>
          </strong>
          <em>{activePower ? "已接收" : "无测点"}</em>
        </div>
        <div>
          <span>
            <Gauge size={14} /> 转子转速
          </span>
          <strong>
            {rotorSpeed?.currentValue.toFixed(1) ?? (runtimeMode === "demo" ? "11.6" : "—")}
            <small>rpm</small>
          </strong>
          <em>稳定</em>
        </div>
        <div>
          <span>
            <Thermometer size={14} /> 发电机温度
          </span>
          <strong>
            {generatorTemp?.currentValue.toFixed(1) ?? (runtimeMode === "demo" ? "67.3" : "—")}
            <small>°C</small>
          </strong>
          <em>正常</em>
        </div>
        <div className="scada-live--warning">
          <span>
            <Activity size={14} /> 轴承振动
          </span>
          <strong>
            {bearingVibration?.currentValue.toFixed(bearingVibration.precision) ??
              (runtimeMode === "demo" ? "4.81" : "—")}
            <small>{bearingVibration?.unit ?? "mm/s"}</small>
          </strong>
          <em>
            {bearingVibration
              ? signalState(bearingVibration) === "warning"
                ? "超过治理阈值"
                : "治理范围内"
              : "无测点"}
          </em>
        </div>
      </section>

      <section className="scada-layout">
        <div className="scada-chart-stack">
          <Card className="scada-main-chart" id="scada-main-chart">
            <CardHeader
              eyebrow={`${selected.metric.toUpperCase()} · ${customWindow ? "CUSTOM" : range}`}
              title={localizedMetricLabel(selected.metric, selected.label)}
              description={`正常范围 ${selected.normalRange[0]}–${selected.normalRange[1]} ${selected.unit} · 当前 ${selected.currentValue.toFixed(selected.precision)} ${selected.unit}`}
              action={
                <div className="chart-actions">
                  <StatusBadge
                    value={signalState(selected)}
                    label={signalState(selected) === "normal" ? "正常" : "警告"}
                  />
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="全屏"
                    title="将主趋势图切换为浏览器全屏"
                    onClick={() =>
                      void document.getElementById("scada-main-chart")?.requestFullscreen()
                    }
                  >
                    <Maximize2 size={15} />
                  </Button>
                </div>
              }
            />
            <div className="scada-chart-context">
              <span>
                <i className="legend-line legend-line--signal" />
                {localizedMetricLabel(selected.metric, selected.label)}
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
              primaryName={localizedMetricLabel(selected.metric, selected.label)}
            />
          </Card>
          <Card className="scada-correlation">
            <CardHeader
              eyebrow="关联信号"
              title="关联信号趋势"
              description="主轴承温度与振动异常的时间相关性"
              action={
                <span className="correlation-score">
                  相关度 <strong>{correlationScore?.toFixed(2) ?? "—"}</strong>
                </span>
              }
            />
            {bearingTemperature && anomalyScore ? (
              <div className="correlation-chart-grid">
                <div>
                  <span>主轴承温度</span>
                  <TimeSeriesChart
                    data={toChartData(bearingTemperature, range)}
                    height={150}
                    unit={bearingTemperature.unit}
                    threshold={bearingTemperature.thresholds[0]?.value}
                    primaryName={bearingTemperature.label}
                  />
                </div>
                <div>
                  <span>异常得分</span>
                  <TimeSeriesChart
                    data={toChartData(anomalyScore, range)}
                    height={150}
                    unit={anomalyScore.unit}
                    threshold={anomalyScore.thresholds[0]?.value}
                    primaryName={anomalyScore.label}
                  />
                </div>
              </div>
            ) : (
              <EmptyState
                icon={<Activity size={20} />}
                title="关联信号不足"
                description="需要主轴承温度和异常得分测点后才能计算关联趋势。"
              />
            )}
          </Card>
        </div>

        <Card className="signals-panel">
          <div className="signals-panel__header">
            <div>
              <span className="eyebrow">测点变量</span>
              <h2>SCADA 测点</h2>
            </div>
            <span>{availableSeries.length} 个信号</span>
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
                      <strong>{localizedMetricLabel(item.metric, item.label)}</strong>
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
              <i /> 数据质量 {goodQualityPercent?.toFixed(2) ?? "—"}%
            </span>
            <span>{selected.sourceId ?? (runtimeMode === "demo" ? "Gateway 01" : "—")}</span>
          </div>
        </Card>
      </section>

      {runtimeMode === "demo" ? (
        <section className="event-ribbon">
          <span className="event-ribbon__icon">
            <AlarmTriangle size={16} />
          </span>
          <span>
            <small>AI 事件 · 09:14:32</small>
            <strong>振动与温升关联异常持续 37 分钟，已升级为 MISSION-2026-0823</strong>
          </span>
          <Link href="/missions/MISSION-2026-0823">
            查看分析证据 <Activity size={13} />
          </Link>
        </section>
      ) : null}
    </AppShell>
  );
}
