"""Draft guardrail layer — validates generated drafts before returning them.

Scans all text fields in ``WebContentDrafts`` for:

1. **Numeric specifications** not grounded in ``ProductFactSheet.key_specs``
   (or other documented fields like constraints / differentiators).
2. **Certifications / standards** not present in
   ``ProductFactSheet.certifications_standards``.
3. **Competitor brand names** not found in source document text.
4. **Pricing claims** not found in source document text.

Violations are replaced with safe placeholder wording (or flagged as
*suggested messaging*), and a ``GuardrailWarning`` is emitted for each so the
caller can surface them in the response metadata.
"""

from __future__ import annotations

import logging
import re

from pda.schemas.factsheet_schema import ProductFactSheet
from pda.schemas.web_content_schemas import (
    GuardrailWarning,
    WebContentDrafts,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Numeric spec: number(s) — possibly with ±, range, "to" — followed by a
# recognised engineering / measurement unit.
_NUMERIC_SPEC_RE = re.compile(
    r"(?:±\s*)?"
    r"\d+(?:[.,]\d+)?"
    r"(?:\s*(?:[-–]|to)\s*(?:±\s*)?\d+(?:[.,]\d+)?)?"
    r"\s*"
    r"(?:"
    # temperature
    r"°\s*[CF]"
    # electrical
    r"|[mkμµn]?A(?:C|DC)?(?=[\s,;.)\/\]\-]|$)"
    r"|[mkμµ]?V(?:DC|AC)?(?=[\s,;.)\/\]\-]|$)"
    r"|[mkμµ]?W(?=[\s,;.)\/\]\-]|$)"
    r"|[kMG]?Hz(?=[\s,;.)\/\]\-]|$)"
    # length
    r"|mm(?=[\s,;.)\/\]\-]|$)"
    r"|cm(?=[\s,;.)\/\]\-]|$)"
    r"|μm|µm|nm"
    r"|km(?=[\s,;.)\/\]\-]|$)"
    r"|(?:inches|inch|in)(?=[\s,;.)\/\]\-]|$)"
    r"|ft(?=[\s,;.)\/\]\-]|$)"
    # mass
    r"|kg(?=[\s,;.)\/\]\-]|$)"
    r"|[mkμµ]?g(?=[\s,;.)\/\]\-]|$)"
    r"|lb(?:s)?(?=[\s,;.)\/\]\-]|$)"
    r"|oz(?=[\s,;.)\/\]\-]|$)"
    # ratio / concentration
    r"|%"
    r"|ppm(?=[\s,;.)\/\]\-]|$)"
    r"|ppb(?=[\s,;.)\/\]\-]|$)"
    # pressure
    r"|[kM]?Pa(?=[\s,;.)\/\]\-]|$)"
    r"|psi(?=[\s,;.)\/\]\-]|$)"
    r"|m?bar(?=[\s,;.)\/\]\-]|$)"
    r"|atm(?=[\s,;.)\/\]\-]|$)"
    # resistance
    r"|[kM]?Ω"
    r"|ohm(?:s)?(?=[\s,;.)\/\]\-]|$)"
    # sound / signal
    r"|dB[mA]?(?=[\s,;.)\/\]\-]|$)"
    # time
    r"|ms(?=[\s,;.)\/\]\-]|$)"
    r"|μs|µs"
    r"|ns(?=[\s,;.)\/\]\-]|$)"
    # flow
    r"|[lL]/(?:min|hr|s)"
    # light
    r"|lux(?=[\s,;.)\/\]\-]|$)"
    r"|cd(?=[\s,;.)\/\]\-]|$)"
    r"|lm(?=[\s,;.)\/\]\-]|$)"
    # torque / speed
    r"|Nm(?=[\s,;.)\/\]\-]|$)"
    r"|[Rr][Pp][Mm](?=[\s,;.)\/\]\-]|$)"
    r")"
)

# IP protection rating (e.g. IP67, IP65)
_IP_RATING_RE = re.compile(r"\bIP\d{2}\b")

# Certification / standard patterns
_CERT_RE = re.compile(
    r"\b(?:"
    r"ISO\s*\d[\d:/ -]*"
    r"|IEC\s*\d[\d:/ -]*"
    r"|IECEx"
    r"|ATEX"
    r"|UL\s*\d*"
    r"|CSA"
    r"|FM\b"
    r"|CE\b"
    r"|SIL\s*\d+"
    r"|NEMA"
    r"|EN\s*\d+"
    r"|RoHS"
    r"|REACH"
    r"|MIL[- ]STD[- ]*\d+"
    r"|FDA"
    r"|NAMUR"
    r"|3-A\b"
    r"|EHEDG"
    r"|API\s*\d+"
    r"|DNV"
    r"|TÜV|TUV"
    r"|PED"
    r"|CRN"
    r")\b",
    re.IGNORECASE,
)

# Pricing patterns
_PRICE_RE = re.compile(
    r"(?:"
    r"[$€£¥]\s*\d[\d,]*(?:\.\d{1,2})?"
    r"|\d[\d,]*(?:\.\d{1,2})?\s*(?:USD|EUR|GBP|dollars?|euros?)"
    r"|(?:priced\s+at|costs?\s+|MSRP|list\s+price|starting\s+(?:at|from))\s*[:$€£¥]?\s*\d"
    r")",
    re.IGNORECASE,
)

# Proper-noun heuristic for competitor-brand detection.
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-Z]+(?:[+&][A-Z][a-zA-Z]+)*\b")

