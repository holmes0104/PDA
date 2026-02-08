"""Export Pydantic models to JSON Schema files for documentation."""

import json
from pathlib import Path

from pda.schemas.models import (
    AuditFinding,
    DocumentChunk,
    EvidenceRef,
    FactValue,
    ProductFactSheet,
    PromptTestResult,
    RubricDimension,
    Scorecard,
    SinglePromptResult,
)

SCHEMA_MODELS = [
    ("DocumentChunk", DocumentChunk),
    ("EvidenceRef", EvidenceRef),
    ("FactValue", FactValue),
    ("ProductFactSheet", ProductFactSheet),
    ("AuditFinding", AuditFinding),
    ("RubricDimension", RubricDimension),
    ("Scorecard", Scorecard),
    ("SinglePromptResult", SinglePromptResult),
    ("PromptTestResult", PromptTestResult),
]


def export_json_schemas(output_dir: str | Path = "schemas_docs") -> None:
    """Write each model's JSON schema to output_dir."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMA_MODELS:
        schema = model.model_json_schema()
        path = out / f"{name}.json"
        path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
