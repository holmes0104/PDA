"""Pytest configuration and shared fixtures."""

import pytest
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PDF_PATH = FIXTURES_DIR / "sample.pdf"

# Test docs directory for integration tests
TEST_DOCS_DIR = Path(__file__).parent.parent / "data" / "test_docs"


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


def _create_test_docs():
    """Generate 2-3 sample PDFs into data/test_docs/ for integration testing.

    PDF 1 — Product brochure (with headings for Overview / Installation /
             Troubleshooting / Technical Data and a spec table).
    PDF 2 — Technical manual (multi-page, with acronyms and spec table).
    PDF 3 — Minimal brochure (single page, few fields).
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        from reportlab.lib.units import inch
    except ImportError:
        pytest.skip("reportlab not installed")

    TEST_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # ── PDF 1: Full product brochure ─────────────────────────────────
    doc1 = SimpleDocTemplate(str(TEST_DOCS_DIR / "brochure_full.pdf"), pagesize=letter)
    styles = getSampleStyleSheet()
    story1 = []

    story1.append(Paragraph("HMT330 Humidity & Temperature Transmitter", styles["Title"]))
    story1.append(Spacer(1, 12))

    story1.append(Paragraph("Overview", styles["Heading1"]))
    story1.append(Paragraph(
        "The HMT330 is a high-accuracy humidity and temperature transmitter designed for "
        "demanding industrial environments. Manufactured by Vaisala. Model number HMT330.",
        styles["BodyText"],
    ))
    story1.append(Spacer(1, 8))

    story1.append(Paragraph("Key Features", styles["Heading2"]))
    story1.append(Paragraph(
        "- Measurement range: 0 to 100 %RH, -70 to +180 °C. "
        "- Accuracy: ±1 %RH (0-90 %RH at 15-25 °C). "
        "- IP65 rated housing. "
        "- Multiple analog and digital output options.",
        styles["BodyText"],
    ))
    story1.append(Spacer(1, 8))

    story1.append(Paragraph("Technical Data", styles["Heading1"]))
    spec_data = [
        ["Parameter", "Value", "Unit", "Conditions"],
        ["Humidity range", "0 ... 100", "%RH", ""],
        ["Humidity accuracy", "±1", "%RH", "0-90 %RH at 15-25 °C"],
        ["Temperature range", "-70 ... +180", "°C", "Probe dependent"],
        ["Response time", "8", "s", "at 20 °C, 90% response"],
        ["Operating voltage", "10 ... 35", "VDC", ""],
        ["Weight", "350", "g", "Without cable"],
    ]
    t1 = Table(spec_data, colWidths=[2 * inch, 1.5 * inch, 0.8 * inch, 2 * inch])
    t1.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    story1.append(t1)
    story1.append(Spacer(1, 12))

    story1.append(Paragraph("Installation", styles["Heading1"]))
    story1.append(Paragraph(
        "Mount the transmitter using the supplied bracket. Connect power supply (10-35 VDC) "
        "and signal cables. For duct mounting, use the optional mounting flange.",
        styles["BodyText"],
    ))
    story1.append(Spacer(1, 8))

    story1.append(Paragraph("Troubleshooting", styles["Heading1"]))
    story1.append(Paragraph(
        "If readings are unstable, check the probe for contamination. Error code E01 indicates "
        "sensor failure. Error code E02 indicates communication timeout. Contact Vaisala support.",
        styles["BodyText"],
    ))
    story1.append(Spacer(1, 8))

    story1.append(Paragraph("Certifications", styles["Heading2"]))
    story1.append(Paragraph(
        "CE, UL, CSA, ATEX/IECEx Zone 2. EMC compliant per EN 61326-1.",
        styles["BodyText"],
    ))
    story1.append(Spacer(1, 8))

    story1.append(Paragraph("Use Cases", styles["Heading2"]))
    story1.append(Paragraph(
        "Process industries: pharmaceutical manufacturing, semiconductor fabs, HVAC systems, "
        "meteorological stations, food processing facilities.",
        styles["BodyText"],
    ))

    doc1.build(story1)

    # ── PDF 2: Technical manual with acronyms ────────────────────────
    doc2 = SimpleDocTemplate(str(TEST_DOCS_DIR / "manual_technical.pdf"), pagesize=letter)
    story2 = []

    story2.append(Paragraph("DPT145 Dewpoint Transmitter — Technical Manual", styles["Title"]))
    story2.append(Spacer(1, 12))

    story2.append(Paragraph("Overview", styles["Heading1"]))
    story2.append(Paragraph(
        "The DPT145 measures dewpoint temperature in compressed air and gases. "
        "Manufactured by Vaisala. Category: industrial sensors.",
        styles["BodyText"],
    ))
    story2.append(Spacer(1, 8))

    story2.append(Paragraph("Acronyms and Abbreviations", styles["Heading1"]))
    story2.append(Paragraph(
        "RH — Relative Humidity. "
        "Td — Dewpoint Temperature. "
        "MTBF — Mean Time Between Failures. "
        "EMC — Electromagnetic Compatibility. "
        "ATEX — Atmosphères Explosibles.",
        styles["BodyText"],
    ))
    story2.append(Spacer(1, 8))

    story2.append(Paragraph("Technical Data", styles["Heading1"]))
    spec_data2 = [
        ["Specification", "Value"],
        ["Dewpoint range", "-80 ... +60 °Ctd"],
        ["Accuracy", "±2 °Ctd"],
        ["Response time (63%)", "< 30 s at -40 °Ctd"],
        ["Operating pressure", "up to 50 bar"],
        ["Power supply", "10 ... 35 VDC"],
        ["Output", "4 ... 20 mA, RS-485"],
    ]
    t2 = Table(spec_data2, colWidths=[2.5 * inch, 3 * inch])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    story2.append(t2)
    story2.append(Spacer(1, 12))

    story2.append(Paragraph("Installation", styles["Heading1"]))
    story2.append(Paragraph(
        "Install the probe directly into the process line via the supplied process fitting. "
        "Ensure the process temperature does not exceed sensor limits.",
        styles["BodyText"],
    ))
    story2.append(Spacer(1, 8))

    story2.append(Paragraph("Troubleshooting", styles["Heading1"]))
    story2.append(Paragraph(
        "Slow readings: check for condensation on the sensor. "
        "Error E10: replace sensor module. Updated 2024. Version 3.2.",
        styles["BodyText"],
    ))

    doc2.build(story2)

    # ── PDF 3: Minimal brochure ──────────────────────────────────────
    c3 = canvas.Canvas(str(TEST_DOCS_DIR / "brochure_minimal.pdf"), pagesize=letter)
    c3.setFont("Helvetica-Bold", 16)
    c3.drawString(100, 750, "MiniSensor 50")
    c3.setFont("Helvetica", 12)
    c3.drawString(100, 720, "A compact temperature sensor for general purpose use.")
    c3.drawString(100, 690, "Range: -40 to 125 °C. Accuracy: ±0.5 °C.")
    c3.drawString(100, 660, "Weight: 25 g. Interface: I2C.")
    c3.save()


@pytest.fixture(scope="session")
def sample_pdf_path():
    """Path to sample PDF; creates it once per session if missing."""
    if not SAMPLE_PDF_PATH.exists():
        _create_sample_pdf()
    return str(SAMPLE_PDF_PATH)


@pytest.fixture(scope="session")
def test_docs_dir():
    """Path to data/test_docs/ with 2-3 generated test PDFs."""
    if not (TEST_DOCS_DIR / "brochure_full.pdf").exists():
        _create_test_docs()
    return TEST_DOCS_DIR


@pytest.fixture(scope="session")
def brochure_full_path(test_docs_dir):
    """Path to the full brochure PDF with headings and tables."""
    return str(test_docs_dir / "brochure_full.pdf")


@pytest.fixture(scope="session")
def manual_technical_path(test_docs_dir):
    """Path to the technical manual PDF with acronyms."""
    return str(test_docs_dir / "manual_technical.pdf")


@pytest.fixture(scope="session")
def brochure_minimal_path(test_docs_dir):
    """Path to the minimal brochure PDF."""
    return str(test_docs_dir / "brochure_minimal.pdf")
