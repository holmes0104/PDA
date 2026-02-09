"""Gap analysis: generate AuditFindings for missing or weak areas in the fact sheet and scorecard."""

from pda.schemas.models import (
    AuditFinding,
    EvidenceRef,
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
    deterministic_results: list | None = None,
    llm_results: list | None = None,
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

    # Low scorecard dimensions (both deterministic and LLM)
    for dim in scorecard.dimensions:
        if dim.score < 5:
            cat = FindingCategory.STRUCTURE if "structural" in dim.dimension_id else FindingCategory.DISCOVERABILITY
            findings.append(
                AuditFinding(
                    finding_id=f"F-{fid:03d}",
                    category=cat,
                    severity=FindingSeverity.MEDIUM,
                    title=f"Low score: {dim.name}",
                    description=dim.details,
                    evidence=dim.evidence,
                    is_grounded=False,
                    recommendation=f"Improve {dim.name.lower()} to increase LLM-readiness.",
                    critic_verified=False,
                )
            )
            fid += 1

    # Incorporate deterministic check recommendations
    if deterministic_results:
        for cr in deterministic_results:
            for rec in getattr(cr, "recommendations", []):
                findings.append(
                    AuditFinding(
                        finding_id=f"F-{fid:03d}",
                        category=FindingCategory.STRUCTURE,
                        severity=FindingSeverity.MEDIUM,
                        title=f"Check: {getattr(cr, 'name', '')}",
                        description=getattr(cr, "details", ""),
                        evidence=[EvidenceRef(chunk_ids=getattr(cr, "evidence_chunk_ids", []))]
                        if getattr(cr, "evidence_chunk_ids", [])
                        else [],
                        is_grounded=False,
                        recommendation=rec,
                        critic_verified=False,
                    )
                )
                fid += 1

    # Incorporate LLM check recommendations
    if llm_results:
        for lr in llm_results:
            for rec in getattr(lr, "recommendations", []):
                findings.append(
                    AuditFinding(
                        finding_id=f"F-{fid:03d}",
                        category=FindingCategory.DISCOVERABILITY,
                        severity=FindingSeverity.MEDIUM,
                        title=f"LLM check: {getattr(lr, 'name', '')}",
                        description=getattr(lr, "rationale", ""),
                        evidence=[EvidenceRef(chunk_ids=getattr(lr, "evidence_chunk_ids", []))]
                        if getattr(lr, "evidence_chunk_ids", [])
                        else [],
                        is_grounded=False,
                        recommendation=rec,
                        critic_verified=False,
                    )
                )
                fid += 1

    # Sort findings by severity (critical first) then by expected score impact
    severity_order = {
        FindingSeverity.CRITICAL: 0,
        FindingSeverity.HIGH: 1,
        FindingSeverity.MEDIUM: 2,
        FindingSeverity.LOW: 3,
        FindingSeverity.INFO: 4,
    }
    findings.sort(key=lambda f: severity_order.get(f.severity, 5))

    return findings
