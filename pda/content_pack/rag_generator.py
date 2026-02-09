"""RAG-based content pack generator: FAQ, how-to-choose, applications, snippets with claim-level citations and tone control."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment, FileSystemLoader

from pda.schemas.content_pack_schemas import (
    Citation,
    ContentPack,
    ContentPackItem,
    Tone,
)

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
MAX_CONTEXT_CHARS = 14_000

PackType = Literal["faq", "how_to_choose", "applications", "snippets"]


def _build_context(
    store: object,
    queries: list[str],
    n_results: int = 15,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> tuple[str, dict[str, dict[str, Any]]]:
    """
    Retrieve chunks from the vector store for a set of queries.
    Returns (context_text, chunk_metadata_map).
    """
    seen: set[str] = set()
    parts: list[str] = []
    meta_map: dict[str, dict[str, Any]] = {}
    total = 0

    for q in queries:
        results = store.query(q, n_results=n_results)
        for r in results:
            cid = r.get("chunk_id", "")
            if cid in seen:
                continue
            seen.add(cid)
            text = r.get("text", "")
            snippet = f"[{cid}] {text[:1500]}"
            if total + len(snippet) > max_chars:
                break
            parts.append(snippet)
            meta_map[cid] = r.get("metadata", {})
            total += len(snippet)

    return "\n\n".join(parts), meta_map


def _parse_items(raw: str) -> list[dict]:
    """Parse LLM output into a list of dicts."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```\w*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    try:
        data = json.loads(s)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def _resolve_citations(
    cited_ids: list[str],
    meta_map: dict[str, dict[str, Any]],
) -> list[Citation]:
    """Turn chunk IDs into Citation objects with resolved metadata."""
    citations: list[Citation] = []
    for cid in cited_ids:
        meta = meta_map.get(cid, {})
        citations.append(
            Citation(
                chunk_id=cid,
                source_ref=meta.get("source_file", ""),
                page_num=meta.get("page_number") if meta.get("page_number", -1) != -1 else None,
                heading_path=meta.get("heading_path"),
                section_title=meta.get("section_heading", ""),
                excerpt="",
            )
        )
    return citations


# ── Query sets for each pack type ────────────────────────────────────────

_PACK_QUERIES: dict[PackType, list[str]] = {
    "faq": [
        "product overview and description",
        "key specifications and technical details",
        "pricing and purchasing options",
        "warranty and support information",
        "use cases and applications",
        "certifications and compliance",
        "installation and maintenance",
    ],
    "how_to_choose": [
        "product variants models and configurations",
        "selection criteria and decision factors",
        "application-specific requirements",
        "specifications comparison",
        "constraints and limitations",
        "compatibility and integration",
    ],
    "applications": [
        "use cases and applications",
        "industry-specific applications",
        "process monitoring quality control",
        "target users and buyer personas",
        "real-world deployment examples",
    ],
    "snippets": [
        "product name and description",
        "key features and benefits",
        "specifications and performance",
        "pricing and availability",
        "warranty support maintenance",
    ],
}


def generate_content_pack_rag(
    store: object,
    llm_provider: object,
    pack_type: PackType = "faq",
    tone: str = "technical",
) -> ContentPack:
    """
    Generate a content pack using RAG retrieval and LLM generation.

    store: vector store with .query() method.
    llm_provider: LLM with .complete() method.
    pack_type: one of 'faq', 'how_to_choose', 'applications', 'snippets'.
    tone: 'technical', 'marketing', or 'hybrid'.
    """
    tone_enum = Tone(tone.lower()) if tone.lower() in Tone.__members__.values() else Tone.TECHNICAL
    queries = _PACK_QUERIES.get(pack_type, _PACK_QUERIES["faq"])

    context_text, meta_map = _build_context(store, queries)

    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    template = env.get_template("content_pack_rag.j2")
    prompt = template.render(
        pack_type=pack_type,
        tone=tone_enum.value,
        chunk_text=context_text,
    )

    raw = llm_provider.complete(prompt)
    items_data = _parse_items(raw)

    items: list[ContentPackItem] = []
    for item_dict in items_data:
        cited_ids = item_dict.get("cited_chunk_ids", [])
        if not isinstance(cited_ids, list):
            cited_ids = []
        cited_ids = [str(c) for c in cited_ids]

        # Also extract inline [chunk-id] references from body
        body = str(item_dict.get("body", ""))
        inline_cites = re.findall(r"\[(pdf-[^\]]+|url-[^\]]+)\]", body)
        all_cite_ids = list(dict.fromkeys(cited_ids + inline_cites))

        citations = _resolve_citations(all_cite_ids, meta_map)

        items.append(
            ContentPackItem(
                item_id=str(item_dict.get("item_id", f"item-{len(items)}")),
                question=item_dict.get("question"),
                title=item_dict.get("title"),
                body=body,
                citations=citations,
                tone=tone_enum,
            )
        )

    return ContentPack(
        pack_type=pack_type,
        tone=tone_enum,
        items=items,
    )


def write_content_pack(pack: ContentPack, out_dir: Path) -> dict[str, Path]:
    """Write a content pack to JSON + Markdown files."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    # JSON export
    json_path = out_dir / f"{pack.pack_type}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(pack.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    written[f"{pack.pack_type}.json"] = json_path

    # Markdown export
    md_path = out_dir / f"{pack.pack_type}.md"
    lines: list[str] = []
    lines.append(f"# {pack.pack_type.replace('_', ' ').title()} (tone: {pack.tone.value})\n")
    for item in pack.items:
        if item.question:
            lines.append(f"## Q: {item.question}\n")
        elif item.title:
            lines.append(f"## {item.title}\n")
        lines.append(f"{item.body}\n")
        if item.citations:
            cite_strs = []
            for c in item.citations:
                parts = [c.chunk_id]
                if c.source_ref:
                    parts.append(c.source_ref)
                if c.page_num is not None:
                    parts.append(f"p.{c.page_num}")
                cite_strs.append(", ".join(parts))
            lines.append("**Sources:** " + " | ".join(cite_strs) + "\n")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    written[f"{pack.pack_type}.md"] = md_path

    return written
