"""Download API routes for serving generated files."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from pda.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


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
        "audit_json": project_dir / "output" / "audit.json",
    }

    # Content pack files can be in output/ (from audit) or outputs/ (from CLI content-pack)
    content_pack_files = {
        "product_page_outline": "product_page_outline.md",
        "faq": "faq.md",
        "comparison": "comparison.md",
        "jsonld": "jsonld_product_skeleton.json",
    }

    valid_types = set(file_map.keys()) | set(content_pack_files.keys()) | {"verifier_report"}
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
    }
    suffix = file_path.suffix.lstrip(".")
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )
