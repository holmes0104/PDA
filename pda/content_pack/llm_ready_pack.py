"""LLM-ready content pack generator — orchestrates preflight, RAG retrieval,
four grounded output types, citation resolution, and Markdown+JSON export."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from pda.schemas.content_pack_schemas import Citation, Tone
from pda.schemas.factsheet_schema import ProductFactSheet
from pda.schemas.llm_ready_pack import (
    CanonicalAnswerBlock,
    ComparisonRow,
    ContentPackBundle,
    DecisionCriterion,
    ExportManifest,
    FAQEntry,
    ManifestFileEntry,
    MissingFactQuestion,
    PreflightResult,
    SelectionGuidance,
    UseCaseFAQ,
    UseCasePage,
)

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
MAX_CONTEXT_CHARS = 18_000

# ── Retrieval queries by section ──────────────────────────────────────────

_SECTION_QUERIES: dict[str, list[str]] = {
    "canonical": [
        "product overview and description",
        "key specifications accuracy range",
        "operating environment conditions",
        "installation setup deployment",
        "maintenance calibration service",
        "compliance certifications standards",
        "integration connectivity outputs protocols",
        "troubleshooting common issues",
        "applications use cases industries",
    ],
    "faq": [
        "product selection guide which model",
        "installation wiring mounting",
        "accuracy specifications precision",
        "environmental limits temperature humidity",
        "compatibility integration protocols",
        "maintenance calibration intervals",
        "troubleshooting error codes diagnostics",
        "accessories optional parts",
    ],
    "selection": [
        "product variants models configurations",
        "selection criteria decision factors",
        "specifications comparison table",
        "application requirements constraints",
        "compatibility interfaces",
        "operating range limits",
    ],
    "usecases": [
        "use cases applications industries",
        "process monitoring quality control",
        "target users buyer personas",
        "deployment examples field installations",
        "measurement requirements constraints",
        "environmental conditions operating ranges",
        "performance accuracy specifications",
    ],
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _build_context(
    store: object,
    queries: list[str],
    n_results: int = 15,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Retrieve chunks and return (context_text, chunk_metadata_map)."""
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


