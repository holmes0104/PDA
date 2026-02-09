"""Build zip export from WebContentDrafts with Evidence sections in each .md file."""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any

from pda.schemas.web_content_schemas import (
    ComparisonDraft,
    LandingPageDraft,
    SEODraft,
    UseCasePageDraft,
    WebContentDrafts,
)


def _slugify(s: str) -> str:
    """Simple slug from title."""
    s = re.sub(r"[^\w\s-]", "", s.lower())
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return s or "untitled"


def _format_evidence_section(refs: list[dict[str, Any]]) -> str:
    """Format evidence refs as markdown section."""
    if not refs:
        return "## Evidence\n\nNo explicit source references in this section.\n\n---\n\n"
    lines = ["## Evidence\n"]
    for r in refs:
        chunk_ids = r.get("chunk_ids") or []
        source = r.get("source_file") or ""
        pages = r.get("page_numbers") or []
        excerpt = r.get("verbatim_excerpt") or ""
        parts = []
        if source:
            parts.append(source)
        if pages:
            parts.append(f"p. {', '.join(str(p) for p in pages)}")
        if chunk_ids:
            parts.append(f"[{', '.join(chunk_ids[:5])}{'…' if len(chunk_ids) > 5 else ''}]")
        if excerpt:
            snippet = excerpt[:120] + "…" if len(excerpt) > 120 else excerpt
            parts.append(f"\"{snippet}\"")
        if parts:
            lines.append("- " + " | ".join(parts))
    lines.append("\n---\n\n")
    return "\n".join(lines)


def _evidence_for_landing(d: LandingPageDraft) -> list[dict]:
    refs: list[dict] = []
    for b in d.benefits:
        refs.extend(e.model_dump() if hasattr(e, "model_dump") else e for e in b.evidence)
    for s in d.specs_explained:
        refs.extend(e.model_dump() if hasattr(e, "model_dump") else e for e in s.evidence)
    return refs


def _evidence_for_faq(d: list) -> list[dict]:
    refs: list[dict] = []
    for f in d:
        for e in getattr(f, "evidence", []):
            refs.append(e.model_dump() if hasattr(e, "model_dump") else e)
    return refs


def _evidence_for_use_case(u: UseCasePageDraft) -> list[dict]:
    return [e.model_dump() if hasattr(e, "model_dump") else e for e in u.evidence]


def _evidence_for_comparison(c: ComparisonDraft) -> list[dict]:
    refs: list[dict] = []
    for d in c.dimensions:
        refs.extend(e.model_dump() if hasattr(e, "model_dump") else e for e in d.evidence)
    return refs


def _landing_page_md(d: LandingPageDraft) -> str:
    lines: list[str] = []
    evidence = _evidence_for_landing(d)
    lines.append(_format_evidence_section(evidence))
    lines.append("# Landing Page\n\n")
    if d.problem_statement:
        lines.append("## Problem Statement\n\n")
        lines.append(d.problem_statement + "\n\n")
    if d.solution_overview:
        lines.append("## Solution Overview\n\n")
        lines.append(d.solution_overview + "\n\n")
    if d.benefits:
        lines.append("## Benefits\n\n")
        for b in d.benefits:
            lines.append(f"### {b.headline}\n\n")
            lines.append(b.description + "\n\n")
    if d.how_it_works:
        lines.append("## How It Works\n\n")
        lines.append(d.how_it_works + "\n\n")
    if d.specs_explained:
        lines.append("## Specifications Explained\n\n")
        for s in d.specs_explained:
            lines.append(f"**{s.spec_name}:** {s.spec_value} {s.unit}\n\n")
            lines.append(s.plain_language + "\n\n")
    if d.call_to_action:
        lines.append("## Call to Action\n\n")
        lines.append(d.call_to_action + "\n\n")
    return "".join(lines)


def _faq_md(d: list) -> str:
    lines: list[str] = []
    evidence = _evidence_for_faq(d)
    lines.append(_format_evidence_section(evidence))
    lines.append("# FAQ\n\n")
    for item in d:
        q = getattr(item, "question", "")
        a = getattr(item, "answer", "")
        lines.append(f"## {q}\n\n")
        lines.append(a + "\n\n")
    return "".join(lines)


def _use_case_md(u: UseCasePageDraft) -> str:
    lines: list[str] = []
    evidence = _evidence_for_use_case(u)
    lines.append(_format_evidence_section(evidence))
    tag = "[Suggested] " if u.is_suggested else ""
    lines.append(f"# {tag}{u.title}\n\n")
    if u.problem_context:
        lines.append("## Problem Context\n\n")
        lines.append(u.problem_context + "\n\n")
    if u.solution_fit:
        lines.append("## Solution Fit\n\n")
        lines.append(u.solution_fit + "\n\n")
    if u.benefits:
        lines.append("## Benefits\n\n")
        for b in u.benefits:
            lines.append(f"- {b}\n")
        lines.append("\n")
    if u.implementation_notes:
        lines.append("## Implementation Notes\n\n")
        lines.append(u.implementation_notes + "\n\n")
    return "".join(lines)


def _comparison_md(c: ComparisonDraft) -> str:
    lines: list[str] = []
    evidence = _evidence_for_comparison(c)
    lines.append(_format_evidence_section(evidence))
    lines.append(f"# {c.title}\n\n")
    if c.best_for:
        lines.append("## Best For\n\n")
        for b in c.best_for:
            lines.append(f"- {b}\n")
        lines.append("\n")
    if c.not_ideal_for:
        lines.append("## Not Ideal For\n\n")
        for n in c.not_ideal_for:
            lines.append(f"- {n}\n")
        lines.append("\n")
    if c.dimensions:
        lines.append("## Comparison Dimensions\n\n")
        lines.append("| Dimension | This Product | Generic Alternative |\n")
        lines.append("|-----------|--------------|---------------------|\n")
        for d in c.dimensions:
            lines.append(f"| {d.dimension} | {d.this_product} | {d.generic_alternative} |\n")
    return "".join(lines)


def _seo_json(d: SEODraft) -> dict[str, Any]:
    return {
        "title_tag": d.title_tag,
        "meta_description": d.meta_description,
        "headings": [{"tag": h.tag, "text": h.text} for h in d.headings],
        "product_jsonld": d.product_jsonld,
    }


def build_content_zip(drafts: WebContentDrafts) -> bytes:
    """Build zip bytes from drafts with Evidence sections in each .md."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        drafts_json = json.dumps(
            drafts.model_dump(mode="json") if hasattr(drafts, "model_dump") else drafts,
            indent=2,
            ensure_ascii=False,
        )
        zf.writestr("drafts.json", drafts_json.encode("utf-8"))

        zf.writestr(
            "landing-page.md",
            _landing_page_md(drafts.landing_page).encode("utf-8"),
        )
        zf.writestr("faq.md", _faq_md(drafts.faq).encode("utf-8"))

        for u in drafts.use_case_pages:
            slug = u.slug or _slugify(u.title)
            path = f"use-cases/{slug}.md"
            zf.writestr(path, _use_case_md(u).encode("utf-8"))

        for c in drafts.comparisons:
            slug = _slugify(c.title)
            path = f"comparisons/{slug}.md"
            zf.writestr(path, _comparison_md(c).encode("utf-8"))

        seo_data = _seo_json(drafts.seo)
        zf.writestr(
            "seo.json",
            json.dumps(seo_data, indent=2, ensure_ascii=False).encode("utf-8"),
        )

    return buf.getvalue()
