"""Gap analysis: generate AuditFindings for missing or weak areas in the fact sheet and scorecard."""

from pda.schemas.models import (
    AuditFinding,
    FindingCategory,
    FindingSeverity,
    ProductFactSheet,
    Scorecard,
)

NOT_FOUND_STR = "NOT_FOUND"


def _is_missing(fv: object) -> bool:
    if fv is None:
        return True
    v = getattr(fv, "value", fv) if hasattr(fv, "value") else fv
    if v is None:
        return True
    if isinstance(v, str) and v.strip().upper() == NOT_FOUND_STR:
        return True
    return False


def run_gap_analysis(
    fact_sheet: ProductFactSheet,
    scorecard: Scorecard,
) -> list[AuditFinding]:
    """
    Generate findings for missing fields and low-scoring dimensions.
    All generated findings have is_grounded=False (recommendations, not facts).
    """
    findings: list[AuditFinding] = []
    fid = 1

    # Missing fact-sheet fields
    checks = [
        ("product_name", "Product name", FindingSeverity.CRITICAL),
        ("manufacturer", "Manufacturer", FindingSeverity.HIGH),
        ("model_number", "Model number", FindingSeverity.HIGH),
        ("category", "Category", FindingSeverity.MEDIUM),
        ("short_description", "Short description", FindingSeverity.HIGH),
        ("target_audience", "Target audience", FindingSeverity.MEDIUM),
        ("pricing", "Pricing", FindingSeverity.MEDIUM),
        ("warranty", "Warranty", FindingSeverity.LOW),
        ("support_info", "Support information", FindingSeverity.LOW),
    ]
    for field, label, severity in checks:
        fv = getattr(fact_sheet, field, None)
        if _is_missing(fv):
            findings.append(
                AuditFinding(
                    finding_id=f"F-{fid:03d}",
                    category=FindingCategory.COMPLETENESS,
                    severity=severity,
                    title=f"Missing: {label}",
                    description=f"The field '{label}' was not found in the source material.",
                    evidence=[],
                    is_grounded=False,
                    recommendation=f"Add explicit {label.lower()} to the brochure or product page.",
                    critic_verified=False,
                )
            )
            fid += 1

    if not fact_sheet.key_features:
        findings.append(
            AuditFinding(
                finding_id=f"F-{fid:03d}",
                category=FindingCategory.COMPLETENESS,
                severity=FindingSeverity.HIGH,
                title="Missing: Key features",
                description="No key features were extracted.",
                evidence=[],
                is_grounded=False,
                recommendation="List 3–5 key features with short descriptions.",
                critic_verified=False,
            )
        )
        fid += 1

    if not fact_sheet.specifications:
        findings.append(
            AuditFinding(
                finding_id=f"F-{fid:03d}",
                category=FindingCategory.COMPLETENESS,
                severity=FindingSeverity.MEDIUM,
                title="Missing: Specifications",
                description="No specifications table or list was found.",
                evidence=[],
                is_grounded=False,
                recommendation="Add a specifications section with units and values.",
                critic_verified=False,
            )
        )
        fid += 1

    # Low scorecard dimensions
    for dim in scorecard.dimensions:
        if dim.score < 5 and dim.scoring_method == "deterministic":
            findings.append(
                AuditFinding(
                    finding_id=f"F-{fid:03d}",
                    category=FindingCategory.STRUCTURE if "structural" in dim.dimension_id else FindingCategory.DISCOVERABILITY,
                    severity=FindingSeverity.MEDIUM,
                    title=f"Low score: {dim.name}",
                    description=dim.details,
                    evidence=[],
                    is_grounded=False,
                    recommendation=f"Improve {dim.name.lower()} to increase LLM-readiness.",
                    critic_verified=False,
                )
            )
            fid += 1

    return findings
