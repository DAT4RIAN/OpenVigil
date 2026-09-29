"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api-client";
import { createDiagnosisRecords, diagnosisModelMeta } from "@/lib/diagnosis-data";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";
import {
  type StatusFilter,
  type RiskFilter,
  type DiagnosisResponse,
  type BenchmarkDiagnosisEnvelope,
  initialRecords,
} from "./diagnosis-center-support";

export function useDiagnosisCenter({ runtimeMode }: { runtimeMode: OpenVigilRuntimeMode }) {
  const workflow = useDemoWorkflow();
  const isProduction = runtimeMode === "production";
  const [selectedId, setSelectedId] = useState("WT-023");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const [selectedBenchmarkReplayId, setSelectedBenchmarkReplayId] = useState("");
  const [revealBenchmarkTruth, setRevealBenchmarkTruth] = useState(false);
  const benchmarkDiagnosisEndpoint =
    runtimeMode === "production"
      ? [
          "/api/backend/benchmarks/diagnoses?limit=16",
          revealBenchmarkTruth ? "&revealTruth=true" : "",
        ].join("")
      : null;
  const benchmarkDiagnosisQuery = useQuery({
    queryKey: ["care-benchmark-diagnoses", benchmarkDiagnosisEndpoint],
    queryFn: ({ signal }) =>
      apiGet<BenchmarkDiagnosisEnvelope>(benchmarkDiagnosisEndpoint ?? "", signal),
    enabled: Boolean(benchmarkDiagnosisEndpoint),
    staleTime: 0,
  });
  const benchmarkDiagnoses = benchmarkDiagnosisQuery.data?.data ?? [];
  const selectedBenchmarkDiagnosis =
    benchmarkDiagnoses.find((row) => row.replay_run_id === selectedBenchmarkReplayId) ??
    benchmarkDiagnoses[0] ??
    null;

  useEffect(() => {
    const turbineId = new URLSearchParams(window.location.search).get("turbineId")?.toUpperCase();
    if (!turbineId || !/^WT-[A-Z0-9-]+$/.test(turbineId)) return;
    const timer = window.setTimeout(() => setSelectedId(turbineId), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (
      !selectedBenchmarkDiagnosis ||
      selectedBenchmarkDiagnosis.replay_run_id === selectedBenchmarkReplayId
    ) {
      return;
    }
    const timer = window.setTimeout(
      () => setSelectedBenchmarkReplayId(selectedBenchmarkDiagnosis.replay_run_id),
      0,
    );
    return () => window.clearTimeout(timer);
  }, [selectedBenchmarkDiagnosis, selectedBenchmarkReplayId]);

  const endpoint = useMemo(() => {
    const params = new URLSearchParams({ limit: "64", sort: "priority-desc" });
    if (query.trim()) params.set("q", query.trim());
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (riskFilter !== "all") params.set("risk", riskFilter);
    return `/api/diagnoses?${params.toString()}`;
  }, [query, riskFilter, statusFilter]);

  const diagnosisQuery = useQuery({
    queryKey: ["diagnoses", endpoint],
    queryFn: ({ signal }) => apiGet<DiagnosisResponse>(endpoint, signal),
    initialData: {
      data: isProduction ? [] : initialRecords,
      meta: {
        count: isProduction ? 0 : initialRecords.length,
        total: isProduction ? 0 : initialRecords.length,
        filteredTotal: isProduction ? 0 : initialRecords.length,
        // production 初始不携带 fixture 模型声明，等待真实查询返回治理元数据。
        model: isProduction
          ? {
              mode: "pending",
              deterministic: false,
              readOnly: true,
              realInference: false,
              notice: "正在读取生产诊断模型元数据…",
            }
          : diagnosisModelMeta,
      },
    },
    initialDataUpdatedAt: 0,
    staleTime: 0,
  });

  const workflowRecords = useMemo(
    () =>
      createDiagnosisRecords({
        missionStatus: workflow.missionStatus,
        decisionStatus: workflow.decisionStatus,
        workOrderStatus: workflow.workOrderStatus,
      }),
    [workflow.decisionStatus, workflow.missionStatus, workflow.workOrderStatus],
  );
  const featured = workflowRecords[22];
  const records = useMemo(
    () =>
      isProduction
        ? diagnosisQuery.data.data
        : diagnosisQuery.data.data.map((record) =>
            record.turbineId === featured.turbineId ? featured : record,
          ),
    [diagnosisQuery.data.data, featured, isProduction],
  );
  const selected = records.find((record) => record.turbineId === selectedId) ?? records[0] ?? null;

  useEffect(() => {
    if (!selected || selected.turbineId === selectedId) return;
    const timer = window.setTimeout(() => setSelectedId(selected.turbineId), 0);
    return () => window.clearTimeout(timer);
  }, [selected, selectedId]);

  const highRiskCount = records.filter(
    (record) => record.risk === "critical" || record.risk === "high",
  ).length;
  const reviewCount = records.filter((record) => record.status === "awaiting-review").length;
  const topCandidate = selected?.candidates[0] ?? null;
  return {
    isProduction,
    setSelectedId,
    query,
    setQuery,
    statusFilter,
    setStatusFilter,
    riskFilter,
    setRiskFilter,
    setSelectedBenchmarkReplayId,
    revealBenchmarkTruth,
    setRevealBenchmarkTruth,
    benchmarkDiagnosisQuery,
    benchmarkDiagnoses,
    selectedBenchmarkDiagnosis,
    diagnosisQuery,
    records,
    selected,
    highRiskCount,
    reviewCount,
    topCandidate,
  };
}
