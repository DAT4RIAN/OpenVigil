/**
 * Shared domain contracts for the WindOps demo data layer.
 *
 * Dates are ISO-8601 strings on purpose: the fixtures are serializable and can
 * be used by server components, route handlers, and client components alike.
 */
export type ISODateTime = string;

export type TurbineStatus =
  | "running"
  | "warning"
  | "critical"
  | "maintenance"
  | "offline"
  | "communication-lost";

export type HealthState =
  | "healthy"
  | "watch"
  | "degraded"
  | "critical"
  | "maintenance"
  | "offline";

export type TrendDirection = "improving" | "stable" | "declining";
export type RiskLevel = "critical" | "high" | "medium" | "low";

export interface GeoCoordinate {
  readonly latitude: number;
  readonly longitude: number;
}

export interface GridPosition {
  readonly row: number;
  readonly column: number;
  readonly string: string;
}

export interface WindFarm {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly nameEn: string;
  readonly operator: string;
  readonly location: string;
  readonly timezone: "Asia/Shanghai";
  readonly coordinates: GeoCoordinate;
  readonly commissionedAt: ISODateTime;
  readonly status: "operational" | "curtailed" | "offline";
  readonly totalCapacityMW: number;
  readonly turbineCount: number;
  readonly turbineModel: string;
  readonly operatingTurbines: number;
  readonly maintenanceTurbines: number;
  readonly offlineTurbines: number;
  readonly currentPowerMW: number;
  readonly todayGenerationGWh: number;
  readonly averageHealthScore: number;
  readonly activeAlarmCount: number;
  readonly activeMissionCount: number;
  readonly weatherSummary: string;
  readonly lastUpdatedAt: ISODateTime;
}

export interface WindTurbine {
  readonly id: string;
  readonly farmId: string;
  readonly displayName: string;
  readonly model: string;
  readonly manufacturer: string;
  readonly serialNumber: string;
  readonly ratedPowerMW: number;
  readonly status: TurbineStatus;
  readonly healthScore: number;
  readonly powerMW: number;
  readonly windSpeedMps: number;
  readonly rotorSpeedRpm: number;
  readonly nacelleDirectionDeg: number;
  readonly availabilityPercent: number;
  readonly activeAlarmCount: number;
  readonly currentMissionId: string | null;
  readonly lastMaintenanceAt: ISODateTime;
  readonly nextInspectionAt: ISODateTime;
  readonly coordinates: GeoCoordinate;
  readonly gridPosition: GridPosition;
}

export type SubsystemKey =
  | "blades"
  | "hub"
  | "main-shaft"
  | "main-bearing"
  | "gearbox"
  | "generator"
  | "converter"
  | "yaw"
  | "pitch"
  | "tower"
  | "foundation"
  | "electrical";

export interface SubsystemHealth {
  readonly id: string;
  readonly turbineId: string;
  readonly key: SubsystemKey;
  readonly name: string;
  readonly healthScore: number;
  readonly state: HealthState;
  readonly trend: TrendDirection;
  readonly activeAlarmCount: number;
  readonly failureProbability30d: number;
  readonly remainingUsefulLifeDays: number | null;
  readonly anomalyScore: number;
  readonly primaryFinding: string;
  readonly assessedAt: ISODateTime;
}

export type AlarmSeverity =
  | "critical"
  | "major"
  | "minor"
  | "warning"
  | "info";
export type AlarmStatus =
  | "active"
  | "acknowledged"
  | "suppressed"
  | "resolved";
export type AlarmAIStatus =
  | "queued"
  | "analyzing"
  | "diagnosed"
  | "action-created"
  | "not-required";

export interface Alarm {
  readonly id: string;
  readonly code: string;
  readonly turbineId: string;
  readonly subsystem: SubsystemKey;
  readonly severity: AlarmSeverity;
  readonly title: string;
  readonly description: string;
  readonly triggeredAt: ISODateTime;
  readonly durationMinutes: number;
  readonly status: AlarmStatus;
  readonly aiStatus: AlarmAIStatus;
  readonly assignee: string | null;
  readonly acknowledgedAt: ISODateTime | null;
  readonly resolvedAt: ISODateTime | null;
  readonly currentValue: number | null;
  readonly threshold: number | null;
  readonly unit: string | null;
  readonly missionId: string | null;
  readonly evidenceIds: readonly string[];
}

export type AgentLayer = "decision" | "review" | "execution";
export type AgentStatus =
  | "idle"
  | "thinking"
  | "working"
  | "waiting"
  | "reviewing"
  | "failed"
  | "offline";

