"use client";

import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import { Activity, Archive, Braces, ExternalLink, Radio, TableProperties } from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/data-display/status-badge";
import {
  PLATFORM_SNAPSHOT_AT,
  assetCatalogHierarchy,
  dataCatalog,
  schemaObjects,
  type DataCatalogCategory,
  type DataCatalogEntry,
  type DataCatalogStatus,
} from "@/lib/platform-admin-data";

import styles from "./data-center-page.module.css";
import type { BenchmarkCurveEnvelope, CatalogEnvelope } from "./data-center-contracts";

export const initialEnvelope: CatalogEnvelope = {
  data: dataCatalog,
  meta: {
    count: dataCatalog.length,
    total: dataCatalog.length,
    deterministic: true,
    readOnly: true,
    snapshotAt: PLATFORM_SNAPSHOT_AT,
    hierarchy: assetCatalogHierarchy,
    schemaObjects,
    schemaObjectCount: schemaObjects.length,
    scadaArchiveCount: 131_072,
  },
};

export const productionEmptyHierarchy: CatalogEnvelope["meta"]["hierarchy"] = {
  farm: { id: "unavailable", name: "未加载", turbineCount: 0, capacityMW: 0 },
  focusTurbine: { id: "unavailable", model: "未加载", healthScore: 0 },
  subsystems: [],
};

export const categoryLabels: Readonly<Record<DataCatalogCategory, string>> = {
  live: "实时数据",
  archive: "历史归档",
  api: "查询 API",
  schema: "Schema",
  benchmark: "Benchmark",
};

export const statusLabels: Readonly<Record<DataCatalogStatus, string>> = {
  ready: "就绪",
  demo: "演示",
  "read-only": "只读",
};

export const categoryIcons = {
  live: Radio,
  archive: Archive,
  api: Braces,
  schema: TableProperties,
  benchmark: Activity,
} as const;

export function formatCount(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function compactHash(value: string | null): string {
  return value ? `${value.slice(0, 10)}…${value.slice(-8)}` : "—";
}

export function summarizeRunCounts(counts: Readonly<Record<string, number>>): string {
  const summary = Object.entries(counts)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([state, count]) => `${state} ${count}`)
    .join(" · ");
  return summary || "尚无运行";
}

export function curvePolyline(points: BenchmarkCurveEnvelope["data"]): string {
  if (!points.length) return "";
  const values = points.map((point) => point.value).filter(Number.isFinite);
  if (!values.length) return "";
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const span = maximum - minimum || 1;
  return points
    .map((point, index) => {
      const x = points.length === 1 ? 0 : (index / (points.length - 1)) * 100;
      const y = 38 - ((point.value - minimum) / span) * 34;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export const catalogColumns: readonly LegacyColumnDef<DataCatalogEntry, unknown>[] = [
  {
    id: "dataset",
    header: "数据集",
    accessorFn: (entry) => `${entry.name} ${entry.id}`,
    cell: ({ row }) => {
      const Icon = categoryIcons[row.original.category];
      return (
        <span className={styles.datasetName}>
          <span>
            <Icon size={15} />
          </span>
          <span>
            <strong>{row.original.name}</strong>
            <small>{row.original.id}</small>
            <em>{row.original.description}</em>
          </span>
        </span>
      );
    },
  },
  {
    accessorKey: "category",
    header: "分类 / 状态",
    cell: ({ row }) => (
      <span className={styles.badgeStack}>
        <span>{categoryLabels[row.original.category]}</span>
        <StatusBadge
          value={row.original.status}
          label={statusLabels[row.original.status]}
          tone={row.original.status === "ready" ? "success" : "neutral"}
          compact
        />
      </span>
    ),
  },
  {
    accessorKey: "recordCount",
    header: "规模",
    cell: ({ row }) => (
      <span>
        <strong className={styles.monoValue}>{formatCount(row.original.recordCount)}</strong>
        <small>{row.original.schemaObjectCount} 个数据模型对象</small>
      </span>
    ),
  },
  {
    accessorKey: "freshness",
    header: "新鲜度 / 质量",
    cell: ({ row }) => (
      <span>
        <strong>{row.original.freshness}</strong>
        <small>{row.original.quality}</small>
      </span>
    ),
  },
  {
    accessorKey: "retention",
    header: "保留策略 / 来源",
    cell: ({ row }) => (
      <span>
        <strong>{row.original.retention}</strong>
        <small>{row.original.source}</small>
      </span>
    ),
  },
  {
    id: "query",
    header: "查询",
    enableSorting: false,
    cell: ({ row }) => (
      <Link className={styles.queryLink} href={row.original.queryHref}>
        {row.original.queryLabel} <ExternalLink size={12} />
      </Link>
    ),
  },
];
