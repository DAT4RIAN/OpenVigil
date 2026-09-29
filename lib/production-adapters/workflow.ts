import { deteriorationRiskPercent } from "../deterioration-risk.ts";
import {
  type JsonRecord,
  isRecord,
  text,
  number,
  list,
  record,
  backendCollection,
  collectionResponse,
} from "./shared.ts";

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
      deteriorationRiskPercent: deteriorationRiskPercent(item.deterioration_risk_percent),
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