export interface AgentMetrics {
  readonly successRate: number;
  readonly averageLatencySeconds: number;
  readonly requests24h: number;
  readonly toolCalls24h: number;
  readonly tokenUsage24h: number;
  readonly missionsCompleted: number;
}

export interface Agent {
  readonly id: string;
  readonly name: string;
  readonly shortName: string;
  readonly layer: AgentLayer;
  readonly role: string;
  readonly description: string;
  readonly status: AgentStatus;
  readonly currentTask: string | null;
  readonly currentMissionId: string | null;
  readonly queueDepth: number;
  readonly model: string;
  readonly promptVersion: string;
  readonly skills: readonly string[];
  readonly tools: readonly string[];
  readonly knowledgeSourceIds: readonly string[];
  readonly metrics: AgentMetrics;
  readonly lastActiveAt: ISODateTime;
}

export type MissionStatus =
  | "detected"
  | "investigating"
  | "diagnosed"
  | "decision-pending"
  | "under-review"
  | "approved"
  | "executing"
  | "completed";

export interface Mission {
  readonly id: string;
  readonly turbineId: string;
  readonly title: string;
  readonly summary: string;
  readonly severity: RiskLevel;
  readonly status: MissionStatus;
  readonly progressPercent: number;
  readonly leadAgentId: string;
  readonly agentIds: readonly string[];
  readonly alarmIds: readonly string[];
  readonly evidenceIds: readonly string[];
  readonly diagnosis: string | null;
  readonly confidencePercent: number | null;
  readonly decisionId: string | null;
  readonly workOrderId: string | null;
  readonly nextAction: string;
  readonly createdAt: ISODateTime;
  readonly updatedAt: ISODateTime;
  readonly targetResolutionAt: ISODateTime;
}

export type EvidenceType =
  | "scada-signal"
  | "vibration-spectrum"
  | "model-output"
  | "historical-case"
  | "maintenance-record"
  | "knowledge-document"
  | "weather-forecast"
  | "resource-check";

export interface EvidenceItem {
  readonly id: string;
  readonly missionId: string;
  readonly turbineId: string;
  readonly type: EvidenceType;
  readonly title: string;
  readonly summary: string;
  readonly sourceLabel: string;
  readonly sourceId: string | null;
  readonly observedAt: ISODateTime;
  readonly metric: string | null;
  readonly value: number | null;
  readonly baseline: number | null;
  readonly unit: string | null;
  readonly deltaPercent: number | null;
  readonly confidencePercent: number | null;
}

export type ActivityKind =
  | "detection"
  | "analysis"
  | "retrieval"
  | "diagnosis"
  | "decision"
  | "review"
  | "approval"
  | "work-order"
  | "execution"
  | "system";

export interface ActivityEvent {
  readonly id: string;
  readonly missionId: string;
  readonly timestamp: ISODateTime;
  readonly agentId: string | null;
  readonly actorLabel: string;
  readonly kind: ActivityKind;
  readonly title: string;
  readonly detail: string;
  readonly evidenceIds: readonly string[];
  readonly outcome: "success" | "in-progress" | "attention" | "neutral";
}

export type DecisionStatus =
  | "draft"
  | "under-review"
  | "approved"
  | "rejected"
  | "revision-requested";
export type ApprovalAction =
  | "approve"
  | "reject"
  | "request-revision"
  | "escalate";

export interface DecisionAlternative {
  readonly id: string;
  readonly label: string;
  readonly title: string;
  readonly description: string;
  readonly safetyRisk: RiskLevel;
  readonly deteriorationRiskPercent: number;
  readonly estimatedCostCny: number;
  readonly estimatedDowntimeHours: number;
  readonly estimatedEnergyLossMWh: number;
  readonly weatherWindowId: string | null;
  readonly requiredResources: readonly string[];
  readonly recommended: boolean;
  readonly rationale: string;
}

export interface HumanApproval {
  readonly required: boolean;
  readonly action: ApprovalAction | null;
  readonly approver: string | null;
  readonly approverRole: string | null;
  readonly timestamp: ISODateTime | null;
  readonly reason: string | null;
  readonly comment: string | null;
}

export interface Decision {
  readonly id: string;
  readonly missionId: string;
  readonly turbineId: string;
  readonly incident: string;
  readonly diagnosis: string;
  readonly confidencePercent: number;
  readonly status: DecisionStatus;
  readonly risk: RiskLevel;
  readonly evidenceIds: readonly string[];
  readonly alternatives: readonly DecisionAlternative[];
  readonly recommendedAlternativeId: string;
  readonly recommendedAction: string;
  readonly weatherWindowId: string | null;
  readonly requiredResources: readonly string[];
  readonly approval: HumanApproval;
  readonly createdAt: ISODateTime;
  readonly updatedAt: ISODateTime;
}

