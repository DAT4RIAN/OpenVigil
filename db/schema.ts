import { sql } from "drizzle-orm";
import {
  check,
  index,
  integer,
  real,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

const timestamps = {
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
};

export const windFarmsTable = sqliteTable("wind_farms", {
  id: text("id").primaryKey(),
  code: text("code").notNull().unique(),
  name: text("name").notNull(),
  location: text("location").notNull(),
  totalCapacityMw: real("total_capacity_mw").notNull(),
  status: text("status").notNull(),
  ...timestamps,
});

export const windTurbinesTable = sqliteTable(
  "wind_turbines",
  {
    id: text("id").primaryKey(),
    farmId: text("farm_id")
      .notNull()
      .references(() => windFarmsTable.id),
    model: text("model").notNull(),
    serialNumber: text("serial_number").notNull().unique(),
    ratedPowerMw: real("rated_power_mw").notNull(),
    status: text("status").notNull(),
    healthScore: real("health_score").notNull(),
    ...timestamps,
  },
  (table) => [index("wind_turbines_farm_idx").on(table.farmId)],
);

export const subsystemsTable = sqliteTable(
  "subsystems",
  {
    id: text("id").primaryKey(),
    turbineId: text("turbine_id")
      .notNull()
      .references(() => windTurbinesTable.id),
    key: text("key").notNull(),
    name: text("name").notNull(),
    healthScore: real("health_score").notNull(),
    state: text("state").notNull(),
    ...timestamps,
  },
  (table) => [uniqueIndex("subsystems_turbine_key_uidx").on(table.turbineId, table.key)],
);

export const sensorsTable = sqliteTable(
  "sensors",
  {
    id: text("id").primaryKey(),
    turbineId: text("turbine_id")
      .notNull()
      .references(() => windTurbinesTable.id),
    subsystemId: text("subsystem_id").references(() => subsystemsTable.id),
    metric: text("metric").notNull(),
    unit: text("unit").notNull(),
    source: text("source").notNull(),
    sampleIntervalSeconds: integer("sample_interval_seconds").notNull(),
    enabled: integer("enabled", { mode: "boolean" }).notNull().default(true),
    ...timestamps,
  },
  (table) => [uniqueIndex("sensors_turbine_metric_uidx").on(table.turbineId, table.metric)],
);

export const scadaMeasurementsTable = sqliteTable(
  "scada_measurements",
  {
    id: text("id").primaryKey(),
    sensorId: text("sensor_id")
      .notNull()
      .references(() => sensorsTable.id),
    turbineId: text("turbine_id")
      .notNull()
      .references(() => windTurbinesTable.id),
    timestamp: text("timestamp").notNull(),
    value: real("value").notNull(),
    quality: text("quality").notNull(),
    isAnomaly: integer("is_anomaly", { mode: "boolean" }).notNull().default(false),
    correlationId: text("correlation_id"),
  },
  (table) => [
    index("scada_turbine_time_idx").on(table.turbineId, table.timestamp),
    index("scada_sensor_time_idx").on(table.sensorId, table.timestamp),
  ],
);

export const alarmsTable = sqliteTable(
  "alarms",
  {
    id: text("id").primaryKey(),
    turbineId: text("turbine_id")
      .notNull()
      .references(() => windTurbinesTable.id),
    subsystemId: text("subsystem_id").references(() => subsystemsTable.id),
    code: text("code").notNull(),
    severity: text("severity").notNull(),
    title: text("title").notNull(),
    status: text("status").notNull(),
    triggeredAt: text("triggered_at").notNull(),
    resolvedAt: text("resolved_at"),
    missionId: text("mission_id"),
    correlationId: text("correlation_id").notNull(),
    ...timestamps,
  },
  (table) => [index("alarms_turbine_status_idx").on(table.turbineId, table.status)],
);

export const healthAssessmentsTable = sqliteTable("health_assessments", {
  id: text("id").primaryKey(),
  turbineId: text("turbine_id")
    .notNull()
    .references(() => windTurbinesTable.id),
  subsystemId: text("subsystem_id").references(() => subsystemsTable.id),
  healthScore: real("health_score").notNull(),
  anomalyScore: real("anomaly_score").notNull(),
  failureProbability30d: real("failure_probability_30d").notNull(),
  remainingUsefulLifeDays: integer("remaining_useful_life_days"),
  assessedAt: text("assessed_at").notNull(),
  modelVersion: text("model_version").notNull(),
});

export const agentsTable = sqliteTable("agents", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  layer: text("layer").notNull(),
  role: text("role").notNull(),
  status: text("status").notNull(),
  model: text("model").notNull(),
  promptVersion: text("prompt_version").notNull(),
  ...timestamps,
});

