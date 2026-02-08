"""Generate content pack from strict ProductFactSheet + audit: outline, FAQ, comparison, JSON-LD. No invented facts; TODO: confirm and audit refs for missing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pda.schemas.factsheet_schema import ProductFactSheet
from pda.schemas.models import AuditFinding, Scorecard

NOT_FOUND = "NOT_FOUND"


def load_factsheet(path: Path | str) -> ProductFactSheet:
    """Load strict ProductFactSheet from factsheet.json."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return ProductFactSheet.model_validate(data)


def load_audit(path: Path | str) -> tuple[Scorecard | None, list[AuditFinding]]:
    """
    Load audit.json with keys: scorecard (optional), findings (required).
    Returns (scorecard or None, findings).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    scorecard = None
    if "scorecard" in data and data["scorecard"]:
        scorecard = Scorecard.model_validate(data["scorecard"])
    findings_data = data.get("findings", [])
    findings = [AuditFinding.model_validate(f) for f in findings_data]
    return scorecard, findings


def _str_val(s: str) -> str | None:
    if not s or s.strip().upper() == NOT_FOUND:
        return None
    return s.strip()


def _ref_chunks(ids: list[str]) -> str:
    if not ids:
        return ""
    return " (chunks: " + ", ".join(ids[:5]) + (")" if len(ids) <= 5 else ", ...)")


def _missing_note(finding: AuditFinding | None) -> str:
    if not finding:
        return " TODO: confirm."
    return f" TODO: confirm (audit: {finding.finding_id} — {finding.title})."


def build_product_page_outline(
    sheet: ProductFactSheet,
    findings: list[AuditFinding],
) -> str:
    """Headings + what each section must contain. References audit for missing."""
    lines: list[str] = []
    lines.append("# Product page outline\n")
    lines.append("Use this outline to structure the product page. Each section should contain only factual content from the fact sheet; where information is missing, add TODO and reference the audit finding.\n")

    def _missing_finding(field_hint: str) -> AuditFinding | None:
        for f in findings:
            if field_hint.lower() in (f.title or "").lower() or field_hint.lower() in (f.description or "").lower():
                return f
        return None

    # Sections keyed to factsheet + audit
    name = _str_val(sheet.product_name)
    lines.append("## 1. Product name and tagline\n")
    if name:
        lines.append(f"- **Must contain:** Product name: {name}. Clear tagline or one-line value proposition.")
        lines.append(f"- Evidence: from fact sheet (product_name).\n")
    else:
        f = _missing_finding("product name") or _missing_finding("Product name")
        lines.append(f"- **Must contain:** Product name and a short tagline.{_missing_note(f)}\n")

    cat = _str_val(sheet.product_category)
    lines.append("## 2. Product category and positioning\n")
    if cat:
        lines.append(f"- **Must contain:** Category: {cat}. How it fits in the portfolio or market.")
        lines.append("- Evidence: from fact sheet (product_category).\n")
    else:
        f = _missing_finding("category")
        lines.append(f"- **Must contain:** Category and positioning.{_missing_note(f)}\n")

    lines.append("## 3. Primary use cases\n")
    if sheet.primary_use_cases:
        lines.append("- **Must contain:** List of primary use cases with short descriptions:")
        for u in sheet.primary_use_cases[:8]:
            lines.append(f"  - {u}")
        lines.append("- Evidence: fact sheet primary_use_cases.\n")
    else:
        f = _missing_finding("use case") or _missing_finding("key feature")
        lines.append(f"- **Must contain:** 3–5 primary use cases or applications.{_missing_note(f)}\n")

    lines.append("## 4. Target buyers and roles\n")
    if sheet.target_buyer_roles:
        lines.append("- **Must contain:** Who should consider this product:")
        for r in sheet.target_buyer_roles:
            lines.append(f"  - {r}")
        lines.append("\n")
    else:
        f = _missing_finding("target") or _missing_finding("audience")
        lines.append(f"- **Must contain:** Target buyer roles or personas.{_missing_note(f)}\n")

    lines.append("## 5. Key specifications\n")
    if sheet.key_specs:
        lines.append("- **Must contain:** Table or list of key specs (name, value, unit, conditions). Each row must be grounded in source.")
        for s in sheet.key_specs[:10]:
            ref = _ref_chunks(s.evidence_chunk_ids)
            lines.append(f"  - {s.name}: {s.value} {s.unit or ''} {s.conditions or ''}{ref}")
        lines.append("\n")
    else:
        f = _missing_finding("specification")
        lines.append(f"- **Must contain:** Key specifications table.{_missing_note(f)}\n")

    lines.append("## 6. Constraints and limitations\n")
    if sheet.constraints:
        lines.append("- **Must contain:** Stated constraints or limitations (no hype); each with evidence.")
        for c in sheet.constraints:
            ref = _ref_chunks(c.evidence_chunk_ids)
            lines.append(f"  - {c.statement}{ref}")
        lines.append("\n")
    else:
        lines.append("- **Must contain:** Any operating limits, environmental or compatibility constraints. If none stated, say so or TODO: confirm.\n")

    lines.append("## 7. Differentiators\n")
    if sheet.differentiators:
        lines.append("- **Must contain:** Factual differentiators (not marketing fluff):")
        for d in sheet.differentiators:
            ref = _ref_chunks(d.evidence_chunk_ids)
            lines.append(f"  - {d.statement}{ref}")
        lines.append("\n")
    else:
        lines.append("- **Must contain:** What distinguishes this product; keep factual.\n")

    lines.append("## 8. Certifications and standards\n")
    if sheet.certifications_standards:
        lines.append("- **Must contain:** List of certifications/standards:")
        for c in sheet.certifications_standards:
            lines.append(f"  - {c}")
        lines.append("\n")
    else:
        f = _missing_finding("certification") or _missing_finding("compliance")
        lines.append(f"- **Must contain:** Relevant certifications and standards.{_missing_note(f)}\n")

    lines.append("## 9. Integrations and interfaces\n")
    if sheet.integrations_interfaces:
        lines.append("- **Must contain:** Integrations, APIs, interfaces:")
        for i in sheet.integrations_interfaces:
            lines.append(f"  - {i}")
        lines.append("\n")
    else:
        f = _missing_finding("compatibility") or _missing_finding("integration")
        lines.append(f"- **Must contain:** Integration and interface options.{_missing_note(f)}\n")

    lines.append("## 10. Maintenance and calibration\n")
    if sheet.maintenance_calibration:
        lines.append("- **Must contain:** Maintenance, calibration, service intervals:")
        for m in sheet.maintenance_calibration:
            lines.append(f"  - {m}")
        lines.append("\n")
    else:
        lines.append("- **Must contain:** Any stated maintenance or calibration requirements, or TODO: confirm.\n")

    summary = _str_val(sheet.source_coverage_summary)
    lines.append("## 11. Source coverage note\n")
    if summary:
        lines.append(f"- **Context:** {summary}\n")
    else:
        lines.append("- Optional: brief note on which sources were used for this outline.\n")

    return "\n".join(lines)


# Buyer intent groups for FAQ
FAQ_INTENT_GROUPS = [
    ("Overview and positioning", ["product name", "category", "what it is", "who it is for"]),
    ("Use cases and applications", ["use case", "application", "best for", "suitable for"]),
    ("Specifications and performance", ["spec", "performance", "dimension", "accuracy", "range"]),
    ("Constraints and limitations", ["limit", "constraint", "not suitable", "restriction"]),
    ("Integrations and compatibility", ["integration", "interface", "API", "compatibility", "connect"]),
    ("Compliance and support", ["certification", "standard", "maintenance", "calibration", "support", "warranty"]),
]


def build_faq_md(
    sheet: ProductFactSheet,
    findings: list[AuditFinding],
    target_count: tuple[int, int] = (20, 40),
) -> str:
    """20–40 FAQs grouped by buyer intent; answers grounded in factsheet with chunk refs."""
    lines: list[str] = []
    lines.append("# FAQ (grounded in fact sheet)\n")
    lines.append("Answers are based only on the product fact sheet. Missing information is marked with TODO and the related audit finding.\n")

    faqs: list[tuple[str, str, list[str]]] = []  # (intent_group, q, a, chunk_refs)

    # Overview
    name = _str_val(sheet.product_name)
    cat = _str_val(sheet.product_category)
    if name:
        faqs.append(("Overview and positioning", "What is this product?", f"{name}. {cat or ''}".strip(), []))
    else:
        f = next((x for x in findings if "product name" in (x.title or "").lower()), None)
        faqs.append(("Overview and positioning", "What is this product?", f"TODO: confirm.{_missing_note(f) if f else ''}".strip(), []))
    if cat:
        faqs.append(("Overview and positioning", "What category does this product belong to?", cat, []))
    if sheet.target_buyer_roles:
        roles = "; ".join(sheet.target_buyer_roles[:5])
        faqs.append(("Overview and positioning", "Who is this product for?", roles, []))

    # Use cases
    for u in sheet.primary_use_cases[:6]:
        faqs.append(("Use cases and applications", f"What is a typical use case for this product?", u, []))
    if not sheet.primary_use_cases:
        f = next((x for x in findings if "use case" in (x.title or "").lower()), None)
        faqs.append(("Use cases and applications", "What are the main use cases?", f"TODO: confirm.{_missing_note(f) if f else ''}".strip(), []))

    # Specs
    for s in sheet.key_specs[:8]:
        q = f"What is the {s.name}?" if s.name else "What are the key specifications?"
        val = f"{s.value} {s.unit}".strip() if s.value else ""
        if s.conditions:
            val = f"{val} ({s.conditions})".strip()
        ref = _ref_chunks(s.evidence_chunk_ids).strip(" ()")
        a = val or "Not specified in source."
        if s.evidence_chunk_ids:
            a += f" [chunks: {', '.join(s.evidence_chunk_ids[:3])}]"
        faqs.append(("Specifications and performance", q, a, s.evidence_chunk_ids))

    # Constraints
    for c in sheet.constraints[:5]:
        ref = _ref_chunks(c.evidence_chunk_ids).strip(" ()")
        a = c.statement
        if c.evidence_chunk_ids:
            a += f" [chunks: {', '.join(c.evidence_chunk_ids[:3])}]"
        faqs.append(("Constraints and limitations", "What are the limitations or constraints?", a, c.evidence_chunk_ids))
    if not sheet.constraints:
        faqs.append(("Constraints and limitations", "What are the limitations?", "No constraints explicitly stated in the fact sheet. TODO: confirm if none apply.", []))

    # Differentiators
    for d in sheet.differentiators[:4]:
        a = d.statement
        if d.evidence_chunk_ids:
            a += f" [chunks: {', '.join(d.evidence_chunk_ids[:3])}]"
        faqs.append(("Overview and positioning", "What makes this product different?", a, d.evidence_chunk_ids))

    # Integrations
    if sheet.integrations_interfaces:
        a = "; ".join(sheet.integrations_interfaces[:6])
        faqs.append(("Integrations and compatibility", "What integrations or interfaces does it support?", a, []))
    else:
        f = next((x for x in findings if "integration" in (x.title or "").lower() or "compatibility" in (x.title or "").lower()), None)
        faqs.append(("Integrations and compatibility", "What integrations are available?", f"TODO: confirm.{_missing_note(f) if f else ''}".strip(), []))

    # Certifications
    if sheet.certifications_standards:
        a = "; ".join(sheet.certifications_standards)
        faqs.append(("Compliance and support", "What certifications or standards does it meet?", a, []))
    else:
        f = next((x for x in findings if "certification" in (x.title or "").lower()), None)
        faqs.append(("Compliance and support", "What certifications does it have?", f"TODO: confirm.{_missing_note(f) if f else ''}".strip(), []))

    # Maintenance
    if sheet.maintenance_calibration:
        a = "; ".join(sheet.maintenance_calibration)
        faqs.append(("Compliance and support", "What maintenance or calibration is required?", a, []))
    else:
        faqs.append(("Compliance and support", "What maintenance is required?", "Not specified in the fact sheet. TODO: confirm.", []))

    # Extra FAQs to reach 20–40: warranty/support, environmental, sourcing
    faqs.append(("Compliance and support", "What warranty or guarantee is offered?", "Not in fact sheet. TODO: confirm (audit completeness).", []))
    faqs.append(("Compliance and support", "How do I get technical support?", "Not in fact sheet. TODO: confirm (audit completeness).", []))
    faqs.append(("Specifications and performance", "What are the environmental operating conditions?", "See key specifications and constraints above; if not listed, TODO: confirm.", []))
    faqs.append(("Overview and positioning", "Where does this product fit in the lineup?", (_str_val(sheet.product_category) or "TODO: confirm category and positioning."), []))
    if sheet.differentiators:
        faqs.append(("Overview and positioning", "Why choose this over alternatives?", "; ".join(d.statement for d in sheet.differentiators[:3]), []))
    if sheet.primary_use_cases and len(sheet.primary_use_cases) >= 2:
        faqs.append(("Use cases and applications", "What problems does this product solve?", "; ".join(sheet.primary_use_cases[:3]), []))

    # Trim or pad to target range
    low, high = target_count
    if len(faqs) > high:
        faqs = faqs[:high]
    # Group by intent
    by_intent: dict[str, list[tuple[str, str, list[str]]]] = {}
    for intent, q, a, refs in faqs:
        by_intent.setdefault(intent, []).append((q, a, refs))
    for group_name in [g[0] for g in FAQ_INTENT_GROUPS]:
        if group_name not in by_intent:
            continue
        lines.append(f"## {group_name}\n")
        for q, a, _ in by_intent[group_name]:
            lines.append(f"**Q:** {q}\n")
            lines.append(f"**A:** {a}\n")
        lines.append("")
    return "\n".join(lines)


def build_comparison_md(sheet: ProductFactSheet) -> str:
    """Dimensions buyers compare + suggested table template + best for / not ideal for."""
    lines: list[str] = []
    lines.append("# Comparison guide\n")
    lines.append("Factual dimensions and suggested comparison table. Best for / not ideal for derived from use cases and constraints.\n")

    # Dimensions from key_specs, constraints, differentiators
    lines.append("## Comparison dimensions\n")
    lines.append("Use these dimensions when comparing with alternatives. All values are from the fact sheet.\n")
    dims: list[str] = []
    for s in sheet.key_specs:
        if s.name:
            dims.append(s.name)
    for c in sheet.constraints:
        if c.statement:
            dims.append("Constraints / limits")
            break
    for d in sheet.differentiators:
        if d.statement:
            dims.append("Differentiators")
            break
    if sheet.certifications_standards:
        dims.append("Certifications")
    if sheet.integrations_interfaces:
        dims.append("Integrations")
    for d in dims:
        lines.append(f"- {d}")
    lines.append("")

    # Table template
    lines.append("## Suggested comparison table\n")
    lines.append("| Dimension | This product | Alternative A | Alternative B |")
    lines.append("|-----------|---------------|----------------|----------------|")
    for s in sheet.key_specs[:12]:
        if s.name:
            val = f"{s.value} {s.unit}".strip() or "—"
            if s.conditions:
                val += f" ({s.conditions})"
            lines.append(f"| {s.name} | {val} | — | — |")
    if sheet.constraints:
        parts = [c.statement[:50] + ("..." if len(c.statement) > 50 else "") for c in sheet.constraints[:3]]
        lines.append("| Constraints | " + "; ".join(parts) + " | — | — |")
    lines.append("")

    # Best for / not ideal for
    lines.append("## Best for\n")
    if sheet.primary_use_cases:
        for u in sheet.primary_use_cases:
            lines.append(f"- {u}")
        lines.append("")
    else:
        lines.append("- TODO: confirm primary use cases from source.\n")
    if sheet.target_buyer_roles:
        lines.append("**Target roles:** " + ", ".join(sheet.target_buyer_roles) + "\n")

    lines.append("## Not ideal for\n")
    if sheet.constraints:
        for c in sheet.constraints:
            lines.append(f"- {c.statement}")
        lines.append("")
    else:
        lines.append("- No constraints explicitly stated; confirm with product owner if there are known mismatches.\n")

    return "\n".join(lines)


def build_jsonld_skeleton(sheet: ProductFactSheet, findings: list[AuditFinding]) -> dict[str, Any]:
    """schema.org Product/ProductModel draft using available fact sheet fields. Missing fields omitted or TODO."""
    obj: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
    }
    name = _str_val(sheet.product_name)
    obj["name"] = name if name else "TODO: confirm product name (audit completeness)"
    desc = _str_val(sheet.source_coverage_summary)
    if desc:
        obj["description"] = desc
    else:
        obj["description"] = "TODO: add short description (audit)"
    cat = _str_val(sheet.product_category)
    if cat:
        obj["category"] = cat
    # ProductModel-style: additionalProperty for specs
    if sheet.key_specs:
        props: list[dict[str, Any]] = []
        for s in sheet.key_specs:
            if s.name or s.value:
                prop: dict[str, Any] = {"@type": "PropertyValue", "name": s.name or "spec", "value": s.value}
                if s.unit:
                    prop["unitText"] = s.unit
                if s.evidence_chunk_ids:
                    prop["evidence_chunk_ids"] = s.evidence_chunk_ids[:5]
                props.append(prop)
        obj["additionalProperty"] = props
    # Brand/sku if we had them in strict schema we could add; strict schema doesn't have manufacturer/model_number
    # Certifications
    if sheet.certifications_standards:
        obj["certification"] = [{"@type": "Certification", "name": c} for c in sheet.certifications_standards]
    return obj


def generate_content_pack_from_factsheet(
    sheet: ProductFactSheet,
    scorecard: Scorecard | None,
    findings: list[AuditFinding],
    out_dir: Path,
) -> dict[str, Path]:
    """Write product_page_outline.md, faq.md, comparison.md, jsonld_product_skeleton.json to out_dir. Returns paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    outline_path = out_dir / "product_page_outline.md"
    outline_path.write_text(build_product_page_outline(sheet, findings), encoding="utf-8")
    written["product_page_outline.md"] = outline_path

    faq_path = out_dir / "faq.md"
    faq_path.write_text(build_faq_md(sheet, findings), encoding="utf-8")
    written["faq.md"] = faq_path

    comparison_path = out_dir / "comparison.md"
    comparison_path.write_text(build_comparison_md(sheet), encoding="utf-8")
    written["comparison.md"] = comparison_path

    jsonld_path = out_dir / "jsonld_product_skeleton.json"
    jsonld = build_jsonld_skeleton(sheet, findings)
    jsonld_path.write_text(json.dumps(jsonld, indent=2), encoding="utf-8")
    written["jsonld_product_skeleton.json"] = jsonld_path

    return written
