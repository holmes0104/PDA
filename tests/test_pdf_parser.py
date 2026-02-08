"""Tests for PDF parser."""

import pytest
from pda.ingest.pdf_parser import parse_pdf


def test_parse_pdf_returns_list_of_tuples(sample_pdf_path):
    result = parse_pdf(sample_pdf_path)
    assert isinstance(result, list)
    assert len(result) >= 1
    for item in result:
        assert isinstance(item, tuple)
        assert len(item) == 2
        page_num, text = item
        assert isinstance(page_num, int)
        assert page_num >= 1
        assert isinstance(text, str)


def test_parse_pdf_extracts_text(sample_pdf_path):
    result = parse_pdf(sample_pdf_path)
    full_text = " ".join(t[1] for t in result)
    assert "Sample" in full_text or "Product" in full_text or "TestWidget" in full_text


def test_parse_pdf_file_not_found():
    with pytest.raises(FileNotFoundError, match="PDF not found"):
        parse_pdf("nonexistent.pdf")
