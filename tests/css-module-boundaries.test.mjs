import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const styleFiles = [
  "01-foundations.css",
  "02-shell-and-shared.css",
  "03-dashboard.css",
  "04-fleet.css",
  "05-asset-detail.css",
  "06-alarms.css",
  "07-agents.css",
  "08-missions.css",
  "09-decisions.css",
  "10-work-orders.css",
  "11-overlays-and-responsive.css",
  "12-health.css",
  "13-access-recovery.css",
  "14-motion.css",
];

test("the global stylesheet preserves import order and the reviewed rule stream", async () => {
  const entry = await readFile(new URL("app/globals.css", root), "utf8");
  const imports = [...entry.matchAll(/@import "\.\/styles\/([^"]+)";/g)].map((match) => match[1]);
  assert.deepEqual(imports, styleFiles);
  assert.doesNotMatch(entry, /(^|\n)\s*[^@\s][^{]*\{/);

  const modules = await Promise.all(
    styleFiles.map((file) => readFile(new URL(`app/styles/${file}`, root), "utf8")),
  );
  const ruleStream = modules.join("").replaceAll(/\s+/g, "");
  // Motion rules added after reviewing their real intermediate and terminal frames.
  // See docs/design/frontend-motion.md; existing screenshot baselines remain unchanged.
  assert.equal(
    createHash("sha256").update(ruleStream).digest("hex"),
    "16937714145e2281f07637c69852988233d3ca91f32ba97176a6ad885534ae26",
  );
});
