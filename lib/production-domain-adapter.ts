import { proxyProductionBackendRequest } from "./production-runtime.ts";

type JsonRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const text = (value: unknown, fallback = ""): string =>
  typeof value === "string" ? value : fallback;
const number = (value: unknown, fallback = 0): number =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const record = (value: unknown): JsonRecord => (isRecord(value) ? value : {});
type BackendCollectionResult = {
  upstream: Response;
  rows: JsonRecord[];
  total: number | null;
  nextCursor: string | null;
  complete: boolean;
};

function jsonError(code: string, message: string, status = 502): Response {
  return Response.json(
    {
      data: null,
      error: { code, message },
      meta: { runtimeMode: "production", fixtureFallback: false },
    },
    { status, headers: { "cache-control": "no-store" } },
  );
}

async function backendCollection(
  request: Request,
  backendPath: string,
  key: string,
): Promise<BackendCollectionResult | Response> {
  const upstream = await proxyProductionBackendRequest(request, backendPath);
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production backend returned invalid JSON.");
  }
  const envelope = isRecord(payload) ? payload : {};
  const rawRows = envelope[key];
  if (!Array.isArray(rawRows) || !rawRows.every(isRecord)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      `The production backend response did not contain a valid ${key} collection.`,
    );
  }
  const rows = rawRows;
  const rawNextCursor = envelope.next_cursor;
  const nextCursor =
    typeof rawNextCursor === "string" && rawNextCursor.length > 0 ? rawNextCursor : null;
  const backendMeta = record(envelope.meta);
  const rawTotal =
    typeof envelope.total === "number"
      ? envelope.total
      : typeof backendMeta.total === "number"
        ? backendMeta.total
        : null;
  const complete = nextCursor === null;
  return {
    upstream,
    rows,
    total: rawTotal ?? (complete ? rows.length : null),
    nextCursor,
    complete,
  };
}

function collectionResponse(
  data: JsonRecord[],
  upstream: Response,
  collection?: Pick<BackendCollectionResult, "total" | "nextCursor" | "complete">,
): Response {
  const total = collection ? collection.total : data.length;
  const nextCursor = collection?.nextCursor ?? null;
  const hasMore = collection ? !collection.complete : false;
  return Response.json(
    {
      data,
      meta: {
        count: data.length,
        total,
        nextCursor,
        hasMore,
        runtimeMode: "production",
        source: "python-fastapi",
        fixtureFallback: false,
      },
    },
    {
      headers: {
        "cache-control": "no-store",
        "x-windops-backend": upstream.headers.get("x-windops-backend") ?? "python-fastapi",
      },
    },
  );
}

const productionAgentIds: Readonly<Record<string, string>> = {
  scada_analysis_agent: "agent-scada-analysis",
  vibration_diagnosis_agent: "agent-vibration-diagnosis",
  failure_diagnosis_agent: "agent-failure-diagnosis",
  knowledge_agent: "agent-knowledge",
  maintenance_strategy_agent: "agent-maintenance-strategy",
  review_committee: "agent-review-committee",
  human_approval_gate: "agent-human-approval-gate",
  work_order_agent: "agent-work-order",
};

function productionAgentLayer(agentKey: string): "decision" | "review" | "execution" {
  if (agentKey === "review_committee" || agentKey === "human_approval_gate") return "review";
  if (agentKey === "work_order_agent") return "execution";
  return "decision";
}

export async function productionAgentsResponse(request: Request): Promise<Response> {
  const result = await backendCollection(request, "/api/v1/agents", "agents");
  if (result instanceof Response) return result;
  const data = result.rows.map((row) => {
    const agentKey = text(row.agent_key);
    const metrics = record(row.metrics);
    const displayName = text(row.display_name, agentKey);
    const lastActiveAt = text(metrics.last_active_at) || null;
    return {
      id: productionAgentIds[agentKey] ?? `agent-${agentKey.replaceAll("_", "-")}`,
      definitionId: text(row.definition_id),
      agentKey,
      catalogVersionId: text(row.catalog_version_id),
      name: displayName,
      shortName: displayName,
      layer: productionAgentLayer(agentKey),
      role: text(row.role, agentKey),
      description: text(row.description),
      status: row.active === true ? "idle" : "offline",
      currentTask: null,
      currentMissionId: null,
      queueDepth: 0,
      model: "LiteLLM（运维方配置）",
      promptVersion: text(row.version),
      skills: list(row.skills).map(String),
      tools: list(row.tools).map(String),
      knowledgeSourceIds: [],
      metrics: {
        successRate:
          typeof metrics.success_rate === "number"
            ? Math.round(metrics.success_rate * 10_000) / 100
            : 0,
        averageLatencySeconds:
          typeof metrics.average_latency_ms === "number"
            ? Math.round(metrics.average_latency_ms) / 1_000
            : 0,
        requests24h: number(metrics.requests),
        toolCalls24h: number(metrics.tool_calls),
        tokenUsage24h: number(metrics.token_usage),
        missionsCompleted: 0,
      },
      lastActiveAt,
    };
  });
  return collectionResponse(data, result.upstream, result);
}

