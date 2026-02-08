"""Buyer-Prompt Simulator: generate prompts, answer from variant-only content, score with factsheet rubric, optional A/B diff."""

import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from pda.schemas.factsheet_schema import ProductFactSheet
from pda.schemas.models import (
    SimulatorAggregateMetrics,
    SimulatorPromptResult,
    SimulatorRunResult,
)
from pda.simulate.prompt_library import get_prompt_set

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
MAX_VARIANT_CHARS = 12000  # cap context size for answer generation


def _factsheet_summary(sheet: ProductFactSheet) -> str:
    """Serialize factsheet to a short summary for the scoring rubric."""
    parts = [
        f"Product: {sheet.product_name}",
        f"Category: {sheet.product_category}",
        f"Use cases: {', '.join(sheet.primary_use_cases) if sheet.primary_use_cases else 'NOT_FOUND'}",
        f"Target roles: {', '.join(sheet.target_buyer_roles) if sheet.target_buyer_roles else 'NOT_FOUND'}",
    ]
    if sheet.key_specs:
        parts.append("Key specs: " + "; ".join(f"{s.name}={s.value} {s.unit}".strip() for s in sheet.key_specs[:15]))
    if sheet.constraints:
        parts.append("Constraints: " + "; ".join(c.statement for c in sheet.constraints[:20]))
    if sheet.differentiators:
        parts.append("Differentiators: " + "; ".join(d.statement for d in sheet.differentiators[:20]))
    if sheet.certifications_standards:
        parts.append("Certifications/standards: " + ", ".join(sheet.certifications_standards))
    if sheet.integrations_interfaces:
        parts.append("Integrations: " + ", ".join(sheet.integrations_interfaces))
    if sheet.maintenance_calibration:
        parts.append("Maintenance/calibration: " + ", ".join(sheet.maintenance_calibration))
    return "\n".join(parts)


def load_factsheet(path: Path) -> ProductFactSheet:
    """Load ProductFactSheet from JSON (factsheet_schema format)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    from pda.extract.factsheet_extractor import _validate_fact_sheet
    return _validate_fact_sheet(data)


def load_variant_content(path: Path) -> str:
    """Load variant content from file. Supports .txt, .md, or .json (with 'content', 'text', or 'summary' key)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Variant path not found: {path}")
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(raw)
        for key in ("content", "text", "summary", "body"):
            if key in data and isinstance(data[key], str):
                return data[key][:MAX_VARIANT_CHARS * 2]  # allow slightly more for JSON-derived
        # If no known key, dump compact JSON as content
        return json.dumps(data, indent=0)[:MAX_VARIANT_CHARS * 2]
    return raw[:MAX_VARIANT_CHARS * 2]


def generate_prompt_set(out_path: Path) -> list[dict]:
    """Generate the 50-prompt set and save to prompts.json. Returns the prompt list."""
    prompts = get_prompt_set()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2)
    return prompts


def _answer_prompt(variant_content: str, buyer_prompt: str, llm_provider: object) -> str:
    """Answer the buyer prompt using ONLY variant content. llm_provider must have .complete(prompt) -> str."""
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    template = env.get_template("buyer_sim.j2")
    context = variant_content[:MAX_VARIANT_CHARS]
    prompt = template.render(chunk_text=context, buyer_prompt=buyer_prompt)
    return llm_provider.complete(prompt) or ""


def _score_response(
    response: str,
    buyer_prompt: str,
    factsheet_summary: str,
    llm_provider: object,
) -> tuple[int, int, int, list[str]]:
    """Score response with rubric; returns (factual, differentiator, constraint, hallucination_flags)."""
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    template = env.get_template("simulator_score_rubric.j2")
    prompt = template.render(
        factsheet_summary=factsheet_summary,
        buyer_prompt=buyer_prompt,
        response=response[:4000],
    )
    raw = llm_provider.complete(prompt) or "{}"
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return 0, 0, 0, ["Scoring parse error"]
    factual = max(0, min(10, int(data.get("factual_correctness", 0))))
    diff_cov = max(0, min(10, int(data.get("differentiator_coverage", 0))))
    constraint = max(0, min(10, int(data.get("constraint_correctness", 0))))
    flags = data.get("hallucination_flags") or []
    if not isinstance(flags, list):
        flags = []
    flags = [str(f) for f in flags if f]
    return factual, diff_cov, constraint, flags


