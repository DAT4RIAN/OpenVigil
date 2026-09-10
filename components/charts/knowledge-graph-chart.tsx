"use client";

import { useEffect, useRef, useState } from "react";
import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import { init, use as registerECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

registerECharts([GraphChart, TooltipComponent, CanvasRenderer]);

export type KnowledgeGraphChartNode = {
  readonly uid: string;
  readonly type: string;
  readonly entityId: string;
  readonly properties: Record<string, string | number | boolean | null | unknown[]>;
};

export type KnowledgeGraphChartRelationship = {
  readonly uid: string;
  readonly type: string;
  readonly sourceUid: string;
  readonly targetUid: string;
};

const categoryColors: Record<string, string> = {
  WindFarm: "#256d85",
  Turbine: "#17816f",
  Subsystem: "#56a764",
  Sensor: "#70a7b8",
  Alarm: "#d14f4f",
  Anomaly: "#e37a38",
  FailureMode: "#c98a1f",
  Evidence: "#7b69b7",
  Mission: "#3d73c5",
  Decision: "#6658a6",
  WorkOrder: "#935f3d",
  Procedure: "#9b7b52",
  Part: "#68737b",
  Resource: "#708997",
  KnowledgeDocument: "#2f8a8a",
  KnowledgePassage: "#48a3a3",
  KnowledgeCase: "#a36293",
};

function css(name: string, fallback: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function KnowledgeGraphChart({
  nodes,
  relationships,
  rootUid,
  selectedUid,
  onSelect,
}: {
  nodes: readonly KnowledgeGraphChartNode[];
  relationships: readonly KnowledgeGraphChartRelationship[];
  rootUid: string;
  selectedUid?: string;
  onSelect: (uid: string) => void;
}) {
  const elementRef = useRef<HTMLDivElement>(null);
  const [themeRevision, setThemeRevision] = useState(0);

  useEffect(() => {
    const handleTheme = () => setThemeRevision((value) => value + 1);
    window.addEventListener("windops-theme-change", handleTheme);
    return () => window.removeEventListener("windops-theme-change", handleTheme);
  }, []);

  useEffect(() => {
    if (!elementRef.current) return;
    const chart = init(elementRef.current);
    const categories = [...new Set(nodes.map((node) => node.type))].sort();
    chart.setOption({
      animationDuration: 450,
      tooltip: {
        backgroundColor: css("--surface", "#fff"),
        borderColor: css("--border", "#dfe4e7"),
        textStyle: { color: css("--foreground", "#182025"), fontSize: 10 },
        formatter: (params: { dataType?: string; data?: { name?: string; value?: string } }) =>
          params.dataType === "edge"
            ? (params.data?.value ?? "关系")
            : (params.data?.name ?? "实体"),
      },
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          force: { repulsion: 165, edgeLength: [55, 115], gravity: 0.08 },
          categories: categories.map((name) => ({
            name,
            itemStyle: { color: categoryColors[name] ?? "#667680" },
          })),
          data: nodes.map((node) => ({
            id: node.uid,
            name: node.entityId,
            category: categories.indexOf(node.type),
            symbolSize: node.uid === rootUid ? 38 : node.type === "FailureMode" ? 31 : 23,
            itemStyle:
              node.uid === selectedUid
                ? { borderColor: css("--foreground", "#182025"), borderWidth: 3 }
                : { borderColor: css("--surface", "#fff"), borderWidth: 1.5 },
            label: {
              show: node.uid === rootUid || node.type === "FailureMode" || node.uid === selectedUid,
              color: css("--foreground", "#182025"),
              fontSize: 9,
              position: "right",
              formatter:
                node.entityId.length > 24 ? `${node.entityId.slice(0, 22)}…` : node.entityId,
            },
          })),
          links: relationships.map((relationship) => ({
            id: relationship.uid,
            source: relationship.sourceUid,
            target: relationship.targetUid,
            value: relationship.type,
            lineStyle: { color: css("--border-strong", "#aeb8bd"), opacity: 0.72 },
          })),
          emphasis: { focus: "adjacency", lineStyle: { width: 2 } },
        },
      ],
    });
    chart.on("click", (params: unknown) => {
      const candidate = params as { dataType?: string; data?: { id?: string } };
      if (candidate.dataType === "node" && candidate.data?.id) onSelect(candidate.data.id);
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(elementRef.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [nodes, onSelect, relationships, rootUid, selectedUid, themeRevision]);

  return (
    <div
      ref={elementRef}
      role="img"
      aria-label={`知识图谱，共 ${nodes.length} 个实体和 ${relationships.length} 条关系`}
      style={{ height: 560, width: "100%" }}
    />
  );
}
