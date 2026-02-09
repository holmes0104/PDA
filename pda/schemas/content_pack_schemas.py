"""Machine-readable export schema for content packs with claim-level citations."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Tone(str, Enum):
    TECHNICAL = "technical"
    MARKETING = "marketing"
    HYBRID = "hybrid"


class Citation(BaseModel):
    """A single citation back to an ingested chunk."""

    chunk_id: str = ""
    source_ref: str = ""       # filename or URL
    page_num: int | None = None
    heading_path: str | None = None
    section_title: str | None = None
    excerpt: str = ""          # verbatim snippet from the source


class ContentPackItem(BaseModel):
    """One item in a content pack (FAQ entry, snippet, guide section, etc.)."""

    item_id: str = ""
    question: str | None = None   # for FAQ items
    title: str | None = None      # for guide / snippet items
    body: str = ""
    citations: list[Citation] = Field(default_factory=list)
    tone: Tone = Tone.TECHNICAL


class ContentPack(BaseModel):
    """An exportable content pack with typed sections."""

    pack_type: Literal["faq", "how_to_choose", "applications", "snippets"] = "faq"
    tone: Tone = Tone.TECHNICAL
    items: list[ContentPackItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
