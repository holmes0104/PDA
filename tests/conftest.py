"""Pytest configuration and shared fixtures."""

import pytest
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PDF_PATH = FIXTURES_DIR / "sample.pdf"


def _create_sample_pdf():
    """Create a minimal PDF with a few lines of text for parsing tests."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        pytest.skip("reportlab not installed")
    SAMPLE_PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(SAMPLE_PDF_PATH), pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(100, 750, "Sample Product Brochure")
    c.drawString(100, 720, "Product Name: TestWidget 3000")
    c.drawString(100, 690, "Key features: Fast, reliable, easy to use.")
    c.drawString(100, 660, "Specifications: Weight 2.5 kg. Dimensions 10 x 20 cm.")
    c.save()


@pytest.fixture(scope="session")
def sample_pdf_path():
    """Path to sample PDF; creates it once per session if missing."""
    if not SAMPLE_PDF_PATH.exists():
        _create_sample_pdf()
    return str(SAMPLE_PDF_PATH)