export const agentSkillsTable = sqliteTable(
  "agent_skills",
  {
    id: text("id").primaryKey(),
    agentId: text("agent_id")
      .notNull()
      .references(() => agentsTable.id),
    name: text("name").notNull(),
    description: text("description").notNull(),
  },
  (table) => [uniqueIndex("agent_skills_agent_name_uidx").on(table.agentId, table.name)],
);

export const agentToolsTable = sqliteTable(
  "agent_tools",
  {
    id: text("id").primaryKey(),
    agentId: text("agent_id")
      .notNull()
      .references(() => agentsTable.id),
    name: text("name").notNull(),
    inputSchema: text("input_schema", { mode: "json" }).notNull(),
    riskLevel: text("risk_level").notNull(),
  },
  (table) => [uniqueIndex("agent_tools_agent_name_uidx").on(table.agentId, table.name)],
);

export const missionsTable = sqliteTable(
  "missions",
  {
    id: text("id").primaryKey(),
    turbineId: text("turbine_id")
      .notNull()
      .references(() => windTurbinesTable.id),
    title: text("title").notNull(),
    severity: text("severity").notNull(),
    status: text("status").notNull(),
    progressPercent: integer("progress_percent").notNull(),
    leadAgentId: text("lead_agent_id")
      .notNull()
      .references(() => agentsTable.id),
    diagnosis: text("diagnosis"),
    confidencePercent: real("confidence_percent"),
    correlationId: text("correlation_id").notNull(),
    ...timestamps,
  },
  (table) => [index("missions_turbine_status_idx").on(table.turbineId, table.status)],
);

export const missionTasksTable = sqliteTable("mission_tasks", {
  id: text("id").primaryKey(),
  missionId: text("mission_id")
    .notNull()
    .references(() => missionsTable.id),
  agentId: text("agent_id").references(() => agentsTable.id),
  title: text("title").notNull(),
  status: text("status").notNull(),
  sequence: integer("sequence").notNull(),
  startedAt: text("started_at"),
  completedAt: text("completed_at"),
});

export const evidenceTable = sqliteTable("evidence", {
  id: text("id").primaryKey(),
  missionId: text("mission_id")
    .notNull()
    .references(() => missionsTable.id),
  turbineId: text("turbine_id")
    .notNull()
    .references(() => windTurbinesTable.id),
  type: text("type").notNull(),
  title: text("title").notNull(),
  summary: text("summary").notNull(),
  sourceLabel: text("source_label").notNull(),
  sourceId: text("source_id"),
  observedAt: text("observed_at").notNull(),
  payload: text("payload", { mode: "json" }),
});

export const decisionsTable = sqliteTable("decisions", {
  id: text("id").primaryKey(),
  missionId: text("mission_id")
    .notNull()
    .references(() => missionsTable.id),
  turbineId: text("turbine_id")
    .notNull()
    .references(() => windTurbinesTable.id),
  status: text("status").notNull(),
  risk: text("risk").notNull(),
  recommendedAction: text("recommended_action").notNull(),
  confidencePercent: real("confidence_percent").notNull(),
  alternatives: text("alternatives", { mode: "json" }).notNull(),
  ...timestamps,
});

export const approvalsTable = sqliteTable("approvals", {
  id: text("id").primaryKey(),
  decisionId: text("decision_id")
    .notNull()
    .references(() => decisionsTable.id),
  action: text("action").notNull(),
  approver: text("approver").notNull(),
  approverRole: text("approver_role").notNull(),
  reason: text("reason").notNull(),
  comment: text("comment").notNull(),
  timestamp: text("timestamp").notNull(),
  correlationId: text("correlation_id").notNull(),
});

