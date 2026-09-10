"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  BrainCircuit,
  ExternalLink,
  FileText,
  HeartPulse,
  LoaderCircle,
  Rocket,
  RotateCcw,
  Search,
  ShieldAlert,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { useWindOpsIdentity } from "@/components/providers/identity-provider";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, EmptyState } from "@/components/ui/primitives";
import { apiGet, apiPost } from "@/lib/api-client";
import {
  PLATFORM_SNAPSHOT_AT,
  modelKinds,
  modelRegistry,
  modelStatuses,
  type ModelKind,
  type ModelRegistryEntry,
  type ModelStatus,
} from "@/lib/platform-admin-data";
import styles from "./model-management-page.module.css";

type ModelEnvelope = {
  data: readonly ModelRegistryEntry[];
  meta: {
    count: number;
    total: number;
    deterministic: boolean;
    readOnly: boolean;
    snapshotAt: string;
    realInferenceCount: number;
    embeddingBackedCount: number;
    artifactCount?: number;
    activeDeploymentCount?: number;
    monitoring?: {
      predictionCount: number;
      succeededCount: number;
      failedCount: number;
      successRate: number | null;
      p95LatencyMs: number;
      lastPredictionAt: string | null;
    };
    disclosure: string;
  };
};

type ModelUploadGrant = {
  model_id: string;
  artifact_uri: string;
  upload_url: string;
  required_headers: Record<string, string>;
};

type BenchmarkMetric = {
  readonly name: string;
  readonly value: number;
  readonly unit: string;
  readonly is_release_metric: boolean;
  readonly threshold_value: number | null;
  readonly threshold_direction: string | null;
  readonly passed: boolean | null;
};

type BenchmarkEvaluation = {
  readonly evaluation_run_id: string;
  readonly model: {
    readonly model_id: string;
    readonly version: string;
    readonly kind: string;
    readonly algorithm: string | null;
    readonly evaluation_role: string | null;
    readonly artifact: { readonly present: boolean; readonly sha256: string | null };
  };
  readonly run: {
    readonly kind: string;
    readonly status: string;
    readonly farm: string | null;
    readonly protocol_version: string;
    readonly feature_set_version: string;
    readonly quality_rule_version: string;
    readonly threshold_policy_version: string;
    readonly threshold_policy_sha256: string;
    readonly random_seed: number;
    readonly input_identity_sha256: string;
    readonly prediction_truth_used: boolean | null;
    readonly dependency_identity: Readonly<Record<string, string>> | null;
    readonly invalidated_at: string | null;
  };
  readonly event_accounting: {
    readonly requested: number;
    readonly scored: number;
    readonly failed: number;
    readonly unscorable: number;
  };
  readonly evaluation_artifact: {
    readonly uri: string | null;
    readonly sha256: string | null;
    readonly present: boolean;
    readonly immutable: boolean;
  };
  readonly metrics: readonly BenchmarkMetric[];
  readonly metrics_truncated: boolean;
  readonly server_gate: {
    readonly eligible: boolean;
    readonly reasons: readonly string[];
    readonly release_metric_count: number;
  };
  readonly deployments: readonly {
    readonly deployment_id: string;
    readonly status: string;
    readonly target_id: string;
    readonly authorization_state: "current" | "stale" | "inactive" | "not-authorized-for-run";
  }[];
};

type BenchmarkEvaluationEnvelope = {
  readonly data: readonly BenchmarkEvaluation[];
  readonly meta: {
    readonly count: number;
    readonly filtered_total: number;
    readonly bounds: {
      readonly evaluation_page_max: number;
      readonly metrics_per_evaluation_max: number;
    };
  };
};

type BenchmarkEventResultEnvelope = {
  readonly data: readonly {
    readonly result_id: string;
    readonly event_id: number;
    readonly farm: string;
    readonly status: "scored" | "failed" | "unscorable";
    readonly scorable: boolean;
    readonly anomaly_detected: boolean | null;
    readonly scores: {
      readonly care: number | null;
      readonly coverage: number | null;
      readonly accuracy: number | null;
      readonly reliability: number | null;
      readonly earliness: number | null;
    };
    readonly failure_code: string | null;
    readonly result_sha256: string;
    readonly prediction_artifact: { readonly present: boolean; readonly sha256: string | null };
    readonly truth: {
      readonly access: "restricted" | "revealed";
      readonly event_label: string | null;
      readonly failure_type: string | null;
      readonly description: string | null;
    };
  }[];
  readonly meta: {
    readonly count: number;
    readonly filtered_total: number;
    readonly truth_revealed: boolean;
    readonly truth_reveal_allowed: boolean;
    readonly bounds: { readonly event_result_page_max: number };
  };
};

