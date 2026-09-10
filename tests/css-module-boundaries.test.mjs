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
];

test("the global stylesheet is an ordered import entry with an unchanged rule stream", async () => {
  const entry = await readFile(new URL("app/globals.css", root), "utf8");
  const imports = [...entry.matchAll(/@import "\.\/styles\/([^"]+)";/g)].map((match) => match[1]);
  assert.deepEqual(imports, styleFiles);
  assert.doesNotMatch(entry, /(^|\n)\s*[^@\s][^{]*\{/);

  const modules = await Promise.all(
    styleFiles.map((file) => readFile(new URL(`app/styles/${file}`, root), "utf8")),
  );
  const ruleStream = modules.join("").replaceAll(/\s+/g, "");
  assert.equal(
    createHash("sha256").update(ruleStream).digest("hex"),
    "1c9f749afefdcd42362501687849100270b73b71da5b82aa51f6617478c7b81e",
  );
});
