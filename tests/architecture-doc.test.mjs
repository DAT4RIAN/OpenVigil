import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile, rm } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { architectureFacts, checkArchitecture } from "../scripts/check-architecture-doc.mjs";

async function fixture(t) {
  await mkdir(".artifacts", { recursive: true });
  const root = await mkdtemp(path.resolve(".artifacts/architecture-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, "app/styles"), { recursive: true });
  await mkdir(path.join(root, "backend/alembic/versions"), { recursive: true });
  await writeFile(path.join(root, "app/globals.css"), '@import "./styles/01.css";');
  await writeFile(path.join(root, "app/styles/01.css"), "body {}");
  await writeFile(
    path.join(root, "backend/alembic/versions/a.py"),
    'revision: str = "a"\ndown_revision: str | None = None\n',
  );
  await writeFile(
    path.join(root, "ARCHITECTURE.md"),
    `# Architecture\n${await architectureFacts(root)}\nKept prose.\n`,
  );
  return root;
}

test("source changes fail read-only checking and explicit regeneration preserves prose", async (t) => {
  const root = await fixture(t);
  await checkArchitecture(root);
  await writeFile(
    path.join(root, "backend/alembic/versions/b.py"),
    'revision = "b"\ndown_revision = "a"\n',
  );
  const before = await readFile(path.join(root, "ARCHITECTURE.md"), "utf8");
  await assert.rejects(checkArchitecture(root), /drifted/);
  assert.equal(await readFile(path.join(root, "ARCHITECTURE.md"), "utf8"), before);
  await checkArchitecture(root, true);
  await checkArchitecture(root);
  assert.match(await readFile(path.join(root, "ARCHITECTURE.md"), "utf8"), /Kept prose/);
});

test("missing CSS, invalid migration ancestry, forks and disconnected cycles fail closed", async (t) => {
  const root = await fixture(t);
  const cssFile = path.join(root, "app/globals.css");
  await writeFile(cssFile, '@import "./styles/missing.css";');
  await assert.rejects(architectureFacts(root), /ENOENT/);
  await writeFile(cssFile, '@import "./styles/01.css";');
  const second = path.join(root, "backend/alembic/versions/b.py");
  await writeFile(second, 'revision = "b"\ndown_revision = "missing"\n');
  await assert.rejects(architectureFacts(root), /Missing migration parent/);
  await writeFile(second, 'revision = "b"\ndown_revision = None\n');
  await assert.rejects(architectureFacts(root), /one migration head/);
  await writeFile(second, 'revision = "b"\ndown_revision = "b"\n');
  await assert.rejects(architectureFacts(root), /Disconnected/);
});

test("missing or duplicated documentation markers cannot be silently repaired", async (t) => {
  const root = await fixture(t);
  const file = path.join(root, "ARCHITECTURE.md");
  await writeFile(file, "Do not overwrite this document.");
  await assert.rejects(checkArchitecture(root, true), /marker/);
  assert.equal(await readFile(file, "utf8"), "Do not overwrite this document.");
});