export const workOrdersTable = sqliteTable(
  "work_orders",
  {
    id: text("id").primaryKey(),
    turbineId: text("turbine_id")
      .notNull()
      .references(() => windTurbinesTable.id),
    missionId: text("mission_id").references(() => missionsTable.id),
    decisionId: text("decision_id").references(() => decisionsTable.id),
    issue: text("issue").notNull(),
    priority: text("priority").notNull(),
    status: text("status").notNull(),
    assignedTeam: text("assigned_team").notNull(),
    plannedStart: text("planned_start").notNull(),
    deadline: text("deadline").notNull(),
    tasks: text("tasks", { mode: "json" }).notNull(),
    safetyPlan: text("safety_plan", { mode: "json" }).notNull(),
    ...timestamps,
  },
  (table) => [index("work_orders_turbine_status_idx").on(table.turbineId, table.status)],
);

/**
 * Stock is stored once on the part master. Reserved and available quantities are
 * derived from active inventory reservations so those values cannot drift apart.
 */
export const sparePartsTable = sqliteTable(
  "spare_parts",
  {
    id: text("id").primaryKey(),
    partNumber: text("part_number").notNull().unique(),
    name: text("name").notNull(),
    category: text("category").notNull(),
    warehouse: text("warehouse").notNull(),
    onHand: integer("on_hand").notNull(),
    reorderPoint: integer("reorder_point").notNull(),
    unit: text("unit").notNull(),
    status: text("status").notNull(),
    compatibleTurbineModels: text("compatible_turbine_models", { mode: "json" }).notNull(),
    ...timestamps,
  },
  (table) => [
    index("spare_parts_category_status_idx").on(table.category, table.status),
    check("spare_parts_on_hand_nonnegative_chk", sql`${table.onHand} >= 0`),
    check("spare_parts_reorder_point_nonnegative_chk", sql`${table.reorderPoint} >= 0`),
    check(
      "spare_parts_status_chk",
      sql`${table.status} in ('in-stock', 'low-stock', 'out-of-stock', 'quarantined')`,
    ),
  ],
);

/** One row represents the planned/issued quantity of one part on one work order. */
export const workOrderPartsTable = sqliteTable(
  "work_order_parts",
  {
    id: text("id").primaryKey(),
    workOrderId: text("work_order_id")
      .notNull()
      .references(() => workOrdersTable.id),
    sparePartId: text("spare_part_id")
      .notNull()
      .references(() => sparePartsTable.id),
    quantityRequired: integer("quantity_required").notNull(),
    quantityIssued: integer("quantity_issued").notNull().default(0),
    status: text("status").notNull(),
    notes: text("notes"),
    ...timestamps,
  },
  (table) => [
    uniqueIndex("work_order_parts_work_order_part_uidx").on(table.workOrderId, table.sparePartId),
    index("work_order_parts_part_status_idx").on(table.sparePartId, table.status),
    check("work_order_parts_required_positive_chk", sql`${table.quantityRequired} > 0`),
    check("work_order_parts_issued_nonnegative_chk", sql`${table.quantityIssued} >= 0`),
    check(
      "work_order_parts_issued_not_over_required_chk",
      sql`${table.quantityIssued} <= ${table.quantityRequired}`,
    ),
    check(
      "work_order_parts_status_chk",
      sql`${table.status} in ('requested', 'reserved', 'issued', 'consumed', 'cancelled')`,
    ),
  ],
);

/**
 * Reservation ledger. It references the normalized work-order/part requirement;
 * the related work order and part are therefore unambiguous without duplicate FKs.
 */
