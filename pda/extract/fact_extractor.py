"""Extract ProductFactSheet from document chunks using LLM and evidence grounding."""

import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from pda.schemas.models import (
    ContentRole,
    DocumentChunk,
    EvidenceRef,
    FactValue,
    ProductFactSheet,
)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
MAX_CHUNK_CHARS = 120000  # ~30k tokens


def _chunk_map(chunks: list[DocumentChunk]) -> dict[str, DocumentChunk]:
    return {c.chunk_id: c for c in chunks}


def _to_evidence_ref(
    chunk_ids: list[str],
    verbatim_excerpt: str,
    chunk_by_id: dict[str, DocumentChunk],
) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for cid in chunk_ids:
        ch = chunk_by_id.get(cid)
        source_file = ch.source_file if ch else ""
        page_numbers = [ch.page_number] if ch and ch.page_number is not None else []
        refs.append(
            EvidenceRef(
                chunk_ids=[cid],
                source_file=source_file,
                page_numbers=page_numbers,
                section=ch.section_heading if ch else None,
                verbatim_excerpt=verbatim_excerpt[:500] if verbatim_excerpt else "",
            )
        )
    if not refs and verbatim_excerpt:
        refs.append(
            EvidenceRef(
                chunk_ids=chunk_ids,
                source_file="",
                page_numbers=[],
                verbatim_excerpt=verbatim_excerpt[:500],
            )
        )
    return refs


def _to_fact_value(raw: dict, chunk_by_id: dict[str, DocumentChunk]) -> FactValue:
    value = raw.get("value", "NOT_FOUND")
    if value is None:
        value = "NOT_FOUND"
    confidence = raw.get("confidence", "LOW") or "LOW"
    if confidence not in ("HIGH", "MEDIUM", "LOW"):
        confidence = "LOW"
    chunk_ids = raw.get("chunk_ids") or []
    excerpt = raw.get("verbatim_excerpt") or ""
    evidence = _to_evidence_ref(chunk_ids, excerpt, chunk_by_id)
    return FactValue(value=value, confidence=confidence, evidence=evidence)


def _parse_extraction(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return json.loads(text)


def extract_fact_sheet(
    chunks: list[DocumentChunk],
    llm_provider: object,
    max_chars: int = MAX_CHUNK_CHARS,
) -> ProductFactSheet:
    """
    Run LLM extraction over chunks and return a grounded ProductFactSheet.
    llm_provider must have .complete(prompt: str) -> str.

    Buyer-tagged chunks are prioritized in the context window; operational
    chunks are appended only if space remains, so the LLM focuses on
    buyer-relevant content.
    """
    chunk_by_id = _chunk_map(chunks)

    # Prioritize buyer-tagged chunks, then fill with operational if space allows
    buyer = [c for c in chunks if c.content_role == ContentRole.BUYER]
    operational = [c for c in chunks if c.content_role == ContentRole.OPERATIONAL]
    ordered = buyer + operational  # buyer first

    total = 0
    use: list[DocumentChunk] = []
    for c in ordered:
        if total + len(c.text) > max_chars:
            break
        use.append(c)
        total += len(c.text)
    if not use:
        use = chunks[:50]
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    template = env.get_template("extract_facts.j2")
    prompt = template.render(chunks=use)
    raw = llm_provider.complete(prompt)
    data = _parse_extraction(raw)

    def fv(key: str) -> FactValue:
        r = data.get(key)
        if r is None or (isinstance(r, dict) and r.get("value") is None):
            return FactValue(value="NOT_FOUND", confidence="LOW", evidence=[])
        if isinstance(r, dict):
            return _to_fact_value(r, chunk_by_id)
        return FactValue(value="NOT_FOUND", confidence="LOW", evidence=[])

    def fv_list(key: str) -> list[FactValue]:
        r = data.get(key)
        if not isinstance(r, list):
            return []
        return [_to_fact_value(item, chunk_by_id) for item in r if isinstance(item, dict)]

    def fv_dict(key: str) -> dict[str, FactValue]:
        r = data.get(key)
        if not isinstance(r, dict):
            return {}
        out: dict[str, FactValue] = {}
        for k, v in r.items():
            if isinstance(v, dict):
                out[k] = _to_fact_value(v, chunk_by_id)
        return out

    return ProductFactSheet(
        product_name=fv("product_name"),
        manufacturer=fv("manufacturer"),
        model_number=fv("model_number"),
        category=fv("category"),
        short_description=fv("short_description"),
        key_features=fv_list("key_features"),
        specifications=fv_dict("specifications"),
        use_cases=fv_list("use_cases"),
        target_audience=fv("target_audience"),
        pricing=fv("pricing"),
        certifications=fv_list("certifications"),
        compatibility=fv_list("compatibility"),
        warranty=fv("warranty"),
        support_info=fv("support_info"),
    )
