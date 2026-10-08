import assert from "node:assert/strict";
import test from "node:test";

import {
  knowledgeIngestionLabel,
  knowledgePageRegions,
  knowledgeSourceLocation,
  verifiedSourceHref,
} from "../lib/knowledge-source.ts";

test("source labels distinguish verified PDF pages from native text and historical unknowns", () => {
  assert.equal(knowledgeSourceLocation({ page_number: 7, native_locator: {} }), "第 7 页");
  assert.equal(
    knowledgeSourceLocation({
      page_number: null,
      native_locator: { kind: "text_lines", line_start: 4, line_end: 8 },
    }),
    "第 4–8 行",
  );
  assert.equal(
    knowledgeSourceLocation({
      page_number: null,
      native_locator: { kind: "docx_table_cell", row_index: 1, column_index: 0 },
    }),
    "表格 · 第 2 行 / 第 1 列",
  );
  assert.equal(
    knowledgeSourceLocation({ page_number: null, native_locator: { kind: "database_text" } }),
    "正文位置未标注",
  );
});

test("PDF navigation preserves a signed source URL and rejects executable protocols", () => {
  const original =
    "https://objects.example/source.pdf?X-Amz-Signature=synthetic-signature&response-content-type=application%2Fpdf";
  const result = new URL(verifiedSourceHref(original, 7));
  assert.equal(result.hash, "#page=7");
  assert.equal(result.search, new URL(original).search);
  assert.equal(new URL(verifiedSourceHref(original, null)).hash, "");
  assert.throws(() => verifiedSourceHref("javascript:alert(1)", null));
  assert.throws(() => verifiedSourceHref("data:text/html,test", null));
});

test("background parsing states do not appear indexed or healthy", () => {
  assert.equal(knowledgeIngestionLabel("pending_parse"), "等待 PDF 解析");
  assert.equal(knowledgeIngestionLabel("parsing"), "正在解析 PDF");
  assert.equal(knowledgeIngestionLabel("parse_failed"), "PDF 解析失败");
  assert.equal(knowledgeIngestionLabel("failed"), "索引失败");
});

test("page-region display uses actual source geometry and refuses cross-page or invalid boxes", () => {
  const passage = {
    page_number: 2,
    native_locator: {
      kind: "docling_pdf_item",
      regions: [
        {
          page_number: 2,
          page_width: 650,
          page_height: 850,
          coordinate_space: "pdf_points_top_left",
          bbox: [20, 40, 200, 80],
        },
      ],
    },
  };
  assert.deepEqual(knowledgePageRegions(passage), [
    {
      pageNumber: 2,
      width: 650,
      height: 850,
      bbox: [20, 40, 200, 80],
    },
  ]);
  const otherPage = structuredClone(passage);
  otherPage.native_locator.regions[0].page_number = 1;
  assert.deepEqual(knowledgePageRegions(otherPage), []);
  const outside = structuredClone(passage);
  outside.native_locator.regions[0].bbox = [20, 40, 700, 80];
  assert.deepEqual(knowledgePageRegions(outside), []);
  const unknownUnits = structuredClone(passage);
  unknownUnits.native_locator.regions[0].coordinate_space = "pixels";
  assert.deepEqual(knowledgePageRegions(unknownUnits), []);
  assert.deepEqual(knowledgePageRegions({ page_number: null, native_locator: {} }), []);
});
