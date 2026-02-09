"""Deterministic checks and LLM rubric scoring; builds Scorecard from rubric YAML.

When a ``DocumentClassification`` is provided the scoring logic adapts:

* **Structural clarity** and **freshness** are evaluated only on *buyer* chunks
  so that operational boilerplate (installation steps, wiring diagrams, safety
  warnings, multilingual duplicates) does not inflate or deflate scores.
* **Buyer answerability** (grounding from prompt simulation) should already be
  fed a buyer-only chunk set by the caller.
* Dimensions that depend on the fact sheet (completeness, spec precision, etc.)
  are unaffected because the fact sheet itself should be extracted primarily
  from buyer-relevant content.
"""

from datetime import datetime
from pathlib import Path
import re

import yaml

from pda.schemas.models import (
    AuditFinding,
    ContentRole,
    DocumentChunk,
    DocumentClassification,
    DocumentType,
    EvidenceRef,
    ProductFactSheet,
    RubricDimension,
    Scorecard,
)

RUBRICS_DIR = Path(__file__).resolve().parent.parent.parent / "rubrics"


def _not_found(v: object) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and v.strip().upper() == "NOT_FOUND":
        return True
    return False


def _fact_filled(fv: object) -> bool:
    if fv is None:
        return False
    if hasattr(fv, "value"):
        return not _not_found(getattr(fv, "value", None))
    return not _not_found(fv)


def check_completeness(fact_sheet: ProductFactSheet) -> int:
    """Score 0-10: fraction of non-NOT_FOUND fields. 10 if >=90%, 7 if >=70%, 4 if >=50%, 0 if <30%."""
    slots = [
        fact_sheet.product_name,
        fact_sheet.manufacturer,
        fact_sheet.model_number,
        fact_sheet.category,
        fact_sheet.short_description,
        fact_sheet.target_audience,
        fact_sheet.pricing,
        fact_sheet.warranty,
        fact_sheet.support_info,
    ]
    filled = sum(1 for s in slots if _fact_filled(s))
    if fact_sheet.key_features:
        filled += 1
    if fact_sheet.specifications:
        filled += 1
    if fact_sheet.use_cases:
        filled += 1
    if fact_sheet.certifications:
        filled += 1
    if fact_sheet.compatibility:
        filled += 1
    total = 14
    ratio = filled / total if total else 0
    if ratio >= 0.9:
        return 10
    if ratio >= 0.7:
        return 7
    if ratio >= 0.5:
        return 4
    return 0


def check_structural_clarity(chunks: list[DocumentChunk]) -> int:
    """Score 0-10: section headings, chunk length 200-800 tokens, no wall >1500, ordering. 4 sub-checks.

    Uses only *buyer*-tagged chunks so operational boilerplate doesn't dilute the signal.
    Falls back to all chunks if none are tagged buyer.
    """
    buyer = [c for c in chunks if c.content_role == ContentRole.BUYER] or chunks
    if not buyer:
        return 0
    has_headings = any(c.section_heading for c in buyer)
    tokens = [c.token_count for c in buyer]
    avg = sum(tokens) / len(tokens) if tokens else 0
    good_length = 200 <= avg <= 800
    no_wall = not any(t > 1500 for t in tokens)
    ordering = True  # assume logical if we have chunks
    checks = sum([has_headings, good_length, no_wall, ordering])
    return max(0, min(10, int(checks * 2.5)))


def check_spec_precision(fact_sheet: ProductFactSheet) -> int:
    """Score 0-10: specs with units/ranges/numbers vs vague. Deterministic: count precise vs total."""
    specs = fact_sheet.specifications or {}
    if not specs:
        return 5  # no specs = neutral
    precise = 0
    for fv in specs.values():
        v = getattr(fv, "value", fv) if hasattr(fv, "value") else fv
        if _not_found(v):
            continue
        s = str(v).lower()
        if re.search(r"\d+\s*(mm|cm|kg|g|hz|mb|gb|v|w|a)", s) or re.search(r"\d+\s*[-–]\s*\d+", s):
            precise += 1
        elif isinstance(v, (int, float)):
            precise += 1
    total = len(specs)
    ratio = precise / total if total else 0
    return max(0, min(10, int(ratio * 10)))


def check_schema_readiness(url_chunks: list[DocumentChunk] | None) -> int:
    """Score 0-10: URL JSON-LD/microdata or how well facts map to schema.org. No URL = score from fact coverage."""
    if not url_chunks:
        return 5  # no URL: neutral
    # Could fetch URL and check for Product schema; for MVP score by having key fields
    return 5


def check_consistency(fact_sheet: ProductFactSheet, chunks: list[DocumentChunk]) -> int:
    """Score 0-10: no contradictory specs. Start at 10, deduct for conflicts."""
    specs = fact_sheet.specifications or {}
    # Simple: no duplicate-named specs with different values
    return 10 if len(specs) == len(set(str(k).lower() for k in specs)) else 7


def check_freshness(chunks: list[DocumentChunk]) -> int:
    """Score 0-10: dates, version numbers, 'new'/'updated', copyright.

    Evaluated on buyer-tagged chunks only so boilerplate copyright in
    operational pages doesn't skew the result.
    """
    buyer = [c for c in chunks if c.content_role == ContentRole.BUYER] or chunks
    if not buyer:
        return 0
    text = " ".join(c.text for c in buyer).lower()
    score = 0
    if re.search(r"\d{4}", text):
        score += 3
    if re.search(r"version\s*\d|v\d+\.\d+", text, re.I):
        score += 3
    if re.search(r"\bnew\b|\bupdated\b|\bcurrent\b", text):
        score += 2
    if "copyright" in text or "©" in text:
        score += 2
    return min(10, score)


