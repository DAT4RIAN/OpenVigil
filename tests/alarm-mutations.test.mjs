import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("alarm-mutation-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

class Statement {
  constructor(database, sql, bindings = []) {
    this.database = database;
    this.sql = sql;
    this.bindings = bindings;
  }
  bind(...bindings) {
    return new Statement(this.database, this.sql, bindings);
  }
  async first() {
    return this.database.prepare(this.sql).get(...this.bindings) ?? null;
  }
  async all() {
    return {
      success: true,
      results: this.database.prepare(this.sql).all(...this.bindings),
      meta: {},
    };
  }
  executeForBatch() {
    const statement = this.database.prepare(this.sql);
    if (/^\s*(?:SELECT|PRAGMA|WITH)\b/i.test(this.sql)) {
      return { success: true, results: statement.all(...this.bindings), meta: { changes: 0 } };
    }
    const result = statement.run(...this.bindings);
    return { success: true, results: [], meta: { changes: Number(result.changes) } };
  }
}

class Database {
  constructor() {
    this.database = new DatabaseSync(":memory:");
    this.database.exec("PRAGMA foreign_keys=ON");
    this.tail = Promise.resolve();
  }
  prepare(sql) {
    return new Statement(this.database, sql);
  }
  batch(statements) {
    const operation = this.tail.then(() => {
      this.database.exec("BEGIN IMMEDIATE");
      try {
        const result = statements.map((statement) => statement.executeForBatch());
        this.database.exec("COMMIT");
        return result;
      } catch (error) {
        this.database.exec("ROLLBACK");
        throw error;
      }
    });
    this.tail = operation.catch(() => undefined);
    return operation;
  }
  close() {
    this.database.close();
  }
}

const assets = { fetch: async () => new Response("Not found", { status: 404 }) };
const context = { waitUntil() {}, passThroughOnException() {} };
async function request(database, method, body, path = "/api/alarms") {
  const response = await worker.fetch(
    new Request(`http://localhost${path}`, {
      method,
      headers: {
        accept: "application/json",
        ...(body ? { "content-type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    }),
    { ASSETS: assets, ...(database ? { DB: database } : {}) },
    context,
  );
  return { response, body: await response.json() };
}

test("alarm acknowledgement and assignment require D1 and persist auditable state", async (t) => {
  const unavailable = await request(undefined, "POST", {
    alarmId: "ALARM-0001",
    action: "acknowledge",
    correlationId: "c",
    idempotencyKey: "i",
  });
  assert.equal(unavailable.response.status, 503);
  assert.equal(unavailable.body.error.code, "PERSISTENCE_UNAVAILABLE");

  const DB = new Database();
  t.after(() => DB.close());
  const initial = await request(DB, "GET");
  const alarm = initial.body.data.find(({ status }) => status === "active");
  assert.ok(alarm);
  const acknowledge = {
    alarmId: alarm.id,
    action: "acknowledge",
    correlationId: "alarm-ack-correlation",
    idempotencyKey: "alarm-ack-idempotency",
  };
  const committed = await request(DB, "POST", acknowledge);
  const replay = await request(DB, "POST", acknowledge);
  assert.equal(committed.response.status, 200, JSON.stringify(committed.body));
  assert.equal(committed.body.data.status, "acknowledged");
  assert.equal(committed.body.meta.persistence, "d1");
  assert.equal(committed.body.meta.audit.actor.id, "demo-alarm-operator");
  assert.equal(replay.body.meta.replayed, true);

  const assigned = await request(DB, "POST", {
    alarmId: alarm.id,
    action: "assign",
    assignee: "值班工程师",
    correlationId: "alarm-assign-correlation",
    idempotencyKey: "alarm-assign-idempotency",
  });
  assert.equal(assigned.response.status, 200, JSON.stringify(assigned.body));
  assert.equal(assigned.body.data.assignee, "值班工程师");
  const snapshot = await request(DB, "GET");
  const archive = await request(DB, "GET", undefined, "/api/alarms?scope=archive");
  assert.equal(snapshot.body.data.find(({ id }) => id === alarm.id).status, "acknowledged");
  assert.equal(snapshot.body.data.find(({ id }) => id === alarm.id).assignee, "值班工程师");
  assert.deepEqual(
    archive.body.data
      .filter(({ id }) => id === alarm.id)
      .map(({ status, assignee, acknowledgedAt }) => ({ status, assignee, acknowledgedAt })),
    snapshot.body.data
      .filter(({ id }) => id === alarm.id)
      .map(({ status, assignee, acknowledgedAt }) => ({ status, assignee, acknowledgedAt })),
    "live and archive rows with the same ID must share the D1 alarm mutation overlay",
  );
  assert.equal(
    DB.database.prepare("SELECT COUNT(*) AS count FROM alarm_mutation_audit").get().count,
    2,
  );

  const competing = await Promise.all([
    request(DB, "POST", {
      alarmId: alarm.id,
      action: "assign",
      assignee: "海维一组",
      correlationId: "alarm-race-one",
      idempotencyKey: "alarm-race-one",
    }),
    request(DB, "POST", {
      alarmId: alarm.id,
      action: "assign",
      assignee: "海维二组",
      correlationId: "alarm-race-two",
      idempotencyKey: "alarm-race-two",
    }),
  ]);
  assert.deepEqual(competing.map(({ response }) => response.status).sort(), [200, 409]);
  assert.equal(
    DB.database.prepare("SELECT COUNT(*) AS count FROM alarm_mutation_audit").get().count,
    3,
    "a losing CAS writer must not leave an orphan audit row",
  );
});

test("alarm runtime initialization upgrades an existing workflow schema without evidence columns", async (t) => {
  const DB = new Database();
  t.after(() => DB.close());
  DB.database.exec(`
    CREATE TABLE workflow_instances (mission_id TEXT PRIMARY KEY, turbine_id TEXT, mission_status TEXT,
      mission_progress_percent INTEGER, decision_id TEXT, decision_status TEXT, decision_risk TEXT,
      approval_required INTEGER, approval_record TEXT, work_order_id TEXT, work_order_status TEXT,
      turbine_health_score INTEGER, main_bearing_health_score INTEGER, knowledge_case_id TEXT,
      revision INTEGER, created_at TEXT, updated_at TEXT);
    CREATE TABLE workflow_tasks (id TEXT PRIMARY KEY, mission_id TEXT, sequence INTEGER, title TEXT,
      completed INTEGER, completed_at TEXT, completed_by TEXT, created_at TEXT, updated_at TEXT);
    CREATE TABLE workflow_audit_events (id TEXT PRIMARY KEY, mission_id TEXT, revision INTEGER,
      event_sequence INTEGER, action TEXT, kind TEXT, actor_id TEXT, actor_name TEXT, actor_role TEXT,
      correlation_id TEXT, idempotency_key TEXT, from_state TEXT, to_state TEXT, detail TEXT, timestamp TEXT);
    CREATE TABLE workflow_idempotency (idempotency_key TEXT PRIMARY KEY, mission_id TEXT,
      request_fingerprint TEXT, response_snapshot TEXT, correlation_id TEXT, created_at TEXT);
  `);
  const snapshot = await request(DB, "GET");
  assert.equal(snapshot.response.status, 200);
  assert.ok(
    DB.database
      .prepare("PRAGMA table_info(workflow_tasks)")
      .all()
      .some(({ name }) => name === "field_evidence"),
  );
  assert.ok(
    DB.database
      .prepare("PRAGMA table_info(workflow_audit_events)")
      .all()
      .some(({ name }) => name === "field_evidence"),
  );
});
