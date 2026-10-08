"""Dependency-light wire contract for the isolated document parser."""

from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PARSE_CONTRACT = "openvigil.document-parse.v1"
MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_BYTES = 24 * 1024 * 1024
MAX_DOCUMENT_PAGES = 200
MAX_TEXT_CHARACTERS = 4_000_000
MAX_PASSAGES = 512
PASSAGE_CHARACTERS = 8_000


class DocumentSourceRegion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    page_number: int = Field(ge=1, le=MAX_DOCUMENT_PAGES)
    bbox: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(min_length=4, max_length=4)
    page_width: float = Field(gt=0, le=14_400, allow_inf_nan=False)
    page_height: float = Field(gt=0, le=14_400, allow_inf_nan=False)
    coordinate_space: Literal["pdf_points_top_left"]

    @model_validator(mode="after")
    def validate_rectangle(self) -> DocumentSourceRegion:
        if not (
            0 <= self.bbox[0] < self.bbox[2] <= self.page_width
            and 0 <= self.bbox[1] < self.bbox[3] <= self.page_height
        ):
            raise ValueError("document parser returned an out-of-page source rectangle")
        return self


class DocumentParsePiece(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    ordinal: int = Field(ge=0, lt=MAX_PASSAGES)
    text: str = Field(min_length=1, max_length=PASSAGE_CHARACTERS)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0, le=MAX_TEXT_CHARACTERS)
    native_locator: dict[str, Any]
    parser_version: str = Field(min_length=1, max_length=160)
    page_number: int = Field(ge=1, le=MAX_DOCUMENT_PAGES)
    section: str | None = Field(default=None, max_length=320)


class DocumentParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    contract: str = Field(pattern=r"^openvigil\.document-parse\.v1$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_code_sha256: dict[str, str]
    library_versions: dict[str, str]
    body: str = Field(min_length=1, max_length=MAX_TEXT_CHARACTERS)
    passages: list[DocumentParsePiece] = Field(min_length=1, max_length=MAX_PASSAGES)
    source_page_count: int = Field(ge=1, le=MAX_DOCUMENT_PAGES)

    @model_validator(mode="after")
    def validate_positions(self) -> DocumentParseResult:
        cursor = 0
        for ordinal, passage in enumerate(self.passages):
            if passage.ordinal != ordinal or passage.page_number > self.source_page_count:
                raise ValueError("document parser returned inconsistent passage identity")
            if passage.char_start < cursor or passage.char_end <= passage.char_start:
                raise ValueError("document parser returned inconsistent text positions")
            if self.body[passage.char_start : passage.char_end] != passage.text:
                raise ValueError("document parser returned text outside its source span")
            if hashlib.sha256(passage.text.encode()).hexdigest() != passage.text_sha256:
                raise ValueError("document parser returned an inconsistent passage hash")
            if self.body[cursor : passage.char_start].strip():
                raise ValueError("document parser omitted text from its passage index")
            if passage.native_locator.get("kind") != "docling_pdf_item":
                raise ValueError("document parser returned an unsupported source locator")
            if passage.native_locator.get("requires_numeric_review") is not True:
                raise ValueError("document parser omitted its numeric review requirement")
            regions = passage.native_locator.get("regions")
            if not isinstance(regions, list) or not regions or len(regions) > MAX_DOCUMENT_PAGES:
                raise ValueError("document parser returned no bounded source regions")
            for region in regions:
                validated = DocumentSourceRegion.model_validate(region)
                if validated.page_number != passage.page_number:
                    raise ValueError("document parser returned a cross-page source region")
            cursor = passage.char_end
        if self.body[cursor:].strip():
            raise ValueError("document parser omitted trailing source text")
        return self
