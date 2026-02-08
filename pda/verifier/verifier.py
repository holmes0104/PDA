"""Verifier pass: identify unsupported statements, contradictions, missing units/conditions."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pda.schemas.factsheet_schema import (
    Constraint,
    Differentiator,
    KeySpec,
    ProductFactSheet as FactsheetSchemaProductFactSheet,
)
from pda.schemas.models import (
    AuditFinding,
    DocumentChunk,
    ProductFactSheet as ModelsProductFactSheet,
    PromptTestResult,
)


@dataclass
class VerifierResult:
    """Result of the verifier pass."""

    blocked_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_queries: list[str] = field(default_factory=list)

    @property
    def has_blocked(self) -> bool:
        return len(self.blocked_issues) > 0


def _check_contradictory_specs_factsheet(sheet: FactsheetSchemaProductFactSheet) -> list[str]:
    """Flag key_specs with same name but different values."""
    issues: list[str] = []
    by_name: dict[str, list[KeySpec]] = {}
    for spec in sheet.key_specs:
        name = (spec.name or "").strip().lower()
        if not name:
            continue
        by_name.setdefault(name, []).append(spec)
    for name, specs in by_name.items():
        values = [f"{s.value}{s.unit or ''}{s.conditions or ''}".strip() for s in specs]
        if len(set(values)) > 1:
            issues.append(
                f"Contradictory spec '{name}': multiple values ({', '.join(repr(v) for v in values[:5])})"
            )
    return issues


def _check_contradictory_specs_models(sheet: ModelsProductFactSheet) -> list[str]:
    """Flag specifications with duplicate keys (case-insensitive) or conflicting values."""
    issues: list[str] = []
    specs = sheet.specifications or {}
    by_key: dict[str, list[tuple[str, Any]]] = {}
    for k, fv in specs.items():
        key_lower = str(k).strip().lower()
        if not key_lower:
            continue
        v = getattr(fv, "value", fv) if hasattr(fv, "value") else fv
        by_key.setdefault(key_lower, []).append((k, v))
    for key_lower, entries in by_key.items():
        if len(entries) > 1:
            values = [str(v) for _, v in entries]
            if len(set(values)) > 1:
                issues.append(
                    f"Contradictory spec '{entries[0][0]}': multiple values ({', '.join(repr(v) for v in values[:5])})"
                )
    return issues


def _check_missing_units_conditions_factsheet(sheet: FactsheetSchemaProductFactSheet) -> list[str]:
    """Flag KeySpecs with numeric values but missing unit or conditions where expected."""
    warnings: list[str] = []
    for i, spec in enumerate(sheet.key_specs):
        if not spec.value or not spec.name:
            continue
        val_str = str(spec.value).strip()
        # Numeric or range-like value often needs units
        if re.search(r"^-?\d+(\.\d+)?\s*[-–]\s*-?\d+", val_str) or re.search(
            r"^-?\d+(\.\d+)?\s*$", val_str
        ):
            if not (spec.unit or spec.conditions):
                # Common units by spec name
                name_lower = (spec.name or "").lower()
                if any(
                    u in name_lower
                    for u in [
                        "weight",
                        "dimension",
                        "length",
                        "width",
                        "height",
                        "temperature",
                        "pressure",
                        "speed",
                        "voltage",
                        "current",
                        "power",
                        "capacity",
                    ]
                ):
                    warnings.append(
                        f"key_specs[{i}] '{spec.name}': value '{spec.value}' likely needs unit or conditions"
                    )
    return warnings


def _check_missing_units_models(sheet: ModelsProductFactSheet) -> list[str]:
    """Flag specifications with numeric values but no unit-like context."""
    warnings: list[str] = []
    specs = sheet.specifications or {}
    for k, fv in specs.items():
        v = getattr(fv, "value", fv) if hasattr(fv, "value") else fv
        if v is None:
            continue
        s = str(v).strip().upper()
        if s == "NOT_FOUND":
            continue
        # Has a bare number but no unit-like suffix
        if re.search(r"^-?\d+(\.\d+)?\s*$", str(v).strip()) and not re.search(
            r"\b(mm|cm|m|kg|g|hz|mb|gb|tb|v|w|a|°c|°f|psi|bar|pa)\b", str(v).lower()
        ):
            k_lower = str(k).lower()
            if any(
                u in k_lower
                for u in [
                    "weight",
                    "dimension",
                    "length",
                    "width",
                    "height",
                    "temperature",
                    "pressure",
                    "voltage",
                    "current",
                    "power",
                ]
            ):
                warnings.append(
                    f"specification '{k}': value '{v}' likely needs units"
                )
    return warnings


def _check_unsupported_recommendations(findings: list[AuditFinding]) -> list[str]:
    """Recommendations without evidence or critic verification."""
    blocked: list[str] = []
    for f in findings:
        if f.is_grounded:
            continue
        if not f.evidence and not f.critic_verified:
            blocked.append(
                f"Recommendation '{f.title}' (finding {f.finding_id}) not supported by evidence or critic"
            )
        elif not f.evidence and f.critic_verified and f.critic_note and "not supported" in (f.critic_note or "").lower():
            blocked.append(
                f"Recommendation '{f.title}' (finding {f.finding_id}) critic indicates not supported"
            )
    return blocked


def _check_content_pack_grounding(
    content_pack: dict[str, Any],
    has_factsheet_fields: bool,
) -> list[str]:
    """Flag content pack statements that may not be grounded (heuristic)."""
    warnings: list[str] = []
    for faq in content_pack.get("faq_pack", []) or []:
        a = faq.get("a", "")
        if a and ("NOT_FOUND" in str(a).upper() or "TODO" in str(a).upper()):
            warnings.append(f"FAQ answer contains NOT_FOUND or TODO: {str(a)[:80]}...")
    for bullet in content_pack.get("comparison_bullets", []) or []:
        if "NOT_FOUND" in str(bullet).upper():
            warnings.append(f"Comparison bullet contains NOT_FOUND: {str(bullet)[:80]}...")
    return warnings


def _suggest_retrieval_queries_factsheet(sheet: FactsheetSchemaProductFactSheet) -> list[str]:
    """Suggest retrieval queries for missing factsheet info."""
    queries: list[str] = []
    if not sheet.product_name or str(sheet.product_name).strip().upper() == "NOT_FOUND":
        queries.append("product name and model identifier")
    if not sheet.product_category or str(sheet.product_category).strip().upper() == "NOT_FOUND":
        queries.append("product category and market positioning")
    if not sheet.primary_use_cases:
        queries.append("primary use cases and applications")
    if not sheet.target_buyer_roles:
        queries.append("target buyer roles and personas")
    if not sheet.key_specs:
        queries.append("key technical specifications dimensions")
    if not sheet.constraints:
        queries.append("constraints limitations restrictions")
    if not sheet.differentiators:
        queries.append("differentiators unique selling points")
    if not sheet.certifications_standards:
        queries.append("certifications standards compliance")
    if not sheet.integrations_interfaces:
        queries.append("integrations interfaces APIs connectivity")
    if not sheet.maintenance_calibration:
        queries.append("maintenance calibration service requirements")
    return queries


def _suggest_retrieval_queries_models(sheet: ModelsProductFactSheet) -> list[str]:
    """Suggest retrieval queries for missing model fact sheet info."""
    queries: list[str] = []
    not_found = lambda v: (
        v is None
        or (hasattr(v, "value") and (getattr(v, "value") is None or str(getattr(v, "value", "")).strip().upper() == "NOT_FOUND"))
        or (isinstance(v, str) and v.strip().upper() == "NOT_FOUND")
    )
    if not_found(sheet.product_name):
        queries.append("product name and model identifier")
    if not_found(sheet.manufacturer):
        queries.append("manufacturer brand company")
    if not_found(sheet.model_number):
        queries.append("model number SKU part number")
    if not_found(sheet.category):
        queries.append("product category classification")
    if not_found(sheet.short_description):
        queries.append("short description value proposition")
    if not_found(sheet.target_audience):
        queries.append("target audience buyer personas")
    if not_found(sheet.pricing):
        queries.append("pricing cost list price")
    if not sheet.key_features:
        queries.append("key features capabilities")
    if not sheet.specifications:
        queries.append("technical specifications dimensions")
    if not sheet.use_cases:
        queries.append("use cases applications")
    return queries


def run_verifier_factsheet(
    sheet: FactsheetSchemaProductFactSheet,
    provenance: dict[str, list[str]] | None = None,
) -> VerifierResult:
    """Run verifier for factsheet pipeline (strict schema)."""
    blocked: list[str] = []
    warnings: list[str] = []

    # Unsupported: items with content but no evidence
    for i, spec in enumerate(sheet.key_specs):
        if (spec.name or spec.value) and not spec.evidence_chunk_ids:
            blocked.append(
                f"key_specs[{i}] '{spec.name}': '{spec.value}' has no evidence_chunk_ids"
            )
    for i, c in enumerate(sheet.constraints):
        if c.statement and not c.evidence_chunk_ids:
            blocked.append(
                f"constraints[{i}] has statement but no evidence_chunk_ids"
            )
    for i, d in enumerate(sheet.differentiators):
        if d.statement and not d.evidence_chunk_ids:
            blocked.append(
                f"differentiators[{i}] has statement but no evidence_chunk_ids"
            )

    blocked.extend(_check_contradictory_specs_factsheet(sheet))
    warnings.extend(_check_missing_units_conditions_factsheet(sheet))
    suggested = _suggest_retrieval_queries_factsheet(sheet)

    return VerifierResult(
        blocked_issues=blocked,
        warnings=warnings,
        suggested_queries=suggested,
    )


def run_verifier_audit_pipeline(
    fact_sheet: ModelsProductFactSheet,
    findings: list[AuditFinding],
    content_pack: dict[str, Any],
    prompt_results: list[PromptTestResult] | None = None,
    chunks: list[DocumentChunk] | None = None,
) -> VerifierResult:
    """Run verifier for audit pipeline (models schema)."""
    blocked: list[str] = []
    warnings: list[str] = []

    blocked.extend(_check_unsupported_recommendations(findings))
    blocked.extend(_check_contradictory_specs_models(fact_sheet))
    warnings.extend(_check_missing_units_models(fact_sheet))
    warnings.extend(
        _check_content_pack_grounding(content_pack, has_factsheet_fields=True)
    )

    # Simulation: low grounding suggests missing info
    if prompt_results:
        for pr in prompt_results:
            if pr.average_grounding < 0.5:
                warnings.append(
                    f"Simulation '{pr.variant_label}': low grounding ({pr.average_grounding:.2f}), consider more retrieval"
                )
            for r in pr.results:
                if r.missing_info and len(r.missing_info) > 2:
                    for mi in r.missing_info[:3]:
                        if mi and mi not in (s.split("?")[0].strip() for s in warnings):
                            warnings.append(
                                f"Missing info (simulation): {str(mi)[:80]}..."
                            )

    suggested = _suggest_retrieval_queries_models(fact_sheet)
    return VerifierResult(
        blocked_issues=blocked,
        warnings=warnings,
        suggested_queries=suggested,
    )


def run_verifier_content_pack(
    sheet: FactsheetSchemaProductFactSheet,
    findings: list[AuditFinding],
    provenance: dict[str, list[str]] | None = None,
) -> VerifierResult:
    """Run verifier for content-pack pipeline (factsheet schema + audit findings)."""
    result = run_verifier_factsheet(sheet, provenance)
    # Also check findings for unsupported recommendations
    result.blocked_issues.extend(_check_unsupported_recommendations(findings))
    return result


def run_verifier(
    *,
    factsheet_schema_sheet: FactsheetSchemaProductFactSheet | None = None,
    models_sheet: ModelsProductFactSheet | None = None,
    provenance: dict[str, list[str]] | None = None,
    findings: list[AuditFinding] | None = None,
    content_pack: dict[str, Any] | None = None,
    prompt_results: list[PromptTestResult] | None = None,
    chunks: list[DocumentChunk] | None = None,
) -> VerifierResult:
    """
    Unified verifier entry. Prefer factsheet_schema_sheet for factsheet pipeline,
    models_sheet for audit pipeline.
    """
    if factsheet_schema_sheet is not None:
        return run_verifier_factsheet(factsheet_schema_sheet, provenance)
    if models_sheet is not None:
        return run_verifier_audit_pipeline(
            models_sheet,
            findings=findings or [],
            content_pack=content_pack or {},
            prompt_results=prompt_results,
            chunks=chunks,
        )
    return VerifierResult()


def write_verifier_report(result: VerifierResult, output_path: Path) -> None:
    """Write verifier_report.md to output_path."""
    lines: list[str] = []
    lines.append("# Verifier Report\n")
    lines.append("## Blocked issues (must fix)\n")
    if result.blocked_issues:
        for issue in result.blocked_issues:
            lines.append(f"- {issue}\n")
    else:
        lines.append("- None\n")
    lines.append("\n## Warnings (review)\n")
    if result.warnings:
        for w in result.warnings:
            lines.append(f"- {w}\n")
    else:
        lines.append("- None\n")
    lines.append("\n## Suggested retrieval queries\n")
    if result.suggested_queries:
        for q in result.suggested_queries:
            lines.append(f"- `{q}`\n")
    else:
        lines.append("- None\n")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(lines), encoding="utf-8")
