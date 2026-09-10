import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  parseProductionControlCursor,
  parseProductionDomainEvent,
  parseProductionEventCursor,
  productionEventStreamUrl,
} from "../lib/production-events.ts";

test("production event URLs start at the live boundary and resume an exact cursor", () => {
  assert.equal(
    productionEventStreamUrl(["alarm.resolved", "alarm.opened", "alarm.opened"], null),
    "/api/agent-events?start=latest&event_type=alarm.opened&event_type=alarm.resolved",
  );
  assert.equal(
    productionEventStreamUrl(["scada.sample.accepted"], "42"),
    "/api/agent-events?cursor=42&event_type=scada.sample.accepted",
  );
  assert.equal(parseProductionEventCursor("9007199254740992"), null);
  assert.equal(parseProductionEventCursor(`v1.${"a".repeat(48)}`), `v1.${"a".repeat(48)}`);
  assert.throws(() => productionEventStreamUrl(["*"], null), /valid explicit event types/);
});

test("production domain events require a typed monotonic SSE identity", () => {
  const event = {
    sequence: 42,
    event_id: "event-42",
    event_type: "alarm.acknowledged",
    aggregate_type: "alarm",
    aggregate_id: "ALARM-42",
    payload: { revision: 2 },
    occurred_at: "2026-08-15T00:00:00Z",
  };
  assert.deepEqual(parseProductionDomainEvent(JSON.stringify(event), "alarm.acknowledged", "42"), {
    ...event,
    sequence: "42",
  });
  assert.equal(parseProductionDomainEvent(JSON.stringify(event), "alarm.assigned", "42"), null);
  assert.equal(parseProductionDomainEvent(JSON.stringify(event), "alarm.acknowledged", "41"), null);
  assert.equal(parseProductionControlCursor('{"next_cursor":42}', "42"), "42");
  assert.equal(parseProductionControlCursor('{"next_cursor":42}', "41"), null);
});

test("production workspaces consume SSE with persisted cursor and bounded reconnect", async () => {
  const hook = await readFile(new URL("../lib/use-production-events.ts", import.meta.url), "utf8");
  assert.match(hook, /new EventSource/);
  assert.match(hook, /window\.sessionStorage/);
  assert.match(hook, /PRODUCTION_EVENT_RETRY_MAX_MS/);
  assert.match(hook, /stream\.ready/);
  assert.match(hook, /persistCursor\(readyCursor\)/);
  assert.match(hook, /reconnect/);

  for (const path of [
    "../components/pages/alarm-center-page.tsx",
    "../components/pages/scada-page.tsx",
    "../components/pages/agent-control-page.tsx",
    "../components/pages/digital-twin-page.tsx",
  ]) {
    const source = await readFile(new URL(path, import.meta.url), "utf8");
    assert.match(source, /useProductionEvents/);
    assert.match(source, /runtimeMode === "production"|isProduction/);
  }
});
