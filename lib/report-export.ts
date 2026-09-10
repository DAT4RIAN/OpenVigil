import { reportToPlainText, type OpenVigilReport } from "./report-data";

export type ReportExportFormat = "pdf" | "docx";

export const reportExportMimeTypes: Readonly<Record<ReportExportFormat, string>> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

const encoder = new TextEncoder();

const concatBytes = (parts: readonly Uint8Array[]): Uint8Array => {
  const length = parts.reduce((sum, part) => sum + part.byteLength, 0);
  const output = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.byteLength;
  }
  return output;
};

const printableText = (value: string): string =>
  [...value]
    .filter((character) => {
      const codePoint = character.codePointAt(0)!;
      return codePoint >= 0x20 && codePoint !== 0x7f;
    })
    .join("")
    .replace(/\s+/g, " ")
    .trim();

const glyphWidth = (character: string): number => (character.codePointAt(0)! <= 0x7f ? 0.55 : 1);

const wrapLine = (value: string, width: number): readonly string[] => {
  const normalized = printableText(value);
  if (!normalized) return [""];
  const lines: string[] = [];
  let current = "";
  let currentWidth = 0;
  for (const character of normalized) {
    const nextWidth = glyphWidth(character);
    if (current && currentWidth + nextWidth > width) {
      lines.push(current.trimEnd());
      current = "";
      currentWidth = 0;
    }
    current += character;
    currentWidth += nextWidth;
  }
  if (current) lines.push(current);
  return lines;
};

/** Encode a PDF Type0/CID text string as UTF-16BE hexadecimal. */
const pdfUnicode = (value: string): string => {
  const normalized = printableText(value);
  let encoded = "";
  for (let index = 0; index < normalized.length; index += 1) {
    const codeUnit = normalized.charCodeAt(index);
    encoded += codeUnit.toString(16).padStart(4, "0").toUpperCase();
  }
  return `<${encoded || "0020"}>`;
};

