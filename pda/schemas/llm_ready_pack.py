"""Schemas for the LLM-ready product content pack — four core outputs + manifest."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pda.schemas.content_pack_schemas import Citation, Tone


# ---------------------------------------------------------------------------
# 1. Canonical Answer Blocks
# ---------------------------------------------------------------------------

class CanonicalAnswerBlock(BaseModel):
    """A single canonical answer block (10-25 per pack)."""

    block_id: str = ""
    question: str = ""
    answer: str = ""
    best_for: str = ""
    not_suitable_when: str = ""
    citations: list[Citation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 2. FAQ Entry (themed)
# ---------------------------------------------------------------------------

FAQ_THEMES = [
    "selection",
    "installation",
    "accuracy_specs",
    "environment_limits",
    "compatibility_integration",
    "maintenance_calibration",
    "troubleshooting",
]


class FAQEntry(BaseModel):
    """A single FAQ entry grouped under a theme."""

    faq_id: str = ""
    theme: str = ""
    question: str = ""
    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 3. Selection Guidance
# ---------------------------------------------------------------------------

class DecisionCriterion(BaseModel):
    """A single 'Choose this product if…' criterion."""

    criterion_id: str = ""
    statement: str = ""
    citations: list[Citation] = Field(default_factory=list)


class ComparisonRow(BaseModel):
    """One row in the variant comparison table."""

    variant: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)


class SelectionGuidance(BaseModel):
    """Selection guidance output."""

    decision_criteria: list[DecisionCriterion] = Field(default_factory=list)
    comparison_table: list[ComparisonRow] = Field(default_factory=list)
    decision_tree_md: str = ""  # Markdown decision tree (or empty)
    missing_info: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 4. Use-case Pages
# ---------------------------------------------------------------------------

class UseCaseFAQ(BaseModel):
    question: str = ""
    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)


class UseCasePage(BaseModel):
    """A single use-case page (3-8 per pack)."""

    page_id: str = ""
    title: str = ""
    problem_context: str = ""
    requirements: str = ""
    why_this_product_fits: str = ""
    implementation_notes: str = ""
    faqs: list[UseCaseFAQ] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Preflight — missing facts
# ---------------------------------------------------------------------------

class MissingFactQuestion(BaseModel):
    """A targeted question to resolve a missing or ambiguous fact."""

    field: str = ""
    question: str = ""
    why_needed: str = ""


class PreflightResult(BaseModel):
    """Result of the lightweight preflight check."""

    product_name: str = ""
    facts_found: int = 0
    facts_expected: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[MissingFactQuestion] = Field(default_factory=list)
    can_generate: bool = True  # False when critical facts are missing


# ---------------------------------------------------------------------------
# Full content pack bundle
# ---------------------------------------------------------------------------

class ContentPackBundle(BaseModel):
    """The complete LLM-ready content pack."""

    project_id: str = ""
    tone: Tone = Tone.TECHNICAL
    preflight: PreflightResult = Field(default_factory=PreflightResult)
    canonical_answers: list[CanonicalAnswerBlock] = Field(default_factory=list)
    faq: list[FAQEntry] = Field(default_factory=list)
    selection_guidance: SelectionGuidance = Field(default_factory=SelectionGuidance)
    use_case_pages: list[UseCasePage] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Export manifest
# ---------------------------------------------------------------------------

class ManifestFileEntry(BaseModel):
    """One file in the export manifest."""

    filename: str = ""
    section: str = ""
    item_count: int = 0
    citation_count: int = 0


class ExportManifest(BaseModel):
    """JSON manifest describing the exported bundle."""

    project_id: str = ""
    tone: str = ""
    files: list[ManifestFileEntry] = Field(default_factory=list)
    total_citations: int = 0
    assumptions: list[str] = Field(default_factory=list)
    preflight_questions: list[MissingFactQuestion] = Field(default_factory=list)