def run_simulator(
    variant_content: str,
    variant_label: str,
    prompts: list[dict],
    factsheet: ProductFactSheet,
    llm_provider: object,
) -> SimulatorRunResult:
    """
    For each prompt, answer using ONLY variant_content, then score with factsheet rubric.
    Returns SimulatorRunResult with results and aggregate_metrics.
    """
    factsheet_summary = _factsheet_summary(factsheet)
    results: list[SimulatorPromptResult] = []
    for p in prompts:
        pid = p.get("id", "")
        category = p.get("category", "")
        buyer_prompt = p.get("prompt", "")
        response = _answer_prompt(variant_content, buyer_prompt, llm_provider)
        factual, diff_cov, constraint, flags = _score_response(
            response, buyer_prompt, factsheet_summary, llm_provider
        )
        results.append(
            SimulatorPromptResult(
                prompt_id=pid,
                category=category,
                buyer_prompt=buyer_prompt,
                response=response[:5000],
                factual_correctness=factual,
                differentiator_coverage=diff_cov,
                constraint_correctness=constraint,
                hallucination_flags=flags,
            )
        )
    n = len(results)
    agg = SimulatorAggregateMetrics(
        avg_factual_correctness=round(sum(r.factual_correctness for r in results) / n, 2) if n else 0,
        avg_differentiator_coverage=round(sum(r.differentiator_coverage for r in results) / n, 2) if n else 0,
        avg_constraint_correctness=round(sum(r.constraint_correctness for r in results) / n, 2) if n else 0,
        total_hallucination_count=sum(len(r.hallucination_flags) for r in results),
        prompts_with_hallucinations=sum(1 for r in results if r.hallucination_flags),
    )
    return SimulatorRunResult(
        variant_label=variant_label,
        results=results,
        aggregate_metrics=agg,
    )


def build_diff_report(
    result_a: SimulatorRunResult,
    result_b: SimulatorRunResult,
    out_path: Path,
) -> None:
    """
    Produce simulator_diff.md: aggregate metrics, improved/regressed prompts, top 10 failure prompts.
    """
    by_id_a = {r.prompt_id: r for r in result_a.results}
    by_id_b = {r.prompt_id: r for r in result_b.results}
    improved: list[str] = []
    regressed: list[str] = []
    for pid, rb in by_id_b.items():
        ra = by_id_a.get(pid)
        if not ra:
            continue
        score_a = (ra.factual_correctness + ra.differentiator_coverage + ra.constraint_correctness) / 3
        score_b = (rb.factual_correctness + rb.differentiator_coverage + rb.constraint_correctness) / 3
        if score_b > score_a:
            improved.append(pid)
        elif score_b < score_a:
            regressed.append(pid)
    # Top 10 failure prompts: lowest composite score in B (or A if single variant; here we use B as "current")
    all_results = result_b.results
    composite = [
        (r.prompt_id, (r.factual_correctness + r.differentiator_coverage + r.constraint_correctness) / 3, len(r.hallucination_flags), r)
        for r in all_results
    ]
    composite.sort(key=lambda x: (x[1], x[2]))  # ascending score, then ascending hallucination count
    top_10_failures = [x[0] for x in composite[:10]]
    failure_details = []
    for pid in top_10_failures:
        r = by_id_b.get(pid)
        if r:
            failure_details.append({
                "prompt_id": pid,
                "category": r.category,
                "buyer_prompt": r.buyer_prompt,
                "factual": r.factual_correctness,
                "differentiator": r.differentiator_coverage,
                "constraint": r.constraint_correctness,
                "hallucination_flags": r.hallucination_flags,
            })

    lines = [
        "# Buyer-Prompt Simulator: A vs B Diff Report",
        "",
        "## Aggregate metrics",
        "",
        "| Metric | Variant A | Variant B |",
        "|--------|-----------|-----------|",
        f"| Avg factual correctness | {result_a.aggregate_metrics.avg_factual_correctness} | {result_b.aggregate_metrics.avg_factual_correctness} |",
        f"| Avg differentiator coverage | {result_a.aggregate_metrics.avg_differentiator_coverage} | {result_b.aggregate_metrics.avg_differentiator_coverage} |",
        f"| Avg constraint correctness | {result_a.aggregate_metrics.avg_constraint_correctness} | {result_b.aggregate_metrics.avg_constraint_correctness} |",
        f"| Total hallucination count | {result_a.aggregate_metrics.total_hallucination_count} | {result_b.aggregate_metrics.total_hallucination_count} |",
        f"| Prompts with hallucinations | {result_a.aggregate_metrics.prompts_with_hallucinations} | {result_b.aggregate_metrics.prompts_with_hallucinations} |",
        "",
        "## Prompts where B improved",
        "",
    ]
    if improved:
        lines.extend([f"- {p}" for p in improved])
    else:
        lines.append("- (none)")
    lines.extend(["", "## Prompts where B regressed", ""])
    if regressed:
        lines.extend([f"- {p}" for p in regressed])
    else:
        lines.append("- (none)")
    lines.extend(["", "## Top 10 failure prompts to fix next (lowest scores in B)", ""])
    for d in failure_details:
        lines.append(f"- **{d['prompt_id']}** ({d['category']}): {d['buyer_prompt'][:80]}...")
        lines.append(f"  - Scores: factual={d['factual']}, differentiator={d['differentiator']}, constraint={d['constraint']}")
        if d["hallucination_flags"]:
            lines.append(f"  - Hallucinations: {d['hallucination_flags']}")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_simulator_result(result: SimulatorRunResult, out_path: Path) -> None:
    """Write SimulatorRunResult to JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, indent=2)
