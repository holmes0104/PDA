"""PDF text extraction with page metadata using pdfplumber."""

from pathlib import Path

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