export const inventoryReservationsTable = sqliteTable(
  "inventory_reservations",
  {
    id: text("id").primaryKey(),
    workOrderPartId: text("work_order_part_id")
      .notNull()
      .references(() => workOrderPartsTable.id),
    quantity: integer("quantity").notNull(),
    status: text("status").notNull(),
    reservedAt: text("reserved_at").notNull(),
    releasedAt: text("released_at"),
    consumedAt: text("consumed_at"),
    correlationId: text("correlation_id").notNull(),
    ...timestamps,
  },
  (table) => [
    index("inventory_reservations_requirement_status_idx").on(table.workOrderPartId, table.status),
    index("inventory_reservations_correlation_idx").on(table.correlationId),
    check("inventory_reservations_quantity_positive_chk", sql`${table.quantity} > 0`),
    check(
      "inventory_reservations_status_chk",
      sql`${table.status} in ('reserved', 'released', 'consumed', 'cancelled')`,
    ),
  ],
);

export const crewsTable = sqliteTable(
  "crews",
  {
    id: text("id").primaryKey(),
    name: text("name").notNull(),
    specialties: text("specialties", { mode: "json" }).notNull(),
    memberCount: integer("member_count").notNull(),
    availability: text("availability").notNull(),
    certifications: text("certifications", { mode: "json" }).notNull(),
    currentLocation: text("current_location").notNull(),
    ...timestamps,
  },
  (table) => [
    index("crews_availability_idx").on(table.availability),
    check("crews_member_count_positive_chk", sql`${table.memberCount} > 0`),
    check(
      "crews_availability_chk",
      sql`${table.availability} in ('available', 'reserved', 'assigned', 'unavailable')`,
    ),
  ],
);

export const vesselsTable = sqliteTable(
  "vessels",
  {
    id: text("id").primaryKey(),
    name: text("name").notNull(),
    vesselType: text("vessel_type").notNull(),
    availability: text("availability").notNull(),
    capacity: integer("capacity").notNull(),
    maxWaveHeightM: real("max_wave_height_m").notNull(),
    berth: text("berth").notNull(),
    ...timestamps,
  },
  (table) => [
    index("vessels_availability_idx").on(table.availability),
    check("vessels_capacity_positive_chk", sql`${table.capacity} > 0`),
    check("vessels_max_wave_height_positive_chk", sql`${table.maxWaveHeightM} > 0`),
    check(
      "vessels_availability_chk",
      sql`${table.availability} in ('available', 'reserved', 'assigned', 'unavailable')`,
    ),
  ],
);

export const maintenanceToolsTable = sqliteTable(
  "maintenance_tools",
  {
    id: text("id").primaryKey(),
    name: text("name").notNull(),
    category: text("category").notNull(),
    availability: text("availability").notNull(),
    calibrationDueAt: text("calibration_due_at").notNull(),
    location: text("location").notNull(),
    ...timestamps,
  },
  (table) => [
    index("maintenance_tools_availability_idx").on(table.availability),
    index("maintenance_tools_calibration_due_idx").on(table.calibrationDueAt),
    check(
      "maintenance_tools_availability_chk",
      sql`${table.availability} in ('available', 'reserved', 'assigned', 'unavailable', 'calibration')`,
    ),
  ],
);

/**
 * Normalized crew/vessel/tool allocation. The exactly-one check keeps the
 * polymorphic assignment referentially sound while retaining concrete FKs.
 */
export const resourceAssignmentsTable = sqliteTable(
  "resource_assignments",
  {
    id: text("id").primaryKey(),
    workOrderId: text("work_order_id")
      .notNull()
      .references(() => workOrdersTable.id),
    crewId: text("crew_id").references(() => crewsTable.id),
    vesselId: text("vessel_id").references(() => vesselsTable.id),
    maintenanceToolId: text("maintenance_tool_id").references(() => maintenanceToolsTable.id),
    role: text("role").notNull(),
    status: text("status").notNull(),
    plannedFrom: text("planned_from").notNull(),
    plannedTo: text("planned_to").notNull(),
    assignedAt: text("assigned_at").notNull(),
    releasedAt: text("released_at"),
    correlationId: text("correlation_id").notNull(),
    ...timestamps,
  },
  (table) => [
    index("resource_assignments_work_order_status_idx").on(table.workOrderId, table.status),
    index("resource_assignments_crew_idx").on(table.crewId),
    index("resource_assignments_vessel_idx").on(table.vesselId),
    index("resource_assignments_tool_idx").on(table.maintenanceToolId),
    check(
      "resource_assignments_exactly_one_resource_chk",
      sql`(case when ${table.crewId} is not null then 1 else 0 end + case when ${table.vesselId} is not null then 1 else 0 end + case when ${table.maintenanceToolId} is not null then 1 else 0 end) = 1`,
    ),
    check(
      "resource_assignments_status_chk",
      sql`${table.status} in ('reserved', 'assigned', 'released', 'cancelled')`,
    ),
    check("resource_assignments_window_chk", sql`${table.plannedTo} > ${table.plannedFrom}`),
  ],
);

