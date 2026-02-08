"""Verifier pass: check evidence grounding, contradictions, and missing units/conditions."""

from pda.verifier.verifier import (
    VerifierResult,
    run_verifier,
    run_verifier_audit_pipeline,
    run_verifier_content_pack,
    run_verifier_factsheet,
    write_verifier_report,
)

__all__ = [
    "VerifierResult",
    "run_verifier",
    "run_verifier_audit_pipeline",
    "run_verifier_content_pack",
    "run_verifier_factsheet",
    "write_verifier_report",
]
