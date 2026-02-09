"""Download API routes for serving generated files (including PDF export)."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from pda.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.post("/download/{project_id}/generate_pdf")
async def generate_pdf(project_id: str):
    """Generate a PDF from the existing HTML report on disk."""
    project_dir = settings.data_dir / "projects" / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    html_path = project_dir / "output" / "report.html"
    if not html_path.exists():
        raise HTTPException(
            status_code=404,
            detail="HTML report not found. Run the audit first.",
        )

    try:
        from pda.report.pdf import write_pdf_report
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="PDF export requires the xhtml2pdf package. Install with: pip install xhtml2pdf",
        )

    html_content = html_path.read_text(encoding="utf-8")
    pdf_path = project_dir / "output" / "report.pdf"

    try:
        write_pdf_report(pdf_path, html_content)
    except Exception as e:
        logger.exception("PDF generation failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)[:300]}")

    return {"status": "ok", "pdf_path": str(pdf_path)}


@router.get("/download/{project_id}/{file_type}")
async def download_file(project_id: str, file_type: str):
    """Download a file from a project."""
    project_dir = settings.data_dir / "projects" / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    # Map file types to actual file paths
    # For content pack files, check both "output/" (audit route) and "outputs/" (CLI/simulate route)
    file_map = {
        "chunks": project_dir / "chunks.jsonl",
        "factsheet": project_dir / "factsheet.json",
        "factsheet_provenance": project_dir / "factsheet_provenance.json",
        "report_md": project_dir / "output" / "report.md",
        "report_html": project_dir / "output" / "report.html",
        "report_pdf": project_dir / "output" / "report.pdf",
        "audit_json": project_dir / "output" / "audit.json",
    }

    # Content pack files can be in output/ (from audit) or outputs/ (from CLI content-pack)
    content_pack_files = {
        "product_page_outline": "product_page_outline.md",
        "faq": "faq.md",
        "comparison": "comparison.md",
        "jsonld": "jsonld_product_skeleton.json",
    }

    # LLM-ready content pack files (in content_pack/ directory)
    llm_content_pack_files = {
        "canonical_answers": "canonical_answers.md",
        "content_pack_faq": "faq.md",
        "selection_guidance": "selection_guidance.md",
        "content_pack_json": "content_pack.json",
        "content_pack_manifest": "manifest.json",
    }

    # Web content drafts (in web_content/ directory)
    web_content_files = {
        "web_content_drafts": "web_content_drafts.json",
    }

    valid_types = set(file_map.keys()) | set(content_pack_files.keys()) | set(llm_content_pack_files.keys()) | set(web_content_files.keys()) | {"verifier_report"}
    if file_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Unknown file type: {file_type}")

    # Verifier report can be in output/ (from audit) or project root (from factsheet)
    if file_type == "verifier_report":
        file_path = project_dir / "output" / "verifier_report.md"
        if not file_path.exists():
            file_path = project_dir / "verifier_report.md"
    elif file_type in content_pack_files:
        filename = content_pack_files[file_type]
        # Check output/ first (audit route), then outputs/ (CLI/simulate route)
        file_path = project_dir / "output" / filename
        if not file_path.exists():
            file_path = project_dir / "outputs" / filename
    elif file_type in llm_content_pack_files:
        filename = llm_content_pack_files[file_type]
        file_path = project_dir / "content_pack" / filename
    elif file_type in web_content_files:
        filename = web_content_files[file_type]
        file_path = project_dir / "web_content" / filename
    elif file_type.startswith("usecase_"):
        # Dynamic use-case page files: usecase_uc-1, usecase_uc-2, etc.
        file_path = project_dir / "content_pack" / f"{file_type}.md"
    else:
        file_path = file_map[file_type]

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_type}")

    # Determine media type
    media_types = {
        "json": "application/json",
        "jsonl": "application/jsonl",
        "md": "text/markdown",
        "html": "text/html",
        "pdf": "application/pdf",
    }
    suffix = file_path.suffix.lstrip(".")
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )
