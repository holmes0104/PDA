"""Content Pack API routes — generate LLM-ready product content bundles."""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status
try:
    from openai import APIError, APIStatusError, RateLimitError
except ImportError:
    APIError = type("APIError", (Exception,), {})
    APIStatusError = type("APIStatusError", (Exception,), {})
    RateLimitError = type("RateLimitError", (Exception,), {})
from pydantic import BaseModel, Field

from pda.config import get_settings
from pda.content_pack.llm_ready_pack import (
    generate_content_pack,
    write_content_pack_bundle,
)
from pda.extract.factsheet_extractor import extract_product_fact_sheet
from pda.ingest.chunker import chunk_document
from pda.ingest.pdf_parser import PDFParseError, parse_pdf
from pda.llm import get_provider
from pda.schemas.llm_ready_pack import MissingFactQuestion
from pda.schemas.models import ChunkSource
from pda.store import VectorStoreBackend, get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GenerateContentPackRequest(BaseModel):
    project_id: str
    tone: str = "technical"  # "technical" | "buyer" | "hybrid"
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    proceed_with_assumptions: bool = False


class PreflightQuestionOut(BaseModel):
    field: str = ""
    question: str = ""
    why_needed: str = ""


class PreflightOut(BaseModel):
    product_name: str = ""
    facts_found: int = 0
    facts_expected: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[PreflightQuestionOut] = Field(default_factory=list)
    can_generate: bool = True


class GenerateContentPackResponse(BaseModel):
    project_id: str
    status: str  # "ok" | "preflight_blocked"
    preflight: PreflightOut
    files: dict[str, str] = Field(default_factory=dict)  # filename -> path
    assumptions: list[str] = Field(default_factory=list)
    manifest_path: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_llm(llm_provider: Optional[str], llm_model: Optional[str]):
    provider_name = (llm_provider or settings.pda_llm_provider).lower()
    if provider_name == "openai":
        api_key = settings.openai_api_key
        default_model = settings.pda_openai_model
    else:
        api_key = settings.anthropic_api_key
        default_model = settings.pda_anthropic_model

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"API key not configured for provider '{provider_name}'.",
        )
    model = llm_model or default_model
    return get_provider(provider_name, api_key=api_key, model=model)


def _get_or_build_store(project_id: str, project_dir: Path) -> VectorStoreBackend:
    """Return a vector store populated with the project's chunks.

    Respects ``PDA_VECTOR_BACKEND``:
    * ``chroma``   — on-disk ChromaDB (needs persistent disk, e.g. Render).
    * ``pgvector`` — Postgres + pgvector (stateless-safe, needs DATABASE_URL).
    """
    backend = settings.pda_vector_backend

    persist_dir: str | None = None
    if backend == "chroma":
        chroma_dir = settings.chroma_dir / project_id
        chroma_dir.mkdir(parents=True, exist_ok=True)
        persist_dir = str(chroma_dir)

    logger.debug("Initialising vector store (backend=%s, project=%s)", backend, project_id)
    store = get_vector_store(
        backend=backend,
        collection_name="pda_factsheet",
        persist_directory=persist_dir,
        embedding_model=settings.pda_embedding_model,
        openai_api_key=settings.openai_api_key,
        database_url=settings.pda_database_url,
        project_id=project_id,
    )

    # If collection is already populated (from a prior factsheet run), skip re-indexing
    try:
        existing = store.query("test", n_results=1)
        if existing:
            return store
    except Exception:
        pass

    # Index from PDFs on disk
    pdf_paths = list(project_dir.glob("*.pdf"))
    chunks = []
    for pdf_path in pdf_paths:
        try:
            pages = parse_pdf(str(pdf_path))
            chunks.extend(chunk_document(pages, source_file=pdf_path.name, source_type=ChunkSource.PDF))
        except (PDFParseError, FileNotFoundError) as e:
            logger.warning("Skipping PDF %s: %s", pdf_path, e)

    if chunks:
        store.add_chunks(chunks)

    return store


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/generate_content_pack",
    response_model=GenerateContentPackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_content_pack_endpoint(request: GenerateContentPackRequest):
    """Generate an LLM-ready content pack from an ingested project."""
    project_dir = settings.data_dir / "projects" / request.project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {request.project_id}")

    pdf_paths = list(project_dir.glob("*.pdf"))
    if not pdf_paths:
        raise HTTPException(status_code=400, detail="No PDFs found in project")

    # --- LLM ---
    llm = _resolve_llm(request.llm_provider, request.llm_model)

    # --- Vector store ---
    store = _get_or_build_store(request.project_id, project_dir)

    # --- Fact sheet (load cached or extract) ---
    factsheet_path = project_dir / "factsheet.json"
    if factsheet_path.exists():
        from pda.schemas.factsheet_schema import ProductFactSheet
        with open(factsheet_path, "r", encoding="utf-8") as f:
            sheet = ProductFactSheet(**json.load(f))
        logger.info("Loaded cached fact sheet for %s", request.project_id)
    else:
        logger.info("Extracting fact sheet for %s", request.project_id)
        try:
            sheet, provenance = extract_product_fact_sheet(store, llm)
            # Cache it
            with open(factsheet_path, "w", encoding="utf-8") as f:
                json.dump(sheet.model_dump(), f, indent=2)
            prov_path = project_dir / "factsheet_provenance.json"
            with open(prov_path, "w", encoding="utf-8") as f:
                json.dump(provenance, f, indent=2)
        except Exception as e:
            logger.exception("Fact sheet extraction failed")
            raise HTTPException(status_code=500, detail=f"Fact sheet extraction failed: {str(e)[:300]}")

    # --- Generate content pack ---
    try:
        bundle = generate_content_pack(
            store=store,
            llm_provider=llm,
            sheet=sheet,
            tone=request.tone,
            proceed_with_assumptions=request.proceed_with_assumptions,
        )
        bundle.project_id = request.project_id
    except (RateLimitError, APIStatusError) as e:
        err = str(e)
        if "insufficient_quota" in err.lower() or "payment" in err.lower():
            raise HTTPException(status_code=402, detail=f"API quota issue: {err[:200]}")
        raise HTTPException(status_code=500, detail=f"API error: {err[:300]}")
    except APIError as e:
        raise HTTPException(status_code=500, detail=f"LLM API error: {str(e)[:300]}")
    except Exception as e:
        logger.exception("Content pack generation failed")
        raise HTTPException(status_code=500, detail=f"Content pack generation failed: {str(e)[:300]}")

    # --- Preflight response ---
    pf = bundle.preflight
    preflight_out = PreflightOut(
        product_name=pf.product_name,
        facts_found=pf.facts_found,
        facts_expected=pf.facts_expected,
        missing_fields=pf.missing_fields,
        questions=[PreflightQuestionOut(field=q.field, question=q.question, why_needed=q.why_needed) for q in pf.questions],
        can_generate=pf.can_generate,
    )

    if not pf.can_generate and not request.proceed_with_assumptions:
        return GenerateContentPackResponse(
            project_id=request.project_id,
            status="preflight_blocked",
            preflight=preflight_out,
        )

    # --- Export bundle ---
    pack_dir = project_dir / "content_pack"
    try:
        written = write_content_pack_bundle(bundle, pack_dir)
    except Exception as e:
        logger.exception("Content pack export failed")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)[:300]}")

    files_out = {name: str(path) for name, path in written.items()}
    manifest_path = str(written.get("manifest.json", ""))

    return GenerateContentPackResponse(
        project_id=request.project_id,
        status="ok",
        preflight=preflight_out,
        files=files_out,
        assumptions=bundle.assumptions,
        manifest_path=manifest_path,
    )
