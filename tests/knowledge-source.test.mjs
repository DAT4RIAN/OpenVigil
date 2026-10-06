import assert from "node:assert/strict";
import test from "node:test";

import { knowledgeSourceLocation, verifiedSourceHref } from "../lib/knowledge-source.ts";

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
