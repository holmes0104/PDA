"""Evaluation harness: load YAML prompts, run RAG, score, output CSV + JSON + dashboard."""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
MAX_CONTEXT_CHARS = 12_000


# ── Data structures ──────────────────────────────────────────────────────

class EvalPrompt:
    """A single evaluation prompt loaded from YAML."""

    def __init__(self, data: dict):
        self.id: str = str(data.get("id", ""))
        self.category: str = str(data.get("category", ""))
        self.prompt: str = str(data.get("prompt", ""))
        self.must_cover: list[str] = data.get("must_cover", []) or []


class EvalResult:
    """Result for one prompt: answer, citations, and scores."""

    def __init__(self):
        self.prompt_id: str = ""
        self.category: str = ""
        self.prompt_text: str = ""
        self.answer: str = ""
        self.cited_chunk_ids: list[str] = []
        self.completeness: int = 0
        self.correctness: int = 0
        self.citation_coverage: int = 0
        self.rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "category": self.category,
            "prompt": self.prompt_text,
            "answer": self.answer,
            "cited_chunk_ids": self.cited_chunk_ids,
            "completeness": self.completeness,
            "correctness": self.correctness,
            "citation_coverage": self.citation_coverage,
            "rationale": self.rationale,
        }


# ── YAML loading ─────────────────────────────────────────────────────────

def load_prompts(yaml_path: str | Path) -> list[EvalPrompt]:
    """Load evaluation prompts from a YAML file."""
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt YAML not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if isinstance(data, list):
        prompts_data = data
    elif isinstance(data, dict):
        prompts_data = data.get("prompts", data.get("questions", []))
    else:
        prompts_data = []
    return [EvalPrompt(p) for p in prompts_data if isinstance(p, dict)]


# ── RAG + answer ─────────────────────────────────────────────────────────

def _retrieve_context(store: object, query: str, n_results: int = 10) -> tuple[str, list[str]]:
    """Retrieve relevant chunks from the vector store and return (context_text, chunk_ids)."""
    results = store.query(query, n_results=n_results)
    parts: list[str] = []
    ids: list[str] = []
    total = 0
    for r in results:
        cid = r.get("chunk_id", "")
        text = r.get("text", "")
        snippet = f"[{cid}] {text[:1500]}"
        if total + len(snippet) > MAX_CONTEXT_CHARS:
            break
        parts.append(snippet)
        ids.append(cid)
        total += len(snippet)
    return "\n\n".join(parts), ids


def _generate_answer(
    context: str,
    buyer_prompt: str,
    llm_provider: object,
) -> str:
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    template = env.get_template("eval_rag_answer.j2")
    prompt = template.render(chunk_text=context, buyer_prompt=buyer_prompt)
    return llm_provider.complete(prompt) or ""


def _extract_cited_ids(answer: str) -> list[str]:
    """Extract [chunk-id] citations from the answer text."""
    return list(dict.fromkeys(re.findall(r"\[(pdf-[^\]]+|url-[^\]]+)\]", answer)))


# ── Scoring ──────────────────────────────────────────────────────────────

