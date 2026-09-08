import {
  applyServerWorkflowMutation,
  initialServerWorkflowSnapshot,
  requireServerWorkflowPersistence,
  SERVER_WORKFLOW_DECISION_ID,
  SERVER_WORKFLOW_MISSION_ID,
  SERVER_WORKFLOW_TURBINE_ID,
  SERVER_WORKFLOW_WORK_ORDER_ID,
  serverWorkflowTaskDefinitions,
  ServerWorkflowTransitionError,
  type ServerWorkflowApproval,
  type ServerWorkflowAuditEvent,
  type ServerWorkflowMutationRequest,
  type ServerWorkflowSnapshot,
  type ServerWorkflowStateSummary,
} from "../lib/server-workflow-contract";
import type { DecisionStatus, MissionStatus, WorkOrderStatus } from "../lib/types";

export interface WorkflowStoreReadResult {
  readonly snapshot: ServerWorkflowSnapshot;
  readonly persistence: "d1" | "ephemeral";
  readonly writable: boolean;
}

export interface WorkflowStoreMutationResult {
  readonly snapshot: ServerWorkflowSnapshot;
  readonly replayed: boolean;
}

interface WorkflowInstanceRow {
  readonly mission_id: string;
  readonly turbine_id: string;
  readonly mission_status: string;
  readonly mission_progress_percent: number;
  readonly decision_id: string;
  readonly decision_status: string;
  readonly decision_risk: string;
  readonly approval_required: number;
  readonly approval_record: unknown;
  readonly work_order_id: string;
  readonly work_order_status: string;
  readonly turbine_health_score: number;
  readonly main_bearing_health_score: number;
  readonly knowledge_case_id: string | null;
  readonly revision: number;
  readonly updated_at: string;
}

interface WorkflowTaskRow {
  readonly id: string;
  readonly sequence: number;
  readonly title: string;
  readonly completed: number;
  readonly completed_at: string | null;
  readonly completed_by: string | null;
}

interface WorkflowAuditRow {
  readonly id: string;
  readonly mission_id: string;
  readonly revision: number;
  readonly event_sequence: number;
  readonly action: ServerWorkflowAuditEvent["action"];
  readonly kind: ServerWorkflowAuditEvent["kind"];
  readonly actor_id: string;
  readonly actor_name: string;
  readonly actor_role: string | null;
  readonly correlation_id: string;
  readonly idempotency_key: string;
  readonly from_state: unknown;
  readonly to_state: unknown;
  readonly detail: string;
  readonly timestamp: string;
}

interface WorkflowIdempotencyRow {
  readonly request_fingerprint: string;
  readonly response_snapshot: unknown;
}

