import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const approvedPolicy = `allowBuilds:
  esbuild: true
  sharp: true
  workerd: true
`;

test("dependency lifecycle scripts use an exact fail-closed allowlist", async () => {
  const policyUrl = new URL("../pnpm-workspace.yaml", import.meta.url);
  const policy = (await readFile(policyUrl, "utf8")).replaceAll("\r\n", "\n");

  assert.equal(policy, approvedPolicy);
  assert.doesNotMatch(policy, /dangerouslyAllowAllBuilds:\s*true/);
});
