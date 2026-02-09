"""Deterministic audit checks: required sections, acronym list, model naming, unit consistency."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pda.schemas.models import DocumentChunk, FactValue, ProductFactSheet


@dataclass
class CheckResult:
    """Outcome of a single deterministic check."""

    check_id: str
    name: str
    score: int = 0          # 0-10
    max_score: int = 10
    details: str = ""
    evidence_chunk_ids: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ── Required-sections check ──────────────────────────────────────────────

_REQUIRED_SECTIONS = {
    "overview": [
        r"\boverview\b", r"\bintroduction\b", r"\babout\b", r"\bsummary\b",
        r"\bproduct\s+description\b",
    ],
    "installation": [
        r"\binstallation\b", r"\bsetup\b", r"\bgetting\s+started\b",
        r"\bmounting\b", r"\bwiring\b",
    ],
    "troubleshooting": [
        r"\btroubleshoot", r"\bfaq\b", r"\bdiagnostic", r"\berror\s+code",
        r"\bcommon\s+(issues|problems)\b",
    ],
    "technical_data": [
        r"\btechnical\s+data\b", r"\bspecification", r"\btechnical\s+spec",
        r"\bperformance\s+data\b", r"\bcharacteristic",
    ],
}


def check_required_sections(chunks: list[DocumentChunk]) -> CheckResult:
    """Score 0-10: how many of the 4 required sections are present."""
    found: dict[str, list[str]] = {}
    for section_name, patterns in _REQUIRED_SECTIONS.items():
        for ch in chunks:
            searchable = " ".join(
                filter(None, [ch.section_heading, ch.heading_path, ch.text[:300]])
            ).lower()
            for pat in patterns:
                if re.search(pat, searchable, re.IGNORECASE):
                    found.setdefault(section_name, []).append(ch.chunk_id)
                    break
            if section_name in found:
                break  # section satisfied

    present = len(found)
    total = len(_REQUIRED_SECTIONS)
    score = min(10, int(present / total * 10))

    missing = [s for s in _REQUIRED_SECTIONS if s not in found]
    recs = [f"Add a dedicated '{s.replace('_', ' ').title()}' section." for s in missing]

    evidence = []
    for ids in found.values():
        evidence.extend(ids[:2])

    return CheckResult(
        check_id="required_sections",
        name="Required Sections",
        score=score,
        details=f"Found {present}/{total} required sections: {', '.join(found)}."
        + (f" Missing: {', '.join(missing)}." if missing else ""),
        evidence_chunk_ids=evidence,
        recommendations=recs,
    )


# ── Acronym list check ──────────────────────────────────────────────────

def check_acronym_list(chunks: list[DocumentChunk]) -> CheckResult:
    """Score 0 or 10: does the doc contain an acronyms/abbreviations/glossary section?"""
    acronym_patterns = [
        r"\bacronym", r"\babbreviation", r"\bglossary\b", r"\bdefinitions?\b",
    ]
    for ch in chunks:
        searchable = " ".join(
            filter(None, [ch.section_heading, ch.heading_path, ch.text[:500]])
        ).lower()
        for pat in acronym_patterns:
            if re.search(pat, searchable, re.IGNORECASE):
                return CheckResult(
                    check_id="acronym_list",
                    name="Acronym / Abbreviation List",
                    score=10,
                    details="Acronym/abbreviation section detected.",
                    evidence_chunk_ids=[ch.chunk_id],
                )
    return CheckResult(
        check_id="acronym_list",
        name="Acronym / Abbreviation List",
        score=0,
        details="No acronym/abbreviation/glossary section found.",
        recommendations=[
            "Add an Acronyms or Abbreviations section listing all product-specific abbreviations."
        ],
    )


# ── Model naming consistency ─────────────────────────────────────────────

def check_model_naming_consistency(
    chunks: list[DocumentChunk],
    fact_sheet: ProductFactSheet | None = None,
) -> CheckResult:
    """
    Score 0-10: is the product model name/number used consistently?

    Strategy: extract candidate model identifiers (from fact sheet or regex),
    then scan for close-but-different variants.
    """
    # Collect canonical candidates
    candidates: set[str] = set()
    if fact_sheet:
        for fv in [fact_sheet.product_name, fact_sheet.model_number]:
            v = _fv_str(fv)
            if v:
                candidates.add(v)

    # Also try regex: sequences like "XX-1234" or "Model XYZ"
    all_text = " ".join(ch.text for ch in chunks)
    model_re = re.compile(
        r"\b[A-Z]{2,}[\-\s]?\d{2,}[A-Z0-9\-]*\b"  # e.g. HMT120, DPT145
    )
    regex_hits = model_re.findall(all_text)
    if regex_hits:
        # Pick the most frequent as canonical
        from collections import Counter
        ctr = Counter(regex_hits)
        top = ctr.most_common(1)[0][0]
        candidates.add(top)

    if not candidates:
        return CheckResult(
            check_id="model_naming",
            name="Model Naming Consistency",
            score=5,
            details="Could not determine canonical model name to check consistency.",
        )

    # Look for inconsistent variants
    variants_found: dict[str, set[str]] = {}
    for canonical in candidates:
        canon_norm = canonical.replace("-", "").replace(" ", "").upper()
        variant_set: set[str] = set()
        for match in regex_hits:
            match_norm = match.replace("-", "").replace(" ", "").upper()
            if match_norm != canon_norm and _levenshtein_ratio(canon_norm, match_norm) > 0.6:
                variant_set.add(match)
        variants_found[canonical] = variant_set

    total_variants = sum(len(v) for v in variants_found.values())
    if total_variants == 0:
        return CheckResult(
            check_id="model_naming",
            name="Model Naming Consistency",
            score=10,
            details=f"Model name(s) ({', '.join(candidates)}) used consistently throughout the document.",
        )

    score = max(0, 10 - total_variants * 2)
    recs: list[str] = []
    for canonical, variants in variants_found.items():
        if variants:
            recs.append(
                f"Standardize model name '{canonical}' — variants found: {', '.join(sorted(variants))}."
            )
    return CheckResult(
        check_id="model_naming",
        name="Model Naming Consistency",
        score=score,
        details=f"{total_variants} variant(s) of model name detected.",
        recommendations=recs,
    )


# ── Unit consistency ─────────────────────────────────────────────────────

_UNIT_FAMILIES = {
    "temperature": {"celsius", "fahrenheit", "kelvin"},
    "length": {"mm", "cm", "inch", "inches", "feet"},
    "weight": {"kg", "lb", "oz", "lbs"},
    "pressure": {"kpa", "mpa", "bar", "psi", "atm"},
    "voltage": {"vdc", "vac"},
}

# Special patterns that can't use \b (e.g. °C, °F)
_SPECIAL_UNIT_FAMILIES = {
    "temperature": [r"°c\b", r"°f\b"],
}


def check_unit_consistency(
    chunks: list[DocumentChunk],
    fact_sheet: ProductFactSheet | None = None,
) -> CheckResult:
    """
    Score 0-10: are units used consistently across the document?

    Detects mixed unit families (e.g. both °C and °F for temperature
    without making it clear both are provided).
    """
    all_text = " ".join(ch.text for ch in chunks).lower()
    specs_text = ""
    if fact_sheet and fact_sheet.specifications:
        specs_text = " ".join(
            str(getattr(fv, "value", fv))
            for fv in fact_sheet.specifications.values()
        ).lower()
    combined = all_text + " " + specs_text

    issues: list[str] = []
    for family_name, units in _UNIT_FAMILIES.items():
        found_units = {u for u in units if re.search(rf"\b{re.escape(u)}\b", combined)}
        if len(found_units) > 1:
            issues.append(f"Mixed {family_name} units: {', '.join(sorted(found_units))}.")

    # Check special patterns (°C, °F, etc.)
    for family_name, patterns in _SPECIAL_UNIT_FAMILIES.items():
        found_special = [p for p in patterns if re.search(p, combined, re.IGNORECASE)]
        if len(found_special) > 1:
            labels = [p.replace(r"\b", "").replace("°", "°") for p in found_special]
            issues.append(f"Mixed {family_name} units: {', '.join(labels)}.")

    # Also check numeric specs without units
    missing_unit_count = 0
    if fact_sheet and fact_sheet.specifications:
        for k, fv in fact_sheet.specifications.items():
            v = _fv_str(fv)
            if v and re.match(r"^-?\d+(\.\d+)?$", v.strip()):
                missing_unit_count += 1

    if missing_unit_count:
        issues.append(f"{missing_unit_count} spec value(s) appear to be bare numbers without units.")

    total_issues = len(issues) + missing_unit_count
    score = max(0, 10 - total_issues * 2)
    return CheckResult(
        check_id="unit_consistency",
        name="Unit Consistency",
        score=score,
        details=" ".join(issues) if issues else "Units appear consistent across the document.",
        recommendations=[
            "Use a single unit system per spec (with conversions parenthetical) "
            "and ensure every numeric spec has an explicit unit."
        ]
        if total_issues > 0
        else [],
    )


# ── Run all deterministic checks ─────────────────────────────────────────

def run_deterministic_checks(
    chunks: list[DocumentChunk],
    fact_sheet: ProductFactSheet | None = None,
) -> list[CheckResult]:
    """Run the full set of deterministic checks and return results."""
    return [
        check_required_sections(chunks),
        check_acronym_list(chunks),
        check_model_naming_consistency(chunks, fact_sheet),
        check_unit_consistency(chunks, fact_sheet),
    ]


# ── helpers ──────────────────────────────────────────────────────────────

def _fv_str(fv: object) -> str | None:
    if fv is None:
        return None
    v = getattr(fv, "value", fv)
    if v is None or (isinstance(v, str) and v.strip().upper() == "NOT_FOUND"):
        return None
    return str(v).strip()


def _levenshtein_ratio(a: str, b: str) -> float:
    """Quick Levenshtein similarity ratio (0-1)."""
    if not a or not b:
        return 0.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0
    # Simple DP edit distance
    rows = len(a) + 1
    cols = len(b) + 1
    prev = list(range(cols))
    for i in range(1, rows):
        curr = [i] + [0] * (cols - 1)
        for j in range(1, cols):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return 1.0 - prev[-1] / max_len
