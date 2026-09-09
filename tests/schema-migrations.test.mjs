import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

const drizzleDirectory = new URL("../drizzle/", import.meta.url);

test("all five Drizzle migrations apply in order to the documented 33-table schema", async () => {
  const migrationFiles = (await readdir(drizzleDirectory))
    .filter((file) => /^000[0-4]_.+\.sql$/.test(file))
    .sort();

  assert.deepEqual(migrationFiles, [
    "0000_windops_domain.sql",
    "0001_resource_inventory.sql",
    "0002_server_workflow.sql",
    "0003_agent_execution_indexes.sql",
    "0004_knowledge_passages.sql",
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
    assert.equal(tables.length, 33);
    assert.ok(tables.some(({ name }) => name === "knowledge_passages"));
    assert.deepEqual(database.prepare("PRAGMA foreign_key_check").all(), []);
  } finally {
    database.close();
  }
});

test("the Drizzle journal and latest snapshot describe the same five-step chain", async () => {
  const journal = JSON.parse(
    await readFile(new URL("meta/_journal.json", drizzleDirectory), "utf8"),
  );
  const snapshot = JSON.parse(
    await readFile(new URL("meta/0004_snapshot.json", drizzleDirectory), "utf8"),
  );

  assert.deepEqual(
    journal.entries.map(({ idx, tag }) => ({ idx, tag })),
    [
      { idx: 0, tag: "0000_windops_domain" },
      { idx: 1, tag: "0001_resource_inventory" },
      { idx: 2, tag: "0002_server_workflow" },
      { idx: 3, tag: "0003_agent_execution_indexes" },
      { idx: 4, tag: "0004_knowledge_passages" },
    ],
  );
  assert.equal(Object.keys(snapshot.tables).length, 33);
  assert.ok(snapshot.tables.knowledge_passages);
});
