"""Pydantic models — single source of truth for DocumentChunk, ProductFactSheet, AuditFinding, Scorecard, PromptTestResult."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChunkSource(str, Enum):
    PDF = "pdf"
    URL = "url"


class DocumentChunk(BaseModel):
    """A single text chunk from a PDF or URL with source metadata."""

    chunk_id: str  # e.g. "pdf-p3-c2" (source-page-chunk_index)
    source_type: ChunkSource
    source_file: str  # filename or URL
    page_number: int | None = None  # None for URL sources
    section_heading: str | None = None  # detected heading above chunk
    heading_path: str | None = None  # for URL: e.g. "Intro / Features"
    text: str = ""
    char_offset_start: int = 0
    char_offset_end: int = 0
    token_count: int = 0
    metadata: dict[str, Any] = {}  # extensible (table flag, image_ref, etc.)


class IngestionChunk(BaseModel):
    """Output format for ingestion layer (chunks.jsonl)."""

    chunk_id: str
    source_type: Literal["pdf", "url"]
    source_ref: str  # pdf filename or url
    page_num: int | None = None  # PDF only
    heading_path: str | None = None  # URL only
    section_title: str | None = None
    text: str = ""


class EvidenceRef(BaseModel):
    """Reference to source evidence (chunk IDs, page, verbatim excerpt)."""

    chunk_ids: list[str] = []
    source_file: str = ""
    page_numbers: list[int] = []
    section: str | None = None
    verbatim_excerpt: str = ""


class FactValue(BaseModel):
    """A single extracted fact with confidence and evidence."""

    value: Any = "NOT_FOUND"  # str, number, list, etc.; use "NOT_FOUND" when missing
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    evidence: list[EvidenceRef] = []


class ProductFactSheet(BaseModel):
    """Structured product facts extracted from source; missing fields use NOT_FOUND."""

    product_name: FactValue = FactValue()
    manufacturer: FactValue = FactValue()
    model_number: FactValue = FactValue()
    category: FactValue = FactValue()
    short_description: FactValue = FactValue()
    key_features: list[FactValue] = []
    specifications: dict[str, FactValue] = {}  # key = spec name
    use_cases: list[FactValue] = []
    target_audience: FactValue = FactValue()
    pricing: FactValue = FactValue()
    certifications: list[FactValue] = []
    compatibility: list[FactValue] = []
    warranty: FactValue = FactValue()
    support_info: FactValue = FactValue()


class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingCategory(str, Enum):
    COMPLETENESS = "completeness"
    STRUCTURE = "structure"
    CONSISTENCY = "consistency"
    SCHEMA_MARKUP = "schema_markup"
    DISCOVERABILITY = "discoverability"
    ACCURACY = "accuracy"


class AuditFinding(BaseModel):
    """A single audit finding (grounded or generated recommendation)."""

    finding_id: str = ""
    category: FindingCategory = FindingCategory.COMPLETENESS
    severity: FindingSeverity = FindingSeverity.INFO
    title: str = ""
    description: str = ""
    evidence: list[EvidenceRef] = []
    is_grounded: bool = True  # True = from source; False = generated rec
    recommendation: str | None = None
    critic_verified: bool = False
    critic_note: str | None = None


class RubricDimension(BaseModel):
    """One dimension of the LLM-readiness scorecard."""

    dimension_id: str = ""
    name: str = ""
    weight: float = 0.0  # 0.0-1.0, weights sum to 1.0
    max_score: int = 10
    score: int = 0
    scoring_method: Literal["deterministic", "llm_rubric"] = "deterministic"
    evidence: list[EvidenceRef] = []
    details: str = ""


class Scorecard(BaseModel):
    """Full LLM-readiness scorecard with dimensions and findings."""

    overall_score: float = 0.0  # weighted average, 0-100
    grade: Literal["A", "B", "C", "D", "F"] = "F"
    dimensions: list[RubricDimension] = []
    findings: list[AuditFinding] = []
    generated_at: datetime = Field(default_factory=datetime.now)


class SinglePromptResult(BaseModel):
    """Result of running one buyer prompt against the content."""

    prompt_id: str = ""
    buyer_prompt: str = ""
    llm_response: str = ""
    facts_cited: list[str] = []
    grounding_score: float = 0.0
    missing_info: list[str] = []


class PromptTestResult(BaseModel):
    """Results for one variant (original or optimized) in the buyer-prompt simulator."""

    variant_label: str = ""
    source_description: str = ""
    results: list[SinglePromptResult] = []
    average_grounding: float = 0.0
    diff_vs_baseline: dict[str, float] | None = None  # per-prompt delta if 2 variants


# --- Buyer-Prompt Simulator (factsheet-based rubric scoring) ---


class SimulatorRubricScores(BaseModel):
    """Per-prompt rubric scores from factsheet-based evaluation."""

    factual_correctness: int = 0  # 0-10
    differentiator_coverage: int = 0  # 0-10
    constraint_correctness: int = 0  # 0-10
    hallucination_flags: list[str] = []


class SimulatorPromptResult(BaseModel):
    """Single prompt: question, answer, and rubric scores."""

    prompt_id: str = ""
    category: str = ""
    buyer_prompt: str = ""
    response: str = ""
    factual_correctness: int = 0
    differentiator_coverage: int = 0
    constraint_correctness: int = 0
    hallucination_flags: list[str] = []


class SimulatorAggregateMetrics(BaseModel):
    """Aggregate metrics for one variant run."""

    avg_factual_correctness: float = 0.0
    avg_differentiator_coverage: float = 0.0
    avg_constraint_correctness: float = 0.0
    total_hallucination_count: int = 0
    prompts_with_hallucinations: int = 0


class SimulatorRunResult(BaseModel):
    """Full result for one variant (A or B) in the Buyer-Prompt Simulator."""

    variant_label: str = ""
    results: list[SimulatorPromptResult] = []
    aggregate_metrics: SimulatorAggregateMetrics = SimulatorAggregateMetrics()
