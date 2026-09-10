"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import {
  Activity,
  Archive,
  Braces,
  ChevronRight,
  Database,
  ExternalLink,
  Lock,
  Radio,
  Search,
  Server,
  TableProperties,
  TowerControl,
} from "lucide-react";
import { StatusBadge } from "@/components/data-display/status-badge";
import { DataTable } from "@/components/data-display/data-table";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import { apiGet, apiPost, OpenVigilApiError } from "@/lib/api-client";
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
import { localizedMetricLabel } from "@/lib/ui-localization";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";

type CatalogEnvelope = {
  data: readonly DataCatalogEntry[];
  meta: {
    count: number;
    total: number;
    deterministic: boolean;
    readOnly: boolean;
    snapshotAt: string | null;
    hierarchy: typeof assetCatalogHierarchy;
    schemaObjects: readonly string[];
    schemaObjectCount: number;
    scadaArchiveCount: number;
  };
};

type PlatformDataGovernanceEnvelope = {
  data_sources: readonly {
    source_id: string;
    display_name: string;
    source_kind: string;
    enabled: boolean;
    policy: Readonly<Record<string, unknown>>;
    secret_configured: boolean;
    updated_at: string;
  }[];
  data_contracts: readonly {
    contract_id: string;
    source_id: string;
    variable: string;
    revision: number;
    contract: Readonly<Record<string, unknown>>;
  }[];
};

type BenchmarkDataset = {
  readonly dataset_version_id: string;
  readonly dataset_id: string;
  readonly version: string;
  readonly status: string;
  readonly manifest: { readonly uri: string; readonly sha256: string };
  readonly archive: {
    readonly size_bytes: number;
    readonly file_count: number;
    readonly content_sha256: string;
    readonly md5: string | null;
    readonly sha256: string | null;
  };
  readonly license: {
    readonly name: string;
    readonly url: string;
    readonly doi: string;
    readonly citation: string;
    readonly attribution: Readonly<Record<string, unknown>>;
  };
  readonly coverage: {
    readonly registered_file_count: number;
    readonly registered_event_count: number;
    readonly farm_count: number;
    readonly asset_count: number;
    readonly train_row_count: number;
    readonly prediction_row_count: number;
    readonly time_point_count: number;
    readonly truth_summary: {
      readonly access: "restricted" | "revealed";
      readonly anomaly_event_count: number | null;
      readonly normal_event_count: number | null;
    };
  };
  readonly layers: Readonly<
    Record<
      string,
      { readonly status: string; readonly event_count?: number; readonly file_count?: number }
    >
  >;
  readonly mapping: {
    readonly total: number;
    readonly enabled: number;
    readonly disabled: number;
    readonly unknown_unit: number;
    readonly failed: number;
  };
  readonly quality: {
    readonly report_count: number;
    readonly completed_count: number;
    readonly failed_count: number;
    readonly mask_count: number;
    readonly raw_values_modified: boolean;
    readonly quality_rule_versions: readonly string[];
    readonly feature_set_versions: readonly string[];
  };
  readonly runs: {
    readonly import: { readonly status: string };
    readonly evaluation: Readonly<Record<string, number>>;
    readonly replay: Readonly<Record<string, number>>;
  };
  readonly created_at: string;
};

type BenchmarkDatasetEnvelope = {
  readonly data: readonly BenchmarkDataset[];
  readonly meta: {
    readonly count: number;
    readonly total: number;
    readonly filtered_total: number;
    readonly offset: number;
    readonly limit: number;
    readonly has_more: boolean;
    readonly next_offset: number | null;
    readonly bounds: Readonly<Record<string, number>>;
  };
};

type BenchmarkReplaySummary = {
  readonly replay_run_id: string;
  readonly status: string;
  readonly online_turbine_id: string;
  readonly replay_anchor_at: string;
  readonly variables: readonly string[];
  readonly variable_count: number;
  readonly variables_truncated: boolean;
};

type BenchmarkEvent = {
  readonly benchmark_event_id: string;
  readonly event_id: number;
  readonly farm: "A" | "B" | "C";
  readonly source_asset_id: string;
  readonly logical_asset_id: string;
  readonly rows: {
    readonly train: number;
    readonly prediction: number;
    readonly total: number;
  };
  readonly truth: {
    readonly access: "restricted" | "revealed";
    readonly event_label: string | null;
  };
  readonly quality: {
    readonly status: string;
    readonly quality_rule_version: string | null;
    readonly feature_set_version: string | null;
    readonly mask_count: number;
    readonly raw_values_modified: boolean;
  };
  readonly evaluation_results: Readonly<Record<string, number>>;
  readonly recent_replays: readonly BenchmarkReplaySummary[];
};

type BenchmarkEventEnvelope = {
  readonly data: readonly BenchmarkEvent[];
  readonly meta: {
    readonly count: number;
    readonly filtered_total: number;
    readonly offset: number;
    readonly limit: number;
    readonly has_more: boolean;
    readonly next_offset: number | null;
    readonly truth_revealed: boolean;
  };
};

