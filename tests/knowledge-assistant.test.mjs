import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("knowledge-test", `${process.pid}-${Date.now()}`);
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

function request(path, init = {}) {
  return worker.fetch(new Request(new URL(path, "http://localhost"), init), environment, context);
}

async function jsonRequest(path, init = {}, expectedStatus = 200) {
  const response = await request(path, {
    headers: { accept: "application/json", ...(init.headers ?? {}) },
    ...init,
  });
  assert.equal(response.status, expectedStatus, `${path} returned ${response.status}`);
  assert.match(response.headers.get("content-type") ?? "", /^application\/json\b/i);
  assert.equal(response.headers.get("cache-control"), "no-store");
  return response.json();
}

const postJson = (body, expectedStatus = 200) =>
  jsonRequest(
    "/api/knowledge-assistant",
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    },
    expectedStatus,
  );

test("knowledge page renders the catalog and default WT-023 question", async () => {
  const response = await request("/knowledge", { headers: { accept: "text/html" } });
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /Knowledge Base/);
  assert.match(html, /WT-023为什么被判断为主轴承退化？/);
  assert.match(html, /DOCUMENT CATALOG/);
  assert.match(html, /DETERMINISTIC/);
});

test("knowledge document API performs exact search, filter, sort, and pagination", async () => {
  const catalog = await jsonRequest("/api/knowledge-documents");
  assert.equal(catalog.ok, true);
  assert.equal(catalog.error, null);
  assert.equal(catalog.data.documents.length, 10);
  assert.equal(catalog.meta.count, 10);
  assert.equal(catalog.meta.total, 10);
  assert.equal(catalog.meta.page, 1);
  assert.equal(catalog.meta.pageSize, 10);
  assert.equal(catalog.meta.deterministic, true);
  assert.equal(catalog.meta.persisted, false);
  assert.equal(catalog.data.facets.vectorized, 10);

  const filtered = await jsonRequest(
    `/api/knowledge-documents?q=${encodeURIComponent("主轴承")}&type=failure-case&sort=title&order=asc&page=1&pageSize=2`,
  );
  assert.equal(filtered.ok, true);
  assert.equal(filtered.meta.type, "failure-case");
  assert.equal(filtered.meta.query, "主轴承");
  assert.ok(filtered.meta.total >= 1);
  assert.ok(filtered.data.documents.length <= 2);
  assert.ok(filtered.data.documents.every((document) => document.type === "failure-case"));
  assert.ok(
    filtered.data.documents.every((document) =>
      [document.id, document.title, document.equipment, document.summary, ...document.tags]
        .join(" ")
        .includes("主轴承"),
    ),
  );

  const [firstPage, secondPage] = await Promise.all([
    jsonRequest("/api/knowledge-documents?sort=title&order=asc&page=1&pageSize=3"),
    jsonRequest("/api/knowledge-documents?sort=title&order=asc&page=2&pageSize=3"),
  ]);
  assert.equal(firstPage.meta.count, 3);
  assert.equal(secondPage.meta.count, 3);
  assert.equal(firstPage.meta.totalPages, 4);
  assert.deepEqual(
    firstPage.data.documents.map((document) => document.title),
    [...firstPage.data.documents]
      .sort((left, right) => left.title.localeCompare(right.title, "zh-CN"))
      .map((document) => document.title),
  );
  assert.equal(
    firstPage.data.documents.some((document) =>
      secondPage.data.documents.some((candidate) => candidate.id === document.id),
    ),
    false,
  );
});

test("knowledge document API returns one strict error envelope for invalid inputs", async () => {
  const cases = [
    ["/api/knowledge-documents?type=secret", "INVALID_DOCUMENT_TYPE"],
    ["/api/knowledge-documents?sort=score", "INVALID_SORT"],
    ["/api/knowledge-documents?order=sideways", "INVALID_SORT_ORDER"],
    ["/api/knowledge-documents?page=0", "INVALID_PAGINATION"],
    ["/api/knowledge-documents?pageSize=51", "INVALID_PAGINATION"],
  ];
  for (const [path, code] of cases) {
    const response = await jsonRequest(path, {}, 400);
    assert.equal(response.ok, false);
    assert.equal(response.data, null);
    assert.equal(response.error.code, code);
    assert.equal(typeof response.error.message, "string");
    assert.equal(response.meta.deterministic, true);
    assert.equal(response.meta.persisted, false);
  }
});

