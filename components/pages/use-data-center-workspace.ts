import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost, OpenVigilApiError } from "@/lib/api-client";
import {
  assetCatalogHierarchy,
  dataCatalog,
  schemaObjects,
  type DataCatalogCategory,
  type DataCatalogStatus,
} from "@/lib/platform-admin-data";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";

import type {
  BenchmarkCurveEnvelope,
  BenchmarkDatasetEnvelope,
  BenchmarkEventEnvelope,
  CatalogEnvelope,
  PlatformDataGovernanceEnvelope,
} from "./data-center-contracts";
import { curvePolyline, initialEnvelope, productionEmptyHierarchy } from "./data-center-support";

export function useDataCenterWorkspace(runtimeMode: OpenVigilRuntimeMode) {
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

  return {
    isProduction,
    category,
    setCategory,
    status,
    setStatus,
    setSelectedSubsystemKey,
    sourceId,
    setSourceId,
    sourceName,
    setSourceName,
    sourceKind,
    setSourceKind,
    sourceSecret,
    setSourceSecret,
    sourceReason,
    setSourceReason,
    contractSourceId,
    setContractSourceId,
    contractVariable,
    setContractVariable,
    contractJson,
    setContractJson,
    contractReason,
    setContractReason,
    benchmarkQueryText,
    setBenchmarkQueryText,
    benchmarkOffset,
    setBenchmarkOffset,
    setSelectedBenchmarkId,
    benchmarkFarm,
    setBenchmarkFarm,
    benchmarkEventOffset,
    setBenchmarkEventOffset,
    setSelectedReplayId,
    setSelectedReplayVariable,
    catalogQuery,
    governanceQuery,
    benchmarkDatasetsQuery,
    benchmarkDatasets,
    activeBenchmarkId,
    activeBenchmark,
    benchmarkEventsQuery,
    benchmarkEvents,
    replayOptions,
    activeReplay,
    activeReplayVariable,
    benchmarkCurveQuery,
    sourceMutation,
    contractMutation,
    hierarchy,
    selectedSubsystem,
    entries,
    filtered,
    scadaArchiveCount,
    schemaObjectCount,
    catalogTotal,
    benchmarkPermissionDenied,
    benchmarkShowsPreviousData,
    benchmarkCurveLine,
  };
}