def _strip_code_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```\w*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


def _parse_json(raw: str) -> Any:
    return json.loads(_strip_code_fence(raw))


def _resolve_citations(
    cited_ids: list[str],
    meta_map: dict[str, dict[str, Any]],
) -> list[Citation]:
    citations: list[Citation] = []
    for cid in cited_ids:
        if not cid:
            continue
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


def _extract_inline_cites(text: str) -> list[str]:
    """Extract [chunk-id] references from text."""
    return re.findall(r"\[(pdf-[^\]]+|url-[^\]]+)\]", text)


def _factsheet_summary(sheet: ProductFactSheet) -> str:
    """Build a concise text summary of the fact sheet for prompt context."""
    lines = [
        f"Product: {sheet.product_name}",
        f"Category: {sheet.product_category}",
    ]
    if sheet.primary_use_cases:
        lines.append(f"Use cases: {', '.join(sheet.primary_use_cases[:5])}")
    if sheet.key_specs:
        specs = [f"{s.name}: {s.value} {s.unit}".strip() for s in sheet.key_specs[:8]]
        lines.append(f"Key specs: {'; '.join(specs)}")
    if sheet.constraints:
        lines.append(f"Constraints: {'; '.join(c.statement for c in sheet.constraints[:4])}")
    if sheet.certifications_standards:
        lines.append(f"Certifications: {', '.join(sheet.certifications_standards[:5])}")
    if sheet.integrations_interfaces:
        lines.append(f"Interfaces: {', '.join(sheet.integrations_interfaces[:5])}")
    if sheet.maintenance_calibration:
        lines.append(f"Maintenance: {', '.join(sheet.maintenance_calibration[:3])}")
    return "\n".join(lines)


# ── Preflight ─────────────────────────────────────────────────────────────

CRITICAL_FIELDS = {"product_name", "product_category", "key_specs", "primary_use_cases"}
IMPORTANT_FIELDS = {
    "target_buyer_roles",
    "constraints",
    "certifications_standards",
    "integrations_interfaces",
    "maintenance_calibration",
}


def run_preflight(
    sheet: ProductFactSheet,
    llm_provider: object | None = None,
) -> PreflightResult:
    """Lightweight preflight: detect missing/ambiguous facts."""
    missing: list[str] = []
    all_fields = list(CRITICAL_FIELDS | IMPORTANT_FIELDS)

    for field in all_fields:
        val = getattr(sheet, field, None)
        if val is None:
            missing.append(field)
        elif isinstance(val, str) and (val == "NOT_FOUND" or not val.strip()):
            missing.append(field)
        elif isinstance(val, list) and len(val) == 0:
            missing.append(field)

    # Determine if we can generate
    critical_missing = [f for f in missing if f in CRITICAL_FIELDS]
    can_generate = len(critical_missing) <= 1  # allow one critical miss (e.g. category)
    if sheet.product_name == "NOT_FOUND":
        can_generate = False
    if isinstance(sheet.key_specs, list) and len(sheet.key_specs) < 2:
        can_generate = False

    # Build questions
    questions: list[MissingFactQuestion] = []
    question_map = {
        "product_name": ("What is the exact product name?", "Required to title all outputs"),
        "product_category": ("What product category does this belong to?", "Needed for FAQ theming and selection guidance"),
        "key_specs": ("What are the key technical specifications (range, accuracy, output)?", "Core specs are needed for answer blocks and comparison tables"),
        "primary_use_cases": ("What are the primary use cases or applications?", "Required to generate use-case pages"),
        "target_buyer_roles": ("Who is the target buyer (e.g., process engineer, facility manager)?", "Helps tailor tone and question framing"),
        "constraints": ("What are the operating limits or constraints?", "Needed for 'not suitable when' fields"),
        "certifications_standards": ("What certifications or standards does the product meet?", "Important for compliance-related FAQs"),
        "integrations_interfaces": ("What output signals or communication protocols are supported?", "Needed for compatibility/integration FAQs"),
        "maintenance_calibration": ("What is the calibration or maintenance schedule?", "Needed for maintenance/calibration FAQs"),
    }
    for field in missing[:7]:
        if field in question_map:
            q, why = question_map[field]
            questions.append(MissingFactQuestion(field=field, question=q, why_needed=why))

    return PreflightResult(
        product_name=sheet.product_name,
        facts_found=len(all_fields) - len(missing),
        facts_expected=len(all_fields),
        missing_fields=missing,
        questions=questions,
        can_generate=can_generate,
    )


# ── Generators per output type ────────────────────────────────────────────

def _generate_canonical_answers(
    store: object,
    llm_provider: object,
    sheet: ProductFactSheet,
    tone: Tone,
    meta_map_out: dict[str, dict[str, Any]],
) -> list[CanonicalAnswerBlock]:
    context_text, meta_map = _build_context(store, _SECTION_QUERIES["canonical"])
    meta_map_out.update(meta_map)

    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    prompt = env.get_template("llm_ready_canonical.j2").render(
        tone=tone.value,
        factsheet_summary=_factsheet_summary(sheet),
        chunk_text=context_text,
    )
    raw = llm_provider.complete(prompt)
    items = _parse_json(raw) if raw else []
    if not isinstance(items, list):
        items = []

    blocks: list[CanonicalAnswerBlock] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cited_ids = [str(c) for c in (item.get("cited_chunk_ids") or [])]
        inline = _extract_inline_cites(str(item.get("answer", "")))
        all_ids = list(dict.fromkeys(cited_ids + inline))
        blocks.append(CanonicalAnswerBlock(
            block_id=str(item.get("block_id", f"cab-{len(blocks)}")),
            question=str(item.get("question", "")),
            answer=str(item.get("answer", "")),
            best_for=str(item.get("best_for", "")),
            not_suitable_when=str(item.get("not_suitable_when", "")),
            citations=_resolve_citations(all_ids, meta_map),
        ))
    return blocks


def _generate_faq(
    store: object,
    llm_provider: object,
    sheet: ProductFactSheet,
    tone: Tone,
    meta_map_out: dict[str, dict[str, Any]],
) -> list[FAQEntry]:
    context_text, meta_map = _build_context(store, _SECTION_QUERIES["faq"])
    meta_map_out.update(meta_map)

    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    prompt = env.get_template("llm_ready_faq.j2").render(
        tone=tone.value,
        factsheet_summary=_factsheet_summary(sheet),
        chunk_text=context_text,
    )
    raw = llm_provider.complete(prompt)
    items = _parse_json(raw) if raw else []
    if not isinstance(items, list):
        items = []

    entries: list[FAQEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cited_ids = [str(c) for c in (item.get("cited_chunk_ids") or [])]
        inline = _extract_inline_cites(str(item.get("answer", "")))
        all_ids = list(dict.fromkeys(cited_ids + inline))
        entries.append(FAQEntry(
            faq_id=str(item.get("faq_id", f"faq-{len(entries)}")),
            theme=str(item.get("theme", "general")),
            question=str(item.get("question", "")),
            answer=str(item.get("answer", "")),
            citations=_resolve_citations(all_ids, meta_map),
        ))
    return entries


def _generate_selection_guidance(
    store: object,
    llm_provider: object,
    sheet: ProductFactSheet,
    tone: Tone,
    meta_map_out: dict[str, dict[str, Any]],
) -> SelectionGuidance:
    context_text, meta_map = _build_context(store, _SECTION_QUERIES["selection"])
    meta_map_out.update(meta_map)

    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    prompt = env.get_template("llm_ready_selection.j2").render(
        tone=tone.value,
        factsheet_summary=_factsheet_summary(sheet),
        chunk_text=context_text,
    )
    raw = llm_provider.complete(prompt)
    data = _parse_json(raw) if raw else {}
    if not isinstance(data, dict):
        data = {}

    # Decision criteria
    criteria: list[DecisionCriterion] = []
    for dc in (data.get("decision_criteria") or []):
        if not isinstance(dc, dict):
            continue
        cited_ids = [str(c) for c in (dc.get("cited_chunk_ids") or [])]
        inline = _extract_inline_cites(str(dc.get("statement", "")))
        all_ids = list(dict.fromkeys(cited_ids + inline))
        criteria.append(DecisionCriterion(
            criterion_id=str(dc.get("criterion_id", f"dc-{len(criteria)}")),
            statement=str(dc.get("statement", "")),
            citations=_resolve_citations(all_ids, meta_map),
        ))

    # Comparison table
    rows: list[ComparisonRow] = []
    for row in (data.get("comparison_table") or []):
        if not isinstance(row, dict):
            continue
        cited_ids = [str(c) for c in (row.get("cited_chunk_ids") or [])]
        rows.append(ComparisonRow(
            variant=str(row.get("variant", "")),
            attributes=row.get("attributes", {}),
            citations=_resolve_citations(cited_ids, meta_map),
        ))

    missing_info = [str(m) for m in (data.get("missing_info") or [])]

    top_cited = [str(c) for c in (data.get("cited_chunk_ids") or [])]

    return SelectionGuidance(
        decision_criteria=criteria,
        comparison_table=rows,
        decision_tree_md=str(data.get("decision_tree_md", "")),
        missing_info=missing_info,
        citations=_resolve_citations(top_cited, meta_map),
    )


def _generate_use_case_pages(
    store: object,
    llm_provider: object,
    sheet: ProductFactSheet,
    tone: Tone,
    meta_map_out: dict[str, dict[str, Any]],
) -> list[UseCasePage]:
    context_text, meta_map = _build_context(store, _SECTION_QUERIES["usecases"])
    meta_map_out.update(meta_map)

    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    prompt = env.get_template("llm_ready_usecases.j2").render(
        tone=tone.value,
        factsheet_summary=_factsheet_summary(sheet),
        chunk_text=context_text,
    )
    raw = llm_provider.complete(prompt)
    items = _parse_json(raw) if raw else []
    if not isinstance(items, list):
        items = []

    pages: list[UseCasePage] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # Parse nested FAQs
        faqs: list[UseCaseFAQ] = []
        for faq_item in (item.get("faqs") or []):
            if not isinstance(faq_item, dict):
                continue
            faq_cited = [str(c) for c in (faq_item.get("cited_chunk_ids") or [])]
            inline = _extract_inline_cites(str(faq_item.get("answer", "")))
            faq_all = list(dict.fromkeys(faq_cited + inline))
            faqs.append(UseCaseFAQ(
                question=str(faq_item.get("question", "")),
                answer=str(faq_item.get("answer", "")),
                citations=_resolve_citations(faq_all, meta_map),
            ))

        cited_ids = [str(c) for c in (item.get("cited_chunk_ids") or [])]
        # Gather inline cites from all text fields
        for field in ("problem_context", "requirements", "why_this_product_fits", "implementation_notes"):
            cited_ids.extend(_extract_inline_cites(str(item.get(field, ""))))
        all_ids = list(dict.fromkeys(cited_ids))

        pages.append(UseCasePage(
            page_id=str(item.get("page_id", f"uc-{len(pages)}")),
            title=str(item.get("title", "")),
            problem_context=str(item.get("problem_context", "")),
            requirements=str(item.get("requirements", "")),
            why_this_product_fits=str(item.get("why_this_product_fits", "")),
            implementation_notes=str(item.get("implementation_notes", "")),
            faqs=faqs,
            citations=_resolve_citations(all_ids, meta_map),
        ))
    return pages


# ── Main orchestrator ─────────────────────────────────────────────────────

def generate_content_pack(
    store: object,
    llm_provider: object,
    sheet: ProductFactSheet,
    tone: str = "technical",
    proceed_with_assumptions: bool = False,
) -> ContentPackBundle:
    """
    Generate the full LLM-ready content pack.

    Returns a ContentPackBundle. If preflight detects critical missing fields
    and proceed_with_assumptions is False, the bundle will have empty outputs
    and preflight.can_generate == False.
    """
    tone_enum = Tone(tone.lower()) if tone.lower() in [t.value for t in Tone] else Tone.TECHNICAL

    # --- Preflight ---
    preflight = run_preflight(sheet, llm_provider)

    if not preflight.can_generate and not proceed_with_assumptions:
        return ContentPackBundle(
            project_id="",
            tone=tone_enum,
            preflight=preflight,
        )

    assumptions: list[str] = []
    if not preflight.can_generate and proceed_with_assumptions:
        assumptions.append("Generating with missing critical fields; outputs may be incomplete.")
        for mf in preflight.missing_fields:
            assumptions.append(f"Field '{mf}' is missing or NOT_FOUND.")

    # Shared meta map for citation resolution across sections
    meta_map_all: dict[str, dict[str, Any]] = {}

    # --- Generate all four outputs ---
    logger.info("Generating canonical answer blocks (tone=%s)", tone_enum.value)
    canonical = _generate_canonical_answers(store, llm_provider, sheet, tone_enum, meta_map_all)

    logger.info("Generating FAQ entries")
    faq = _generate_faq(store, llm_provider, sheet, tone_enum, meta_map_all)

    logger.info("Generating selection guidance")
    selection = _generate_selection_guidance(store, llm_provider, sheet, tone_enum, meta_map_all)

    logger.info("Generating use-case pages")
    usecases = _generate_use_case_pages(store, llm_provider, sheet, tone_enum, meta_map_all)

    return ContentPackBundle(
        project_id="",
        tone=tone_enum,
        preflight=preflight,
        canonical_answers=canonical,
        faq=faq,
        selection_guidance=selection,
        use_case_pages=usecases,
        assumptions=assumptions,
    )


# ── Export to Markdown + JSON ─────────────────────────────────────────────

def _cite_str(citations: list[Citation]) -> str:
    """Format citations as a compact source string."""
    parts: list[str] = []
    for c in citations:
        elems = [c.chunk_id]
        if c.source_ref:
            elems.append(c.source_ref)
        if c.page_num is not None:
            elems.append(f"p.{c.page_num}")
        parts.append(", ".join(elems))
    return " | ".join(parts)


def write_content_pack_bundle(bundle: ContentPackBundle, out_dir: Path) -> dict[str, Path]:
    """Write the full bundle to Markdown files + JSON manifest. Returns {filename: path}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    total_citations = 0

    # --- 1. Canonical Answer Blocks ---
    lines: list[str] = [f"# Canonical Answer Blocks (tone: {bundle.tone.value})\n"]
    for b in bundle.canonical_answers:
        lines.append(f"## {b.question}\n")
        lines.append(f"{b.answer}\n")
        lines.append(f"**Best for:** {b.best_for}\n")
        lines.append(f"**Not suitable when:** {b.not_suitable_when}\n")
        if b.citations:
            lines.append(f"**Sources:** {_cite_str(b.citations)}\n")
            total_citations += len(b.citations)
        lines.append("")
    md_path = out_dir / "canonical_answers.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    written["canonical_answers.md"] = md_path

    # --- 2. FAQ ---
    lines = [f"# Product FAQ (tone: {bundle.tone.value})\n"]
    current_theme = ""
    for entry in sorted(bundle.faq, key=lambda e: e.theme):
        if entry.theme != current_theme:
            current_theme = entry.theme
            lines.append(f"\n## {current_theme.replace('_', ' ').title()}\n")
        lines.append(f"### Q: {entry.question}\n")
        lines.append(f"{entry.answer}\n")
        if entry.citations:
            lines.append(f"**Sources:** {_cite_str(entry.citations)}\n")
            total_citations += len(entry.citations)
        lines.append("")
    md_path = out_dir / "faq.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    written["faq.md"] = md_path

    # --- 3. Selection Guidance ---
    sg = bundle.selection_guidance
    lines = [f"# Selection Guidance (tone: {bundle.tone.value})\n"]
    lines.append("## Decision Criteria\n")
    for dc in sg.decision_criteria:
        lines.append(f"- {dc.statement}")
        if dc.citations:
            lines.append(f"  **Sources:** {_cite_str(dc.citations)}")
            total_citations += len(dc.citations)
    lines.append("")
    if sg.comparison_table:
        lines.append("## Comparison Table\n")
        # Build header from first row's attributes
        if sg.comparison_table:
            attrs = list(sg.comparison_table[0].attributes.keys())
            header = "| Variant | " + " | ".join(a.replace("_", " ").title() for a in attrs) + " |"
            sep = "|" + "|".join(["---"] * (len(attrs) + 1)) + "|"
            lines.append(header)
            lines.append(sep)
            for row in sg.comparison_table:
                vals = [row.attributes.get(a, "") for a in attrs]
                lines.append(f"| {row.variant} | " + " | ".join(vals) + " |")
                total_citations += len(row.citations)
        lines.append("")
    if sg.decision_tree_md:
        lines.append("## Decision Tree\n")
        lines.append(sg.decision_tree_md)
        lines.append("")
    if sg.missing_info:
        lines.append("## Missing Information\n")
        for mi in sg.missing_info:
            lines.append(f"- {mi}")
        lines.append("")
    total_citations += len(sg.citations)
    md_path = out_dir / "selection_guidance.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    written["selection_guidance.md"] = md_path

    # --- 4. Use-case Pages ---
    for page in bundle.use_case_pages:
        lines = [f"# {page.title}\n"]
        lines.append("## Problem Context\n")
        lines.append(f"{page.problem_context}\n")
        lines.append("## Requirements\n")
        lines.append(f"{page.requirements}\n")
        lines.append("## Why This Product Fits\n")
        lines.append(f"{page.why_this_product_fits}\n")
        lines.append("## Implementation Notes\n")
        lines.append(f"{page.implementation_notes}\n")
        if page.faqs:
            lines.append("## FAQs\n")
            for faq in page.faqs:
                lines.append(f"### Q: {faq.question}\n")
                lines.append(f"{faq.answer}\n")
                if faq.citations:
                    lines.append(f"**Sources:** {_cite_str(faq.citations)}\n")
                    total_citations += len(faq.citations)
        if page.citations:
            lines.append(f"\n**Page sources:** {_cite_str(page.citations)}\n")
            total_citations += len(page.citations)

        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", page.page_id)
        md_path = out_dir / f"usecase_{safe_id}.md"
        md_path.write_text("\n".join(lines), encoding="utf-8")
        written[f"usecase_{safe_id}.md"] = md_path

    # --- 5. Full bundle JSON ---
    json_path = out_dir / "content_pack.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(bundle.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    written["content_pack.json"] = json_path

    # --- 6. Manifest ---
    manifest_files: list[ManifestFileEntry] = []
    manifest_files.append(ManifestFileEntry(
        filename="canonical_answers.md",
        section="canonical_answers",
        item_count=len(bundle.canonical_answers),
        citation_count=sum(len(b.citations) for b in bundle.canonical_answers),
    ))
    manifest_files.append(ManifestFileEntry(
        filename="faq.md",
        section="faq",
        item_count=len(bundle.faq),
        citation_count=sum(len(e.citations) for e in bundle.faq),
    ))
    manifest_files.append(ManifestFileEntry(
        filename="selection_guidance.md",
        section="selection_guidance",
        item_count=len(sg.decision_criteria) + len(sg.comparison_table),
        citation_count=(
            sum(len(dc.citations) for dc in sg.decision_criteria)
            + sum(len(r.citations) for r in sg.comparison_table)
            + len(sg.citations)
        ),
    ))
    for page in bundle.use_case_pages:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", page.page_id)
        manifest_files.append(ManifestFileEntry(
            filename=f"usecase_{safe_id}.md",
            section="use_case_page",
            item_count=1 + len(page.faqs),
            citation_count=len(page.citations) + sum(len(faq.citations) for faq in page.faqs),
        ))

    manifest = ExportManifest(
        project_id=bundle.project_id,
        tone=bundle.tone.value,
        files=manifest_files,
        total_citations=total_citations,
        assumptions=bundle.assumptions,
        preflight_questions=bundle.preflight.questions if not bundle.preflight.can_generate else [],
    )
    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    written["manifest.json"] = manifest_path

    return written
