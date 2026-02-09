"""Web Content API route — async generation with job polling.

POST /api/products/{product_id}/generate-content
  → Creates GenerationJob, returns { job_id, status } immediately.
  → Background task runs generation.

GET /api/generation-jobs/{job_id}
  → Returns status, progress, drafts (when ready).
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import Response

try:
    from openai import APIError, APIStatusError, RateLimitError
except ImportError:
    APIError = type("APIError", (Exception,), {})
    APIStatusError = type("APIStatusError", (Exception,), {})
    RateLimitError = type("RateLimitError", (Exception,), {})

from pda.config import get_settings
from pda.content_pack.web_content_generator import (
    generate_web_content,
    load_factsheet,
)
from pda.drafts import get_drafts_store
from pda.jobs import GenerationJob, JobStatus, get_job_store, _new_job_id
from pda.llm import get_provider
from pda.schemas.web_content_schemas import (
    GenerateContentJobResponse,
    GenerateWebContentRequest,
    GenerateWebContentResponse,
    GenerationJobStatusResponse,
)
from pda.store import VectorStoreBackend, get_vector_store
from pda.ingest.chunker import chunk_document
from pda.ingest.pdf_parser import PDFParseError, parse_pdf
from pda.schemas.models import ChunkSource

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _idempotency_key(product_id: str, request: GenerateWebContentRequest) -> str:
    """Stable hash for retry-safe idempotency."""
    payload = f"{product_id}|{request.tone}|{request.length}|{request.audience}|{request.llm_provider or ''}|{request.llm_model or ''}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _resolve_llm(llm_provider: Optional[str], llm_model: Optional[str]):
    """Return (provider_instance, provider_name, model_name)."""
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
    return get_provider(provider_name, api_key=api_key, model=model), provider_name, model


def _get_or_build_store(project_id: str, project_dir: Path) -> VectorStoreBackend:
    """Return a vector store populated with the project's chunks.

    Respects ``PDA_VECTOR_BACKEND``:
    * ``chroma``   — on-disk ChromaDB (needs persistent disk, e.g. Render).
    * ``pgvector`` — Postgres + pgvector (stateless-safe, needs DATABASE_URL).
    """
    backend = settings.pda_vector_backend

    # For chroma, ensure the persist directory exists on the host.
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

    try:
        existing = store.query("test", n_results=1)
        if existing:
            return store
    except Exception:
        pass

    pdf_paths = list(project_dir.glob("*.pdf"))
    chunks = []
    for pdf_path in pdf_paths:
        try:
            pages = parse_pdf(str(pdf_path))
            chunks.extend(
                chunk_document(pages, source_file=pdf_path.name, source_type=ChunkSource.PDF)
            )
        except (PDFParseError, FileNotFoundError) as e:
            logger.warning("Skipping PDF %s: %s", pdf_path, e)

    if chunks:
        store.add_chunks(chunks)

    return store


def _load_or_extract_factsheet(project_dir: Path, llm, store):
    """Load cached factsheet or extract if missing. Returns (sheet, factsheet_path)."""
    factsheet_path = project_dir / "factsheet.json"
    if factsheet_path.exists():
        sheet = load_factsheet(factsheet_path)
        return sheet, str(factsheet_path)

    from pda.extract.factsheet_extractor import extract_product_fact_sheet

    try:
        sheet, provenance = extract_product_fact_sheet(store, llm)
        with open(factsheet_path, "w", encoding="utf-8") as f:
            json.dump(sheet.model_dump(), f, indent=2)
        prov_path = project_dir / "factsheet_provenance.json"
        with open(prov_path, "w", encoding="utf-8") as f:
            json.dump(provenance, f, indent=2)
        return sheet, str(factsheet_path)
    except Exception as e:
        raise RuntimeError(f"Fact sheet extraction failed: {str(e)[:300]}")


def _run_generation_task(job_id: str, product_id: str, params: dict) -> None:
    """Background task: run generation and update job state."""
    store = get_job_store()
    job = store.get(job_id)
    if not job or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        return

    job.status = JobStatus.RUNNING
    job.progress = 10
    store.update(job)

    project_dir = settings.data_dir / "projects" / product_id
    if not project_dir.exists():
        job.status = JobStatus.FAILED
        job.error_message = f"Project not found: {product_id}"
        job.progress = 0
        store.update(job)
        return

    try:
        llm, provider_name, model_name = _resolve_llm(
            params.get("llm_provider"), params.get("llm_model")
        )
    except HTTPException as e:
        job.status = JobStatus.FAILED
        job.error_message = e.detail or "LLM init failed"
        store.update(job)
        return
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error_message = str(e)[:300]
        store.update(job)
        return

    try:
        store_vec = _get_or_build_store(product_id, project_dir)
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error_message = f"Vector store failed: {str(e)[:200]}"
        store.update(job)
        return

    try:
        sheet, factsheet_path = _load_or_extract_factsheet(project_dir, llm, store_vec)
    except RuntimeError as e:
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        store.update(job)
        return

    audit_path_str = str(project_dir / "output" / "audit.json") if (project_dir / "output" / "audit.json").exists() else ""

    job.progress = 30
    store.update(job)

    try:
        drafts, metadata = generate_web_content(
            store=store_vec,
            llm=llm,
            sheet=sheet,
            product_id=product_id,
            tone=params.get("tone", "neutral"),
            length=params.get("length", "medium"),
            audience=params.get("audience", "ops_manager"),
            llm_provider_name=provider_name,
            llm_model_name=model_name,
            factsheet_path=factsheet_path,
            audit_path=audit_path_str,
        )
    except (RateLimitError, APIStatusError) as e:
        err = str(e)
        job.status = JobStatus.FAILED
        job.error_message = f"API quota/error: {err[:200]}"
        store.update(job)
        return
    except APIError as e:
        job.status = JobStatus.FAILED
        job.error_message = f"LLM API error: {str(e)[:200]}"
        store.update(job)
        return
    except Exception as e:
        logger.exception("Web content generation failed")
        job.status = JobStatus.FAILED
        job.error_message = str(e)[:300]
        store.update(job)
        return

    job.progress = 100
    job.status = JobStatus.SUCCEEDED
    job.drafts = drafts.model_dump(mode="json")
    job.metadata = metadata.model_dump(mode="json")
    job.error_message = None
    store.update(job)

    web_content_dir = project_dir / "web_content"
    web_content_dir.mkdir(parents=True, exist_ok=True)
    drafts_path = web_content_dir / "web_content_drafts.json"
    try:
        payload = GenerateWebContentResponse(drafts=drafts, metadata=metadata)
        with open(drafts_path, "w", encoding="utf-8") as f:
            json.dump(payload.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Failed to persist web content drafts: %s", e)

    params_hash = hashlib.sha256(
        f"{product_id}|{params.get('tone','')}|{params.get('length','')}|{params.get('audience','')}|{params.get('llm_provider','')}|{params.get('llm_model','')}".encode()
    ).hexdigest()[:32]
    try:
        from pda.drafts import get_drafts_store
        drafts_store = get_drafts_store()
        drafts_store.save(
            product_id=product_id,
            params_hash=params_hash,
            tone=params.get("tone", "neutral"),
            length=params.get("length", "medium"),
            audience=params.get("audience", "ops_manager"),
            drafts_json=drafts.model_dump(mode="json"),
        )
    except Exception as e:
        logger.warning("Failed to persist drafts to DB: %s", e)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/products/{product_id}/generate-content",
    response_model=GenerateContentJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start web content generation (async)",
    description=(
        "Creates a generation job and returns immediately. Poll GET /api/generation-jobs/{job_id} "
        "for status and drafts. Idempotent: same product_id + params returns existing job if queued/running."
    ),
)
async def generate_web_content_endpoint(
    product_id: str,
    request: GenerateWebContentRequest,
    background_tasks: BackgroundTasks,
):
    """Start async web content generation — returns job_id for polling."""

    project_dir = settings.data_dir / "projects" / product_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Product/project not found: {product_id}")

    if not list(project_dir.glob("*.pdf")):
        raise HTTPException(status_code=400, detail="No PDFs found in project. Run ingestion first.")

    try:
        _resolve_llm(request.llm_provider, request.llm_model)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM init failed: {str(e)[:200]}")

    idem_key = _idempotency_key(product_id, request)
    job_store = get_job_store()

    existing = job_store.get_by_idempotency_key(idem_key)
    if existing and existing.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        return GenerateContentJobResponse(
            job_id=existing.job_id,
            status=existing.status.value,
        )

    params = {
        "tone": request.tone,
        "length": request.length,
        "audience": request.audience,
        "llm_provider": request.llm_provider,
        "llm_model": request.llm_model,
    }

    job = GenerationJob(
        job_id=_new_job_id(),
        product_id=product_id,
        idempotency_key=idem_key,
        status=JobStatus.QUEUED,
        progress=0,
        params=params,
    )
    job_store.create(job)

    background_tasks.add_task(_run_generation_task, job.job_id, product_id, params)

    return GenerateContentJobResponse(job_id=job.job_id, status=job.status.value)


@router.get(
    "/generation-jobs/{job_id}",
    response_model=GenerationJobStatusResponse,
    summary="Get generation job status",
    description="Poll this endpoint for job status. Returns drafts when status is succeeded.",
)
async def get_generation_job(job_id: str):
    """Return job status, progress, and drafts (when ready)."""
    job_store = get_job_store()
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    from pda.schemas.web_content_schemas import WebContentDrafts, GenerationMetadata

    drafts = None
    if job.drafts:
        drafts = WebContentDrafts.model_validate(job.drafts)

    metadata = None
    if job.metadata:
        metadata = GenerationMetadata.model_validate(job.metadata)

    return GenerationJobStatusResponse(
        job_id=job.job_id,
        product_id=job.product_id,
        status=job.status.value,
        progress=job.progress,
        drafts=drafts,
        metadata=metadata,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else "",
        updated_at=job.updated_at.isoformat() if job.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Content drafts (fetch) & Export
# ---------------------------------------------------------------------------

def _load_drafts_for_product(product_id: str) -> "WebContentDrafts | None":
    """Load latest drafts from DB or file fallback."""
    from pda.schemas.web_content_schemas import WebContentDrafts
    drafts_store = get_drafts_store()
    data = drafts_store.get_latest(product_id)
    if data:
        return WebContentDrafts.model_validate(data)
    project_dir = settings.data_dir / "projects" / product_id
    drafts_path = project_dir / "web_content" / "web_content_drafts.json"
    if drafts_path.exists():
        with open(drafts_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        drafts_data = payload.get("drafts", payload)
        return WebContentDrafts.model_validate(drafts_data)
    return None


@router.get(
    "/products/{product_id}/content-drafts",
    summary="Get latest content drafts",
    description="Returns the latest web content drafts for display. 404 if none generated.",
    responses={404: {"description": "No drafts found for product"}},
)
async def get_content_drafts(product_id: str):
    """Return latest drafts JSON for a product."""
    drafts = _load_drafts_for_product(product_id)
    if not drafts:
        raise HTTPException(
            status_code=404,
            detail=f"No content drafts found for product {product_id}. Run generation first.",
        )
    return drafts.model_dump(mode="json")


@router.get(
    "/products/{product_id}/exports/content",
    summary="Export content as zip",
    description="Returns zip with drafts.json, landing-page.md, faq.md, use-cases/<slug>.md, comparisons/<slug>.md, seo.json. Each .md includes Evidence section.",
    responses={404: {"description": "No drafts found for product"}},
)
async def export_content(
    product_id: str,
    format: str = "zip",
):
    """Export web content drafts as zip file."""
    if format != "zip":
        raise HTTPException(status_code=400, detail="Only format=zip is supported")

    drafts = _load_drafts_for_product(product_id)
    if not drafts:
        raise HTTPException(
            status_code=404,
            detail=f"No content drafts found for product {product_id}. Run generation first.",
        )

    from pda.content_pack.export_content import build_content_zip


    zip_bytes = build_content_zip(drafts)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="content-{product_id}.zip"'},
    )
