import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("agent-tool-persistence-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

class SQLiteD1Statement {
  constructor(database, sql, bindings = []) {
    this.database = database;
    this.sql = sql;
    this.bindings = bindings;
  }

  bind(...bindings) {
    return new SQLiteD1Statement(this.database, this.sql, bindings);
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

  async run() {
    const statement = this.database.prepare(this.sql);
    if (/^\s*(?:SELECT|PRAGMA|WITH)\b/i.test(this.sql)) {
      return {
        success: true,
        results: statement.all(...this.bindings),
        meta: { changes: 0 },
      };
    }
    const result = statement.run(...this.bindings);
    return {
      success: true,
      results: [],
      meta: {
        changes: Number(result.changes),
        last_row_id: Number(result.lastInsertRowid),
      },
    };
  }
}

class SQLiteD1Database {
  constructor() {
    this.database = new DatabaseSync(":memory:");
    this.database.exec("PRAGMA foreign_keys=ON");
  }

  prepare(sql) {
    return new SQLiteD1Statement(this.database, sql);
  }

  async batch(statements) {
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const results = [];
      for (const statement of statements) results.push(await statement.run());
      this.database.exec("COMMIT");
      return results;
    } catch (error) {
      this.database.exec("ROLLBACK");
      throw error;
    }
  }

  close() {
    this.database.close();
  }
}

const assets = { fetch: async () => new Response("Not found", { status: 404 }) };
const context = { waitUntil() {}, passThroughOnException() {} };

async function fetchJson(environment, method = "GET", body, query = "") {
  const response = await worker.fetch(
    new Request(`http://localhost/api/agent-tools${query}`, {
      method,
      headers: {
        accept: "application/json",
        ...(body === undefined ? {} : { "content-type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
    environment,
    context,
  );
  return { response, body: await response.json() };
}

const successBody = {
  tool: "get_turbine_status",
  args: { turbineId: "WT-023" },
  agentId: "agent-scada-analysis",
  missionId: "MISSION-2026-0823",
};

test("Agent Tool POST requires D1 by default before executing", async () => {
  const { response, body } = await fetchJson({ ASSETS: assets }, "POST", {
    ...successBody,
    idempotencyKey: "agent-test-d1-required",
  });
  assert.equal(response.status, 503);
  assert.equal(body.error.code, "AUDIT_PERSISTENCE_UNAVAILABLE");
  assert.equal(body.data, null);
  assert.equal(body.meta.persistence, "unavailable");
  assert.equal(body.meta.writable, false);
});

test("D1 Agent Tool API is empty-database safe, linked, filterable, and idempotent", async (t) => {
  const DB = new SQLiteD1Database();
  t.after(() => DB.close());
  const environment = { ASSETS: assets, DB };
  const idempotencyKey = "agent-test-persist-001";

  const created = await fetchJson(environment, "POST", { ...successBody, idempotencyKey });
  assert.equal(created.response.status, 200);
  assert.equal(created.body.ok, true);
  assert.equal(created.body.meta.persistence, "d1");
  assert.equal(created.body.meta.persisted, true);
  assert.equal(created.body.meta.replayed, false);
  const execution = created.body.data.execution;
  assert.equal(execution.status, "succeeded");
  assert.equal(execution.agentId, successBody.agentId);
  assert.equal(execution.missionId, successBody.missionId);
  assert.equal(execution.idempotencyKey, idempotencyKey);
  assert.match(execution.executionId, /^AGEXEC-[0-9A-F]{64}$/);
  assert.equal(execution.correlationId, `WOPS-GET_TURBINE_STATUS-${execution.executionId}`);
  assert.match(execution.requestFingerprint, /^[0-9a-f]{64}$/);
  assert.equal(
    execution.tokenEstimate.total,
    execution.tokenEstimate.input + execution.tokenEstimate.output,
  );

  const replay = await fetchJson(environment, "POST", { ...successBody, idempotencyKey });
  assert.equal(replay.response.status, 200);
  assert.equal(replay.body.meta.replayed, true);
  assert.deepEqual(replay.body.data.execution, execution);
  assert.equal(
    DB.database.prepare("SELECT COUNT(*) AS count FROM agent_executions").get().count,
    1,
  );

  const conflict = await fetchJson(environment, "POST", {
    tool: "query_scada",
    args: { turbineId: "WT-023", metric: "main-bearing-temperature", limit: 8 },
    agentId: successBody.agentId,
    missionId: successBody.missionId,
    idempotencyKey,
  });
  assert.equal(conflict.response.status, 409);
  assert.equal(conflict.body.error.code, "IDEMPOTENCY_KEY_REUSED");

  const failed = await fetchJson(environment, "POST", {
    tool: "update_work_order",
    args: {
      workOrderId: "WO-20260823-017",
      plannedStart: "2026-08-14T18:00:00+08:00",
      deadline: "2026-08-14T17:00:00+08:00",
      dryRun: true,
    },
    agentId: "agent-crew-scheduling",
    missionId: successBody.missionId,
    idempotencyKey: "agent-test-persist-failed-001",
  });
  assert.equal(failed.response.status, 422);
  assert.equal(failed.body.error.code, "INVALID_WORK_ORDER_SCHEDULE");
  assert.equal(failed.body.meta.persistence, "d1");
  assert.equal(failed.body.data.execution.status, "failed");
  assert.equal(failed.body.data.execution.result.ok, false);

  const filtered = await fetchJson(
    environment,
    "GET",
    undefined,
    `?agentId=agent-crew-scheduling&missionId=${successBody.missionId}&status=failed&toolName=update_work_order&limit=10`,
  );
  assert.equal(filtered.response.status, 200);
  assert.equal(filtered.body.meta.persistence, "d1");
  assert.equal(filtered.body.meta.totalHistoryCount, 1);
  assert.equal(filtered.body.data.executionHistory.length, 1);
  assert.equal(
    filtered.body.data.executionHistory[0].executionId,
    failed.body.data.execution.executionId,
  );
  assert.doesNotMatch(
    JSON.stringify([execution, failed.body.data.execution, filtered.body]),
    /chain.?of.?thought|hidden.?reasoning|\bcot\b/i,
  );

  const indexNames = DB.database
    .prepare(
      "SELECT name FROM sqlite_schema WHERE type='index' AND name LIKE 'agent_executions_%' ORDER BY name",
    )
    .all()
    .map((row) => row.name);
  assert.ok(indexNames.includes("agent_executions_agent_time_idx"));
  assert.ok(indexNames.includes("agent_executions_status_time_idx"));
  assert.ok(indexNames.includes("agent_executions_tool_time_idx"));
  assert.ok(indexNames.includes("agent_executions_correlation_uidx"));
  assert.deepEqual(DB.database.prepare("PRAGMA foreign_key_check").all(), []);
});

test("explicit persist=false keeps a clearly non-durable idempotent runtime ledger", async () => {
  const environment = { ASSETS: assets };
  const requestBody = {
    ...successBody,
    missionId: undefined,
    idempotencyKey: "agent-test-runtime-001",
    persist: false,
  };
  const created = await fetchJson(environment, "POST", requestBody);
  const replay = await fetchJson(environment, "POST", requestBody);
  assert.equal(created.response.status, 200);
  assert.equal(created.body.meta.persistence, "runtime-memory");
  assert.equal(created.body.meta.persisted, false);
  assert.equal(created.body.meta.replayed, false);
  assert.equal(replay.body.meta.replayed, true);
  assert.deepEqual(replay.body.data.execution, created.body.data.execution);

  const rows = await fetchJson(
    environment,
    "GET",
    undefined,
    "?agentId=agent-scada-analysis&toolName=get_turbine_status&limit=100",
  );
  assert.equal(rows.body.meta.persistence, "runtime-memory");
  assert.ok(
    rows.body.data.executionHistory.some(
      (execution) => execution.idempotencyKey === requestBody.idempotencyKey,
    ),
  );
});
