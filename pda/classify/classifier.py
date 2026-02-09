"""Document classifier: determines document type from structural signals before extraction.

Uses purely heuristic / deterministic signals — no LLM call required.

Signals analysed
----------------
* table_density       – fraction of chunks that look like table rows
* step_instruction    – presence of numbered/bulleted installation or calibration steps
* error_code          – fault / error code patterns
* multilingual        – repeated content in multiple languages
* marketing_language  – benefit / feature / value-proposition phrasing
* spec_sheet_density  – dense numeric spec tables
"""

from __future__ import annotations

import re
from typing import Any

from pda.schemas.models import (
    DocumentChunk,
    DocumentClassification,
    DocumentType,
)

# ---------------------------------------------------------------------------
# Individual signal detectors  (each returns 0.0 – 1.0)
# ---------------------------------------------------------------------------

# Patterns that suggest table-style content (pipe delimiters, tab-separated, etc.)
_TABLE_RE = re.compile(
    r"(\|.*\|)|(\t\S+\t)|(\d+\s{2,}\S+\s{2,}\S+)",
)

# Step-by-step instruction patterns
_STEP_RE = re.compile(
    r"(?i)\b(step\s+\d|fase\s+\d|schritt\s+\d|étape\s+\d"
    r"|^\s*\d+\)\s|^\s*\d+\.\s+"
    r"|install|calibrat|wir(e|ing)|mount|connect\s+to|tighten"
    r"|torque\s+to|align|remove\s+the|attach\s+the"
    r"|assemble|disassemble|fasten)",
    re.MULTILINE,
)

# Error / fault code patterns
_ERROR_CODE_RE = re.compile(
    r"(?i)\b(err(?:or)?\s*(?:code)?[\s:_-]*(?:\d+|[A-Z]{1,4}\d+))"
    r"|\bfault\s*(?:code)?[\s:_-]*\d+"
    r"|\bE\d{3,4}\b"
    r"|\balarm\s*(?:code)?[\s:_-]*\d+",
)

# Safety warning patterns
_SAFETY_RE = re.compile(
    r"(?i)\b(warning|caution|danger|do\s+not|achtung|attention"
    r"|risk\s+of|electric\s+shock|high\s+voltage|protective\s+equipment"
    r"|safety\s+glasses|hard\s+hat|lockout|tagout)\b",
)

# Marketing / benefit language
_MARKETING_RE = re.compile(
    r"(?i)\b(benefit|advantage|leading|innovative|state[\s-]of[\s-]the[\s-]art"
    r"|unmatched|best[\s-]in[\s-]class|world[\s-]class|cutting[\s-]edge"
    r"|designed\s+for|empowers|enables|ideal\s+for|perfect\s+for"
    r"|trusted\s+by|proven\s+in|delivers|offers|features?\b"
    r"|value\s+proposition|roi|total\s+cost\s+of\s+ownership"
    r"|competitive|outperform|industry[\s-]leading)\b",
)

# Spec-sheet density: lines that are mostly numbers + units
_SPEC_LINE_RE = re.compile(
    r"(?i)\d[\d.,]*\s*(?:mm|cm|m|in|ft|kg|g|lb|oz|°C|°F|K|Pa|bar|psi"
    r"|V|A|W|kW|Hz|kHz|MHz|GHz|dB|Ω|mA|μA|ppm|ppb|%RH|RH|s|ms|μs"
    r"|L|mL|gal|cfm|lpm|rpm|Nm|J|cal|lux|cd|lm)\b",
)

# Multilingual repetition: detect common non-English language markers
_MULTILINGUAL_RE = re.compile(
    r"(?i)\b(siehe|hinweis|achtung|betriebsanleitung"
    r"|voir|remarque|mise\s+en\s+garde"
    r"|véase|nota|precaución|advertencia"
    r"|vedi|nota|attenzione"
    r"|参照|注意|警告|取扱説明書"
    r"|참조|주의|경고)\b",
)


def _signal_ratio(pattern: re.Pattern, chunks: list[DocumentChunk]) -> float:
    """Fraction of chunks matching *pattern*."""
    if not chunks:
        return 0.0
    hits = sum(1 for c in chunks if pattern.search(c.text))
    return hits / len(chunks)


def _signal_count_per_chunk(pattern: re.Pattern, chunks: list[DocumentChunk]) -> float:
    """Average number of matches per chunk."""
    if not chunks:
        return 0.0
    total = sum(len(pattern.findall(c.text)) for c in chunks)
    return total / len(chunks)


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------

