import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("diagnosis-center-test", `${process.pid}-${Date.now()}`);
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

test("diagnosis API returns a deterministic read-only 64 turbine differential diagnosis fixture", async () => {
  const [first, repeated] = await Promise.all([
    fetchJson("/api/diagnoses"),
    fetchJson("/api/diagnoses"),
  ]);

  assert.deepEqual(repeated, first);
  assert.equal(first.meta.total, 64);
  assert.equal(first.meta.filteredTotal, 64);
  assert.equal(first.meta.count, 64);
  assert.equal(first.meta.model.mode, "deterministic-diagnostic-fixture");
  assert.equal(first.meta.model.deterministic, true);
  assert.equal(first.meta.model.readOnly, true);
  assert.equal(first.meta.model.realInference, false);
  assert.equal(first.meta.model.publicTraceOnly, true);
  assert.equal(new Set(first.data.map((record) => record.turbineId)).size, 64);

  for (const record of first.data) {
    assert.equal(
      record.candidates.reduce((total, candidate) => total + candidate.probabilityPercent, 0),
      100,
    );
    assert.ok(record.candidates.every((candidate) => candidate.counterEvidence.length > 0));
    assert.ok(record.collaboration.every((step) => typeof step.publicOutput === "string"));
    assert.ok(
      record.citations.every((citation) => citation.deepLink && citation.href.startsWith("/")),
    );
  }
});

test("WT-023 diagnosis reflects the canonical under-review D1 workflow without premature execution", async () => {
  const body = await fetchJson("/api/diagnoses?turbineId=wt-023");
  assert.equal(body.meta.count, 1);
  const featured = body.data[0];

  assert.equal(featured.turbineId, "WT-023");
  assert.equal(featured.status, "awaiting-review");
  assert.equal(featured.missionId, "MISSION-2026-0823");
  assert.equal(featured.candidates[0].faultMode, "主轴承外圈早期退化");
  assert.equal(featured.candidates[0].probabilityPercent, 87);
  assert.equal(featured.gate.state, "locked");
  assert.equal(featured.gate.decisionStatus, "under-review");
  assert.equal(featured.gate.workOrderStatus, "draft");
  assert.match(featured.gate.explanation, /草稿|人工复核/);
  assert.ok(featured.gate.blockedActions.some((action) => /自动|执行/.test(action)));
  assert.equal(
    featured.collaboration.find((step) => step.id === "DX-023-STEP-05").status,
    "waiting-human",
  );

  const serialized = JSON.stringify(featured);
  assert.doesNotMatch(serialized, /chain.of.thought|思维链|隐藏推理|internal reasoning/i);
  assert.doesNotMatch(serialized, /已批准|已执行|已完成现场/);
});

test("diagnosis API applies strict search, status, risk, turbine, sort, and pagination contracts", async () => {
  const [searched, reviewed, highRisk, turbine, confidence, finalPage] = await Promise.all([
    fetchJson(`/api/diagnoses?q=${encodeURIComponent("主轴承")}`),
    fetchJson("/api/diagnoses?status=awaiting-review"),
    fetchJson("/api/diagnoses?risk=high"),
    fetchJson("/api/diagnoses?turbineId=WT-041"),
    fetchJson("/api/diagnoses?sort=confidence-desc&limit=8"),
    fetchJson("/api/diagnoses?offset=64&limit=8"),
  ]);

  assert.ok(searched.data.some((record) => record.turbineId === "WT-023"));
  assert.ok(reviewed.data.length > 0);
  assert.ok(reviewed.data.every((record) => record.status === "awaiting-review"));
  assert.ok(highRisk.data.length > 0);
  assert.ok(highRisk.data.every((record) => record.risk === "high"));
  assert.equal(turbine.meta.count, 1);
  assert.equal(turbine.data[0].turbineId, "WT-041");
  assert.ok(
    confidence.data.every(
      (record, index, data) =>
        index === 0 || data[index - 1].overallConfidencePercent >= record.overallConfidencePercent,
    ),
  );
  assert.equal(finalPage.meta.count, 0);
});

test("diagnosis API rejects unsupported filters and malformed parameters", async () => {
  const cases = [
    ["/api/diagnoses?unknown=true", "INVALID_QUERY_PARAMETER", 400],
    ["/api/diagnoses?status=approved", "INVALID_STATUS", 400],
    ["/api/diagnoses?risk=urgent", "INVALID_RISK", 400],
    ["/api/diagnoses?sort=random", "INVALID_SORT", 400],
    ["/api/diagnoses?turbineId=23", "INVALID_TURBINE_ID", 400],
    ["/api/diagnoses?turbineId=WT-999", "TURBINE_NOT_FOUND", 404],
    ["/api/diagnoses?offset=-1", "INVALID_PAGINATION", 400],
    ["/api/diagnoses?limit=65", "INVALID_PAGINATION", 400],
  ];

  for (const [path, code, status] of cases) {
    const body = await fetchJson(path, status);
    assert.equal(body.error.code, code);
  }
});

test("diagnosis center SSR renders anomaly intake, differential diagnosis, collaboration, evidence, and HITL boundaries", async () => {
  const response = await fetchRoute("/diagnosis", { accept: "text/html" });
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /智能诊断中心/);
  assert.match(html, /WT-023/);
  assert.match(html, /异常接入/);
  assert.match(html, /差分诊断/);
  assert.match(html, /主轴承外圈早期退化/);
  assert.match(html, /Agent 协作记录/);
  assert.match(html, /证据引用/);
  assert.match(html, /HITL 门禁锁定/);
  assert.match(html, /只读演示/);
  assert.match(html, /无真实推理/);
  assert.match(html, /查看现有 Mission|查看 WT-023 Mission/);
  assert.doesNotMatch(html, /chain.of.thought|思维链|隐藏推理|internal reasoning/i);
  assert.doesNotMatch(html, />启动诊断</);
});

test("diagnosis selection remains inside filtered records and clears detail for an empty result", async () => {
  const source = await import("node:fs/promises").then((fs) =>
    fs.readFile(new URL("../components/pages/diagnosis-center-page.tsx", import.meta.url), "utf8"),
  );

  assert.match(source, /const selected = records\.find\([\s\S]*?\?\? records\[0\] \?\? null;/);
  assert.doesNotMatch(source, /const selected\s*=\s*workflowRecords\.find/);
  assert.match(source, /if \(!selected \|\| selected\.turbineId === selectedId\) return;/);
  assert.match(source, /selected && topCandidate \? \(/);
  assert.match(source, /没有可显示的诊断详情/);
});
