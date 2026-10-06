from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from importlib.metadata import version
from io import BytesIO
from typing import Any
from zipfile import ZipFile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

MAX_TEXT_CHARACTERS = 4_000_000
MAX_PASSAGES = 512
PASSAGE_CHARACTERS = 8_000
PARSER_CONTRACT = "openvigil.native-passages.v1"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class ParsedPassage:
    ordinal: int
    text: str
    text_sha256: str
    char_start: int
    char_end: int
    native_locator: dict[str, Any]
    parser_version: str
    page_number: int | None = None
    section: str | None = None


@dataclass(frozen=True)
class ParsedKnowledge:
    body: str
    passages: tuple[ParsedPassage, ...]
    source_page_count: int | None = None


def _normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\x00", "").splitlines()).strip()


def _from_units(
    units: list[tuple[str, dict[str, Any], int | None, str | None]], parser_version: str
) -> ParsedKnowledge:
    bodies: list[str] = []
    passages: list[ParsedPassage] = []
    offset = 0
    for raw_text, locator, page_number, section in units:
        text = _normalize(raw_text)
        if not text:
            continue
        if bodies:
            offset += 2
        if offset + len(text) > MAX_TEXT_CHARACTERS:
            raise ValueError("knowledge document extracted text exceeds the indexing limit")
        bodies.append(text)
        for start in range(0, len(text), PASSAGE_CHARACTERS):
            piece = text[start : start + PASSAGE_CHARACTERS]
            if len(passages) >= MAX_PASSAGES:
                raise ValueError("knowledge document exceeds the maximum number of passages")
            passages.append(
                ParsedPassage(
                    ordinal=len(passages),
                    text=piece,
                    text_sha256=hashlib.sha256(piece.encode()).hexdigest(),
                    char_start=offset + start,
                    char_end=offset + start + len(piece),
                    native_locator={
                        **locator,
                        "unit_char_start": start,
                        "unit_char_end": start + len(piece),
                        "coordinate_space": "normalized_extracted_text",
                        "bbox": None,
                    },
                    page_number=page_number,
                    section=section,
                    parser_version=parser_version,
                )
            )
        offset += len(text)
    if not passages:
        raise ValueError("knowledge document extraction produced no text; OCR may be required")
    return ParsedKnowledge("\n\n".join(bodies), tuple(passages))


def parse_legacy_body(body: str) -> ParsedKnowledge:
    """Historical database text has no verified file/page correspondence."""
    if not body.strip() or len(body) > MAX_TEXT_CHARACTERS:
        raise ValueError("historical knowledge text is empty or exceeds the indexing limit")
    if len(body) > MAX_PASSAGES * PASSAGE_CHARACTERS:
        raise ValueError("historical knowledge text exceeds the passage limit")
    pieces = tuple(
        ParsedPassage(
            ordinal=start // PASSAGE_CHARACTERS,
            text=body[start : start + PASSAGE_CHARACTERS],
            text_sha256=hashlib.sha256(
                body[start : start + PASSAGE_CHARACTERS].encode()
            ).hexdigest(),
            char_start=start,
            char_end=min(len(body), start + PASSAGE_CHARACTERS),
            native_locator={"kind": "database_text", "source_verified": False, "bbox": None},
            parser_version=f"{PARSER_CONTRACT};legacy-database-text",
        )
        for start in range(0, len(body), PASSAGE_CHARACTERS)
    )
    return ParsedKnowledge(body, pieces)


def _parse(content: bytes, content_type: str) -> ParsedKnowledge:
    units: list[tuple[str, dict[str, Any], int | None, str | None]] = []
    parser_version = PARSER_CONTRACT
    source_page_count = None
    try:
        if content_type in {"text/plain", "text/markdown"}:
            lines = content.decode("utf-8-sig").splitlines()
            section = None
            block: list[str] = []
            first_line = 1
            for index, line in enumerate(lines, start=1):
                heading = (
                    re.match(r"^#{1,6}\s+(.+)$", line) if content_type == "text/markdown" else None
                )
                if (not line.strip() or heading) and block:
                    units.append(
                        (
                            "\n".join(block),
                            {"kind": "text_lines", "line_start": first_line, "line_end": index - 1},
                            None,
                            section,
                        )
                    )
                    block = []
                if heading:
                    section = heading.group(1).strip()[:320]
                if line.strip():
                    if not block:
                        first_line = index
                    block.append(line)
            if block:
                units.append(
                    (
                        "\n".join(block),
                        {"kind": "text_lines", "line_start": first_line, "line_end": len(lines)},
                        None,
                        section,
                    )
                )
        elif content_type == "application/pdf":
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError("encrypted PDF knowledge documents are not accepted")
            if len(reader.pages) > 2_000:
                raise ValueError("knowledge PDF exceeds the page limit")
            source_page_count = len(reader.pages)
            parser_version += f";pypdf={version('pypdf')}"
            for number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                units.append(
                    (text, {"kind": "pdf_page", "page_number": number, "ocr": False}, number, None)
                )
        elif content_type == DOCX_TYPE:
            with ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if (
                    len(entries) > 10_000
                    or sum(entry.file_size for entry in entries) > 200 * 1024 * 1024
                ):
                    raise ValueError("knowledge DOCX expanded content exceeds the parser limit")
            document = Document(BytesIO(content))
            parser_version += f";python-docx={version('python-docx')}"
            section = None
            for item_index, item in enumerate(document.iter_inner_content()):
                if isinstance(item, Paragraph):
                    if item.style is not None and item.style.name.startswith("Heading"):
                        section = item.text.strip()[:320] or None
                    units.append(
                        (
                            item.text,
                            {"kind": "docx_paragraph", "body_item_index": item_index},
                            None,
                            section,
                        )
                    )
                elif isinstance(item, Table):
                    for row_index, row in enumerate(item.rows):
                        # Merged cells are stored once, with their actual grid coordinates.
                        seen_cells: set[int] = set()
                        for column_index, cell in enumerate(row.cells):
                            identity = id(cell._tc)
                            if identity in seen_cells:
                                continue
                            seen_cells.add(identity)
                            units.append(
                                (
                                    cell.text,
                                    {
                                        "kind": "docx_table_cell",
                                        "body_item_index": item_index,
                                        "row_index": row_index,
                                        "column_index": column_index,
                                    },
                                    None,
                                    section,
                                )
                            )
        else:
            raise ValueError("knowledge document content type is not supported")
        result = _from_units(units, parser_version)
        return ParsedKnowledge(result.body, result.passages, source_page_count)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("knowledge document could not be parsed") from exc


async def parse_knowledge_content(content: bytes, content_type: str) -> ParsedKnowledge:
    return await asyncio.to_thread(_parse, content, content_type)
