"""Product Fact Sheet extraction via targeted retrieval and LLM on retrieved chunks only."""

import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from pda.schemas.factsheet_schema import (
    ProductFactSheet,
    KeySpec,
    Constraint,
    Differentiator,
)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

# Targeted queries per section; retrieve() runs with these, then LLM sees only retrieved chunks.
SECTION_QUERIES = [
    "product name and product category",
    "primary use cases and applications",
    "target buyer roles and personas",
    "key specifications technical specs dimensions",
    "constraints limitations restrictions",
    "differentiators unique selling points advantages",
    "certifications standards compliance",
    "integrations interfaces APIs connectivity",
    "maintenance calibration service",
    "source coverage summary",
]

MAX_RETRIES = 2  # max fix-JSON attempts after initial parse failure
RETRIEVE_N_RESULTS = 10


def _chunks_from_store(store, queries: list[str], n_results: int = RETRIEVE_N_RESULTS) -> list[dict]:
    """Run targeted queries and return deduplicated chunks (by chunk_id)."""
    seen: set[str] = set()
    out: list[dict] = []
    for q in queries:
        results = store.query(q, n_results=n_results)
        for r in results:
            cid = r.get("chunk_id")
            if cid and cid not in seen:
                seen.add(cid)
                out.append({"chunk_id": cid, "text": r.get("text", "")})
    return out


def _strip_code_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```\w*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


def _parse_json(raw: str) -> dict:
    return json.loads(_strip_code_fence(raw))


def _validate_fact_sheet(data: dict) -> ProductFactSheet:
    """Build ProductFactSheet from dict; normalize so Pydantic accepts it."""
    def norm_list_str(v):
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return []

    def norm_key_specs(v):
        if not isinstance(v, list):
            return []
        out = []
        for item in v:
            if not isinstance(item, dict):
                continue
            out.append(KeySpec(
                name=str(item.get("name", "")),
                value=str(item.get("value", "")),
                unit=str(item.get("unit", "")),
                conditions=str(item.get("conditions", "")),
                evidence_chunk_ids=[str(x) for x in (item.get("evidence_chunk_ids") or [])],
            ))
        return out

    def norm_constraints(v):
        if not isinstance(v, list):
            return []
        return [
            Constraint(
                statement=str(item.get("statement", "")),
                evidence_chunk_ids=[str(x) for x in (item.get("evidence_chunk_ids") or [])],
            )
            for item in v
            if isinstance(item, dict)
        ]

    def norm_differentiators(v):
        if not isinstance(v, list):
            return []
        return [
            Differentiator(
                statement=str(item.get("statement", "")),
                evidence_chunk_ids=[str(x) for x in (item.get("evidence_chunk_ids") or [])],
            )
            for item in v
            if isinstance(item, dict)
        ]

    return ProductFactSheet(
        product_name=str(data.get("product_name")) if data.get("product_name") is not None else "NOT_FOUND",
        product_category=str(data.get("product_category")) if data.get("product_category") is not None else "NOT_FOUND",
        primary_use_cases=norm_list_str(data.get("primary_use_cases")),
        target_buyer_roles=norm_list_str(data.get("target_buyer_roles")),
        key_specs=norm_key_specs(data.get("key_specs")),
        constraints=norm_constraints(data.get("constraints")),
        differentiators=norm_differentiators(data.get("differentiators")),
        certifications_standards=norm_list_str(data.get("certifications_standards")),
        integrations_interfaces=norm_list_str(data.get("integrations_interfaces")),
        maintenance_calibration=norm_list_str(data.get("maintenance_calibration")),
        source_coverage_summary=str(data.get("source_coverage_summary")) if data.get("source_coverage_summary") is not None else "NOT_FOUND",
    )


def extract_product_fact_sheet(store, llm_provider, max_retries: int = MAX_RETRIES) -> tuple[ProductFactSheet, dict]:
    """
    Run targeted retrieval, then LLM on retrieved chunks only. Return (ProductFactSheet, provenance).
    store must have .query(query_text, n_results=...) -> list[{chunk_id, text, ...}].
    llm_provider must have .complete(prompt: str) -> str.
    provenance: field name -> list of evidence chunk_ids used for that field.
    """
    chunks = _chunks_from_store(store, SECTION_QUERIES)
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    extract_tpl = env.get_template("factsheet_extract.j2")
    fix_tpl = env.get_template("factsheet_fix_json.j2")

    prompt = extract_tpl.render(chunks=chunks)
    raw = llm_provider.complete(prompt)
    attempts = 0
    last_raw = raw

    while attempts <= max_retries:
        try:
            data = _parse_json(last_raw)
            sheet = _validate_fact_sheet(data)
            break
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            attempts += 1
            if attempts > max_retries:
                raise ValueError(
                    f"Could not produce valid ProductFactSheet JSON after {max_retries + 1} attempts. Last error: {e}"
                ) from e
            fix_prompt = fix_tpl.render(invalid_json=last_raw)
            last_raw = llm_provider.complete(fix_prompt)

    # Build provenance: each field -> list of evidence chunk_ids
    provenance = _build_provenance(sheet)
    return sheet, provenance


def require_evidence_for_non_not_found(sheet: ProductFactSheet) -> list[str]:
    """
    Validate that every non-NOT_FOUND item has non-empty evidence_chunk_ids.
    Returns list of violation messages; empty if valid.
    """
    violations = []
    for i, spec in enumerate(sheet.key_specs):
        if (spec.name or spec.value) and not spec.evidence_chunk_ids:
            violations.append(f"key_specs[{i}] has name/value but empty evidence_chunk_ids")
    for i, c in enumerate(sheet.constraints):
        if c.statement and not c.evidence_chunk_ids:
            violations.append(f"constraints[{i}] has statement but empty evidence_chunk_ids")
    for i, d in enumerate(sheet.differentiators):
        if d.statement and not d.evidence_chunk_ids:
            violations.append(f"differentiators[{i}] has statement but empty evidence_chunk_ids")
    return violations


def _build_provenance(sheet: ProductFactSheet) -> dict:
    """Map each field to list of evidence chunk_ids (for scalar fields, from section-level retrieval we don't have per-field chunks here; we collect from nested evidence_chunk_ids)."""
    provenance = {}

    def add(field: str, chunk_ids: list[str]) -> None:
        provenance[field] = list(dict.fromkeys(chunk_ids))

    add("product_name", [])  # scalar; no embedded evidence in schema
    add("product_category", [])
    add("primary_use_cases", [])
    add("target_buyer_roles", [])
    add("key_specs", [cid for s in sheet.key_specs for cid in s.evidence_chunk_ids])
    add("constraints", [cid for c in sheet.constraints for cid in c.evidence_chunk_ids])
    add("differentiators", [cid for d in sheet.differentiators for cid in d.evidence_chunk_ids])
    add("certifications_standards", [])
    add("integrations_interfaces", [])
    add("maintenance_calibration", [])
    add("source_coverage_summary", [])

    return provenance
