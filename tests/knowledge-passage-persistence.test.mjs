import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("knowledge-passage-test", `${process.pid}-${Date.now()}`);
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
      return { success: true, results: statement.all(...this.bindings), meta: { changes: 0 } };
    }
    const result = statement.run(...this.bindings);
    return {
      success: true,
      results: [],
      meta: { changes: Number(result.changes), last_row_id: Number(result.lastInsertRowid) },
    };
  }
}

class SQLiteD1Database {
  constructor() {
    this.database = new DatabaseSync(":memory:");
    this.database.exec("PRAGMA foreign_keys=ON");
    this.batchTail = Promise.resolve();
  }

  prepare(sql) {
    return new SQLiteD1Statement(this.database, sql);
  }

  batch(statements) {
    const operation = this.batchTail.then(async () => {
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
    });
    this.batchTail = operation.catch(() => undefined);
    return operation;
  }

  close() {
    this.database.close();
  }
}

const assets = { fetch: async () => new Response("Not found", { status: 404 }) };
const context = { waitUntil() {}, passThroughOnException() {} };

async function fetchApi(database, path, method = "GET", body) {
  const response = await worker.fetch(
    new Request(`http://localhost${path}`, {
      method,
      headers: {
        accept: "application/json",
        ...(body === undefined ? {} : { "content-type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
    { ASSETS: assets, DB: database },
    context,
  );
  return { response, body: await response.json() };
}

const ask = (database, body) => fetchApi(database, "/api/knowledge-assistant", "POST", body);

function createKnowledgeTables(database) {
  database.exec(`
    CREATE TABLE knowledge_documents (
      id TEXT PRIMARY KEY NOT NULL,
      title TEXT NOT NULL,
      type TEXT NOT NULL,
      equipment TEXT NOT NULL,
      version TEXT NOT NULL,
      vectorized INTEGER NOT NULL,
      source_uri TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE knowledge_passages (
      id TEXT PRIMARY KEY NOT NULL,
      document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
      page INTEGER NOT NULL CHECK (page > 0),
      section TEXT NOT NULL,
      body TEXT NOT NULL,
      content_hash TEXT NOT NULL,
      token_count INTEGER NOT NULL CHECK (token_count >= 0),
      turbine_id TEXT,
      mission_id TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
  `);
}

function insertDocument(database, id, title) {
  database
    .prepare(
      `INSERT INTO knowledge_documents (
        id, title, type, equipment, version, vectorized, source_uri,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(
      id,
      title,
      "maintenance-procedure",
      "external equipment",
      "external-version",
      0,
      "/external-source",
      "2024-01-01T00:00:00Z",
      "2024-01-01T00:00:00Z",
    );
}

function insertPassage(database, passage) {
  database
    .prepare(
      `INSERT INTO knowledge_passages (
        id, document_id, page, section, body, content_hash, token_count,
        turbine_id, mission_id, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(
      passage.id,
      passage.documentId,
      passage.page ?? 1,
      passage.section ?? "external section",
      passage.body,
      passage.contentHash,
      passage.tokenCount ?? 1,
      passage.turbineId ?? null,
      passage.missionId ?? null,
      passage.createdAt ?? "2024-01-01T00:00:00Z",
      passage.updatedAt ?? "2024-01-01T00:00:00Z",
    );
}

const workflowActorIds = {
  approve: "demo-duty-chief",
  "start-work-order": "demo-maintenance-team",
  "set-task-completion": "demo-maintenance-team",
  "complete-work-order": "demo-verification-engineer",
  reset: "demo-operator",
};

async function mutateWorkflow(database, snapshot, action, idempotencyKey, extra = {}) {
  const result = await fetchApi(database, "/api/workflow/WT-023", "POST", {
    action,
    actor: { id: workflowActorIds[action], name: "Ignored caller label" },
    expectedRevision: snapshot.revision,
    idempotencyKey,
    correlationId: `CORR-${idempotencyKey}`,
    ...extra,
  });
  assert.equal(result.response.status, 200, JSON.stringify(result.body));
  return result.body.data;
}

test("empty D1 is deterministically seeded and citations are persisted passage bodies", async (t) => {
  const DB = new SQLiteD1Database();
  t.after(() => DB.close());
  const input = {
    question: "WT-023 主轴承退化的振动、温升和 BPFO 证据是什么？",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
  };
  const first = await ask(DB, input);
  const repeated = await ask(DB, input);
  assert.equal(first.response.status, 200, JSON.stringify(first.body));
  assert.deepEqual(repeated.body, first.body);
  assert.equal(first.body.meta.persistence, "d1");
  assert.equal(first.body.meta.persisted, true);
  assert.equal(first.body.meta.retrievalMode, "deterministic-d1-passage-retrieval");
  assert.equal(first.body.meta.realEmbedding, false);
  assert.equal(
    DB.database.prepare("SELECT COUNT(*) AS count FROM knowledge_documents").get().count,
    10,
  );
  assert.equal(
    DB.database.prepare("SELECT COUNT(*) AS count FROM knowledge_passages").get().count,
    12,
  );

  for (const citation of first.body.data.answer.citations) {
    const persisted = DB.database
      .prepare("SELECT body FROM knowledge_passages WHERE id = ?")
      .get(citation.passageId);
    assert.ok(persisted);
    assert.ok(persisted.body.includes(citation.quote.replace(/^…|…$/g, "")));
    assert.equal(citation.summary, citation.quote);
  }
  const scores = first.body.data.answer.citations.map((citation) => citation.score);
  assert.deepEqual(
    scores,
    [...scores].sort((left, right) => right - left),
  );
  assert.doesNotMatch(JSON.stringify(first.body), /chain.?of.?thought|hidden.?reasoning|\bcot\b/i);

  const indexes = DB.database
    .prepare(
      "SELECT name FROM sqlite_schema WHERE type='index' AND name LIKE 'knowledge_passages_%' ORDER BY name",
    )
    .all()
    .map((row) => row.name);
  assert.deepEqual(indexes, [
    "knowledge_passages_document_hash_uidx",
    "knowledge_passages_document_page_idx",
    "knowledge_passages_scope_idx",
  ]);
  assert.deepEqual(DB.database.prepare("PRAGMA foreign_key_check").all(), []);
});

test("D1 passage scope excludes another turbine and preserves general passages", async (t) => {
  const DB = new SQLiteD1Database();
  t.after(() => DB.close());
  const response = await ask(DB, {
    question: "齿轮箱磨粒和齿面点蚀",
    turbineId: "WT-041",
    missionId: "MISSION-2026-0824",
  });
  assert.equal(response.response.status, 200, JSON.stringify(response.body));
  assert.ok(response.body.data.answer.citations.length > 0);
  assert.equal(response.body.data.answer.citations[0].docId, "KB-GEARBOX-CASE-022");
  assert.ok(
    response.body.data.answer.citations.every(
      (citation) => citation.docId !== "KB-SCADA-REPORT-023",
    ),
  );
  const scopedCount = DB.database
    .prepare(
      `SELECT COUNT(*) AS count FROM knowledge_passages
       WHERE (turbine_id IS NULL OR turbine_id = ?)
         AND (mission_id IS NULL OR mission_id = ?)`,
    )
    .get("WT-041", "MISSION-2026-0824").count;
  assert.equal(response.body.data.answer.retrieval.candidateCount, scopedCount);
});

test("reset removes the persisted workflow passage without touching static seeds", async (t) => {
  const DB = new SQLiteD1Database();
  t.after(() => DB.close());

  const workflow = await fetchApi(DB, "/api/workflow/WT-023");
  assert.equal(workflow.response.status, 200, JSON.stringify(workflow.body));
  let snapshot = workflow.body.data;
  snapshot = await mutateWorkflow(DB, snapshot, "approve", "passage-reset-approve", {
    reason: "Evidence and execution constraints verified",
    comment: "Approve the guarded maintenance path",
  });
  snapshot = await mutateWorkflow(DB, snapshot, "start-work-order", "passage-reset-start");
  for (const [index, task] of snapshot.workOrder.tasks.entries()) {
    snapshot = await mutateWorkflow(
      DB,
      snapshot,
      "set-task-completion",
      `passage-reset-task-${index + 1}`,
      { taskId: task.id, completed: true },
    );
  }
  snapshot = await mutateWorkflow(DB, snapshot, "complete-work-order", "passage-reset-complete");
  assert.equal(snapshot.knowledgeCaseId, "KB-CASE-2026-WT023-CLOSED");

  const input = {
    question: "WT-023 closed-loop verification and health feedback evidence",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
  };
  const closedAnswer = await ask(DB, input);
  assert.equal(closedAnswer.response.status, 200, JSON.stringify(closedAnswer.body));
  assert.ok(
    DB.database
      .prepare("SELECT 1 FROM knowledge_passages WHERE id = ?")
      .get("KBP-KB-CASE-2026-WT023-CLOSED-006"),
  );

  snapshot = await mutateWorkflow(DB, snapshot, "reset", "passage-reset-action");
  assert.equal(snapshot.knowledgeCaseId, null);
  const [resetAnswer, repeatedResetAnswer] = await Promise.all([ask(DB, input), ask(DB, input)]);
  assert.equal(resetAnswer.response.status, 200, JSON.stringify(resetAnswer.body));
  assert.equal(repeatedResetAnswer.response.status, 200, JSON.stringify(repeatedResetAnswer.body));
  assert.equal(resetAnswer.body.meta.knowledgeCaseId, null);
  assert.equal(repeatedResetAnswer.body.meta.knowledgeCaseId, null);
  assert.ok(
    resetAnswer.body.data.answer.citations.every(
      ({ docId }) => docId !== "KB-CASE-2026-WT023-CLOSED",
    ),
  );
  assert.equal(
    DB.database
      .prepare("SELECT 1 FROM knowledge_passages WHERE id = ?")
      .get("KBP-KB-CASE-2026-WT023-CLOSED-006"),
    undefined,
  );
  assert.ok(
    DB.database.prepare("SELECT 1 FROM knowledge_passages WHERE id = ?").get("KBP-MB-PROC-004-009"),
  );
  assert.equal(
    DB.database.prepare("SELECT COUNT(*) AS count FROM knowledge_passages").get().count,
    12,
  );
  assert.deepEqual(DB.database.prepare("PRAGMA foreign_key_check").all(), []);
});

test("fixture sync refreshes managed rows, removes retired IDs, and preserves external overlays", async (t) => {
  const DB = new SQLiteD1Database();
  t.after(() => DB.close());
  createKnowledgeTables(DB.database);

  insertDocument(DB.database, "KB-MB-PROC-004", "externally managed document title");
  insertDocument(DB.database, "KB-CLOSED-USER-001", "dynamic workflow overlay");
  DB.database
    .prepare("UPDATE knowledge_documents SET version = ?, type = ? WHERE id = ?")
    .run("Server closed-loop v1", "failure-case", "KB-CLOSED-USER-001");
  insertPassage(DB.database, {
    id: "KBP-MB-PROC-004-009",
    documentId: "KB-MB-PROC-004",
    body: "stale fixture body",
    contentHash: "stale-current-hash",
    turbineId: "WT-999",
    missionId: "MISSION-STALE",
  });
  insertPassage(DB.database, {
    id: "KBP-MB-PROC-004-008",
    documentId: "KB-MB-PROC-004",
    body: "retired fixture body",
    contentHash: "retired-fixture-hash",
  });
  insertPassage(DB.database, {
    id: "KBP-KB-CLOSED-USER-001-006",
    documentId: "KB-CLOSED-USER-001",
    body: "dynamic workflow passage must survive fixture synchronization",
    contentHash: "dynamic-overlay-hash",
    turbineId: "WT-041",
    missionId: "MISSION-2026-0824",
  });

  const input = {
    question: "main bearing inspection procedure",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
  };
  const [result, concurrentResult] = await Promise.all([ask(DB, input), ask(DB, input)]);
  assert.equal(result.response.status, 200, JSON.stringify(result.body));
  assert.equal(concurrentResult.response.status, 200, JSON.stringify(concurrentResult.body));
  assert.deepEqual(concurrentResult.body, result.body);

  const refreshed = DB.database
    .prepare(
      `SELECT body, content_hash, token_count, turbine_id, mission_id
       FROM knowledge_passages WHERE id = ?`,
    )
    .get("KBP-MB-PROC-004-009");
  assert.ok(refreshed);
  assert.notEqual(refreshed.body, "stale fixture body");
  assert.notEqual(refreshed.content_hash, "stale-current-hash");
  assert.ok(refreshed.token_count > 1);
  assert.equal(refreshed.turbine_id, null);
  assert.equal(refreshed.mission_id, null);
  assert.equal(
    DB.database
      .prepare("SELECT COUNT(*) AS count FROM knowledge_passages WHERE id = ?")
      .get("KBP-MB-PROC-004-008").count,
    0,
  );

  const overlay = DB.database
    .prepare(
      `SELECT document_id, body, content_hash, turbine_id, mission_id
       FROM knowledge_passages WHERE id = ?`,
    )
    .get("KBP-KB-CLOSED-USER-001-006");
  assert.deepEqual(
    { ...overlay },
    {
      document_id: "KB-CLOSED-USER-001",
      body: "dynamic workflow passage must survive fixture synchronization",
      content_hash: "dynamic-overlay-hash",
      turbine_id: "WT-041",
      mission_id: "MISSION-2026-0824",
    },
  );
  assert.equal(
    DB.database.prepare("SELECT title FROM knowledge_documents WHERE id = ?").get("KB-MB-PROC-004")
      .title,
    "海上风机主轴承状态检查与取证规程",
  );
  assert.equal(
    DB.database
      .prepare("SELECT title FROM knowledge_documents WHERE id = ?")
      .get("KB-CLOSED-USER-001").title,
    "dynamic workflow overlay",
  );
  assert.deepEqual(DB.database.prepare("PRAGMA foreign_key_check").all(), []);
});
