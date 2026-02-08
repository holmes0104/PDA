"""Markdown report assembly: fact sheet, scorecard, findings, content pack, prompt sim."""

import json
from pathlib import Path
from typing import Any

from pda.schemas.models import (
    AuditFinding,
    ProductFactSheet,
    PromptTestResult,
    Scorecard,
)


def _fact_value_repr(fv: Any) -> str:
    if fv is None:
        return "NOT_FOUND"
    v = getattr(fv, "value", fv)
    if v is None or (isinstance(v, str) and str(v).strip().upper() == "NOT_FOUND"):
        return "NOT_FOUND"
    if hasattr(fv, "evidence") and getattr(fv, "evidence"):
        refs = getattr(fv, "evidence", [])
        chunks = [r.chunk_ids for r in refs if getattr(r, "chunk_ids", None)]
        cite = " (chunks: " + ", ".join(c[0] for c in chunks if c) + ")" if chunks else ""
        return str(v) + cite
    return str(v)


def render_markdown_report(
    fact_sheet: ProductFactSheet,
    scorecard: Scorecard,
    findings: list[AuditFinding],
    content_pack: dict[str, Any],
    prompt_results: list[PromptTestResult] | None = None,
    pdf_path: str = "",
    url_list: list[str] | None = None,
) -> str:
    """Assemble a single Markdown report with all sections."""
    sections: list[str] = []

    sections.append("# LLM Product Discoverability Audit Report\n")
    if pdf_path:
        sections.append(f"**PDF:** `{pdf_path}`  \n")
    if url_list:
        sections.append("**URLs:** " + ", ".join(f"`{u}`" for u in url_list) + "\n")
    sections.append("---\n")

    # 1) Product Fact Sheet (JSON + evidence)
    sections.append("## 1. Product Fact Sheet (JSON)\n")
    sheet_dict = fact_sheet.model_dump()
    sections.append("```json\n" + json.dumps(sheet_dict, indent=2, default=str) + "\n```\n")

    # 2) Scorecard
    sections.append("## 2. LLM-Readiness Scorecard\n")
    sections.append(f"- **Overall score:** {scorecard.overall_score}/100  \n")
    sections.append(f"- **Grade:** {scorecard.grade}  \n\n")
    sections.append("| Dimension | Score | Method | Details |\n|-----------|-------|--------|--------|\n")
    for d in scorecard.dimensions:
        detail = (d.details or "")[:80] + ("..." if len(d.details or "") > 80 else "")
        sections.append(f"| {d.name} | {d.score}/{d.max_score} | {d.scoring_method} | {detail} |\n")
    sections.append("\n---\n")

    # 3) Gap analysis + recommendations (Facts vs Recommendations)
    sections.append("## 3. Gap Analysis & Recommendations\n")
    grounded = [f for f in findings if f.is_grounded]
    generated = [f for f in findings if not f.is_grounded]
    if grounded:
        sections.append("### Grounded findings (from source)\n")
        for f in grounded:
            sections.append(f"- **{f.title}** [{f.severity.value}] {f.description}\n")
    if generated:
        sections.append("### Recommendations (generated)\n")
        for f in generated:
            badge = " ⚠️ Not supported by source" if not f.critic_verified and f.critic_note else ""
            sections.append(f"- **{f.title}** [{f.severity.value}]{badge}\n")
            sections.append(f"  - {f.description}\n")
            if f.recommendation:
                sections.append(f"  - *Recommendation:* {f.recommendation}\n")
            if f.critic_note:
                sections.append(f"  - *Critic:* {f.critic_note[:200]}\n")
    sections.append("\n---\n")

    # 4) LLM-friendly content pack
    sections.append("## 4. LLM-Friendly Content Pack\n")
    sections.append("### Page outline\n")
    for line in content_pack.get("page_outline", []):
        sections.append(f"- {line}\n")
    sections.append("\n### FAQ pack\n")
    for faq in content_pack.get("faq_pack", []):
        sections.append(f"- **Q:** {faq.get('q', '')}  \n  **A:** {faq.get('a', '')}\n")
    sections.append("\n### Comparison bullets\n")
    for b in content_pack.get("comparison_bullets", []):
        sections.append(f"- {b}\n")
    sections.append("\n### Constraints\n")
    for c in content_pack.get("constraints", []):
        sections.append(f"- {c}\n")
    sections.append("\n### Schema.org JSON-LD skeleton\n")
    sections.append("```json\n" + content_pack.get("schema_org_json", "{}") + "\n```\n")
    sections.append("\n---\n")

    # 5) Buyer-prompt simulator
    if prompt_results:
        sections.append("## 5. Buyer-Prompt Simulator Results\n")
        for pr in prompt_results:
            sections.append(f"### Variant: {pr.variant_label}\n")
            sections.append(f"Average grounding: {pr.average_grounding}\n\n")
            for r in pr.results:
                sections.append(f"- **Q:** {r.buyer_prompt}\n")
                sections.append(f"  **A:** {r.llm_response[:400]}...\n")
                sections.append(f"  Grounding: {r.grounding_score}\n")
            if pr.diff_vs_baseline:
                sections.append("\n**Diff vs baseline:** " + json.dumps(pr.diff_vs_baseline) + "\n")
            sections.append("\n")

    return "\n".join(sections)


def write_markdown_report(output_path: str | Path, content: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(content, encoding="utf-8")