def classify_document(chunks: list[DocumentChunk]) -> DocumentClassification:
    """Classify the document type based on structural signals in the chunks.

    Returns a ``DocumentClassification`` with:
    * ``document_type`` — one of *product_marketing*, *technical_manual*,
      *installation_calibration*, or *mixed*.
    * ``confidence`` — 0-1 indicating how strongly the signals point to one type.
    * ``signals`` — dict of raw signal scores for debugging / transparency.
    """
    if not chunks:
        return DocumentClassification(
            document_type=DocumentType.MIXED,
            confidence=0.0,
            signals={},
        )

    signals: dict[str, Any] = {}

    # Compute raw signals
    signals["table_density"] = round(_signal_ratio(_TABLE_RE, chunks), 3)
    signals["step_instruction_ratio"] = round(_signal_ratio(_STEP_RE, chunks), 3)
    signals["step_instruction_avg"] = round(_signal_count_per_chunk(_STEP_RE, chunks), 3)
    signals["error_code_ratio"] = round(_signal_ratio(_ERROR_CODE_RE, chunks), 3)
    signals["safety_warning_ratio"] = round(_signal_ratio(_SAFETY_RE, chunks), 3)
    signals["marketing_language_ratio"] = round(_signal_ratio(_MARKETING_RE, chunks), 3)
    signals["marketing_language_avg"] = round(_signal_count_per_chunk(_MARKETING_RE, chunks), 3)
    signals["spec_line_ratio"] = round(_signal_ratio(_SPEC_LINE_RE, chunks), 3)
    signals["multilingual_ratio"] = round(_signal_ratio(_MULTILINGUAL_RE, chunks), 3)

    # --- Composite scores for each document type (0–1) ---

    # Installation / calibration guide — heavy step-by-step, error codes, safety, wiring
    install_score = (
        0.35 * min(1.0, signals["step_instruction_ratio"] * 2.0)
        + 0.20 * min(1.0, signals["error_code_ratio"] * 3.0)
        + 0.20 * min(1.0, signals["safety_warning_ratio"] * 2.5)
        + 0.15 * min(1.0, signals["multilingual_ratio"] * 3.0)
        + 0.10 * min(1.0, signals["table_density"] * 1.5)
    )

    # Technical manual / quick guide — spec-dense, some tables, moderate steps
    technical_score = (
        0.30 * min(1.0, signals["spec_line_ratio"] * 1.5)
        + 0.25 * min(1.0, signals["table_density"] * 2.0)
        + 0.15 * min(1.0, signals["step_instruction_ratio"] * 1.5)
        + 0.15 * min(1.0, signals["error_code_ratio"] * 2.0)
        + 0.10 * min(1.0, signals["safety_warning_ratio"] * 2.0)
        + 0.05 * (1.0 - min(1.0, signals["marketing_language_ratio"] * 2.0))
    )

    # Product marketing sheet — marketing language, light on steps/errors
    marketing_score = (
        0.40 * min(1.0, signals["marketing_language_ratio"] * 2.0)
        + 0.20 * min(1.0, signals["marketing_language_avg"] / 3.0)
        + 0.15 * (1.0 - min(1.0, signals["step_instruction_ratio"] * 3.0))
        + 0.10 * (1.0 - min(1.0, signals["error_code_ratio"] * 5.0))
        + 0.10 * min(1.0, signals["spec_line_ratio"] * 1.5)
        + 0.05 * (1.0 - min(1.0, signals["safety_warning_ratio"] * 3.0))
    )

    signals["_composite_install"] = round(install_score, 3)
    signals["_composite_technical"] = round(technical_score, 3)
    signals["_composite_marketing"] = round(marketing_score, 3)

    # --- Decision logic ---
    scores = {
        DocumentType.INSTALLATION_CALIBRATION: install_score,
        DocumentType.TECHNICAL_MANUAL: technical_score,
        DocumentType.PRODUCT_MARKETING: marketing_score,
    }
    best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
    best_score = scores[best_type]

    # If the gap between best and second-best is small → "mixed"
    sorted_scores = sorted(scores.values(), reverse=True)
    gap = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]

    # Thresholds
    MIN_CONFIDENCE = 0.25  # minimum composite score to claim a type
    MIN_GAP = 0.08         # minimum separation to avoid "mixed"

    if best_score < MIN_CONFIDENCE or gap < MIN_GAP:
        doc_type = DocumentType.MIXED
        confidence = round(max(0.0, 1.0 - (sorted_scores[1] / max(sorted_scores[0], 0.01))), 2)
    else:
        doc_type = best_type
        confidence = round(min(1.0, best_score + gap), 2)

    return DocumentClassification(
        document_type=doc_type,
        confidence=confidence,
        signals=signals,
    )
