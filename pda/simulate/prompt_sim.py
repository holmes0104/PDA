"""Buyer-prompt simulator: run canonical prompts against content, compute grounding, optional before/after diff."""

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from pda.schemas.models import DocumentChunk, PromptTestResult, SinglePromptResult

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

# Canonical buyer prompts (5–8)
DEFAULT_BUYER_PROMPTS = [
    "What is this product and who is it for?",
    "What are the main features and benefits?",
    "What are the key specifications or technical details?",
    "How much does it cost and what are the purchase options?",
    "What warranty or support is included?",
    "How does this compare to alternatives or competitors?",
]

MAX_CHUNK_CHARS = 8000


def _chunk_context(chunks: list[DocumentChunk]) -> str:
    total = 0
    parts = []
    for c in chunks:
        if total + len(c.text) > MAX_CHUNK_CHARS:
            break
        parts.append(f"[{c.chunk_id}] (page {c.page_number or 'N/A'})\n{c.text[:1500]}")
        total += len(c.text)
    return "\n\n".join(parts) if parts else "\n\n".join(f"[{c.chunk_id}]\n{c.text[:500]}" for c in chunks[:10])


def _grounding_score(response: str, chunk_ids: list[str]) -> float:
    """0-1: fraction of cited chunk IDs + penalty for 'not stated'."""
    if not response or not chunk_ids:
        return 0.0
    response_lower = response.lower()
    if "not stated" in response_lower or "not in the source" in response_lower:
        return 0.2
    cited = sum(1 for cid in chunk_ids if cid in response)
    return min(1.0, 0.3 + 0.7 * (cited / max(1, len(chunk_ids))))


def _cited_chunk_ids(response: str, chunk_ids: list[str]) -> list[str]:
    return [cid for cid in chunk_ids if cid in response]


def _missing_info(response: str) -> list[str]:
    if "not stated" in response.lower() or "not in the source" in response.lower():
        return ["Information not found in source."]
    return []


def run_prompt_simulation(
    chunks: list[DocumentChunk],
    llm_provider: object,
    variant_label: str = "original",
    source_description: str = "PDF brochure",
    buyer_prompts: list[str] | None = None,
) -> PromptTestResult:
    """
    Run each buyer prompt with chunk context, collect response and grounding.
    llm_provider must have .complete(prompt: str) -> str.
    """
    prompts = buyer_prompts or DEFAULT_BUYER_PROMPTS
    chunk_ids = [c.chunk_id for c in chunks]
    context = _chunk_context(chunks)
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    template = env.get_template("buyer_sim.j2")
    results: list[SinglePromptResult] = []
    for i, q in enumerate(prompts):
        prompt = template.render(chunk_text=context, buyer_prompt=q)
        raw = llm_provider.complete(prompt)
        score = _grounding_score(raw, chunk_ids)
        results.append(
            SinglePromptResult(
                prompt_id=f"P{i+1}",
                buyer_prompt=q,
                llm_response=raw[:2000],
                facts_cited=_cited_chunk_ids(raw, chunk_ids),
                grounding_score=round(score, 2),
                missing_info=_missing_info(raw),
            )
        )
    avg = sum(r.grounding_score for r in results) / len(results) if results else 0.0
    return PromptTestResult(
        variant_label=variant_label,
        source_description=source_description,
        results=results,
        average_grounding=round(avg, 2),
        diff_vs_baseline=None,
    )


def run_prompt_simulation_two_variants(
    chunks_a: list[DocumentChunk],
    chunks_b: list[DocumentChunk],
    llm_provider: object,
    label_a: str = "original",
    label_b: str = "optimized",
) -> tuple[PromptTestResult, PromptTestResult]:
    """Run simulator on two chunk sets and add per-prompt diff to the second result."""
    res_a = run_prompt_simulation(chunks_a, llm_provider, variant_label=label_a, source_description=label_a)
    res_b = run_prompt_simulation(chunks_b, llm_provider, variant_label=label_b, source_description=label_b)
    diff: dict[str, float] = {}
    for rb in res_b.results:
        ra_match = next((r for r in res_a.results if r.prompt_id == rb.prompt_id), None)
        if ra_match:
            diff[rb.prompt_id] = round(rb.grounding_score - ra_match.grounding_score, 2)
    res_b.diff_vs_baseline = diff
    return res_a, res_b
