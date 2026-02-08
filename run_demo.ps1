# Run full PDA demo: ingest -> factsheet -> audit -> content-pack -> simulate -> verify.
# From project root, with venv activated and .env configured.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Sample = "sample"
$Pdf = Join-Path $Sample "brochure.pdf"

if (-not (Test-Path $Pdf)) {
    Write-Host "Generating $Pdf (requires reportlab)..."
    python scripts/generate_sample_brochure.py
}

Write-Host "=== 1. Ingest ==="
pda ingest --pdf $Pdf --out $Sample

Write-Host "=== 2. Factsheet ==="
pda factsheet --project $Sample --out (Join-Path $Sample "factsheet.json") --allow-unsafe

Write-Host "=== 3. Audit ==="
pda audit $Pdf --output (Join-Path $Sample "output") --allow-unsafe

Write-Host "=== 4. Content-pack ==="
pda content-pack --project $Sample --factsheet (Join-Path $Sample "factsheet.json") --audit (Join-Path $Sample "output\audit.json") --out (Join-Path $Sample "outputs") --allow-unsafe

Write-Host "=== 5. Simulate ==="
pda simulate --project $Sample --factsheet (Join-Path $Sample "factsheet.json") --variantA (Join-Path $Sample "outputs\product_page_outline.md") --out (Join-Path $Sample "outputs")

Write-Host "=== 6. Verify ==="
pda verify --project $Sample --factsheet (Join-Path $Sample "factsheet.json") --audit (Join-Path $Sample "output\audit.json") --out (Join-Path $Sample "outputs")

Write-Host "Demo complete. See $Sample\output and $Sample\outputs."
