import type { Alarm } from "../lib/types";

export type AlarmMutationAction = "acknowledge" | "assign";

export interface AlarmMutationRequest {
  readonly alarmId: string;
  readonly action: AlarmMutationAction;
  readonly assignee?: string | null;
  readonly correlationId: string;
  readonly idempotencyKey: string;
}

export interface AlarmMutationAudit {
  readonly id: string;
  readonly alarmId: string;
  readonly action: AlarmMutationAction;
  readonly actor: { readonly id: string; readonly name: string; readonly role: string };
  readonly before: { readonly status: Alarm["status"]; readonly assignee: string | null };
  readonly after: { readonly status: Alarm["status"]; readonly assignee: string | null };
  readonly correlationId: string;
  readonly idempotencyKey: string;
  readonly timestamp: string;
}

interface AlarmStateRow {
  readonly alarm_id: string;
  readonly status: Alarm["status"];
  readonly assignee: string | null;
  readonly acknowledged_at: string | null;
  readonly revision: number;
  readonly mutation_token: string;
  readonly updated_at: string;
}

interface IdempotencyRow {
  readonly request_fingerprint: string;
}

const actor = {
  id: "demo-alarm-operator",
  name: "值班工程师",
  role: "alarm-operator",
} as const;

const CREATE_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS alarm_runtime_state (
    alarm_id TEXT PRIMARY KEY NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'acknowledged', 'suppressed', 'resolved')),
    assignee TEXT,
    acknowledged_at TEXT,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    mutation_token TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS alarm_mutation_audit (
    id TEXT PRIMARY KEY NOT NULL,
    alarm_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('acknowledge', 'assign')),
    actor_id TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    before_state TEXT NOT NULL,
    after_state TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_fingerprint TEXT NOT NULL,
    timestamp TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS alarm_mutation_audit_alarm_time_idx ON alarm_mutation_audit (alarm_id, timestamp)`,
] as const;

const initializationByDatabase = new WeakMap<D1Database, Promise<void>>();

async function initialize(database: D1Database): Promise<void> {
  const existing = initializationByDatabase.get(database);
  if (existing) return existing;
  const initialization = (async () => {
    await database.batch(CREATE_STATEMENTS.map((statement) => database.prepare(statement)));
    const columns = await database
      .prepare("PRAGMA table_info(alarm_runtime_state)")
      .all<{ name: string }>();
    if (!columns.results.some((column) => column.name === "mutation_token")) {
      await database.batch([
        database.prepare(
          "ALTER TABLE alarm_runtime_state ADD COLUMN mutation_token TEXT NOT NULL DEFAULT ''",
        ),
      ]);
    }
  })();
  initializationByDatabase.set(database, initialization);
  try {
    await initialization;
  } catch (error) {
    initializationByDatabase.delete(database);
    throw error;
  }
}

export async function overlayAlarmRuntimeState(
  database: D1Database | undefined,
  alarms: readonly Alarm[],
): Promise<readonly Alarm[]> {
  if (!database) return alarms;
  await initialize(database);
  const result = await database.prepare("SELECT * FROM alarm_runtime_state").all<AlarmStateRow>();
  const states = new Map(result.results.map((row) => [row.alarm_id, row]));
  return alarms.map((alarm) => {
    const state = states.get(alarm.id);
    return state
      ? {
          ...alarm,
          status: state.status,
          assignee: state.assignee,
          acknowledgedAt: state.acknowledged_at,
        }
      : alarm;
  });
}

export async function mutateAlarmRuntimeState(
  database: D1Database | undefined,
  alarm: Alarm,
  request: AlarmMutationRequest,
  timestamp = new Date().toISOString(),
): Promise<{
  readonly alarm: Alarm;
  readonly audit: AlarmMutationAudit;
  readonly replayed: boolean;
}> {
  if (!database) throw new Error("PERSISTENCE_UNAVAILABLE");
  await initialize(database);
  const fingerprint = JSON.stringify(request);
  const prior = await database
    .prepare("SELECT request_fingerprint FROM alarm_mutation_audit WHERE idempotency_key = ?")
    .bind(request.idempotencyKey)
    .first<IdempotencyRow>();
  const currentRow = await database
    .prepare("SELECT * FROM alarm_runtime_state WHERE alarm_id = ?")
    .bind(alarm.id)
    .first<AlarmStateRow>();
  const current: Alarm = currentRow
    ? {
        ...alarm,
        status: currentRow.status,
        assignee: currentRow.assignee,
        acknowledgedAt: currentRow.acknowledged_at,
      }
    : alarm;
  if (prior) {
    if (prior.request_fingerprint !== fingerprint) throw new Error("IDEMPOTENCY_KEY_REUSED");
    const audit = await readAlarmAudit(database, request.idempotencyKey);
    return { alarm: current, audit, replayed: true };
  }
  if (current.status === "resolved") throw new Error("ALARM_IMMUTABLE");
  if (request.action === "acknowledge" && current.status !== "active") {
    throw new Error("ALARM_ALREADY_ACKNOWLEDGED");
  }
  const after = {
    status: request.action === "acknowledge" ? ("acknowledged" as const) : current.status,
    assignee: request.action === "assign" ? (request.assignee ?? null) : current.assignee,
  };
  const acknowledgedAt = request.action === "acknowledge" ? timestamp : current.acknowledgedAt;
  const revision = (currentRow?.revision ?? 0) + 1;
  const stateMutationToken = request.idempotencyKey;
  const audit: AlarmMutationAudit = {
    id: `ALARM-AUDIT-${alarm.id}-${revision}`,
    alarmId: alarm.id,
    action: request.action,
    actor,
    before: { status: current.status, assignee: current.assignee },
    after,
    correlationId: request.correlationId,
    idempotencyKey: request.idempotencyKey,
    timestamp,
  };
  const results = await database.batch([
    database
      .prepare(
        `INSERT INTO alarm_runtime_state (alarm_id, status, assignee, acknowledged_at, revision, mutation_token, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(alarm_id) DO UPDATE SET status = excluded.status, assignee = excluded.assignee,
           acknowledged_at = excluded.acknowledged_at, revision = excluded.revision,
           mutation_token = excluded.mutation_token, updated_at = excluded.updated_at
         WHERE alarm_runtime_state.revision = ?`,
      )
      .bind(
        alarm.id,
        after.status,
        after.assignee,
        acknowledgedAt,
        revision,
        stateMutationToken,
        timestamp,
        currentRow?.revision ?? 0,
      ),
    database
      .prepare(
        `INSERT INTO alarm_mutation_audit (id, alarm_id, action, actor_id, actor_name, actor_role,
          before_state, after_state, correlation_id, idempotency_key, timestamp, request_fingerprint)
         SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
         WHERE EXISTS (
           SELECT 1 FROM alarm_runtime_state
           WHERE alarm_id = ? AND revision = ? AND mutation_token = ?
         )`,
      )
      .bind(
        audit.id,
        alarm.id,
        request.action,
        actor.id,
        actor.name,
        actor.role,
        JSON.stringify(audit.before),
        JSON.stringify(audit.after),
        request.correlationId,
        request.idempotencyKey,
        timestamp,
        fingerprint,
        alarm.id,
        revision,
        stateMutationToken,
      ),
  ]);
  if (Number(results[0]?.meta.changes ?? 0) !== 1 || Number(results[1]?.meta.changes ?? 0) !== 1) {
    throw new Error("ALARM_REVISION_CONFLICT");
  }
  return {
    alarm: { ...current, ...after, acknowledgedAt },
    audit,
    replayed: false,
  };
}

async function readAlarmAudit(
  database: D1Database,
  idempotencyKey: string,
): Promise<AlarmMutationAudit> {
  const row = await database
    .prepare("SELECT * FROM alarm_mutation_audit WHERE idempotency_key = ?")
    .bind(idempotencyKey)
    .first<Record<string, unknown>>();
  if (!row) throw new Error("ALARM_AUDIT_NOT_FOUND");
  return {
    id: String(row.id),
    alarmId: String(row.alarm_id),
    action: String(row.action) as AlarmMutationAction,
    actor: { id: String(row.actor_id), name: String(row.actor_name), role: String(row.actor_role) },
    before: JSON.parse(String(row.before_state)) as AlarmMutationAudit["before"],
    after: JSON.parse(String(row.after_state)) as AlarmMutationAudit["after"],
    correlationId: String(row.correlation_id),
    idempotencyKey: String(row.idempotency_key),
    timestamp: String(row.timestamp),
  };
}