const predictiveInputSchema = JSON.stringify(
  {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    type: "object",
    additionalProperties: false,
    required: ["turbine_id", "observed_at", "signals"],
    properties: {
      turbine_id: { type: "string" },
      turbine_model: { type: "string" },
      health_score: { type: "number" },
      active_alarm_count: { type: "integer", minimum: 0 },
      observed_at: { type: "string", format: "date-time" },
      signals: { type: "object", additionalProperties: { type: "number" } },
    },
  },
  null,
  2,
);

const predictiveOutputSchema = JSON.stringify(
  {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    type: "object",
    additionalProperties: false,
    required: [
      "component",
      "failure_probability_30d",
      "remaining_useful_life_days",
      "anomaly_score",
      "primary_finding",
    ],
    properties: {
      component: { type: "string" },
      component_health: { type: "number", minimum: 0, maximum: 100 },
      failure_probability_30d: { type: "number", minimum: 0, maximum: 100 },
      remaining_useful_life_days: { type: "number", minimum: 0 },
      anomaly_score: { type: "number", minimum: 0, maximum: 1 },
      primary_finding: { type: "string" },
      trend: { enum: ["improving", "stable", "declining"] },
    },
  },
  null,
  2,
);

const initialEnvelope: ModelEnvelope = {
  data: modelRegistry,
  meta: {
    count: modelRegistry.length,
    total: modelRegistry.length,
    deterministic: true,
    readOnly: true,
    snapshotAt: PLATFORM_SNAPSHOT_AT,
    realInferenceCount: 0,
    embeddingBackedCount: 0,
    disclosure:
      "Registry availability describes demo capability, not the presence of trained weights or hosted inference.",
  },
};

const kindLabels: Readonly<Record<ModelKind, string>> = {
  anomaly: "异常检测",
  predictive: "预测维护",
  health: "健康评分",
  retrieval: "知识检索",
  report: "报告生成",
};

const kindIcons = {
  anomaly: Activity,
  predictive: BarChart3,
  health: HeartPulse,
  retrieval: BrainCircuit,
  report: FileText,
} as const;

