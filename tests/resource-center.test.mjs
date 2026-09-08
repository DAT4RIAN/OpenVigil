import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("resource-center-test", `${process.pid}-${Date.now()}`);
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

test("resource center exposes a deterministic WT-023 execution plan", async () => {
  const [all, repeated, featured] = await Promise.all([
    fetchJson("/api/resources"),
    fetchJson("/api/resources"),
    fetchJson("/api/resources?workOrderId=wo-20260823-017"),
  ]);

  assert.deepEqual(repeated, all);
  assert.equal(all.meta.count, 25);
  assert.equal(all.meta.total, 25);
  assert.equal(all.meta.spareParts, 7);
  assert.equal(all.meta.crews, 4);
  assert.equal(all.meta.vessels, 3);
  assert.equal(all.meta.tools, 6);
  assert.equal(all.meta.weatherWindows, 5);
  assert.equal(all.meta.deterministic, true);

  const bearing = all.data.spareParts.find((item) => item.partNumber === "GB-MB-165-01");
  assert.ok(bearing, "main bearing inventory must exist");
  assert.equal(bearing.onHand, 2);
  assert.equal(bearing.reserved, 1);
  assert.equal(bearing.available, 1);
  assert.equal(bearing.status, "low-stock");
  assert.deepEqual(bearing.reservedForWorkOrderIds, ["WO-20260823-017"]);

  assert.equal(featured.meta.workOrderId, "WO-20260823-017");
  assert.equal(featured.data.spareParts.length, 2);
  assert.equal(featured.data.crews.length, 1);
  assert.equal(featured.data.crews[0].name, "海维二组");
  assert.equal(featured.data.vessels.length, 1);
  assert.equal(featured.data.vessels[0].name, "CTV-03 东海迅捷");
  assert.equal(featured.data.tools.length, 4);
  assert.ok(
    featured.data.weatherWindows.some(
      (window) => window.suitability === "suitable" && window.waveHeightM <= 1.8,
    ),
  );

  const tools = await fetchJson("/api/resources?category=tools&q=振动");
  assert.equal(tools.meta.count, 1);
  assert.equal(tools.data.tools[0].assignedWorkOrderId, "WO-20260823-017");
  assert.equal(tools.data.spareParts.length, 0);

  const invalid = await fetchJson("/api/resources?category=everything", 400);
  assert.equal(invalid.error.code, "INVALID_RESOURCE_CATEGORY");
});

test("resource center server-renders its operational markers", async () => {
  const response = await fetchRoute("/resources", { accept: "text/html" });
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /运维资源中心/);
  assert.match(html, /WO-20260823-017/);
  assert.match(html, /GB-MB-165-01/);
  assert.match(html, /CTV-03/);
});
