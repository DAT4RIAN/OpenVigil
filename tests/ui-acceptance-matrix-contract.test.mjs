import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import { test } from "node:test";
import {
  lifecycleAcceptanceMatrix,
  roleAcceptanceMatrix,
  routeAcceptanceMatrix,
  viewportAcceptanceMatrix,
} from "./e2e/ui-acceptance-matrix.ts";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("UI acceptance matrix pins every route, target viewport, role, and governed lifecycle", () => {
  assert.equal(routeAcceptanceMatrix.length, 22);
  assert.equal(new Set(routeAcceptanceMatrix.map(({ path }) => path)).size, 22);
  assert.deepEqual(
    viewportAcceptanceMatrix.map(({ width, height }) => `${width}x${height}`),
    ["1440x900", "1280x800", "900x900", "390x844"],
  );
  assert.deepEqual(
    roleAcceptanceMatrix.map(({ role }) => role),
    ["operations_manager", "operations_approver", "maintenance_reviewer", "field_technician"],
  );
  for (const lifecycle of [
    "initial-loading",
    "refreshing",
    "success-empty",
    "permission-error",
    "conflict",
    "service-error",
    "network-error",
    "stale",
    "disabled",
  ]) {
    assert.ok(lifecycleAcceptanceMatrix.decision.includes(lifecycle));
  }
  assert.deepEqual(lifecycleAcceptanceMatrix.governedCommand, [
    "running",
    "success",
    "failed",
    "result-unknown",
    "reconciled",
  ]);
});

test("stable dashboard baselines are checked in for release viewports", () => {
  for (const image of [
    "dashboard-desktop-1440.png",
    "dashboard-desktop-1280.png",
    "dashboard-mobile-390.png",
  ]) {
    assert.ok(
      statSync(new URL(`./e2e/__screenshots__/${image}`, import.meta.url)).size > 10_000,
      `${image} must be a material checked-in baseline`,
    );
  }
});

test("required browser jobs fail closed on skipped tests and preserve UI evidence", () => {
  const workflow = read("../.github/workflows/ci.yml");
  const config = read("../playwright.config.ts");
  const queryMatrix = read("./e2e/query-state-matrix.spec.ts");
  const roleMatrix = read("./e2e/identity-and-mobile.spec.ts");

  assert.match(workflow, /browser-e2e:[\s\S]*?WINDOPS_FAIL_ON_SKIPPED: "1"/);
  assert.match(workflow, /real-cross-layer-e2e:[\s\S]*?WINDOPS_FAIL_ON_SKIPPED: "1"/);
  assert.match(workflow, /tests\/e2e\/__screenshots__/);
  assert.match(config, /playwright-no-skips-reporter\.mjs/);
  assert.match(config, /WINDOPS_E2E_REAL_BACKEND === "1"/);
  assert.match(queryMatrix, /name: "decisions"/);
  assert.match(queryMatrix, /distinguishes loading, empty, failures, stale data, and recovery/);
  assert.match(
    roleMatrix,
    /decision approval controls fail closed by backend-issued role capability/,
  );
});