function scopedBackendRequest(request: Request, resource: "alarms" | "work-orders"): Request {
  const url = new URL(request.url);
  const scope = url.searchParams.get("scope");
  url.searchParams.delete("scope");
  if (scope === "archive") {
    url.searchParams.set("status", resource === "alarms" ? "resolved" : "completed");
  }
  return new Request(url, request);
}

function missionStatus(value: unknown): string {
  const normalized = text(value).replaceAll("_", "-");
  return normalized === "rejected" ? "rejected" : normalized;
}

function risk(value: unknown): "critical" | "high" | "medium" | "low" {
  if (value === "critical") return "critical";
  if (value === "major" || value === "high") return "high";
  if (value === "minor" || value === "medium" || value === "warning") return "medium";
  return "low";
}

function missionProgress(status: string): number {
  return (
    {
      detected: 10,
      investigating: 25,
      diagnosed: 45,
      "decision-pending": 55,
      "under-review": 65,
      approved: 75,
      executing: 85,
      completed: 100,
      rejected: 100,
    }[status] ?? 0
  );
}

function nextMissionAction(status: string): string {
  return (
    {
      detected: "等待分析调度",
      investigating: "收集并验证证据",
      diagnosed: "生成维护候选方案",
      "decision-pending": "完成决策草案",
      "under-review": "等待人工审核",
      approved: "等待资源与天气窗口",
      executing: "执行现场工单",
      completed: "闭环已完成",
      rejected: "任务已被人工拒绝",
    }[status] ?? "检查任务状态"
  );
}

export async function productionMissionsResponse(request: Request): Promise<Response> {
  const result = await backendCollection(request, "/api/v1/missions", "missions");
  if (result instanceof Response) return result;
  const data = result.rows.map((row) => {
    const status = missionStatus(row.status);
    const diagnosis = record(row.diagnosis);
    const createdAt = text(row.created_at);
    const updatedAt = text(row.updated_at, createdAt);
    return {
      id: text(row.mission_id),
      turbineId: text(row.turbine_id),
      title: text(row.title),
      summary: text(diagnosis.conclusion, text(row.title)),
      severity: risk(row.severity),
      status,
      progressPercent: missionProgress(status),
      leadAgentId: "failure_diagnosis_agent",
      agentIds: [],
      alarmIds: [text(row.alarm_id)].filter(Boolean),
      evidenceIds: list(row.evidence_ids).map(String),
      diagnosis: text(diagnosis.conclusion) || null,
      confidencePercent:
        typeof diagnosis.confidence === "number" ? Math.round(diagnosis.confidence * 100) : null,
      decisionId: text(row.decision_id) || null,
      workOrderId: text(row.work_order_id) || null,
      nextAction: nextMissionAction(status),
      createdAt,
      updatedAt,
      targetResolutionAt: updatedAt,
    };
  });
  return collectionResponse(data, result.upstream, result);
}

function alarmStatus(value: unknown): string {
  const normalized = text(value);
  if (normalized === "open") return "active";
  return normalized;
}

function alarmAiStatus(value: unknown, hasMission: boolean): string {
  const normalized = text(value);
  if (normalized.includes("approval")) return "diagnosed";
  if (normalized.includes("completed")) return "action-created";
  if (normalized.includes("revision") || normalized === "queued") return "queued";
  if (normalized.includes("analy")) return "analyzing";
  return hasMission ? "diagnosed" : "not-required";
}

export async function productionAlarmsResponse(request: Request): Promise<Response> {
  const result = await backendCollection(
    scopedBackendRequest(request, "alarms"),
    "/api/v1/alarms",
    "alarms",
  );
  if (result instanceof Response) return result;
  const data = result.rows.map((row) => {
    const evidence = record(row.evidence);
    const attributes = record(evidence.attributes);
    const missionId = text(row.mission_id) || null;
    const triggeredAt = text(row.triggered_at);
    return {
      id: text(row.alarm_id),
      code: text(row.code),
      turbineId: text(row.turbine_id),
      subsystem: text(row.subsystem),
      severity: text(row.severity),
      title: text(row.title),
      description: text(row.title),
      triggeredAt,
      durationMinutes: Math.max(0, Math.round((Date.now() - Date.parse(triggeredAt)) / 60_000)),
      status: alarmStatus(row.status),
      aiStatus: alarmAiStatus(row.ai_status, Boolean(missionId)),
      assignee: text(row.assigned_to) || null,
      acknowledgedAt: text(row.acknowledged_at) || null,
      resolvedAt: text(row.resolved_at) || null,
      currentValue: typeof evidence.value === "number" ? evidence.value : null,
      threshold: typeof attributes.threshold === "number" ? attributes.threshold : null,
      unit: text(evidence.unit) || null,
      sourceVariable: text(evidence.variable) || null,
      missionId,
      evidenceIds: [],
      revision: number(row.revision, 1),
      updatedAt: text(row.updated_at, triggeredAt),
    };
  });
  return collectionResponse(data, result.upstream, result);
}

function decisionStatus(value: unknown): string {
  const normalized = text(value).replaceAll("_", "-");
  if (normalized === "pending-approval") return "under-review";
  return normalized;
}

