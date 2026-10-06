export interface NativeKnowledgePassage {
  readonly passage_id: string;
  readonly document_id: string;
  readonly document_version: string;
  readonly ordinal: number;
  readonly page_number: number | null;
  readonly section: string | null;
  readonly text: string;
  readonly source_sha256: string | null;
  readonly text_sha256: string;
  readonly native_locator: Readonly<Record<string, unknown>>;
}

export function knowledgeSourceLocation(
  passage: Pick<NativeKnowledgePassage, "page_number" | "native_locator">,
): string {
  if (passage.page_number !== null && passage.page_number > 0) {
    return `第 ${passage.page_number} 页`;
  }
  const locator = passage.native_locator;
  if (locator.kind === "text_lines" && typeof locator.line_start === "number") {
    const end = typeof locator.line_end === "number" ? locator.line_end : locator.line_start;
    return locator.line_start === end
      ? `第 ${locator.line_start} 行`
      : `第 ${locator.line_start}–${end} 行`;
  }
  if (locator.kind === "docx_table_cell") {
    const row = locator.row_index;
    const column = locator.column_index;
    if (typeof row === "number" && typeof column === "number") {
      return `表格 · 第 ${row + 1} 行 / 第 ${column + 1} 列`;
    }
  }
  if (locator.kind === "docx_paragraph" && typeof locator.body_item_index === "number") {
    return `正文块 ${locator.body_item_index + 1}`;
  }
  return "正文位置未标注";
}

export function verifiedSourceHref(url: string, page: number | null): string {
  const parsed = new URL(url);
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("原文下载地址不可用。请检查对象存储配置。");
  }
  if (page !== null && Number.isInteger(page) && page > 0) parsed.hash = `page=${page}`;
  return parsed.href;
}
