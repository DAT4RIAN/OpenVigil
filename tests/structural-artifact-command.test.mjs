import assert from "node:assert/strict";
import test from "node:test";
import { createHash } from "node:crypto";
import { StructuralArtifactCommand } from "../lib/structural-artifact-command.ts";
import { OpenVigilApiError } from "../lib/api-client.ts";

const result = { evidence: { id: "synthetic-handoff" }, mission_revision: 5 };
const valid = (value) => typeof value?.evidence?.id === "string";
const grant = {
  artifact_uri: "minio://synthetic-test/work-orders/WO-test/tasks/task-test/evidence.json",
  upload_url: "https://upload.example.test/synthetic-evidence",
  required_headers: { "content-type": "application/json" },
  expires_at: "2099-01-01T00:00:00Z",
};
const input = () => ({
  file: new File(['{"source":"synthetic_test"}'], "evidence.json", { type: "application/json" }),
  presignPath: "/api/backend/structural-work-orders/WO-test/retests/uploads/presign",
  presignBody: { content_type: "application/json" },
  commandPath: "/api/backend/structural-work-orders/WO-test/retests",
  commandBody: {
    expected_mission_revision: 4,
    measurement: { retest_source_id: "synthetic-force" },
  },
});

test("proxy failure after a write freezes its key and an authorization failure cannot erase uncertainty", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  let stage = 0;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), ...init });
    if (String(url).endsWith("presign")) return Response.json(grant);
    if (init.method === "PUT") return new Response(null, { status: 200 });
    if (stage === 0) return Response.json({ error: { code: "BACKEND_TIMEOUT" } }, { status: 504 });
    if (stage === 1) return Response.json({ error: { code: "FORBIDDEN" } }, { status: 403 });
    return Response.json(result);
  };
  try {
    const command = new StructuralArtifactCommand();
    await assert.rejects(
      () => command.run(input(), valid),
      (error) => error.status === 504,
    );
    assert.equal(command.resultUnknown, true);
    stage = 1;
    await assert.rejects(
      () => command.run(input(), valid),
      (error) => error.status === 403,
    );
    assert.equal(command.resultUnknown, true);
    stage = 2;
    assert.deepEqual(await command.run(input(), valid), result);
    assert.equal(command.resultUnknown, false);
    const writes = calls.filter((call) => call.url.endsWith("/retests"));
    assert.equal(writes.length, 3);
    assert.equal(new Set(writes.map((call) => call.body)).size, 1);
    assert.equal(
      new Set(writes.map((call) => new Headers(call.headers).get("idempotency-key"))).size,
      1,
    );
    assert.equal(calls.filter((call) => call.method === "PUT").length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("lost handoff response replays frozen revision, artifact and key without another PUT", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  let fail = true;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), ...init });
    if (String(url).endsWith("presign")) return Response.json(grant);
    if (init.method === "PUT") return new Response(null, { status: 200 });
    if (fail) throw new TypeError("synthetic committed response loss");
    return Response.json(result);
  };
  try {
    const command = new StructuralArtifactCommand();
    const first = input();
    await assert.rejects(
      () => command.run(first, valid),
      (error) => error instanceof OpenVigilApiError && error.code === "COMMAND_RESULT_UNKNOWN",
    );
    assert.equal(command.resultUnknown, true);
    fail = false;
    // A refresh can already show revision 5. Reconciliation must replay 4.
    assert.deepEqual(
      await command.run({ ...input(), commandBody: { expected_mission_revision: 5 } }, valid),
      result,
    );
    const business = calls.filter((item) => item.url.endsWith("/retests"));
    assert.equal(business.length, 3);
    assert.equal(new Set(business.map((item) => item.body)).size, 1);
    assert.equal(JSON.parse(business[0].body).expected_mission_revision, 4);
    assert.equal(
      new Set(business.map((item) => new Headers(item.headers).get("idempotency-key"))).size,
      1,
    );
    assert.equal(JSON.parse(business[0].body).artifact_uri, grant.artifact_uri);
    assert.equal(
      JSON.parse(business[0].body).artifact_sha256,
      createHash("sha256")
        .update(Buffer.from(await first.file.arrayBuffer()))
        .digest("hex"),
    );
    assert.equal(calls.filter((item) => item.method === "PUT").length, 1);
    const put = calls.find((item) => item.method === "PUT");
    assert.equal(put.body, first.file);
    assert.equal(put.credentials, "omit");
    assert.equal(new Headers(put.headers).has("authorization"), false);
    assert.equal(command.resultUnknown, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("a failed object upload blocks registration and retries its retained grant", async () => {
  const originalFetch = globalThis.fetch;
  let uploads = 0;
  let presigns = 0;
  let registrations = 0;
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("presign")) {
      presigns++;
      return Response.json(grant);
    }
    if (init.method === "PUT") {
      uploads++;
      return new Response(null, { status: uploads === 1 ? 503 : 200 });
    }
    registrations++;
    return Response.json(result);
  };
  try {
    const command = new StructuralArtifactCommand();
    const request = input();
    await assert.rejects(() => command.run(request, valid), /HTTP 503/);
    assert.equal(registrations, 0);
    assert.equal(command.resultUnknown, false);
    assert.deepEqual(await command.run(request, valid), result);
    assert.equal(presigns, 1);
    assert.equal(uploads, 2);
    assert.equal(registrations, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("an expired unused grant is renewed, while malformed command results preserve replay", async () => {
  const originalFetch = globalThis.fetch;
  const presignKeys = [];
  const commandKeys = [];
  let uploads = 0;
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("presign")) {
      presignKeys.push(new Headers(init.headers).get("idempotency-key"));
      return Response.json({
        ...grant,
        expires_at: presignKeys.length === 1 ? "2000-01-01T00:00:00Z" : grant.expires_at,
      });
    }
    if (init.method === "PUT") {
      uploads++;
      return new Response(null);
    }
    commandKeys.push(new Headers(init.headers).get("idempotency-key"));
    return commandKeys.length === 1
      ? new Response("{truncated", { status: 201 })
      : Response.json(result);
  };
  try {
    const command = new StructuralArtifactCommand();
    const request = input();
    await assert.rejects(() => command.run(request, valid), /已过期/);
    assert.equal(uploads, 0);
    await assert.rejects(
      () => command.run(request, valid),
      (error) => error.code === "COMMAND_RESULT_UNKNOWN",
    );
    assert.equal(command.resultUnknown, true);
    assert.deepEqual(await command.run(request, valid), result);
    assert.equal(presignKeys.length, 2);
    assert.notEqual(presignKeys[0], presignKeys[1]);
    assert.deepEqual(commandKeys, [commandKeys[0], commandKeys[0]]);
    assert.equal(uploads, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("invalid successful handoff shape is unknown and cannot silently reset its command", async () => {
  const originalFetch = globalThis.fetch;
  const keys = [];
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("presign")) return Response.json(grant);
    if (init.method === "PUT") return new Response(null);
    keys.push(new Headers(init.headers).get("idempotency-key"));
    return Response.json(keys.length === 1 ? { unrelated: true } : result);
  };
  try {
    const command = new StructuralArtifactCommand();
    await assert.rejects(
      () => command.run(input(), valid),
      (error) => error.code === "COMMAND_RESULT_UNKNOWN",
    );
    assert.deepEqual(await command.run(input(), valid), result);
    assert.deepEqual(keys, [keys[0], keys[0]]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