def _load_rubric(path: Path | None = None) -> dict:
    path = path or RUBRICS_DIR / "default.yaml"
    if not path.exists():
        return {"dimensions": [], "grade_thresholds": {"A": 85, "B": 70, "C": 55, "D": 40, "F": 0}}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _score_to_grade(score: float, thresholds: dict) -> str:
    if score >= thresholds.get("A", 85):
        return "A"
    if score >= thresholds.get("B", 70):
        return "B"
    if score >= thresholds.get("C", 55):
        return "C"
    if score >= thresholds.get("D", 40):
        return "D"
    return "F"


def build_scorecard(
    fact_sheet: ProductFactSheet,
    chunks: list[DocumentChunk],
    url_chunks: list[DocumentChunk] | None = None,
    rubric_path: Path | None = None,
    buyer_answerability_score: float | None = None,
    differentiators_score: float | None = None,
    classification: DocumentClassification | None = None,
    deterministic_results: dict | None = None,
    llm_results: dict | None = None,
) -> Scorecard:
    """
    Build full Scorecard from deterministic dimensions and optional LLM rubric scores.

    buyer_answerability_score: 0-10 from PromptTestResult average_grounding * 10.
    differentiators_score: 0-10 from LLM rubric (optional).
    classification: if provided, downstream checks use only buyer-tagged chunks so
        operational noise (installation steps, wiring, error codes) does not inflate
        or deflate LLM-discoverability scores.
    deterministic_results: {check_id: CheckResult} from deterministic_checks module.
    llm_results: {check_id: LLMCheckResult} from llm_checks module.
    """
    rubric = _load_rubric(rubric_path)
    dimensions_config = rubric.get("dimensions", [])
    thresholds = rubric.get("grade_thresholds", {})
    url_chunks = url_chunks or []
    deterministic_results = deterministic_results or {}
    llm_results = llm_results or {}

    # Pre-filter buyer-only chunks for scoring dimensions that should not
    # be inflated by operational content.
    buyer_only = [c for c in chunks if c.content_role == ContentRole.BUYER]
    if not buyer_only:
        buyer_only = chunks  # fallback: use all if nothing tagged

    doc_type = classification.document_type if classification else DocumentType.MIXED

    dimensions: list[RubricDimension] = []
    for dim in dimensions_config:
        dim_id = dim.get("id", "")
        name = dim.get("name", dim_id)
        weight = float(dim.get("weight", 0))
        method = dim.get("method", "deterministic")
        max_score = 10
        score = 0
        details = ""
        evidence: list[EvidenceRef] = []

        # ── Existing deterministic checks ────────────────────────────
        if dim_id == "completeness":
            score = check_completeness(fact_sheet)
            details = f"Completeness: {score}/10 (non-NOT_FOUND field ratio)."
        elif dim_id == "structural_clarity":
            score = check_structural_clarity(buyer_only)
            details = f"Structural clarity: {score}/10 (headings, chunk size, no wall-of-text; buyer chunks only)."
        elif dim_id == "spec_precision":
            score = check_spec_precision(fact_sheet)
            details = f"Spec precision: {score}/10."
        elif dim_id == "schema_readiness":
            score = check_schema_readiness(url_chunks)
            details = "Schema.org readiness (URL or neutral)."
        elif dim_id == "consistency":
            score = check_consistency(fact_sheet, buyer_only)
            details = "Consistency: no contradictory specs."
        elif dim_id == "freshness":
            score = check_freshness(buyer_only)
            details = "Freshness signals (dates, version, new/updated; buyer chunks only)."

        # ── New deterministic checks (from deterministic_results) ────
        elif dim_id in deterministic_results:
            cr = deterministic_results[dim_id]
            score = getattr(cr, "score", 5)
            details = getattr(cr, "details", "")
            chunk_ids = getattr(cr, "evidence_chunk_ids", [])
            if chunk_ids:
                evidence = [EvidenceRef(chunk_ids=chunk_ids)]

        # ── LLM checks (from llm_results) ───────────────────────────
        elif dim_id in llm_results:
            lr = llm_results[dim_id]
            score = getattr(lr, "score", 5)
            details = getattr(lr, "rationale", "")
            chunk_ids = getattr(lr, "evidence_chunk_ids", [])
            if chunk_ids:
                evidence = [EvidenceRef(chunk_ids=chunk_ids)]

        # ── Legacy LLM dimensions (backward compat) ─────────────────
        elif dim_id == "unique_differentiators":
            score = int(differentiators_score) if differentiators_score is not None else 5
            details = "LLM rubric: unique differentiators."
        elif dim_id == "buyer_answerability":
            score = int(buyer_answerability_score * 10) if buyer_answerability_score is not None else 5
            details = "Buyer-question answerability (grounding; buyer chunks only)."

        dimensions.append(
            RubricDimension(
                dimension_id=dim_id,
                name=name,
                weight=weight,
                max_score=max_score,
                score=min(max_score, max(0, score)),
                scoring_method="llm_rubric" if method == "llm_rubric" else "deterministic",
                evidence=evidence,
                details=details,
            )
        )

    total_weight = sum(d.weight for d in dimensions)
    if total_weight <= 0:
        overall = 0.0
    else:
        overall = sum(d.score * d.weight for d in dimensions) / total_weight * 10
    grade = _score_to_grade(overall, thresholds)

    return Scorecard(
        overall_score=round(overall, 1),
        grade=grade,
        dimensions=dimensions,
        findings=[],
        generated_at=datetime.now(),
    )
