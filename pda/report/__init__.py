"""Stage 7 — report assembly (Markdown, HTML, and PDF)."""

from pda.report.markdown import render_markdown_report
from pda.report.html import render_html_report

__all__ = ["render_markdown_report", "render_html_report"]

# PDF export is optional — depends on xhtml2pdf
try:
    from pda.report.pdf import render_pdf_report, write_pdf_report
    __all__ += ["render_pdf_report", "write_pdf_report"]
except ImportError:
    pass
