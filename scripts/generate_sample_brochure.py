"""Generate a minimal sample PDF brochure for the demo. No external licensing; project-owned content."""

from pathlib import Path


def main() -> None:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        raise SystemExit("Install reportlab: pip install reportlab")

    root = Path(__file__).resolve().parent.parent
    out = root / "sample" / "brochure.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out), pagesize=letter)
    c.setFont("Helvetica", 14)
    c.drawString(100, 750, "Sample Product Brochure")
    c.setFont("Helvetica", 12)
    c.drawString(100, 720, "Product Name: DemoWidget 100")
    c.drawString(100, 690, "Category: Industrial sensors")
    c.drawString(100, 660, "Key features: High accuracy, IP67 rated, -40 to 85 C operating range.")
    c.drawString(100, 630, "Specifications: Weight 0.5 kg. Dimensions 50 x 30 x 20 mm.")
    c.drawString(100, 600, "Use cases: Process monitoring, quality control, R&D.")
    c.drawString(100, 570, "Target users: Engineers, plant managers, system integrators.")
    c.save()
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
