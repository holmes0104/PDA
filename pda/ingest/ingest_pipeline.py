"""Ingestion pipeline: extract from PDF/URL, chunk, and save."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from pda.ingest.chunker import chunk_document, chunk_url_sections, document_chunks_to_ingestion
from pda.ingest.pdf_parser import PDFParseError, parse_pdf
from pda.ingest.url_scraper import scrape_url_structured
from pda.schemas.models import ChunkSource, IngestionChunk


def run_ingestion(
    pdf_path: str,
    url: str | None,
    out_dir: Path,
) -> list[IngestionChunk]:
    """
    Run ingestion: extract from PDF (and optionally URL), chunk, save chunks.jsonl
    and raw_extraction/ for debugging.
    pdf_path: required path to PDF.
    url: optional product page URL.
    Returns list of IngestionChunk.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw_extraction"
    raw_dir.mkdir(exist_ok=True)

    chunks: list[IngestionChunk] = []

    # PDF (required)
    if pdf_path:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        logger.info("Parsing PDF: %s", pdf_path)
        pages = parse_pdf(str(pdf_path))
        pdf_name = pdf_path.name

        # Save raw extraction for debugging
        raw_pdf = raw_dir / "pdf_pages.json"
        with open(raw_pdf, "w", encoding="utf-8") as f:
            json.dump(
                [{"page_num": p, "text": t} for p, t in pages],
                f,
                indent=2,
                ensure_ascii=False,
            )

        doc_chunks = chunk_document(pages, source_file=pdf_name, source_type=ChunkSource.PDF)
        chunks.extend(document_chunks_to_ingestion(doc_chunks))

    # URL
    if url:
        logger.info("Scraping URL: %s", url)
        html, sections = scrape_url_structured(url)

        # Save raw extraction for debugging
        raw_html = raw_dir / "url_page.html"
        with open(raw_html, "w", encoding="utf-8") as f:
            f.write(html)
        raw_sections = raw_dir / "url_sections.json"
        with open(raw_sections, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "heading_path": s.heading_path,
                        "section_title": s.section_title,
                        "text": s.text[:500] + "..." if len(s.text) > 500 else s.text,
                    }
                    for s in sections
                ],
                f,
                indent=2,
                ensure_ascii=False,
            )

        url_chunks = chunk_url_sections(sections, source_ref=url)
        chunks.extend(url_chunks)

    # Write chunks.jsonl
    chunks_path = out_dir / "chunks.jsonl"
    with open(chunks_path, "w", encoding="utf-8") as f:
        for ch in chunks:
            f.write(ch.model_dump_json() + "\n")
    logger.info("Wrote %s (%d chunks)", chunks_path, len(chunks))

    return chunks