test("default assistant question returns a repeatable structured answer with source citations", async () => {
  const input = {
    question: "WT-023为什么被判断为主轴承退化？",
    turbineId: "wt-023",
    missionId: "mission-2026-0823",
  };
  const [first, repeated] = await Promise.all([postJson(input), postJson(input)]);
  assert.deepEqual(repeated, first);
  assert.equal(first.ok, true);
  assert.equal(first.error, null);
  assert.equal(first.meta.deterministic, true);
  assert.equal(first.meta.realEmbedding, false);
  assert.equal(first.meta.retrievalMode, "deterministic-keyword-demo");

  const answer = first.data.answer;
  assert.equal(answer.question, input.question);
  assert.deepEqual(answer.scope, {
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
  });
  assert.equal(answer.answer.confidencePercent, 87);
  assert.equal(answer.answer.findings.length, 4);
  assert.match(answer.answer.findings[0].value, /3\.79.*4\.81.*27%/);
  assert.match(answer.answer.findings[1].value, /8\.4°C/);
  assert.match(answer.answer.findings[2].value, /BPFO.*19%/);
  assert.match(answer.answer.conclusion, /润滑脂取样与内窥镜检查/);
  assert.equal(answer.citations.length, 4);
  assert.equal(answer.retrieval.retrievedCount, answer.citations.length);
  assert.equal(answer.retrieval.candidateCount, 30);
  assert.equal(answer.retrieval.supportingFailureCaseIds.length, 2);
  assert.ok(answer.retrieval.evidenceIds.includes("EV-023-VIB-001"));
  assert.ok(answer.retrieval.evidenceIds.includes("EV-023-SPECTRUM-005"));
  assert.match(answer.disclaimer, /不是生产级 embedding/);

  const knownDocumentIds = new Set([
    "KB-GW165-OM-001",
    "KB-MB-PROC-004",
    "KB-CASE-2019-017",
    "KB-SCADA-REPORT-023",
    "KB-ISO-10816",
    "KB-WO-2025-118",
    "KB-SAFETY-STD-011",
    "KB-OPS-PROC-002",
    "KB-GEARBOX-CASE-022",
    "KB-INSPECTION-023-2026Q2",
  ]);
  for (const citation of answer.citations) {
    assert.ok(knownDocumentIds.has(citation.docId));
    assert.equal(typeof citation.title, "string");
    assert.ok(citation.title.length > 0);
    assert.ok(Number.isInteger(citation.page) && citation.page > 0);
    assert.equal(typeof citation.summary, "string");
    assert.ok(citation.summary.length > 20);
    assert.match(citation.href, /^\/knowledge\?document=/);
  }
});

test("assistant API rejects malformed bodies, unknown fields, and unsupported demo scope", async () => {
  const invalidJson = await jsonRequest(
    "/api/knowledge-assistant",
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{not-json",
    },
    400,
  );
  assert.equal(invalidJson.error.code, "INVALID_JSON");

  const cases = [
    [[], 400, "INVALID_REQUEST"],
    [{}, 400, "INVALID_QUESTION"],
    [{ question: "   " }, 400, "INVALID_QUESTION"],
    [{ question: "test", debug: true }, 400, "UNKNOWN_FIELDS"],
    [{ question: "test", turbineId: 23 }, 400, "INVALID_SCOPE"],
    [{ question: "test", turbineId: "WT-041" }, 422, "UNSUPPORTED_DEMO_SCOPE"],
  ];
  for (const [body, status, code] of cases) {
    const response = await postJson(body, status);
    assert.equal(response.ok, false);
    assert.equal(response.data, null);
    assert.equal(response.error.code, code);
    assert.equal(typeof response.error.message, "string");
    assert.equal(response.meta.deterministic, true);
    assert.equal(response.meta.realEmbedding, false);
  }
});
