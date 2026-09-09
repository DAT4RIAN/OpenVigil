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
  assert.equal(first.meta.retrievalMode, "fixture-passage-fallback");
  assert.equal(first.meta.persistence, "fixture");

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
  assert.ok(answer.citations.length >= 3);
  assert.equal(answer.retrieval.retrievedCount, answer.citations.length);
  assert.equal(answer.retrieval.candidateCount, 11);
  assert.equal(answer.retrieval.supportingFailureCaseIds.length, 2);
  assert.ok(answer.retrieval.evidenceIds.includes("EV-023-VIB-001"));
  assert.ok(answer.retrieval.evidenceIds.includes("EV-023-SPECTRUM-005"));
  assert.match(answer.disclaimer, /passage 正文上的确定性词项与短语检索/);

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
    assert.match(citation.passageId, /^KBP-/);
    assert.equal(typeof citation.section, "string");
    assert.ok(citation.section.length > 0);
    assert.equal(typeof citation.quote, "string");
    assert.equal(typeof citation.summary, "string");
    assert.ok(citation.summary.length > 20);
    assert.equal(citation.summary, citation.quote);
    assert.ok(citation.score > 0);
    assert.match(citation.href, /^\/knowledge\?document=/);
  }
  const citedPassages = new Set(answer.citations.map((citation) => citation.passageId));
  for (const finding of answer.answer.findings) {
    assert.ok(finding.citationIds.length > 0);
    assert.deepEqual(finding.citationIds, finding.passageIds);
    assert.ok(finding.passageIds.every((passageId) => citedPassages.has(passageId)));
  }
  assert.doesNotMatch(JSON.stringify(first), /chain.?of.?thought|hidden.?reasoning|\bcot\b/i);
});

test("WT-023 safety questions retrieve Chinese passage text without borrowing the bearing diagnosis", async () => {
  const response = await postJson({
    question: "海上登塔和能源隔离条件是什么？",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
  });

  assert.equal(response.ok, true);
  assert.ok(response.data.answer.retrieval.queryTerms.length > 0);
  assert.ok(response.data.answer.citations.length > 0);
  assert.equal(response.data.answer.citations[0].docId, "KB-SAFETY-STD-011");
  assert.match(response.data.answer.citations[0].quote, /海上登塔.*能源隔离/);
  assert.ok(
    response.data.answer.answer.findings.every(
      (finding) => finding.citationIds.length > 0 && finding.passageIds.length > 0,
    ),
  );
  assert.notEqual(response.data.answer.answer.confidencePercent, 87);
  assert.deepEqual(response.data.answer.retrieval.evidenceIds, []);
  assert.deepEqual(response.data.answer.retrieval.supportingFailureCaseIds, []);
  assert.doesNotMatch(response.data.answer.answer.conclusion, /主轴承早期退化/);
});

test("maintenance procedure questions do not inherit the WT-023 diagnosis confidence", async () => {
  const response = await postJson({
    question: "主轴承润滑脂取样和内窥镜检查要求是什么？",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
  });

  assert.equal(response.ok, true);
  assert.ok(response.data.answer.citations.length > 0);
  assert.equal(response.data.answer.citations[0].docId, "KB-MB-PROC-004");
  assert.notEqual(response.data.answer.answer.confidencePercent, 87);
  assert.deepEqual(response.data.answer.retrieval.evidenceIds, []);
  assert.deepEqual(response.data.answer.retrieval.supportingFailureCaseIds, []);
  assert.doesNotMatch(response.data.answer.answer.conclusion, /主轴承早期退化/);
  assert.ok(
    response.data.answer.answer.findings.every(
      (finding) => finding.citationIds.length > 0 && finding.passageIds.length > 0,
    ),
  );
});

test("assistant API rejects malformed bodies, unknown scope, and mission/turbine mismatch", async () => {
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
    [{ question: "test", turbineId: "WT-999" }, 422, "TURBINE_NOT_FOUND"],
    [{ question: "test", missionId: "MISSION-2099-9999" }, 422, "MISSION_NOT_FOUND"],
    [
      { question: "test", turbineId: "WT-023", missionId: "MISSION-2026-0824" },
      422,
      "MISSION_TURBINE_MISMATCH",
    ],
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

test("assistant supports a second valid scope and returns no invented result without matched body evidence", async () => {
  const gearbox = await postJson({
    question: "WT-041 齿轮箱磨粒和齿面点蚀有什么证据？",
    turbineId: "WT-041",
    missionId: "MISSION-2026-0824",
  });
  assert.equal(gearbox.ok, true);
  assert.ok(gearbox.data.answer.citations.length > 0);
  assert.equal(gearbox.data.answer.citations[0].docId, "KB-GEARBOX-CASE-022");
  assert.match(gearbox.data.answer.citations[0].quote, /WT-041.*磨粒.*齿面点蚀/);

  const noEvidence = await postJson({
    question: "量子引力与黑洞信息悖论",
    turbineId: "WT-041",
    missionId: "MISSION-2026-0824",
  });
  assert.equal(noEvidence.ok, true);
  assert.equal(noEvidence.data.answer.citations.length, 0);
  assert.equal(noEvidence.data.answer.answer.confidencePercent, 0);
  assert.equal(noEvidence.data.answer.answer.findings.length, 0);
  assert.match(noEvidence.data.answer.answer.conclusion, /证据不足/);
  assert.doesNotMatch(JSON.stringify(noEvidence), /主轴承早期退化/);
});