function highestAlternativeRisk(
  alternatives: JsonRecord[],
): "critical" | "high" | "medium" | "low" {
  const rank = { low: 0, medium: 1, high: 2, critical: 3 } as const;
  return alternatives.reduce<"critical" | "high" | "medium" | "low">((highest, item) => {
    const current = risk(item.safety_risk);
    return rank[current] > rank[highest] ? current : highest;
  }, "low");
}

export async function productionDecisionsResponse(request: Request): Promise<Response> {
  const result = await backendCollection(request, "/api/v1/decisions", "decisions");
  if (result instanceof Response) return result;
  const data = result.rows.map((row) => {
    const diagnosis = record(row.diagnosis);
    const approval = record(row.approval);
    const alternatives = list(row.alternatives).filter(isRecord);
    const recommendedAlternativeId = text(row.recommended_alternative_id);
    const mappedAlternatives = alternatives.map((item) => ({
      id: text(item.alternative_id),
      label: text(item.alternative_id),
      title: text(item.title),
      description: text(item.action),
      safetyRisk: risk(item.safety_risk),
      deteriorationRiskPercent: number(item.deterioration_risk_percent),
      estimatedCostCny: number(item.estimated_cost_cny),
      estimatedDowntimeHours: number(item.estimated_downtime_hours),
      estimatedEnergyLossMWh: number(item.estimated_energy_loss_mwh),
      weatherWindowId: text(item.weather_window_id) || null,
      requiredResources: list(item.required_resources).map(String),
      recommended: Boolean(item.recommended),
      rationale: text(item.rationale, text(row.recommendation_reason)),
    }));
    const selected =
      mappedAlternatives.find(
        (item) => item.id === (text(row.selected_alternative_id) || recommendedAlternativeId),
      ) ?? mappedAlternatives[0];
    return {
      id: text(row.decision_id),
      missionId: text(row.mission_id),
      missionRevision: number(row.mission_revision),
      turbineId: text(row.turbine_id),
      incident: text(row.incident),
      diagnosis: text(diagnosis.conclusion, text(row.incident)),
      confidencePercent: Math.round(number(diagnosis.confidence) * 100),
      status: decisionStatus(row.status),
      risk: highestAlternativeRisk(alternatives),
      evidenceIds: list(row.evidence_ids).map(String),
      alternatives: mappedAlternatives,
      recommendedAlternativeId,
      recommendedAction:
        mappedAlternatives.find((item) => item.id === recommendedAlternativeId)?.description ?? "",
      weatherWindowId: selected?.weatherWindowId ?? null,
      requiredResources: selected?.requiredResources ?? [],
      approval: {
        required: true,
        action: text(approval.action).replaceAll("_", "-") || null,
        selectedAlternativeId: text(approval.selected_alternative_id) || null,
        approver: text(approval.approver) || null,
        approverRole: null,
        timestamp: text(approval.created_at) || null,
        reason: text(approval.reason) || null,
        comment: text(approval.comment) || null,
      },
      createdAt: text(row.created_at),
      updatedAt: text(row.updated_at),
    };
  });
  return collectionResponse(data, result.upstream, result);
}

export async function productionWorkOrdersResponse(request: Request): Promise<Response> {
  const result = await backendCollection(
    scopedBackendRequest(request, "work-orders"),
    "/api/v1/work-orders",
    "work_orders",
  );
  if (result instanceof Response) return result;
  const data = result.rows.map((row) => {
    const safety = record(row.safety_plan);
    const closure = record(row.closure_policy);
    const eam = isRecord(row.eam) ? row.eam : null;
    const createdAt = text(row.created_at);
    const updatedAt = text(row.updated_at, createdAt);
    return {
      id: text(row.work_order_id),
      turbineId: text(row.turbine_id),
      issue: text(row.title),
      description: text(row.title),
      priority: text(row.priority, "high"),
      status: text(row.status).replaceAll("_", "-"),
      assignedTeam: text(row.assigned_team, "未分配"),
      createdByAgentId: text(row.created_by) || null,
      relatedMissionId: text(row.mission_id) || null,
      decisionId: null,
      plannedStart: text(row.planned_start, createdAt),
      deadline: text(row.deadline, createdAt),
      estimatedDurationHours: number(row.estimated_duration_hours),
      riskLevel: risk(safety.risk_level),
      tasks: list(row.tasks)
        .filter(isRecord)
        .map((task) => ({
          id: text(task.task_id),
          sequence: number(task.sequence),
          title: text(task.title),
          completed: task.status === "completed",
          completionNote: text(task.result) || null,
          schemaVersion: text(task.schema_version),
          measurementSchema: record(task.measurement_schema),
        })),
      ppeRequirements: list(safety.ppe).map(String),
      requiredTools: list(safety.required_tools).map(String),
      spareParts: list(safety.spare_parts).map((name) => ({
        partNumber: "",
        name: String(name),
        quantity: 1,
        available: 0,
        reserved: 0,
      })),
      safetyProcedures: list(safety.procedures).map(String),
      closurePolicy: closure,
      eam: eam
        ? {
            provider: text(eam.provider) || null,
            externalId: text(eam.external_id) || null,
            syncStatus: text(eam.sync_status, "pending"),
            externalUpdatedAt: text(eam.external_updated_at) || null,
            updatedAt: text(eam.updated_at) || null,
          }
        : null,
      createdAt,
      updatedAt,
    };
  });
  return collectionResponse(data, result.upstream, result);
}

