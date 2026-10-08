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

export function knowledgeIngestionLabel(status?: string): string {
  switch (status) {
    case "indexed":
      return "已索引";
    case "pending_parse":
      return "等待 PDF 解析";
    case "parsing":
      return "正在解析 PDF";
    case "parse_failed":
      return "PDF 解析失败";
    case "failed":
      return "索引失败";
    default:
      return "等待索引";
  }
}

export interface KnowledgePageRegion {
  readonly pageNumber: number;
  readonly width: number;
  readonly height: number;
  readonly bbox: readonly [number, number, number, number];
}

export function knowledgePageRegions(
  passage: NativeKnowledgePassage,
): readonly KnowledgePageRegion[] {
  const locator = passage.native_locator;
  if (locator.kind !== "docling_pdf_item" || !Array.isArray(locator.regions)) return [];
  if (locator.regions.length === 0 || locator.regions.length > 200) return [];
  const regions: KnowledgePageRegion[] = [];
  for (const raw of locator.regions) {
    if (typeof raw !== "object" || raw === null) return [];
    const value = raw as Record<string, unknown>;
    const bbox = value.bbox;
    const width = value.page_width;
    const height = value.page_height;
    const page = value.page_number;
    if (
      value.coordinate_space !== "pdf_points_top_left" ||
      page !== passage.page_number ||
      typeof page !== "number" ||
      !Number.isInteger(page) ||
      page < 1 ||
      typeof width !== "number" ||
      !Number.isFinite(width) ||
      width <= 0 ||
      width > 14400 ||
      typeof height !== "number" ||
      !Number.isFinite(height) ||
      height <= 0 ||
      height > 14400 ||
      !Array.isArray(bbox) ||
      bbox.length !== 4 ||
      !bbox.every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate))
    )
      return [];
    const [left, top, right, bottom] = bbox as [number, number, number, number];
    if (!(
      0 <= left &&
      left < right &&
      right <= width &&
      0 <= top &&
      top < bottom &&
      bottom <= height
    ))
      return [];
    regions.push({ pageNumber: page, width, height, bbox: [left, top, right, bottom] });
  }
  return regions;
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
