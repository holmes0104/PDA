"""Factsheet API routes."""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
try:
    from openai import APIError, APIStatusError, RateLimitError
except ImportError:
    APIError = type("APIError", (Exception,), {})
    APIStatusError = type("APIStatusError", (Exception,), {})
    RateLimitError = type("RateLimitError", (Exception,), {})
from pydantic import BaseModel

from pda.classify import classify_document, tag_chunks
from pda.config import get_settings
from pda.extract.factsheet_extractor import extract_product_fact_sheet
from pda.ingest.pdf_parser import PDFParseError, parse_pdf
from pda.ingest.chunker import chunk_document
from pda.llm import get_provider
from pda.schemas.models import ChunkSource
from pda.store import get_vector_store
from pda.verifier import run_verifier_factsheet, write_verifier_report

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


class FactsheetRequest(BaseModel):
    project_id: str
    llm_provider: Optional[str] = None   # "openai" | "anthropic" — overrides server default
    llm_model: Optional[str] = None      # e.g. "gpt-4o", "claude-3-5-sonnet-20241022"


class FactsheetResponse(BaseModel):
    project_id: str
    factsheet_path: str
    provenance_path: str
    verifier_report_path: str


def _resolve_llm(llm_provider: Optional[str], llm_model: Optional[str]):
    """Build an LLM provider instance, honouring optional overrides from the request."""
    provider_name = (llm_provider or settings.pda_llm_provider).lower()

    # Resolve API key
    if provider_name == "openai":
        api_key = settings.openai_api_key
        default_model = settings.pda_openai_model
    else:
        api_key = settings.anthropic_api_key
        default_model = settings.pda_anthropic_model

    model = llm_model or default_model
    return get_provider(provider_name, api_key=api_key, model=model)


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

    # --- Document classification & content-role tagging ---
    classification = classify_document(chunks)
    tag_chunks(chunks, classification)
    logger.info(
        "Document classified as %s (confidence=%.2f)",
        classification.document_type.value,
        classification.confidence,
    )
    import json as _json
    cls_path = project_dir / "classification.json"
    with open(cls_path, "w", encoding="utf-8") as _f:
        _json.dump(classification.model_dump(), _f, indent=2, ensure_ascii=False)

    # Vector store — respects PDA_VECTOR_BACKEND (chroma | pgvector)
    backend = settings.pda_vector_backend
    persist_dir: str | None = None
    if backend == "chroma":
        chroma_dir = settings.chroma_dir / request.project_id
        chroma_dir.mkdir(parents=True, exist_ok=True)
        persist_dir = str(chroma_dir)

    logger.info(
        "Initialising vector store (backend=%s, project=%s) — indexing %d chunks",
        backend, request.project_id, len(chunks),
    )
    store = get_vector_store(
        backend=backend,
        collection_name="pda_factsheet",
        persist_directory=persist_dir,
        embedding_model=settings.pda_embedding_model,
        openai_api_key=settings.openai_api_key,
        database_url=settings.pda_database_url,
        project_id=request.project_id,
    )
    store.add_chunks(chunks)

    # Extract fact sheet — use request-level LLM overrides if provided
    provider_name = (request.llm_provider or settings.pda_llm_provider).lower()
    if provider_name == "openai":
        api_key = settings.openai_api_key
    else:
        api_key = settings.anthropic_api_key
    
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"API key not configured for provider '{provider_name}'. Please set {'OPENAI_API_KEY' if provider_name == 'openai' else 'ANTHROPIC_API_KEY'} in .env",
        )
    
    llm = _resolve_llm(request.llm_provider, request.llm_model)

    logger.info(
        "Extracting fact sheet (provider=%s, model=%s)",
        request.llm_provider or settings.pda_llm_provider,
        request.llm_model or "default",
    )
    try:
        sheet, provenance = extract_product_fact_sheet(store, llm)
    except (RateLimitError, APIStatusError) as e:
        status_code = getattr(e, "status_code", None)
        err_msg = str(e)
        if status_code == 402 or "insufficient_quota" in err_msg.lower() or "payment" in err_msg.lower() or "429" in err_msg:
            logger.error("API quota/payment error: %s", err_msg)
            raise HTTPException(
                status_code=402,
                detail=f"API quota/payment issue: {err_msg[:200]}. Please check your billing for the selected provider.",
            )
        logger.exception("API error during factsheet extraction")
        raise HTTPException(status_code=500, detail=f"API error during factsheet extraction: {err_msg[:300]}")
    except APIError as e:
        err_msg = str(e)
        logger.exception("OpenAI API error during factsheet extraction")
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {err_msg[:300]}")
    except Exception as e:
        err_msg = str(e)
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