export function ModelManagementPage({ runtimeMode }: { runtimeMode: "demo" | "production" }) {
  const { can } = useWindOpsIdentity();
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

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/models">
      <PageHeader
        eyebrow="模型治理"
        title="模型管理"
        description={
          runtimeMode === "production"
            ? "登记经过哈希校验的模型制品，治理部署流量、回滚和在线推理监控。"
            : "审阅 WindOps 当前确定性评分、检索与文档生成能力，以及它们真实的运行边界。"
        }
        breadcrumb={["平台管理", "模型管理"]}
        meta={
          <>
            <StatusBadge
              value={runtimeMode}
              label={runtimeMode === "production" ? "生产模型治理" : "能力披露"}
              tone={runtimeMode === "production" ? "success" : "warning"}
            />
            <span className="page-meta-text">
              {runtimeMode === "production"
                ? "制品哈希 · Schema 门禁 · 灰度流量 · 可审计回滚"
                : "无训练权重 · 无托管推理 · 无真实 embedding"}
            </span>
          </>
        }
        actions={
          runtimeMode === "production" ? (
            <Button
              onClick={() => setRegistrationOpen(true)}
              disabled={mutationState.busy || !canManageModels}
              title={canManageModels ? undefined : "需要 model.manage capability"}
            >
              <Upload size={15} /> 登记模型制品
            </Button>
          ) : undefined
        }
      />

      <section className={styles.disclosure} aria-label="模型能力披露">
        <ShieldAlert size={19} />
        <div>
          <strong>
            {runtimeMode === "production"
              ? "模型执行与应用控制保持隔离"
              : "这是能力注册表，不是生产 ML 模型仓库"}
          </strong>
          <p>{registryQuery.data?.meta.disclosure ?? initialEnvelope.meta.disclosure}</p>
        </div>
        <span>
          真实推理 <b>{registryQuery.data?.meta.realInferenceCount ?? 0}</b>
        </span>
        <span>
          {runtimeMode === "production" ? "活动部署" : "向量嵌入支持"}{" "}
          <b>
            {runtimeMode === "production"
              ? (registryQuery.data?.meta.activeDeploymentCount ?? 0)
              : (registryQuery.data?.meta.embeddingBackedCount ?? 0)}
          </b>
        </span>
      </section>

      {runtimeMode === "production" && !canManageModels ? (
        <div className={styles.errorBanner} role="status" data-capability="model.manage">
          当前身份可审阅模型注册表，但登记、部署、激活和回滚需要运维经理及全局模型授权。
        </div>
      ) : null}

      <section className={styles.kpis} aria-label="模型注册表摘要">
        <Card>
          <small>已注册引擎</small>
          <strong>{registryQuery.data?.meta.total ?? modelRegistry.length}</strong>
          <em>确定性能力</em>
        </Card>
        <Card>
          <small>{runtimeMode === "production" ? "活动部署" : "仅演示"}</small>
          <strong>
            {runtimeMode === "production"
              ? (registryQuery.data?.meta.activeDeploymentCount ?? 0)
              : modelRegistry.filter((model) => model.status === "demo-only").length}
          </strong>
          <em>{runtimeMode === "production" ? "总流量覆盖 100%" : "不可用于真实决策"}</em>
        </Card>
        <Card>
          <small>真实推理</small>
          <strong>{registryQuery.data?.meta.realInferenceCount ?? 0}</strong>
          <em>
            {runtimeMode === "production"
              ? `P95 ${registryQuery.data?.meta.monitoring?.p95LatencyMs ?? 0} ms`
              : "未配置模型服务"}
          </em>
        </Card>
        <Card>
          <small>模型制品</small>
          <strong>{registryQuery.data?.meta.artifactCount ?? 0}</strong>
          <em>{runtimeMode === "production" ? "MinIO + SHA-256" : "无权重与校准包"}</em>
        </Card>
      </section>

      <Card className={styles.toolbar}>
        <label className={styles.searchField}>
          <Search size={15} />
          <span className="sr-only">搜索模型能力</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={100}
            placeholder="搜索模型、输入或输出…"
          />
        </label>
        <label>
          <span>能力类型</span>
          <select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}>
            <option value="all">全部类型</option>
            {modelKinds.map((value) => (
              <option value={value} key={value}>
                {kindLabels[value]}
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
            {modelStatuses.map((value) => (
              <option value={value} key={value}>
                {value === "available"
                  ? "可用"
                  : runtimeMode === "production"
                    ? "待部署"
                    : "仅演示"}
              </option>
            ))}
          </select>
        </label>
        <span className={styles.resultCount}>
          {registryQuery.isFetching
            ? "同步中…"
            : `${models.length} / ${registryQuery.data?.meta.total ?? modelRegistry.length}`}
        </span>
      </Card>

      {registryQuery.isError ? (
        <div className={styles.errorBanner} role="alert">
          {runtimeMode === "production"
            ? "生产模型注册表不可用；未回退到演示数据。"
            : "API 同步失败；继续显示最后一次确定性注册表快照。"}
        </div>
      ) : null}
      {mutationState.error || mutationState.message ? (
        <div className={styles.errorBanner} role="status">
          {mutationState.error ?? mutationState.message}
        </div>
      ) : null}

      <section className={styles.workspace}>
        <Card className={styles.registryList}>
          <CardHeader
            eyebrow="能力注册表"
            title="能力与版本"
            description="选择条目查看输入、输出、指标与限制。"
          />
          {registryQuery.isLoading ? (
            <div className={styles.loadingState}>正在读取模型注册表…</div>
          ) : models.length ? (
            <div className={styles.modelList}>
              {models.map((model) => {
                const Icon = kindIcons[model.kind];
                return (
                  <button
                    type="button"
                    data-selected={selected?.id === model.id}
                    onClick={() => {
                      setSelectedId(model.id);
                      setSelectedEvaluationId("");
                      setRevealEvaluationTruth(false);
                    }}
                    key={model.id}
                  >
                    <span className={styles.modelIcon}>
                      <Icon size={17} />
                    </span>
                    <span>
                      <strong>{model.name}</strong>
                      <small>
                        {model.id} · v{model.version}
                      </small>
                      <em>{model.runtime}</em>
                    </span>
                    <span className={styles.modelState}>
                      <StatusBadge
                        value={model.status}
                        label={
                          model.status === "available"
                            ? "可用"
                            : runtimeMode === "production"
                              ? "待部署"
                              : "仅演示"
                        }
                        tone={model.status === "available" ? "success" : "warning"}
                        compact
                      />
                      <small>{kindLabels[model.kind]}</small>
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={<Search size={20} />}
              title="没有匹配的能力"
              description="调整搜索词、能力类型或状态过滤后重试。"
            />
          )}
        </Card>

        <Card className={styles.detailPanel}>
          {selected ? (
            <>
              <CardHeader
                eyebrow={`${kindLabels[selected.kind]} · v${selected.version}`}
                title={selected.name}
                description={selected.runtime}
                action={
                  <StatusBadge
                    value={selected.lifecycleStatus ?? "deterministic"}
                    label={selected.lifecycleStatus ?? "确定性"}
                    tone={selected.realInference ? "success" : "info"}
                  />
                }
              />

              <div className={styles.boundaries}>
                <span data-enabled={selected.realInference}>
                  <Sparkles size={14} />
                  <span>
                    <small>真实推理</small>
                    <strong>{selected.realInference ? "已连接" : "未连接"}</strong>
                  </span>
                </span>
                <span data-enabled={selected.usesEmbeddings}>
                  <BrainCircuit size={14} />
                  <span>
                    <small>向量嵌入</small>
                    <strong>{selected.usesEmbeddings ? "已连接" : "未连接"}</strong>
                  </span>
                </span>
                <span data-enabled={selected.artifactBacked}>
                  <FileText size={14} />
                  <span>
                    <small>模型制品</small>
                    <strong>{selected.artifactBacked ? "已登记" : "无"}</strong>
                  </span>
                </span>
              </div>

              <div className={styles.ioGrid}>
                <section>
                  <h3>输入</h3>
                  <ul>
                    {selected.inputs.map((value) => (
                      <li key={value}>{value}</li>
                    ))}
                  </ul>
                </section>
                <section>
                  <h3>输出</h3>
                  <ul>
                    {selected.outputs.map((value) => (
                      <li key={value}>{value}</li>
                    ))}
                  </ul>
                </section>
              </div>

              <section className={styles.metrics}>
                <h3>指标与证据</h3>
                <div>
                  {selected.metrics.map((metric) => (
                    <span key={metric.label}>
                      <small>{metric.label}</small>
                      <strong>{metric.value}</strong>
                    </span>
                  ))}
                </div>
              </section>

              <section className={styles.limitation}>
                <ShieldAlert size={16} />
                <div>
                  <strong>能力边界</strong>
                  <p>{selected.limitation}</p>
                </div>
              </section>

              {runtimeMode === "production" ? (
                <section className={styles.deployments}>
                  <div>
                    <h3>部署与流量</h3>
                    <Button
                      variant="secondary"
                      onClick={() => void stageDeployment()}
                      disabled={!canManageModels || mutationState.busy}
                    >
                      <Rocket size={14} /> 创建部署
                    </Button>
                  </div>
                  {selected.deployments?.length ? (
                    selected.deployments.map((deployment) => (
                      <article key={deployment.id}>
                        <span>
                          <strong>{deployment.targetId}</strong>
                          <small>
                            {deployment.status} · {deployment.trafficPercent}% 流量
                          </small>
                        </span>
                        <div>
                          {deployment.status !== "active" ? (
                            <Button
                              variant="secondary"
                              onClick={() => void activate(deployment.id)}
                              disabled={mutationState.busy || !canManageModels}
                            >
                              <Rocket size={13} /> 激活
                            </Button>
                          ) : null}
                          {deployment.status === "inactive" ? (
                            <Button
                              variant="secondary"
                              onClick={() => void rollback(deployment.id)}
                              disabled={mutationState.busy || !canManageModels}
                            >
                              <RotateCcw size={13} /> 回滚至此
                            </Button>
                          ) : null}
                        </div>
                      </article>
                    ))
                  ) : (
                    <p>尚无部署。登记制品后创建部署，激活前不会接收生产流量。</p>
                  )}
                </section>
              ) : null}

              {runtimeMode === "production" && selected.kind === "anomaly" ? (
                <section className={styles.benchmarkGovernance} aria-label="CARE 基准评估治理">
                  <div className={styles.benchmarkHeader}>
                    <div>
                      <span>CARE v6 · 权威评估</span>
                      <h3>异常模型发布证据</h3>
                      <p>数据库指标与不可变制品；服务器门槛不可由页面覆盖。</p>
                    </div>
                    <Button
                      variant="secondary"
                      onClick={() => void benchmarkEvaluationsQuery.refetch()}
                      disabled={benchmarkEvaluationsQuery.isFetching}
                    >
                      <RotateCcw size={13} />
                      {benchmarkEvaluationsQuery.isFetching ? "同步中…" : "刷新评估"}
                    </Button>
                  </div>

                  {benchmarkEvaluationsQuery.isLoading ? (
                    <div className={styles.benchmarkState}>
                      <LoaderCircle size={15} /> 正在读取受治理评估…
                    </div>
                  ) : benchmarkEvaluationsQuery.isError ? (
                    <div className={styles.benchmarkState} data-tone="error" role="alert">
                      <ShieldAlert size={15} /> 评估 API 或权限校验失败；未显示演示指标。
                    </div>
                  ) : !benchmarkEvaluations.length ? (
                    <div className={styles.benchmarkState}>
                      此 anomaly 模型没有可用的 CARE 评估运行；模型不得据此宣称通过发布门槛。
                    </div>
                  ) : selectedEvaluation ? (
                    <>
                      <div className={styles.evaluationTabs} role="list" aria-label="评估运行">
                        {benchmarkEvaluations.map((evaluation) => (
                          <button
                            type="button"
                            key={evaluation.evaluation_run_id}
                            data-selected={
                              evaluation.evaluation_run_id === selectedEvaluation.evaluation_run_id
                            }
                            onClick={() => {
                              setSelectedEvaluationId(evaluation.evaluation_run_id);
                              setRevealEvaluationTruth(false);
                            }}
                          >
                            <strong>{evaluation.model.evaluation_role ?? "未标注角色"}</strong>
                            <small>{evaluation.evaluation_run_id}</small>
                            <StatusBadge
                              value={evaluation.server_gate.eligible ? "passed" : "failed"}
                              label={evaluation.server_gate.eligible ? "门槛通过" : "门槛失败"}
                              tone={evaluation.server_gate.eligible ? "success" : "critical"}
                              compact
                            />
                          </button>
                        ))}
                      </div>

                      <div className={styles.evaluationFacts}>
                        <span>
                          <small>算法 / 类型</small>
                          <strong>
                            {selectedEvaluation.model.algorithm ?? "未登记"} · anomaly
                          </strong>
                        </span>
                        <span>
                          <small>协议 / 风场</small>
                          <strong>
                            {selectedEvaluation.run.protocol_version} ·{" "}
                            {selectedEvaluation.run.farm ?? "多场"}
                          </strong>
                        </span>
                        <span>
                          <small>特征 / 质量</small>
                          <strong>
                            {selectedEvaluation.run.feature_set_version} ·{" "}
                            {selectedEvaluation.run.quality_rule_version}
                          </strong>
                        </span>
                        <span>
                          <small>阈值 / 随机种子</small>
                          <strong>
                            {selectedEvaluation.run.threshold_policy_version} ·{" "}
                            {selectedEvaluation.run.random_seed}
                          </strong>
                        </span>
                      </div>

                      <div
                        className={styles.releaseGate}
                        data-passed={selectedEvaluation.server_gate.eligible}
                      >
                        <ShieldAlert size={15} />
                        <span>
                          <strong>
                            服务器发布门槛：
                            {selectedEvaluation.server_gate.eligible ? "通过" : "未通过"}
                          </strong>
                          <small>
                            {selectedEvaluation.server_gate.reasons.length
                              ? selectedEvaluation.server_gate.reasons.join(" · ")
                              : "不可变评估、事件核算和 release metrics 均满足。"}
                          </small>
                        </span>
                      </div>

                      <div className={styles.accountingGrid}>
                        {Object.entries(selectedEvaluation.event_accounting).map(([key, value]) => (
                          <span
                            key={key}
                            data-alert={(key === "failed" || key === "unscorable") && value > 0}
                          >
                            <small>
                              {key === "requested"
                                ? "请求事件"
                                : key === "scored"
                                  ? "已评分"
                                  : key === "failed"
                                    ? "失败"
                                    : "不可评分"}
                            </small>
                            <strong>{value}</strong>
                          </span>
                        ))}
                      </div>

                      <div className={styles.metricTable}>
                        {selectedEvaluation.metrics.map((metric) => (
                          <span key={metric.name} data-failed={metric.passed === false}>
                            <small>{metric.name}</small>
                            <strong>
                              {metric.value} {metric.unit}
                            </strong>
                            <em>
                              {metric.is_release_metric
                                ? [
                                    "release",
                                    metric.threshold_direction ?? "—",
                                    metric.threshold_value ?? "—",
                                    metric.passed ? "PASS" : "FAIL",
                                  ].join(" · ")
                                : "观察指标"}
                            </em>
                          </span>
                        ))}
                      </div>

                      <div className={styles.artifactStatus}>
                        <span data-missing={!selectedEvaluation.model.artifact.present}>
                          模型制品{" "}
                          {selectedEvaluation.model.artifact.present
                            ? selectedEvaluation.model.artifact.sha256?.slice(0, 12)
                            : "缺失"}
                        </span>
                        <span data-missing={!selectedEvaluation.evaluation_artifact.present}>
                          评估制品{" "}
                          {selectedEvaluation.evaluation_artifact.present
                            ? selectedEvaluation.evaluation_artifact.sha256?.slice(0, 12)
                            : "缺失"}
                        </span>
                        {selectedEvaluation.deployments.map((deployment) => (
                          <span
                            key={deployment.deployment_id}
                            data-missing={deployment.authorization_state === "stale"}
                          >
                            部署 {deployment.deployment_id.slice(0, 12)} ·{" "}
                            {deployment.authorization_state === "current"
                              ? "授权当前"
                              : deployment.authorization_state === "stale"
                                ? "授权已陈旧"
                                : deployment.authorization_state}
                          </span>
                        ))}
                      </div>

                      <div className={styles.resultHeader}>
                        <div>
                          <strong>事件级结果</strong>
                          <small>
                            失败与不可评分事件不会隐藏；提前量是事件评分项，不是经验证 RUL。
                          </small>
                        </div>
                        <Button
                          variant="secondary"
                          onClick={() => setRevealEvaluationTruth((current) => !current)}
                          disabled={
                            benchmarkResultsQuery.isFetching ||
                            !benchmarkResultsQuery.data?.meta.truth_reveal_allowed
                          }
                          title={
                            benchmarkResultsQuery.data?.meta.truth_reveal_allowed
                              ? undefined
                              : "当前身份没有 benchmark_truth 数据范围"
                          }
                        >
                          {revealEvaluationTruth ? "隐藏真值" : "按权限揭示真值"}
                        </Button>
                      </div>
                      {benchmarkResultsQuery.isLoading ? (
                        <div className={styles.benchmarkState}>正在读取事件结果…</div>
                      ) : benchmarkResultsQuery.isError ? (
                        <div className={styles.benchmarkState} data-tone="error" role="alert">
                          事件结果或真值权限请求失败；未回退到 fixture。
                        </div>
                      ) : benchmarkResultsQuery.data?.data.length ? (
                        <div className={styles.eventResults}>
                          {benchmarkResultsQuery.data.data.map((result) => (
                            <article key={result.result_id} data-status={result.status}>
                              <span>
                                <strong>
                                  {result.farm}
                                  {result.event_id} · {result.status}
                                </strong>
                                <small>
                                  {result.failure_code ?? result.result_sha256.slice(0, 12)}
                                </small>
                              </span>
                              <span>
                                <small>CARE / coverage / accuracy</small>
                                <strong>
                                  {result.scores.care ?? "—"} / {result.scores.coverage ?? "—"} /{" "}
                                  {result.scores.accuracy ?? "—"}
                                </strong>
                              </span>
                              <span>
                                <small>真值</small>
                                <strong>
                                  {result.truth.access === "revealed"
                                    ? [
                                        result.truth.event_label ?? "—",
                                        result.truth.failure_type ?? "无故障描述",
                                      ].join(" · ")
                                    : "受限"}
                                </strong>
                              </span>
                            </article>
                          ))}
                        </div>
                      ) : (
                        <div className={styles.benchmarkState}>该评估没有事件级结果。</div>
                      )}
                    </>
                  ) : null}
                </section>
              ) : runtimeMode === "demo" && selected.kind === "anomaly" ? (
                <section className={styles.benchmarkGovernance} aria-label="CARE 基准评估边界">
                  <div className={styles.benchmarkState}>
                    演示模式不会用固定模型卡冒充 CARE 评估、release metric 或服务器门槛。
                  </div>
                </section>
              ) : null}

              <Link className={styles.endpointLink} href={selected.endpoint}>
                打开只读接口 <ExternalLink size={13} />
              </Link>
            </>
          ) : (
            <EmptyState
              icon={<BrainCircuit size={20} />}
              title="选择一项能力"
              description="从左侧注册表选择能力以查看详情。"
            />
          )}
        </Card>
      </section>

      {registrationOpen ? (
        <div className={styles.dialogBackdrop} role="presentation">
          <form
            className={styles.registrationDialog}
            onSubmit={(event) => void registerArtifact(event)}
          >
            <header>
              <div>
                <strong>登记预测模型制品</strong>
                <p>制品将直传对象存储；后端验证对象范围、内容类型和 SHA-256。</p>
              </div>
              <button type="button" onClick={() => setRegistrationOpen(false)} aria-label="关闭">
                <X size={16} />
              </button>
            </header>
            <div className={styles.registrationGrid}>
              <label>
                <span>模型 ID</span>
                <input
                  required
                  pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,63}"
                  value={registration.modelId}
                  onChange={(event) =>
                    setRegistration((current) => ({ ...current, modelId: event.target.value }))
                  }
                />
              </label>
              <label>
                <span>版本</span>
                <input
                  required
                  value={registration.version}
                  onChange={(event) =>
                    setRegistration((current) => ({ ...current, version: event.target.value }))
                  }
                />
              </label>
              <label className={styles.wideField}>
                <span>名称</span>
                <input
                  required
                  value={registration.name}
                  onChange={(event) =>
                    setRegistration((current) => ({ ...current, name: event.target.value }))
                  }
                />
              </label>
              <label className={styles.wideField}>
                <span>制品（ONNX、JSON、ZIP 或二进制包）</span>
                <input
                  required
                  type="file"
                  accept=".onnx,.json,.zip,.bin,application/onnx,application/json,application/zip"
                  onChange={(event) => setArtifact(event.target.files?.[0] ?? null)}
                />
              </label>
              <label className={styles.wideField}>
                <span>治理说明</span>
                <input
                  required
                  minLength={3}
                  value={registration.description}
                  onChange={(event) =>
                    setRegistration((current) => ({
                      ...current,
                      description: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                <span>输入 JSON Schema</span>
                <textarea
                  required
                  rows={14}
                  value={registration.inputSchema}
                  onChange={(event) =>
                    setRegistration((current) => ({
                      ...current,
                      inputSchema: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                <span>输出 JSON Schema</span>
                <textarea
                  required
                  rows={14}
                  value={registration.outputSchema}
                  onChange={(event) =>
                    setRegistration((current) => ({
                      ...current,
                      outputSchema: event.target.value,
                    }))
                  }
                />
              </label>
              <label className={styles.wideField}>
                <span>验证指标 JSON</span>
                <textarea
                  required
                  rows={3}
                  value={registration.metrics}
                  onChange={(event) =>
                    setRegistration((current) => ({ ...current, metrics: event.target.value }))
                  }
                />
              </label>
            </div>
            <footer>
              <Button type="button" variant="secondary" onClick={() => setRegistrationOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={mutationState.busy || !canManageModels}>
                {mutationState.busy ? <LoaderCircle size={14} /> : <Upload size={14} />}
                校验并登记
              </Button>
            </footer>
          </form>
        </div>
      ) : null}
    </AppShell>
  );
}
