import assert from "node:assert/strict";
import test from "node:test";

import {
  deriveQueryViewState,
  latestValidTimestamp,
  mergeRuntimeHealth,
  queryRuntimeHealth,
} from "../lib/query-state.ts";

const NOW = Date.parse("2026-09-04T08:00:00Z");

test("latest authoritative timestamp ignores invalid and missing values", () => {
  assert.equal(
    latestValidTimestamp(["invalid", null, "2026-09-04T07:58:00Z", "2026-09-04T07:59:00Z"]),
    Date.parse("2026-09-04T07:59:00Z"),
  );
  assert.equal(latestValidTimestamp([undefined, ""]), null);
});

function state(overrides = {}) {
  return deriveQueryViewState({
    data: undefined,
    dataUpdatedAt: 0,
    error: null,
    isError: false,
    isFetching: true,
    isPending: true,
    isStale: true,
    isEmpty: (data) => Array.isArray(data) && data.length === 0,
    now: NOW,
    staleAfterMs: 60_000,
    ...overrides,
  });
}

test("query lifecycle keeps loading, empty, and successful data distinct", () => {
  assert.equal(state().lifecycle, "initial-loading");
  assert.equal(
    state({
      data: [],
      dataUpdatedAt: NOW,
      isFetching: false,
      isPending: false,
      isStale: false,
    }).lifecycle,
    "success-empty",
  );
  assert.equal(
    state({
      data: [{ id: "MISSION-1" }],
      dataUpdatedAt: NOW,
      isFetching: false,
      isPending: false,
      isStale: false,
    }).lifecycle,
    "success-data",
  );
});

test("refresh keeps prior data while failed refresh is explicitly stale", () => {
  const refreshing = state({
    data: [{ id: "WO-1" }],
    dataUpdatedAt: NOW - 10_000,
    isPending: false,
    isStale: false,
  });
  assert.equal(refreshing.lifecycle, "refreshing");
  assert.equal(refreshing.health, "ready");
  assert.equal(refreshing.hasData, true);

  const failed = state({
    data: [{ id: "WO-1" }],
    dataUpdatedAt: NOW - 70_000,
    error: {
      status: 503,
      code: "BACKEND_UNAVAILABLE",
      correlationId: "read-stale-001",
      message: "unavailable",
    },
    isError: true,
    isFetching: false,
    isPending: false,
  });
  assert.equal(failed.lifecycle, "error-stale");
  assert.equal(failed.health, "stale");
  assert.equal(failed.error.correlationId, "read-stale-001");
});

test("errors without data never become empty and preserve recovery classification", () => {
  const permission = state({
    error: { status: 403, code: "FORBIDDEN", message: "forbidden" },
    isError: true,
    isFetching: false,
    isPending: false,
  });
  assert.equal(permission.lifecycle, "error-no-data");
  assert.equal(permission.health, "degraded");
  assert.equal(permission.error.kind, "permission");

  const conflict = state({
    error: { status: 409, code: "REVISION_CONFLICT", message: "conflict" },
    isError: true,
    isFetching: false,
    isPending: false,
  });
  assert.equal(conflict.lifecycle, "error-no-data");
  assert.equal(conflict.health, "degraded");
  assert.equal(conflict.error.kind, "conflict");

  const network = state({
    error: {
      status: 0,
      code: "NETWORK_FAILURE",
      correlationId: "read-offline-001",
      message: "offline",
    },
    isError: true,
    isFetching: false,
    isPending: false,
  });
  assert.equal(network.lifecycle, "error-no-data");
  assert.equal(network.health, "offline");
  assert.equal(network.error.kind, "network");
});

test("source freshness and partial failures produce shared shell health semantics", () => {
  const stale = state({
    data: [{ id: "PRED-1" }],
    dataUpdatedAt: NOW,
    sourceUpdatedAt: NOW - 61_000,
    isFetching: false,
    isPending: false,
    isStale: false,
  });
  assert.equal(stale.lifecycle, "success-data");
  assert.equal(stale.health, "stale");

  const primary = queryRuntimeHealth(
    state({
      data: [{ id: "MISSION-1" }],
      dataUpdatedAt: NOW,
      isFetching: false,
      isPending: false,
      isStale: false,
    }),
    "Mission 台账",
  );
  const secondary = queryRuntimeHealth(
    state({
      error: { status: 503, code: "ALARM_OFFLINE", message: "offline" },
      isError: true,
      isFetching: false,
      isPending: false,
    }),
    "告警选择器",
    { partial: true },
  );
  const merged = mergeRuntimeHealth(primary, secondary);
  assert.equal(primary.label, "Ready");
  assert.equal(secondary.label, "Degraded");
  assert.equal(merged.label, "Degraded");
  assert.match(merged.detail, /告警选择器/);
});
