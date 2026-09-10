import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("platform-admin-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

const canarySecret = "must-not-appear-in-system-status";
const environment = {
  ASSETS: {
    fetch: async () => new Response("Not found", { status: 404 }),
  },
  WINDOPS_TEST_SECRET: canarySecret,
  API_TOKEN: "also-must-not-appear",
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

test("platform admin fixtures expose a deterministic 32+ object catalog and honest model boundaries", async () => {
  const [catalog, repeatedCatalog, archive, retrieval] = await Promise.all([
    fetchJson("/api/data-catalog"),
    fetchJson("/api/data-catalog"),
    fetchJson("/api/data-catalog?category=archive"),
    fetchJson("/api/model-registry?kind=retrieval"),
  ]);

  assert.deepEqual(repeatedCatalog, catalog);
  assert.equal(catalog.meta.schemaObjects.length, 33);
  assert.equal(new Set(catalog.meta.schemaObjects).size, catalog.meta.schemaObjects.length);
  assert.equal(catalog.meta.hierarchy.farm.turbineCount, 64);
  assert.equal(catalog.meta.hierarchy.subsystems.length, 12);
  assert.ok(
    catalog.meta.hierarchy.subsystems.some(
      (subsystem) =>
        subsystem.key === "main-bearing" &&
        subsystem.sensors.some((sensor) => sensor.metric === "main-bearing-vibration-rms"),
    ),
  );
  assert.equal(
    catalog.data.find((entry) => entry.id === "DATA-ARCHIVE-SCADA")?.recordCount,
    131_072,
  );
  assert.ok(archive.data.every((entry) => entry.category === "archive"));
  assert.equal(retrieval.data.length, 1);
  assert.equal(retrieval.data[0].kind, "retrieval");
  assert.equal(retrieval.data[0].realInference, false);
  assert.equal(retrieval.data[0].usesEmbeddings, false);
  assert.equal(retrieval.data[0].artifactBacked, false);
});

test("data catalog API provides filtering, hierarchy, query links, and strict parameters", async () => {
  const [first, repeated, archive, schema, search, page] = await Promise.all([
    fetchJson("/api/data-catalog"),
    fetchJson("/api/data-catalog"),
    fetchJson("/api/data-catalog?category=archive"),
    fetchJson("/api/data-catalog?category=schema&status=read-only"),
    fetchJson("/api/data-catalog?q=SCADA"),
    fetchJson("/api/data-catalog?offset=1&limit=2"),
  ]);

  assert.deepEqual(repeated, first);
  assert.equal(first.meta.deterministic, true);
  assert.equal(first.meta.readOnly, true);
  assert.equal(first.meta.scadaArchiveCount, 131_072);
  assert.equal(first.meta.schemaObjectCount, 33);
  assert.equal(first.meta.hierarchy.farm.turbineCount, 64);
  assert.equal(first.meta.hierarchy.subsystems.length, 12);
  assert.ok(first.data.every((entry) => entry.queryHref.startsWith("/")));
  assert.ok(archive.data.length >= 4);
  assert.ok(archive.data.every((entry) => entry.category === "archive"));
  assert.equal(schema.data.length, 1);
  assert.equal(schema.data[0].schemaObjectCount, 33);
  assert.ok(search.data.some((entry) => entry.id === "DATA-ARCHIVE-SCADA"));
  assert.equal(page.data.length, 2);
  assert.equal(page.meta.offset, 1);
  assert.equal(page.meta.limit, 2);
  assert.equal(page.meta.hasMore, true);
  assert.equal(page.meta.nextOffset, 3);

  const invalidCases = [
    ["/api/data-catalog?category=warehouse", "INVALID_CATEGORY"],
    ["/api/data-catalog?status=online", "INVALID_STATUS"],
    ["/api/data-catalog?offset=-1", "INVALID_OFFSET"],
    ["/api/data-catalog?limit=65", "INVALID_LIMIT"],
    ["/api/data-catalog?unexpected=1", "INVALID_QUERY_PARAMETER"],
    [`/api/data-catalog?q=${"x".repeat(101)}`, "INVALID_QUERY"],
  ];
  for (const [path, code] of invalidCases) {
    const body = await fetchJson(path, 400);
    assert.equal(body.error.code, code);
  }
});

test("model registry API discloses deterministic implementations without claiming ML inference", async () => {
  const [first, repeated, retrieval, available] = await Promise.all([
    fetchJson("/api/model-registry"),
    fetchJson("/api/model-registry"),
    fetchJson("/api/model-registry?kind=retrieval"),
    fetchJson("/api/model-registry?status=available"),
  ]);

  assert.deepEqual(repeated, first);
  assert.equal(first.meta.total, 5);
  assert.equal(first.meta.realInferenceCount, 0);
  assert.equal(first.meta.embeddingBackedCount, 0);
  assert.ok(first.data.every((model) => model.realInference === false));
  assert.ok(first.data.every((model) => model.usesEmbeddings === false));
  assert.equal(retrieval.data.length, 1);
  assert.match(retrieval.data[0].limitation, /embedding/i);
  assert.equal(available.data.length, 1);
  assert.equal(available.data[0].kind, "report");

  const invalidCases = [
    ["/api/model-registry?kind=llm", "INVALID_MODEL_KIND"],
    ["/api/model-registry?status=trained", "INVALID_MODEL_STATUS"],
    ["/api/model-registry?version=1", "INVALID_QUERY_PARAMETER"],
  ];
  for (const [path, code] of invalidCases) {
    const body = await fetchJson(path, 400);
    assert.equal(body.error.code, code);
  }
});

test("system status API is read-only, diagnostic, and never echoes environment values", async () => {
  const [first, repeated] = await Promise.all([
    fetchJson("/api/system-status"),
    fetchJson("/api/system-status"),
  ]);

  assert.deepEqual(repeated, first);
  assert.equal(first.meta.deterministic, true);
  assert.equal(first.meta.readOnly, true);
  assert.equal(first.meta.redacted, true);
  assert.equal(first.data.security.environmentValuesExposed, false);
  assert.equal(first.data.security.secretNamesExposed, false);
  assert.equal(first.data.identity.authenticated, false);
  assert.equal(first.data.websockets.length, 3);
  assert.equal(first.data.connections.length, 4);
  assert.ok(first.data.connections.some((connection) => connection.id === "d1-workflow"));

  const serialized = JSON.stringify(first);
  assert.doesNotMatch(serialized, new RegExp(canarySecret, "i"));
  assert.doesNotMatch(serialized, /also-must-not-appear/i);

  const invalid = await fetchJson("/api/system-status?verbose=true", 400);
  assert.equal(invalid.error.code, "INVALID_QUERY_PARAMETER");
});

test("platform admin pages render real workspaces and explicit safety boundaries", async () => {
  const pages = await Promise.all([
    fetchRoute("/data", { accept: "text/html" }),
    fetchRoute("/models", { accept: "text/html" }),
    fetchRoute("/settings", { accept: "text/html" }),
  ]);
  for (const response of pages) {
    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  }

  const [dataHtml, modelHtml, settingsHtml] = await Promise.all(
    pages.map((response) => response.text()),
  );
  assert.match(dataHtml, /数据中心/);
  assert.match(dataHtml, /风场 → 风机 → 子系统 → 传感器/);
  assert.match(dataHtml, /131,072/);
  assert.match(dataHtml, /数据集目录/);
  assert.match(dataHtml, /受治理基准数据/);
  assert.match(dataHtml, /生产数据连接未启用/);
  assert.match(dataHtml, /不会用 fixture 冒充 CARE/);
  assert.match(modelHtml, /模型管理/);
  assert.match(modelHtml, /不是真正?生产 ML 模型仓库|不是生产 ML 模型仓库/);
  assert.match(modelHtml, /无真实 embedding/);
  assert.match(settingsHtml, /系统设置/);
  assert.match(settingsHtml, /连接诊断/);
  assert.match(settingsHtml, /诊断已脱敏/);
  assert.match(settingsHtml, /显示主题/);
});
