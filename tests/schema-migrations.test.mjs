import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

const drizzleDirectory = new URL("../drizzle/", import.meta.url);

test("all seven Drizzle migrations apply in order to the documented 35-table schema", async () => {
  const migrationFiles = (await readdir(drizzleDirectory))
    .filter((file) => /^000[0-6]_.+\.sql$/.test(file))
    .sort();

  assert.deepEqual(migrationFiles, [
    "0000_windops_domain.sql",
    "0001_resource_inventory.sql",
    "0002_server_workflow.sql",
    "0003_agent_execution_indexes.sql",
    "0004_knowledge_passages.sql",
    "0005_workflow_field_evidence.sql",
    "0006_alarm_mutation_token.sql",
  ]);

  const database = new DatabaseSync(":memory:");
  try {
    database.exec("PRAGMA foreign_keys = ON");
    for (const file of migrationFiles) {
      const sql = await readFile(new URL(file, drizzleDirectory), "utf8");
      database.exec(sql.replaceAll("--> statement-breakpoint", ""));
    }

    const tables = database
      .prepare(
        "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
      )
      .all();
    assert.equal(tables.length, 35);
    assert.ok(tables.some(({ name }) => name === "knowledge_passages"));
    assert.ok(tables.some(({ name }) => name === "alarm_runtime_state"));
    assert.ok(tables.some(({ name }) => name === "alarm_mutation_audit"));
    assert.ok(
      database
        .prepare("PRAGMA table_info(alarm_runtime_state)")
        .all()
        .some(({ name }) => name === "mutation_token"),
    );
    assert.ok(
      database
        .prepare("PRAGMA table_info(workflow_tasks)")
        .all()
        .some(({ name }) => name === "field_evidence"),
    );
    assert.deepEqual(database.prepare("PRAGMA foreign_key_check").all(), []);
  } finally {
    database.close();
  }
});

test("the Drizzle journal and latest snapshot describe the same seven-step chain", async () => {
  const journal = JSON.parse(
    await readFile(new URL("meta/_journal.json", drizzleDirectory), "utf8"),
  );
  const snapshot = JSON.parse(
    await readFile(new URL("meta/0006_snapshot.json", drizzleDirectory), "utf8"),
  );

  assert.deepEqual(
    journal.entries.map(({ idx, tag }) => ({ idx, tag })),
    [
      { idx: 0, tag: "0000_windops_domain" },
      { idx: 1, tag: "0001_resource_inventory" },
      { idx: 2, tag: "0002_server_workflow" },
      { idx: 3, tag: "0003_agent_execution_indexes" },
      { idx: 4, tag: "0004_knowledge_passages" },
      { idx: 5, tag: "0005_workflow_field_evidence" },
      { idx: 6, tag: "0006_alarm_mutation_token" },
    ],
  );
  assert.equal(Object.keys(snapshot.tables).length, 35);
  assert.ok(snapshot.tables.knowledge_passages);
  assert.ok(snapshot.tables.alarm_runtime_state);
  assert.ok(snapshot.tables.alarm_mutation_audit);
});