type BenchmarkCurveEnvelope = {
  readonly data: readonly {
    readonly observed_at: string;
    readonly value: number;
    readonly unit: string;
    readonly quality: string;
    readonly source_row_id: number | null;
    readonly observed_at_is_synthetic: boolean;
  }[];
  readonly meta: {
    readonly replay_run_id: string;
    readonly variable: string;
    readonly count: number;
    readonly source_point_count: number;
    readonly max_points: number;
    readonly downsample_algorithm: string;
    readonly bounded: boolean;
    readonly raw_csv_loaded: boolean;
    readonly truth_included: boolean;
    readonly time_semantics: string;
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

const productionEmptyHierarchy: CatalogEnvelope["meta"]["hierarchy"] = {
  farm: { id: "unavailable", name: "未加载", turbineCount: 0, capacityMW: 0 },
  focusTurbine: { id: "unavailable", model: "未加载", healthScore: 0 },
  subsystems: [],
};

const categoryLabels: Readonly<Record<DataCatalogCategory, string>> = {
  live: "实时数据",
  archive: "历史归档",
  api: "查询 API",
  schema: "Schema",
  benchmark: "Benchmark",
};

const statusLabels: Readonly<Record<DataCatalogStatus, string>> = {
  ready: "就绪",
  demo: "演示",
  "read-only": "只读",
};

const categoryIcons = {
  live: Radio,
  archive: Archive,
  api: Braces,
  schema: TableProperties,
  benchmark: Activity,
} as const;

function formatCount(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function compactHash(value: string | null): string {
  return value ? `${value.slice(0, 10)}…${value.slice(-8)}` : "—";
}

function summarizeRunCounts(counts: Readonly<Record<string, number>>): string {
  const summary = Object.entries(counts)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([state, count]) => `${state} ${count}`)
    .join(" · ");
  return summary || "尚无运行";
}

function curvePolyline(points: BenchmarkCurveEnvelope["data"]): string {
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

const catalogColumns: readonly LegacyColumnDef<DataCatalogEntry, unknown>[] = [
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

export function DataCenterPage({ runtimeMode }: { runtimeMode: OpenVigilRuntimeMode }) {
  const isProduction = runtimeMode === "production";
  const [category, setCategory] = useState<"all" | DataCatalogCategory>("all");
  const [status, setStatus] = useState<"all" | DataCatalogStatus>("all");
  const [selectedSubsystemKey, setSelectedSubsystemKey] = useState("main-bearing");
  const [sourceId, setSourceId] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [sourceKind, setSourceKind] = useState("opcua");
  const [sourceSecret, setSourceSecret] = useState("");
  const [sourceReason, setSourceReason] = useState("");
  const [contractSourceId, setContractSourceId] = useState("");
  const [contractVariable, setContractVariable] = useState("");
  const [contractJson, setContractJson] = useState(
    '{\n  "label": "Main bearing temperature",\n  "unit": "celsius",\n  "normal_min": -20,\n  "normal_max": 75,\n  "warning_threshold": 80,\n  "critical_threshold": 90\n}',
  );
  const [contractReason, setContractReason] = useState("");
  const [benchmarkQueryText, setBenchmarkQueryText] = useState("");
  const [benchmarkOffset, setBenchmarkOffset] = useState(0);
  const [selectedBenchmarkId, setSelectedBenchmarkId] = useState("");
  const [benchmarkFarm, setBenchmarkFarm] = useState<"all" | "A" | "B" | "C">("all");
  const [benchmarkEventOffset, setBenchmarkEventOffset] = useState(0);
  const [selectedReplayId, setSelectedReplayId] = useState("");
  const [selectedReplayVariable, setSelectedReplayVariable] = useState("");
  const queryClient = useQueryClient();

  const endpoint = useMemo(() => {
    const parameters = new URLSearchParams();
    if (category !== "all") parameters.set("category", category);
    if (status !== "all") parameters.set("status", status);
    const suffix = parameters.toString();
    return `/api/data-catalog${suffix ? `?${suffix}` : ""}`;
  }, [category, status]);

  const catalogQuery = useQuery({
    queryKey: ["data-catalog", endpoint],
    queryFn: ({ signal }) => apiGet<CatalogEnvelope>(endpoint, signal),
    initialData:
      endpoint === "/api/data-catalog"
        ? isProduction
          ? {
              data: [],
              meta: {
                count: 0,
                total: 0,
                deterministic: false,
                readOnly: false,
                snapshotAt: null,
                hierarchy: productionEmptyHierarchy,
                schemaObjects: [],
                schemaObjectCount: 0,
                scadaArchiveCount: 0,
              },
            }
          : initialEnvelope
        : undefined,
    initialDataUpdatedAt: 0,
    placeholderData: (previous) => previous,
  });
  const governanceQuery = useQuery({
    queryKey: ["data-governance"],
    queryFn: ({ signal }) =>
      apiGet<PlatformDataGovernanceEnvelope>("/api/backend/platform/configurations", signal),
    enabled: isProduction,
    retry: false,
  });
  const benchmarkDatasetEndpoint = useMemo(() => {
    const parameters = new URLSearchParams({
      limit: "10",
      offset: String(benchmarkOffset),
    });
    if (benchmarkQueryText.trim()) parameters.set("q", benchmarkQueryText.trim());
    return `/api/backend/benchmarks/datasets?${parameters.toString()}`;
  }, [benchmarkOffset, benchmarkQueryText]);
  const benchmarkDatasetsQuery = useQuery({
    queryKey: ["care-benchmark-datasets", benchmarkDatasetEndpoint],
    queryFn: async ({ signal }) => {
      const payload = await apiGet<BenchmarkDatasetEnvelope>(benchmarkDatasetEndpoint, signal);
      if (
        payload.meta.limit > 50 ||
        payload.data.length > payload.meta.limit ||
        payload.meta.count !== payload.data.length
      ) {
        throw new Error("Benchmark 数据集响应违反服务端分页上限。");
      }
      return payload;
    },
    enabled: isProduction,
    retry: false,
    placeholderData: (previous) => previous,
  });
  const benchmarkDatasets = benchmarkDatasetsQuery.data?.data ?? [];
  const activeBenchmarkId = benchmarkDatasets.some(
    (dataset) => dataset.dataset_version_id === selectedBenchmarkId,
  )
    ? selectedBenchmarkId
    : (benchmarkDatasets[0]?.dataset_version_id ?? "");
  const activeBenchmark = benchmarkDatasets.find(
    (dataset) => dataset.dataset_version_id === activeBenchmarkId,
  );
  const benchmarkEventsEndpoint = useMemo(() => {
    if (!activeBenchmarkId) return "";
    const parameters = new URLSearchParams({
      limit: "12",
      offset: String(benchmarkEventOffset),
    });
    if (benchmarkFarm !== "all") parameters.set("farm", benchmarkFarm);
    return `/api/backend/benchmarks/datasets/${encodeURIComponent(activeBenchmarkId)}/events?${parameters.toString()}`;
  }, [activeBenchmarkId, benchmarkEventOffset, benchmarkFarm]);
  const benchmarkEventsQuery = useQuery({
    queryKey: ["care-benchmark-events", benchmarkEventsEndpoint],
    queryFn: async ({ signal }) => {
      const payload = await apiGet<BenchmarkEventEnvelope>(benchmarkEventsEndpoint, signal);
      if (
        payload.meta.limit > 64 ||
        payload.data.length > payload.meta.limit ||
        payload.meta.count !== payload.data.length
      ) {
        throw new Error("Benchmark 事件响应违反服务端分页上限。");
      }
      return payload;
    },
    enabled: isProduction && Boolean(benchmarkEventsEndpoint),
    retry: false,
    placeholderData: (previous) => previous,
  });
  const benchmarkEvents = benchmarkEventsQuery.data?.data ?? [];
  const replayOptions = benchmarkEvents.flatMap((event) => event.recent_replays);
  const activeReplay =
    replayOptions.find((replay) => replay.replay_run_id === selectedReplayId) ?? replayOptions[0];
  const activeReplayVariable = activeReplay?.variables.includes(selectedReplayVariable)
    ? selectedReplayVariable
    : (activeReplay?.variables[0] ?? "");
  const benchmarkCurveEndpoint =
    activeReplay && activeReplayVariable
      ? `/api/backend/benchmarks/replay-runs/${encodeURIComponent(activeReplay.replay_run_id)}/curve?variable=${encodeURIComponent(activeReplayVariable)}&maxPoints=128`
      : "";
  const benchmarkCurveQuery = useQuery({
    queryKey: ["care-benchmark-curve", benchmarkCurveEndpoint],
    queryFn: async ({ signal }) => {
      const payload = await apiGet<BenchmarkCurveEnvelope>(benchmarkCurveEndpoint, signal);
      if (
        !payload.meta.bounded ||
        payload.meta.raw_csv_loaded ||
        payload.meta.truth_included ||
        payload.data.length > payload.meta.max_points
      ) {
        throw new Error("Benchmark 曲线响应违反降采样或真值隔离合同。");
      }
      return payload;
    },
    enabled: isProduction && Boolean(benchmarkCurveEndpoint),
    retry: false,
    placeholderData: (previous) => previous,
  });
  const sourceMutation = useMutation({
    mutationFn: () => {
      const existing = governanceQuery.data?.data_sources.find(
        (source) => source.source_id === sourceId.trim(),
      );
      return apiPost("/api/backend/platform/data-sources", {
        source_id: sourceId.trim(),
        display_name: sourceName.trim(),
        source_kind: sourceKind,
        enabled: true,
        sequence_required: true,
        max_lateness_seconds: 300,
        max_future_skew_seconds: 120,
        expected_heartbeat_seconds: 60,
        allowed_turbines: [],
        allowed_variables: [],
        secret_reference: sourceSecret.trim() || null,
        expected_updated_at: existing?.updated_at ?? null,
        reason: sourceReason.trim(),
      });
    },
    onSuccess: async () => {
      setSourceReason("");
      setSourceSecret("");
      await queryClient.invalidateQueries({ queryKey: ["data-governance"] });
      await queryClient.invalidateQueries({ queryKey: ["data-catalog"] });
    },
  });
  const contractMutation = useMutation({
    mutationFn: () => {
      const parsed = JSON.parse(contractJson) as unknown;
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error("数据契约必须是 JSON 对象。");
      }
      const current = governanceQuery.data?.data_contracts.find(
        (contract) =>
          contract.source_id === contractSourceId.trim() &&
          contract.variable === contractVariable.trim(),
      );
      return apiPost("/api/backend/platform/data-contracts", {
        source_id: contractSourceId.trim(),
        variable: contractVariable.trim(),
        contract: parsed,
        expected_revision: current?.revision ?? 0,
        reason: contractReason.trim(),
      });
    },
    onSuccess: async () => {
      setContractReason("");
      await queryClient.invalidateQueries({ queryKey: ["data-governance"] });
      await queryClient.invalidateQueries({ queryKey: ["data-catalog"] });
    },
  });

  const hierarchy =
    catalogQuery.data?.meta.hierarchy ??
    (isProduction ? productionEmptyHierarchy : assetCatalogHierarchy);
  const selectedSubsystem =
    hierarchy.subsystems.find((subsystem) => subsystem.key === selectedSubsystemKey) ??
    hierarchy.subsystems[0];
  const entries = catalogQuery.data?.data ?? [];
  const filtered = category !== "all" || status !== "all";
  const scadaArchiveCount =
    catalogQuery.data?.meta.scadaArchiveCount ?? (isProduction ? 0 : 131_072);
  const schemaObjectCount =
    catalogQuery.data?.meta.schemaObjectCount ?? (isProduction ? 0 : schemaObjects.length);
  const catalogTotal = catalogQuery.data?.meta.total ?? (isProduction ? 0 : dataCatalog.length);
  const benchmarkPermissionDenied =
    benchmarkDatasetsQuery.error instanceof OpenVigilApiError &&
    benchmarkDatasetsQuery.error.status === 403;
  const benchmarkShowsPreviousData =
    benchmarkDatasetsQuery.isPlaceholderData ||
    benchmarkEventsQuery.isPlaceholderData ||
    benchmarkCurveQuery.isPlaceholderData;
  const benchmarkCurvePoints = benchmarkCurveQuery.data?.data ?? [];
  const benchmarkCurveLine = curvePolyline(benchmarkCurvePoints);

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/data">
      <PageHeader
        eyebrow="平台治理"
        title="数据中心"
        description="从风场资产树追踪到测点，并审阅实时、归档、API 与 D1 Schema 数据资产。"
        breadcrumb={["平台管理", "数据中心"]}
        meta={
          <>
            <StatusBadge
              value="ready"
              label={isProduction ? "权威数据目录" : "确定性数据 · 只读"}
              tone="success"
            />
            <span className="page-meta-text">
              目录快照{" "}
              {catalogQuery.data?.meta.snapshotAt
                ? new Date(catalogQuery.data.meta.snapshotAt).toLocaleString("zh-CN")
                : "—"}
            </span>
          </>
        }
      />

      <section className={styles.kpis} aria-label="数据目录摘要">
        <Card>
          <span className={styles.kpiIcon}>
            <Database size={18} />
          </span>
          <small>SCADA 归档</small>
          <strong>{formatCount(scadaArchiveCount)}</strong>
          <em>{isProduction ? "TimescaleDB 实际记录" : "64 × 16 × 128"}</em>
        </Card>
        <Card>
          <span className={styles.kpiIcon}>
            <TableProperties size={18} />
          </span>
          <small>数据模型对象</small>
          <strong>{schemaObjectCount}</strong>
          <em>{isProduction ? "PostgreSQL 逻辑对象" : "D1 逻辑对象"}</em>
        </Card>
        <Card>
          <span className={styles.kpiIcon}>
            <TowerControl size={18} />
          </span>
          <small>资产树</small>
          <strong>{hierarchy.farm.turbineCount}</strong>
          <em>台风机 · {hierarchy.subsystems.length} 子系统</em>
        </Card>
        <Card>
          <span className={styles.kpiIcon}>
            <Server size={18} />
          </span>
          <small>目录数据集</small>
          <strong>{catalogTotal}</strong>
          <em>{isProduction ? "查询与受治理配置入口" : "统一只读查询入口"}</em>
        </Card>
      </section>

      <section className={styles.topGrid}>
        <Card className={styles.assetTree}>
          <CardHeader
            eyebrow="资产层级"
            title="风场 → 风机 → 子系统 → 传感器"
            description={
              isProduction
                ? "目录只展示已由真实遥测源写入并保留质量码的测点。"
                : "展开 WT-023 的完整 12 子系统测点目录；其余 63 台机组使用同一资产 Schema。"
            }
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
            <span>{hierarchy.farm.turbineCount} 台风机</span>
          </div>
          <div className={styles.treeBranch}>
            <div className={styles.focusTurbine}>
              <ChevronRight size={14} />
              <div>
                <strong>{hierarchy.focusTurbine.id}</strong>
                <small>
                  {hierarchy.focusTurbine.model} · 健康度 {hierarchy.focusTurbine.healthScore}
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
                    <small>{subsystem.sensors.length} 个传感器</small>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </Card>

        <Card className={styles.sensorPanel}>
          <CardHeader
            eyebrow="传感器检查器"
            title={selectedSubsystem?.name ?? "传感器"}
            description={
              isProduction
                ? "测点来自 TimescaleDB 实际变量；目录不会生成未接入传感器。"
                : "仅 Schema 表示目录中已定义、但当前演示归档没有伪造该测点数据。"
            }
            action={
              selectedSubsystem ? (
                <StatusBadge
                  value={selectedSubsystem.state}
                  label={`健康度 ${selectedSubsystem.healthScore}`}
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
                  <strong>{localizedMetricLabel(sensor.metric)}</strong>
                  <small>
                    {sensor.id} · {sensor.unit}
                  </small>
                </span>
                <StatusBadge
                  value={sensor.source}
                  label={sensor.source === "live-and-archive" ? "实时 + 归档" : "仅数据模型"}
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
            {isProduction
              ? "生产目录仅把已接收、带来源和质量状态的变量标记为实时与归档。"
              : "当前 SCADA 归档只包含 16 个明确声明的指标。目录不会把未接入测点标记为实时，也不会生成虚假测量值。"}
          </p>
        </Card>
      </section>

      {isProduction ? (
        <section className={styles.topGrid} aria-label="数据源与数据契约治理">
          <Card className={styles.assetTree}>
            <CardHeader
              eyebrow="采集源治理"
              title="配置真实数据源"
              description="写入版本化采集策略；凭据只保存 Secret Manager 引用，不进入浏览器响应。"
            />
            <label>
              <span>Source ID</span>
              <input
                value={sourceId}
                onChange={(event) => setSourceId(event.target.value.toLowerCase())}
                placeholder="offshore-opcua-01"
              />
            </label>
            <label>
              <span>显示名称</span>
              <input
                value={sourceName}
                onChange={(event) => setSourceName(event.target.value)}
                placeholder="Offshore OPC UA 01"
              />
            </label>
            <label>
              <span>协议</span>
              <select value={sourceKind} onChange={(event) => setSourceKind(event.target.value)}>
                {["opcua", "mqtt", "iec61400_25", "cms", "weather", "rest"].map((kind) => (
                  <option value={kind} key={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Secret Manager 引用</span>
              <input
                value={sourceSecret}
                onChange={(event) => setSourceSecret(event.target.value)}
                placeholder="vault://openvigil/scada/offshore-opcua-01"
              />
            </label>
            <label>
              <span>变更原因</span>
              <input
                value={sourceReason}
                onChange={(event) => setSourceReason(event.target.value)}
                placeholder="关联采集接入审批单"
              />
            </label>
            {sourceMutation.error instanceof Error ? (
              <div className={styles.errorBanner} role="alert">
                {sourceMutation.error.message}
              </div>
            ) : null}
            <Button
              loading={sourceMutation.isPending}
              disabled={
                sourceId.trim().length < 3 ||
                sourceName.trim().length < 3 ||
                sourceReason.trim().length < 3
              }
              onClick={() => sourceMutation.mutate()}
            >
              保存数据源策略
            </Button>
            <div className={styles.sensorList}>
              {(governanceQuery.data?.data_sources ?? []).map((source) => (
                <div key={source.source_id}>
                  <span className={styles.sensorDot} data-live={source.enabled} />
                  <span>
                    <strong>{source.display_name}</strong>
                    <small>
                      {source.source_id} · {source.source_kind}
                    </small>
                  </span>
                  <StatusBadge
                    value={source.secret_configured ? "secret-bound" : "no-secret"}
                    label={source.secret_configured ? "凭据已托管" : "无凭据"}
                    tone={source.secret_configured ? "success" : "warning"}
                    compact
                  />
                </div>
              ))}
            </div>
          </Card>

          <Card className={styles.sensorPanel}>
            <CardHeader
              eyebrow="Schema 治理"
              title="激活数据契约"
              description="契约经过 Pydantic 校验并以 CAS 修订激活，采集器会立即使用活动契约进行单位、阈值和质量校验。"
            />
            <label>
              <span>Source ID</span>
              <input
                value={contractSourceId}
                onChange={(event) => setContractSourceId(event.target.value.toLowerCase())}
                placeholder="offshore-opcua-01"
              />
            </label>
            <label>
              <span>变量</span>
              <input
                value={contractVariable}
                onChange={(event) => setContractVariable(event.target.value.toLowerCase())}
                placeholder="main_bearing_temperature"
              />
            </label>
            <label>
              <span>契约 JSON</span>
              <textarea
                className="approval-comment"
                value={contractJson}
                onChange={(event) => setContractJson(event.target.value)}
                aria-label="数据契约 JSON"
              />
            </label>
            <label>
              <span>变更原因</span>
              <input
                value={contractReason}
                onChange={(event) => setContractReason(event.target.value)}
                placeholder="关联数据契约审批单"
              />
            </label>
            {contractMutation.error instanceof Error ? (
              <div className={styles.errorBanner} role="alert">
                {contractMutation.error.message}
              </div>
            ) : null}
            <Button
              loading={contractMutation.isPending}
              disabled={
                contractSourceId.trim().length < 3 ||
                contractVariable.trim().length < 2 ||
                contractReason.trim().length < 3
              }
              onClick={() => contractMutation.mutate()}
            >
              激活数据契约修订
            </Button>
            <div className={styles.sensorList}>
              {(governanceQuery.data?.data_contracts ?? []).map((contract) => (
                <div key={contract.contract_id}>
                  <span className={styles.sensorDot} data-live />
                  <span>
                    <strong>{contract.variable}</strong>
                    <small>
                      {contract.source_id} · 修订 {contract.revision}
                    </small>
                  </span>
                  <StatusBadge value="active" label="已激活" tone="success" compact />
                </div>
              ))}
            </div>
          </Card>
        </section>
      ) : null}

      <section id="care-benchmarks" aria-label="CARE 受治理基准数据">
        <Card className={styles.benchmarkPanel}>
          <CardHeader
            eyebrow="CARE Benchmark"
            title="受治理基准数据"
            description="从 PostgreSQL 元数据读取版本、许可证、校验和、映射、质量与运行状态；曲线仅使用服务端有界降采样。"
            action={
              isProduction && benchmarkDatasetsQuery.data ? (
                <span className={styles.resultCount}>
                  {benchmarkDatasetsQuery.data.meta.count} /{" "}
                  {benchmarkDatasetsQuery.data.meta.filtered_total}
                </span>
              ) : null
            }
          />
          {!isProduction ? (
            <div className={styles.benchmarkState} data-state="disabled">
              <Lock size={18} />
              <span>
                <strong>生产数据连接未启用</strong>
                <small>演示模式不会用 fixture 冒充 CARE 导入、评估或回放结果。</small>
              </span>
            </div>
          ) : benchmarkPermissionDenied ? (
            <div className={styles.benchmarkState} data-state="permission" role="alert">
              <Lock size={18} />
              <span>
                <strong>无 Benchmark 数据权限</strong>
                <small>当前身份缺少 benchmark scope；服务端已失败关闭且未返回数据。</small>
              </span>
            </div>
          ) : benchmarkDatasetsQuery.isLoading ? (
            <div className={styles.benchmarkState} aria-busy="true">
              <Activity size={18} />
              <span>
                <strong>正在读取基准元数据…</strong>
                <small>查询使用固定 10 条服务端分页上限。</small>
              </span>
            </div>
          ) : benchmarkDatasetsQuery.isError ? (
            <div className={styles.benchmarkState} data-state="error" role="alert">
              <Activity size={18} />
              <span>
                <strong>基准目录读取失败</strong>
                <small>
                  {benchmarkDatasetsQuery.error instanceof Error
                    ? benchmarkDatasetsQuery.error.message
                    : "生产 API 返回了未知错误。"}
                </small>
              </span>
            </div>
          ) : !benchmarkDatasets.length || !activeBenchmark ? (
            <div className={styles.benchmarkState} data-state="empty">
              <Database size={18} />
              <span>
                <strong>没有匹配的基准数据集</strong>
                <small>调整服务端搜索条件，或先完成受治理数据集登记。</small>
              </span>
            </div>
          ) : (
            <div className={styles.benchmarkBody}>
              <div className={styles.benchmarkToolbar}>
                <label>
                  <span>服务端搜索</span>
                  <input
                    value={benchmarkQueryText}
                    maxLength={100}
                    onChange={(event) => {
                      setBenchmarkQueryText(event.target.value);
                      setBenchmarkOffset(0);
                      setBenchmarkEventOffset(0);
                    }}
                    placeholder="版本、DOI 或许可证"
                  />
                </label>
                <label>
                  <span>数据集版本</span>
                  <select
                    value={activeBenchmarkId}
                    onChange={(event) => {
                      setSelectedBenchmarkId(event.target.value);
                      setBenchmarkEventOffset(0);
                      setSelectedReplayId("");
                      setSelectedReplayVariable("");
                    }}
                  >
                    {benchmarkDatasets.map((dataset) => (
                      <option value={dataset.dataset_version_id} key={dataset.dataset_version_id}>
                        {dataset.dataset_id} {dataset.version}
                      </option>
                    ))}
                  </select>
                </label>
                <span className={styles.paginationControls}>
                  <button
                    type="button"
                    disabled={benchmarkOffset === 0 || benchmarkDatasetsQuery.isFetching}
                    onClick={() => setBenchmarkOffset(Math.max(0, benchmarkOffset - 10))}
                  >
                    上一页
                  </button>
                  <button
                    type="button"
                    disabled={
                      !benchmarkDatasetsQuery.data?.meta.has_more ||
                      benchmarkDatasetsQuery.isFetching
                    }
                    onClick={() =>
                      setBenchmarkOffset(
                        benchmarkDatasetsQuery.data?.meta.next_offset ?? benchmarkOffset,
                      )
                    }
                  >
                    下一页
                  </button>
                </span>
              </div>

              {benchmarkShowsPreviousData ? (
                <div className={styles.staleBanner} role="status">
                  正在刷新；当前暂时显示上一份有界快照，完成后会自动替换。
                </div>
              ) : null}

              <div className={styles.benchmarkIdentity}>
                <div>
                  <span className={styles.benchmarkTitleLine}>
                    <strong>
                      {activeBenchmark.dataset_id} {activeBenchmark.version}
                    </strong>
                    <StatusBadge
                      value={activeBenchmark.status}
                      label={activeBenchmark.status}
                      tone={activeBenchmark.status === "ready" ? "success" : "neutral"}
                      compact
                    />
                  </span>
                  <small>{activeBenchmark.dataset_version_id}</small>
                  <p>{activeBenchmark.license.citation}</p>
                </div>
                <div className={styles.benchmarkLinks}>
                  <a
                    href={`https://doi.org/${activeBenchmark.license.doi}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    DOI {activeBenchmark.license.doi} <ExternalLink size={11} />
                  </a>
                  <a href={activeBenchmark.license.url} target="_blank" rel="noreferrer">
                    {activeBenchmark.license.name} <ExternalLink size={11} />
                  </a>
                </div>
              </div>

              <div className={styles.benchmarkMetrics}>
                <div>
                  <small>覆盖事件 / 场 / 资产</small>
                  <strong>
                    {activeBenchmark.coverage.registered_event_count} /{" "}
                    {activeBenchmark.coverage.farm_count} / {activeBenchmark.coverage.asset_count}
                  </strong>
                  <em>{formatCount(activeBenchmark.coverage.time_point_count)} 个时间点</em>
                </div>
                <div>
                  <small>Train / Prediction</small>
                  <strong>
                    {formatCount(activeBenchmark.coverage.train_row_count)} /{" "}
                    {formatCount(activeBenchmark.coverage.prediction_row_count)}
                  </strong>
                  <em>匿名事件内时间，禁止跨事件排序</em>
                </div>
                <div>
                  <small>映射启用 / 总数</small>
                  <strong>
                    {activeBenchmark.mapping.enabled} / {activeBenchmark.mapping.total}
                  </strong>
                  <em>
                    禁用 {activeBenchmark.mapping.disabled} · 未知单位{" "}
                    {activeBenchmark.mapping.unknown_unit}
                  </em>
                </div>
                <div>
                  <small>质量报告 / Mask</small>
                  <strong>
                    {activeBenchmark.quality.completed_count} /{" "}
                    {formatCount(activeBenchmark.quality.mask_count)}
                  </strong>
                  <em>
                    {activeBenchmark.quality.raw_values_modified ? "原值已变更" : "原始值未改写"} ·
                    失败 {activeBenchmark.quality.failed_count}
                  </em>
                </div>
              </div>

              <div className={styles.benchmarkDetailGrid}>
                <div>
                  <h3>不可变身份</h3>
                  <dl>
                    <div>
                      <dt>Manifest SHA-256</dt>
                      <dd title={activeBenchmark.manifest.sha256}>
                        {compactHash(activeBenchmark.manifest.sha256)}
                      </dd>
                    </div>
                    <div>
                      <dt>Archive SHA-256</dt>
                      <dd title={activeBenchmark.archive.sha256 ?? undefined}>
                        {compactHash(activeBenchmark.archive.sha256)}
                      </dd>
                    </div>
                    <div>
                      <dt>Content SHA-256</dt>
                      <dd title={activeBenchmark.archive.content_sha256}>
                        {compactHash(activeBenchmark.archive.content_sha256)}
                      </dd>
                    </div>
                    <div>
                      <dt>Archive MD5</dt>
                      <dd title={activeBenchmark.archive.md5 ?? undefined}>
                        {compactHash(activeBenchmark.archive.md5)}
                      </dd>
                    </div>
                  </dl>
                </div>
                <div>
                  <h3>数据层</h3>
                  <dl>
                    {Object.entries(activeBenchmark.layers).map(([layer, value]) => (
                      <div key={layer}>
                        <dt>{layer}</dt>
                        <dd>{value.status}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
                <div>
                  <h3>运行状态</h3>
                  <dl>
                    <div>
                      <dt>Import</dt>
                      <dd>{activeBenchmark.runs.import.status}</dd>
                    </div>
                    <div>
                      <dt>Evaluation</dt>
                      <dd>{summarizeRunCounts(activeBenchmark.runs.evaluation)}</dd>
                    </div>
                    <div>
                      <dt>Replay</dt>
                      <dd>{summarizeRunCounts(activeBenchmark.runs.replay)}</dd>
                    </div>
                    <div>
                      <dt>Truth</dt>
                      <dd>{activeBenchmark.coverage.truth_summary.access}</dd>
                    </div>
                  </dl>
                </div>
              </div>

              <div className={styles.benchmarkSubsection}>
                <div className={styles.benchmarkSubheader}>
                  <span>
                    <strong>事件与质量摘要</strong>
                    <small>每页最多 12 个事件；prediction 真值默认受限。</small>
                  </span>
                  <label>
                    <span>风场</span>
                    <select
                      value={benchmarkFarm}
                      onChange={(event) => {
                        setBenchmarkFarm(event.target.value as typeof benchmarkFarm);
                        setBenchmarkEventOffset(0);
                      }}
                    >
                      <option value="all">全部</option>
                      <option value="A">A</option>
                      <option value="B">B</option>
                      <option value="C">C</option>
                    </select>
                  </label>
                  <span className={styles.paginationControls}>
                    <button
                      type="button"
                      disabled={benchmarkEventOffset === 0 || benchmarkEventsQuery.isFetching}
                      onClick={() =>
                        setBenchmarkEventOffset(Math.max(0, benchmarkEventOffset - 12))
                      }
                    >
                      上一页
                    </button>
                    <button
                      type="button"
                      disabled={
                        !benchmarkEventsQuery.data?.meta.has_more || benchmarkEventsQuery.isFetching
                      }
                      onClick={() =>
                        setBenchmarkEventOffset(
                          benchmarkEventsQuery.data?.meta.next_offset ?? benchmarkEventOffset,
                        )
                      }
                    >
                      下一页
                    </button>
                  </span>
                </div>
                {benchmarkEventsQuery.isLoading ? (
                  <div className={styles.benchmarkState} aria-busy="true">
                    正在读取事件摘要…
                  </div>
                ) : benchmarkEventsQuery.isError ? (
                  <div className={styles.benchmarkState} data-state="error" role="alert">
                    事件摘要读取失败；未使用本地或前端 fixture 回退。
                  </div>
                ) : benchmarkEvents.length ? (
                  <div className={styles.benchmarkEventList}>
                    {benchmarkEvents.map((event) => (
                      <article key={event.benchmark_event_id}>
                        <span>
                          <strong>
                            {event.farm}
                            {event.event_id} · {event.logical_asset_id}
                          </strong>
                          <small>
                            {formatCount(event.rows.total)} 行 · train{" "}
                            {formatCount(event.rows.train)} · prediction{" "}
                            {formatCount(event.rows.prediction)}
                          </small>
                        </span>
                        <span>
                          <small>质量</small>
                          <strong>{event.quality.status}</strong>
                          <em>{formatCount(event.quality.mask_count)} masks</em>
                        </span>
                        <span>
                          <small>评估</small>
                          <strong>{summarizeRunCounts(event.evaluation_results)}</strong>
                          <em>{event.recent_replays.length} 个最近回放</em>
                        </span>
                        <StatusBadge
                          value={event.truth.access}
                          label={event.truth.access === "restricted" ? "真值受限" : "真值可见"}
                          tone={event.truth.access === "restricted" ? "neutral" : "warning"}
                          compact
                        />
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className={styles.benchmarkState} data-state="empty">
                    当前筛选没有事件摘要。
                  </div>
                )}
              </div>

              <div className={styles.benchmarkSubsection}>
                <div className={styles.benchmarkSubheader}>
                  <span>
                    <strong>服务端降采样曲线</strong>
                    <small>最多 128 点；浏览器不读取原始 CSV，也不包含 prediction 真值。</small>
                  </span>
                  <label>
                    <span>Replay run</span>
                    <select
                      value={activeReplay?.replay_run_id ?? ""}
                      disabled={!replayOptions.length}
                      onChange={(event) => {
                        setSelectedReplayId(event.target.value);
                        setSelectedReplayVariable("");
                      }}
                    >
                      {!replayOptions.length ? <option value="">无可用回放</option> : null}
                      {replayOptions.map((replay) => (
                        <option value={replay.replay_run_id} key={replay.replay_run_id}>
                          {replay.replay_run_id} · {replay.status}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>变量</span>
                    <select
                      value={activeReplayVariable}
                      disabled={!activeReplay?.variables.length}
                      onChange={(event) => setSelectedReplayVariable(event.target.value)}
                    >
                      {!activeReplay?.variables.length ? <option value="">无变量</option> : null}
                      {activeReplay?.variables.map((variable) => (
                        <option value={variable} key={variable}>
                          {variable}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {benchmarkCurveQuery.isLoading ? (
                  <div className={styles.benchmarkState} aria-busy="true">
                    正在请求降采样曲线…
                  </div>
                ) : benchmarkCurveQuery.isError ? (
                  <div className={styles.benchmarkState} data-state="error" role="alert">
                    曲线读取失败；服务端未回退到原始文件。
                  </div>
                ) : benchmarkCurveLine ? (
                  <div className={styles.curvePanel}>
                    <svg
                      viewBox="0 0 100 40"
                      role="img"
                      aria-label={`${activeReplayVariable} 服务端降采样曲线`}
                    >
                      <polyline points={benchmarkCurveLine} vectorEffect="non-scaling-stroke" />
                    </svg>
                    <span>
                      <strong>{activeReplayVariable}</strong>
                      <small>
                        {benchmarkCurveQuery.data?.meta.count} /{" "}
                        {formatCount(benchmarkCurveQuery.data?.meta.source_point_count ?? 0)} 点 ·{" "}
                        {benchmarkCurveQuery.data?.meta.downsample_algorithm}
                      </small>
                    </span>
                  </div>
                ) : (
                  <div className={styles.benchmarkState} data-state="empty">
                    选择包含持久化样本的回放和变量后显示曲线。
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>
      </section>

      <Card className={styles.catalogPanel}>
        <CardHeader
          eyebrow="数据集目录"
          title="数据集目录"
          description="每个条目均给出新鲜度、质量、保留策略、来源和可执行查询链接。"
          action={
            <span className={styles.resultCount}>
              {catalogQuery.isFetching ? "同步中…" : `${entries.length} / ${catalogTotal}`}
            </span>
          }
        />
        {catalogQuery.isError ? (
          <div className={styles.errorBanner} role="alert">
            API 同步失败；
            {isProduction ? "生产模式不会显示演示目录。" : "目录继续显示最后一次确定性快照。"}
          </div>
        ) : null}
        {catalogQuery.isLoading ? (
          <div className={styles.loadingState}>正在读取数据目录…</div>
        ) : entries.length ? (
          <div className={styles.tableWrap}>
            <DataTable
              data={entries}
              columns={catalogColumns}
              getRowId={(entry) => entry.id}
              initialSorting={[{ id: "dataset", desc: false }]}
              pageSize={6}
              searchTextForRow={(entry) =>
                `${entry.name} ${entry.id} ${entry.source} ${entry.description}`
              }
              searchPlaceholder="搜索名称、ID、来源…"
              filterControls={
                <>
                  <label>
                    <span>分类</span>
                    <select
                      aria-label="筛选数据集分类"
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
                      aria-label="筛选数据集状态"
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
                </>
              }
              bulkActions={[
                {
                  label: "复制数据集 ID",
                  onActivate: (selectedEntries) =>
                    navigator.clipboard.writeText(
                      selectedEntries.map((entry) => entry.id).join("\n"),
                    ),
                },
              ]}
              csvExport={{
                filename: "openvigil-data-catalog.csv",
                columns: [
                  { label: "数据集ID", value: (entry) => entry.id },
                  { label: "名称", value: (entry) => entry.name },
                  { label: "分类", value: (entry) => categoryLabels[entry.category] },
                  { label: "状态", value: (entry) => statusLabels[entry.status] },
                  { label: "记录数", value: (entry) => entry.recordCount },
                  { label: "新鲜度", value: (entry) => entry.freshness },
                  { label: "质量", value: (entry) => entry.quality },
                  { label: "保留策略", value: (entry) => entry.retention },
                  { label: "来源", value: (entry) => entry.source },
                  { label: "查询链接", value: (entry) => entry.queryHref },
                ],
              }}
            />
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
