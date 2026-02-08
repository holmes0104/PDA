# One-time setup: create venv and install PDA and dependencies.
# Run in PowerShell from the PDA folder: .\install.ps1

$projectRoot = $PSScriptRoot
Set-Location $projectRoot

$py = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $v = & $cmd --version 2>&1
        if ($v -match "Python 3\.(1[1-9]|[2-9][0-9])") { $py = $cmd; break }
    } catch {}
}
if (-not $py) {
    Write-Host "Python 3.11+ not found. Install from https://www.python.org/downloads/ and add to PATH." -ForegroundColor Red
    exit 1
}

Write-Host "Using: $py" -ForegroundColor Cyan
& $py -m venv .venv
if ($LASTEXITCODE -ne 0) { Write-Host "venv failed"; exit 1 }

$activate = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
& $activate
pip install --upgrade pip
pip install -e .
pip install reportlab

Write-Host ""
Write-Host "Install done. Next:" -ForegroundColor Green
Write-Host "  1. copy .env.example .env"
Write-Host "  2. Edit .env and set OPENAI_API_KEY or ANTHROPIC_API_KEY"
Write-Host "  3. Run: .\.venv\Scripts\Activate.ps1"
Write-Host "  4. Run: pda audit `"path\to\your\brochure.pdf`""
Write-Host "  Or: .\run_audit.ps1 `"path\to\your\brochure.pdf`""
