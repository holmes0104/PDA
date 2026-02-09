"""Web-ready product content generator.

Orchestrates LLM calls to produce landing page, FAQ, use-case pages,
comparisons, and SEO drafts — all grounded in the stored fact sheet
and audit artifacts.  No hallucinated specs, certifications, pricing,
or competitor names.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from pda.guardrails import run_draft_guardrails
from pda.schemas.factsheet_schema import ProductFactSheet
from pda.schemas.models import AuditFinding, Scorecard
from pda.schemas.web_content_schemas import (
    BenefitItem,
    ComparisonDimension,
    ComparisonDraft,
    EvidenceRef,
    FAQItem,
    GenerationMetadata,
    LandingPageDraft,
    SEODraft,
    SEOHeading,
    SpecExplained,
    UseCasePageDraft,
    WebContentDrafts,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
MAX_CONTEXT_CHARS = 18_000

# Retrieval queries (tailored for web-content sections)
_SECTION_QUERIES: dict[str, list[str]] = {
    "landing": [
        "product overview description value proposition",
        "key specifications accuracy range performance",
        "working principle technology how it works",
        "applications use cases industries",
        "benefits advantages strengths",
        "operating environment conditions",
    ],
    "faq": [
        "product overview what is this",
        "specifications accuracy range precision",
        "installation setup mounting wiring",
        "maintenance calibration service intervals",
        "compatibility integration protocols interfaces",
        "certifications compliance standards",
        "constraints limitations environmental limits",
        "troubleshooting diagnostics error",
        "applications use cases",
    ],
    "usecases": [
        "use cases applications industries deployment",
        "process monitoring quality control",
        "measurement requirements constraints",
        "environmental conditions operating ranges",
        "performance accuracy specifications",
        "target users buyer personas roles",
    ],
    "comparisons": [
        "product variants models comparison",
        "specifications comparison table",
        "advantages differentiators unique",
        "constraints limitations not suitable",
        "operating range limits environmental",
    ],
    "seo": [
        "product name category description",
        "key features value proposition",
        "specifications certifications standards",
    ],
}


# ---------------------------------------------------------------------------
# Helpers (re-usable across sections)
# ---------------------------------------------------------------------------

def _build_context(
    store: object,
    queries: list[str],
    n_results: int = 15,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Retrieve chunks from the vector store and return (text, meta_map)."""
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


def _extract_inline_cites(text: str) -> list[str]:
    """Extract [chunk-id] references from text."""
    return re.findall(r"\[(pdf-[^\]]+|url-[^\]]+)\]", text)


def _to_evidence_refs(
    cited_ids: list[str],
    meta_map: dict[str, dict[str, Any]],
) -> list[EvidenceRef]:
    """Convert chunk IDs → EvidenceRef objects using the metadata map."""
    refs: list[EvidenceRef] = []
    for cid in cited_ids:
        if not cid:
            continue
        meta = meta_map.get(cid, {})
        page = meta.get("page_number")
        pages = [page] if page and page != -1 else []
        refs.append(
            EvidenceRef(
                chunk_ids=[cid],
                source_file=meta.get("source_file", ""),
                page_numbers=pages,
                verbatim_excerpt="",
            )
        )
    return refs


def _factsheet_summary(sheet: ProductFactSheet) -> str:
    """Build a concise text summary of the fact sheet for prompt context."""
    lines = [
        f"Product: {sheet.product_name}",
        f"Category: {sheet.product_category}",
    ]
    if sheet.primary_use_cases:
        lines.append(f"Use cases: {', '.join(sheet.primary_use_cases[:6])}")
    if sheet.target_buyer_roles:
        lines.append(f"Target buyers: {', '.join(sheet.target_buyer_roles[:4])}")
    if sheet.key_specs:
        specs = [f"{s.name}: {s.value} {s.unit}".strip() for s in sheet.key_specs[:10]]
        lines.append(f"Key specs: {'; '.join(specs)}")
    if sheet.constraints:
        lines.append(f"Constraints: {'; '.join(c.statement for c in sheet.constraints[:4])}")
    if sheet.differentiators:
        lines.append(f"Differentiators: {'; '.join(d.statement for d in sheet.differentiators[:4])}")
    if sheet.certifications_standards:
        lines.append(f"Certifications: {', '.join(sheet.certifications_standards[:5])}")
    if sheet.integrations_interfaces:
        lines.append(f"Interfaces: {', '.join(sheet.integrations_interfaces[:5])}")
    if sheet.maintenance_calibration:
        lines.append(f"Maintenance: {', '.join(sheet.maintenance_calibration[:3])}")
    return "\n".join(lines)


def _render_prompt(template_name: str, **kwargs: Any) -> str:
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    return env.get_template(template_name).render(**kwargs)


# ---------------------------------------------------------------------------
# Valid-spec set for post-processing enforcement
# ---------------------------------------------------------------------------

def _build_valid_spec_set(sheet: ProductFactSheet) -> set[str]:
    """Build a set of normalised (name, value) pairs from the fact sheet."""
    specs: set[str] = set()
    for s in sheet.key_specs:
        key = f"{s.name.strip().lower()}|{s.value.strip().lower()}"
        specs.add(key)
    return specs


def _spec_is_grounded(name: str, value: str, valid: set[str]) -> bool:
    key = f"{name.strip().lower()}|{value.strip().lower()}"
    return key in valid


# ---------------------------------------------------------------------------
# Section generators
# ---------------------------------------------------------------------------

def _generate_landing_page(
    store: object,
    llm: object,
    sheet: ProductFactSheet,
    tone: str,
    length: str,
    audience: str,
    meta_map_out: dict[str, dict[str, Any]],
    valid_specs: set[str],
) -> LandingPageDraft:
    context_text, meta_map = _build_context(store, _SECTION_QUERIES["landing"])
    meta_map_out.update(meta_map)

    prompt = _render_prompt(
        "web_content_landing.j2",
        tone=tone,
        length=length,
        audience=audience,
        factsheet_summary=_factsheet_summary(sheet),
        chunk_text=context_text,
    )
    raw = llm.complete(prompt)
    data = _parse_json(raw) if raw else {}
    if not isinstance(data, dict):
        data = {}

    # Benefits
    benefits: list[BenefitItem] = []
    for b in (data.get("benefits") or []):
        if not isinstance(b, dict):
            continue
        cited = [str(c) for c in (b.get("cited_chunk_ids") or [])]
        inline = _extract_inline_cites(str(b.get("description", "")))
        all_ids = list(dict.fromkeys(cited + inline))
        benefits.append(BenefitItem(
            headline=str(b.get("headline", "")),
            description=str(b.get("description", "")),
            is_factual=bool(b.get("is_factual", True)),
            evidence=_to_evidence_refs(all_ids, meta_map),
        ))

    # Specs explained — enforce grounding
    specs_explained: list[SpecExplained] = []
    for s in (data.get("specs_explained") or []):
        if not isinstance(s, dict):
            continue
        name = str(s.get("spec_name", ""))
        value = str(s.get("spec_value", ""))
        if not _spec_is_grounded(name, value, valid_specs):
            logger.warning("Dropping ungrounded spec: %s = %s", name, value)
            continue
        cited = [str(c) for c in (s.get("cited_chunk_ids") or [])]
        inline = _extract_inline_cites(str(s.get("plain_language", "")))
        all_ids = list(dict.fromkeys(cited + inline))
        specs_explained.append(SpecExplained(
            spec_name=name,
            spec_value=value,
            unit=str(s.get("unit", "")),
            plain_language=str(s.get("plain_language", "")),
            evidence=_to_evidence_refs(all_ids, meta_map),
        ))

    # Problem / solution / how it works
    problem_text = str(data.get("problem_statement", ""))
    solution_text = str(data.get("solution_overview", ""))
    how_text = str(data.get("how_it_works", ""))

    return LandingPageDraft(
        problem_statement=problem_text,
        solution_overview=solution_text,
        benefits=benefits,
        how_it_works=how_text,
        specs_explained=specs_explained,
        call_to_action=str(data.get("call_to_action", "")),
    )