/** Create a deterministic, self-contained PDF 1.4 document without a runtime dependency. */
export function createReportPdf(report: OpenVigilReport): Uint8Array {
  const wrapped = reportToPlainText(report).flatMap((line) => wrapLine(line, 94));
  const linesPerPage = 42;
  const pages = Array.from(
    { length: Math.max(1, Math.ceil(wrapped.length / linesPerPage)) },
    (_, index) => wrapped.slice(index * linesPerPage, (index + 1) * linesPerPage),
  );
  const fontId = 3 + pages.length * 2;
  const descendantFontId = fontId + 1;
  const objects: string[] = [];

  objects[0] = "<< /Type /Catalog /Pages 2 0 R >>";
  objects[1] = `<< /Type /Pages /Kids [${pages
    .map((_, index) => `${3 + index * 2} 0 R`)
    .join(" ")}] /Count ${pages.length} >>`;

  pages.forEach((pageLines, index) => {
    const pageId = 3 + index * 2;
    const contentId = pageId + 1;
    const commands = [
      "BT",
      "/F1 15 Tf",
      "0.10 0.24 0.27 rg",
      "50 790 Td",
      `${pdfUnicode(index === 0 ? report.title : `${report.title} - continued`)} Tj`,
      "/F1 9 Tf",
      "0.16 0.20 0.22 rg",
      "0 -24 Td",
      ...pageLines.map((line) => `${pdfUnicode(line || " ")} Tj\n0 -16 Td`),
      "ET",
      "BT /F1 8 Tf 0.38 0.42 0.44 rg 50 30 Td",
      `${pdfUnicode(`OpenVigil report ${report.id} | Page ${index + 1} of ${pages.length}`)} Tj ET`,
    ];
    const stream = commands.join("\n");
    const streamLength = encoder.encode(stream).byteLength;
    objects[pageId - 1] =
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] ` +
      `/Resources << /Font << /F1 ${fontId} 0 R >> >> /Contents ${contentId} 0 R >>`;
    objects[contentId - 1] = `<< /Length ${streamLength} >>\nstream\n${stream}\nendstream`;
  });
  objects[fontId - 1] =
    `<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H ` +
    `/DescendantFonts [${descendantFontId} 0 R] >>`;
  objects[descendantFontId - 1] =
    "<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light " +
    "/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> >>";

  const header = "%PDF-1.4\n%\u00e2\u00e3\u00cf\u00d3\n";
  let document = header;
  const offsets: number[] = [0];
  objects.forEach((object, index) => {
    offsets.push(encoder.encode(document).byteLength);
    document += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefOffset = encoder.encode(document).byteLength;
  const xref = [
    "xref",
    `0 ${objects.length + 1}`,
    "0000000000 65535 f ",
    ...offsets.slice(1).map((offset) => `${offset.toString().padStart(10, "0")} 00000 n `),
    "trailer",
    `<< /Size ${objects.length + 1} /Root 1 0 R >>`,
    "startxref",
    `${xrefOffset}`,
    "%%EOF",
    "",
  ].join("\n");
  return encoder.encode(document + xref);
}

const xmlEscape = (value: string): string =>
  value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");

let crcTable: Uint32Array | null = null;

const getCrcTable = (): Uint32Array => {
  if (crcTable) return crcTable;
  crcTable = Uint32Array.from({ length: 256 }, (_, index) => {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    return value >>> 0;
  });
  return crcTable;
};

const crc32 = (bytes: Uint8Array): number => {
  const table = getCrcTable();
  let crc = 0xffffffff;
  for (const byte of bytes) crc = table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
};

const littleEndian = (length: number, writes: (view: DataView) => void): Uint8Array => {
  const bytes = new Uint8Array(length);
  writes(new DataView(bytes.buffer));
  return bytes;
};

interface ZipEntry {
  readonly name: string;
  readonly nameBytes: Uint8Array;
  readonly data: Uint8Array;
  readonly crc: number;
  readonly offset: number;
}

const zipStored = (files: readonly { readonly name: string; readonly content: string }[]) => {
  const localParts: Uint8Array[] = [];
  const entries: ZipEntry[] = [];
  let offset = 0;
  const dosTime = (10 << 11) | (30 << 5);
  const dosDate = ((2026 - 1980) << 9) | (8 << 5) | 13;

  for (const file of files) {
    const nameBytes = encoder.encode(file.name);
    const data = encoder.encode(file.content);
    const checksum = crc32(data);
    const header = littleEndian(30, (view) => {
      view.setUint32(0, 0x04034b50, true);
      view.setUint16(4, 20, true);
      view.setUint16(6, 0x0800, true);
      view.setUint16(8, 0, true);
      view.setUint16(10, dosTime, true);
      view.setUint16(12, dosDate, true);
      view.setUint32(14, checksum, true);
      view.setUint32(18, data.byteLength, true);
      view.setUint32(22, data.byteLength, true);
      view.setUint16(26, nameBytes.byteLength, true);
      view.setUint16(28, 0, true);
    });
    localParts.push(header, nameBytes, data);
    entries.push({ name: file.name, nameBytes, data, crc: checksum, offset });
    offset += header.byteLength + nameBytes.byteLength + data.byteLength;
  }

  const centralOffset = offset;
  const centralParts: Uint8Array[] = [];
  for (const entry of entries) {
    const header = littleEndian(46, (view) => {
      view.setUint32(0, 0x02014b50, true);
      view.setUint16(4, 20, true);
      view.setUint16(6, 20, true);
      view.setUint16(8, 0x0800, true);
      view.setUint16(10, 0, true);
      view.setUint16(12, dosTime, true);
      view.setUint16(14, dosDate, true);
      view.setUint32(16, entry.crc, true);
      view.setUint32(20, entry.data.byteLength, true);
      view.setUint32(24, entry.data.byteLength, true);
      view.setUint16(28, entry.nameBytes.byteLength, true);
      view.setUint16(30, 0, true);
      view.setUint16(32, 0, true);
      view.setUint16(34, 0, true);
      view.setUint16(36, 0, true);
      view.setUint32(38, 0, true);
      view.setUint32(42, entry.offset, true);
    });
    centralParts.push(header, entry.nameBytes);
  }
  const central = concatBytes(centralParts);
  const end = littleEndian(22, (view) => {
    view.setUint32(0, 0x06054b50, true);
    view.setUint16(4, 0, true);
    view.setUint16(6, 0, true);
    view.setUint16(8, entries.length, true);
    view.setUint16(10, entries.length, true);
    view.setUint32(12, central.byteLength, true);
    view.setUint32(16, centralOffset, true);
    view.setUint16(20, 0, true);
  });
  return concatBytes([...localParts, central, end]);
};

const wordParagraph = (
  value: string,
  options?: { readonly bold?: boolean; readonly size?: number },
) => {
  const properties = [
    options?.bold ? "<w:b/>" : "",
    options?.size ? `<w:sz w:val="${options.size}"/>` : "",
  ].join("");
  return `<w:p><w:r>${properties ? `<w:rPr>${properties}</w:rPr>` : ""}<w:t xml:space="preserve">${xmlEscape(value || " ")}</w:t></w:r></w:p>`;
};

/** Create a minimal but standards-compliant DOCX package using stored ZIP entries. */
export function createReportDocx(report: OpenVigilReport): Uint8Array {
  const paragraphs = reportToPlainText(report).map((line, index) => {
    const isHeading =
      index === 0 ||
      line === "EXECUTIVE HIGHLIGHT" ||
      line === "KEY METRICS" ||
      line === "WORKFLOW TRACE" ||
      report.sections.some((section) => line === section.heading.toUpperCase());
    return wordParagraph(line, {
      bold: isHeading,
      size: index === 0 ? 32 : isHeading ? 24 : 20,
    });
  });
  const documentXml =
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
    `<w:body>${paragraphs.join("")}<w:sectPr>` +
    '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/>' +
    "</w:sectPr></w:body></w:document>";
  const contentTypes =
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>' +
    "</Types>";
  const relationships =
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>' +
    "</Relationships>";
  const createdAt = new Date(report.generatedAt).toISOString();
  const coreProperties =
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">' +
    `<dc:title>${xmlEscape(report.title)}</dc:title>` +
    "<dc:creator>OpenVigil Report Center</dc:creator>" +
    `<dc:subject>${xmlEscape(report.typeLabel)}</dc:subject>` +
    `<dcterms:created xsi:type="dcterms:W3CDTF">${createdAt}</dcterms:created>` +
    `<dcterms:modified xsi:type="dcterms:W3CDTF">${createdAt}</dcterms:modified>` +
    "</cp:coreProperties>";

  return zipStored([
    { name: "[Content_Types].xml", content: contentTypes },
    { name: "_rels/.rels", content: relationships },
    { name: "docProps/core.xml", content: coreProperties },
    { name: "word/document.xml", content: documentXml },
  ]);
}

export const reportExportFilename = (
  report: Pick<OpenVigilReport, "id">,
  format: ReportExportFormat,
): string => `${report.id.toLowerCase()}.${format}`;
