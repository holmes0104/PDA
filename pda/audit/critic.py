"""Critic pass: verify that generated recommendations are supported by source chunks."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from pda.schemas.models import AuditFinding, DocumentChunk

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def run_critic_pass(
    findings: list[AuditFinding],
    chunks: list[DocumentChunk],
    llm_provider: object,
) -> list[AuditFinding]:
    """
    For each finding with is_grounded=False, ask the LLM whether the recommendation
    is supported by the source chunks. Set critic_verified and critic_note.
    llm_provider must have .complete(prompt: str) -> str.
    """
    chunk_by_id = {c.chunk_id: c for c in chunks}
    chunk_text = "\n\n".join(
        f"[{c.chunk_id}] (page {c.page_number}) {c.text[:800]}"
        for c in chunks[:30]
    )
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    template = env.get_template("critic_verify.j2")
    result: list[AuditFinding] = []
    for f in findings:
        if f.is_grounded:
            result.append(f)
            continue
        prompt = template.render(
            finding_title=f.title,
            finding_recommendation=f.recommendation or "",
            chunk_text=chunk_text,
        )
        raw = llm_provider.complete(prompt)
        verified = "yes" in raw.lower() and "not supported" not in raw.lower()[:200]
        note = raw.strip()[:500] if raw else None
        result.append(
            AuditFinding(
                finding_id=f.finding_id,
                category=f.category,
                severity=f.severity,
                title=f.title,
                description=f.description,
                evidence=f.evidence,
                is_grounded=f.is_grounded,
                recommendation=f.recommendation,
                critic_verified=verified,
                critic_note=note,
            )
        )
    return result
