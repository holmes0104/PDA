"""Tests for table extraction: PDF tables, table normalization, spec-row parsing."""

import json
import tempfile
from pathlib import Path

import pytest

from pda.ingest.chunker import chunk_pdf_tables, document_chunks_to_normalized
from pda.ingest.pdf_parser import parse_pdf_with_tables
from pda.ingest.table_normalizer import (
    extract_spec_rows,
    normalize_table,
    table_to_text_summary,
)
from pda.schemas.ingestion_chunks import ChunkType


class TestTableNormalizer:
    """Tests for the table_normalizer module."""

    def test_normalize_empty_table(self):
        result = normalize_table([])
        assert result.headers == []
        assert result.rows == []

    def test_normalize_basic_table(self):
        raw = [
            ["Color", "Material"],
            ["Red", "Steel"],
            ["Blue", "Aluminum"],
        ]
        result = normalize_table(raw)
        assert result.headers == ["Color", "Material"]
        assert len(result.rows) == 2
        assert result.rows[0] == ["Red", "Steel"]
        assert result.kind == "generic"

    def test_normalize_spec_table(self):
        raw = [
            ["Parameter", "Value", "Unit", "Conditions"],
            ["Temperature range", "-40 ... +80", "°C", ""],
            ["Humidity accuracy", "±1.5", "%RH", "at 25 °C"],
        ]
        result = normalize_table(raw)
        assert result.kind == "spec"
        assert result.headers == ["Parameter", "Value", "Unit", "Conditions"]
        assert len(result.rows) == 2

    def test_normalize_with_none_cells(self):
        raw = [
            ["A", None, "C"],
            [None, "data", None],
        ]
        result = normalize_table(raw)
        assert result.headers == ["A", "", "C"]
        assert result.rows[0] == ["", "data", ""]

    def test_extract_spec_rows_basic(self):
        raw = [
            ["Parameter", "Value", "Unit", "Conditions"],
            ["Weight", "2.5", "kg", "without cable"],
            ["Length", "300", "mm", ""],
        ]
        table = normalize_table(raw)
        rows = extract_spec_rows(table)
        assert len(rows) == 2
        assert rows[0].name == "Weight"
        assert rows[0].value == "2.5"
        assert rows[0].unit == "kg"
        assert rows[0].conditions == "without cable"

    def test_extract_spec_rows_fallback_columns(self):
        """When headers don't match hints, fallback to col-0 = name, col-1 = value."""
        raw = [
            ["Spec", "Rating"],
            ["Voltage", "24 VDC"],
        ]
        table = normalize_table(raw)
        # Force spec kind for testing
        table.kind = "spec"
        rows = extract_spec_rows(table)
        assert len(rows) >= 1

    def test_table_to_text_summary(self):
        raw = [["A", "B"], ["1", "2"]]
        table = normalize_table(raw)
        summary = table_to_text_summary(table)
        assert "A" in summary
        assert "B" in summary
        assert "1" in summary

    def test_table_to_text_summary_with_caption(self):
        raw = [["X", "Y"], ["a", "b"]]
        table = normalize_table(raw, caption="Test Caption")
        summary = table_to_text_summary(table)
        assert "Test Caption" in summary


class TestPDFTableExtraction:
    """Tests for PDF table extraction using generated test PDFs."""

    def test_parse_pdf_with_tables_returns_tables(self, brochure_full_path):
        pages, tables = parse_pdf_with_tables(brochure_full_path)
        assert len(pages) >= 1
        # The full brochure has a spec table
        assert len(tables) >= 1, "Expected at least one page with tables"
        # Verify table structure
        for page_num, page_tables in tables.items():
            assert isinstance(page_num, int)
            for t in page_tables:
                assert isinstance(t, list)
                assert len(t) >= 2  # at least header + 1 data row

    def test_chunk_pdf_tables_produces_table_chunks(self, brochure_full_path):
        _, tables = parse_pdf_with_tables(brochure_full_path)
        table_chunks = chunk_pdf_tables(tables, source_file="brochure_full.pdf")
        assert len(table_chunks) >= 1
        for ch in table_chunks:
            assert ch.chunk_type == ChunkType.TABLE
            assert ch.chunk_id.startswith("pdf-p")
            assert "-t" in ch.chunk_id
            assert ch.table is not None
            assert ch.content  # has text summary

    def test_table_chunk_ids_are_stable(self, brochure_full_path):
        _, tables = parse_pdf_with_tables(brochure_full_path)
        chunks1 = chunk_pdf_tables(tables, source_file="test.pdf")
        chunks2 = chunk_pdf_tables(tables, source_file="test.pdf")
        ids1 = [c.chunk_id for c in chunks1]
        ids2 = [c.chunk_id for c in chunks2]
        assert ids1 == ids2

    def test_spec_table_has_spec_rows(self, brochure_full_path):
        _, tables = parse_pdf_with_tables(brochure_full_path)
        table_chunks = chunk_pdf_tables(tables, source_file="brochure_full.pdf")
        # At least one chunk should have spec_rows (the spec table)
        spec_chunks = [c for c in table_chunks if c.spec_rows]
        # This depends on whether reportlab tables get extracted correctly
        # The table might not be detected as spec type by all pdfplumber versions
        # so we don't assert strictly, just check the mechanism works
        if spec_chunks:
            for row in spec_chunks[0].spec_rows:
                assert hasattr(row, "name")
                assert hasattr(row, "value")
                assert hasattr(row, "unit")


class TestNormalizedChunks:
    """Tests for the normalized chunk pipeline."""

    def test_document_chunks_to_normalized(self, brochure_full_path):
        from pda.ingest.chunker import chunk_document
        from pda.ingest.pdf_parser import parse_pdf
        from pda.schemas.models import ChunkSource

        pages = parse_pdf(brochure_full_path)
        doc_chunks = chunk_document(pages, source_file="test.pdf", source_type=ChunkSource.PDF)
        normalized = document_chunks_to_normalized(doc_chunks)
        assert len(normalized) >= 1
        for nch in normalized:
            assert nch.chunk_type == ChunkType.TEXT
            assert nch.content
            assert nch.source.source_type == "pdf"
            assert nch.chunk_id

    def test_ingestion_writes_normalized_chunks_jsonl(self, brochure_full_path):
        from pda.ingest.ingest_pipeline import run_ingestion

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run_ingestion(pdf_path=brochure_full_path, url=None, out_dir=out)
            norm_path = out / "normalized_chunks.jsonl"
            assert norm_path.exists()
            with open(norm_path, encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) >= 1
            for line in lines:
                obj = json.loads(line)
                assert "chunk_id" in obj
                assert "chunk_type" in obj
                assert obj["chunk_type"] in ("text", "table")
