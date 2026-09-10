import assert from "node:assert/strict";
import test from "node:test";

import { API_ACCESS_EVENT } from "../lib/api-access-events.ts";
import { apiGet, apiPost, apiPostCommand, WindOpsApiError } from "../lib/api-client.ts";

test("POST transport retry reuses the exact idempotency key and request body", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ input: String(input), init });
    if (calls.length === 1) throw new TypeError("simulated lost response");
    return Response.json({ commandId: "CMD-STABLE-001" });
  };
  try {
    const result = await apiPostCommand(
      "/api/backend/missions/MISSION-1/comments",
      { body: "Response was lost after commit" },
      "network-loss-comment-001",
    );

    assert.deepEqual(result, { commandId: "CMD-STABLE-001" });
    assert.equal(calls.length, 2);
    assert.equal(calls[0].input, calls[1].input);
    assert.equal(calls[0].init.body, calls[1].init.body);
    assert.equal(
      new Headers(calls[0].init.headers).get("idempotency-key"),
      "network-loss-comment-001",
    );
    assert.equal(
      new Headers(calls[1].init.headers).get("idempotency-key"),
      "network-loss-comment-001",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("automatic POST keys remain stable across the one transport retry", async () => {
  const originalFetch = globalThis.fetch;
  const observedKeys = [];
  globalThis.fetch = async (_input, init) => {
    observedKeys.push(new Headers(init.headers).get("idempotency-key"));
    if (observedKeys.length === 1) throw new TypeError("simulated connection reset");
    return Response.json({ ok: true });
  };
  try {
    assert.deepEqual(await apiPost("/api/backend/resources/reassignments", { value: 1 }), {
      ok: true,
    });
    assert.equal(observedKeys.length, 2);
    assert.equal(observedKeys[0], observedKeys[1]);
    assert.match(observedKeys[0], /^windops-command-/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("API access failures distinguish authentication, authorization, backend, and network", async () => {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  const browserWindow = new EventTarget();
  const failures = [];
  browserWindow.addEventListener(API_ACCESS_EVENT, (event) => failures.push(event.detail));
  globalThis.window = browserWindow;

  try {
    for (const [status, kind] of [
      [401, "authentication"],
      [403, "authorization"],
      [503, "backend"],
    ]) {
      globalThis.fetch = async () =>
        Response.json(
          { error: { code: `STATUS_${status}`, message: `failure ${status}` } },
          { status },
        );
      await assert.rejects(
        () => apiGet("/api/backend/session"),
        (error) => error instanceof WindOpsApiError && error.status === status,
      );
      assert.equal(failures.at(-1).kind, kind);
      assert.equal(failures.at(-1).status, status);
    }

    globalThis.fetch = async () => {
      throw new TypeError("network down");
    };
    await assert.rejects(() => apiGet("/api/backend/session"), /network down/);
    assert.equal(failures.at(-1).kind, "network");
    assert.equal(failures.at(-1).status, null);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
  }
});
