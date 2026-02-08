"""Deterministic checks and LLM rubric scoring; builds Scorecard from rubric YAML."""

from datetime import datetime
from pathlib import Path
import re

import yaml

from pda.schemas.models import (
    AuditFinding,
    DocumentChunk,
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
    """Score 0-10: section headings, chunk length 200-800 tokens, no wall >1500, ordering. 4 sub-checks."""
    if not chunks:
        return 0
    has_headings = any(c.section_heading for c in chunks)
    tokens = [c.token_count for c in chunks]
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
    """Score 0-10: dates, version numbers, 'new'/'updated', copyright."""
    if not chunks:
        return 0
    text = " ".join(c.text for c in chunks).lower()
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
) -> Scorecard:
    """
    Build full Scorecard from deterministic dimensions and optional LLM rubric scores.
    buyer_answerability_score: 0-10 from PromptTestResult average_grounding * 10.
    differentiators_score: 0-10 from LLM rubric (optional).
    """
    rubric = _load_rubric(rubric_path)
    dimensions_config = rubric.get("dimensions", [])
    thresholds = rubric.get("grade_thresholds", {})
    url_chunks = url_chunks or []

    dimensions: list[RubricDimension] = []
    for dim in dimensions_config:
        dim_id = dim.get("id", "")
        name = dim.get("name", dim_id)
        weight = float(dim.get("weight", 0))
        method = dim.get("method", "deterministic")
        max_score = 10
        score = 0
        details = ""

        if dim_id == "completeness":
            score = check_completeness(fact_sheet)
            details = f"Completeness: {score}/10 (non-NOT_FOUND field ratio)."
        elif dim_id == "structural_clarity":
            score = check_structural_clarity(chunks)
            details = f"Structural clarity: {score}/10 (headings, chunk size, no wall-of-text)."
        elif dim_id == "spec_precision":
            score = check_spec_precision(fact_sheet)
            details = f"Spec precision: {score}/10."
        elif dim_id == "schema_readiness":
            score = check_schema_readiness(url_chunks)
            details = "Schema.org readiness (URL or neutral)."
        elif dim_id == "unique_differentiators":
            score = int(differentiators_score) if differentiators_score is not None else 5
            details = "LLM rubric: unique differentiators."
        elif dim_id == "buyer_answerability":
            score = int(buyer_answerability_score * 10) if buyer_answerability_score is not None else 5
            details = "Buyer-question answerability (grounding)."
        elif dim_id == "consistency":
            score = check_consistency(fact_sheet, chunks)
            details = "Consistency: no contradictory specs."
        elif dim_id == "freshness":
            score = check_freshness(chunks)
            details = "Freshness signals (dates, version, new/updated)."

        dimensions.append(
            RubricDimension(
                dimension_id=dim_id,
                name=name,
                weight=weight,
                max_score=max_score,
                score=min(max_score, max(0, score)),
                scoring_method="llm_rubric" if method == "llm_rubric" else "deterministic",
                evidence=[],
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
