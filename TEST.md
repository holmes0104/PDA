# Test the tool — where to open the report

The app runs **on your PC**. There is no web URL; you test it by running an audit and opening the report file.

## 1. Finish install (if you haven’t)

In PowerShell, from the PDA folder:

```powershell
cd C:\Users\holme\Documents\PDA
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install reportlab
```

## 2. Run one audit

Use any PDF (e.g. a product brochure or the sample from tests):

```powershell
.\.venv\Scripts\Activate.ps1
pda audit "C:\Users\holme\Documents\PDA\tests\fixtures\sample.pdf"
```

*(Create the sample PDF first with: `pytest tests/test_pdf_parser.py -v` — that creates `tests/fixtures/sample.pdf`. Or use any PDF path you have.)*

## 3. Open the report (your test “environment”)

After the audit finishes, open the report in your browser:

**Report (HTML):**  
[file:///C:/Users/holme/Documents/PDA/output/report.html](file:///C:/Users/holme/Documents/PDA/output/report.html)

**Output folder (index page):**  
[file:///C:/Users/holme/Documents/PDA/output/index.html](file:///C:/Users/holme/Documents/PDA/output/index.html)

- You can paste either link into your browser’s address bar, or  
- In File Explorer go to `C:\Users\holme\Documents\PDA\output` and double‑click `report.html` (after an audit) or `index.html`.

The first time you open `report.html` it will only show content after you’ve run at least one `pda audit ...`.
