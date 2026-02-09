"""PDF report: convert styled HTML report to PDF using xhtml2pdf."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def render_pdf_report(html_content: str) -> bytes:
    """Convert an HTML report string to PDF bytes.

    Uses xhtml2pdf (pisa) which is a pure-Python HTML-to-PDF converter.
    Falls back gracefully if xhtml2pdf is not installed.
    """
    try:
        from xhtml2pdf import pisa  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError(
            "xhtml2pdf is not installed. Run: pip install xhtml2pdf"
        )

    from io import BytesIO

    buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=buffer)

    if pisa_status.err:
        logger.error("xhtml2pdf returned %d error(s)", pisa_status.err)
        raise RuntimeError(f"PDF generation failed with {pisa_status.err} error(s)")

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def write_pdf_report(output_path: str | Path, html_content: str) -> None:
    """Generate a PDF from HTML and write to *output_path*."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = render_pdf_report(html_content)
    Path(output_path).write_bytes(pdf_bytes)