const CREATE_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS workflow_instances (
    mission_id TEXT PRIMARY KEY NOT NULL,
    turbine_id TEXT NOT NULL UNIQUE,
    mission_status TEXT NOT NULL CHECK (mission_status IN ('under-review', 'approved', 'decision-pending', 'diagnosed', 'executing', 'completed')),
    mission_progress_percent INTEGER NOT NULL CHECK (mission_progress_percent BETWEEN 0 AND 100),
    decision_id TEXT NOT NULL UNIQUE,
    decision_status TEXT NOT NULL CHECK (decision_status IN ('under-review', 'approved', 'rejected', 'revision-requested')),
    decision_risk TEXT NOT NULL CHECK (decision_risk = 'high'),
    approval_required INTEGER NOT NULL DEFAULT 1,
    approval_record TEXT,
    work_order_id TEXT NOT NULL UNIQUE,
    work_order_status TEXT NOT NULL CHECK (work_order_status IN ('draft', 'scheduled', 'in-progress', 'completed')),
    turbine_health_score INTEGER NOT NULL CHECK (turbine_health_score BETWEEN 0 AND 100),
    main_bearing_health_score INTEGER NOT NULL CHECK (main_bearing_health_score BETWEEN 0 AND 100),
    knowledge_case_id TEXT,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE UNIQUE INDEX IF NOT EXISTS workflow_instances_turbine_idx ON workflow_instances (turbine_id)`,
  `CREATE TABLE IF NOT EXISTS workflow_tasks (
    id TEXT PRIMARY KEY NOT NULL,
    mission_id TEXT NOT NULL REFERENCES workflow_instances(mission_id),
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    title TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    completed_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (mission_id, sequence)
  )`,
  `CREATE INDEX IF NOT EXISTS workflow_tasks_mission_completed_idx ON workflow_tasks (mission_id, completed)`,
  `CREATE TABLE IF NOT EXISTS workflow_audit_events (
    id TEXT PRIMARY KEY NOT NULL,
    mission_id TEXT NOT NULL REFERENCES workflow_instances(mission_id),
    revision INTEGER NOT NULL CHECK (revision > 0),
    event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
    action TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('approval', 'execution', 'verification', 'knowledge', 'reset')),
    actor_id TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    actor_role TEXT,
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    detail TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    UNIQUE (mission_id, revision, event_sequence)
  )`,
  `CREATE INDEX IF NOT EXISTS workflow_audit_mission_time_idx ON workflow_audit_events (mission_id, timestamp)`,
  `CREATE INDEX IF NOT EXISTS workflow_audit_correlation_idx ON workflow_audit_events (correlation_id)`,
  `CREATE TRIGGER IF NOT EXISTS workflow_audit_revision_guard
    BEFORE INSERT ON workflow_audit_events
    FOR EACH ROW
    WHEN COALESCE((SELECT revision FROM workflow_instances WHERE mission_id = NEW.mission_id), -1) != NEW.revision
    BEGIN
      SELECT RAISE(ABORT, 'workflow revision conflict');
    END`,
  `CREATE TABLE IF NOT EXISTS workflow_idempotency (
    idempotency_key TEXT PRIMARY KEY NOT NULL,
    mission_id TEXT NOT NULL REFERENCES workflow_instances(mission_id),
    request_fingerprint TEXT NOT NULL,
    response_snapshot TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    created_at TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS workflow_idempotency_mission_time_idx ON workflow_idempotency (mission_id, created_at)`,
] as const;

const parseJson = <T>(value: unknown): T => {
  if (typeof value === "string") return JSON.parse(value) as T;
  return value as T;
};

const requestFingerprint = (request: ServerWorkflowMutationRequest): string =>
  JSON.stringify({
    action: request.action,
    actor: {
      id: request.actor.id,
      name: request.actor.name,
      role: request.actor.role ?? null,
    },
    correlationId: request.correlationId,
    expectedRevision: request.expectedRevision,
    reason: request.reason ?? null,
    comment: request.comment ?? null,
    taskId: request.taskId ?? null,
    completed: request.completed ?? null,
  });

const initializationByDatabase = new WeakMap<D1Database, Promise<void>>();

async function initialize(database: D1Database): Promise<void> {
  const existing = initializationByDatabase.get(database);
  if (existing) return existing;

  const initialization = (async () => {
    await database.batch(CREATE_STATEMENTS.map((statement) => database.prepare(statement)));

    const baseline = initialServerWorkflowSnapshot();
    const seedStatements = [
      database
        .prepare(
          `INSERT OR IGNORE INTO workflow_instances (
          mission_id, turbine_id, mission_status, mission_progress_percent,
          decision_id, decision_status, decision_risk, approval_required,
          approval_record, work_order_id, work_order_status,
          turbine_health_score, main_bearing_health_score, knowledge_case_id,
          revision, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .bind(
          baseline.mission.id,
          baseline.turbineId,
          baseline.mission.status,
          baseline.mission.progressPercent,
          baseline.decision.id,
          baseline.decision.status,
          baseline.decision.risk,
          1,
          null,
          baseline.workOrder.id,
          baseline.workOrder.status,
          baseline.health.turbineScore,
          baseline.health.mainBearingScore,
          baseline.knowledgeCaseId,
          baseline.revision,
          baseline.updatedAt,
          baseline.updatedAt,
        ),
      ...baseline.workOrder.tasks.map((task) =>
        database
          .prepare(
            `INSERT OR IGNORE INTO workflow_tasks (
            id, mission_id, sequence, title, completed, completed_at,
            completed_by, created_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          )
          .bind(
            task.id,
            baseline.mission.id,
            task.sequence,
            task.title,
            0,
            null,
            null,
            baseline.updatedAt,
            baseline.updatedAt,
          ),
      ),
    ];
    await database.batch(seedStatements);
  })();

  initializationByDatabase.set(database, initialization);
  try {
    await initialization;
  } catch (error) {
    initializationByDatabase.delete(database);
    throw error;
  }
}

async function readD1Snapshot(database: D1Database): Promise<ServerWorkflowSnapshot> {
  const [instanceResult, tasksResult, auditResult] = await database.batch<
    WorkflowInstanceRow | WorkflowTaskRow | WorkflowAuditRow
  >([
    database
      .prepare(`SELECT * FROM workflow_instances WHERE mission_id = ?`)
      .bind(SERVER_WORKFLOW_MISSION_ID),
    database
      .prepare(`SELECT * FROM workflow_tasks WHERE mission_id = ? ORDER BY sequence ASC`)
      .bind(SERVER_WORKFLOW_MISSION_ID),
    database
      .prepare(
        `SELECT * FROM workflow_audit_events WHERE mission_id = ? ORDER BY revision ASC, event_sequence ASC`,
      )
      .bind(SERVER_WORKFLOW_MISSION_ID),
  ]);
  const instance = instanceResult.results[0] as WorkflowInstanceRow | undefined;

  if (!instance) {
    throw new ServerWorkflowTransitionError(
      "WORKFLOW_NOT_INITIALIZED",
      "The WT-023 workflow instance could not be initialized.",
      503,
    );
  }

  const tasks = (tasksResult.results as WorkflowTaskRow[]).map((task) => ({
    id: task.id,
    sequence: task.sequence,
    title: task.title,
    completed: task.completed === 1,
    completedAt: task.completed_at,
    completedBy: task.completed_by,
  }));
  if (tasks.length !== serverWorkflowTaskDefinitions.length) {
    throw new ServerWorkflowTransitionError(
      "WORKFLOW_INTEGRITY_ERROR",
      `Expected five WT-023 tasks, but found ${tasks.length}.`,
      503,
    );
  }

  const auditEvents = (auditResult.results as WorkflowAuditRow[]).map(
    (event): ServerWorkflowAuditEvent => ({
      id: event.id,
      missionId: SERVER_WORKFLOW_MISSION_ID,
      revision: event.revision,
      eventSequence: event.event_sequence,
      action: event.action,
      kind: event.kind,
      actor: {
        id: event.actor_id,
        name: event.actor_name,
        ...(event.actor_role ? { role: event.actor_role } : {}),
      },
      correlationId: event.correlation_id,
      idempotencyKey: event.idempotency_key,
      fromState: parseJson<ServerWorkflowStateSummary>(event.from_state),
      toState: parseJson<ServerWorkflowStateSummary>(event.to_state),
      detail: event.detail,
      timestamp: event.timestamp,
    }),
  );

  return {
    turbineId: SERVER_WORKFLOW_TURBINE_ID,
    mission: {
      id: SERVER_WORKFLOW_MISSION_ID,
      status: instance.mission_status as MissionStatus,
      progressPercent: instance.mission_progress_percent,
    },
    decision: {
      id: SERVER_WORKFLOW_DECISION_ID,
      risk: "high",
      status: instance.decision_status as DecisionStatus,
      approvalRequired: true,
      approval: instance.approval_record
        ? parseJson<ServerWorkflowApproval>(instance.approval_record)
        : null,
    },
    workOrder: {
      id: SERVER_WORKFLOW_WORK_ORDER_ID,
      status: instance.work_order_status as WorkOrderStatus,
      tasks,
      completedTaskCount: tasks.filter((task) => task.completed).length,
      totalTaskCount: tasks.length,
    },
    health: {
      turbineScore: instance.turbine_health_score,
      mainBearingScore: instance.main_bearing_health_score,
    },
    knowledgeCaseId: instance.knowledge_case_id,
    auditEvents,
    revision: instance.revision,
    updatedAt: instance.updated_at,
  };
}

export async function readServerWorkflow(database?: D1Database): Promise<WorkflowStoreReadResult> {
  if (!database) {
    return {
      snapshot: initialServerWorkflowSnapshot(),
      persistence: "ephemeral",
      writable: false,
    };
  }

  await initialize(database);
  return {
    snapshot: await readD1Snapshot(database),
    persistence: "d1",
    writable: true,
  };
}

function isConstraintError(error: unknown): boolean {
  return (
    error instanceof Error && /constraint|unique|workflow revision conflict/i.test(error.message)
  );
}

export async function mutateServerWorkflow(
  database: D1Database | undefined,
  request: ServerWorkflowMutationRequest,
  timestamp = new Date().toISOString(),
): Promise<WorkflowStoreMutationResult> {
  if (!database) {
    requireServerWorkflowPersistence(false);
  }

  await initialize(database);
  const fingerprint = requestFingerprint(request);
  const prior = await database
    .prepare(
      `SELECT request_fingerprint, response_snapshot FROM workflow_idempotency WHERE idempotency_key = ?`,
    )
    .bind(request.idempotencyKey)
    .first<WorkflowIdempotencyRow>();
  if (prior) {
    if (prior.request_fingerprint !== fingerprint) {
      throw new ServerWorkflowTransitionError(
        "IDEMPOTENCY_KEY_REUSED",
        "This idempotency key was already used for a different request.",
        409,
      );
    }
    return { snapshot: parseJson<ServerWorkflowSnapshot>(prior.response_snapshot), replayed: true };
  }

  const current = await readD1Snapshot(database);
  const next = applyServerWorkflowMutation(current, request, timestamp);
  const newEvents = next.auditEvents.filter((event) => event.revision === next.revision);
  const approvalJson = next.decision.approval ? JSON.stringify(next.decision.approval) : null;

  const statements = [
    database
      .prepare(
        `UPDATE workflow_instances SET
          mission_status = ?, mission_progress_percent = ?, decision_status = ?,
          approval_record = ?, work_order_status = ?, turbine_health_score = ?,
          main_bearing_health_score = ?, knowledge_case_id = ?, revision = ?, updated_at = ?
        WHERE mission_id = ? AND revision = ?`,
      )
      .bind(
        next.mission.status,
        next.mission.progressPercent,
        next.decision.status,
        approvalJson,
        next.workOrder.status,
        next.health.turbineScore,
        next.health.mainBearingScore,
        next.knowledgeCaseId,
        next.revision,
        next.updatedAt,
        next.mission.id,
        current.revision,
      ),
    ...next.workOrder.tasks.map((task) =>
      database
        .prepare(
          `UPDATE workflow_tasks SET completed = ?, completed_at = ?, completed_by = ?, updated_at = ?
          WHERE id = ? AND mission_id = ?`,
        )
        .bind(
          task.completed ? 1 : 0,
          task.completedAt,
          task.completedBy,
          next.updatedAt,
          task.id,
          next.mission.id,
        ),
    ),
    ...newEvents.map((event) =>
      database
        .prepare(
          `INSERT INTO workflow_audit_events (
            id, mission_id, revision, event_sequence, action, kind, actor_id,
            actor_name, actor_role, correlation_id, idempotency_key, from_state,
            to_state, detail, timestamp
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .bind(
          event.id,
          event.missionId,
          event.revision,
          event.eventSequence,
          event.action,
          event.kind,
          event.actor.id,
          event.actor.name,
          event.actor.role ?? null,
          event.correlationId,
          event.idempotencyKey,
          JSON.stringify(event.fromState),
          JSON.stringify(event.toState),
          event.detail,
          event.timestamp,
        ),
    ),
    database
      .prepare(
        `INSERT INTO workflow_idempotency (
          idempotency_key, mission_id, request_fingerprint, response_snapshot,
          correlation_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        request.idempotencyKey,
        next.mission.id,
        fingerprint,
        JSON.stringify(next),
        request.correlationId,
        timestamp,
      ),
  ];

  try {
    const results = await database.batch(statements);
    const updateChanges = Number(results[0]?.meta.changes ?? 0);
    if (updateChanges !== 1) {
      throw new ServerWorkflowTransitionError(
        "REVISION_CONFLICT",
        "The workflow changed while this request was being committed.",
        409,
        { expectedRevision: request.expectedRevision },
      );
    }
  } catch (error) {
    if (error instanceof ServerWorkflowTransitionError) throw error;
    if (isConstraintError(error)) {
      const replay = await database
        .prepare(
          `SELECT request_fingerprint, response_snapshot FROM workflow_idempotency WHERE idempotency_key = ?`,
        )
        .bind(request.idempotencyKey)
        .first<WorkflowIdempotencyRow>();
      if (replay?.request_fingerprint === fingerprint) {
        return {
          snapshot: parseJson<ServerWorkflowSnapshot>(replay.response_snapshot),
          replayed: true,
        };
      }
      throw new ServerWorkflowTransitionError(
        "REVISION_CONFLICT",
        "The workflow changed while this request was being committed.",
        409,
        { expectedRevision: request.expectedRevision },
      );
    }
    throw error;
  }

  return { snapshot: next, replayed: false };
}