export const maintenanceRecordsTable = sqliteTable("maintenance_records", {
  id: text("id").primaryKey(),
  workOrderId: text("work_order_id")
    .notNull()
    .references(() => workOrdersTable.id),
  turbineId: text("turbine_id")
    .notNull()
    .references(() => windTurbinesTable.id),
  performedBy: text("performed_by").notNull(),
  startedAt: text("started_at").notNull(),
  completedAt: text("completed_at").notNull(),
  findings: text("findings").notNull(),
  verification: text("verification").notNull(),
  evidenceIds: text("evidence_ids", { mode: "json" }).notNull(),
});

export const knowledgeDocumentsTable = sqliteTable("knowledge_documents", {
  id: text("id").primaryKey(),
  title: text("title").notNull(),
  type: text("type").notNull(),
  equipment: text("equipment").notNull(),
  version: text("version").notNull(),
  vectorized: integer("vectorized", { mode: "boolean" }).notNull(),
  sourceUri: text("source_uri"),
  ...timestamps,
});

/**
 * Retrieval is grounded at passage granularity. Scope columns are intentionally
 * nullable: null means the passage is generally applicable, while populated
 * values constrain it to the referenced operational context. Document
 * provenance remains relational through the required knowledge-document FK.
 */
export const knowledgePassagesTable = sqliteTable(
  "knowledge_passages",
  {
    id: text("id").primaryKey(),
    documentId: text("document_id")
      .notNull()
      .references(() => knowledgeDocumentsTable.id),
    page: integer("page").notNull(),
    section: text("section").notNull(),
    body: text("body").notNull(),
    contentHash: text("content_hash").notNull(),
    tokenCount: integer("token_count").notNull(),
    turbineId: text("turbine_id"),
    missionId: text("mission_id"),
    ...timestamps,
  },
  (table) => [
    index("knowledge_passages_document_page_idx").on(table.documentId, table.page),
    index("knowledge_passages_scope_idx").on(table.turbineId, table.missionId),
    uniqueIndex("knowledge_passages_document_hash_uidx").on(table.documentId, table.contentHash),
    check("knowledge_passages_page_positive_chk", sql`${table.page} > 0`),
    check("knowledge_passages_token_count_nonnegative_chk", sql`${table.tokenCount} >= 0`),
  ],
);

export const failureCasesTable = sqliteTable("failure_cases", {
  id: text("id").primaryKey(),
  turbineId: text("turbine_id").references(() => windTurbinesTable.id),
  component: text("component").notNull(),
  failureMode: text("failure_mode").notNull(),
  symptoms: text("symptoms", { mode: "json" }).notNull(),
  rootCause: text("root_cause").notNull(),
  action: text("action").notNull(),
  outcome: text("outcome").notNull(),
  sourceDocumentIds: text("source_document_ids", { mode: "json" }).notNull(),
  closedAt: text("closed_at").notNull(),
});

