"""Pydantic models for the web-ready content generation endpoint.

Covers request, per-section draft models, the full WebContentDrafts bundle,
and the top-level response envelope.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Guardrail warning — emitted when the post-generation guardrail layer
# detects an ungrounded claim in a draft text field.
# ---------------------------------------------------------------------------

class GuardrailWarning(BaseModel):
    """A warning produced by the post-generation guardrail validation layer."""

    category: Literal[
        "ungrounded_numeric_spec",
        "ungrounded_certification",
        "competitor_brand",
        "ungrounded_pricing",
    ]
    severity: Literal["removed", "replaced", "flagged"] = "replaced"
    field_path: str = ""  # e.g. "landing_page.benefits[0].description"
    original_snippet: str = ""
    replacement: str = ""
    detail: str = ""


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class GenerateWebContentRequest(BaseModel):
    """Body for POST /api/products/{product_id}/generate-content."""

    tone: Literal["neutral", "technical", "marketing"] = "neutral"
    length: Literal["short", "medium", "long"] = "medium"
    audience: Literal["engineer", "procurement", "ops_manager"] = "ops_manager"

    # Optional LLM overrides (consistent with other routes)
    llm_provider: str | None = None
    llm_model: str | None = None


# ---------------------------------------------------------------------------
# Evidence wrapper — every factual claim must carry this
# ---------------------------------------------------------------------------

class EvidenceRef(BaseModel):
    """Pointer back to an extracted fact / source chunk."""

    chunk_ids: list[str] = Field(default_factory=list)
    source_file: str = ""
    page_numbers: list[int] = Field(default_factory=list)
    verbatim_excerpt: str = ""


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

class BenefitItem(BaseModel):
    headline: str = ""
    description: str = ""
    is_factual: bool = True
    evidence: list[EvidenceRef] = Field(default_factory=list)


class SpecExplained(BaseModel):
    """A numeric spec with plain-language explanation — must be grounded."""

    spec_name: str = ""
    spec_value: str = ""
    unit: str = ""
    plain_language: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)


class LandingPageDraft(BaseModel):
    """Problem-first landing page structure."""

    problem_statement: str = ""
    solution_overview: str = ""
    benefits: list[BenefitItem] = Field(default_factory=list)
    how_it_works: str = ""
    specs_explained: list[SpecExplained] = Field(default_factory=list)
    call_to_action: str = ""


# ---------------------------------------------------------------------------
# FAQ
# ---------------------------------------------------------------------------

class FAQItem(BaseModel):
    question: str = ""
    answer: str = ""
    is_factual: bool = True  # False ⇒ suggested / editorial
    evidence: list[EvidenceRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Use-case pages
# ---------------------------------------------------------------------------

class UseCasePageDraft(BaseModel):
    title: str = ""
    slug: str = ""
    is_suggested: bool = False  # True ⇒ not explicitly in source
    problem_context: str = ""
    solution_fit: str = ""
    benefits: list[str] = Field(default_factory=list)
    implementation_notes: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------

class ComparisonDimension(BaseModel):
    dimension: str = ""
    this_product: str = ""
    generic_alternative: str = ""  # no competitor names unless in source
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ComparisonDraft(BaseModel):
    title: str = ""
    best_for: list[str] = Field(default_factory=list)
    not_ideal_for: list[str] = Field(default_factory=list)
    dimensions: list[ComparisonDimension] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SEO
# ---------------------------------------------------------------------------

class SEOHeading(BaseModel):
    tag: Literal["h1", "h2"] = "h2"
    text: str = ""


class SEODraft(BaseModel):
    title_tag: str = ""
    meta_description: str = ""
    headings: list[SEOHeading] = Field(default_factory=list)
    product_jsonld: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Full drafts bundle
# ---------------------------------------------------------------------------

class WebContentDrafts(BaseModel):
    """Complete set of web-ready content drafts for one product."""

    landing_page: LandingPageDraft = Field(default_factory=LandingPageDraft)
    faq: list[FAQItem] = Field(default_factory=list)
    use_case_pages: list[UseCasePageDraft] = Field(default_factory=list)
    comparisons: list[ComparisonDraft] = Field(default_factory=list)
    seo: SEODraft = Field(default_factory=SEODraft)


# ---------------------------------------------------------------------------
# Generation metadata
# ---------------------------------------------------------------------------

class GenerationMetadata(BaseModel):
    product_id: str = ""
    tone: str = ""
    length: str = ""
    audience: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    token_usage: dict[str, int] = Field(
        default_factory=dict,
        description="Token counts if available: prompt_tokens, completion_tokens, total_tokens.",
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generation_duration_s: float = 0.0
    factsheet_path: str = ""
    audit_path: str = ""
    guardrail_warnings: list[GuardrailWarning] = Field(
        default_factory=list,
        description="Warnings emitted by the post-generation guardrail layer.",
    )


# ---------------------------------------------------------------------------
# Response envelope (sync — kept for internal use)
# ---------------------------------------------------------------------------

class GenerateWebContentResponse(BaseModel):
    """Top-level response for POST /api/products/{product_id}/generate-content."""

    drafts: WebContentDrafts = Field(default_factory=WebContentDrafts)
    metadata: GenerationMetadata = Field(default_factory=GenerationMetadata)


# ---------------------------------------------------------------------------
# Async job responses
# ---------------------------------------------------------------------------

class GenerateContentJobResponse(BaseModel):
    """Immediate response for POST /api/products/{product_id}/generate-content."""

    job_id: str = ""
    status: str = "queued"


class GenerationJobStatusResponse(BaseModel):
    """Response for GET /api/generation-jobs/{job_id}."""

    job_id: str = ""
    product_id: str = ""
    status: str = ""
    progress: int = 0
    drafts: WebContentDrafts | None = None
    metadata: GenerationMetadata | None = None
    error_message: str | None = None
    created_at: str = ""
    updated_at: str = ""
