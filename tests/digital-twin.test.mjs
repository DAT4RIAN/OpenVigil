import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("digital-twin-test", `${process.pid}-${Date.now()}`);
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

function fetchRoute(path, headers = {}) {
  return worker.fetch(
    new Request(new URL(path, "http://localhost"), { headers }),
    environment,
    context,
  );
}

async function fetchJson(path, expectedStatus = 200) {
  const response = await fetchRoute(path, { accept: "application/json" });
  assert.equal(response.status, expectedStatus, `${path} returned ${response.status}`);
  assert.match(response.headers.get("content-type") ?? "", /^application\/json\b/i);
  return response.json();
}

test("digital twin API returns a deterministic twelve-subsystem WT-023 snapshot", async () => {
  const [first, repeated] = await Promise.all([
    fetchJson("/api/digital-twin?turbineId=WT-023"),
    fetchJson("/api/digital-twin?turbineId=wt-023"),
  ]);

  assert.deepEqual(repeated, first);
  assert.equal(first.data.subsystems.length, 12);
  assert.equal(first.data.turbine.id, "WT-023");
  assert.equal(first.data.turbine.healthScore, 68);
  assert.equal(first.data.context.missionStatus, "under-review");
  assert.equal(first.data.context.workOrderStatus, "draft");
  assert.equal(first.data.model.realPhysicsSimulation, false);
  assert.equal(first.data.model.readOnly, true);
  assert.equal(first.data.model.source, "ephemeral-workflow-overlay");
  assert.equal(first.meta.workflowPersistence, "ephemeral");
  assert.equal(first.meta.readOnly, true);
});

test("digital twin API supports the full fleet and validates turbine IDs", async () => {
  const generic = await fetchJson("/api/digital-twin?turbineId=WT-041");
  assert.equal(generic.data.subsystems.length, 12);
  assert.equal(generic.data.turbine.id, "WT-041");
  assert.equal(generic.data.model.source, "fixture");
  assert.equal(
    generic.data.subsystems.reduce((total, subsystem) => total + subsystem.alertCount, 0),
    generic.data.context.activeAlarmCount,
  );

  const unknown = await fetchJson("/api/digital-twin?turbineId=WT-999", 404);
  assert.equal(unknown.error.code, "TURBINE_NOT_FOUND");
  const invalid = await fetchJson("/api/digital-twin?turbineId=DROP_TABLE", 400);
  assert.equal(invalid.error.code, "INVALID_TURBINE_ID");
});

test("digital twin page renders its model, signals, and read-only boundary", async () => {
  const response = await fetchRoute("/digital-twin", { accept: "text/html" });
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /数字孪生/);
  assert.match(html, /运营数字孪生/);
  assert.match(html, /12 个子系统/);
  assert.match(html, /非物理仿真/);
  assert.match(html, /只读/);
});

test("digital twin client fallback is asset-scoped and labels the actual workflow persistence", async () => {
  const source = await import("node:fs/promises").then((fs) =>
    fs.readFile(new URL("../components/pages/digital-twin-page.tsx", import.meta.url), "utf8"),
  );

  assert.doesNotMatch(source, /const initialSnapshot\s*=\s*buildDigitalTwinSnapshot\("WT-023"\)/);
  assert.match(source, /buildDigitalTwinSnapshot\(turbineId\)/);
  assert.match(source, /workflowPersistence === "d1"/);
  assert.match(source, /同资产降级快照/);
  assert.doesNotMatch(source, /SCADA 与 D1\s*工作流状态/);
});