export const agentExecutionsTable = sqliteTable(
  "agent_executions",
  {
    id: text("id").primaryKey(),
    missionId: text("mission_id").references(() => missionsTable.id),
    agentId: text("agent_id")
      .notNull()
      .references(() => agentsTable.id),
    toolName: text("tool_name").notNull(),
    status: text("status").notNull(),
    input: text("input", { mode: "json" }).notNull(),
    output: text("output", { mode: "json" }),
    startedAt: text("started_at").notNull(),
    completedAt: text("completed_at"),
    latencyMs: integer("latency_ms"),
    tokenUsage: integer("token_usage"),
    error: text("error"),
    correlationId: text("correlation_id").notNull(),
  },
  (table) => [
    index("agent_executions_mission_time_idx").on(table.missionId, table.startedAt),
    index("agent_executions_agent_time_idx").on(table.agentId, table.startedAt),
    index("agent_executions_status_time_idx").on(table.status, table.startedAt),
    index("agent_executions_tool_time_idx").on(table.toolName, table.startedAt),
    uniqueIndex("agent_executions_correlation_uidx").on(table.correlationId),
  ],
);

export const activityEventsTable = sqliteTable(
  "activity_events",
  {
    id: text("id").primaryKey(),
    missionId: text("mission_id")
      .notNull()
      .references(() => missionsTable.id),
    actorType: text("actor_type").notNull(),
    actorId: text("actor_id"),
    kind: text("kind").notNull(),
    title: text("title").notNull(),
    detail: text("detail").notNull(),
    timestamp: text("timestamp").notNull(),
    correlationId: text("correlation_id").notNull(),
  },
  (table) => [index("activity_mission_time_idx").on(table.missionId, table.timestamp)],
);

/**
 * Authoritative server-side state for the WT-023 closed-loop demo. The runtime
 * store intentionally keeps this workflow separate from the read-only fixture
 * tables above so it can safely bootstrap on a newly provisioned D1 database.
 */
export const workflowInstancesTable = sqliteTable(
  "workflow_instances",
  {
    missionId: text("mission_id").primaryKey(),
    turbineId: text("turbine_id").notNull().unique(),
    missionStatus: text("mission_status").notNull(),
    missionProgressPercent: integer("mission_progress_percent").notNull(),
    decisionId: text("decision_id").notNull().unique(),
    decisionStatus: text("decision_status").notNull(),
    decisionRisk: text("decision_risk").notNull(),
    approvalRequired: integer("approval_required", { mode: "boolean" }).notNull().default(true),
    approvalRecord: text("approval_record", { mode: "json" }),
    workOrderId: text("work_order_id").notNull().unique(),
    workOrderStatus: text("work_order_status").notNull(),
    turbineHealthScore: integer("turbine_health_score").notNull(),
    mainBearingHealthScore: integer("main_bearing_health_score").notNull(),
    knowledgeCaseId: text("knowledge_case_id"),
    revision: integer("revision").notNull().default(0),
    ...timestamps,
  },
  (table) => [
    index("workflow_instances_turbine_idx").on(table.turbineId),
    check(
      "workflow_instances_mission_status_chk",
      sql`${table.missionStatus} in ('under-review', 'approved', 'decision-pending', 'diagnosed', 'executing', 'completed')`,
    ),
    check(
      "workflow_instances_decision_status_chk",
      sql`${table.decisionStatus} in ('under-review', 'approved', 'rejected', 'revision-requested')`,
    ),
    check("workflow_instances_decision_risk_chk", sql`${table.decisionRisk} = 'high'`),
    check(
      "workflow_instances_work_order_status_chk",
      sql`${table.workOrderStatus} in ('draft', 'scheduled', 'in-progress', 'completed')`,
    ),
    check(
      "workflow_instances_mission_progress_chk",
      sql`${table.missionProgressPercent} between 0 and 100`,
    ),
    check(
      "workflow_instances_turbine_health_chk",
      sql`${table.turbineHealthScore} between 0 and 100`,
    ),
    check(
      "workflow_instances_main_bearing_health_chk",
      sql`${table.mainBearingHealthScore} between 0 and 100`,
    ),
    check("workflow_instances_revision_nonnegative_chk", sql`${table.revision} >= 0`),
  ],
);

