"""Audit API routes."""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

try:
    from openai import APIError, APIStatusError, RateLimitError
except ImportError:  # openai not installed — define stubs so except clauses never match
    APIError = type("APIError", (Exception,), {})
    APIStatusError = type("APIStatusError", (Exception,), {})
    RateLimitError = type("RateLimitError", (Exception,), {})

from pda.audit import run_critic_pass, run_gap_analysis
from pda.audit.scorecard import build_scorecard
from pda.classify import classify_document, tag_chunks
from pda.config import get_settings
from pda.content_pack.generator import generate_content_pack
from pda.extract.fact_extractor import extract_fact_sheet
from pda.ingest.chunker import chunk_document
from pda.ingest.pdf_parser import PDFParseError, parse_pdf
from pda.llm import get_provider
from pda.report.html import render_html_report, write_html_report
from pda.report.markdown import render_markdown_report, write_markdown_report
from pda.schemas.models import ChunkSource
from pda.simulate.prompt_sim import run_prompt_simulation
from pda.verifier import run_verifier_audit_pipeline, write_verifier_report

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


class AuditRequest(BaseModel):
    project_id: str
    url: Optional[list[str]] = None
    allow_unsafe: bool = False
    llm_provider: Optional[str] = None   # "openai" | "anthropic" — overrides server default
    llm_model: Optional[str] = None      # e.g. "gpt-4o", "claude-3-5-sonnet-20241022"


class AuditResponse(BaseModel):
    project_id: str
    report_md_path: str
    report_html_path: str
    audit_json_path: str
    verifier_report_path: str


