"""Ingestion pipeline: extract from PDF/URL, chunk, classify, tag, and save."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from pda.classify.classifier import classify_document
from pda.classify.content_tagger import tag_chunks
from pda.ingest.chunker import (
    chunk_document,
    chunk_pdf_tables,
    chunk_url_sections,
    chunk_url_tables,
    document_chunks_to_ingestion,
    document_chunks_to_normalized,
)
from pda.ingest.pdf_parser import PDFParseError, parse_pdf, parse_pdf_with_tables
from pda.ingest.url_scraper import scrape_url_structured, scrape_url_with_tables
from pda.schemas.ingestion_chunks import NormalizedChunk
from pda.schemas.models import ChunkSource, DocumentClassification, IngestionChunk


def run_ingestion(
    pdf_path: str,
    url: str | None,
    out_dir: Path,
) -> tuple[list[IngestionChunk], DocumentClassification]:
    """
    Run ingestion: extract from PDF (and optionally URL), chunk, classify the
    document, tag each chunk with a content_role (buyer / operational), and
    save chunks.jsonl + raw_extraction/ for debugging.

    pdf_path: required path to PDF.
    url: optional product page URL.
    Returns (list of IngestionChunk, DocumentClassification).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw_extraction"
    raw_dir.mkdir(exist_ok=True)

    chunks: list[IngestionChunk] = []
    normalized_chunks: list[NormalizedChunk] = []
    # We also keep the full-fidelity DocumentChunks for classification / tagging
    _doc_chunks = []

    # PDF (required)
    if pdf_path:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        logger.info("Parsing PDF: %s", pdf_path)
        pages, tables_by_page = parse_pdf_with_tables(str(pdf_path))
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

        # Save raw tables
        if tables_by_page:
            raw_tables_path = raw_dir / "pdf_tables.json"
            with open(raw_tables_path, "w", encoding="utf-8") as f:
                json.dump(
                    {str(k): v for k, v in tables_by_page.items()},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

        doc_chunks = chunk_document(pages, source_file=pdf_name, source_type=ChunkSource.PDF)
        _doc_chunks.extend(doc_chunks)
        chunks.extend(document_chunks_to_ingestion(doc_chunks))

        # Normalized text chunks
        normalized_chunks.extend(document_chunks_to_normalized(doc_chunks))

        # Table chunks
        table_chunks = chunk_pdf_tables(tables_by_page, source_file=pdf_name)
        normalized_chunks.extend(table_chunks)

    # URL
    if url:
        logger.info("Scraping URL: %s", url)
        try:
            html, sections, url_tables = scrape_url_with_tables(url)
        except Exception:
            # Fallback to non-table version
            html, sections = scrape_url_structured(url)
            url_tables = []

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

        if url_tables:
            raw_url_tables = raw_dir / "url_tables.json"
            with open(raw_url_tables, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {"heading_path": ut.heading_path, "rows": ut.rows, "caption": ut.caption}
                        for ut in url_tables
                    ],
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

        url_chunks = chunk_url_sections(sections, source_ref=url)
        chunks.extend(url_chunks)

        # URL table chunks (normalized)
        url_table_chunks = chunk_url_tables(url_tables, source_ref=url)
        normalized_chunks.extend(url_table_chunks)

    # --- Document classification & content-role tagging ---
    classification = classify_document(_doc_chunks)
    tag_chunks(_doc_chunks, classification)
    logger.info(
        "Document classified as %s (confidence=%.2f)",
        classification.document_type.value,
        classification.confidence,
    )

    # Propagate content_role back to IngestionChunks (by chunk_id)
    role_map = {c.chunk_id: c.content_role.value for c in _doc_chunks}
    buyer_count = 0
    operational_count = 0
    for ch in chunks:
        role = role_map.get(ch.chunk_id, "buyer")
        ch.__dict__["_content_role"] = role
        if role == "buyer":
            buyer_count += 1
        else:
            operational_count += 1
    logger.info(
        "Content tagging: %d buyer, %d operational chunks",
        buyer_count,
        operational_count,
    )

    # Propagate content_role to NormalizedChunks
    for nch in normalized_chunks:
        nch.content_role = role_map.get(nch.chunk_id, "buyer")

    # Write chunks.jsonl — legacy IngestionChunk format (with content_role)
    chunks_path = out_dir / "chunks.jsonl"
    with open(chunks_path, "w", encoding="utf-8") as f:
        for ch in chunks:
            data = ch.model_dump()
            data["content_role"] = ch.__dict__.get("_content_role", "buyer")
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    logger.info("Wrote %s (%d chunks)", chunks_path, len(chunks))

    # Write normalized_chunks.jsonl — new schema (text + table)
    norm_path = out_dir / "normalized_chunks.jsonl"
    with open(norm_path, "w", encoding="utf-8") as f:
        for nch in normalized_chunks:
            f.write(json.dumps(nch.model_dump(mode="json"), ensure_ascii=False) + "\n")
    logger.info("Wrote %s (%d normalized chunks)", norm_path, len(normalized_chunks))

    # Write classification result
    cls_path = out_dir / "classification.json"
    with open(cls_path, "w", encoding="utf-8") as f:
        json.dump(classification.model_dump(), f, indent=2, ensure_ascii=False)
    logger.info("Wrote %s", cls_path)

    return chunks, classification
