"""Dedicated Docling entrypoint. Input is one JSON header followed by PDF bytes."""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
from importlib import import_module
from importlib.metadata import version
from io import BytesIO
from math import isfinite
from pathlib import Path
from typing import Any

from windops_backend.document_parse_contract import (
    MAX_DOCUMENT_PAGES,
    MAX_INPUT_BYTES,
    MAX_PASSAGES,
    MAX_TEXT_CHARACTERS,
    PARSE_CONTRACT,
    PASSAGE_CHARACTERS,
    DocumentParsePiece,
    DocumentParseResult,
)
from windops_backend.document_parse_identity import observed_parser_versions, parser_code_identity
from windops_backend.document_parse_models import verify_model_bundle


def _source_regions(item: Any, document: Any) -> list[dict[str, Any]]:
    regions = []
    for provenance in item.prov:
        page = document.pages[provenance.page_no]
        bbox = provenance.bbox.to_top_left_origin(page_height=page.size.height)
        regions.append(
            {
                "page_number": provenance.page_no,
                "bbox": [bbox.l, bbox.t, bbox.r, bbox.b],
                "page_width": page.size.width,
                "page_height": page.size.height,
                "coordinate_space": "pdf_points_top_left",
            }
        )
    return regions


def _document_units(document: Any) -> list[tuple[str, dict[str, Any], int, str | None]]:
    units: list[tuple[str, dict[str, Any], int, str | None]] = []
    section = None
    for item, _level in document.iterate_items():
        label = item.label.value
        if not getattr(item, "prov", None):
            continue
        regions = _source_regions(item, document)
        pages = {region["page_number"] for region in regions}
        locator = {
            "kind": "docling_pdf_item",
            "item_ref": item.self_ref,
            "label": label,
            "regions": regions,
            "ocr_mode": "automatic",
            "requires_numeric_review": True,
            "text_coordinate_space": "normalized_extracted_text",
        }
        if label == "table":
            # A cross-page table needs a per-cell page mapping; never guess it.
            if len(pages) != 1:
                raise ValueError("cross-page table cell locations require explicit verification")
            page_number = next(iter(pages))
            for cell in item.data.table_cells:
                if cell.text.strip():
                    units.append(
                        (
                            cell.text,
                            {
                                **locator,
                                "table_cell": {
                                    "row_start": cell.start_row_offset_idx,
                                    "row_end": cell.end_row_offset_idx,
                                    "column_start": cell.start_col_offset_idx,
                                    "column_end": cell.end_col_offset_idx,
                                    "column_header": cell.column_header,
                                    "row_header": cell.row_header,
                                },
                                "location_precision": "table_region",
                            },
                            page_number,
                            section,
                        )
                    )
        elif hasattr(item, "text") and item.text.strip():
            if len(pages) != 1:
                raise ValueError("cross-page text locations require explicit verification")
            if label == "section_header":
                section = item.text.strip()[:320]
            units.append((item.text, locator, next(iter(pages)), section))
        if len(units) > MAX_PASSAGES:
            raise ValueError("document parser exceeded the passage limit")
    return units


def _assemble(
    document: Any, *, source_sha256: str, model_manifest_sha256: str
) -> DocumentParseResult:
    parser_version = ";".join(
        [
            PARSE_CONTRACT,
            f"docling-slim={version('docling-slim')}",
            f"core={version('docling-core')}",
            f"rapidocr={version('rapidocr')}",
        ]
    )
    parts: list[str] = []
    pieces: list[DocumentParsePiece] = []
    offset = 0
    for raw_text, locator, page_number, section in _document_units(document):
        text = "\n".join(
            line.rstrip() for line in raw_text.replace("\x00", "").splitlines()
        ).strip()
        if not text:
            continue
        if parts:
            offset += 2
        if offset + len(text) > MAX_TEXT_CHARACTERS:
            raise ValueError("document parser exceeded the extracted text limit")
        parts.append(text)
        for start in range(0, len(text), PASSAGE_CHARACTERS):
            if len(pieces) >= MAX_PASSAGES:
                raise ValueError("document parser exceeded the passage limit")
            piece = text[start : start + PASSAGE_CHARACTERS]
            pieces.append(
                DocumentParsePiece(
                    ordinal=len(pieces),
                    text=piece,
                    text_sha256=hashlib.sha256(piece.encode()).hexdigest(),
                    char_start=offset + start,
                    char_end=offset + start + len(piece),
                    native_locator={
                        **locator,
                        "unit_char_start": start,
                        "unit_char_end": start + len(piece),
                    },
                    parser_version=parser_version,
                    page_number=page_number,
                    section=section,
                )
            )
        offset += len(text)
    return DocumentParseResult(
        contract=PARSE_CONTRACT,
        source_sha256=source_sha256,
        model_manifest_sha256=model_manifest_sha256,
        execution_code_sha256=parser_code_identity(),
        library_versions=observed_parser_versions(),
        body="\n\n".join(parts),
        passages=pieces,
        source_page_count=len(document.pages),
    )


