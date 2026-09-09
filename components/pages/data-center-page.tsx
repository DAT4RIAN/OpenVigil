"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Archive,
  Braces,
  ChevronRight,
  Database,
  ExternalLink,
  Radio,
  Search,
  Server,
  TableProperties,
  TowerControl,
} from "lucide-react";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import {
  PLATFORM_SNAPSHOT_AT,
  assetCatalogHierarchy,
  dataCatalog,
  dataCatalogCategories,
  dataCatalogStatuses,
  schemaObjects,
  type DataCatalogCategory,
  type DataCatalogEntry,
  type DataCatalogStatus,
} from "@/lib/platform-admin-data";
import styles from "./data-center-page.module.css";

type CatalogEnvelope = {
  data: readonly DataCatalogEntry[];
  meta: {
    count: number;
    total: number;
    deterministic: true;
    readOnly: true;
    snapshotAt: string;
    hierarchy: typeof assetCatalogHierarchy;
    schemaObjects: readonly string[];
    schemaObjectCount: number;
    scadaArchiveCount: number;
  };
};

const initialEnvelope: CatalogEnvelope = {
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

const categoryLabels: Readonly<Record<DataCatalogCategory, string>> = {
  live: "实时数据",
  archive: "历史归档",
  api: "查询 API",
  schema: "Schema",
};

const statusLabels: Readonly<Record<DataCatalogStatus, string>> = {
  ready: "READY",
  demo: "DEMO",
  "read-only": "READ ONLY",
};

const categoryIcons = {
  live: Radio,
  archive: Archive,
  api: Braces,
  schema: TableProperties,
} as const;

function formatCount(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function DataCenterPage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<"all" | DataCatalogCategory>("all");
  const [status, setStatus] = useState<"all" | DataCatalogStatus>("all");
  const [selectedSubsystemKey, setSelectedSubsystemKey] = useState("main-bearing");

  const endpoint = useMemo(() => {
    const parameters = new URLSearchParams();
    if (query.trim()) parameters.set("q", query.trim());
    if (category !== "all") parameters.set("category", category);
    if (status !== "all") parameters.set("status", status);
    const suffix = parameters.toString();
    return `/api/data-catalog${suffix ? `?${suffix}` : ""}`;
  }, [category, query, status]);

  const catalogQuery = useQuery({
    queryKey: ["data-catalog", endpoint],
    queryFn: ({ signal }) => apiGet<CatalogEnvelope>(endpoint, signal),
    initialData: endpoint === "/api/data-catalog" ? initialEnvelope : undefined,
    initialDataUpdatedAt: 0,
    placeholderData: (previous) => previous,
  });

  const hierarchy = catalogQuery.data?.meta.hierarchy ?? assetCatalogHierarchy;
  const selectedSubsystem =
    hierarchy.subsystems.find((subsystem) => subsystem.key === selectedSubsystemKey) ??
    hierarchy.subsystems[0];
  const entries = catalogQuery.data?.data ?? [];
  const filtered = category !== "all" || status !== "all" || Boolean(query.trim());

  return (
    <AppShell activePath="/data">
      <PageHeader
        eyebrow="PLATFORM GOVERNANCE"
        title="数据中心"
        description="从风场资产树追踪到测点，并审阅实时、归档、API 与 D1 Schema 数据资产。"
        breadcrumb={["平台管理", "数据中心"]}
        meta={
          <>
            <StatusBadge value="ready" label="DETERMINISTIC · READ ONLY" tone="success" />
            <span className="page-meta-text">目录快照 2026-08-13 10:30</span>
          </>
        }
      />

      <section className={styles.kpis} aria-label="数据目录摘要">
        <Card>
          <span className={styles.kpiIcon}>
            <Database size={18} />
          </span>
          <small>SCADA ARCHIVE</small>
          <strong>{formatCount(catalogQuery.data?.meta.scadaArchiveCount ?? 131_072)}</strong>
          <em>64 × 16 × 128</em>
        </Card>
        <Card>
          <span className={styles.kpiIcon}>
            <TableProperties size={18} />
          </span>
          <small>SCHEMA OBJECTS</small>
          <strong>{catalogQuery.data?.meta.schemaObjectCount ?? schemaObjects.length}</strong>
          <em>D1 逻辑对象</em>
        </Card>
        <Card>
          <span className={styles.kpiIcon}>
            <TowerControl size={18} />
          </span>
          <small>ASSET TREE</small>
          <strong>{hierarchy.farm.turbineCount}</strong>
          <em>台风机 · {hierarchy.subsystems.length} 子系统</em>
        </Card>
        <Card>
          <span className={styles.kpiIcon}>
            <Server size={18} />
          </span>
          <small>CATALOG DATASETS</small>
          <strong>{catalogQuery.data?.meta.total ?? dataCatalog.length}</strong>
          <em>统一只读查询入口</em>
        </Card>
      </section>

      <section className={styles.topGrid}>
        <Card className={styles.assetTree}>
          <CardHeader
            eyebrow="ASSET HIERARCHY"
            title="WindFarm → Turbine → Subsystem → Sensor"
            description="展开 WT-023 的完整 12 子系统测点目录；其余 63 台机组使用同一资产 Schema。"
          />
          <div className={styles.treeRoot}>
            <span className={styles.treeNodeIcon}>
              <Database size={15} />
            </span>
            <div>
              <strong>{hierarchy.farm.name}</strong>
              <small>
                {hierarchy.farm.id} · {hierarchy.farm.capacityMW} MW
              </small>
            </div>
            <span>{hierarchy.farm.turbineCount} turbines</span>
          </div>
          <div className={styles.treeBranch}>
            <div className={styles.focusTurbine}>
              <ChevronRight size={14} />
              <div>
                <strong>{hierarchy.focusTurbine.id}</strong>
                <small>
                  {hierarchy.focusTurbine.model} · Health {hierarchy.focusTurbine.healthScore}
                </small>
              </div>
              <Link href="/turbines/WT-023">资产详情</Link>
            </div>
            <div className={styles.subsystemGrid}>
              {hierarchy.subsystems.map((subsystem) => (
                <button
                  type="button"
                  key={subsystem.id}
                  data-selected={selectedSubsystem?.key === subsystem.key}
                  onClick={() => setSelectedSubsystemKey(subsystem.key)}
                >
                  <span>
                    <strong>{subsystem.name}</strong>
                    <small>{subsystem.key}</small>
                  </span>
                  <span>
                    <b>{subsystem.healthScore}</b>
                    <small>{subsystem.sensors.length} sensors</small>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </Card>

        <Card className={styles.sensorPanel}>
          <CardHeader
            eyebrow="SENSOR INSPECTOR"
            title={selectedSubsystem?.name ?? "传感器"}
            description="schema-only 表示目录中已定义、但当前演示归档没有伪造该测点数据。"
            action={
              selectedSubsystem ? (
                <StatusBadge
                  value={selectedSubsystem.state}
                  label={`HEALTH ${selectedSubsystem.healthScore}`}
                  tone={selectedSubsystem.healthScore < 75 ? "critical" : "success"}
                />
              ) : null
            }
          />
          <div className={styles.sensorList}>
            {selectedSubsystem?.sensors.map((sensor) => (
              <div key={sensor.id}>
                <span
                  className={styles.sensorDot}
                  data-live={sensor.source === "live-and-archive"}
                />
                <span>
                  <strong>{sensor.metric}</strong>
                  <small>
                    {sensor.id} · {sensor.unit}
                  </small>
                </span>
                <StatusBadge
                  value={sensor.source}
                  label={sensor.source === "live-and-archive" ? "LIVE + ARCHIVE" : "SCHEMA ONLY"}
                  tone={sensor.source === "live-and-archive" ? "success" : "neutral"}
                  compact
                />
                {sensor.queryHref ? (
                  <Link href={sensor.queryHref} aria-label={`查询 ${sensor.metric}`}>
                    <ExternalLink size={13} />
                  </Link>
                ) : (
                  <span className={styles.noQuery}>—</span>
                )}
              </div>
            ))}
          </div>
          <p className={styles.boundaryNote}>
            当前 SCADA 归档只包含 16
            个明确声明的指标。目录不会把未接入测点标记为实时，也不会生成虚假测量值。
          </p>
        </Card>
      </section>

      <Card className={styles.catalogPanel}>
        <CardHeader
          eyebrow="DATASET CATALOG"
          title="数据集目录"
          description="每个条目均给出新鲜度、质量、保留策略、来源和可执行查询链接。"
          action={
            <span className={styles.resultCount}>
              {catalogQuery.isFetching
                ? "同步中…"
                : `${entries.length} / ${catalogQuery.data?.meta.total ?? dataCatalog.length}`}
            </span>
          }
        />
        <div className={styles.toolbar}>
          <label className={styles.searchField}>
            <Search size={15} />
            <span className="sr-only">搜索数据集</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索名称、ID、来源…"
              maxLength={100}
            />
          </label>
          <label>
            <span>分类</span>
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value as typeof category)}
            >
              <option value="all">全部分类</option>
              {dataCatalogCategories.map((value) => (
                <option value={value} key={value}>
                  {categoryLabels[value]}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>状态</span>
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value as typeof status)}
            >
              <option value="all">全部状态</option>
              {dataCatalogStatuses.map((value) => (
                <option value={value} key={value}>
                  {statusLabels[value]}
                </option>
              ))}
            </select>
          </label>
        </div>

        {catalogQuery.isError ? (
          <div className={styles.errorBanner} role="alert">
            API 同步失败；目录继续显示最后一次确定性快照。
          </div>
        ) : null}
        {catalogQuery.isLoading ? (
          <div className={styles.loadingState}>正在读取数据目录…</div>
        ) : entries.length ? (
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>数据集</th>
                  <th>分类 / 状态</th>
                  <th>规模</th>
                  <th>Freshness / Quality</th>
                  <th>Retention / Source</th>
                  <th>查询</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const Icon = categoryIcons[entry.category];
                  return (
                    <tr key={entry.id}>
                      <td>
                        <span className={styles.datasetName}>
                          <span>
                            <Icon size={15} />
                          </span>
                          <span>
                            <strong>{entry.name}</strong>
                            <small>{entry.id}</small>
                            <em>{entry.description}</em>
                          </span>
                        </span>
                      </td>
                      <td>
                        <span className={styles.badgeStack}>
                          <span>{categoryLabels[entry.category]}</span>
                          <StatusBadge
                            value={entry.status}
                            label={statusLabels[entry.status]}
                            tone={entry.status === "ready" ? "success" : "neutral"}
                            compact
                          />
                        </span>
                      </td>
                      <td>
                        <strong className={styles.monoValue}>
                          {formatCount(entry.recordCount)}
                        </strong>
                        <small>{entry.schemaObjectCount} schema objects</small>
                      </td>
                      <td>
                        <strong>{entry.freshness}</strong>
                        <small>{entry.quality}</small>
                      </td>
                      <td>
                        <strong>{entry.retention}</strong>
                        <small>{entry.source}</small>
                      </td>
                      <td>
                        <Link className={styles.queryLink} href={entry.queryHref}>
                          {entry.queryLabel} <ExternalLink size={12} />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={<Search size={20} />}
            title="没有匹配的数据集"
            description={filtered ? "调整搜索词、分类或状态过滤后重试。" : "目录当前为空。"}
          />
        )}
      </Card>
    </AppShell>
  );
}