def _generate_faq(
    store: object,
    llm: object,
    sheet: ProductFactSheet,
    tone: str,
    length: str,
    audience: str,
    meta_map_out: dict[str, dict[str, Any]],
) -> list[FAQItem]:
    context_text, meta_map = _build_context(store, _SECTION_QUERIES["faq"])
    meta_map_out.update(meta_map)

    prompt = _render_prompt(
        "web_content_faq.j2",
        tone=tone,
        length=length,
        audience=audience,
        factsheet_summary=_factsheet_summary(sheet),
        chunk_text=context_text,
    )
    raw = llm.complete(prompt)
    items = _parse_json(raw) if raw else []
    if not isinstance(items, list):
        items = []

    faq_items: list[FAQItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cited = [str(c) for c in (item.get("cited_chunk_ids") or [])]
        inline = _extract_inline_cites(str(item.get("answer", "")))
        all_ids = list(dict.fromkeys(cited + inline))
        faq_items.append(FAQItem(
            question=str(item.get("question", "")),
            answer=str(item.get("answer", "")),
            is_factual=bool(item.get("is_factual", True)),
            evidence=_to_evidence_refs(all_ids, meta_map),
        ))
    return faq_items


def _generate_use_case_pages(
    store: object,
    llm: object,
    sheet: ProductFactSheet,
    tone: str,
    length: str,
    audience: str,
    meta_map_out: dict[str, dict[str, Any]],
) -> list[UseCasePageDraft]:
    context_text, meta_map = _build_context(store, _SECTION_QUERIES["usecases"])
    meta_map_out.update(meta_map)

    prompt = _render_prompt(
        "web_content_usecases.j2",
        tone=tone,
        length=length,
        audience=audience,
        factsheet_summary=_factsheet_summary(sheet),
        chunk_text=context_text,
    )
    raw = llm.complete(prompt)
    items = _parse_json(raw) if raw else []
    if not isinstance(items, list):
        items = []

    pages: list[UseCasePageDraft] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cited = [str(c) for c in (item.get("cited_chunk_ids") or [])]
        for field in ("problem_context", "solution_fit", "implementation_notes"):
            cited.extend(_extract_inline_cites(str(item.get(field, ""))))
        for b in (item.get("benefits") or []):
            cited.extend(_extract_inline_cites(str(b)))
        all_ids = list(dict.fromkeys(cited))

        pages.append(UseCasePageDraft(
            title=str(item.get("title", "")),
            slug=str(item.get("slug", "")),
            is_suggested=bool(item.get("is_suggested", False)),
            problem_context=str(item.get("problem_context", "")),
            solution_fit=str(item.get("solution_fit", "")),
            benefits=[str(b) for b in (item.get("benefits") or [])],
            implementation_notes=str(item.get("implementation_notes", "")),
            evidence=_to_evidence_refs(all_ids, meta_map),
        ))
    return pages


def _generate_comparisons(
    store: object,
    llm: object,
    sheet: ProductFactSheet,
    tone: str,
    length: str,
    audience: str,
    meta_map_out: dict[str, dict[str, Any]],
    valid_specs: set[str],
) -> list[ComparisonDraft]:
    context_text, meta_map = _build_context(store, _SECTION_QUERIES["comparisons"])
    meta_map_out.update(meta_map)

    prompt = _render_prompt(
        "web_content_comparisons.j2",
        tone=tone,
        length=length,
        audience=audience,
        factsheet_summary=_factsheet_summary(sheet),
        chunk_text=context_text,
    )
    raw = llm.complete(prompt)
    items = _parse_json(raw) if raw else []
    if not isinstance(items, list):
        items = []

    comparisons: list[ComparisonDraft] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        dimensions: list[ComparisonDimension] = []
        for d in (item.get("dimensions") or []):
            if not isinstance(d, dict):
                continue
            inline = _extract_inline_cites(str(d.get("this_product", "")))
            dimensions.append(ComparisonDimension(
                dimension=str(d.get("dimension", "")),
                this_product=str(d.get("this_product", "")),
                generic_alternative=str(d.get("generic_alternative", "")),
                evidence=_to_evidence_refs(inline, meta_map),
            ))

        best_for_raw = [str(b) for b in (item.get("best_for") or [])]
        not_ideal_raw = [str(n) for n in (item.get("not_ideal_for") or [])]

        comparisons.append(ComparisonDraft(
            title=str(item.get("title", "")),
            best_for=best_for_raw,
            not_ideal_for=not_ideal_raw,
            dimensions=dimensions,
        ))
    return comparisons


def _generate_seo(
    llm: object,
    sheet: ProductFactSheet,
    tone: str,
    audience: str,
    valid_specs: set[str],
) -> SEODraft:
    prompt = _render_prompt(
        "web_content_seo.j2",
        tone=tone,
        audience=audience,
        factsheet_summary=_factsheet_summary(sheet),
    )
    raw = llm.complete(prompt)
    data = _parse_json(raw) if raw else {}
    if not isinstance(data, dict):
        data = {}

    headings: list[SEOHeading] = []
    for h in (data.get("headings") or []):
        if not isinstance(h, dict):
            continue
        tag = h.get("tag", "h2")
        if tag not in ("h1", "h2"):
            tag = "h2"
        headings.append(SEOHeading(tag=tag, text=str(h.get("text", ""))))

    jsonld = data.get("product_jsonld", {})
    if not isinstance(jsonld, dict):
        jsonld = {}

    return SEODraft(
        title_tag=str(data.get("title_tag", "")),
        meta_description=str(data.get("meta_description", "")),
        headings=headings,
        product_jsonld=jsonld,
    )


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_factsheet(path: Path) -> ProductFactSheet:
    """Load strict ProductFactSheet from factsheet.json."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return ProductFactSheet.model_validate(data)


def load_audit(path: Path) -> tuple[Scorecard | None, list[AuditFinding]]:
    """Load audit.json → (scorecard | None, findings)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    scorecard = None
    if "scorecard" in data and data["scorecard"]:
        scorecard = Scorecard.model_validate(data["scorecard"])
    findings = [AuditFinding.model_validate(f) for f in data.get("findings", [])]
    return scorecard, findings


# ---------------------------------------------------------------------------
# Source-text sample for guardrail brand / pricing checks
# ---------------------------------------------------------------------------

_GUARDRAIL_QUERIES: list[str] = [
    "product overview description",
    "specifications features performance",
    "pricing cost list price",
    "brands manufacturer competitor comparison",
    "certifications standards compliance",
]


def _build_source_text_sample(
    store: object,
    max_chars: int = 30_000,
) -> str:
    """Retrieve a broad sample of source-document text for guardrail checks.

    The returned text is used to verify competitor-brand and pricing claims
    that appear in the generated drafts.
    """
    text, _ = _build_context(
        store,
        _GUARDRAIL_QUERIES,
        n_results=25,
        max_chars=max_chars,
    )
    return text


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def generate_web_content(
    *,
    store: object,
    llm: object,
    sheet: ProductFactSheet,
    product_id: str,
    tone: str = "neutral",
    length: str = "medium",
    audience: str = "ops_manager",
    llm_provider_name: str = "",
    llm_model_name: str = "",
    factsheet_path: str = "",
    audit_path: str = "",
) -> tuple[WebContentDrafts, GenerationMetadata]:
    """Generate all five web-content sections and return (drafts, metadata).

    Parameters
    ----------
    store : vector store instance (has .query)
    llm : LLM provider instance (has .complete)
    sheet : loaded ProductFactSheet
    product_id : project / product identifier
    tone, length, audience : generation parameters
    llm_provider_name, llm_model_name : for metadata recording
    factsheet_path, audit_path : for metadata recording
    """
    t0 = time.time()
    meta_map_all: dict[str, dict[str, Any]] = {}
    valid_specs = _build_valid_spec_set(sheet)

    # 1. Landing page
    logger.info("Generating landing page draft (tone=%s, length=%s, audience=%s)", tone, length, audience)
    landing = _generate_landing_page(store, llm, sheet, tone, length, audience, meta_map_all, valid_specs)

    # 2. FAQ
    logger.info("Generating FAQ items")
    faq = _generate_faq(store, llm, sheet, tone, length, audience, meta_map_all)

    # 3. Use-case pages
    logger.info("Generating use-case pages")
    usecases = _generate_use_case_pages(store, llm, sheet, tone, length, audience, meta_map_all)

    # 4. Comparisons
    logger.info("Generating comparison drafts")
    comparisons = _generate_comparisons(store, llm, sheet, tone, length, audience, meta_map_all, valid_specs)

    # 5. SEO
    logger.info("Generating SEO draft")
    seo = _generate_seo(llm, sheet, tone, audience, valid_specs)

    drafts = WebContentDrafts(
        landing_page=landing,
        faq=faq,
        use_case_pages=usecases,
        comparisons=comparisons,
        seo=seo,
    )

    # ------------------------------------------------------------------
    # 6. Guardrail pass — validate all draft text fields before returning
    # ------------------------------------------------------------------
    logger.info("Running post-generation guardrail pass")
    source_text = _build_source_text_sample(store)
    guardrail_warnings = run_draft_guardrails(drafts, sheet, source_text=source_text)

    elapsed = time.time() - t0

    metadata = GenerationMetadata(
        product_id=product_id,
        tone=tone,
        length=length,
        audience=audience,
        llm_provider=llm_provider_name,
        llm_model=llm_model_name,
        generated_at=__import__("datetime").datetime.utcnow(),
        generation_duration_s=round(elapsed, 2),
        factsheet_path=factsheet_path,
        audit_path=audit_path,
        guardrail_warnings=guardrail_warnings,
    )

    return drafts, metadata
