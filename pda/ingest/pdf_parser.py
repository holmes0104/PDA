"""PDF text extraction with page metadata using pdfplumber."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pdfplumber


class PDFParseError(Exception):
    """Raised when the PDF cannot be parsed (corrupt or invalid)."""


def parse_pdf(path: str) -> list[tuple[int, str]]:
    """
    Extract text from each page of a PDF.

    Returns a list of (page_number, text) tuples. Page numbers are 1-based.
    Raises FileNotFoundError if path does not exist; PDFParseError on invalid/corrupt PDFs.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    try:
        with pdfplumber.open(path) as pdf:
            result: list[tuple[int, str]] = []
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text()
                except Exception:
                    text = ""
                result.append((i, text or ""))
            return result
    except Exception as e:
        raise PDFParseError(f"Could not parse PDF {path}: {e}") from e


def parse_pdf_with_tables(
    path: str,
) -> tuple[list[tuple[int, str]], dict[int, list[list[list[Any]]]]]:
    """
    Extract text **and** tables from each page of a PDF.

    Returns:
        (pages, tables_by_page)
        - pages: list of (page_number, text) tuples (1-based).
        - tables_by_page: {page_number: [table, ...]} where each table is
          a list-of-rows (list[list[str|None]]).
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"PDF not found: {path_obj}")
    try:
        with pdfplumber.open(path_obj) as pdf:
            pages: list[tuple[int, str]] = []
            tables_by_page: dict[int, list[list[list[Any]]]] = {}
            for i, page in enumerate(pdf.pages, start=1):
                # Text
                try:
                    text = page.extract_text()
                except Exception:
                    text = ""
                pages.append((i, text or ""))

                # Tables
                try:
                    raw_tables = page.extract_tables() or []
                    if raw_tables:
                        tables_by_page[i] = raw_tables
                except Exception:
                    pass  # graceful: skip table extraction failures
            return pages, tables_by_page
    except Exception as e:
        raise PDFParseError(f"Could not parse PDF {path_obj}: {e}") from e
