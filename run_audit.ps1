# Run PDA audit — usage: .\run_audit.ps1 "C:\path\to\brochure.pdf"
# Or edit $pdfPath below and run: .\run_audit.ps1

param(
    [Parameter(Mandatory=$false)]
    [string]$pdfPath = ""
)

$projectRoot = $PSScriptRoot
Set-Location $projectRoot

$venvActivate = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Host "Virtual environment not found. Run these first:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  pip install -e ."
    exit 1
}

& $venvActivate
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ([string]::IsNullOrWhiteSpace($pdfPath)) {
    Write-Host "Usage: .\run_audit.ps1 `"C:\path\to\brochure.pdf`""
    Write-Host "Or: pda audit `"C:\path\to\brochure.pdf`""
    exit 0
}

pda audit $pdfPath
exit $LASTEXITCODE
