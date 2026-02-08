# How to install and run the LLM Product Discoverability Auditor

## 1. Install Python (if needed)

If `python --version` in a terminal fails or opens the Microsoft Store:

- **Option A:** Install from [python.org](https://www.python.org/downloads/) — download "Windows installer (64-bit)", run it, and **check "Add python.exe to PATH"** before finishing.
- **Option B:** Install from Microsoft Store — search "Python 3.12" (or 3.11), install it. Then turn off the app execution alias that blocks the command: **Settings → Apps → Advanced app settings → App execution aliases** — set "App Installer" for `python.exe` and `python3.exe` to **Off**.

Close and reopen your terminal after installing.

## 2. Open a terminal in the project folder

- In File Explorer go to `C:\Users\holme\Documents\PDA`.
- In the address bar type `cmd` or `powershell` and press Enter, or right‑click in the folder and choose "Open in Terminal".

## 3. Create a virtual environment and install the app

Run these commands one by one:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

If you see an error about running scripts, run once (as Administrator if needed):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then run again:

```powershell
.venv\Scripts\Activate.ps1
pip install -e .
```

Optional (for tests that need a sample PDF):

```powershell
pip install reportlab
```

## 4. Set your API key

1. Copy the example env file:
   ```powershell
   copy .env.example .env
   ```
2. Open `.env` in Notepad or your editor.
3. Set either:
   - `PDA_LLM_PROVIDER=openai` and `OPENAI_API_KEY=sk-your-key-here`, or  
   - `PDA_LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=sk-ant-your-key-here`

Save the file.

## 5. How to run the app

**From the same terminal where you activated the venv:**

```powershell
# Activate venv (if not already)
.venv\Scripts\Activate.ps1

# Run an audit (replace with your PDF path)
pda audit "C:\path\to\your\brochure.pdf"
```

**Examples:**

```powershell
# PDF only — report goes to ./output
pda audit brochure.pdf

# PDF + one product URL
pda audit brochure.pdf --url "https://example.com/product"

# PDF + two URLs (compare variants in the report)
pda audit brochure.pdf --url "https://example.com/v1" --url "https://example.com/v2"

# Use Anthropic instead of OpenAI
pda audit brochure.pdf --provider anthropic

# Custom output folder
pda audit brochure.pdf --output "C:\Users\holme\Documents\my-report"

# Markdown report only (no HTML)
pda audit brochure.pdf --format md
```

**Where to find the report:**

- Default: `C:\Users\holme\Documents\PDA\output\report.md` and `report.html`.
- With `--output "C:\...\my-report"`: inside that folder.

Open `report.html` in a browser or `report.md` in any text editor.

## 6. Run tests (optional)

```powershell
.venv\Scripts\Activate.ps1
pytest tests/ -v
```

## Quick reference: open app from this folder

1. Open Terminal in `PDA` (e.g. type `powershell` in the folder’s address bar).
2. Run: `.venv\Scripts\Activate.ps1`
3. Run: `pda audit "path\to\your\file.pdf"`