const knowledgeDocumentTypes = new Set([
  "equipment-manual",
  "maintenance-procedure",
  "incident-case",
  "failure-case",
  "technical-standard",
  "manufacturer-bulletin",
  "historical-work-order",
  "inspection-report",
  "scada-analysis-report",
]);

export async function productionKnowledgeDocumentsResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const backendUrl = new URL(request.url);
  backendUrl.search = "";
  const query = sourceUrl.searchParams.get("q");
  const type = sourceUrl.searchParams.get("type");
  if (query) backendUrl.searchParams.set("q", query);
  if (type && type !== "all") backendUrl.searchParams.set("document_type", type);
  backendUrl.searchParams.set("limit", "200");
  const result = await backendCollection(
    new Request(backendUrl, request),
    "/api/v1/knowledge/documents",
    "documents",
  );
  if (result instanceof Response) return result;
  const documents = result.rows.map((row) => {
    const metadata = record(row.metadata);
    const documentType = text(row.document_type, "technical-standard");
    return {
      id: text(row.document_id),
      title: text(row.title),
      type: knowledgeDocumentTypes.has(documentType) ? documentType : "technical-standard",
      equipment: text(metadata.equipment, "未标注"),
      manufacturer: text(metadata.manufacturer) || null,
      version: text(row.document_version, "1"),
      updatedAt: text(row.updated_at, text(row.created_at)),
      vectorized: row.vectorized === true,
      pageCount: number(metadata.page_count),
      language: text(metadata.language, "zh-CN") === "en-US" ? "en-US" : "zh-CN",
      tags: list(metadata.tags).map(String),
      summary: text(metadata.summary, text(row.title)),
      relatedTurbineIds: list(metadata.related_turbine_ids).map(String),
      relatedMissionIds: list(metadata.related_mission_ids).map(String),
      ingestionStatus: text(row.ingestion_status, "pending"),
      embeddingProvider: text(row.embedding_provider) || null,
      embeddingModel: text(row.embedding_model) || null,
      artifactUri: text(row.artifact_uri) || null,
      artifactSha256: text(row.artifact_sha256) || null,
    };
  });
  return Response.json(
    {
      ok: true,
      data: {
        documents,
        facets: {
          vectorized: documents.filter((document) => document.vectorized).length,
        },
      },
      error: null,
      meta: {
        count: documents.length,
        total: result.total,
        nextCursor: result.nextCursor,
        hasMore: !result.complete,
        deterministic: false,
        persisted: true,
        runtimeMode: "production",
        source: "python-fastapi",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store" } },
  );
}

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

function assignedWorkOrder(row: JsonRecord): string | null {
  const reservation = list(row.reservations).find(isRecord);
  return reservation ? text(reservation.work_order_id) || null : null;
}

function assignedMission(row: JsonRecord): string | null {
  const reservation = list(row.reservations).find(isRecord);
  return reservation ? text(reservation.mission_id) || null : null;
}

function resourceAvailability(value: unknown): string {
  if (value === "reserved") return "reserved";
  if (value === "maintenance") return "maintenance";
  return "available";
}

export async function productionResourcesResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const category = (sourceUrl.searchParams.get("category") ?? "all").trim().toLowerCase();
  const resourceTypes: Record<string, string | null> = {
    all: null,
    "spare-parts": "spare_part",
    crews: "crew",
    vessels: "vessel",
    tools: "tool",
    weather: "__weather_only__",
  };
  if (!(category in resourceTypes)) {
    return jsonError("INVALID_RESOURCE_CATEGORY", "The resource category is invalid.", 400);
  }
  const backendUrl = new URL(request.url);
  backendUrl.search = "";
  const resourceType = resourceTypes[category];
  if (resourceType) backendUrl.searchParams.set("resource_type", resourceType);
  for (const [sourceKey, backendKey] of [
    ["q", "q"],
    ["workOrderId", "workOrderId"],
    ["cursor", "cursor"],
    ["limit", "limit"],
    ["weatherCursor", "weather_cursor"],
    ["weatherLimit", "weather_limit"],
  ] as const) {
    const value = sourceUrl.searchParams.get(sourceKey)?.trim();
    if (value) backendUrl.searchParams.set(backendKey, value);
  }
  const upstream = await proxyProductionBackendRequest(
    new Request(backendUrl, request),
    "/api/v1/resources",
  );
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production backend returned invalid JSON.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.resources)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend response did not contain a valid resources collection.",
    );
  }
  const resources = payload.resources.filter(isRecord);
  const spareParts = resources
    .filter((row) => row.resource_type === "spare_part")
    .map((row) => {
      const attributes = record(row.attributes);
      const reserved = list(row.reservations)
        .filter(isRecord)
        .reduce((sum, item) => sum + number(item.quantity), 0);
      const onHand = number(row.quantity);
      const available = Math.max(0, onHand - reserved);
      const reorderPoint = number(attributes.reorder_point);
      return {
        id: text(row.resource_id),
        partNumber: text(attributes.part_number, text(row.resource_id)),
        name: text(row.name),
        category: text(attributes.category, "uncategorized"),
        warehouse: text(attributes.warehouse),
        onHand,
        reserved,
        available,
        reorderPoint,
        unit: text(attributes.unit, "item"),
        status:
          available === 0 ? "out-of-stock" : available <= reorderPoint ? "low-stock" : "in-stock",
        reservedForWorkOrderIds: list(row.reservations)
          .filter(isRecord)
          .map((item) => text(item.work_order_id))
          .filter(Boolean),
        compatibleTurbineModels: list(attributes.compatible_turbine_models).map(String),
        updatedAt: text(row.updated_at),
      };
    });
  const crews = resources
    .filter((row) => row.resource_type === "crew")
    .map((row) => {
      const attributes = record(row.attributes);
      return {
        id: text(row.resource_id),
        name: text(row.name),
        specialties: list(attributes.specialties).map(String),
        memberCount: number(attributes.member_count, number(row.quantity)),
        availability: resourceAvailability(row.status),
        assignedWorkOrderId: assignedWorkOrder(row),
        assignedMissionId: assignedMission(row),
        certifications: list(attributes.certifications).map(String),
        currentLocation: text(attributes.current_location),
      };
    });
  const vessels = resources
    .filter((row) => row.resource_type === "vessel")
    .map((row) => {
      const attributes = record(row.attributes);
      return {
        id: text(row.resource_id),
        name: text(row.name),
        vesselType: text(attributes.vessel_type),
        availability: resourceAvailability(row.status),
        assignedWorkOrderId: assignedWorkOrder(row),
        assignedMissionId: assignedMission(row),
        capacity: number(attributes.capacity),
        maxWaveHeightM: number(attributes.max_wave_height_m),
        berth: text(attributes.berth),
        eta: text(attributes.eta) || null,
      };
    });
  const tools = resources
    .filter((row) => row.resource_type === "tool")
    .map((row) => {
      const attributes = record(row.attributes);
      return {
        id: text(row.resource_id),
        name: text(row.name),
        category: text(attributes.category),
        availability: resourceAvailability(row.status),
        assignedWorkOrderId: assignedWorkOrder(row),
        assignedMissionId: assignedMission(row),
        calibrationDueAt: text(attributes.calibration_due_at),
        location: text(attributes.location),
      };
    });
  const weatherWindows = list(payload.weather_windows)
    .filter(isRecord)
    .map((row) => {
      const attributes = record(row.attributes);
      return {
        id: text(row.window_id),
        farmId: text(row.wind_farm_id),
        startsAt: text(row.starts_at),
        endsAt: text(row.ends_at),
        suitability: row.suitable === true ? "suitable" : "unsuitable",
        windSpeedMps: number(row.wind_speed_ms),
        gustSpeedMps: number(attributes.gust_speed_mps),
        waveHeightM: number(row.wave_height_m),
        visibilityKm: number(attributes.visibility_km),
        precipitationMm: number(attributes.precipitation_mm),
        lightningRisk: text(attributes.lightning_risk),
        temperatureC: number(attributes.temperature_c),
        reason: text(attributes.reason),
        recommendedFor: list(attributes.recommended_for).map(String),
      };
    });
  const data = { spareParts, crews, vessels, tools, weatherWindows };
  const count = Object.values(data).reduce((sum, rows) => sum + rows.length, 0);
  const resourceTotal = number(payload.total, resources.length);
  const weatherCount = number(payload.weather_count, weatherWindows.length);
  return Response.json(
    {
      data,
      meta: {
        count,
        total: resourceTotal + weatherCount,
        resourceTotal,
        nextCursor: text(payload.next_cursor) || null,
        weatherNextCursor: text(payload.weather_next_cursor) || null,
        hasMore: Boolean(payload.next_cursor || payload.weather_next_cursor),
        snapshotAt: new Date().toISOString(),
        deterministic: false,
        runtimeMode: "production",
        source: "python-fastapi",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export async function productionTurbinesResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const parameters = new URLSearchParams(sourceUrl.searchParams);
  parameters.set("limit", "200");
  const proxyRequest = new Request(`${sourceUrl.origin}${sourceUrl.pathname}?${parameters}`, {
    method: "GET",
    headers: request.headers,
  });
  const upstream = await proxyProductionBackendRequest(proxyRequest, "/api/v1/turbines");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production turbine response was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.turbines)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a governed turbine collection.",
    );
  }
  const rows = payload.turbines.filter(isRecord);
  const farms = list(payload.wind_farms).filter(isRecord);
  const data = rows.map((row, index) => {
    const updatedAt = text(row.updated_at, new Date(0).toISOString());
    const latitude = typeof row.latitude === "number" ? row.latitude : null;
    const longitude = typeof row.longitude === "number" ? row.longitude : null;
    const telemetryObservedAt = text(row.telemetry_observed_at) || null;
    const availabilityAvailable = typeof row.availability_percent === "number";
    const lastMaintenanceAt = text(row.last_maintenance_at) || null;
    const nextInspectionAt = text(row.next_inspection_at) || null;
    return {
      id: text(row.turbine_id),
      farmId: text(row.wind_farm_id),
      displayName: text(row.turbine_id),
      model: text(row.model),
      manufacturer: text(row.manufacturer, "unconfigured"),
      serialNumber: "unconfigured",
      ratedPowerMW: 0,
      status: text(row.status),
      healthScore: number(row.health_score),
      powerMW: number(row.active_power_mw),
      windSpeedMps: number(row.wind_speed_ms),
      rotorSpeedRpm: number(row.rotor_speed_rpm),
      nacelleDirectionDeg: number(row.nacelle_direction_deg),
      availabilityPercent: number(row.availability_percent),
      activeAlarmCount: number(row.active_alarm_count),
      currentMissionId: text(row.current_mission_id) || null,
      lastMaintenanceAt: lastMaintenanceAt ?? updatedAt,
      nextInspectionAt: nextInspectionAt ?? updatedAt,
      coordinates: { latitude: latitude ?? 0, longitude: longitude ?? 0 },
      gridPosition: { row: Math.floor(index / 8), column: index % 8 },
      updatedAt,
      telemetryObservedAt,
      telemetryAvailable: telemetryObservedAt !== null,
      availabilityAvailable,
      coordinatesConfigured: latitude !== null && longitude !== null,
      lastMaintenanceRecorded: lastMaintenanceAt !== null,
      nextInspectionRecorded: nextInspectionAt !== null,
    };
  });
  const currentPowerMW = data.reduce((total, turbine) => total + turbine.powerMW, 0);
  const averageHealthScore = data.length
    ? data.reduce((total, turbine) => total + turbine.healthScore, 0) / data.length
    : 0;
  const availabilityRows = data.filter((turbine) => turbine.availabilityAvailable);
  const averageAvailabilityPercent = availabilityRows.length
    ? availabilityRows.reduce((total, turbine) => total + turbine.availabilityPercent, 0) /
      availabilityRows.length
    : null;
  return Response.json(
    {
      data,
      meta: {
        count: data.length,
        total: data.length,
        runtimeMode: "production",
        source: "python-fastapi",
        fixtureFallback: false,
        snapshotAt: new Date().toISOString(),
        farms: farms.map((farm) => ({
          id: text(farm.wind_farm_id),
          name: text(farm.name),
          capacityMW: number(farm.capacity_mw),
        })),
        fleet: {
          currentPowerMW,
          averageHealthScore,
          activeAlarmCount: data.reduce((total, turbine) => total + turbine.activeAlarmCount, 0),
          activeMissionCount: data.filter((turbine) => turbine.currentMissionId).length,
          generationAvailable: false,
          averageAvailabilityPercent,
          telemetryAssetCount: data.filter((turbine) => turbine.telemetryAvailable).length,
        },
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

function scadaIntervalLabel(seconds: number): string {
  if (seconds < 60) return `${seconds} sec`;
  if (seconds < 3600) return `${Math.ceil(seconds / 60)} min`;
  return `${Math.ceil(seconds / 3600)} hour`;
}

export async function productionScadaHistoryResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const parameters = new URLSearchParams();
  const turbineId = sourceUrl.searchParams.get("turbineId")?.trim();
  if (!turbineId) {
    return jsonError("TURBINE_ID_REQUIRED", "turbineId is required in production mode.", 422);
  }
  parameters.set("turbine_id", turbineId);
  parameters.set("range", sourceUrl.searchParams.get("range")?.trim() || "24H");
  const startsAt = sourceUrl.searchParams.get("from")?.trim();
  const endsAt = sourceUrl.searchParams.get("to")?.trim();
  if (startsAt) parameters.set("from", startsAt);
  if (endsAt) parameters.set("to", endsAt);
  for (const variable of sourceUrl.searchParams.getAll("metric")) {
    parameters.append("variable", variable.replaceAll("-", "_"));
  }
  parameters.set("points_per_series", "1000");
  const proxyRequest = new Request(`${sourceUrl.origin}${sourceUrl.pathname}?${parameters}`, {
    method: "GET",
    headers: request.headers,
  });
  const upstream = await proxyProductionBackendRequest(proxyRequest, "/api/v1/scada/history");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production SCADA response was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.data) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a valid SCADA history response.",
    );
  }
  const data = payload.data.filter(isRecord).map((row) => {
    const normalRange = list(row.normal_range);
    const points = list(row.points)
      .filter(isRecord)
      .map((point) => ({
        timestamp: text(point.timestamp),
        value: number(point.value),
        quality: point.quality === "bad" || point.quality === "uncertain" ? point.quality : "good",
        isAnomaly: point.is_anomaly === true,
        aiEvent: null,
        late: point.late === true,
      }));
    return {
      id: text(row.series_id),
      turbineId: text(row.turbine_id),
      sourceId: text(row.source_id),
      metric: text(row.variable).replaceAll("_", "-"),
      label: text(row.label),
      unit: text(row.unit),
      precision: number(row.precision, 2),
      currentValue: points.at(-1)?.value ?? 0,
      normalRange: [number(normalRange[0]), number(normalRange[1])],
      thresholds: list(row.thresholds)
        .filter(isRecord)
        .map((threshold) => ({
          id: text(threshold.id),
          label: text(threshold.label),
          value: number(threshold.value),
          direction: threshold.direction === "below" ? "below" : "above",
          severity: threshold.severity === "critical" ? "critical" : "warning",
        })),
      points,
    };
  });
  const intervalSeconds = number(payload.meta.interval_seconds, 1);
  return Response.json(
    {
      data,
      meta: {
        count: data.length,
        pointCount: number(payload.meta.point_count),
        turbineId: text(payload.meta.turbine_id),
        range: text(payload.meta.range, "24H"),
        interval: scadaIntervalLabel(intervalSeconds),
        startsAt: text(payload.meta.starts_at),
        endsAt: text(payload.meta.ends_at),
        snapshotAt: text(payload.meta.snapshot_at),
        deterministic: false,
        runtimeMode: "production",
        source: "python-fastapi-timescaledb",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export async function productionScadaMeasurementsResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const parameters = new URLSearchParams();
  const turbineId = sourceUrl.searchParams.get("turbineId")?.trim();
  const metric = sourceUrl.searchParams.get("metric")?.trim();
  for (const key of ["offset", "limit", "from", "to"] as const) {
    const value = sourceUrl.searchParams.get(key)?.trim();
    if (value) parameters.set(key, value);
  }
  if (turbineId) parameters.set("turbine_id", turbineId);
  if (metric) parameters.set("variable", metric.replaceAll("-", "_"));
  const proxyRequest = new Request(`${sourceUrl.origin}${sourceUrl.pathname}?${parameters}`, {
    method: "GET",
    headers: request.headers,
  });
  const upstream = await proxyProductionBackendRequest(proxyRequest, "/api/v1/scada/measurements");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production SCADA archive was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.measurements) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a valid SCADA archive page.",
    );
  }
  const data = payload.measurements.filter(isRecord).map((row) => ({
    id: text(row.sample_id),
    sequence: number(row.source_sequence),
    turbineId: text(row.turbine_id),
    sourceId: text(row.source_id),
    sourceEventId: text(row.source_event_id),
    metric: text(row.variable).replaceAll("_", "-"),
    label: text(row.label),
    timestamp: text(row.observed_at),
    receivedAt: text(row.received_at),
    value: number(row.value),
    unit: text(row.unit),
    quality: row.quality === "bad" || row.quality === "uncertain" ? row.quality : "good",
    qualityCode: text(row.quality_code) || null,
    late: row.late === true,
    isAnomaly: row.is_anomaly === true,
  }));
  return Response.json(
    {
      data,
      meta: {
        total: number(payload.meta.total),
        offset: number(payload.meta.offset),
        limit: number(payload.meta.limit, 100),
        turbineId: text(payload.meta.turbine_id) || null,
        metric: text(payload.meta.variable).replaceAll("_", "-") || null,
        from: text(payload.meta.from) || null,
        to: text(payload.meta.to) || null,
        snapshotAt: text(payload.meta.snapshot_at),
        deterministic: false,
        runtimeMode: "production",
        source: "python-fastapi-timescaledb",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export async function productionHealthAssessmentsResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const parameters = new URLSearchParams();
  const turbineId = sourceUrl.searchParams.get("turbineId")?.trim();
  if (turbineId) parameters.set("turbine_id", turbineId);
  for (const key of ["state", "risk", "cursor", "limit"] as const) {
    const value = sourceUrl.searchParams.get(key)?.trim();
    if (value) parameters.set(key, value);
  }
  const proxyRequest = new Request(`${sourceUrl.origin}${sourceUrl.pathname}?${parameters}`, {
    method: "GET",
    headers: request.headers,
  });
  const upstream = await proxyProductionBackendRequest(proxyRequest, "/api/v1/health/assessments");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production health response was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.assessments) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return valid health assessments.",
    );
  }
  const data = payload.assessments.filter(isRecord).map((row) => ({
    id: text(row.assessment_id),
    turbineId: text(row.turbine_id),
    turbineModel: text(row.turbine_model),
    healthScore: number(row.health_score),
    state: text(row.state),
    trend: text(row.trend),
    riskLevel: text(row.risk_level),
    activeAlarmCount: number(row.active_alarm_count),
    anomalyScore: number(row.anomaly_score),
    predictionAvailable: row.prediction_available === true,
    primaryFinding: text(row.primary_finding),
    missionId: text(row.mission_id) || null,
    assessedAt: text(row.assessed_at),
  }));
  return Response.json(
    {
      data,
      meta: {
        count: data.length,
        total: number(payload.meta.total),
        nextCursor: text(payload.meta.next_cursor) || null,
        hasMore: payload.meta.has_more === true,
        snapshotAt: text(payload.meta.snapshot_at),
        predictionProvider: text(payload.meta.prediction_provider) || null,
        deterministic: false,
        runtimeMode: "production",
        source: "python-fastapi",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

async function productionOperationalView(
  request: Request,
  backendPath: string,
  options: {
    readonly model?: JsonRecord;
    readonly meta?: (meta: JsonRecord) => JsonRecord;
  } = {},
): Promise<Response> {
  const upstream = await proxyProductionBackendRequest(request, backendPath);
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production operational view was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.data) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a valid operational collection.",
    );
  }
  const sourceMeta = payload.meta;
  return Response.json(
    {
      data: payload.data,
      meta: {
        count: number(sourceMeta.count, payload.data.length),
        total: number(sourceMeta.total, payload.data.length),
        filteredTotal: number(sourceMeta.filtered_total, payload.data.length),
        offset: number(sourceMeta.offset),
        limit: number(sourceMeta.limit, payload.data.length),
        nextOffset: typeof sourceMeta.next_offset === "number" ? sourceMeta.next_offset : null,
        hasMore: sourceMeta.has_more === true,
        snapshotAt: text(sourceMeta.snapshot_at),
        runtimeMode: "production",
        fixtureFallback: false,
        source: text(sourceMeta.source, "python-fastapi"),
        ...(isRecord(sourceMeta.related_data_boundaries)
          ? { relatedDataBoundaries: sourceMeta.related_data_boundaries }
          : {}),
        ...(options.model ? { model: options.model } : {}),
        ...(options.meta ? options.meta(sourceMeta) : {}),
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export function productionDiagnosesResponse(request: Request): Promise<Response> {
  return productionOperationalView(request, "/api/v1/diagnoses", {
    model: {
      mode: "governed-mission-diagnosis",
      deterministic: false,
      readOnly: true,
      realInference: true,
      publicTraceOnly: true,
      snapshotAt: null,
      notice: "诊断来自持久化 Mission、证据和 Agent 执行；模型供应方以每条执行账本为准。",
    },
  });
}

export function productionMaintenancePlansResponse(request: Request): Promise<Response> {
  return productionOperationalView(request, "/api/v1/maintenance-plans", {
    model: {
      mode: "governed-operational-schedule",
      deterministic: false,
      readOnly: false,
      snapshotAt: null,
      notice: "计划由持久化工单、资源预留与天气窗口实时派生。",
      provenance: ["work_orders", "resource_reservations", "weather_windows", "turbines"],
    },
  });
}

export async function productionDigitalTwinResponse(request: Request): Promise<Response> {
  const upstream = await proxyProductionBackendRequest(request, "/api/v1/digital-twin");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production twin response was invalid.");
  }
  if (!isRecord(payload) || !isRecord(payload.data) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a valid digital twin snapshot.",
    );
  }
  return Response.json(
    {
      data: payload.data,
      meta: {
        turbineId: text(payload.meta.turbine_id),
        snapshotAt: text(payload.meta.snapshot_at),
        deterministic: false,
        readOnly: true,
        runtimeMode: "production",
        source: text(payload.meta.source),
        fixtureFallback: false,
        workflowPersistence: "postgresql",
        workflowRevision: 0,
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export async function productionReportsResponse(request: Request): Promise<Response> {
  const upstream = await proxyProductionBackendRequest(request, "/api/v1/reports");
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production report response was invalid.");
  }
  if (!isRecord(payload) || !Array.isArray(payload.data) || !isRecord(payload.meta)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      "The production backend did not return a valid report collection.",
    );
  }
  const reports = payload.data.filter(isRecord);
  const typeCounts: Record<string, number> = {};
  const periodCounts: Record<string, number> = {};
  for (const report of reports) {
    const reportType = text(report.type);
    const period = text(report.period);
    if (reportType) typeCounts[reportType] = (typeCounts[reportType] ?? 0) + 1;
    if (period) periodCounts[period] = (periodCounts[period] ?? 0) + 1;
  }
  const workflowRevision = reports.reduce(
    (maximum, report) => Math.max(maximum, number(record(report.workflow).revision)),
    0,
  );
  return Response.json(
    {
      ok: true,
      data: {
        reports,
        facets: { reportTypes: typeCounts, periods: periodCounts },
      },
      error: null,
      meta: {
        count: number(payload.meta.count, reports.length),
        total: number(payload.meta.filtered_total, reports.length),
        catalogTotal: number(payload.meta.total, reports.length),
        snapshotAt: text(payload.meta.snapshot_at),
        workflowPersistence: "postgresql",
        workflowRevision,
        persisted: payload.meta.persisted === true,
        runtimeMode: "production",
        fixtureFallback: false,
        source: text(payload.meta.source),
      },
    },
    { headers: { "cache-control": "no-store", "x-windops-backend": "python-fastapi" } },
  );
}

export function productionDataCatalogResponse(request: Request): Promise<Response> {
  return productionOperationalView(request, "/api/v1/data-catalog", {
    meta: (meta) => ({
      scadaArchiveCount: number(meta.scada_archive_count),
      schemaObjectCount: number(meta.schema_object_count),
      hierarchy: record(meta.hierarchy),
      deterministic: false,
      readOnly: false,
    }),
  });
}