export const workflowTasksTable = sqliteTable(
  "workflow_tasks",
  {
    id: text("id").primaryKey(),
    missionId: text("mission_id")
      .notNull()
      .references(() => workflowInstancesTable.missionId),
    sequence: integer("sequence").notNull(),
    title: text("title").notNull(),
    completed: integer("completed", { mode: "boolean" }).notNull().default(false),
    completedAt: text("completed_at"),
    completedBy: text("completed_by"),
    fieldEvidence: text("field_evidence", { mode: "json" }),
    ...timestamps,
  },
  (table) => [
    uniqueIndex("workflow_tasks_mission_sequence_uidx").on(table.missionId, table.sequence),
    index("workflow_tasks_mission_completed_idx").on(table.missionId, table.completed),
    check("workflow_tasks_sequence_positive_chk", sql`${table.sequence} > 0`),
  ],
);

export const workflowAuditEventsTable = sqliteTable(
  "workflow_audit_events",
  {
    id: text("id").primaryKey(),
    missionId: text("mission_id")
      .notNull()
      .references(() => workflowInstancesTable.missionId),
    revision: integer("revision").notNull(),
    eventSequence: integer("event_sequence").notNull(),
    action: text("action").notNull(),
    kind: text("kind").notNull(),
    actorId: text("actor_id").notNull(),
    actorName: text("actor_name").notNull(),
    actorRole: text("actor_role"),
    correlationId: text("correlation_id").notNull(),
    idempotencyKey: text("idempotency_key").notNull(),
    fromState: text("from_state", { mode: "json" }).notNull(),
    toState: text("to_state", { mode: "json" }).notNull(),
    detail: text("detail").notNull(),
    fieldEvidence: text("field_evidence", { mode: "json" }),
    timestamp: text("timestamp").notNull(),
  },
  (table) => [
    uniqueIndex("workflow_audit_mission_revision_sequence_uidx").on(
      table.missionId,
      table.revision,
      table.eventSequence,
    ),
    index("workflow_audit_mission_time_idx").on(table.missionId, table.timestamp),
    index("workflow_audit_correlation_idx").on(table.correlationId),
    check("workflow_audit_revision_positive_chk", sql`${table.revision} > 0`),
    check("workflow_audit_event_sequence_positive_chk", sql`${table.eventSequence} > 0`),
    check(
      "workflow_audit_kind_chk",
      sql`${table.kind} in ('approval', 'execution', 'verification', 'knowledge', 'reset')`,
    ),
  ],
);

export const workflowIdempotencyTable = sqliteTable(
  "workflow_idempotency",
  {
    idempotencyKey: text("idempotency_key").primaryKey(),
    missionId: text("mission_id")
      .notNull()
      .references(() => workflowInstancesTable.missionId),
    requestFingerprint: text("request_fingerprint").notNull(),
    responseSnapshot: text("response_snapshot", { mode: "json" }).notNull(),
    correlationId: text("correlation_id").notNull(),
    createdAt: text("created_at").notNull(),
  },
  (table) => [index("workflow_idempotency_mission_time_idx").on(table.missionId, table.createdAt)],
);

export const alarmRuntimeStateTable = sqliteTable("alarm_runtime_state", {
  alarmId: text("alarm_id").primaryKey(),
  status: text("status").notNull(),
  assignee: text("assignee"),
  acknowledgedAt: text("acknowledged_at"),
  revision: integer("revision").notNull().default(0),
  mutationToken: text("mutation_token").notNull().default(""),
  updatedAt: text("updated_at").notNull(),
});

export const alarmMutationAuditTable = sqliteTable(
  "alarm_mutation_audit",
  {
    id: text("id").primaryKey(),
    alarmId: text("alarm_id").notNull(),
    action: text("action").notNull(),
    actorId: text("actor_id").notNull(),
    actorName: text("actor_name").notNull(),
    actorRole: text("actor_role").notNull(),
    beforeState: text("before_state", { mode: "json" }).notNull(),
    afterState: text("after_state", { mode: "json" }).notNull(),
    correlationId: text("correlation_id").notNull(),
    idempotencyKey: text("idempotency_key").notNull().unique(),
    requestFingerprint: text("request_fingerprint").notNull(),
    timestamp: text("timestamp").notNull(),
  },
  (table) => [index("alarm_mutation_audit_alarm_time_idx").on(table.alarmId, table.timestamp)],
);
