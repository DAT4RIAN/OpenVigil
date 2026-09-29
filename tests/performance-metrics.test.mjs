import assert from "node:assert/strict";
import test from "node:test";
import { dataCounts, percentile, summarizeSamples } from "../scripts/performance-metrics.mjs";

test("nearest-rank P95 includes the tail and does not mutate measurements", () => {
  const values = [100, ...Array.from({ length: 19 }, (_, index) => index)];
  assert.equal(percentile(values, 0.95), 18);
  assert.equal(percentile(values, 1), 100);
  assert.equal(values[0], 100);
  for (const values of [[], [NaN], [Infinity], [-1]]) {
    assert.throws(() => percentile(values, 0.95));
  }
});

test("failed, missing, or dropped samples never satisfy a latency gate", () => {
  assert.throws(() => summarizeSamples([], "ms", 100, 0));
  const valid = Array.from({ length: 5 }, () => ({ ms: 10, error: null }));
  assert.equal(summarizeSamples(valid, "ms", 20, 5).passed, true);
  for (const samples of [
    valid.slice(0, 4),
    [...valid, valid[0]],
    [...valid.slice(1), { ms: 1, error: "HTTP_500" }],
    [...valid.slice(1), { ms: null, error: null }],
    [...valid.slice(1), { ms: Infinity, error: null }],
    [...valid.slice(1), { ms: 21, error: null }],
  ])
    assert.equal(summarizeSamples(samples, "ms", 20, 5).passed, false);
});

test("API shape counting distinguishes empty data from errors without exposing records", () => {
  assert.deepEqual(dataCounts({ turbines: [], wind_farms: [] }, ["turbines", "wind_farms"]), {
    turbines: 0,
    wind_farms: 0,
  });
  assert.throws(() => dataCounts({ agents: [] }, ["agents", "skills", "tools"]));
  assert.deepEqual(dataCounts({ data: [{ secret: "never emitted" }] }), { rows: 1 });
  assert.deepEqual(dataCounts({ data: { agents: [1, 2], tools: [1], name: "redacted" } }), {
    agents: 2,
    tools: 1,
  });
  assert.deepEqual(dataCounts({ data: [] }), { rows: 0 });
  for (const payload of [{}, { data: null }, { data: [], error: { code: "DENIED" } }]) {
    assert.throws(() => dataCounts(payload));
  }
});