def _score_answer(
    answer: str,
    buyer_prompt: str,
    context: str,
    must_cover: list[str],
    llm_provider: object,
) -> dict:
    """Use an LLM judge to score completeness, correctness, citation coverage."""
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    template = env.get_template("eval_judge.j2")
    prompt = template.render(
        buyer_prompt=buyer_prompt,
        answer=answer[:4000],
        chunk_text=context,
        must_cover=must_cover,
    )
    raw = llm_provider.complete(prompt) or "{}"
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```\w*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        data = {}

    return {
        "completeness": max(0, min(10, int(data.get("completeness", 0)))),
        "correctness": max(0, min(10, int(data.get("correctness", 0)))),
        "citation_coverage": max(0, min(10, int(data.get("citation_coverage", 0)))),
        "rationale": str(data.get("rationale", "")),
    }


def _deterministic_citation_coverage(answer: str, available_chunk_ids: list[str]) -> float:
    """Compute a deterministic citation coverage score (0-1).

    Counts the fraction of answer sentences that contain at least one [chunk-id] citation.
    Splits on sentence-ending punctuation followed by whitespace or end-of-string,
    avoiding splits on decimal points (e.g. "2.5").
    """
    # Split on ". " or "! " or "? " (sentence boundaries) but not on "2.5"
    sentences = [s.strip() for s in re.split(r"(?<!\d)[.!?]+(?:\s|$)", answer) if s.strip()]
    if not sentences:
        return 0.0
    cited = sum(
        1 for s in sentences if re.search(r"\[(pdf-|url-)", s)
    )
    return cited / len(sentences)


# ── Main harness ─────────────────────────────────────────────────────────

def run_eval_harness(
    prompts_path: str | Path,
    store: object,
    llm_provider: object,
    out_dir: str | Path,
) -> list[EvalResult]:
    """
    Run the full eval harness:
    1. Load YAML prompts
    2. For each prompt: retrieve chunks, generate answer, score
    3. Write results.json, results.csv, dashboard.html
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prompts = load_prompts(prompts_path)
    if not prompts:
        logger.warning("No prompts loaded from %s", prompts_path)
        return []

    results: list[EvalResult] = []
    for ep in prompts:
        logger.info("Eval prompt: %s", ep.id or ep.prompt[:60])
        context, available_ids = _retrieve_context(store, ep.prompt)
        answer = _generate_answer(context, ep.prompt, llm_provider)
        cited_ids = _extract_cited_ids(answer)
        scores = _score_answer(answer, ep.prompt, context, ep.must_cover, llm_provider)

        # Blend deterministic citation coverage with LLM judge
        det_cov = _deterministic_citation_coverage(answer, available_ids)
        blended_citation = int(
            0.5 * scores["citation_coverage"] + 0.5 * (det_cov * 10)
        )

        r = EvalResult()
        r.prompt_id = ep.id
        r.category = ep.category
        r.prompt_text = ep.prompt
        r.answer = answer
        r.cited_chunk_ids = cited_ids
        r.completeness = scores["completeness"]
        r.correctness = scores["correctness"]
        r.citation_coverage = min(10, blended_citation)
        r.rationale = scores["rationale"]
        results.append(r)

    # ── Write outputs ────────────────────────────────────────────────
    _write_json(results, out_dir / "results.json")
    _write_csv(results, out_dir / "results.csv")
    _write_dashboard(results, out_dir / "dashboard.html")

    logger.info("Eval harness: %d prompts scored, output at %s", len(results), out_dir)
    return results


# ── Output writers ───────────────────────────────────────────────────────

def _write_json(results: list[EvalResult], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in results], f, indent=2, ensure_ascii=False)


def _write_csv(results: list[EvalResult], path: Path) -> None:
    fieldnames = [
        "prompt_id", "category", "prompt", "completeness",
        "correctness", "citation_coverage", "cited_chunk_ids", "rationale",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "prompt_id": r.prompt_id,
                "category": r.category,
                "prompt": r.prompt_text,
                "completeness": r.completeness,
                "correctness": r.correctness,
                "citation_coverage": r.citation_coverage,
                "cited_chunk_ids": ";".join(r.cited_chunk_ids),
                "rationale": r.rationale[:300],
            })


def _write_dashboard(results: list[EvalResult], path: Path) -> None:
    """Generate a self-contained static HTML dashboard."""
    if not results:
        path.write_text("<html><body><h1>No results</h1></body></html>", encoding="utf-8")
        return

    n = len(results)
    avg_comp = sum(r.completeness for r in results) / n
    avg_corr = sum(r.correctness for r in results) / n
    avg_cite = sum(r.citation_coverage for r in results) / n

    # Per-category aggregates
    cats: dict[str, list[EvalResult]] = {}
    for r in results:
        cats.setdefault(r.category or "uncategorized", []).append(r)

    cat_rows = ""
    for cat, rs in sorted(cats.items()):
        cn = len(rs)
        cat_rows += f"""
        <tr>
            <td>{cat}</td>
            <td>{cn}</td>
            <td>{sum(r.completeness for r in rs)/cn:.1f}</td>
            <td>{sum(r.correctness for r in rs)/cn:.1f}</td>
            <td>{sum(r.citation_coverage for r in rs)/cn:.1f}</td>
        </tr>"""

    detail_rows = ""
    for r in results:
        color = "#4caf50" if r.correctness >= 7 else ("#ff9800" if r.correctness >= 4 else "#f44336")
        detail_rows += f"""
        <tr>
            <td>{r.prompt_id}</td>
            <td>{r.category}</td>
            <td title="{r.prompt_text[:200]}">{r.prompt_text[:80]}...</td>
            <td>{r.completeness}</td>
            <td style="color:{color};font-weight:bold">{r.correctness}</td>
            <td>{r.citation_coverage}</td>
            <td>{len(r.cited_chunk_ids)}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>PDA Eval Dashboard</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 0 auto; padding: 1rem; }}
h1 {{ border-bottom: 2px solid #333; padding-bottom: 0.5rem; }}
.summary {{ display: flex; gap: 2rem; margin-bottom: 2rem; }}
.card {{ background: #f5f5f5; padding: 1rem 1.5rem; border-radius: 8px; text-align: center; min-width: 140px; }}
.card h3 {{ margin: 0 0 0.5rem; color: #666; font-size: 0.85rem; text-transform: uppercase; }}
.card .score {{ font-size: 2rem; font-weight: bold; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
th, td {{ border: 1px solid #ddd; padding: 0.5rem 0.75rem; text-align: left; font-size: 0.9rem; }}
th {{ background: #f0f0f0; position: sticky; top: 0; }}
tr:hover {{ background: #fafafa; }}
</style>
</head>
<body>
<h1>PDA Evaluation Dashboard</h1>
<p>{n} prompts evaluated</p>

<div class="summary">
    <div class="card"><h3>Avg Completeness</h3><div class="score">{avg_comp:.1f}</div></div>
    <div class="card"><h3>Avg Correctness</h3><div class="score">{avg_corr:.1f}</div></div>
    <div class="card"><h3>Avg Citation Coverage</h3><div class="score">{avg_cite:.1f}</div></div>
</div>

<h2>By Category</h2>
<table>
<tr><th>Category</th><th>Count</th><th>Completeness</th><th>Correctness</th><th>Citation Cov.</th></tr>
{cat_rows}
</table>

<h2>Detail Results</h2>
<table>
<tr><th>ID</th><th>Category</th><th>Prompt</th><th>Comp.</th><th>Corr.</th><th>Cite.</th><th># Cites</th></tr>
{detail_rows}
</table>
</body>
</html>"""

    path.write_text(html, encoding="utf-8")
