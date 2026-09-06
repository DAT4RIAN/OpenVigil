"use client";

import { useEffect, useRef } from "react";
import { LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
} from "echarts/components";
import { color, graphic, init, use as registerECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

registerECharts([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

export type TimeSeriesPoint = {
  timestamp: string;
  value: number;
  anomaly?: boolean;
  aiEvent?: boolean;
};

function css(name: string, fallback: string) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export function TimeSeriesChart({
  data,
  height = 240,
  unit = "MW",
  threshold,
  secondaryData,
  secondaryName,
  primaryName = "当前值",
  compact = false,
}: {
  data: TimeSeriesPoint[];
  height?: number;
  unit?: string;
  threshold?: number;
  secondaryData?: TimeSeriesPoint[];
  secondaryName?: string;
  primaryName?: string;
  compact?: boolean;
}) {
  const elementRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!elementRef.current) return;
    const chart = init(elementRef.current);
    const text = css("--foreground-muted", "#647179");
    const grid = css("--chart-grid", "#e9edef");
    const primary = css("--primary", "#176b75");
    const critical = css("--critical", "#c84545");
    const info = css("--info", "#3978b9");
    const warning = css("--warning", "#b8790b");

    const anomalies = data.filter((point) => point.anomaly).map((point) => [point.timestamp, point.value]);
    const aiEvents = data.filter((point) => point.aiEvent).map((point) => [point.timestamp, point.value]);

    chart.setOption({
      animationDuration: 450,
      grid: compact
        ? { left: 4, right: 4, top: 6, bottom: 2, containLabel: false }
        : { left: 12, right: 18, top: 36, bottom: 28, containLabel: true },
      legend: compact || !secondaryData
        ? undefined
        : {
            data: [primaryName, secondaryName ?? "对比值"],
            right: 10,
            top: 5,
            textStyle: { color: text, fontSize: 9 },
            itemWidth: 12,
            itemHeight: 3,
          },
      tooltip: compact
        ? undefined
        : {
            trigger: "axis",
            backgroundColor: css("--surface", "#fff"),
            borderColor: css("--border", "#dfe4e7"),
            borderWidth: 1,
            padding: 10,
            textStyle: { color: css("--foreground", "#182025"), fontSize: 10 },
            valueFormatter: (value: unknown) => `${Number(value).toFixed(1)} ${unit}`,
          },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: data.map((point) => point.timestamp),
        axisLine: { lineStyle: { color: grid } },
        axisTick: { show: false },
        axisLabel: compact ? { show: false } : { color: text, fontSize: 9, margin: 10 },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitNumber: compact ? 2 : 4,
        axisLabel: compact ? { show: false } : { color: text, fontSize: 9, formatter: `{value} ${unit}` },
        splitLine: { lineStyle: { color: grid, type: "dashed" } },
      },
      dataZoom: compact
        ? undefined
        : [
            { type: "inside", start: 0, end: 100 },
            { type: "slider", show: false, start: 0, end: 100 },
          ],
      series: [
        {
          name: primaryName,
          type: "line",
          data: data.map((point) => point.value),
          symbol: "none",
          smooth: 0.28,
          lineStyle: { color: primary, width: compact ? 1.5 : 2 },
          areaStyle: {
            color: new graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: color.modifyAlpha(primary, compact ? 0.17 : 0.22) },
              { offset: 1, color: color.modifyAlpha(primary, 0.01) },
            ]),
          },
          markLine: threshold === undefined
            ? undefined
            : {
                silent: true,
                symbol: "none",
                label: compact ? { show: false } : { formatter: `阈值 ${threshold} ${unit}`, color: warning, fontSize: 9, position: "insideEndTop" },
                lineStyle: { color: warning, type: "dashed", width: 1 },
                data: [{ yAxis: threshold }],
              },
          markPoint: compact
            ? undefined
            : {
                symbol: "circle",
                symbolSize: 7,
                label: { show: false },
                data: [
                  ...anomalies.map(([xAxis, yAxis]) => ({ coord: [xAxis, yAxis], itemStyle: { color: critical }, name: "异常" })),
                  ...aiEvents.map(([xAxis, yAxis]) => ({ coord: [xAxis, yAxis], itemStyle: { color: info }, name: "AI 事件" })),
                ],
              },
        },
        ...(secondaryData
          ? [
              {
                name: secondaryName ?? "对比值",
                type: "line" as const,
                data: secondaryData.map((point) => point.value),
                symbol: "none",
                smooth: 0.28,
                lineStyle: { color: info, width: 1.5, type: "dashed" as const },
              },
            ]
          : []),
      ],
    });

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(elementRef.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [compact, data, primaryName, secondaryData, secondaryName, threshold, unit]);

  return <div ref={elementRef} role="img" aria-label={`${primaryName}时间序列图`} style={{ height, width: "100%" }} />;
}
