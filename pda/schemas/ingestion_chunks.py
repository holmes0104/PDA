"""Normalized chunk schema for ingestion output — supports text and table chunks."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChunkType(str, Enum):
    """The kind of content a chunk carries."""
    TEXT = "text"
    TABLE = "table"


class SourceInfo(BaseModel):
    """Where this chunk came from."""
    source_type: Literal["pdf", "url"] = "pdf"
    source_ref: str = ""          # filename or URL
    page_num: int | None = None   # PDF page (1-based)
    heading_path: str | None = None  # URL heading breadcrumb
    section_title: str | None = None


class TableSpec(BaseModel):
    """Structured representation of a table extracted from a document."""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    caption: str | None = None
    kind: Literal["spec", "generic"] = "generic"


class SpecRow(BaseModel):
    """A single spec-table row normalised to name/value/unit/conditions."""
    name: str = ""
    value: str = ""
    unit: str = ""
    conditions: str = ""


class NormalizedChunk(BaseModel):
    """
    Unified chunk format emitted by the ingestion pipeline.

    * Text chunks carry ``content`` (plain text) and ``chunk_type == 'text'``.
    * Table chunks carry ``table`` (structured JSON) and ``chunk_type == 'table'``;
      ``content`` holds a textual summary used for embedding.
    """

    chunk_id: str
    chunk_type: ChunkType = ChunkType.TEXT
    source: SourceInfo = Field(default_factory=SourceInfo)
    content: str = ""                 # text (or table summary for embedding)
    table: TableSpec | None = None    # structured table data
    spec_rows: list[SpecRow] | None = None  # parsed spec rows (spec tables only)
    char_offset_start: int = 0
    char_offset_end: int = 0
    token_count: int = 0
    content_role: Literal["buyer", "operational"] = "buyer"
    metadata: dict[str, Any] = Field(default_factory=dict)