# Words that look like proper nouns but are not brand names.
_NON_BRAND_WORDS: frozenset[str] = frozenset(
    {
        # common sentence starters / determiners / misc
        "The", "This", "That", "These", "Those", "There", "Here",
        "What", "How", "Why", "When", "Where", "Which", "Who",
        "Each", "Every", "Some", "Many", "Most", "Any", "All",
        "Note", "Important", "Warning", "Caution", "Example",
        "True", "False", "None", "Yes", "No",
        # common technical / domain terms
        "FAQ", "SEO", "API", "URL", "PDF", "LED", "LCD",
        "Bluetooth", "Ethernet", "Modbus", "Profibus", "Profinet",
        "WiFi", "Internet",
        # generic nouns often capitalised in headings
        "Product", "System", "Device", "Sensor", "Instrument",
        "Meter", "Controller", "Transmitter", "Analyzer", "Analyser",
        "Monitor", "Detector", "Probe", "Valve", "Actuator", "Pump",
        "Solution", "Technology", "Alternative", "Generic", "Traditional",
        "Conventional", "Typical", "Standard", "Industrial", "Process",
        "Temperature", "Pressure", "Flow", "Level", "Humidity",
        "Accuracy", "Precision", "Range", "Resolution",
        "Installation", "Maintenance", "Calibration", "Configuration",
        "Overview", "Summary", "Introduction", "Conclusion",
        "Benefits", "Features", "Specifications", "Applications",
        "Comparison", "Versus",
    }
)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Lowercase, collapse whitespace, normalise dashes & micro sign."""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("–", "-").replace("—", "-")
    s = s.replace("μ", "µ")
    return s


# ---------------------------------------------------------------------------
# Allowed-set builders
# ---------------------------------------------------------------------------

def _build_allowed_numeric_set(sheet: ProductFactSheet) -> set[str]:
    """Build normalised set of all numeric + unit strings from the fact sheet.

    Draws from ``key_specs``, ``constraints``, ``differentiators``,
    ``maintenance_calibration``, and ``integrations_interfaces`` so that any
    documented numeric claim is considered grounded.
    """
    allowed: set[str] = set()

    for spec in sheet.key_specs:
        if not spec.value:
            continue
        # "value unit" with space
        allowed.add(_normalize(f"{spec.value} {spec.unit}"))
        # value only (may embed the unit)
        allowed.add(_normalize(spec.value))
        # collapsed (no space)
        allowed.add(_normalize(f"{spec.value}{spec.unit}"))

    # Also harvest numeric + unit fragments from free-text factsheet fields.
    _harvest_texts = []
    for c in sheet.constraints:
        _harvest_texts.append(c.statement)
    for d in sheet.differentiators:
        _harvest_texts.append(d.statement)
    for text in sheet.maintenance_calibration:
        _harvest_texts.append(text)
    for text in sheet.integrations_interfaces:
        _harvest_texts.append(text)

    for text in _harvest_texts:
        for m in _NUMERIC_SPEC_RE.finditer(text):
            allowed.add(_normalize(m.group()))
        for m in _IP_RATING_RE.finditer(text):
            allowed.add(_normalize(m.group()))

    return allowed


def _build_allowed_certs(sheet: ProductFactSheet) -> set[str]:
    """Normalised set of certifications / standards from the fact sheet."""
    return {_normalize(c) for c in sheet.certifications_standards if c}


# ---------------------------------------------------------------------------
# Grounding checks
# ---------------------------------------------------------------------------

def _numeric_is_grounded(match_text: str, allowed: set[str]) -> bool:
    """Return *True* if *match_text* appears (possibly as a substring) in the
    allowed set built from the fact sheet."""
    norm = _normalize(match_text)
    norm_nospace = re.sub(r"\s+", "", norm)

    if norm in allowed or norm_nospace in allowed:
        return True

    for a in allowed:
        a_nospace = re.sub(r"\s+", "", a)
        # Either direction substring match (covers "±0.1 °c" inside
        # "±0.1 °c at 25 °c" or vice-versa).
        if norm_nospace in a_nospace or a_nospace in norm_nospace:
            return True
        if norm in a or a in norm:
            return True

    return False


def _cert_is_grounded(cert_text: str, allowed: set[str]) -> bool:
    norm = _normalize(cert_text)
    for a in allowed:
        if norm in a or a in norm:
            return True
    return False


# ---------------------------------------------------------------------------
# Per-field text cleaner (replaces violations in-place)
# ---------------------------------------------------------------------------

def _clean_text_field(
    text: str,
    field_path: str,
    allowed_numerics: set[str],
    allowed_certs: set[str],
    product_name_lower: str,
    source_text_lower: str,
    warnings: list[GuardrailWarning],
) -> str:
    """Scan *text* for violations, replace them, and append warnings."""
    if not text or not text.strip():
        return text

    # --- 1. Numeric specs ------------------------------------------------
    def _numeric_replacer(m: re.Match) -> str:
        original = m.group()
        if _numeric_is_grounded(original, allowed_numerics):
            return original
        replacement = "[refer to datasheet]"
        warnings.append(
            GuardrailWarning(
                category="ungrounded_numeric_spec",
                severity="replaced",
                field_path=field_path,
                original_snippet=original,
                replacement=replacement,
                detail=(
                    f"Numeric spec '{original}' not found in fact sheet "
                    f"key_specs or other documented fields."
                ),
            )
        )
        logger.warning(
            "Guardrail: ungrounded numeric '%s' in %s — replaced",
            original,
            field_path,
        )
        return replacement

    result = _NUMERIC_SPEC_RE.sub(_numeric_replacer, text)

    def _ip_replacer(m: re.Match) -> str:
        original = m.group()
        if _numeric_is_grounded(original, allowed_numerics):
            return original
        replacement = "[refer to datasheet]"
        warnings.append(
            GuardrailWarning(
                category="ungrounded_numeric_spec",
                severity="replaced",
                field_path=field_path,
                original_snippet=original,
                replacement=replacement,
                detail=(
                    f"IP rating '{original}' not found in fact sheet "
                    f"key_specs or other documented fields."
                ),
            )
        )
        logger.warning(
            "Guardrail: ungrounded IP rating '%s' in %s — replaced",
            original,
            field_path,
        )
        return replacement

    result = _IP_RATING_RE.sub(_ip_replacer, result)

    # --- 2. Certifications ------------------------------------------------
    def _cert_replacer(m: re.Match) -> str:
        original = m.group()
        if _cert_is_grounded(original, allowed_certs):
            return original
        replacement = "[certification not verified]"
        warnings.append(
            GuardrailWarning(
                category="ungrounded_certification",
                severity="replaced",
                field_path=field_path,
                original_snippet=original,
                replacement=replacement,
                detail=(
                    f"Certification '{original}' not in fact sheet "
                    f"certifications_standards."
                ),
            )
        )
        logger.warning(
            "Guardrail: ungrounded certification '%s' in %s — replaced",
            original,
            field_path,
        )
        return replacement

    result = _CERT_RE.sub(_cert_replacer, result)

    # --- 3. Pricing -------------------------------------------------------
    def _price_replacer(m: re.Match) -> str:
        original = m.group()
        if source_text_lower and original.lower() in source_text_lower:
            return original  # present in source docs — allowed
        replacement = "[pricing not verified]"
        warnings.append(
            GuardrailWarning(
                category="ungrounded_pricing",
                severity="replaced",
                field_path=field_path,
                original_snippet=original,
                replacement=replacement,
                detail=(
                    f"Pricing claim '{original}' not found in source "
                    f"documents."
                ),
            )
        )
        logger.warning(
            "Guardrail: ungrounded pricing '%s' in %s — replaced",
            original,
            field_path,
        )
        return replacement

    result = _PRICE_RE.sub(_price_replacer, result)

    return result


# ---------------------------------------------------------------------------
# Competitor-brand scanner (applied to comparison sections)
# ---------------------------------------------------------------------------

def _scan_for_competitor_brands(
    text: str,
    field_path: str,
    product_name_lower: str,
    source_text_lower: str,
    warnings: list[GuardrailWarning],
) -> str:
    """Flag / replace proper nouns that look like competitor brand names.

    Applied primarily to comparison ``generic_alternative`` fields where the
    LLM is most likely to leak a competitor name.
    """
    if not text or not text.strip():
        return text

    result = text
    for m in _PROPER_NOUN_RE.finditer(text):
        word = m.group()
        # Skip short words, known non-brands, and the product's own name.
        if len(word) < 3:
            continue
        if word in _NON_BRAND_WORDS:
            continue
        word_lower = word.lower()
        if word_lower in product_name_lower:
            continue
        # If the word appears in source documents it's considered allowed.
        if source_text_lower and word_lower in source_text_lower:
            continue

        replacement = "[competitor name removed]"
        result = result.replace(word, replacement, 1)
        warnings.append(
            GuardrailWarning(
                category="competitor_brand",
                severity="replaced",
                field_path=field_path,
                original_snippet=word,
                replacement=replacement,
                detail=(
                    f"Possible competitor brand '{word}' not found in "
                    f"source documents — replaced."
                ),
            )
        )
        logger.warning(
            "Guardrail: possible competitor brand '%s' in %s — replaced",
            word,
            field_path,
        )

    return result


# ---------------------------------------------------------------------------
# Section-level cleaners
# ---------------------------------------------------------------------------

def _clean_landing_page(
    drafts: WebContentDrafts,
    allowed_numerics: set[str],
    allowed_certs: set[str],
    product_name_lower: str,
    source_text_lower: str,
    warnings: list[GuardrailWarning],
) -> None:
    lp = drafts.landing_page

    lp.problem_statement = _clean_text_field(
        lp.problem_statement, "landing_page.problem_statement",
        allowed_numerics, allowed_certs, product_name_lower,
        source_text_lower, warnings,
    )
    lp.solution_overview = _clean_text_field(
        lp.solution_overview, "landing_page.solution_overview",
        allowed_numerics, allowed_certs, product_name_lower,
        source_text_lower, warnings,
    )
    lp.how_it_works = _clean_text_field(
        lp.how_it_works, "landing_page.how_it_works",
        allowed_numerics, allowed_certs, product_name_lower,
        source_text_lower, warnings,
    )
    lp.call_to_action = _clean_text_field(
        lp.call_to_action, "landing_page.call_to_action",
        allowed_numerics, allowed_certs, product_name_lower,
        source_text_lower, warnings,
    )

    for i, benefit in enumerate(lp.benefits):
        path = f"landing_page.benefits[{i}].description"
        before = benefit.description
        benefit.description = _clean_text_field(
            benefit.description, path,
            allowed_numerics, allowed_certs, product_name_lower,
            source_text_lower, warnings,
        )
        # If the text was modified, mark the benefit as non-factual
        # (suggested messaging).
        if benefit.description != before:
            benefit.is_factual = False

    # specs_explained are already validated by _spec_is_grounded in the
    # generator; run the text cleaner on plain_language for extra safety.
    for i, spec in enumerate(lp.specs_explained):
        path = f"landing_page.specs_explained[{i}].plain_language"
        spec.plain_language = _clean_text_field(
            spec.plain_language, path,
            allowed_numerics, allowed_certs, product_name_lower,
            source_text_lower, warnings,
        )


def _clean_faq(
    drafts: WebContentDrafts,
    allowed_numerics: set[str],
    allowed_certs: set[str],
    product_name_lower: str,
    source_text_lower: str,
    warnings: list[GuardrailWarning],
) -> None:
    for i, item in enumerate(drafts.faq):
        path = f"faq[{i}].answer"
        before = item.answer
        item.answer = _clean_text_field(
            item.answer, path,
            allowed_numerics, allowed_certs, product_name_lower,
            source_text_lower, warnings,
        )
        if item.answer != before:
            item.is_factual = False


def _clean_use_case_pages(
    drafts: WebContentDrafts,
    allowed_numerics: set[str],
    allowed_certs: set[str],
    product_name_lower: str,
    source_text_lower: str,
    warnings: list[GuardrailWarning],
) -> None:
    for i, page in enumerate(drafts.use_case_pages):
        for field_name in ("problem_context", "solution_fit", "implementation_notes"):
            path = f"use_case_pages[{i}].{field_name}"
            before = getattr(page, field_name)
            cleaned = _clean_text_field(
                before, path,
                allowed_numerics, allowed_certs, product_name_lower,
                source_text_lower, warnings,
            )
            setattr(page, field_name, cleaned)

        for j, benefit in enumerate(page.benefits):
            path = f"use_case_pages[{i}].benefits[{j}]"
            cleaned = _clean_text_field(
                benefit, path,
                allowed_numerics, allowed_certs, product_name_lower,
                source_text_lower, warnings,
            )
            page.benefits[j] = cleaned


def _clean_comparisons(
    drafts: WebContentDrafts,
    allowed_numerics: set[str],
    allowed_certs: set[str],
    product_name_lower: str,
    source_text_lower: str,
    warnings: list[GuardrailWarning],
) -> None:
    for i, comp in enumerate(drafts.comparisons):
        for j, dim in enumerate(comp.dimensions):
            # Clean this_product text
            path_tp = f"comparisons[{i}].dimensions[{j}].this_product"
            dim.this_product = _clean_text_field(
                dim.this_product, path_tp,
                allowed_numerics, allowed_certs, product_name_lower,
                source_text_lower, warnings,
            )
            # Clean generic_alternative text (+ competitor brand check)
            path_ga = f"comparisons[{i}].dimensions[{j}].generic_alternative"
            dim.generic_alternative = _clean_text_field(
                dim.generic_alternative, path_ga,
                allowed_numerics, allowed_certs, product_name_lower,
                source_text_lower, warnings,
            )
            dim.generic_alternative = _scan_for_competitor_brands(
                dim.generic_alternative, path_ga,
                product_name_lower, source_text_lower, warnings,
            )

        # best_for / not_ideal_for lists
        for j, text in enumerate(comp.best_for):
            path = f"comparisons[{i}].best_for[{j}]"
            comp.best_for[j] = _clean_text_field(
                text, path,
                allowed_numerics, allowed_certs, product_name_lower,
                source_text_lower, warnings,
            )
        for j, text in enumerate(comp.not_ideal_for):
            path = f"comparisons[{i}].not_ideal_for[{j}]"
            comp.not_ideal_for[j] = _clean_text_field(
                text, path,
                allowed_numerics, allowed_certs, product_name_lower,
                source_text_lower, warnings,
            )


def _clean_seo(
    drafts: WebContentDrafts,
    allowed_numerics: set[str],
    allowed_certs: set[str],
    product_name_lower: str,
    source_text_lower: str,
    warnings: list[GuardrailWarning],
) -> None:
    seo = drafts.seo
    seo.title_tag = _clean_text_field(
        seo.title_tag, "seo.title_tag",
        allowed_numerics, allowed_certs, product_name_lower,
        source_text_lower, warnings,
    )
    seo.meta_description = _clean_text_field(
        seo.meta_description, "seo.meta_description",
        allowed_numerics, allowed_certs, product_name_lower,
        source_text_lower, warnings,
    )
    for i, h in enumerate(seo.headings):
        path = f"seo.headings[{i}].text"
        h.text = _clean_text_field(
            h.text, path,
            allowed_numerics, allowed_certs, product_name_lower,
            source_text_lower, warnings,
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_draft_guardrails(
    drafts: WebContentDrafts,
    sheet: ProductFactSheet,
    source_text: str = "",
) -> list[GuardrailWarning]:
    """Run the full guardrail validation pass on *drafts* **in-place**.

    Parameters
    ----------
    drafts:
        The generated ``WebContentDrafts`` — modified in-place.  Text fields
        containing ungrounded claims are replaced with safe placeholders and
        ``is_factual`` flags are set to ``False`` where applicable.
    sheet:
        The ``ProductFactSheet`` used during generation.  Provides the ground
        truth for numeric specs, certifications, etc.
    source_text:
        Concatenated source-document chunk text used during generation.
        Used to verify competitor-brand and pricing claims.  If empty,
        brand / pricing checks fall back to the fact sheet only.

    Returns
    -------
    list[GuardrailWarning]
        Every warning emitted during the scan.  The caller should attach
        these to ``GenerationMetadata.guardrail_warnings``.
    """
    warnings: list[GuardrailWarning] = []

    allowed_numerics = _build_allowed_numeric_set(sheet)
    allowed_certs = _build_allowed_certs(sheet)
    product_name_lower = _normalize(sheet.product_name)
    source_text_lower = source_text.lower() if source_text else ""

    _clean_landing_page(
        drafts, allowed_numerics, allowed_certs,
        product_name_lower, source_text_lower, warnings,
    )
    _clean_faq(
        drafts, allowed_numerics, allowed_certs,
        product_name_lower, source_text_lower, warnings,
    )
    _clean_use_case_pages(
        drafts, allowed_numerics, allowed_certs,
        product_name_lower, source_text_lower, warnings,
    )
    _clean_comparisons(
        drafts, allowed_numerics, allowed_certs,
        product_name_lower, source_text_lower, warnings,
    )
    _clean_seo(
        drafts, allowed_numerics, allowed_certs,
        product_name_lower, source_text_lower, warnings,
    )

    if warnings:
        logger.info(
            "Guardrail pass complete: %d warning(s) emitted "
            "(numeric=%d, cert=%d, brand=%d, pricing=%d)",
            len(warnings),
            sum(1 for w in warnings if w.category == "ungrounded_numeric_spec"),
            sum(1 for w in warnings if w.category == "ungrounded_certification"),
            sum(1 for w in warnings if w.category == "competitor_brand"),
            sum(1 for w in warnings if w.category == "ungrounded_pricing"),
        )
    else:
        logger.info("Guardrail pass complete: no warnings — all claims grounded.")

    return warnings
