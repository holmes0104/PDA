"""Stage 1 — document ingestion: PDF parsing, URL scraping, chunking."""

from pda.ingest.chunker import chunk_document, chunk_url_sections, document_chunks_to_ingestion
from pda.ingest.ingest_pipeline import run_ingestion
from pda.ingest.pdf_parser import parse_pdf
from pda.ingest.url_scraper import scrape_url, scrape_url_structured

__all__ = [
    "chunk_document",
    "chunk_url_sections",
    "document_chunks_to_ingestion",
    "parse_pdf",
    "run_ingestion",
    "scrape_url",
    "scrape_url_structured",
]
