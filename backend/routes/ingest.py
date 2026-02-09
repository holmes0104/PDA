"""Ingest API routes."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from pda.config import get_settings
from pda.ingest.ingest_pipeline import run_ingestion

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

# Max upload size from settings (default 50 MB)
MAX_UPLOAD_BYTES = settings.max_upload_bytes


class IngestResponse(BaseModel):
    project_id: str
    chunks_count: int
    chunks_path: str
    raw_extraction_path: str
    document_type: str = ""
    document_type_confidence: float = 0.0


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_pdf(
    pdf: UploadFile = File(..., description="PDF file to ingest"),
    url: Optional[str] = Form(None, description="Optional product page URL to scrape"),
    project_id: Optional[str] = Form(None, description="Optional project ID"),
):
    """Ingest PDF (and optional URL), chunk, save to project directory."""
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Read file content and enforce size limit
    content = await pdf.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    # Generate project_id if not provided
    if not project_id:
        import uuid
        project_id = str(uuid.uuid4())

    project_dir = settings.data_dir / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded PDF
    pdf_path = project_dir / pdf.filename
    with open(pdf_path, "wb") as f:
        f.write(content)

    logger.info("Ingesting PDF: %s (project: %s, url: %s)", pdf.filename, project_id, url or "none")

    try:
        chunks, classification = run_ingestion(
            pdf_path=str(pdf_path),
            url=url,
            out_dir=project_dir,
        )
    except Exception as e:
        logger.exception("Ingestion failed")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    return IngestResponse(
        project_id=project_id,
        chunks_count=len(chunks),
        chunks_path=str(project_dir / "chunks.jsonl"),
        raw_extraction_path=str(project_dir / "raw_extraction"),
        document_type=classification.document_type.value,
        document_type_confidence=round(classification.confidence, 2),
    )
