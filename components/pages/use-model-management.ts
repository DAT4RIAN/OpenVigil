import { useMemo, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { apiGet, apiPost } from "@/lib/api-client";
import { modelRegistry, type ModelKind, type ModelStatus } from "@/lib/platform-admin-data";

import type {
  BenchmarkEvaluationEnvelope,
  BenchmarkEventResultEnvelope,
  ModelEnvelope,
  ModelUploadGrant,
} from "./model-management-contracts";
import {
  initialEnvelope,
  predictiveInputSchema,
  predictiveOutputSchema,
} from "./model-management-support";

export function useModelManagement(runtimeMode: "demo" | "production") {
  const { can } = useOpenVigilIdentity();
  const canManageModels = runtimeMode === "demo" || can("model.manage");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | ModelKind>("all");
  const [status, setStatus] = useState<"all" | ModelStatus>("all");
  const [selectedId, setSelectedId] = useState(modelRegistry[0]?.id ?? "");
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [artifact, setArtifact] = useState<File | null>(null);
  const [registration, setRegistration] = useState({
    modelId: "",
    name: "",
    version: "1.0.0",
    description: "",
    inputSchema: predictiveInputSchema,
    outputSchema: predictiveOutputSchema,
    metrics: '{"validation_set":"required","approval_ticket":"required"}',
  });
  const [mutationState, setMutationState] = useState<{
    busy: boolean;
    error: string | null;
    message: string | null;
  }>({ busy: false, error: null, message: null });

  const endpoint = useMemo(() => {
    const parameters = new URLSearchParams();
    if (query.trim()) parameters.set("q", query.trim());
    if (kind !== "all") parameters.set("kind", kind);
    if (status !== "all") parameters.set("status", status);
    const suffix = parameters.toString();
    return `/api/model-registry${suffix ? `?${suffix}` : ""}`;
  }, [kind, query, status]);

  const registryQuery = useQuery({
    queryKey: ["model-registry", endpoint],
    queryFn: ({ signal }) => apiGet<ModelEnvelope>(endpoint, signal),
    initialData:
      runtimeMode === "demo" && endpoint === "/api/model-registry" ? initialEnvelope : undefined,
    initialDataUpdatedAt: 0,
    placeholderData: (previous) => previous,
  });

  const models = registryQuery.data?.data ?? [];
  const selected = models.find((model) => model.id === selectedId) ?? models[0] ?? null;
  const [selectedEvaluationId, setSelectedEvaluationId] = useState("");
  const [revealEvaluationTruth, setRevealEvaluationTruth] = useState(false);
  const benchmarkEvaluationEndpoint =
    runtimeMode === "production" && selected?.kind === "anomaly"
      ? `/api/backend/benchmarks/evaluations?modelId=${encodeURIComponent(selected.id)}&limit=16`
      : null;
  const benchmarkEvaluationsQuery = useQuery({
    queryKey: ["care-benchmark-evaluations", benchmarkEvaluationEndpoint],
    queryFn: ({ signal }) =>
      apiGet<BenchmarkEvaluationEnvelope>(benchmarkEvaluationEndpoint ?? "", signal),
    enabled: Boolean(benchmarkEvaluationEndpoint),
    staleTime: 0,
  });
  const benchmarkEvaluations = benchmarkEvaluationsQuery.data?.data ?? [];
  const selectedEvaluation =
    benchmarkEvaluations.find(
      (evaluation) => evaluation.evaluation_run_id === selectedEvaluationId,
    ) ??
    benchmarkEvaluations[0] ??
    null;
  const benchmarkResultsEndpoint = selectedEvaluation
    ? `/api/backend/benchmarks/evaluations/${encodeURIComponent(selectedEvaluation.evaluation_run_id)}/results?limit=64&revealTruth=${revealEvaluationTruth}`
    : null;
  const benchmarkResultsQuery = useQuery({
    queryKey: ["care-benchmark-event-results", benchmarkResultsEndpoint],
    queryFn: ({ signal }) =>
      apiGet<BenchmarkEventResultEnvelope>(benchmarkResultsEndpoint ?? "", signal),
    enabled: runtimeMode === "production" && Boolean(benchmarkResultsEndpoint),
    staleTime: 0,
  });

  const registerArtifact = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canManageModels) {
      setMutationState({ busy: false, error: "当前角色没有登记模型制品的权限。", message: null });
      return;
    }
    if (!artifact) {
      setMutationState({ busy: false, error: "请选择模型制品文件。", message: null });
      return;
    }
    setMutationState({ busy: true, error: null, message: null });
    try {
      const inputSchema = JSON.parse(registration.inputSchema) as object;
      const outputSchema = JSON.parse(registration.outputSchema) as object;
      const metrics = JSON.parse(registration.metrics) as object;
      const bytes = await artifact.arrayBuffer();
      const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
        .map((value) => value.toString(16).padStart(2, "0"))
        .join("");
      const extension = artifact.name.split(".").pop()?.toLowerCase();
      const contentType =
        extension === "onnx"
          ? "application/onnx"
          : extension === "json"
            ? "application/json"
            : extension === "zip"
              ? "application/zip"
              : "application/octet-stream";
      const grant = await apiPost<ModelUploadGrant>("/api/backend/models/uploads/presign", {
        model_id: registration.modelId,
        file_name: artifact.name,
        content_type: contentType,
        artifact_sha256: digest,
      });
      const uploaded = await fetch(grant.upload_url, {
        method: "PUT",
        headers: { ...grant.required_headers, "content-type": contentType },
        body: artifact,
      });
      if (!uploaded.ok) throw new Error(`对象存储上传失败（${uploaded.status}）`);
      await apiPost("/api/backend/models", {
        model_id: registration.modelId,
        name: registration.name,
        version: registration.version,
        kind: "predictive",
        description: registration.description,
        artifact_uri: grant.artifact_uri,
        artifact_sha256: digest,
        content_type: contentType,
        input_schema: inputSchema,
        output_schema: outputSchema,
        metrics,
      });
      setRegistrationOpen(false);
      setArtifact(null);
      setSelectedId(registration.modelId);
      setMutationState({ busy: false, error: null, message: "模型制品已校验并登记。" });
      await registryQuery.refetch();
    } catch (error) {
      setMutationState({
        busy: false,
        error: error instanceof Error ? error.message : "模型登记失败。",
        message: null,
      });
    }
  };

  const stageDeployment = async () => {
    if (!canManageModels) {
      setMutationState({ busy: false, error: "当前角色没有创建模型部署的权限。", message: null });
      return;
    }
    if (!selected) return;
    const targetId = window.prompt("输入已由运维配置的推理目标 ID：", "predictive-primary");
    if (!targetId) return;
    const approvalTicket = window.prompt("输入上线审批/变更单号：");
    if (!approvalTicket) return;
    setMutationState({ busy: true, error: null, message: null });
    try {
      await apiPost(`/api/backend/models/${encodeURIComponent(selected.id)}/deployments`, {
        target_id: targetId,
        stage: "production",
        evaluation_gate: { approval_ticket: approvalTicket },
      });
      setMutationState({ busy: false, error: null, message: "部署已进入待激活状态。" });
      await registryQuery.refetch();
    } catch (error) {
      setMutationState({
        busy: false,
        error: error instanceof Error ? error.message : "部署创建失败。",
        message: null,
      });
    }
  };

  const activate = async (deploymentId: string) => {
    if (!canManageModels) {
      setMutationState({ busy: false, error: "当前角色没有激活模型部署的权限。", message: null });
      return;
    }
    const percentageText = window.prompt("本次承载生产流量百分比（1-100）：", "100");
    if (!percentageText) return;
    const trafficPercent = Number(percentageText);
    if (!Number.isInteger(trafficPercent) || trafficPercent < 1 || trafficPercent > 100) {
      setMutationState({ busy: false, error: "流量百分比必须是 1-100 的整数。", message: null });
      return;
    }
    const reason = window.prompt("输入激活原因或变更单说明：");
    if (!reason) return;
    setMutationState({ busy: true, error: null, message: null });
    try {
      await apiPost(`/api/backend/models/deployments/${deploymentId}/activate`, {
        traffic_percent: trafficPercent,
        reason,
      });
      setMutationState({ busy: false, error: null, message: "部署流量已原子切换。" });
      await registryQuery.refetch();
    } catch (error) {
      setMutationState({
        busy: false,
        error: error instanceof Error ? error.message : "激活失败。",
        message: null,
      });
    }
  };

  const rollback = async (deploymentId: string) => {
    if (!canManageModels) {
      setMutationState({ busy: false, error: "当前角色没有回滚模型部署的权限。", message: null });
      return;
    }
    if (!selected) return;
    const reason = window.prompt("输入回滚原因或事件单号：");
    if (!reason) return;
    setMutationState({ busy: true, error: null, message: null });
    try {
      await apiPost(`/api/backend/models/${encodeURIComponent(selected.id)}/rollback`, {
        target_deployment_id: deploymentId,
        reason,
      });
      setMutationState({ busy: false, error: null, message: "已回滚到所选部署并恢复 100% 流量。" });
      await registryQuery.refetch();
    } catch (error) {
      setMutationState({
        busy: false,
        error: error instanceof Error ? error.message : "回滚失败。",
        message: null,
      });
    }
  };

  return {
    canManageModels,
    query,
    setQuery,
    kind,
    setKind,
    status,
    setStatus,
    setSelectedId,
    registrationOpen,
    setRegistrationOpen,
    setArtifact,
    registration,
    setRegistration,
    mutationState,
    setSelectedEvaluationId,
    revealEvaluationTruth,
    setRevealEvaluationTruth,
    registryQuery,
    models,
    selected,
    benchmarkEvaluationsQuery,
    benchmarkEvaluations,
    selectedEvaluation,
    benchmarkResultsQuery,
    registerArtifact,
    stageDeployment,
    activate,
    rollback,
  };
}
