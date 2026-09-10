import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("report-center-test", `${process.pid}-${Date.now()}`);
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

async function jsonRequest(path, expectedStatus = 200) {
  const response = await request(path, { headers: { accept: "application/json" } });
  assert.equal(response.status, expectedStatus, `${path} returned ${response.status}`);
  assert.match(response.headers.get("content-type") ?? "", /^application\/json\b/i);
  assert.equal(response.headers.get("cache-control"), "no-store");
  return response.json();
}

function parseStoredZip(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const decoder = new TextDecoder();
  const entries = new Map();
  let offset = 0;
  while (offset + 4 <= bytes.byteLength && view.getUint32(offset, true) === 0x04034b50) {
    const compressedSize = view.getUint32(offset + 18, true);
    const nameLength = view.getUint16(offset + 26, true);
    const extraLength = view.getUint16(offset + 28, true);
    const nameStart = offset + 30;
    const dataStart = nameStart + nameLength + extraLength;
    const name = decoder.decode(bytes.slice(nameStart, nameStart + nameLength));
    entries.set(name, bytes.slice(dataStart, dataStart + compressedSize));
    offset = dataStart + compressedSize;
  }
  return { entries, centralOffset: offset };
}

test("报告中心渲染六类受控报告", async () => {
  const response = await request("/reports", { headers: { accept: "text/html" } });
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /报告中心/);
  assert.match(html, /运营日报/);
  assert.match(html, /告警分析/);
  assert.match(html, /AI 诊断/);
  assert.match(html, /维护报告/);
  assert.match(html, /资产健康/);
  assert.match(html, /风场周报/);
  assert.match(html, /PDF 1\.4/);
  assert.match(html, /DOCX OOXML/);
});

test("report catalog exposes six deterministic fixture-backed documents with workflow overlay", async () => {
  const catalog = await jsonRequest("/api/reports");
  assert.equal(catalog.ok, true);
  assert.equal(catalog.error, null);
  assert.equal(catalog.data.reports.length, 6);
  assert.equal(catalog.meta.count, 6);
  assert.equal(catalog.meta.total, 6);
  assert.equal(catalog.meta.catalogTotal, 6);
  assert.equal(catalog.meta.deterministic, true);
  assert.equal(catalog.meta.source, "fixtures-plus-server-workflow");
  assert.deepEqual(
    new Set(catalog.data.reports.map((report) => report.type)),
    new Set([
      "daily-operations",
      "alarm-analysis",
      "ai-diagnosis",
      "maintenance",
      "asset-health",
      "weekly-wind-farm",
    ]),
  );

  for (const report of catalog.data.reports) {
    assert.equal(report.status, "ready");
    assert.equal(report.workflow.turbineId, "WT-023");
    assert.equal(report.workflow.revision, catalog.meta.workflowRevision);
    assert.equal(report.metrics.length, 4);
    assert.ok(report.sections.length >= 2);
    assert.ok(report.linkedEntityIds.length >= 3);
  }

  const diagnosis = catalog.data.reports.find((report) => report.type === "ai-diagnosis");
  assert.ok(diagnosis);
  assert.match(diagnosis.highlight, /置信度为 87%/);
  assert.ok(diagnosis.linkedEntityIds.includes("MISSION-2026-0823"));
  assert.ok(diagnosis.linkedEntityIds.includes("DECISION-2026-0823"));
});

test("report catalog supports exact type, period, search, sort, and pagination filters", async () => {
  const alarm = await jsonRequest("/api/reports?type=alarm-analysis&period=daily&q=WT-023");
  assert.equal(alarm.meta.total, 1);
  assert.equal(alarm.data.reports[0].type, "alarm-analysis");

  const weekly = await jsonRequest("/api/reports?period=weekly");
  assert.equal(weekly.meta.total, 1);
  assert.equal(weekly.data.reports[0].type, "weekly-wind-farm");

  const page = await jsonRequest("/api/reports?sort=title&order=asc&page=2&pageSize=2");
  assert.equal(page.meta.count, 2);
  assert.equal(page.meta.page, 2);
  assert.equal(page.meta.pageSize, 2);
  assert.equal(page.meta.totalPages, 3);

  const detail = await jsonRequest(`/api/reports/${alarm.data.reports[0].id}`);
  assert.equal(detail.ok, true);
  assert.deepEqual(detail.data.report, alarm.data.reports[0]);
});

