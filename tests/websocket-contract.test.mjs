import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("websocket-contract-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

const environment = {
  ASSETS: {
    fetch: async () => new Response("Not found", { status: 404 }),
  },
};

const context = {
  waitUntil() {},
  passThroughOnException() {},
};

async function fetchJson(path, headers = {}) {
  const response = await worker.fetch(
    new Request(new URL(path, "http://localhost"), {
      headers: { accept: "application/json", ...headers },
    }),
    environment,
    context,
  );
  const body = await response.json();
  return { response, body };
}

test("all realtime endpoints advertise one deterministic WebSocket protocol", async () => {
  for (const channel of ["scada", "alarms", "agent-events"]) {
    const { response, body } = await fetchJson(`/ws/${channel}`);
    assert.equal(response.status, 426);
    assert.equal(response.headers.get("upgrade"), "websocket");
    assert.equal(body.error.code, "WEBSOCKET_UPGRADE_REQUIRED");
    assert.equal(body.meta.channel, channel);
    assert.equal(body.meta.protocol, "windops.realtime.v1");
    assert.equal(body.meta.deterministic, true);
  }
});

test("Node fallback remains finite for attempted upgrade requests", async () => {
  const { response, body } = await fetchJson("/ws/scada", {
    connection: "Upgrade",
    upgrade: "websocket",
  });
  assert.equal(response.status, 426);
  assert.equal(body.error.code, "WEBSOCKET_UPGRADE_REQUIRED");
  assert.equal(body.meta.runtimeSupported, false);
});
