"""Tests for ingestion layer: chunk_id stability, metadata presence, empty-text handling."""

import json
import tempfile
from pathlib import Path

import pytest

from pda.ingest.chunker import (
    chunk_document,
    chunk_url_sections,
    document_chunks_to_ingestion,
)
from pda.ingest.ingest_pipeline import run_ingestion
from pda.ingest.pdf_parser import parse_pdf
from pda.ingest.url_scraper import URLSection, _parse_markdown_sections
from pda.schemas.models import ChunkSource, IngestionChunk


def test_chunk_id_stability_pdf(sample_pdf_path):
    """Same PDF produces same chunk_ids on repeated runs."""
    pages1 = parse_pdf(sample_pdf_path)
    chunks1 = chunk_document(pages1, source_file="sample.pdf", source_type=ChunkSource.PDF)
    ing1 = document_chunks_to_ingestion(chunks1)

    pages2 = parse_pdf(sample_pdf_path)
    chunks2 = chunk_document(pages2, source_file="sample.pdf", source_type=ChunkSource.PDF)
    ing2 = document_chunks_to_ingestion(chunks2)

    ids1 = [c.chunk_id for c in ing1]
    ids2 = [c.chunk_id for c in ing2]
    assert ids1 == ids2, "chunk_ids must be stable across runs"


def test_chunk_id_stability_url():
    """Same URL sections produce same chunk_ids on repeated runs."""
    sections = [
        URLSection(heading_path="Intro", section_title="Intro", text="Some intro text."),
        URLSection(heading_path="Features / Specs", section_title="Specs", text="Spec details here."),
    ]
    ch1 = chunk_url_sections(sections, source_ref="https://example.com/product")
    ch2 = chunk_url_sections(sections, source_ref="https://example.com/product")

    ids1 = [c.chunk_id for c in ch1]
    ids2 = [c.chunk_id for c in ch2]
    assert ids1 == ids2, "chunk_ids must be stable for URL sections"


def test_metadata_presence_pdf(sample_pdf_path):
    """PDF chunks have required metadata: chunk_id, source_type, source_ref, page_num, section_title."""
    pages = parse_pdf(sample_pdf_path)
    chunks = chunk_document(pages, source_file="sample.pdf", source_type=ChunkSource.PDF)
    ing = document_chunks_to_ingestion(chunks)
    assert len(ing) >= 1
    for ch in ing:
        assert ch.chunk_id
        assert ch.source_type == "pdf"
        assert ch.source_ref == "sample.pdf"
        assert ch.page_num is not None
        assert ch.page_num >= 1
        assert ch.heading_path is None
        assert ch.text


def test_metadata_presence_url():
    """URL chunks have required metadata: chunk_id, source_type, source_ref, heading_path."""
    sections = [
        URLSection(heading_path="Features", section_title="Features", text="Feature list here."),
    ]
    ing = chunk_url_sections(sections, source_ref="https://example.com")
    assert len(ing) >= 1
    for ch in ing:
        assert ch.chunk_id
        assert ch.source_type == "url"
        assert ch.source_ref == "https://example.com"
        assert ch.page_num is None
        assert ch.heading_path == "Features"
        assert ch.section_title == "Features"
        assert ch.text


def test_empty_text_handling_pdf(sample_pdf_path):
    """Empty text chunks are skipped in ingestion output."""
    # Chunk a page with mostly empty content - we skip empty in document_chunks_to_ingestion
    pages = [(1, ""), (2, "Only page 2 has content.")]
    chunks = chunk_document(pages, source_file="empty.pdf", source_type=ChunkSource.PDF)
    ing = document_chunks_to_ingestion(chunks)
    assert len(ing) >= 1
    for ch in ing:
        assert ch.text.strip(), "No chunk should have empty text"


def test_empty_text_handling_url():
    """Empty sections are skipped in URL chunking."""
    sections = [
        URLSection(heading_path="Empty", section_title="Empty", text="   \n\n   "),
        URLSection(heading_path="Full", section_title="Full", text="Content here."),
    ]
    ing = chunk_url_sections(sections, source_ref="https://example.com")
    assert len(ing) == 1
    assert ing[0].text == "Content here."
    assert ing[0].section_title == "Full"


def test_ingest_end_to_end(sample_pdf_path):
    """Ingestion runs end-to-end and produces chunks.jsonl and raw_extraction/."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        chunks, _classification = run_ingestion(pdf_path=sample_pdf_path, url=None, out_dir=out_dir)

        assert (out_dir / "chunks.jsonl").exists()
        assert (out_dir / "raw_extraction" / "pdf_pages.json").exists()

        with open(out_dir / "chunks.jsonl", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == len(chunks)
        for line in lines:
            obj = json.loads(line)
            assert "chunk_id" in obj
            assert "source_type" in obj
            assert "source_ref" in obj
            assert "text" in obj
            assert obj["source_type"] == "pdf"
            assert obj["page_num"] is not None


def test_parse_markdown_sections():
    """Markdown parsing yields sections by heading."""
    md = """# Intro

Intro paragraph here.

## Features

Feature one. Feature two.

### Specs

Spec details.
"""
    sections = _parse_markdown_sections(md)
    assert len(sections) >= 2
    paths = [s.heading_path for s in sections if s.heading_path]
    assert "Intro" in paths or any("Intro" in p for p in paths)
