import { index, integer, real, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

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
  (table) => [index("agent_executions_mission_time_idx").on(table.missionId, table.startedAt)],
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
