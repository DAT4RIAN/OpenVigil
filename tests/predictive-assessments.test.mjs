import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("predictive-test", `${process.pid}-${Date.now()}`);
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

test("predictive API returns a deterministic risk-ranked 64 turbine fixture", async () => {
  const [first, repeated] = await Promise.all([
    fetchJson("/api/predictive-assessments"),
    fetchJson("/api/predictive-assessments"),
  ]);

  assert.deepEqual(repeated, first);
  assert.equal(first.meta.total, 64);
  assert.equal(first.meta.filteredTotal, 64);
  assert.equal(first.meta.count, 64);
  assert.equal(first.meta.model.mode, "deterministic-fixture");
  assert.equal(first.meta.model.deterministic, true);
  assert.equal(first.meta.model.readOnly, true);
  assert.equal(first.meta.model.performsRealInference, false);
  assert.equal(new Set(first.data.map((item) => item.turbineId)).size, 64);

  for (let index = 1; index < first.data.length; index += 1) {
    assert.ok(
      first.data[index - 1].priorityScore >= first.data[index].priorityScore,
      "default results must remain in descending maintenance priority order",
    );
  }

  const featured = first.data.find((item) => item.turbineId === "WT-023");
  assert.ok(featured);
  assert.equal(featured.component, "主轴承");
  assert.equal(featured.componentHealth, 63);
  assert.equal(featured.failureProbability30d, 34);
  assert.equal(featured.remainingUsefulLifeDays, 47);
  assert.equal(featured.anomalyScore, 0.86);
  assert.equal(featured.probabilityBand, 4);
  assert.equal(featured.consequenceBand, 4);
  assert.equal(featured.matrixRisk, "high");
});

test("predictive API supports exact turbine, risk, trend, query, sort, and pagination filters", async () => {
  const [featured, high, declining, queried, lowestRul, pageEnd] = await Promise.all([
    fetchJson("/api/predictive-assessments?turbineId=wt-023"),
    fetchJson("/api/predictive-assessments?risk=high"),
    fetchJson("/api/predictive-assessments?trend=declining"),
    fetchJson(`/api/predictive-assessments?q=${encodeURIComponent("主轴承")}`),
    fetchJson("/api/predictive-assessments?sort=rul-asc&limit=8"),
    fetchJson("/api/predictive-assessments?offset=64&limit=8"),
  ]);

  assert.equal(featured.meta.count, 1);
  assert.equal(featured.data[0].turbineId, "WT-023");
  assert.ok(high.data.length > 0);
  assert.ok(high.data.every((item) => item.matrixRisk === "high"));
  assert.ok(declining.data.length > 0);
  assert.ok(declining.data.every((item) => item.trend === "declining"));
  assert.ok(queried.data.some((item) => item.turbineId === "WT-023"));
  assert.equal(lowestRul.meta.count, 8);
  assert.ok(
    lowestRul.data.every(
      (item, index, data) =>
        index === 0 || data[index - 1].remainingUsefulLifeDays <= item.remainingUsefulLifeDays,
    ),
  );
  assert.equal(pageEnd.meta.count, 0);
});

test("predictive API rejects invalid filter and pagination contracts", async () => {
  const cases = [
    ["/api/predictive-assessments?risk=urgent", "INVALID_RISK"],
    ["/api/predictive-assessments?trend=falling", "INVALID_TREND"],
    ["/api/predictive-assessments?sort=random", "INVALID_SORT"],
    ["/api/predictive-assessments?offset=-1", "INVALID_PAGINATION"],
    ["/api/predictive-assessments?limit=65", "INVALID_PAGINATION"],
  ];

  for (const [path, code] of cases) {
    const body = await fetchJson(path, 400);
    assert.equal(body.error.code, code);
  }
});

test("predictive maintenance page renders the WT-023 model story", async () => {
  const response = await fetchRoute("/predictive-maintenance", { accept: "text/html" });
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /预测性维护/);
  assert.match(html, /WT-023/);
  assert.match(html, /FAILURE PROBABILITY/);
  assert.match(html, /PROBABILITY × CONSEQUENCE/);
  assert.match(html, /FIXTURE MODEL/);
  assert.match(html, /无真实推理/);
});