@router.post("/audit", response_model=AuditResponse, status_code=status.HTTP_201_CREATED)
async def run_audit(request: AuditRequest):
    """Run full audit pipeline."""
    project_dir = settings.data_dir / "projects" / request.project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {request.project_id}")

    pdf_paths = list(project_dir.glob("*.pdf"))
    if not pdf_paths:
        raise HTTPException(status_code=400, detail="No PDFs found in project")

    pdf_path = pdf_paths[0]  # Use first PDF
    pdf_name = pdf_path.name

    try:
        pages = parse_pdf(str(pdf_path))
    except (PDFParseError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=f"PDF parse error: {str(e)}")

    chunks = chunk_document(pages, source_file=pdf_name, source_type=ChunkSource.PDF)

    url_chunks = []
    if request.url:
        from pda.ingest.url_scraper import scrape_url
        for u in request.url:
            try:
                text = scrape_url(u)
                uc = chunk_document([(0, text)], source_file=u, source_type=ChunkSource.URL)
                url_chunks.extend(uc)
            except Exception as e:
                logger.warning("URL scraping skipped for %s: %s", u, e)
        chunks.extend(url_chunks)

    # --- Document classification & content-role tagging ---
    classification = classify_document(chunks)
    tag_chunks(chunks, classification)
    logger.info(
        "Document classified as %s (confidence=%.2f, buyer=%d, operational=%d)",
        classification.document_type.value,
        classification.confidence,
        sum(1 for c in chunks if c.content_role.value == "buyer"),
        sum(1 for c in chunks if c.content_role.value == "operational"),
    )
    # Persist classification alongside project artefacts
    import json as _json
    cls_path = project_dir / "classification.json"
    with open(cls_path, "w", encoding="utf-8") as _f:
        _json.dump(classification.model_dump(), _f, indent=2, ensure_ascii=False)

    # Extract facts — honour request-level LLM overrides
    provider_name = (request.llm_provider or settings.pda_llm_provider).lower()
    if provider_name == "openai":
        api_key = settings.openai_api_key
        default_model = settings.pda_openai_model
    else:
        api_key = settings.anthropic_api_key
        default_model = settings.pda_anthropic_model
    model = request.llm_model or default_model
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"API key not configured for provider '{provider_name}'. Please set {'OPENAI_API_KEY' if provider_name == 'openai' else 'ANTHROPIC_API_KEY'} in .env",
        )
    llm = get_provider(provider_name, api_key=api_key, model=model)
    logger.info("Audit using provider=%s model=%s", provider_name, model)
    try:
        fact_sheet = extract_fact_sheet(chunks, llm)
    except (RateLimitError, APIStatusError) as e:
        status_code = getattr(e, "status_code", None)
        err_msg = str(e)
        if status_code == 402 or "insufficient_quota" in err_msg.lower() or "payment" in err_msg.lower() or "429" in err_msg:
            logger.error("API quota/payment error: %s", err_msg)
            raise HTTPException(
                status_code=402,
                detail=f"API quota/payment issue: {err_msg[:200]}. Please check your billing at https://platform.openai.com/settings/organization/billing",
            )
        logger.exception("API error during fact extraction")
        raise HTTPException(status_code=500, detail=f"API error during fact extraction: {err_msg[:300]}")
    except APIError as e:
        err_msg = str(e)
        logger.exception("OpenAI API error during fact extraction")
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {err_msg[:300]}")
    except Exception as e:
        err_msg = str(e)
        logger.exception("Fact extraction failed")
        raise HTTPException(status_code=500, detail=f"Fact extraction failed: {err_msg[:300]}")

    # Scorecard
    try:
        prompt_result = run_prompt_simulation(chunks, llm, source_description=pdf_name)
    except (RateLimitError, APIStatusError) as e:
        status_code = getattr(e, "status_code", None)
        err_msg = str(e)
        if status_code == 402 or "insufficient_quota" in err_msg.lower() or "payment" in err_msg.lower() or "429" in err_msg:
            logger.error("API quota/payment error: %s", err_msg)
            raise HTTPException(
                status_code=402,
                detail=f"API quota/payment issue: {err_msg[:200]}. Please check your billing at https://platform.openai.com/settings/organization/billing",
            )
        logger.exception("API error during prompt simulation")
        raise HTTPException(status_code=500, detail=f"API error during prompt simulation: {err_msg[:300]}")
    except APIError as e:
        err_msg = str(e)
        logger.exception("OpenAI API error during prompt simulation")
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {err_msg[:300]}")
    except Exception as e:
        err_msg = str(e)
        logger.exception("Prompt simulation failed")
        raise HTTPException(status_code=500, detail=f"Prompt simulation failed: {err_msg[:300]}")

    scorecard = build_scorecard(
        fact_sheet, chunks,
        buyer_answerability_score=prompt_result.average_grounding,
        classification=classification,
    )

    # Gap analysis
    findings = run_gap_analysis(fact_sheet, scorecard)
    scorecard.findings = findings
    try:
        findings = run_critic_pass(findings, chunks, llm)
    except (RateLimitError, APIStatusError) as e:
        status_code = getattr(e, "status_code", None)
        err_msg = str(e)
        if status_code == 402 or "insufficient_quota" in err_msg.lower() or "payment" in err_msg.lower() or "429" in err_msg:
            logger.error("API quota/payment error: %s", err_msg)
            raise HTTPException(
                status_code=402,
                detail=f"API quota/payment issue: {err_msg[:200]}. Please check your billing at https://platform.openai.com/settings/organization/billing",
            )
        logger.exception("API error during critic pass")
        raise HTTPException(status_code=500, detail=f"API error during critic pass: {err_msg[:300]}")
    except APIError as e:
        err_msg = str(e)
        logger.exception("OpenAI API error during critic pass")
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {err_msg[:300]}")
    except Exception as e:
        err_msg = str(e)
        logger.exception("Critic pass failed")
        raise HTTPException(status_code=500, detail=f"Critic pass failed: {err_msg[:300]}")

    # Content pack (dict for report)
    content_pack = generate_content_pack(fact_sheet)

    # Verifier
    verifier_result = run_verifier_audit_pipeline(
        fact_sheet,
        findings=findings,
        content_pack=content_pack,
        prompt_results=[prompt_result],
        chunks=chunks,
    )

    output_dir = project_dir / "output"
    output_dir.mkdir(exist_ok=True)

    # Also write individual content-pack files for download
    from pda.content_pack.content_pack_from_factsheet import (
        build_product_page_outline,
        build_faq_md,
        build_comparison_md,
        build_jsonld_skeleton,
    )
    from pda.schemas.factsheet_schema import ProductFactSheet as FactsheetSchema
    # Build a minimal factsheet-schema version for content pack file generation
    try:
        fs_data = {
            "product_name": fact_sheet.product_name.value if hasattr(fact_sheet.product_name, "value") else str(fact_sheet.product_name),
            "product_category": fact_sheet.category.value if hasattr(fact_sheet.category, "value") else str(fact_sheet.category),
            "primary_use_cases": [uc.value if hasattr(uc, "value") else str(uc) for uc in (fact_sheet.use_cases or [])],
            "target_buyer_roles": [fact_sheet.target_audience.value if hasattr(fact_sheet.target_audience, "value") else str(fact_sheet.target_audience)] if fact_sheet.target_audience else [],
            "key_specs": [],
            "constraints": [],
            "differentiators": [],
            "certifications_standards": [c.value if hasattr(c, "value") else str(c) for c in (fact_sheet.certifications or [])],
            "integrations_interfaces": [c.value if hasattr(c, "value") else str(c) for c in (fact_sheet.compatibility or [])],
            "maintenance_calibration": [],
            "source_coverage_summary": "NOT_FOUND",
        }
        # Add specs
        for k, fv in (fact_sheet.specifications or {}).items():
            val = fv.value if hasattr(fv, "value") else str(fv)
            fs_data["key_specs"].append({"name": k, "value": str(val), "unit": "", "conditions": "", "evidence_chunk_ids": []})
        fs_schema = FactsheetSchema.model_validate(fs_data)

        content_pack_dir = output_dir
        content_pack_dir.mkdir(parents=True, exist_ok=True)
        outline_path = content_pack_dir / "product_page_outline.md"
        outline_path.write_text(build_product_page_outline(fs_schema, findings), encoding="utf-8")
        faq_path = content_pack_dir / "faq.md"
        faq_path.write_text(build_faq_md(fs_schema, findings), encoding="utf-8")
        comparison_path = content_pack_dir / "comparison.md"
        comparison_path.write_text(build_comparison_md(fs_schema), encoding="utf-8")
        import json as json_mod
        jsonld_path = content_pack_dir / "jsonld_product_skeleton.json"
        jsonld_path.write_text(json_mod.dumps(build_jsonld_skeleton(fs_schema, findings), indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Could not write content pack files: %s", e)

    verifier_path = output_dir / "verifier_report.md"
    write_verifier_report(verifier_result, verifier_path)

    if verifier_result.has_blocked and not request.allow_unsafe:
        raise HTTPException(
            status_code=400,
            detail="Verifier found blocked issues. Review verifier_report.md or set allow_unsafe=true",
        )

    # Reports
    md_content = render_markdown_report(
        fact_sheet=fact_sheet,
        scorecard=scorecard,
        findings=findings,
        content_pack=content_pack,
        prompt_results=[prompt_result],
        pdf_path=str(pdf_path),
        url_list=request.url,
    )
    md_path = output_dir / "report.md"
    write_markdown_report(md_path, md_content)

    html_content = render_html_report(
        fact_sheet=fact_sheet,
        scorecard=scorecard,
        findings=findings,
        content_pack=content_pack,
        prompt_results=[prompt_result],
        pdf_path=str(pdf_path),
        url_list=request.url,
    )
    html_path = output_dir / "report.html"
    write_html_report(html_path, html_content)

    # Audit JSON (includes classification for downstream consumers)
    audit_path = output_dir / "audit.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "classification": classification.model_dump(),
                "scorecard": scorecard.model_dump(mode="json"),
                "findings": [x.model_dump(mode="json") for x in findings],
            },
            f,
            indent=2,
            default=str,  # fallback: stringify datetime and other non-serialisable types
        )

    return AuditResponse(
        project_id=request.project_id,
        report_md_path=str(md_path),
        report_html_path=str(html_path),
        audit_json_path=str(audit_path),
        verifier_report_path=str(verifier_path),
    )
