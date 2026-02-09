"""LLM-based audit checks: selection guidance, use-case coverage, comparability, buyer answerability, trust/citation strength."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from pda.schemas.models import DocumentChunk

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
MAX_CONTEXT_CHARS = 12_000  # cap context sent to LLM


@dataclass
class LLMCheckResult:
    """Outcome of a single LLM-based check."""

    check_id: str
    name: str
    score: int = 0          # 0-10
    max_score: int = 10
    rationale: str = ""
    evidence_chunk_ids: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def _build_context(chunks: list[DocumentChunk], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Build a textual context block from chunks."""
    parts: list[str] = []
    total = 0
    for ch in chunks:
        snippet = f"[{ch.chunk_id}] (page {ch.page_number or 'N/A'}) {ch.text[:1500]}"
        if total + len(snippet) > max_chars:
            break
        parts.append(snippet)
        total += len(snippet)
    return "\n\n".join(parts) if parts else ""


def _parse_llm_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```\w*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}


def _run_single_check(
    check_id: str,
    check_name: str,
    template_name: str,
    chunks: list[DocumentChunk],
    llm_provider: object,
    extra_vars: dict | None = None,
) -> LLMCheckResult:
    """
    Run a single LLM-based check using a Jinja2 prompt template.

    The template is expected to instruct the LLM to return JSON with:
    ``score_0_10``, ``rationale``, ``recommendations`` (list[str]),
    ``evidence_chunk_ids`` (list[str]).
    """
    context = _build_context(chunks)
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    template = env.get_template(template_name)
    variables = {"chunk_text": context, **(extra_vars or {})}
    prompt = template.render(**variables)
    raw = llm_provider.complete(prompt)
    data = _parse_llm_json(raw)

    score = max(0, min(10, int(data.get("score_0_10", 0))))
    rationale = str(data.get("rationale", raw[:500]))
    recs = data.get("recommendations", [])
    if not isinstance(recs, list):
        recs = [str(recs)]
    evidence = data.get("evidence_chunk_ids", [])
    if not isinstance(evidence, list):
        evidence = []

    return LLMCheckResult(
        check_id=check_id,
        name=check_name,
        score=score,
        rationale=rationale,
        evidence_chunk_ids=[str(e) for e in evidence],
        recommendations=[str(r) for r in recs],
    )


# ── Individual LLM checks ───────────────────────────────────────────────

def check_selection_guidance(chunks: list[DocumentChunk], llm_provider: object) -> LLMCheckResult:
    return _run_single_check(
        "selection_guidance",
        "Selection Guidance",
        "llm_check_selection_guidance.j2",
        chunks,
        llm_provider,
    )


def check_use_case_coverage(chunks: list[DocumentChunk], llm_provider: object) -> LLMCheckResult:
    return _run_single_check(
        "use_case_coverage",
        "Use-Case Coverage",
        "llm_check_use_case_coverage.j2",
        chunks,
        llm_provider,
    )


def check_comparability(chunks: list[DocumentChunk], llm_provider: object) -> LLMCheckResult:
    return _run_single_check(
        "comparability",
        "Comparability",
        "llm_check_comparability.j2",
        chunks,
        llm_provider,
    )


def check_buyer_answerability(chunks: list[DocumentChunk], llm_provider: object) -> LLMCheckResult:
    return _run_single_check(
        "buyer_answerability_llm",
        "Buyer-Question Answerability (LLM)",
        "llm_check_buyer_answerability.j2",
        chunks,
        llm_provider,
    )


def check_trust_citation_strength(chunks: list[DocumentChunk], llm_provider: object) -> LLMCheckResult:
    return _run_single_check(
        "trust_citation_strength",
        "Trust / Citation Strength",
        "llm_check_trust_citation.j2",
        chunks,
        llm_provider,
    )


# ── Run all LLM checks ──────────────────────────────────────────────────

def run_llm_checks(
    chunks: list[DocumentChunk],
    llm_provider: object,
) -> list[LLMCheckResult]:
    """Run the full set of LLM-based audit checks and return results."""
    return [
        check_selection_guidance(chunks, llm_provider),
        check_use_case_coverage(chunks, llm_provider),
        check_comparability(chunks, llm_provider),
        check_buyer_answerability(chunks, llm_provider),
        check_trust_citation_strength(chunks, llm_provider),
    ]
