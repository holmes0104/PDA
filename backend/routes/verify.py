"""Verify API routes."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from pda.config import get_settings
from pda.content_pack.content_pack_from_factsheet import load_audit, load_factsheet
from pda.verifier import VerifierResult, run_verifier_content_pack, run_verifier_factsheet, write_verifier_report

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


class VerifyRequest(BaseModel):
    project_id: str
    factsheet_path: str
    audit_path: str


class VerifyResponse(BaseModel):
    project_id: str
    verifier_report_path: str
    has_blocked: bool


@router.post("/verify", response_model=VerifyResponse, status_code=status.HTTP_201_CREATED)
async def run_verify(request: VerifyRequest):
    """Run verifier on factsheet + audit."""
    project_dir = settings.data_dir / "projects" / request.project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {request.project_id}")

    factsheet_path = project_dir / request.factsheet_path if not Path(request.factsheet_path).is_absolute() else Path(request.factsheet_path)
    audit_path = project_dir / request.audit_path if not Path(request.audit_path).is_absolute() else Path(request.audit_path)

    if not factsheet_path.exists():
        raise HTTPException(status_code=404, detail=f"Factsheet not found: {factsheet_path}")
    if not audit_path.exists():
        raise HTTPException(status_code=404, detail=f"Audit file not found: {audit_path}")

    sheet = load_factsheet(factsheet_path)
    scorecard, findings = load_audit(audit_path)

    provenance_path = factsheet_path.parent / "factsheet_provenance.json"
    provenance = {}
    if provenance_path.exists():
        import json
        with open(provenance_path, encoding="utf-8") as f:
            provenance = json.load(f)

    r1 = run_verifier_factsheet(sheet, provenance)
    r2 = run_verifier_content_pack(sheet, findings, provenance)
    merged = VerifierResult(
        blocked_issues=r1.blocked_issues + r2.blocked_issues,
        warnings=r1.warnings + r2.warnings,
        suggested_queries=list(dict.fromkeys(r1.suggested_queries + r2.suggested_queries)),
    )

    output_dir = project_dir / "outputs"
    output_dir.mkdir(exist_ok=True)
    verifier_path = output_dir / "verifier_report.md"
    write_verifier_report(merged, verifier_path)

    return VerifyResponse(
        project_id=request.project_id,
        verifier_report_path=str(verifier_path),
        has_blocked=merged.has_blocked,
    )
