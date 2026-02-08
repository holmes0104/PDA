"""Tests for chunker."""

import pytest
from pda.ingest.chunker import chunk_document, chunk_single_text
from pda.schemas.models import ChunkSource


def test_chunk_document_returns_document_chunks(sample_pdf_path):
    from pda.ingest.pdf_parser import parse_pdf
    pages = parse_pdf(sample_pdf_path)
    chunks = chunk_document(pages, source_file="sample.pdf", source_type=ChunkSource.PDF)
    assert len(chunks) >= 1
    for ch in chunks:
        assert ch.chunk_id.startswith("pdf-p")
        assert ch.source_file == "sample.pdf"
        assert ch.source_type == ChunkSource.PDF
        assert ch.page_number is not None
        assert ch.text
        assert ch.char_offset_start >= 0
        assert ch.char_offset_end >= ch.char_offset_start
        assert ch.token_count >= 1


def test_chunk_document_chunk_ids_unique(sample_pdf_path):
    from pda.ingest.pdf_parser import parse_pdf
    pages = parse_pdf(sample_pdf_path)
    chunks = chunk_document(pages, source_file="x.pdf", source_type=ChunkSource.PDF)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunk_single_text():
    text = "This is a single paragraph of content. " * 20
    chunks = chunk_single_text(text, source_file="https://example.com", source_type=ChunkSource.URL)
    assert len(chunks) >= 1
    assert chunks[0].source_type == ChunkSource.URL
    assert chunks[0].chunk_id.startswith("url-")
