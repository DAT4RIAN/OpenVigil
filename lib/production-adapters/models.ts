import { proxyProductionBackendRequest } from "../production-runtime.ts";
import { isRecord, text, number, list, record, jsonError, backendCollection } from "./shared.ts";

export async function productionModelsResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const backendUrl = new URL(request.url);
  backendUrl.search = "";
  const query = sourceUrl.searchParams.get("q");
  const kind = sourceUrl.searchParams.get("kind");
  if (query) backendUrl.searchParams.set("q", query);
  if (kind) backendUrl.searchParams.set("kind", kind);
  const upstream = await proxyProductionBackendRequest(
    new Request(backendUrl, request),
    "/api/v1/models",
  );
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The model registry returned invalid JSON.");
  }
  const envelope = record(payload);
  const rows = list(envelope.models).filter(isRecord);
  const backendMeta = record(envelope.meta);
  const monitoring = record(backendMeta.monitoring);
  const data = rows.map((row) => {
    const lifecycleStatus = text(row.status, "registered");
    const deployments = list(row.deployments).filter(isRecord);
    const active = deployments.some((item) => item.status === "active");
    const inputSchema = record(row.input_schema);
    const outputSchema = record(row.output_schema);
    const metrics = record(row.metrics);
    return {
      id: text(row.model_id),
      name: text(row.name),
      version: text(row.version),
      kind: text(row.kind, "predictive"),
      status: active ? "available" : "demo-only",
      lifecycleStatus,
      runtime: active ? "受治理的外部 HTTPS 推理服务" : "模型制品已登记，尚未承载生产流量",
      inputs: Object.keys(record(inputSchema.properties)),
      outputs: Object.keys(record(outputSchema.properties)),
      metrics: Object.entries(metrics).map(([label, value]) => ({
        label,
        value: typeof value === "string" ? value : JSON.stringify(value),
      })),
      realInference: active,
      usesEmbeddings: false,
      artifactBacked: Boolean(text(row.artifact_uri) && text(row.artifact_sha256)),
      artifactSha256: text(row.artifact_sha256),
      endpoint: "/api/predictive-assessments",
      limitation: text(
        row.description,
        "推理输出必须经过已登记 JSON Schema 校验，且不会触发自动控制。",
      ),
      deterministic: false,
      updatedAt: text(row.updated_at, text(row.created_at)),
      deployments: deployments.map((item) => ({
        id: text(item.deployment_id),
        status: text(item.status),
        targetId: text(item.target_id),
        trafficPercent: number(item.traffic_percent),
        activatedAt: text(item.activated_at) || null,
      })),
    };
  });
  const status = sourceUrl.searchParams.get("status");
  const filtered = status ? data.filter((item) => item.status === status) : data;
  return Response.json(
    {
      data: filtered,
      meta: {
        count: filtered.length,
        total: data.length,
        deterministic: false,
        readOnly: false,
        snapshotAt: text(monitoring.last_prediction_at, new Date().toISOString()),
        realInferenceCount: number(backendMeta.real_inference_count),
        embeddingBackedCount: 0,
        artifactCount: number(backendMeta.artifact_count),
        activeDeploymentCount: number(backendMeta.active_deployment_count),
        monitoring: {
          predictionCount: number(monitoring.prediction_count),
          succeededCount: number(monitoring.succeeded_count),
          failedCount: number(monitoring.failed_count),
          successRate: typeof monitoring.success_rate === "number" ? monitoring.success_rate : null,
          p95LatencyMs: number(monitoring.p95_latency_ms),
          lastPredictionAt: text(monitoring.last_prediction_at) || null,
        },
        disclosure: "模型制品、部署流量、在线推理与监控均来自 PostgreSQL 权威账本和外部推理服务。",
        runtimeMode: "production",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store" } },
  );
}

export async function productionPredictiveAssessmentsResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const backendUrl = new URL(request.url);
  backendUrl.search = "";
  for (const key of ["turbineId", "risk", "trend", "limit"] as const) {
    const value = sourceUrl.searchParams.get(key);
    if (value) backendUrl.searchParams.set(key === "turbineId" ? "turbine_id" : key, value);
  }
  const result = await backendCollection(
    new Request(backendUrl, request),
    "/api/v1/predictive-assessments",
    "assessments",
  );
  if (result instanceof Response) return result;
  const data = result.rows.map((row) => {
    const anomalyScore = number(row.anomaly_score);
    const componentHealth = number(row.component_health);
    const activeAlarmCount = number(row.active_alarm_count);
    const anomalyBand =
      anomalyScore >= 0.9
        ? 5
        : anomalyScore >= 0.75
          ? 4
          : anomalyScore >= 0.6
            ? 3
            : anomalyScore >= 0.4
              ? 2
              : 1;
    const healthBand =
      componentHealth < 50
        ? 5
        : componentHealth < 65
          ? 4
          : componentHealth < 75
            ? 3
            : componentHealth < 90
              ? 2
              : 1;
    const evidenceBand = Math.min(5, Math.max(1, anomalyBand, healthBand, activeAlarmCount));
    const consequenceBand = number(row.consequence_band);
    const riskScore = evidenceBand * consequenceBand;
    const matrixRisk =
      riskScore >= 20 ? "critical" : riskScore >= 12 ? "high" : riskScore >= 6 ? "medium" : "low";
    return {
      id: text(row.assessment_id),
      turbineId: text(row.turbine_id),
      turbineModel: text(row.turbine_model),
      healthScore: number(row.health_score),
      state: text(row.state, "watch"),
      trend: text(row.trend, "stable"),
      riskLevel: matrixRisk,
      anomalyScore,
      primaryFinding: text(row.primary_finding),
      assessedAt: text(row.assessed_at),
      component: text(row.component),
      componentHealth,
      turbineStatus: text(row.turbine_status, "running"),
      activeAlarmCount,
      evidenceBand,
      consequenceBand,
      matrixRisk,
      riskScore,
      priorityScore: Number(
        (
          (100 - componentHealth) * consequenceBand +
          anomalyScore * 10 +
          activeAlarmCount * 5
        ).toFixed(2),
      ),
      modelId: text(row.model_id),
      deploymentId: text(row.deployment_id),
      featureObservedAt: text(row.feature_observed_at),
      latencyMs: number(row.latency_ms),
    };
  });
  return Response.json(
    {
      data,
      meta: {
        count: data.length,
        total: data.length,
        filteredTotal: data.length,
        model: {
          id: data[0]?.modelId ?? "unavailable",
          label: data.length ? "生产在线状态评估" : "尚无可用在线状态评估",
          mode: "external-governed-inference",
          observationWindowHours: 24,
          evaluatedAt: data[0]?.assessedAt ?? new Date().toISOString(),
          deterministic: false,
          readOnly: false,
          performsRealInference: data.length > 0,
          notice: data.length
            ? "结果来自已登记制品和受治理 HTTPS 推理端点；仅使用健康、异常、告警与后果证据排序。"
            : "尚无成功的生产状态评估。请先登记、部署合格模型并运行在线评估。",
        },
        runtimeMode: "production",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store" } },
  );
}