def convert_pdf(
    content: bytes, *, models_path: Path, model_manifest_sha256: str
) -> DocumentParseResult:
    if not content or len(content) > MAX_INPUT_BYTES or not content.startswith(b"%PDF-"):
        raise ValueError("document parser requires a bounded PDF artifact")
    verify_model_bundle(models_path, model_manifest_sha256)
    observed_parser_versions()
    pdf_reader = import_module("pypdf").PdfReader(BytesIO(content))
    if pdf_reader.is_encrypted:
        raise ValueError("encrypted PDF knowledge artifacts are not accepted")
    if not 1 <= len(pdf_reader.pages) <= MAX_DOCUMENT_PAGES:
        raise ValueError("knowledge PDF exceeds the independent parser page limit")
    for page in pdf_reader.pages:
        user_unit = float(page.get("/UserUnit", 1))
        width = float(page.mediabox.width) * user_unit
        height = float(page.mediabox.height) * user_unit
        if (
            not isfinite(user_unit)
            or user_unit <= 0
            or not isfinite(width)
            or not isfinite(height)
            or not 0 < width <= 2000
            or not 0 < height <= 2000
        ):
            raise ValueError("knowledge PDF page exceeds the bounded rendering dimensions")
    if version("docling-slim") != "2.133.0":
        raise ValueError("document parser package differs from the pinned reference")
    # These imports occur only in this dedicated process and optional runtime.
    base = import_module("docling.datamodel.base_models")
    options = import_module("docling.datamodel.pipeline_options")
    accelerator = import_module("docling.datamodel.accelerator_options")
    converters = import_module("docling.document_converter")
    pipeline_options = options.PdfPipelineOptions(
        artifacts_path=models_path,
        do_ocr=True,
        do_table_structure=True,
        enable_remote_services=False,
        allow_external_plugins=False,
        accelerator_options=accelerator.AcceleratorOptions(
            device=accelerator.AcceleratorDevice.CPU, num_threads=1
        ),
        ocr_options=options.RapidOcrOptions(
            lang=["ch"],
            backend="onnxruntime",
            rapidocr_params={
                "EngineConfig.onnxruntime.intra_op_num_threads": 1,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            },
        ),
        document_timeout=150,
        ocr_batch_size=1,
        layout_batch_size=1,
        table_batch_size=1,
    )
    converter = converters.DocumentConverter(
        allowed_formats=[base.InputFormat.PDF],
        format_options={
            base.InputFormat.PDF: converters.PdfFormatOption(pipeline_options=pipeline_options)
        },
    )
    result = converter.convert(
        base.DocumentStream(name="source.pdf", stream=BytesIO(content)),
        max_num_pages=MAX_DOCUMENT_PAGES,
        max_file_size=MAX_INPUT_BYTES,
        raises_on_error=True,
    )
    if result.status != base.ConversionStatus.SUCCESS:
        raise ValueError("document parser did not complete all pages")
    if set(result.document.pages) != set(range(1, len(pdf_reader.pages) + 1)):
        raise ValueError("document parser omitted or renumbered source pages")
    return _assemble(
        result.document,
        source_sha256=hashlib.sha256(content).hexdigest(),
        model_manifest_sha256=model_manifest_sha256,
    )


def main() -> int:
    try:
        raw_header = sys.stdin.buffer.readline(16 * 1024 + 1)
        if len(raw_header) > 16 * 1024 or not raw_header.endswith(b"\n"):
            raise ValueError("document parser header exceeded its limit")
        header = json.loads(raw_header)
        if not isinstance(header, dict) or set(header) != {
            "source_sha256",
            "models_path",
            "model_manifest_sha256",
        }:
            raise ValueError("document parser header is invalid")
        content = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if hashlib.sha256(content).hexdigest() != header["source_sha256"]:
            raise ValueError("document parser input hash mismatch")
        # Third-party progress text must not corrupt the machine-readable wire.
        with contextlib.redirect_stdout(sys.stderr):
            result = convert_pdf(
                content,
                models_path=Path(header["models_path"]),
                model_manifest_sha256=header["model_manifest_sha256"],
            )
        sys.stdout.write(result.model_dump_json())
        return 0
    except Exception as exc:
        # Source bytes and exception details never leave the isolated process.
        sys.stderr.write(f"document parser failed: {type(exc).__name__}\n")
        sys.stdout.write(
            json.dumps(
                {
                    "error_code": "document_parser_failed",
                    "failure_type": type(exc).__name__,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