test("report APIs reject unsupported parameters and malformed filters with one error envelope", async () => {
  const cases = [
    ["/api/reports?debug=true", "UNKNOWN_PARAMETERS", 400],
    ["/api/reports?type=secret", "INVALID_REPORT_TYPE", 400],
    ["/api/reports?period=quarterly", "INVALID_REPORT_PERIOD", 400],
    ["/api/reports?sort=score", "INVALID_SORT", 400],
    ["/api/reports?order=sideways", "INVALID_SORT_ORDER", 400],
    ["/api/reports?page=0", "INVALID_PAGINATION", 400],
    ["/api/reports?pageSize=25", "INVALID_PAGINATION", 400],
    ["/api/reports/RPT-UNKNOWN", "REPORT_NOT_FOUND", 404],
    ["/api/reports/RPT-DAILY-20260813?debug=true", "UNKNOWN_PARAMETERS", 400],
    ["/api/reports/RPT-DAILY-20260813/export", "INVALID_EXPORT_FORMAT", 400],
    ["/api/reports/RPT-DAILY-20260813/export?format=csv", "INVALID_EXPORT_FORMAT", 400],
    ["/api/reports/RPT-DAILY-20260813/export?format=pdf&format=docx", "INVALID_EXPORT_FORMAT", 400],
    ["/api/reports/RPT-DAILY-20260813/export?format=pdf&debug=true", "UNKNOWN_PARAMETERS", 400],
    [
      "/api/reports/RPT-DAILY-20260813/export?format=pdf&expectedRevision=999",
      "REPORT_REVISION_CONFLICT",
      409,
    ],
    ["/api/reports/RPT-UNKNOWN/export?format=pdf&expectedRevision=0", "REPORT_NOT_FOUND", 404],
  ];

  for (const [path, code, status] of cases) {
    const body = await jsonRequest(path, status);
    assert.equal(body.ok, false);
    assert.equal(body.data, null);
    assert.equal(body.error.code, code);
    assert.equal(body.meta.deterministic, true);
  }
});

test("PDF export returns a verifiable PDF 1.4 file with a valid xref pointer", async () => {
  const response = await request(
    "/api/reports/RPT-AI-WT023-20260813/export?format=pdf&expectedRevision=0",
  );
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("content-type"), "application/pdf");
  assert.match(response.headers.get("content-disposition") ?? "", /\.pdf"$/);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  assert.equal(response.headers.get("x-windops-report-id"), "RPT-AI-WT023-20260813");

  const bytes = new Uint8Array(await response.arrayBuffer());
  assert.equal(response.headers.get("content-length"), bytes.byteLength.toString());
  assert.ok(bytes.byteLength > 2_000);
  assert.deepEqual([...bytes.slice(0, 5)], [0x25, 0x50, 0x44, 0x46, 0x2d]);
  const text = new TextDecoder("latin1").decode(bytes);
  assert.match(text, /^%PDF-1\.4/);
  assert.match(text, /\/Encoding \/UniGB-UCS2-H/);
  assert.match(text, /\/BaseFont \/STSong-Light/);
  assert.match(text, /0041004900208BCA65AD62A5544A/);
  assert.match(text, /4E3B8F74627F/);
  assert.match(text, /xref\n0 \d+/);
  assert.match(text, /%%EOF\n$/);
  const xrefMatch = text.match(/startxref\n(\d+)\n%%EOF/);
  assert.ok(xrefMatch);
  const xrefOffset = Number(xrefMatch[1]);
  assert.equal(text.slice(xrefOffset, xrefOffset + 4), "xref");
});

test("DOCX export returns a real ZIP package with required OOXML parts", async () => {
  const response = await request(
    "/api/reports/RPT-MAINT-20260813/export?format=docx&expectedRevision=0",
  );
  assert.equal(response.status, 200);
  assert.equal(
    response.headers.get("content-type"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  );
  assert.match(response.headers.get("content-disposition") ?? "", /\.docx"$/);
  assert.equal(response.headers.get("x-windops-report-id"), "RPT-MAINT-20260813");

  const bytes = new Uint8Array(await response.arrayBuffer());
  assert.equal(response.headers.get("content-length"), bytes.byteLength.toString());
  assert.ok(bytes.byteLength > 3_000);
  assert.deepEqual([...bytes.slice(0, 4)], [0x50, 0x4b, 0x03, 0x04]);
  assert.deepEqual([...bytes.slice(-22, -18)], [0x50, 0x4b, 0x05, 0x06]);

  const { entries, centralOffset } = parseStoredZip(bytes);
  assert.deepEqual(
    new Set(entries.keys()),
    new Set(["[Content_Types].xml", "_rels/.rels", "docProps/core.xml", "word/document.xml"]),
  );
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  assert.equal(view.getUint32(centralOffset, true), 0x02014b50);
  const documentXml = new TextDecoder().decode(entries.get("word/document.xml"));
  const contentTypes = new TextDecoder().decode(entries.get("[Content_Types].xml"));
  assert.match(documentXml, /^<\?xml/);
  assert.match(documentXml, /<w:document/);
  assert.match(documentXml, /维护报告/);
  assert.match(documentXml, /工作流追溯.*WT-023 Mission=/s);
  assert.match(contentTypes, /wordprocessingml\.document\.main\+xml/);
});
