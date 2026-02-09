"""Stage 6 — LLM-friendly content pack generation."""

from pda.content_pack.generator import generate_content_pack as generate_content_pack_legacy
from pda.content_pack.llm_ready_pack import (
    generate_content_pack,
    write_content_pack_bundle,
)

__all__ = [
    "generate_content_pack_legacy",
    "generate_content_pack",
    "write_content_pack_bundle",
]