export type WorkOrderPriority = "critical" | "high" | "medium" | "low";
export type WorkOrderStatus =
  | "draft"
  | "pending-approval"
  | "scheduled"
  | "in-progress"
  | "paused"
  | "completed"
  | "closed";

export interface WorkOrderTask {
  readonly id: string;
  readonly sequence: number;
  readonly title: string;
  readonly completed: boolean;
  readonly completionNote: string | null;
}

export interface WorkOrderPart {
  readonly partNumber: string;
  readonly name: string;
  readonly quantity: number;
  readonly available: number;
  readonly reserved: number;
}

export interface WorkOrder {
  readonly id: string;
  readonly turbineId: string;
  readonly issue: string;
  readonly description: string;
  readonly priority: WorkOrderPriority;
  readonly status: WorkOrderStatus;
  readonly assignedTeam: string;
  readonly createdByAgentId: string | null;
  readonly relatedMissionId: string | null;
  readonly decisionId: string | null;
  readonly plannedStart: ISODateTime;
  readonly deadline: ISODateTime;
  readonly estimatedDurationHours: number;
  readonly riskLevel: RiskLevel;
  readonly tasks: readonly WorkOrderTask[];
  readonly ppeRequirements: readonly string[];
  readonly requiredTools: readonly string[];
  readonly spareParts: readonly WorkOrderPart[];
  readonly safetyProcedures: readonly string[];
  readonly createdAt: ISODateTime;
  readonly updatedAt: ISODateTime;
}

export type ScadaMetric =
  | "wind-speed"
  | "wind-direction"
  | "rotor-speed"
  | "generator-speed"
  | "active-power"
  | "reactive-power"
  | "generator-temperature"
  | "gearbox-oil-temperature"
  | "main-bearing-temperature"
  | "main-bearing-vibration-rms"
  | "nacelle-temperature"
  | "tower-acceleration"
  | "blade-pitch"
  | "yaw-error"
  | "grid-voltage"
  | "grid-frequency"
  | "anomaly-score";

export interface ScadaThreshold {
  readonly id: string;
  readonly label: string;
  readonly value: number;
  readonly direction: "above" | "below";
  readonly severity: "warning" | "critical";
}

export interface ScadaPoint {
  readonly timestamp: ISODateTime;
  readonly value: number;
  readonly quality: "good" | "uncertain" | "bad";
  readonly isAnomaly: boolean;
  readonly aiEvent: string | null;
}

export interface ScadaSeries {
  readonly id: string;
  readonly turbineId: string;
  readonly metric: ScadaMetric;
  readonly label: string;
  readonly unit: string;
  readonly precision: number;
  readonly currentValue: number;
  readonly normalRange: readonly [number, number];
  readonly thresholds: readonly ScadaThreshold[];
  readonly points: readonly ScadaPoint[];
}

export type WeatherSuitability = "suitable" | "conditional" | "unsafe";

export interface WeatherWindow {
  readonly id: string;
  readonly farmId: string;
  readonly startsAt: ISODateTime;
  readonly endsAt: ISODateTime;
  readonly suitability: WeatherSuitability;
  readonly windSpeedMps: number;
  readonly gustSpeedMps: number;
  readonly waveHeightM: number;
  readonly visibilityKm: number;
  readonly precipitationMm: number;
  readonly lightningRisk: "none" | "low" | "moderate" | "high";
  readonly temperatureC: number;
  readonly reason: string;
  readonly recommendedFor: readonly string[];
}

export type KnowledgeDocumentType =
  | "equipment-manual"
  | "maintenance-procedure"
  | "incident-case"
  | "failure-case"
  | "technical-standard"
  | "manufacturer-bulletin"
  | "historical-work-order"
  | "inspection-report"
  | "scada-analysis-report";

export interface KnowledgeDocument {
  readonly id: string;
  readonly title: string;
  readonly type: KnowledgeDocumentType;
  readonly equipment: string;
  readonly manufacturer: string | null;
  readonly version: string;
  readonly updatedAt: ISODateTime;
  readonly vectorized: boolean;
  readonly pageCount: number;
  readonly language: "zh-CN" | "en-US";
  readonly tags: readonly string[];
  readonly summary: string;
  readonly relatedTurbineIds: readonly string[];
  readonly relatedMissionIds: readonly string[];
}

