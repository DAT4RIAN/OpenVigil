import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("maintenance-plan-test", `${process.pid}-${Date.now()}`);
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

test("maintenance plan API returns a deterministic read-only schedule derived from operational fixtures", async () => {
  const [first, repeated] = await Promise.all([
    fetchJson("/api/maintenance-plans"),
    fetchJson("/api/maintenance-plans"),
  ]);

  assert.deepEqual(repeated, first);
  assert.equal(first.meta.total, 9);
  assert.equal(first.meta.filteredTotal, 9);
  assert.equal(first.meta.model.mode, "derived-demo-schedule");
  assert.equal(first.meta.model.deterministic, true);
  assert.equal(first.meta.model.readOnly, true);
  assert.deepEqual(first.meta.model.provenance, [
    "workOrders",
    "weatherWindows",
    "resources",
    "turbines",
  ]);

  const featured = first.data.find((plan) => plan.workOrderId === "WO-20260823-017");
  assert.ok(featured);
  assert.equal(featured.turbineId, "WT-023");
  assert.equal(featured.workOrderStatus, "draft");
  assert.equal(featured.status, "approval-gated");
  assert.equal(featured.weather.id, "WW-20260814-AM");
  assert.equal(featured.weather.state, "suitable");
  assert.equal(featured.weather.coverage, "full");
  assert.equal(featured.crew.id, "CREW-OFFSHORE-02");
  assert.equal(featured.vessels[0].id, "VESSEL-CTV-03");
  assert.ok(featured.spareParts.length >= 2);
  assert.ok(featured.tools.length >= 4);
  assert.ok(featured.conflicts.some((conflict) => conflict.code === "APPROVAL_GATE"));
  assert.equal(featured.readOnly, true);
});

test("maintenance plan API applies exact filters and deterministic sorting", async () => {
  const [turbine, critical, conditional, team, readiness] = await Promise.all([
    fetchJson("/api/maintenance-plans?q=WT-041"),
    fetchJson("/api/maintenance-plans?risk=critical"),
    fetchJson("/api/maintenance-plans?window=conditional"),
    fetchJson("/api/maintenance-plans?team=CREW-OFFSHORE-02"),
    fetchJson("/api/maintenance-plans?sort=readiness-desc&limit=5"),
  ]);

  assert.equal(turbine.meta.filteredTotal, 1);
  assert.equal(turbine.data[0].turbineId, "WT-041");
  assert.ok(critical.data.length > 0);
  assert.ok(critical.data.every((plan) => plan.risk === "critical"));
  assert.ok(conditional.data.length > 0);
  assert.ok(conditional.data.every((plan) => plan.weather.state === "conditional"));
  assert.ok(team.data.length > 0);
  assert.ok(team.data.every((plan) => plan.teamKey === "CREW-OFFSHORE-02"));
  assert.equal(readiness.data.length, 5);
  assert.ok(
    readiness.data.every(
      (plan, index, plans) =>
        index === 0 || plans[index - 1].readinessPercent >= plan.readinessPercent,
    ),
  );
});

test("maintenance plan API rejects unsupported filters, sorts, teams, and pagination", async () => {
  const cases = [
    ["/api/maintenance-plans?status=queued", "INVALID_STATUS"],
    ["/api/maintenance-plans?risk=urgent", "INVALID_RISK"],
    ["/api/maintenance-plans?window=storm", "INVALID_WINDOW"],
    ["/api/maintenance-plans?team=missing", "INVALID_TEAM"],
    ["/api/maintenance-plans?sort=random", "INVALID_SORT"],
    ["/api/maintenance-plans?offset=-1", "INVALID_PAGINATION"],
    ["/api/maintenance-plans?unknown=true", "INVALID_QUERY_PARAMETER"],
  ];

  for (const [path, code] of cases) {
    const body = await fetchJson(path, 400);
    assert.equal(body.error.code, code);
  }
});

test("maintenance plan page renders calendar, list, resource, weather, and conflict controls", async () => {
  const response = await fetchRoute("/maintenance", { accept: "text/html" });
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /维护计划/);
  assert.match(html, /确定性演示排程/);
  assert.match(html, /演示数据 · 只读/);
  assert.match(html, /计划日历/);
  assert.match(html, /日历/);
  assert.match(html, /列表/);
  assert.match(html, /WT-023/);
  assert.match(html, /WO-20260823-017/);
  assert.match(html, /天气窗口/);
  assert.match(html, /维护班组/);
  assert.match(html, /作业船舶/);
  assert.match(html, /冲突与风险/);
});
