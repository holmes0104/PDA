"""Unified pipeline API — upload once, get everything.

POST /api/pipeline
  → Accepts PDF (+ optional URL), returns { job_id } immediately.
  → Background task runs the full chain:
      Ingest → Factsheet → Audit → Web-Content Drafts

GET /api/pipeline-jobs/{job_id}
  → Poll for status, stage, progress, and final results.

The frontend only needs these two endpoints for the entire workflow.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

try:
    from openai import APIError, APIStatusError, RateLimitError
except ImportError:
    APIError = type("APIError", (Exception,), {})
    APIStatusError = type("APIStatusError", (Exception,), {})
    RateLimitError = type("RateLimitError", (Exception,), {})

from pda.config import get_settings
from pda.jobs import GenerationJob, JobStatus, get_job_store, _new_job_id
from pda.llm import get_provider

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class PipelineStartResponse(BaseModel):
    """Immediate response for POST /api/pipeline."""

    job_id: str = ""
    project_id: str = ""
    status: str = "queued"


class PipelineStageInfo(BaseModel):
    """Human-readable pipeline-stage metadata stored inside the job."""

    stage: str = "queued"  # queued | ingest | factsheet | audit | content | done
    stage_detail: str = ""
    has_factsheet: bool = False
    has_audit: bool = False
    has_content: bool = False


class PipelineJobStatusResponse(BaseModel):
    """Response for GET /api/pipeline-jobs/{job_id}."""

    job_id: str = ""
    product_id: str = ""
    status: str = ""
    progress: int = 0
    stage: str = ""
    stage_detail: str = ""
    has_factsheet: bool = False
    has_audit: bool = False
    has_content: bool = False
    drafts: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_llm(llm_provider: str | None, llm_model: str | None):
    """Return (provider_instance, provider_name, model_name)."""
    provider_name = (llm_provider or settings.pda_llm_provider).lower()
    if provider_name == "openai":
        api_key = settings.openai_api_key
        default_model = settings.pda_openai_model
    else:
        api_key = settings.anthropic_api_key
        default_model = settings.pda_anthropic_model

    if not api_key:
        raise ValueError(
            f"API key not configured for provider '{provider_name}'."
        )
    model = llm_model or default_model
    return get_provider(provider_name, api_key=api_key, model=model), provider_name, model


def _update_stage(
    job: GenerationJob,
    store,
    *,
    progress: int,
    stage: str,
    detail: str,
    has_factsheet: bool = False,
    has_audit: bool = False,
    has_content: bool = False,
) -> None:
    """Update job with pipeline-stage metadata."""
    job.progress = progress
    job.status = JobStatus.RUNNING
    meta = job.metadata or {}
    meta["stage"] = stage
    meta["stage_detail"] = detail
    meta["has_factsheet"] = has_factsheet
    meta["has_audit"] = has_audit
    meta["has_content"] = has_content
    job.metadata = meta
    store.update(job)


def _fail(job: GenerationJob, store, message: str) -> None:
    job.status = JobStatus.FAILED
    job.error_message = message[:500]
    store.update(job)


# ---------------------------------------------------------------------------
# Background task — full pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(  # noqa: C901 (complexity unavoidable for a multi-stage orchestrator)
    job_id: str,
    project_id: str,
    params: dict[str, Any],
) -> None:
    """Execute Ingest → Factsheet → Audit → Content Drafts in sequence."""
    job_store = get_job_store()
    job = job_store.get(job_id)
    if not job or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        return

    project_dir = settings.data_dir / "projects" / project_id

    # --- LLM ----------------------------------------------------------
    try:
        llm, provider_name, model_name = _resolve_llm(
            params.get("llm_provider"), params.get("llm_model"),
        )
    except (ValueError, Exception) as e:
        _fail(job, job_store, f"LLM initialisation failed: {e}")
        return

    # ==================================================================
    # Stage 1 — INGEST (parse PDF, chunk, classify)
    # ==================================================================
    _update_stage(job, job_store, progress=5, stage="ingest",
                  detail="Parsing and chunking the PDF…")

    from pda.ingest.pdf_parser import PDFParseError, parse_pdf
    from pda.ingest.chunker import chunk_document
    from pda.classify import classify_document, tag_chunks
    from pda.schemas.models import ChunkSource

    pdf_paths = list(project_dir.glob("*.pdf"))
    if not pdf_paths:
        _fail(job, job_store, "No PDFs found in project directory.")
        return

    try:
        all_chunks = []
        for pdf_path in pdf_paths:
            pages = parse_pdf(str(pdf_path))
            all_chunks.extend(
                chunk_document(pages, source_file=pdf_path.name,
                               source_type=ChunkSource.PDF)
            )
    except (PDFParseError, FileNotFoundError, Exception) as e:
        _fail(job, job_store, f"PDF parsing failed: {e}")
        return

    if not all_chunks:
        _fail(job, job_store, "No text chunks could be extracted from the PDF.")
        return

    # Optional URL scraping
    url = params.get("url")
    if url:
        try:
            from pda.ingest.url_scraper import scrape_url
            text = scrape_url(url)
            url_chunks = chunk_document(
                [(0, text)], source_file=url, source_type=ChunkSource.URL,
            )
            all_chunks.extend(url_chunks)
        except Exception as e:
            logger.warning("URL scraping skipped for %s: %s", url, e)

    # Classify & tag
    classification = classify_document(all_chunks)
    tag_chunks(all_chunks, classification)
    cls_path = project_dir / "classification.json"
    try:
        with open(cls_path, "w", encoding="utf-8") as f:
            json.dump(classification.model_dump(), f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    _update_stage(job, job_store, progress=12, stage="ingest",
                  detail=f"Ingested {len(all_chunks)} chunks. Building vector store…")

    # --- Vector store --------------------------------------------------
    from pda.store import get_vector_store

    backend = settings.pda_vector_backend
    persist_dir: str | None = None
    if backend == "chroma":
        chroma_dir = settings.chroma_dir / project_id
        chroma_dir.mkdir(parents=True, exist_ok=True)
        persist_dir = str(chroma_dir)

    try:
        vec_store = get_vector_store(
            backend=backend,
            collection_name="pda_factsheet",
            persist_directory=persist_dir,
            embedding_model=settings.pda_embedding_model,
            openai_api_key=settings.openai_api_key,
            database_url=settings.pda_database_url,
            project_id=project_id,
        )
        vec_store.add_chunks(all_chunks)
    except Exception as e:
        _fail(job, job_store, f"Vector store indexing failed: {e}")
        return

    # ==================================================================
    # Stage 2 — FACTSHEET EXTRACTION
    # ==================================================================
    _update_stage(job, job_store, progress=18, stage="factsheet",
                  detail="Extracting structured product fact sheet…")

    factsheet_path = project_dir / "factsheet.json"
    try:
        from pda.extract.factsheet_extractor import extract_product_fact_sheet
        sheet, provenance = extract_product_fact_sheet(vec_store, llm)
        with open(factsheet_path, "w", encoding="utf-8") as f:
            json.dump(sheet.model_dump(), f, indent=2)
        prov_path = project_dir / "factsheet_provenance.json"
        with open(prov_path, "w", encoding="utf-8") as f:
            json.dump(provenance, f, indent=2)
    except (RateLimitError, APIStatusError) as e:
        _fail(job, job_store, f"API quota/error during factsheet extraction: {str(e)[:300]}")
        return
    except Exception as e:
        _fail(job, job_store, f"Factsheet extraction failed: {str(e)[:300]}")
        return

    # Verifier on factsheet
    try:
        from pda.verifier import run_verifier_factsheet, write_verifier_report
        verifier_result = run_verifier_factsheet(sheet, provenance)
        verifier_path = project_dir / "verifier_report.md"
        write_verifier_report(verifier_result, verifier_path)
    except Exception as e:
        logger.warning("Factsheet verifier failed (non-fatal): %s", e)

    _update_stage(job, job_store, progress=32, stage="factsheet",
                  detail="Fact sheet extracted.",
                  has_factsheet=True)

    # ==================================================================
    # Stage 3 — AUDIT (scorecard, gap analysis, critic, reports)
    # ==================================================================
    _update_stage(job, job_store, progress=35, stage="audit",
                  detail="Running quality audit (scorecard & gap analysis)…",
                  has_factsheet=True)

    output_dir = project_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from pda.extract.fact_extractor import extract_fact_sheet
        from pda.simulate.prompt_sim import run_prompt_simulation
        from pda.audit.scorecard import build_scorecard
        from pda.audit import run_gap_analysis, run_critic_pass
        from pda.content_pack.generator import generate_content_pack as gen_cp_legacy
        from pda.verifier import run_verifier_audit_pipeline
        from pda.report.html import render_html_report, write_html_report
        from pda.report.markdown import render_markdown_report, write_markdown_report

        pdf_name = pdf_paths[0].name

        # Legacy fact sheet for audit pipeline (uses models.ProductFactSheet)
        legacy_fact_sheet = extract_fact_sheet(all_chunks, llm)

        _update_stage(job, job_store, progress=42, stage="audit",
                      detail="Running buyer-prompt simulation…",
                      has_factsheet=True)

        prompt_result = run_prompt_simulation(
            all_chunks, llm, source_description=pdf_name,
        )

        scorecard = build_scorecard(
            legacy_fact_sheet, all_chunks,
            buyer_answerability_score=prompt_result.average_grounding,
            classification=classification,
        )

        _update_stage(job, job_store, progress=50, stage="audit",
                      detail="Running gap analysis & critic pass…",
                      has_factsheet=True)

        findings = run_gap_analysis(legacy_fact_sheet, scorecard)
        scorecard.findings = findings

        try:
            findings = run_critic_pass(findings, all_chunks, llm)
        except Exception as e:
            logger.warning("Critic pass failed (non-fatal): %s", e)

        content_pack = gen_cp_legacy(legacy_fact_sheet)

        verifier_audit = run_verifier_audit_pipeline(
            legacy_fact_sheet,
            findings=findings,
            content_pack=content_pack,
            prompt_results=[prompt_result],
            chunks=all_chunks,
        )
        verifier_audit_path = output_dir / "verifier_report.md"
        write_verifier_report(verifier_audit, verifier_audit_path)

        _update_stage(job, job_store, progress=58, stage="audit",
                      detail="Writing audit reports…",
                      has_factsheet=True)

        # Reports
        md_content = render_markdown_report(
            fact_sheet=legacy_fact_sheet,
            scorecard=scorecard,
            findings=findings,
            content_pack=content_pack,
            prompt_results=[prompt_result],
            pdf_path=str(pdf_paths[0]),
            url_list=[url] if url else None,
        )
        write_markdown_report(output_dir / "report.md", md_content)

        html_content = render_html_report(
            fact_sheet=legacy_fact_sheet,
            scorecard=scorecard,
            findings=findings,
            content_pack=content_pack,
            prompt_results=[prompt_result],
            pdf_path=str(pdf_paths[0]),
            url_list=[url] if url else None,
        )
        write_html_report(output_dir / "report.html", html_content)

        audit_path = output_dir / "audit.json"
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "classification": classification.model_dump(),
                    "scorecard": scorecard.model_dump(mode="json"),
                    "findings": [x.model_dump(mode="json") for x in findings],
                },
                f, indent=2, default=str,
            )

        # Content-pack files for download (best-effort)
        try:
            from pda.content_pack.content_pack_from_factsheet import (
                build_product_page_outline,
                build_faq_md,
                build_comparison_md,
                build_jsonld_skeleton,
            )
            from pda.schemas.factsheet_schema import ProductFactSheet as FSSchema

            fs_data: dict[str, Any] = {
                "product_name": getattr(legacy_fact_sheet.product_name, "value", str(legacy_fact_sheet.product_name)),
                "product_category": getattr(legacy_fact_sheet.category, "value", str(legacy_fact_sheet.category)),
                "primary_use_cases": [getattr(uc, "value", str(uc)) for uc in (legacy_fact_sheet.use_cases or [])],
                "target_buyer_roles": [getattr(legacy_fact_sheet.target_audience, "value", str(legacy_fact_sheet.target_audience))] if legacy_fact_sheet.target_audience else [],
                "key_specs": [],
                "constraints": [],
                "differentiators": [],
                "certifications_standards": [getattr(c, "value", str(c)) for c in (legacy_fact_sheet.certifications or [])],
                "integrations_interfaces": [getattr(c, "value", str(c)) for c in (legacy_fact_sheet.compatibility or [])],
                "maintenance_calibration": [],
                "source_coverage_summary": "NOT_FOUND",
            }
            for k, fv in (legacy_fact_sheet.specifications or {}).items():
                val = fv.value if hasattr(fv, "value") else str(fv)
                fs_data["key_specs"].append({"name": k, "value": str(val), "unit": "", "conditions": "", "evidence_chunk_ids": []})
            fs_schema = FSSchema.model_validate(fs_data)

            (output_dir / "product_page_outline.md").write_text(
                build_product_page_outline(fs_schema, findings), encoding="utf-8",
            )
            (output_dir / "faq.md").write_text(
                build_faq_md(fs_schema, findings), encoding="utf-8",
            )
            (output_dir / "comparison.md").write_text(
                build_comparison_md(fs_schema), encoding="utf-8",
            )
            (output_dir / "jsonld_product_skeleton.json").write_text(
                json.dumps(build_jsonld_skeleton(fs_schema, findings), indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Could not write content-pack files: %s", e)

    except (RateLimitError, APIStatusError) as e:
        _fail(job, job_store, f"API quota/error during audit: {str(e)[:300]}")
        return
    except Exception as e:
        logger.exception("Audit stage failed")
        _fail(job, job_store, f"Audit failed: {str(e)[:300]}")
        return

    _update_stage(job, job_store, progress=65, stage="audit",
                  detail="Audit complete.",
                  has_factsheet=True, has_audit=True)

    # ==================================================================
    # Stage 4 — WEB-CONTENT DRAFTS
    # ==================================================================
    _update_stage(job, job_store, progress=68, stage="content",
                  detail="Generating web-ready content drafts (landing, FAQ, use-cases, comparisons, SEO)…",
                  has_factsheet=True, has_audit=True)

    try:
        from pda.content_pack.web_content_generator import (
            generate_web_content,
            load_factsheet,
        )
        from pda.schemas.web_content_schemas import (
            GenerateWebContentResponse,
        )

        strict_sheet = load_factsheet(factsheet_path)

        drafts, gen_metadata = generate_web_content(
            store=vec_store,
            llm=llm,
            sheet=strict_sheet,
            product_id=project_id,
            tone=params.get("tone", "neutral"),
            length=params.get("length", "medium"),
            audience=params.get("audience", "ops_manager"),
            llm_provider_name=provider_name,
            llm_model_name=model_name,
            factsheet_path=str(factsheet_path),
            audit_path=str(output_dir / "audit.json"),
        )

        # Persist drafts to disk
        web_dir = project_dir / "web_content"
        web_dir.mkdir(parents=True, exist_ok=True)
        drafts_path = web_dir / "web_content_drafts.json"
        payload = GenerateWebContentResponse(drafts=drafts, metadata=gen_metadata)
        with open(drafts_path, "w", encoding="utf-8") as f:
            json.dump(payload.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        # Persist to DB drafts store (best-effort)
        try:
            from pda.drafts import get_drafts_store
            drafts_store = get_drafts_store()
            params_hash = hashlib.sha256(
                f"{project_id}|{params.get('tone', '')}|{params.get('length', '')}|{params.get('audience', '')}".encode()
            ).hexdigest()[:32]
            drafts_store.save(
                product_id=project_id,
                params_hash=params_hash,
                tone=params.get("tone", "neutral"),
                length=params.get("length", "medium"),
                audience=params.get("audience", "ops_manager"),
                drafts_json=drafts.model_dump(mode="json"),
            )
        except Exception as e:
            logger.warning("Failed to persist drafts to DB: %s", e)

    except (RateLimitError, APIStatusError) as e:
        _fail(job, job_store, f"API quota/error during content generation: {str(e)[:300]}")
        return
    except Exception as e:
        logger.exception("Content generation stage failed")
        _fail(job, job_store, f"Content generation failed: {str(e)[:300]}")
        return

    # ==================================================================
    # DONE — mark job as succeeded
    # ==================================================================
    job.progress = 100
    job.status = JobStatus.SUCCEEDED
    job.error_message = None
    job.drafts = drafts.model_dump(mode="json")
    meta = job.metadata or {}
    meta.update({
        "stage": "done",
        "stage_detail": "Pipeline complete — all artifacts ready.",
        "has_factsheet": True,
        "has_audit": True,
        "has_content": True,
        "content_metadata": gen_metadata.model_dump(mode="json"),
    })
    job.metadata = meta
    job_store.update(job)

    logger.info("Pipeline job %s completed for project %s", job_id, project_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/pipeline",
    response_model=PipelineStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start the full pipeline (upload → facts → audit → content)",
    description=(
        "Accepts a PDF upload (+ optional URL), saves it, and kicks off a "
        "background job that runs Ingest → Factsheet → Audit → Content Drafts. "
        "Poll GET /api/pipeline-jobs/{job_id} for progress."
    ),
)
async def start_pipeline(
    background_tasks: BackgroundTasks,
    pdf: UploadFile = File(..., description="PDF file to ingest"),
    url: Optional[str] = Form(None, description="Optional product page URL to scrape"),
    project_id: Optional[str] = Form(None, description="Optional project ID (auto-generated if omitted)"),
    llm_provider: Optional[str] = Form(None, description="LLM provider override (openai | anthropic)"),
    llm_model: Optional[str] = Form(None, description="LLM model override"),
    tone: str = Form("neutral", description="Content tone: neutral | technical | marketing"),
    length: str = Form("medium", description="Content length: short | medium | long"),
    audience: str = Form("ops_manager", description="Target audience: engineer | procurement | ops_manager"),
):
    """Upload a PDF and start the full pipeline — returns a job ID for polling."""

    # Validate PDF
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF.")

    content = await pdf.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum is {settings.max_upload_bytes // (1024 * 1024)} MB.",
        )

    # Project directory
    if not project_id:
        project_id = str(uuid.uuid4())

    project_dir = settings.data_dir / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = project_dir / pdf.filename
    with open(pdf_path, "wb") as f:
        f.write(content)

    # Validate LLM eagerly so the user gets a fast error
    try:
        _resolve_llm(llm_provider, llm_model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM init failed: {str(e)[:200]}")

    # Create job
    params = {
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "tone": tone,
        "length": length,
        "audience": audience,
        "url": url,
    }

    job = GenerationJob(
        job_id=_new_job_id(),
        product_id=project_id,
        idempotency_key=f"pipeline-{project_id}",
        status=JobStatus.QUEUED,
        progress=0,
        params=params,
        metadata={
            "stage": "queued",
            "stage_detail": "Pipeline job queued.",
            "has_factsheet": False,
            "has_audit": False,
            "has_content": False,
        },
    )
    job_store = get_job_store()
    job_store.create(job)

    background_tasks.add_task(_run_pipeline, job.job_id, project_id, params)

    logger.info("Pipeline job %s created for project %s", job.job_id, project_id)

    return PipelineStartResponse(
        job_id=job.job_id,
        project_id=project_id,
        status="queued",
    )


@router.get(
    "/pipeline-jobs/{job_id}",
    response_model=PipelineJobStatusResponse,
    summary="Poll pipeline job status",
    description="Returns current stage, progress, and results when the pipeline completes.",
)
async def get_pipeline_job(job_id: str):
    """Return pipeline job status, stage info, and drafts (when done)."""
    job_store = get_job_store()
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    meta = job.metadata or {}

    return PipelineJobStatusResponse(
        job_id=job.job_id,
        product_id=job.product_id,
        status=job.status.value,
        progress=job.progress,
        stage=meta.get("stage", ""),
        stage_detail=meta.get("stage_detail", ""),
        has_factsheet=meta.get("has_factsheet", False),
        has_audit=meta.get("has_audit", False),
        has_content=meta.get("has_content", False),
        drafts=job.drafts,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else "",
        updated_at=job.updated_at.isoformat() if job.updated_at else "",
    )
