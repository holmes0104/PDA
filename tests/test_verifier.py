"""Tests for verifier pass."""

import pytest

from pda.schemas.factsheet_schema import (
    KeySpec,
    ProductFactSheet as FactsheetProductFactSheet,
)
from pda.schemas.models import (
    AuditFinding,
    FindingCategory,
    FindingSeverity,
    ProductFactSheet as ModelsProductFactSheet,
    FactValue,
    PromptTestResult,
    SinglePromptResult,
)
from pda.verifier import (
    run_verifier_audit_pipeline,
    run_verifier_factsheet,
    run_verifier_content_pack,
    write_verifier_report,
)


def test_run_verifier_factsheet_empty_evidence_blocked():
    """Statements without evidence_chunk_ids should be blocked."""
    sheet = FactsheetProductFactSheet(
        product_name="Test Product",
        key_specs=[
            KeySpec(name="Weight", value="5", unit="", conditions="", evidence_chunk_ids=[]),
        ],
    )
    result = run_verifier_factsheet(sheet, None)
    assert result.has_blocked
    assert any("evidence_chunk_ids" in issue for issue in result.blocked_issues)


def test_run_verifier_factsheet_with_evidence_no_blocked():
    """Statements with evidence should not be blocked for that reason."""
    sheet = FactsheetProductFactSheet(
        product_name="Test Product",
        key_specs=[
            KeySpec(name="Weight", value="5", unit="kg", conditions="", evidence_chunk_ids=["c1"]),
        ],
    )
    result = run_verifier_factsheet(sheet, None)
    assert not any("evidence_chunk_ids" in issue for issue in result.blocked_issues)


def test_run_verifier_factsheet_contradictory_specs():
    """Same spec name with different values should be flagged."""
    sheet = FactsheetProductFactSheet(
        key_specs=[
            KeySpec(name="Weight", value="5", unit="kg", conditions="", evidence_chunk_ids=["c1"]),
            KeySpec(name="weight", value="10", unit="kg", conditions="", evidence_chunk_ids=["c2"]),
        ],
    )
    result = run_verifier_factsheet(sheet, None)
    assert any("Contradictory" in issue for issue in result.blocked_issues)


def test_run_verifier_factsheet_missing_units_warning():
    """Numeric specs without units should produce warnings."""
    sheet = FactsheetProductFactSheet(
        key_specs=[
            KeySpec(name="Weight", value="5", unit="", conditions="", evidence_chunk_ids=["c1"]),
        ],
    )
    result = run_verifier_factsheet(sheet, None)
    assert any("unit" in w.lower() for w in result.warnings)


def test_run_verifier_factsheet_suggested_queries():
    """Missing fields should produce suggested retrieval queries."""
    sheet = FactsheetProductFactSheet(
        product_name="NOT_FOUND",
        key_specs=[],
    )
    result = run_verifier_factsheet(sheet, None)
    assert len(result.suggested_queries) > 0
    assert any("product name" in q.lower() for q in result.suggested_queries)


def test_run_verifier_audit_pipeline_unsupported_recommendation():
    """Recommendations without evidence or critic verification should be blocked."""
    findings = [
        AuditFinding(
            finding_id="F-001",
            title="Add product name",
            recommendation="Add product name",
            is_grounded=False,
            evidence=[],
            critic_verified=False,
        ),
    ]
    fact_sheet = ModelsProductFactSheet()
    content_pack = {}
    result = run_verifier_audit_pipeline(
        fact_sheet,
        findings=findings,
        content_pack=content_pack,
    )
    assert result.has_blocked
    assert any("Recommendation" in issue for issue in result.blocked_issues)


def test_run_verifier_audit_pipeline_allow_critic_verified():
    """Recommendations with critic_verified=True should not be blocked for lack of evidence."""
    findings = [
        AuditFinding(
            finding_id="F-001",
            title="Add product name",
            recommendation="Add product name",
            is_grounded=False,
            evidence=[],
            critic_verified=True,
        ),
    ]
    fact_sheet = ModelsProductFactSheet()
    content_pack = {}
    result = run_verifier_audit_pipeline(
        fact_sheet,
        findings=findings,
        content_pack=content_pack,
    )
    assert not any("Recommendation" in issue for issue in result.blocked_issues)


def test_write_verifier_report(tmp_path):
    """Verifier report should be written to file."""
    from pda.verifier import VerifierResult

    result = VerifierResult(
        blocked_issues=["issue 1"],
        warnings=["warning 1"],
        suggested_queries=["query 1"],
    )
    out = tmp_path / "verifier_report.md"
    write_verifier_report(result, out)
    content = out.read_text()
    assert "Blocked issues" in content
    assert "issue 1" in content
    assert "Warnings" in content
    assert "warning 1" in content
    assert "Suggested retrieval queries" in content
    assert "query 1" in content
