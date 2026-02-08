"""Factsheet API routes."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from pda.config import get_settings
from pda.extract.factsheet_extractor import extract_product_fact_sheet
from pda.ingest.pdf_parser import PDFParseError, parse_pdf
from pda.ingest.chunker import chunk_document
from pda.llm import get_provider
from pda.schemas.models import ChunkSource
from pda.store.vectorstore import VectorStore
from pda.verifier import run_verifier_factsheet, write_verifier_report

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


class FactsheetRequest(BaseModel):
    project_id: str


class FactsheetResponse(BaseModel):
    project_id: str
    factsheet_path: str
    provenance_path: str
    verifier_report_path: str


@router.post("/factsheet", response_model=FactsheetResponse, status_code=status.HTTP_201_CREATED)
async def extract_factsheet(request: FactsheetRequest):
    """Extract product fact sheet from project PDFs."""
    project_dir = settings.data_dir / "projects" / request.project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {request.project_id}")

    # Find PDFs in project
    pdf_paths = list(project_dir.glob("*.pdf"))
    if not pdf_paths:
        raise HTTPException(status_code=400, detail="No PDFs found in project")

    chunks = []
    for pdf_path in pdf_paths:
        try:
            pages = parse_pdf(str(pdf_path))
            chunks.extend(chunk_document(pages, source_file=pdf_path.name, source_type=ChunkSource.PDF))
        except (PDFParseError, FileNotFoundError) as e:
            logger.warning("Skipping PDF %s: %s", pdf_path, e)

    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks extracted from PDFs")

    # Vector store
    chroma_dir = settings.chroma_dir / request.project_id
    chroma_dir.mkdir(parents=True, exist_ok=True)
    store = VectorStore(
        collection_name="pda_factsheet",
        persist_directory=str(chroma_dir),
        embedding_model=settings.pda_embedding_model,
        openai_api_key=settings.openai_api_key,
    )
    logger.info("Indexing %d chunks", len(chunks))
    store.add_chunks(chunks)

    # Extract fact sheet
    provider_name = settings.pda_llm_provider.lower()
    llm = get_provider(
        provider_name,
        api_key=settings.openai_api_key if provider_name == "openai" else settings.anthropic_api_key,
        model=settings.pda_openai_model if provider_name == "openai" else settings.pda_anthropic_model,
    )

    logger.info("Extracting fact sheet")
    try:
        sheet, provenance = extract_product_fact_sheet(store, llm)
    except Exception as e:
        err_msg = str(e)
        if "insufficient_quota" in err_msg or "429" in err_msg:
            raise HTTPException(
                status_code=402,
                detail="OpenAI API quota exceeded. Please check your billing at https://platform.openai.com/settings/organization/billing",
            )
        logger.exception("Factsheet extraction failed")
        raise HTTPException(status_code=500, detail=f"Factsheet extraction failed: {err_msg[:300]}")

    # Save factsheet
    factsheet_path = project_dir / "factsheet.json"
    with open(factsheet_path, "w", encoding="utf-8") as f:
        json.dump(sheet.model_dump(), f, indent=2)

    provenance_path = project_dir / "factsheet_provenance.json"
    with open(provenance_path, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)

    # Verifier
    verifier_result = run_verifier_factsheet(sheet, provenance)
    verifier_path = project_dir / "verifier_report.md"
    write_verifier_report(verifier_result, verifier_path)

    return FactsheetResponse(
        project_id=request.project_id,
        factsheet_path=str(factsheet_path),
        provenance_path=str(provenance_path),
        verifier_report_path=str(verifier_path),
    )
